"""Transcription providers: a recording in, words with clocks out.

Priced by the minute, which is the axis `Usage` counts them on. Prices live here, with
the providers, for the reason the translation prices live with theirs: they are a
property of the model rather than of counting, and a model nobody has priced counts
its seconds and costs nothing — an unknown price is not zero, but pretending to know
it is worse.
"""

from __future__ import annotations

import os
from typing import cast

from ..errors import ProviderError
from .base import Transcriber
from .elevenlabs import ScribeTranscriber
from .null import NullTranscriber
from .openai_whisper import WhisperTranscriber

__all__ = ["PRICES", "Transcriber", "build", "default_name", "names"]

#: Dollars per minute of audio, by the name each provider reports on its usage.
PRICES: dict[str, float] = {
    "openai/whisper-1": 0.006,
    "elevenlabs/scribe_v2": 0.0067,
}

_BUILDERS: dict[str, type] = {
    "null": NullTranscriber,
    "openai": WhisperTranscriber,
    "elevenlabs": ScribeTranscriber,
}


def names() -> list[str]:
    return sorted(_BUILDERS)


def default_name() -> str:
    """Which transcriber runs when nobody names one.

    The environment first, then whichever paid provider has a key on this machine —
    Scribe before whisper, because its Hebrew is the better of the two and the reader
    lives with the transcript.
    """
    named = os.environ.get("TARGUM_TRANSCRIBER", "")
    if named:
        return named
    if os.environ.get("ELEVENLABS_API_KEY"):
        return "elevenlabs"
    return "openai"


def build(name: str, **options: object) -> Transcriber:
    builder = _BUILDERS.get(name)
    if builder is None:
        raise ProviderError(f"No transcriber named '{name}'.", f"Available: {', '.join(names())}")
    return cast(Transcriber, builder(**options))
