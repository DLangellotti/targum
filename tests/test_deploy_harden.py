"""deploy/harden.sh, read off the text (targum-internal#9).

The script edits sshd and the firewall of the box, and the failure worth pinning is the
one that needs no box to see: an order. A drop-in sshd is told about before `sshd -t`
has read it, or a drop policy loaded before the rule that lets SSH through, is a
lock-out whose only warning is a session that stops answering. Both orders are in the
text, so they are asserted on the text.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"
SCRIPT = DEPLOY / "harden.sh"
WALL = DEPLOY / "nftables-targum-wall.conf"


def code(path: Path) -> list[str]:
    """The script's lines with comments and blank lines dropped, so an order asserted
    below is the order things run in and not the order the comments mention them."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def first(lines: list[str], pattern: str) -> int:
    for i, line in enumerate(lines):
        if re.search(pattern, line):
            return i
    raise AssertionError(f"nothing in harden.sh matches {pattern!r}")


@pytest.fixture(scope="module")
def script() -> list[str]:
    return code(SCRIPT)


def test_it_parses() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
def test_shellcheck_is_clean() -> None:
    subprocess.run(["shellcheck", str(SCRIPT)], check=True)


def test_it_stops_on_the_first_error(script: list[str]) -> None:
    assert "set -euo pipefail" in script


def test_sshd_is_checked_before_it_is_reloaded(script: list[str]) -> None:
    """The drop-in is written, `sshd -t` reads it, and only then is sshd reloaded."""
    written = first(script, r"put_file 0644 \"\$SSHD_DROPIN\"")
    checked = first(script, r"^if ! sshd -t; then")
    reloaded = first(script, r"^systemctl reload ssh")
    assert written < checked < reloaded


def test_a_rejected_sshd_config_is_taken_back_before_anything_else(script: list[str]) -> None:
    checked = first(script, r"^if ! sshd -t; then")
    assert script[checked + 1] == 'rm -f "$SSHD_DROPIN"'
    assert script[checked + 3].startswith("die ")


def test_sshd_is_never_restarted(script: list[str]) -> None:
    """A restart drops the listener; a reload leaves every open session where it is."""
    assert not any(re.search(r"(restart|stop|kill)\s+(ssh|sshd)\b", line) for line in script)
    assert not any(re.search(r"systemctl\s+restart\s+ssh", line) for line in script)


def test_passwords_go_off_only_where_root_has_a_key(script: list[str]) -> None:
    key_check = first(script, r"/root/\.ssh/authorized_keys")
    written = first(script, r"put_file 0644 \"\$SSHD_DROPIN\"")
    assert key_check < written
    assert script[key_check + 1].startswith("|| die ")


def test_the_drop_in_says_keys_only() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    block = text.split("<<'SSHD'", 1)[1].split("\nSSHD\n", 1)[0]
    assert "PasswordAuthentication no" in block
    assert "PermitRootLogin prohibit-password" in block


def test_the_wall_lets_ssh_in_before_anything_else() -> None:
    """The SSH accept is in the same file as the drop policy, so one nft transaction
    brings both — and it is the first rule after loopback, so no later rule sits between
    a new SSH connection and its accept."""
    rules = [line for line in code(WALL) if not line.startswith(("table", "chain", "}"))]
    assert rules[0].startswith("type filter hook input") and "policy drop" in rules[0]
    assert rules[1] == 'iif "lo" accept'
    assert rules[2] == "tcp dport 22 accept"


def test_the_wall_opens_only_ssh_and_the_web() -> None:
    ports = {
        int(p)
        for line in code(WALL)
        if line.startswith("tcp dport")
        for p in re.findall(r"\d+", line)
    }
    assert ports == {22, 80, 443}
    assert not any("4416" in line for line in code(WALL)), "the minter stays shut"


def test_the_wall_keeps_the_network_working() -> None:
    """ICMPv6 is neighbour discovery and DHCP is the v4 address; drop either and the box
    goes dark by itself some minutes after the wall went up."""
    text = "\n".join(code(WALL))
    assert "ipv6-icmp" in text
    assert "ct state established,related accept" in text
    assert re.search(r"udp dport \{ 68, 546 \} accept", text)


def test_the_wall_is_checked_then_can_undo_itself_then_goes_up(script: list[str]) -> None:
    """`nft -c`, then the rollback timer, then the load — in that order, and the rollback
    exists on disk before any of it."""
    rollback_written = first(script, r"put_file 0755 \"\$ROLLBACK\"")
    checked = first(script, r"^if ! nft -c -f \"\$NFT_CONF\"; then")
    armed = first(script, r"^systemd-run .*--on-active=")
    loaded = first(script, r"^systemctl reload nftables")
    assert rollback_written < checked < armed < loaded


def test_ufw_is_not_used(script: list[str]) -> None:
    """nftables.conf opens with `flush ruleset` and races ufw at boot; see the wall file."""
    assert not any(re.search(r"\bufw\b", line) for line in script)


MUTATING = re.compile(
    r"^(fallocate|mkswap|swapon|chmod|apt-get|systemd-run|install |cp |mv "
    r"|systemctl (reload|restart|enable|stop|reset-failed)|printf .*>>)"
)


def branch(condition: str) -> str:
    if '"$DRY" = 1' in condition:
        return "dry"
    if '"$DRY" = 0' in condition:
        return "real"
    return "neutral"


def test_every_change_waits_for_a_real_run() -> None:
    """A command that changes the box runs through `act`, or inside a branch that only a
    real run reaches. One bare at the top level would run under --dry-run too."""
    now: list[str] = []  # the branch each open `if` is in
    seen: list[set[str]] = []  # the kinds of condition each open `if` has had
    for line in code(SCRIPT):
        one_line = line.endswith("; fi")
        if re.match(r"^if\b", line) and not one_line:
            now.append(branch(line))
            seen.append({now[-1]})
        elif re.match(r"^elif\b", line):
            now[-1] = branch(line)
            seen[-1].add(now[-1])
        elif line == "else":
            now[-1] = "real" if "dry" in seen[-1] else "dry" if "real" in seen[-1] else "neutral"
        elif line == "fi":
            now.pop()
            seen.pop()
        if MUTATING.match(line):
            assert "real" in now, f"runs under --dry-run: {line}"
    assert not now, "the walk lost count of if/fi"


def test_it_refuses_anywhere_but_the_box() -> None:
    """Here, and on CI, it is the wrong machine: it must say so and change nothing."""
    run = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run"], capture_output=True, text=True, check=False
    )
    assert run.returncode == 1
    assert "REFUSED" in run.stderr


def test_provision_points_at_it() -> None:
    assert "harden.sh" in (DEPLOY / "provision.sh").read_text(encoding="utf-8")
    assert "harden.sh" in (DEPLOY / "README.md").read_text(encoding="utf-8")
