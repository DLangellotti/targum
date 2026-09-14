"""The transcriber interface. One method, priced by the minute."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from ..usage import Usage
from .models import Transcript

Progress = Callable[[int], None]

#: What a provider may answer for a language, and the tag the rest of targum means by it.
#: Whisper answers with a name ("hebrew"); Scribe is documented to answer "en" and accepts
#: ISO-639-3 besides, so "heb" is a spelling it may use. Every rule downstream asks the
#: short tag — the rule that reads English past inside Hebrew asks for exactly "he", and
#: handed "heb" it would read every English word in as a word of the text (2026-09-14).
LANGUAGE_TAGS = {
    "hebrew": "he", "heb": "he", "iw": "he",
    "yiddish": "yi", "yid": "yi",
    "english": "en", "eng": "en",
    "russian": "ru", "rus": "ru",
    "ukrainian": "uk", "ukr": "uk",
    "arabic": "ar", "ara": "ar",
    "french": "fr", "fra": "fr", "fre": "fr",
    "italian": "it", "ita": "it",
    "aramaic": "arc",
}  # fmt: skip


def language_tag(said: str) -> str:
    """The short tag for what a provider said the recording is in; "" for nothing."""
    lowered = (said or "").strip().lower().replace("_", "-").split("-")[0]
    return LANGUAGE_TAGS.get(lowered, lowered if len(lowered) <= 3 else "")


class Transcriber(Protocol):
    """One way of turning a recording into words with clocks.

    Providers return words timed against the file they were handed — a part's own cut,
    never the whole book. What a call really cost accumulates on `spent`, in seconds,
    the way the translation providers accumulate tokens.
    """

    name: str
    model: str
    needs_key: bool
    spent: Usage

    def available(self) -> tuple[bool, str]: ...

    def price_per_minute(self) -> float: ...

    def transcribe(
        self,
        audio: Path,
        language: str = "",
        on_progress: Progress | None = None,
    ) -> Transcript: ...
