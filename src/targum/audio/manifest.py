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
    #: The part's video cut, same convention, or "" for a soundtrack-only source. The
    #: same padded start and end as the audio cut, so one set of spans times both.
    video: str = ""
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
    #: The address the recording was fetched from, where it had one, and "" for a file
    #: somebody uploaded. `source` is the local file by the time this is written — the
    #: build adopts what it fetched — so without this the page could not say where the
    #: video lives, which for a YouTube import is the one link a reader should be handed
    #: back: targum holds a study copy, and the video's home is not here.
    home: str = ""
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


def keeps_video(folder: Path) -> bool:
    """Whether the import beside this reader kept its pictures.

    Asked of the manifest, not of the `video/` sidecar folder: the sidecar is a copy the
    build makes and remakes, while the manifest is the claim. A part that lost its cut
    is a soundtrack, and a manifest with no video in any part is an audio import.
    """
    kept = load(folder)
    return kept is not None and any(part.video for part in kept.parts)


def load(folder: Path) -> AudioManifest | None:
    path = folder / MANIFEST
    if not path.exists():
        return None
    try:
        return AudioManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - a malformed manifest must not stop a build
        return None
