"""Every ffmpeg and ffprobe call, in one place, so tests can stand in for the binaries.

Subprocess rather than a Python audio library — the same position `recording/cut.py`
takes: one dependency not taken is one that cannot break, and ffmpeg is the tool that
actually knows every container this will meet.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from ..errors import TargumError
from . import BITRATE

#: Below this many dB of the peak counts as silence, held for at least this long. The
#: values the dialogue writer settled on, which found every seam TTS left; speech
#: recorded in a room needs the pause to be longer than a breath, hence 0.4 not 0.18.
FLOOR_DB = 35
LEAST_SILENCE_S = 0.4

_SILENCE_START = re.compile(r"silence_start:\s*([0-9.]+)")
_SILENCE_END = re.compile(r"silence_end:\s*([0-9.]+)")

UNREADABLE = "targum could not read this audio file."


def ffprobe_json(path: Path) -> dict[str, Any]:
    """What ffprobe knows about the file: format, streams, chapters, tags."""
    try:
        done = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_chapters",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise TargumError(UNREADABLE) from error
    try:
        answer: dict[str, Any] = json.loads(done.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError as error:
        raise TargumError(UNREADABLE) from error
    return answer


def duration(path: Path) -> float:
    raw = ffprobe_json(path).get("format", {}).get("duration")
    try:
        return float(raw)
    except (TypeError, ValueError) as error:
        raise TargumError(UNREADABLE) from error


def cut(source: Path, into: Path, start: float, end: float) -> None:
    """One part of the recording, re-encoded rather than stream-copied.

    `-c copy` cuts on frame boundaries, which moves the start by up to a frame and
    leaves every span in the part off by that much. A span is aligned to a tenth of a
    second, so the cut re-encodes — the same decision `recording/cut.py` records.
    """
    into.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-ss",
                f"{max(0.0, start):.3f}",
                "-to",
                f"{end:.3f}",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "1",
                "-b:a",
                BITRATE,
                str(into),
            ],
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        # ffmpeg writes in place, so a failure leaves a truncated file — and a file
        # that exists is a file the next build trusts. Gone with the error.
        into.unlink(missing_ok=True)
        raise TargumError(UNREADABLE) from error


def cut_video(source: Path, into: Path, start: float, end: float) -> None:
    """One part of a video, pictures kept, at the sidecar's modest size.

    The same `-ss`/`-to` re-encode as `cut()`, for the same reason: a stream copy moves
    the cut to a keyframe, and the spans in the part are aligned tighter than that. The
    two cuts share their start and end exactly, so a span timed against the part's mp3
    holds against its mp4. `faststart` moves the index to the front — a player behind a
    Range request reads the tail first otherwise, which is a second round trip per part.
    """
    from ..video import VIDEO_AUDIO_BITRATE, VIDEO_CRF, VIDEO_HEIGHT

    into.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-y",
                "-ss",
                f"{max(0.0, start):.3f}",
                "-to",
                f"{end:.3f}",
                "-i",
                str(source),
                "-vf",
                # floor to even: -2 keeps the width even, and an odd source height
                # under the ceiling would otherwise fail yuv420p outright.
                f"scale=-2:'min({VIDEO_HEIGHT},floor(ih/2)*2)'",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                str(VIDEO_CRF),
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                VIDEO_AUDIO_BITRATE,
                "-movflags",
                "+faststart",
                str(into),
            ],
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        # A truncated mp4 left behind would be recorded by the next manifest write
        # and never re-cut — the guard is `exists()`, so failure must leave nothing.
        into.unlink(missing_ok=True)
        raise TargumError(UNREADABLE) from error


def silences(path: Path, start: float, length: float) -> list[tuple[float, float]]:
    """The silences in one window of the file, in seconds into the whole file.

    ffmpeg writes silencedetect's findings to stderr as prose; parsing that prose is
    the documented interface. Timestamps come back relative to the seek point, so the
    window's own start is added before anything is returned.
    """
    try:
        done = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-ss",
                f"{max(0.0, start):.3f}",
                "-t",
                f"{length:.3f}",
                "-i",
                str(path),
                "-af",
                f"silencedetect=noise=-{FLOOR_DB}dB:d={LEAST_SILENCE_S}",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise TargumError(UNREADABLE) from error
    text = done.stderr.decode("utf-8", "replace")
    starts = [float(m.group(1)) for m in _SILENCE_START.finditer(text)]
    ends = [float(m.group(1)) for m in _SILENCE_END.finditer(text)]
    found: list[tuple[float, float]] = []
    for a, b in zip(starts, ends, strict=False):
        if b > a:
            found.append((start + a, start + b))
    return found
