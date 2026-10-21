"""A video import's picture: one frame of its own cut (design.md §12, 2026-09-24).

The shelf draws a cover where the library drew one and the text's first letter where it
did not, and a video somebody brought in had only the letter. Its own film is the obvious
picture, and it is already beside the reader. A YouTube thumbnail would be a fetch from
somebody else's server for every reader's import. The library's own videos are the one
exception, fetched once by `targum thumbs` under each video's CC BY and served from the
box (design.md §12, "Every text has a picture").
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..audio import manifest as manifest_module
from ..audio.manifest import POSTER

#: How wide the picture is kept: the shelf draws it at 56px, a phone card at about 200.
WIDTH = 480


def ensure(folder: Path) -> bool:
    """Write the poster beside a video import if it has none, and say whether it has one.

    Best effort: a text with no video, a missing cut or a failing ffmpeg leaves the letter
    tile, and never stops the build that asked.
    """
    target = folder / POSTER
    if target.is_file():
        return True
    kept = manifest_module.load(folder)
    part = next((one for one in (kept.parts if kept else []) if one.video), None)
    if part is None:
        return False
    source = folder / part.video
    if not source.is_file():
        return False
    # A second in, past a fade from black, or the middle of a cut shorter than two.
    at = min(1.0, max(0.0, (part.end - part.start) / 2))
    return still(source, target, at)


def still(source: Path, target: Path, at: float, width: int = WIDTH) -> bool:
    """One frame of `source`, `at` seconds in, written whole to `target` as a JPEG, or
    nothing. Best effort, as `ensure` is: a failing ffmpeg leaves no file and says so."""
    partial = target.with_suffix(".part.jpg")
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-ss",
                f"{at:.3f}",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                f"scale='min({width},iw)':-2",
                "-q:v",
                "4",
                str(partial),
            ],
            capture_output=True,
            check=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        partial.unlink(missing_ok=True)
        return False
    if not partial.is_file() or partial.stat().st_size == 0:
        partial.unlink(missing_ok=True)
        return False
    partial.replace(target)
    return True


#: Where a part's frame is kept, beside the reader's folder rather than in it — a build
#: empties the folder, and the film under a frame does not change — for the contents
#: page's filmstrip (design.md §12, "A contents page is a page of its own", 2026-10-09).
FRAMES = "frames"


def frame_name(number: int) -> str:
    return f"part-{number:03d}.jpg"


def part_frames(folder: Path) -> dict[int, str]:
    """A frame of each part's own film, kept in the text's `frames/`, by part number, as
    the path the contents page names it by from beside the reader's pages.

    Cut from the film already on the disk, a tenth of the way in — past a title card,
    short of the end — and never fetched. A part not made yet, or with no film, has none,
    and its cell says it is getting ready. A frame already there is kept."""
    kept = manifest_module.load(folder)
    if kept is None:
        return {}
    found: dict[int, str] = {}
    for part in kept.parts:
        if not part.video:
            continue
        source = folder / part.video
        target = folder / FRAMES / frame_name(part.number)
        if not target.is_file():
            if not source.is_file():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            at = max(0.0, min(30.0, (part.end - part.start) / 10))
            if not still(source, target, at):
                continue
        found[part.number] = f"../{FRAMES}/{target.name}"
    return found
