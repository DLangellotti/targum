"""A provider that echoes its input.

Every test runs through this one, so the suite costs nothing and works offline.
"""

from __future__ import annotations

from ..models import Segment, Style
from .base import Progress


class NullProvider:
    name = "null"
    needs_key = False
    default_model = None

    def available(self) -> tuple[bool, str]:
        return True, "echoes the source, for testing"

    def translate(
        self,
        segments: list[Segment],
        source_language: str,
        target_language: str,
        style: Style,
        on_progress: Progress | None = None,
    ) -> dict[str, str]:
        if on_progress:
            on_progress(len(segments))
        return {segment.id: segment.text for segment in segments}
