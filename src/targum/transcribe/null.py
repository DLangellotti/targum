"""A transcriber that invents nothing but its clocks. For tests, and costs nothing."""

from __future__ import annotations

from pathlib import Path

from ..usage import Usage
from .base import Progress
from .models import Transcript, Word


class NullTranscriber:
    """Spreads a given text evenly over the file's length.

    The text is a parameter rather than read from anywhere: what the tests assert is
    the plumbing — parts, caching, spans, budgets — and a second of silence keeps the
    same time as a second of speech.
    """

    name = "null"
    model = ""
    needs_key = False

    def __init__(
        self,
        text: str = "",
        language: str = "he",
        speakers: int = 1,
    ) -> None:
        self.text = text
        self.language = language
        self.speakers = max(1, speakers)
        self.spent = Usage()

    def available(self) -> tuple[bool, str]:
        return True, "invents a transcript, for testing"

    def price_per_minute(self) -> float:
        return 0.0

    def transcribe(
        self,
        audio: Path,
        language: str = "",
        on_progress: Progress | None = None,
    ) -> Transcript:
        from ..audio import tools

        length = tools.duration(audio)
        pieces = self.text.split()
        step = length / max(1, len(pieces))
        words = [
            Word(
                text=piece,
                start=round(index * step, 3),
                end=round((index + 1) * step, 3),
                speaker=str(index * self.speakers // max(1, len(pieces)) + 1)
                if self.speakers > 1
                else "",
            )
            for index, piece in enumerate(pieces)
        ]
        self.spent.add_seconds(self.name, length)
        if on_progress:
            on_progress(len(words))
        return Transcript(
            provider=self.name,
            language=self.language,
            duration=length,
            words=words,
        )
