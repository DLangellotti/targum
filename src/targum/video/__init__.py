"""Video import: the same recording import, with the pictures allowed to ride along.

A video source runs the audio pipeline unchanged — probe, parts, transcription,
alignment, translation are all about the soundtrack — and keeps one thing extra: a
modest-resolution cut of each part, standing beside the reader as a sidecar file. The
audio package's "a gigabyte of film for five minutes of sound is the wrong trade"
still holds where sound is all that was asked for; here the film is the thing asked for.
"""

from __future__ import annotations

import shutil
from pathlib import Path

#: What a video import may arrive as. Closed, for the same reason `AUDIO_SUFFIXES` is.
VIDEO_SUFFIXES = frozenset({".mp4", ".m4v", ".mov", ".webm", ".mkv"})

#: Four hours, tighter than audio's twelve: a part of video runs 50-100 MB where a part
#: of speech runs two, and the ceiling has to answer for the disk it implies.
MAX_VIDEO_DURATION_S = 14_400.0

#: The most a single video file may be, downloaded or uploaded.
MAX_VIDEO_BYTES = 4 * 1024**3

#: What a part is transcoded to: enough to read a face and a slide, small enough that a
#: twelve-minute part stays under ~100 MB beside the reader.
VIDEO_HEIGHT = 480
VIDEO_CRF = 28
VIDEO_AUDIO_BITRATE = "64k"


def is_video(source: str) -> bool:
    """Whether this source names a video file, by its suffix alone."""
    return Path(source).suffix.lower() in VIDEO_SUFFIXES


def ytdlp_available() -> tuple[bool, str]:
    """Whether YouTube can be fetched at all, and what to do about it if not."""
    if shutil.which("yt-dlp"):
        return True, "yt-dlp"
    return False, "install yt-dlp. YouTube imports are off until it is."
