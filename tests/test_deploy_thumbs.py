"""deploy.sh carries the library's covers to the box and never takes one away.

The covers are drawn on the laptop (`targum thumbs`) into targum-out/thumbs and served on
the box from /var/lib/targum/targums/thumbs; nothing carried them until 2026-10-08, when
they went over by hand. The box also draws a cover for every upload, which the laptop
never has, so the copy must add and replace and never delete.

The step is cut out of deploy.sh and run on its own, with `ssh` and `rsync` stood in for:
`ssh` runs its command locally (a chown is only noted), and `rsync` is the real one, with
the host taken off the destination so the "box" is a directory here. `runuser` is noted
and runs what it was given as this user, since a test cannot switch to targum.

The folder is the service's, so on the box every step here runs as targum and follows no
symlink (targum-internal#512): root following one a compromised service planted would
write wherever it points.
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

# `targum thumbs`, stood in for: the dry run's two last lines, and for --for-box the
# library's lines and what stays behind, where anything named home1-… is an upload's.
FAKE_THUMBS = """#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
with open(os.environ["CALLS"], "a") as calls:
    calls.write("thumbs " + " ".join(sys.argv[1:]) + "\\n")
if "--for-box" in sys.argv:
    box = Path(sys.argv[sys.argv.index("--for-box") + 1])
    where = Path(os.environ["TARGUM_THUMBS"])
    try:
        lines = json.loads((where / "sources.json").read_text(encoding="utf-8"))
    except OSError:
        lines = {}
    mine = {k: v for k, v in lines.items() if not k.startswith("home1-")}
    (box / "sources.json").write_text(json.dumps(mine), encoding="utf-8")
    behind = sorted(f.name for f in where.glob("home1-*.webp"))
    (box / "exclude").write_text("".join("/" + n + "\\n" for n in behind), encoding="utf-8")
else:
    print("2 own · 1 drawn · 3 tile")
    print("3 rows without a picture")
"""

FAKE_RSYNC = """#!/usr/bin/env bash
echo "rsync $*" >> "$CALLS"
echo "rsh $RSYNC_RSH" >> "$CALLS"
args=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    -e) shift 2; continue ;;
    --rsync-path=*) shift; continue ;;
    box:*) args+=("${1#box:}") ;;
    *) args+=("$1") ;;
  esac
  shift
done
exec "$REAL_RSYNC" "${args[@]}"
"""

FAKE_RUNUSER = """#!/usr/bin/env bash
echo "runuser $*" >> "$CALLS"
while [ "$1" != "--" ]; do shift; done
shift
exec "$@"
"""


def step() -> str:
    found = re.search(
        r"^# The library's cover pictures.*?^fi$", SCRIPT.read_text(encoding="utf-8"), re.M | re.S
    )
    assert found, "deploy.sh no longer carries the covers"
    return found.group(0)


def run(tmp_path: Path, thumbs: Path, box: Path, *, check: bool = True) -> tuple[str, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (
        ("ssh", FAKE_SSH),
        ("rsync", FAKE_RSYNC),
        ("thumbs", FAKE_THUMBS),
        ("runuser", FAKE_RUNUSER),
    ):
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
        check=check,
    )
    if not check and done.returncode == 0:
        raise AssertionError("the step was meant to stop, and finished")
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
    # Arrived as the service's own, so nothing is handed over after (targum-internal#512).
    assert not any("chown" in call for call in calls)
    assert any(call.startswith("rsync ") for call in calls)
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


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync is what deploy.sh copies with")
def test_a_laptop_upload_never_replaces_the_boxs(tmp_path: Path) -> None:
    import json

    thumbs = tmp_path / "thumbs"
    thumbs.mkdir()
    (thumbs / "genesis.webp").write_bytes(b"drawn")
    (thumbs / "home1-notes.webp").write_bytes(b"the laptop's")
    laptop = {"home1-notes": {"from": "drawn", "date": "2026-08-26"}}
    (thumbs / "sources.json").write_text(json.dumps(laptop), encoding="utf-8")
    box = tmp_path / "box"
    box.mkdir()
    (box / "home1-notes.webp").write_bytes(b"the box's")
    theirs = {"from": "drawn", "date": "2026-10-20"}
    (box / "sources.json").write_text(json.dumps({"home1-notes": theirs}), encoding="utf-8")

    said, calls = run(tmp_path, thumbs, box)

    assert (box / "home1-notes.webp").read_bytes() == b"the box's"
    assert json.loads((box / "sources.json").read_text(encoding="utf-8")) == {"home1-notes": theirs}
    assert (box / "genesis.webp").read_bytes() == b"drawn"
    assert "   1 covers" in said.splitlines()


def test_the_merge_waits_for_the_boxs_writers(tmp_path: Path) -> None:
    """The box's covers write their lines under thumbs.record's lock, and the merge takes
    the same one: a line written while a deploy merges is never lost."""
    found = re.search(r"^MERGE_SOURCES='(.*?)'$", step(), re.M | re.S)
    assert found
    merge = found.group(1)
    assert "fcntl.flock" in merge and '".sources.json.lock"' in merge
    from targum import thumbs

    assert f".{thumbs.SOURCES}.lock" == ".sources.json.lock"


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync is what deploy.sh copies with")
def test_every_write_on_the_box_is_targums_never_roots(tmp_path: Path) -> None:
    """targum-internal#512: the folder is the service's, so root writing into it follows
    whatever the service left there. The mkdir, the receiving rsync and the merge all run
    as targum, and no chown -R walks the folder as root afterwards."""
    thumbs = tmp_path / "thumbs"
    thumbs.mkdir()
    (thumbs / "genesis.webp").write_bytes(b"drawn")
    (thumbs / "sources.json").write_text("{}", encoding="utf-8")
    box = tmp_path / "box"

    run(tmp_path, thumbs, box)

    on_the_box = [call.removeprefix("ssh ") for call in calls_of(tmp_path, "ssh ")]
    assert on_the_box, "nothing ran on the box"
    for command in on_the_box:
        assert command.startswith("runuser -u targum -- "), command
    assert not any("chown" in command for command in on_the_box)
    # The laptop's rsync, not the server half a local copy starts for itself.
    copies = [c for c in calls_of(tmp_path, "rsync ") if " --server " not in c]
    assert copies and all("--rsync-path=runuser -u targum -- rsync" in c for c in copies)
    assert (box / "genesis.webp").read_bytes() == b"drawn"


def calls_of(tmp_path: Path, prefix: str) -> list[str]:
    return [
        c
        for c in (tmp_path / "calls").read_text(encoding="utf-8").splitlines()
        if c.startswith(prefix)
    ]


def _with_a_planted_link(tmp_path: Path, name: str) -> tuple[Path, Path, Path]:
    import json

    thumbs = tmp_path / "thumbs"
    thumbs.mkdir()
    (thumbs / "genesis.webp").write_bytes(b"drawn")
    (thumbs / "sources.json").write_text(json.dumps({"genesis": {"from": "drawn"}}), "utf-8")
    box = tmp_path / "box"
    box.mkdir()
    (box / "sources.json").write_text(json.dumps({"home1-notes": {"from": "drawn"}}), "utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_text("not the service's\n", encoding="utf-8")
    (box / name).unlink(missing_ok=True)
    (box / name).symlink_to(elsewhere)
    return thumbs, box, elsewhere


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync is what deploy.sh copies with")
def test_the_merge_writes_through_no_planted_part(tmp_path: Path) -> None:
    """A sources.json.part left as a symlink is replaced, never written through."""
    import json

    thumbs, box, elsewhere = _with_a_planted_link(tmp_path, "sources.json.part")

    run(tmp_path, thumbs, box)

    assert elsewhere.read_text(encoding="utf-8") == "not the service's\n"
    assert not (box / "sources.json").is_symlink()
    assert json.loads((box / "sources.json").read_text(encoding="utf-8")) == {
        "genesis": {"from": "drawn"},
        "home1-notes": {"from": "drawn"},
    }


@pytest.mark.skipif(shutil.which("rsync") is None, reason="rsync is what deploy.sh copies with")
@pytest.mark.parametrize("name", ["sources.json", ".sources.json.lock"])
def test_the_merge_refuses_a_symlinked_sources_or_lock(tmp_path: Path, name: str) -> None:
    """sources.json or its lock as a symlink stops the deploy here, before the wheel goes
    in, rather than reading or opening whatever it points at."""
    thumbs, box, elsewhere = _with_a_planted_link(tmp_path, name)

    run(tmp_path, thumbs, box, check=False)

    assert elsewhere.read_text(encoding="utf-8") == "not the service's\n"
    assert (box / name).is_symlink(), "left as found, for whoever looks into it"
