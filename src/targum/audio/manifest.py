"""The one file the renderer reads: which part holds each line, and where.

Beside document.json rather than in a global recordings folder, so the audio travels
with the text — into the trash, out of it, onto another disk — and so the page finds it
with no restart and no registry: the manifest either sits beside the reader or it does
not, and that is the whole claim.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from ..paths import write_atomic

MANIFEST = "audio.json"


class ManifestPart(BaseModel):
    number: int
    title: str = ""
    #: Seconds into the whole recording. The spans below are into this part's own file.
    start: float
    end: float
    #: The cut file, relative to the targum's folder, or "" while untranscribed.
    audio: str = ""
    transcribed: bool = False
    provider: str = ""
    refiner: str = ""
    spans: dict[str, list[float]] = Field(default_factory=dict)
    #: Per segment, each written word's clock: [charStart, charEnd, start, end], the
    #: char offsets into the segment's own text. What lets a card play one word.
    words: dict[str, list[list[float]]] = Field(default_factory=dict)
    speakers: dict[str, str] = Field(default_factory=dict)


class AudioManifest(BaseModel):
    source: str
    sha256: str
    duration: float
    language: str
    parts: list[ManifestPart] = Field(default_factory=list)

    def part_for(self, segment_ids: list[str]) -> ManifestPart | None:
        """The part that holds these lines — by what the spans contain, never by
        position, for the reason `recording.Recording.part_for` records."""
        wanted = [sid for sid in segment_ids if sid]
        if not wanted:
            return None
        for part in self.parts:
            if any(sid in part.spans for sid in wanted):
                return part
        return None


def write(folder: Path, manifest: AudioManifest) -> None:
    write_atomic(folder / MANIFEST, manifest.model_dump_json(indent=2) + "\n")


def load(folder: Path) -> AudioManifest | None:
    path = folder / MANIFEST
    if not path.exists():
        return None
    try:
        return AudioManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - a malformed manifest must not stop a build
        return None
