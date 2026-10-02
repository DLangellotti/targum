"""deploy/ship-audio.sh refuses to delete what only the box holds (targum-internal#402).

Every copy in the script is an `rsync --delete`, so a run from a machine missing part of
the shelf takes that part off the box. These run the script itself against a stand-in
`ssh` and `rsync` on PATH: the "box" is a local folder, and an rsync that was reached is
a line in a log.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"
SCRIPT = DEPLOY / "ship-audio.sh"

FAKE_SSH = """#!/usr/bin/env bash
shift
case "$1" in
  find*) [ -n "${FAKE_SSH_FAILS:-}" ] && exit 255; bash -c "$1" ;;
  *) cat >/dev/null 2>&1 || true ;;
esac
"""

FAKE_RSYNC = """#!/usr/bin/env bash
echo "$*" >> "$RSYNC_LOG"
"""


def shelf(root: Path, recordings: list[str], scenes: list[str]) -> tuple[Path, Path]:
    rec = root / "recordings"
    dia = root / "dialogues"
    rec.mkdir(parents=True)
    dia.mkdir(parents=True)
    for name in recordings:
        (rec / name).mkdir()
        (rec / name / "recording.json").write_text("{}")
    for name in scenes:
        (dia / name).write_text("{}")
    return rec, dia


def run(
    tmp_path: Path, here: list[str], there: list[str], **env: str
) -> subprocess.CompletedProcess[str]:
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for name, body in (("ssh", FAKE_SSH), ("rsync", FAKE_RSYNC)):
        (bin_ / name).write_text(body)
        (bin_ / name).chmod(0o755)
    rec, dia = shelf(tmp_path / "laptop", here, ["01-hello.json"])
    box_rec, box_dia = shelf(tmp_path / "box", there, ["01-hello.json"])
    # Finder litter on the box is not a recording, and must not stop a ship.
    (box_rec / "._DS_Store").write_text("")
    return subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{bin_}:{os.environ['PATH']}",
            "RSYNC_LOG": str(tmp_path / "rsync.log"),
            "TARGUM_HOST": "root@box.invalid",
            "TARGUM_RECORDING_DIR": str(rec),
            "TARGUM_DIALOGUE_DIR": str(dia),
            "TARGUM_VIDEO_DIR": str(tmp_path / "no-videos"),
            "TARGUM_REMOTE_RECORDINGS": str(box_rec),
            "TARGUM_REMOTE_DIALOGUES": str(box_dia),
            "TARGUM_REMOTE_VIDEOS": str(tmp_path / "box" / "videos"),
            **env,
        },
    )


def test_it_parses() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)


def test_a_recording_only_the_box_holds_stops_the_ship_and_is_named(tmp_path: Path) -> None:
    got = run(tmp_path, here=["genesis"], there=["genesis", "la-parure"])
    assert got.returncode != 0
    assert "la-parure" in got.stderr
    assert "genesis" not in got.stderr.replace(str(tmp_path), "")
    assert not (tmp_path / "rsync.log").exists(), "nothing may be copied once the box holds more"


def test_a_box_that_holds_nothing_extra_is_shipped(tmp_path: Path) -> None:
    got = run(tmp_path, here=["genesis", "exodus"], there=["genesis"])
    assert got.returncode == 0, got.stderr
    assert "--delete" in (tmp_path / "rsync.log").read_text()


def test_a_box_that_cannot_be_asked_is_not_read_as_empty(tmp_path: Path) -> None:
    got = run(tmp_path, here=["genesis"], there=["genesis", "la-parure"], FAKE_SSH_FAILS="1")
    assert got.returncode != 0
    assert not (tmp_path / "rsync.log").exists()
