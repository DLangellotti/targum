"""The transcriber interface. One method, priced by the minute."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from ..usage import Usage
from .models import Transcript

Progress = Callable[[int], None]


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
