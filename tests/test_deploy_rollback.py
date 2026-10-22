"""Stepping back without a laptop build: what deploy.sh leaves on the box, and rollback.sh.

targum-internal#482. Every deploy now keeps its wheel, its constraints and its extras in
/var/lib/targum-deploy/wheels/<sha12>/ (the last five), appends "<utc> <sha> <who>" to
/var/lib/targum-deploy/deploys.log, copies the database as the service account and checks the
copy before anything is installed (the last ten), and keeps the catalogue it replaces as
catalogue.json.prev. rollback.sh puts a kept wheel back the way deploy.sh installed it.

Nothing here reaches a box. deploy.sh is read as text, and its box-side block is rendered
the way bash renders the heredoc and syntax-checked; rollback.sh is run with `ssh` and
`curl` stood in for, so what it would say to the box is captured instead of sent.
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from pathlib import Path

import pytest

from targum import backup

ROOT = Path(__file__).resolve().parent.parent
DEPLOY = ROOT / "deploy" / "deploy.sh"
ROLLBACK = ROOT / "deploy" / "rollback.sh"


def text(path: Path = DEPLOY) -> str:
    return path.read_text(encoding="utf-8")


def box_block() -> str:
    """deploy.sh's heredoc as the box receives it, with this side's values filled in.

    An unquoted heredoc also joins backslash-continued lines, so a command split over
    several lines in the script is one line here, as the box's shell reads it.
    """
    found = re.search(r'"bash -euo pipefail -s" <<EOF\n(.*?)\nEOF\n', text(), re.S)
    assert found, "deploy.sh no longer sends the box one block"
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "REMOTE_WHEEL": "/tmp/targum-1.0-py3-none-any.whl",
        "REMOTE_CONSTRAINTS": "/tmp/box-constraints.txt",
        "REMOTE_EXTRAS": "difficulty,covers",
        "KEEP_AS": "0123456789ab",
        "SHA": "0123456789abcdef0123456789abcdef01234567",
        "STAMP": "20261022T120000Z",
        "WHO": "david",
    }
    rendered = subprocess.run(
        ["bash", "-c", "cat <<EOF\n" + found.group(1) + "\nEOF\n"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return rendered


def test_both_scripts_parse() -> None:
    for script in (DEPLOY, ROLLBACK):
        subprocess.run(["bash", "-n", str(script)], check=True)
    assert os.access(ROLLBACK, os.X_OK), "rollback.sh is run as ./deploy/rollback.sh"


def test_the_box_block_parses_once_rendered() -> None:
    """An escaping slip in an unquoted heredoc is a syntax error only the box would see."""
    subprocess.run(["bash", "-n"], input=box_block(), text=True, check=True)


def test_a_running_deploy_is_refused_before_anything_changes() -> None:
    """The guard used to sit below the install (since e63b406b), so a refused deploy had
    already swapped the wheel under the rebuild it was refusing to race."""
    block = box_block()
    guard = block.index("systemctl is-active --quiet targum-deploy.service")
    for later in ("sqlite3", "uv tool install", "/etc/targum/catalogue.json", "deploys.log"):
        assert guard < block.index(later), later


def test_the_database_is_copied_as_targum_and_checked_before_the_install() -> None:
    block = box_block()
    copy = re.search(
        r"systemd-run [^\n]*--uid=targum --gid=targum\s+/usr/bin/sqlite3 "
        r"/var/lib/targum/targum\.db \"\.backup '\$BEFORE'\"",
        block,
    )
    assert copy, "the copy is SQLite's .backup, run as the service account"
    assert "BEFORE=/var/lib/targum/backups/targum.db.before-0123456789ab-20261022T120000Z" in (
        block
    )
    check = block.index("pragma integrity_check;")
    assert '[ "$CHECKED" != "ok" ]' in block
    stop = block.index('[ "$CHECKED" != "ok" ]')
    assert block.index("exit 1", stop) < block.index("uv tool install")
    assert copy.start() < check < block.index("uv tool install")
    # A copy that could not be made stops the deploy on its own, before the check.
    failed = block[copy.end() : block.index("CHECKED=")]
    assert "exit 1" in failed, "a failed .backup stops the deploy where it failed"


def test_a_running_deploy_is_refused_before_anything_is_sent() -> None:
    """The keys merge rewrites the env file a running rebuild's later steps read, and the
    covers land in the live thumbs directory: both happen before the box-side block."""
    script = text()
    guard = re.search(
        r'if ssh "\$\{SSH_OPTS\[@\]\}" "\$HOST" "systemctl is-active --quiet '
        r'targum-deploy\.service"; then\n(?:[^\n]*\n){0,4}?\s*exit 1',
        script,
    )
    assert guard, "the laptop asks before it sends"
    for later in ("scp -q", "rsync -a", "$MERGE", "$MERGE_SOURCES"):
        assert guard.start() < script.index(later), later


def test_the_copies_before_deploys_keep_to_ten_and_leave_the_nightly_alone() -> None:
    block = box_block()
    prune = re.search(r"grep -E '([^']+)'\s+\| tail -n \+11 ", block)
    assert prune, "the copies before each deploy are pruned to the last ten"
    # Through bash -c inside double quotes on the box, so its anchor arrives escaped.
    ours = re.compile(prune.group(1).replace("\\$", "$"))
    name = "targum.db.before-0123456789ab-20261022T120000Z"
    assert ours.match(name) and ours.match(name.replace("ab-", "ab-dirty-"))
    # Hand-made copies from before this are not ours to prune, nor the nightly fourteen.
    for other in ("targum.db.before-deploy-2026-10-21b", "targum-20261022-040000.db"):
        assert not ours.match(other), other
    # And the nightly sweep never takes one of ours either.
    for pattern in ("targum-*.db", "cache-*.zip"):
        assert not fnmatch.fnmatch(name, pattern)
    assert backup.KEEP == 14


def test_each_wheel_is_kept_with_its_constraints_after_it_installs() -> None:
    block = box_block()
    assert "DEPLOYS=/var/lib/targum-deploy\n" in block
    assert "KEPT=$DEPLOYS/wheels/0123456789ab\n" in block
    keep = block.index('install -o root -g root -m 0644 "/tmp/targum-1.0-py3-none-any.whl"')
    assert "/tmp/box-constraints.txt" in block[keep : block.index("\n", keep)]
    assert block.index("uv tool install") < keep, "only a wheel that installed is kept"
    assert 'printf \'%s\\n\' "difficulty,covers" > "$KEPT/extras"' in block
    prune = block.index('find "$DEPLOYS/wheels" -mindepth 1 -maxdepth 1 -type d')
    assert "| sort -rn | tail -n +6 | cut -d' ' -f2- | xargs -r rm -rf --" in block[prune:]
    # The one just kept is the newest, so the prune comes after it is in place.
    assert keep < prune and block.index('touch "$KEPT"') < prune


def test_root_writes_nothing_inside_the_service_accounts_directory() -> None:
    """/var/lib/targum is targum's: it can swap a root-owned child for a symlink, and a
    root rm -rf, install -d or append would follow it. What root keeps lives in
    /var/lib/targum-deploy; what goes in /var/lib/targum is written as targum."""
    for block in (box_block(), text(ROLLBACK)):
        assert not re.search(r"rm -rf[^\n]*/var/lib/targum/", block)
        assert not re.search(r">>?\s*\"?/var/lib/targum/", block)
        assert not re.search(r"install -d[^\n]*/var/lib/targum/", block)
        assert "/var/lib/targum/wheels" not in block
        assert "/var/lib/targum/deploys.log" not in block
    assert '[ -L "$DEPLOYS" ]' in box_block(), "a symlinked directory is refused"


PRUNE = re.compile(r'find "\$DEPLOYS/wheels" .*?xargs -r rm -rf --', re.S)


def test_the_prune_keeps_five_and_never_follows_a_link(tmp_path: Path) -> None:
    probe = subprocess.run(
        ["find", str(tmp_path), "-maxdepth", "0", "-printf", "%p"], capture_output=True, text=True
    )
    if probe.returncode != 0:
        pytest.skip("this find has no -printf; the box's GNU find does")
    found = PRUNE.search(box_block())
    assert found
    wheels = tmp_path / "deploys" / "wheels"
    wheels.mkdir(parents=True)
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep").write_text("x")
    for age, name in enumerate(["a", "b", "c", "d", "e", "f", "g"]):
        (wheels / name).mkdir()
        os.utime(wheels / name, (1000 + age, 1000 + age))
    (wheels / "zzz").symlink_to(victim)
    subprocess.run(
        ["bash", "-c", found.group(0)],
        env={"PATH": os.environ["PATH"], "DEPLOYS": str(tmp_path / "deploys")},
        check=True,
    )
    assert sorted(p.name for p in wheels.iterdir()) == ["c", "d", "e", "f", "g", "zzz"]
    assert (victim / "keep").exists()


def test_every_deploy_says_who_shipped_what_and_when() -> None:
    block = box_block()
    line = (
        "printf '%s %s %s\\n' \"20261022T120000Z\" "
        '"0123456789abcdef0123456789abcdef01234567" "david" >> "$DEPLOYS/deploys.log"'
    )
    assert line in block
    script = text()
    assert re.search(r"^WHO=\"\$\(id -un ", script, re.M), "who is the laptop's account"
    assert re.search(r'^SHA="\$\(git rev-parse HEAD\)"', script, re.M)
    # Never a key: nothing from the vault is anywhere near the line.
    assert "SECRETS" not in block and "OP_" not in block


def test_the_catalogue_it_replaces_is_kept_first() -> None:
    block = box_block()
    keep = (
        "install -o root -g targum -m 0640 "
        "/etc/targum/catalogue.json /etc/targum/catalogue.json.prev"
    )
    prev = block.index(keep)
    # Not cp -p: the copy's time says when it was replaced, which rollback.sh shows.
    assert "cp -p /etc/targum/catalogue.json" not in block
    assert prev < block.index("/tmp/catalogue.json /etc/targum/catalogue.json\n")
    assert "! cmp -s /tmp/catalogue.json /etc/targum/catalogue.json" in block


# --- rollback.sh, with ssh and curl stood in for --------------------------------------

FAKE_SSH = """#!/usr/bin/env bash
while [ "${1#-}" != "$1" ]; do shift 2; done
shift
if [ "$*" = "bash -euo pipefail -s" ]; then
  cat > "$SENT"
  exit "${BOX_EXIT:-0}"
fi
echo "$*" >> "$CALLS"
case "$*" in
  find\\ *) printf '%s' "$BOX_SAYS" ;;
esac
"""

FAKE_CURL = """#!/usr/bin/env bash
echo "$*" >> "$CURLS"
echo '{"ok": true, "store": true}'
"""


def run_rollback(tmp_path: Path, *args: str, box_says: str) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("ssh", FAKE_SSH), ("curl", FAKE_CURL)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "TARGUM_HOST": "root@box.invalid",
        "DOMAIN": "box.invalid",
        "SENT": str(tmp_path / "sent"),
        "CALLS": str(tmp_path / "calls"),
        "CURLS": str(tmp_path / "curls"),
        "BOX_SAYS": box_says,
    }
    return subprocess.run(
        ["bash", str(ROLLBACK), *args],
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )


KEPT = "wheel 0123456789ab\nwheel fedcba987654\nwheel fedcba987654-dirty\n"


def test_a_commit_the_box_does_not_keep_is_refused_and_said(tmp_path: Path) -> None:
    done = run_rollback(tmp_path, "abcdef1", box_says=KEPT)
    assert done.returncode == 1
    assert "keeps no wheel for abcdef1" in done.stderr
    assert "0123456789ab" in done.stderr, "and says what it does keep"
    assert not (tmp_path / "sent").exists(), "nothing was sent to change the box"
    assert not (tmp_path / "curls").exists()


def test_something_that_is_not_a_commit_never_reaches_the_box(tmp_path: Path) -> None:
    done = run_rollback(tmp_path, "abc; rm -rf /", box_says=KEPT)
    assert done.returncode == 2
    assert "is not a commit" in done.stderr
    assert not (tmp_path / "sent").exists()


def test_an_ambiguous_commit_is_refused(tmp_path: Path) -> None:
    done = run_rollback(tmp_path, "fedcba9", box_says="wheel fedcba987654\nwheel fedcba98aaaa\n")
    assert done.returncode == 1 and "more than one" in done.stderr
    assert not (tmp_path / "sent").exists()


def test_with_no_commit_it_lists_what_the_box_keeps(tmp_path: Path) -> None:
    done = run_rollback(tmp_path, box_says=KEPT)
    assert done.returncode == 2
    assert "fedcba987654" in done.stderr
    assert "deploys.log" in (tmp_path / "calls").read_text()
    assert not (tmp_path / "sent").exists()


def test_a_kept_wheel_goes_back_as_deploy_installed_it(tmp_path: Path) -> None:
    sha = "0123456789abcdef0123456789abcdef01234567"
    done = run_rollback(tmp_path, sha, box_says=KEPT)
    assert done.returncode == 0, done.stderr
    sent = (tmp_path / "sent").read_text()
    subprocess.run(["bash", "-n"], input=sent, text=True, check=True)
    assert "KEPT=/var/lib/targum-deploy/wheels/0123456789ab\n" in sent
    install = re.search(r"sudo -u targum env HOME=/srv/targum[^\n]*", sent)
    assert install, "installed as the service account"
    assert "uv tool install --force" in install.group(0)
    assert '--constraints "$KEPT/box-constraints.txt"' in install.group(0)
    assert "download.pytorch.org/whl/cpu" in install.group(0)
    guard = sent.index("systemctl is-active --quiet targum-deploy.service")
    assert guard < sent.index("uv tool install") < sent.index("systemctl restart targum")
    assert re.search(r"printf '%s %s %s rollback\\n' \"\d{8}T\d{6}Z\" \"0123456789ab\" ", sent)
    # The wheel it put back is touched, or it stays the oldest by time and the next
    # deploy prunes the one that is running.
    touched = sent.index('touch "$KEPT"')
    assert sent.index("uv tool install") < touched < sent.index("systemctl restart targum")
    assert ">> /var/lib/targum-deploy/deploys.log" in sent
    assert "https://box.invalid/health" in (tmp_path / "curls").read_text()
    assert "uv build" not in text(ROLLBACK), "nothing is built on the laptop"


def test_a_dirty_name_is_matched_only_when_asked_for(tmp_path: Path) -> None:
    assert run_rollback(tmp_path, "fedcba987654", box_says=KEPT).returncode == 0
    assert "wheels/fedcba987654\n" in (tmp_path / "sent").read_text()
    assert run_rollback(tmp_path, "fedcba9-dirty", box_says=KEPT).returncode == 0
    assert "wheels/fedcba987654-dirty\n" in (tmp_path / "sent").read_text()


@pytest.mark.parametrize(("flag", "swapped"), [((), False), (("--catalogue",), True)])
def test_the_catalogue_goes_back_only_when_asked(
    tmp_path: Path, flag: tuple[str, ...], swapped: bool
) -> None:
    says = KEPT + "catalogue-prev 2026-10-21T09:00Z\n"
    done = run_rollback(tmp_path, "0123456", *flag, box_says=says)
    assert done.returncode == 0, done.stderr
    sent = (tmp_path / "sent").read_text()
    assert ('if [ "1" = 1 ]; then' in sent) is swapped
    assert "mv /etc/targum/catalogue.json.prev /etc/targum/catalogue.json" in sent
    if not swapped:
        assert "--catalogue puts back the one a deploy replaced on 2026-10-21T09:00Z" in done.stdout
