"""deploy.sh puts the catalogue lemma index in place without root opening targum's file.

`targum catalogue-lemmas` runs as the service account and writes under /var/lib/targum,
which is targum's; root then puts the index in /etc/targum, which only root writes. Root
opening the file by name would follow a symlink planted there and copy whatever it points
at into /etc/targum, readable by the service (targum-internal#512). So it is read as
targum and written as root.

The step is cut out of the deploy unit and run on its own, with its two directories moved
under a temporary one and `systemd-run`, `runuser` and `chown` stood in for: the first
writes the index, the second is noted and runs what it was given as this user, since a
test cannot switch to targum, and the third is noted.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy" / "deploy.sh"

FAKE_SYSTEMD_RUN = """#!/usr/bin/env bash
echo "systemd-run $*" >> "$CALLS"
[ -n "${FAIL_INDEX:-}" ] && exit 1
[ -n "${NO_INDEX:-}" ] && exit 0
while [ "$#" -gt 0 ]; do
  [ "$1" = "--write" ] && printf '{"genesis": ["בראשית"]}\\n' > "$2"
  shift
done
"""

FAKE_RUNUSER = """#!/usr/bin/env bash
echo "runuser $*" >> "$CALLS"
while [ "$1" != "--" ]; do shift; done
shift
exec "$@"
"""

FAKE_CHOWN = """#!/usr/bin/env bash
echo "chown $*" >> "$CALLS"
"""


def step() -> str:
    found = re.search(
        r"^      if systemd-run [^\n]*\n[^\n]*\n"
        r"\s*/usr/local/bin/targum catalogue-lemmas.*?^      fi$",
        SCRIPT.read_text(encoding="utf-8"),
        re.M | re.S,
    )
    assert found, "deploy.sh no longer puts the catalogue lemma index in place"
    return found.group(0)


def run(tmp_path: Path, **env_extra: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (
        ("systemd-run", FAKE_SYSTEMD_RUN),
        ("runuser", FAKE_RUNUSER),
        ("chown", FAKE_CHOWN),
    ):
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    etc, var = tmp_path / "etc", tmp_path / "var"
    etc.mkdir(exist_ok=True)
    var.mkdir(exist_ok=True)
    calls = tmp_path / "calls"
    calls.touch()
    body = step().replace("/etc/targum/", f"{etc}/").replace("/var/lib/targum/", f"{var}/")
    done = subprocess.run(
        ["bash", "-c", "set -euo pipefail\n" + body],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "CALLS": str(calls),
            **env_extra,
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return done, calls.read_text(encoding="utf-8").splitlines()


def test_roots_side_never_opens_targums_file_by_name() -> None:
    """The source is in targum's folder: it is read through runuser and nothing else."""
    body = re.sub(r"^\s*#.*$", "", step(), flags=re.M)
    mentions = [
        line for line in body.splitlines() if "/var/lib/targum/catalogue-lemmas.json" in line
    ]
    assert len(mentions) == 2, mentions  # written by the command, read back once
    assert "--write /var/lib/targum/catalogue-lemmas.json" in mentions[0]
    assert (
        mentions[1]
        .strip()
        .startswith("if ! { runuser -u targum -- cat /var/lib/targum/catalogue-lemmas.json")
    ), mentions[1]
    assert "install " not in body, "install opens its source as root"


def test_the_index_lands_root_owned_0640_and_read_as_targum(tmp_path: Path) -> None:
    done, calls = run(tmp_path)

    assert done.returncode == 0, done.stderr
    placed = tmp_path / "etc" / "lemmas.json"
    assert placed.read_text(encoding="utf-8") == '{"genesis": ["בראשית"]}\n'
    assert stat.S_IMODE(placed.stat().st_mode) == 0o640
    assert f"runuser -u targum -- cat {tmp_path}/var/catalogue-lemmas.json" in calls
    assert f"chown root:targum {tmp_path}/etc/.lemmas.json.part" in calls
    assert not (tmp_path / "etc" / ".lemmas.json.part").exists()


def test_a_planted_part_is_replaced_not_written_through(tmp_path: Path) -> None:
    """/etc/targum is root's, so this cannot be planted on the box; the write still
    replaces a name rather than following one."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_text("root's\n", encoding="utf-8")
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "lemmas.json").symlink_to(elsewhere)

    done, _ = run(tmp_path)

    assert done.returncode == 0, done.stderr
    assert elsewhere.read_text(encoding="utf-8") == "root's\n"
    assert not (tmp_path / "etc" / "lemmas.json").is_symlink()


def test_an_index_that_was_not_written_keeps_the_old_one_and_does_not_stop(
    tmp_path: Path,
) -> None:
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "lemmas.json").write_text("the old one\n", encoding="utf-8")

    done, calls = run(tmp_path, FAIL_INDEX="1")

    assert done.returncode == 0, "not fatal: the restart after it must still run"
    assert (tmp_path / "etc" / "lemmas.json").read_text(encoding="utf-8") == "the old one\n"
    assert "the library keeps the one it had" in done.stderr
    assert not any(call.startswith("runuser") for call in calls)


def test_an_index_that_cannot_be_read_keeps_the_old_one_and_leaves_no_part(
    tmp_path: Path,
) -> None:
    """The command said it wrote the file and it is not there (or targum cannot read it):
    nothing half-written goes in, and the deploy goes on."""
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "lemmas.json").write_text("the old one\n", encoding="utf-8")

    done, _ = run(tmp_path, NO_INDEX="1")  # said it wrote the file, and wrote nothing

    assert done.returncode == 0, done.stderr
    assert (tmp_path / "etc" / "lemmas.json").read_text(encoding="utf-8") == "the old one\n"
    assert not (tmp_path / "etc" / ".lemmas.json.part").exists()
    assert "could not be put in place" in done.stderr
