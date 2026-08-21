"""The provider interface, and the batching every provider shares."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Protocol

from ..models import Segment, Style

Progress = Callable[[int], None]


class Provider(Protocol):
    """One way of turning source segments into target text.

    Providers return a mapping keyed by segment ID, never a list. Order is not a
    contract; the ID is.
    """

    name: str
    needs_key: bool

    def available(self) -> tuple[bool, str]: ...

    def translate(
        self,
        segments: list[Segment],
        source_language: str,
        target_language: str,
        style: Style,
        on_progress: Progress | None = None,
    ) -> dict[str, str]: ...


def batches(segments: list[Segment], size: int) -> Iterator[list[Segment]]:
    for start in range(0, len(segments), size):
        yield segments[start : start + size]


def context_window(segments: list[Segment], batch: list[Segment], span: int = 2) -> tuple[str, str]:
    """The sentences on either side of a batch, as prose.

    Translation quality depends on knowing what came before; alignment depends on not
    letting that context leak into the output. So context goes in as plain text and
    only the batch is asked for back.
    """
    first = segments.index(batch[0])
    last = segments.index(batch[-1])
    before = " ".join(s.text for s in segments[max(0, first - span) : first])
    after = " ".join(s.text for s in segments[last + 1 : last + 1 + span])
    return before, after
