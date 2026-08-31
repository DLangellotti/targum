"""What a recording is, asked once and written down beside it."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from ..errors import TargumError
from ..paths import write_atomic
from ..video import MAX_VIDEO_DURATION_S
from . import DRM_SUFFIXES, MAX_DURATION_S, MIN_DURATION_S, tools

PROBE = "probe.json"


class Mark(BaseModel):
    """One chapter mark the file itself carries."""

    start: float
    end: float
    title: str = ""


class Probe(BaseModel):
    """What ffprobe said, kept so it is never asked twice of a gigabyte."""

    duration: float
    sha256: str
    title: str = ""
    artist: str = ""
    codec: str = ""
    has_video: bool = False
    chapters: list[Mark] = Field(default_factory=list)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for piece in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(piece)
    return digest.hexdigest()


def _floated(raw: Any) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def examine(path: Path, *, allow_video: bool = False) -> Probe:
    """Probe the file, and refuse what an import must not accept.

    `allow_video` is set only when the import chose the video path by the source's own
    suffix or address. An audio-suffixed file hiding a video stream is still refused —
    the routing decides what the file may be, not the file.
    """
    if path.suffix.lower() in DRM_SUFFIXES:
        raise TargumError("This file is protected, so targum cannot read it.")
    answer = tools.ffprobe_json(path)
    form = answer.get("format") or {}
    tags = {str(k).lower(): str(v) for k, v in (form.get("tags") or {}).items()}
    streams = answer.get("streams") or []
    sound = [s for s in streams if s.get("codec_type") == "audio"]
    moving = [
        s
        for s in streams
        if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")
    ]
    if not sound and moving:
        raise TargumError("There is nothing to transcribe in a silent video.")
    if not sound or (moving and not allow_video):
        # A film with a soundtrack is not a recording, and extracting one from the
        # other is a different product. Attached cover art is not moving pictures.
        raise TargumError(tools.UNREADABLE)
    length = _floated(form.get("duration"))
    if length < MIN_DURATION_S:
        raise TargumError(tools.UNREADABLE)
    if moving and length > MAX_VIDEO_DURATION_S:
        raise TargumError("That video is over 4 hours.")
    if length > MAX_DURATION_S:
        raise TargumError("That recording is over 12 hours.")
    marks = [
        Mark(
            start=_floated(chapter.get("start_time")),
            end=_floated(chapter.get("end_time")),
            title=str((chapter.get("tags") or {}).get("title") or ""),
        )
        for chapter in (answer.get("chapters") or [])
    ]
    return Probe(
        duration=length,
        sha256=sha256(path),
        title=tags.get("title", ""),
        artist=tags.get("artist", ""),
        codec=str(sound[0].get("codec_name") or ""),
        has_video=bool(moving),
        chapters=[m for m in marks if m.end > m.start],
    )


def adopt(source: Path, workspace: Path, *, move: bool = False, allow_video: bool = False) -> Path:
    """The recording, inside the targum's own folder, with its probe beside it.

    Copied rather than moved unless asked: a file named on the command line is the
    reader's own and stays theirs. The server moves, because its copy in `uploads/` is
    already the only one.
    """
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / f"source{source.suffix.lower()}"
    if source.resolve() != target.resolve():
        if move:
            shutil.move(str(source), str(target))
        else:
            shutil.copy2(source, target)
    checked = examine(target, allow_video=allow_video)
    write_atomic(workspace / PROBE, checked.model_dump_json(indent=2) + "\n")
    return target


def load(workspace: Path) -> Probe | None:
    path = workspace / PROBE
    if not path.exists():
        return None
    try:
        return Probe.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - a malformed probe reads as absent, and is redone
        return None
