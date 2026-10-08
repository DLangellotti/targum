"""deploy.sh carries the library's covers to the box and never takes one away.

The covers are drawn on the laptop (`targum thumbs`) into targum-out/thumbs and served on
the box from /var/lib/targum/targums/thumbs; nothing carried them until 2026-10-08, when
they went over by hand. The box also draws a cover for every upload, which the laptop
never has, so the copy must add and replace and never delete.

The step is cut out of deploy.sh and run on its own, with `ssh` and `rsync` stood in for:
`ssh` runs its command locally (a chown is only noted), and `rsync` is the real one, with
the host taken off the destination so the "box" is a directory here.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy" / "deploy.sh"

FAKE_SSH = """#!/usr/bin/env bash
while [ "${1#-}" != "$1" ]; do shift 2; done
shift
echo "ssh $*" >> "$CALLS"
case "$*" in
  chown*) ;;
  *) bash -c "$*" ;;
esac
"""

FAKE_RSYNC = """#!/usr/bin/env bash
echo "rsync $*" >> "$CALLS"
echo "rsh $RSYNC_RSH" >> "$CALLS"
args=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    -e) shift 2; continue ;;
    box:*) args+=("${1#box:}") ;;
    *) args+=("$1") ;;
  esac
  shift
done
exec "$REAL_RSYNC" "${args[@]}"
"""


def step() -> str:
    found = re.search(
        r"^# The library's cover pictures.*?^fi$", SCRIPT.read_text(encoding="utf-8"), re.M | re.S
    )
    assert found, "deploy.sh no longer carries the covers"
    return found.group(0)


def run(tmp_path: Path, thumbs: Path, box: Path) -> tuple[str, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("ssh", FAKE_SSH), ("rsync", FAKE_RSYNC)):
        (bin_dir / name).write_text(body, encoding="utf-8")
        (bin_dir / name).chmod(0o755)
    calls = tmp_path / "calls"
    calls.touch()
    prelude = 'set -euo pipefail\nHOST=box\nSSH_OPTS=(-o ServerAliveInterval=60)\nROOT="$PWD"\n'
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "CALLS": str(calls),
        "REAL_RSYNC": str(shutil.which("rsync")),
        "TARGUM_THUMBS": str(thumbs),
        "TARGUM_REMOTE_THUMBS": str(box),
    }
    done = subprocess.run(
        ["bash", "-c", prelude + step()],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout + done.stderr, calls.read_text(encoding="utf-8").splitlines()


def test_the_step_never_deletes() -> None:
    assert "--delete" not in re.sub(r"^\s*#.*$", "", step(), flags=re.M)


def test_a_laptop_without_covers_skips_quietly(tmp_path: Path) -> None:
    said, calls = run(tmp_path, tmp_path / "missing", tmp_path / "box")
    assert said == ""
    assert calls == []


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync is what deploy.sh copies with")
def test_covers_arrive_box_only_covers_stay_and_partials_stay_behind(tmp_path: Path) -> None:
    thumbs = tmp_path / "thumbs"
    (thumbs / "small").mkdir(parents=True)
    (thumbs / "genesis.webp").write_bytes(b"redrawn")
    (thumbs / "small" / "genesis.webp").write_bytes(b"small")
    (thumbs / "sources.json").write_text("{}", encoding="utf-8")
    (thumbs / ".exodus.webp.part").write_bytes(b"half")
    (thumbs / ".DS_Store").write_bytes(b"")
    (thumbs / "leviticus.webp.tmp").write_bytes(b"half")
    box = tmp_path / "box"
    box.mkdir()
    (box / "genesis.webp").write_bytes(b"old")
    (box / "home1-upload.webp").write_bytes(b"theirs")

    said, calls = run(tmp_path, thumbs, box)

    assert (box / "genesis.webp").read_bytes() == b"redrawn"
    assert (box / "small" / "genesis.webp").read_bytes() == b"small"
    assert (box / "sources.json").is_file()
    assert (box / "home1-upload.webp").read_bytes() == b"theirs"
    assert not (box / ".exodus.webp.part").exists()
    assert not (box / ".DS_Store").exists()
    assert not (box / "leviticus.webp.tmp").exists()
    # Handed to the service after the copy, since 2.6.9 has no --chown.
    assert calls[-1] == f"ssh chown -R targum:targum '{box}'"
    assert any(call.startswith("rsync ") for call in calls[:-1])
    assert "rsh ssh -o ServerAliveInterval=60 " in calls
    assert "2 covers" in said
