"""A video import's picture: one frame of its own cut (design.md §12, 2026-09-24).

The shelf draws a cover where the library drew one and the text's first letter where it
did not, and a video somebody brought in had only the letter. Its own film is the obvious
picture, and it is already beside the reader. A YouTube thumbnail would be a fetch from
somebody else's server, which neither the policy nor the fetch-nothing rule allows.
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
                f"scale='min({WIDTH},iw)':-2",
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
