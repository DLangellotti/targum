"""The refiner interface: from words heard to paragraphs somebody can read.

Versioned by name, like every stage that can improve: renaming a refiner redoes its
work everywhere for nothing, because the transcript it reads is cached and paid for.
"""

from __future__ import annotations

from typing import Protocol

from ..models import Refined, Transcript


class Refiner(Protocol):
    name: str

    def refine(self, transcript: Transcript) -> Refined: ...
