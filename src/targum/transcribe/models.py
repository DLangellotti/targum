"""What a transcription is, at each of its two stages.

A `Transcript` is what a provider heard: words with clocks, kept raw so a better
refiner can revisit it for nothing. A `Refined` is what a reader will read: the same
words gathered into paragraphs, with everything that was never speech dropped. Every
paragraph keeps its words, so the timings survive any refiner — including one that
rewrites the punctuation — as long as each kept word still maps to a heard one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, Field

from ..ids import content_hash
from ..paths import write_atomic


class Word(BaseModel):
    """One word as heard: its text, its clock, and how sure the provider was."""

    text: str
    #: Seconds into the file that was transcribed — a part's own file, not the book.
    start: float
    end: float
    confidence: float = 1.0
    speaker: str = ""
    #: Laughter, music, an ad sting — something tagged as sound rather than speech.
    event: bool = False


class Transcript(BaseModel):
    provider: str
    model: str = ""
    language: str = ""
    duration: float = 0.0
    words: list[Word] = Field(default_factory=list)


class RefinedParagraph(BaseModel):
    text: str
    speaker: str = ""
    words: list[Word] = Field(default_factory=list)


class Refined(BaseModel):
    refiner: str
    provider: str = ""
    language: str = ""
    paragraphs: list[RefinedParagraph] = Field(default_factory=list)


def transcript_hash(transcript: Transcript) -> str:
    """What this transcript is, for keying the refinement that reads it."""
    return content_hash(transcript.model_dump_json())


M = TypeVar("M", bound=BaseModel)


def write(path: Path, model: BaseModel) -> None:
    write_atomic(path, model.model_dump_json(indent=2) + "\n")


def load(cls: type[M], path: Path) -> M | None:
    if not path.exists():
        return None
    try:
        return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - a malformed artifact reads as absent
        return None
