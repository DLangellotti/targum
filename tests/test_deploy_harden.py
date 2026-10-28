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
CADDY = DEPLOY / "caddy-sandbox.conf"


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
    reloaded = first(script, r"systemctl reload ssh")
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
    # Forwarding off changes nothing about how anyone logs in, so it cannot lock a door.
    assert "X11Forwarding no" in block
    assert "AllowAgentForwarding no" in block
    assert not re.search(r"^\s*(MaxAuthTries|AllowUsers|Port|ListenAddress)\b", block, re.M), (
        "a line that decides who gets in belongs in its own reviewed change"
    )


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
    armed = first(script, r"^if ! systemd-run .*--on-active=")
    loaded = first(script, r"\{ systemctl reload nftables")
    assert rollback_written < checked < armed < loaded


def test_ufw_is_not_used(script: list[str]) -> None:
    """nftables.conf opens with `flush ruleset` and races ufw at boot; see the wall file."""
    assert not any(re.search(r"\bufw\b", line) for line in script)


MUTATING = re.compile(
    r"^(fallocate|mkswap|swapon|chmod|apt-get|systemd-run|install |cp |mv "
    r"|systemctl (reload|restart|enable|stop|reset-failed|daemon-reload)|printf .*>>)"
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
    lines = code(SCRIPT)
    functions = {m.group(1) for line in lines if (m := re.match(r"^(\w+)\(\) \{$", line))}
    calls = re.compile(rf"^({'|'.join(sorted(functions))})$") if functions else None
    inside = False
    for line in lines:
        # A function's body runs where it is called; the call is what is checked.
        if re.match(r"^\w+\(\) \{$", line) and line[:-4] not in {"act", "put_file", "die", "say"}:
            inside = True
            continue
        if inside:
            inside = line != "}"
            continue
        if calls and calls.match(line):
            assert "real" in now, f"runs under --dry-run: {line}"
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


def caddy_rules() -> dict[str, str]:
    return dict(line.split("=", 1) for line in code(CADDY) if "=" in line)


def test_caddy_s_sandbox_keeps_what_caddy_needs() -> None:
    """Its certificates and autosave live in /var/lib/caddy and the visitor count reads its
    logs in /var/log/caddy; it binds 80 and 443 as the caddy user. Lose any of those and
    the site is down, so the drop-in names each."""
    rules = caddy_rules()
    assert code(CADDY)[0] == "[Service]"
    assert rules["ProtectSystem"] == "strict"
    assert set(rules["ReadWritePaths"].split()) == {"/var/lib/caddy", "/var/log/caddy"}
    assert set(rules["CapabilityBoundingSet"].split()) == {
        "CAP_NET_BIND_SERVICE",
        "CAP_NET_ADMIN",
    }
    assert {"AF_INET", "AF_INET6", "AF_UNIX"} <= set(rules["RestrictAddressFamilies"].split())
    # A drop-in adds; the package's own start line, user and capabilities stay its own.
    for key in ("ExecStart", "ExecReload", "User", "AmbientCapabilities"):
        assert key not in rules


def test_every_log_caddy_writes_is_inside_its_sandbox() -> None:
    caddyfile = (DEPLOY / "Caddyfile").read_text(encoding="utf-8")
    logs = re.findall(r"output file (\S+)", caddyfile)
    assert logs
    for log in logs:
        assert log.startswith("/var/log/caddy/"), log
    assert not re.search(r"^\s*(root|file_server)\b", caddyfile, re.M), (
        "Caddy serves files from disk now; the sandbox has to be able to read them"
    )


STUB = """#!/bin/bash
echo "$(basename "$0") $*" >> "$LOG"
for f in $FAIL; do
  [[ "$(basename "$0") $*" == *"${f//_/ }"* ]] && exit 1
done
exit 0
"""


def run_caddy_up(tmp_path: Path, fail: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """harden.sh's own `caddy_up`, run as the script runs it (`set -euo pipefail`), with
    systemctl, systemd-analyze and curl stubbed: each logs its call and fails when its
    command line holds one of FAIL's words (`_` for a space)."""
    text = SCRIPT.read_text(encoding="utf-8")
    body = re.search(r"^caddy_up\(\) \{\n.*?^\}\n", text, re.M | re.S)
    assert body, "harden.sh has no caddy_up function"
    stubs = tmp_path / "bin"
    stubs.mkdir()
    for name in ("systemctl", "systemd-analyze", "curl"):
        (stubs / name).write_text(STUB, encoding="utf-8")
        (stubs / name).chmod(0o755)
    dropin = tmp_path / "10-targum-sandbox.conf"
    dropin.write_text("[Service]\n", encoding="utf-8")
    log = tmp_path / "calls.log"
    harness = tmp_path / "run.sh"
    harness.write_text(
        "set -euo pipefail\n"
        "say() { printf '%s\\n' \"$*\"; }\n"
        "die() { printf 'REFUSED: %s\\n' \"$*\" >&2; exit 1; }\n"
        f'CADDY_DROPIN="{dropin}"\n' + body.group(0) + "caddy_up\n",
        encoding="utf-8",
    )
    run = subprocess.run(
        ["bash", str(harness)],
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": f"{stubs}:/usr/bin:/bin", "LOG": str(log), "FAIL": fail},
    )
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return run, calls


def test_caddy_comes_up_in_its_sandbox_when_every_step_passes(tmp_path: Path) -> None:
    run, calls = run_caddy_up(tmp_path, "")
    assert run.returncode == 0, run.stderr
    assert (tmp_path / "10-targum-sandbox.conf").exists()
    assert [call.split()[0:2] for call in calls] == [
        ["systemd-analyze", "verify"],
        ["systemctl", "daemon-reload"],
        ["systemctl", "restart"],
        ["systemctl", "is-active"],
        ["curl", "-fsS"],
    ]
    assert "https://targum.page/health" in calls[-1]


@pytest.mark.parametrize(
    "fail",
    ["systemctl_daemon-reload", "systemctl_restart_caddy", "systemctl_is-active", "curl"],
)
def test_any_failed_step_takes_the_sandbox_out_and_restarts_caddy(
    tmp_path: Path, fail: str
) -> None:
    """Under `set -e`, each of these failing used to end the script before its undo when
    it was a bare line (qa on targum#967): the drop-in stayed and Caddy stayed down."""
    run, calls = run_caddy_up(tmp_path, fail)
    assert run.returncode == 1
    assert "REFUSED: caddy did not serve the site" in run.stderr
    assert not (tmp_path / "10-targum-sandbox.conf").exists()
    failed = next(i for i, call in enumerate(calls) if fail.replace("_", " ") in call)
    assert any(call == "systemctl restart caddy" for call in calls[failed + 1 :]), calls
    # And it got that far: nothing after the failing step but the undo.
    assert not any(call.startswith("curl") for call in calls[failed + 1 :])


def test_a_rejected_caddy_drop_in_never_reaches_systemd(tmp_path: Path) -> None:
    run, calls = run_caddy_up(tmp_path, "systemd-analyze")
    assert run.returncode == 1
    assert not (tmp_path / "10-targum-sandbox.conf").exists()
    assert not any(call.startswith("systemctl") for call in calls)


def test_no_undo_is_left_behind_a_bare_step(script: list[str]) -> None:
    """The other places a failure under `set -e` could leave a half-done change: an sshd
    reload that fails puts the old drop-in back, and a rollback timer that will not arm
    takes the wall's include out before anything loads."""
    reload = first(script, r"! systemctl reload ssh\.service; then$")
    assert script[reload + 1] == 'rm -f "$SSHD_DROPIN"'
    assert script[reload + 3].startswith("die ")
    armed = first(script, r"^if ! systemd-run .*--on-active=")
    assert script[armed + 1] == '"$ROLLBACK" >/dev/null'
    assert script[armed + 2].startswith("die ")
    made = first(script, r"act fallocate")
    assert script[made].startswith("if ! {")
    assert script[made + 1] == 'rm -f "$SWAPFILE"'
    assert not any(re.match(r"^systemctl (daemon-reload|restart caddy)$", line) for line in script)


def test_it_says_a_reboot_is_waiting_and_never_reboots(script: list[str]) -> None:
    assert any("/var/run/reboot-required" in line for line in script)
    assert not any(
        re.search(r"(^|[;&|]\s*)(reboot|shutdown|systemctl (reboot|kexec|poweroff))\b", line)
        for line in script
    )


def test_the_minter_unit_does_not_claim_a_loopback_binding() -> None:
    """It binds every interface; a comment saying otherwise is how a wall gets taken down
    as unnecessary."""
    unit = (DEPLOY / "bgutil-pot.service").read_text(encoding="utf-8")
    assert "which is the loopback" not in unit
    assert "*:4416" in unit
