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

FAKE_THUMBS = """#!/usr/bin/env bash
echo "thumbs $*" >> "$CALLS"
echo "2 own · 1 drawn · 3 tile"
echo "3 rows without a picture"
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
    for name, body in (("ssh", FAKE_SSH), ("rsync", FAKE_RSYNC), ("thumbs", FAKE_THUMBS)):
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
        "TARGUM_THUMBS_CLI": str(bin_dir / "thumbs"),
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


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync is what deploy.sh copies with")
def test_the_rows_without_a_picture_are_counted_before_anything_goes(tmp_path: Path) -> None:
    thumbs = tmp_path / "thumbs"
    thumbs.mkdir()
    (thumbs / "genesis.webp").write_bytes(b"drawn")
    box = tmp_path / "box"
    box.mkdir()

    said, calls = run(tmp_path, thumbs, box)

    assert "   3 rows without a picture" in said.splitlines()
    assert calls[0] == f"thumbs --dry-run --no-fetch --out {tmp_path}", (
        "counted first, spending nothing"
    )


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync is what deploy.sh copies with")
def test_sources_are_merged_so_the_boxs_own_lines_stay(tmp_path: Path) -> None:
    import json

    thumbs = tmp_path / "thumbs"
    thumbs.mkdir()
    (thumbs / "genesis.webp").write_bytes(b"drawn")
    laptop = {
        "genesis": {"from": "drawn", "model": "openai/gpt-image-2", "date": "2026-10-08"},
        "ka-x": {"from": "video poster", "licence": "CC BY 4.0"},
    }
    (thumbs / "sources.json").write_text(json.dumps(laptop), encoding="utf-8")
    box = tmp_path / "box"
    box.mkdir()
    upload = {"from": "drawn", "model": "openai/gpt-image-2", "date": "2026-10-20"}
    (box / "sources.json").write_text(
        json.dumps({"home1-notes": upload, "ka-x": {"from": "stale"}}), encoding="utf-8"
    )

    run(tmp_path, thumbs, box)

    merged = json.loads((box / "sources.json").read_text(encoding="utf-8"))
    assert merged == {**laptop, "home1-notes": upload}, (
        "this machine's lines win; the box keeps its own"
    )
