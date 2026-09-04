"""Public domain sources, addressed by identifier rather than by URL."""

from __future__ import annotations

from typing import Protocol

from ...errors import UnsupportedSource
from ...models import Document
from .dialogue import DialogueFetcher
from .gutenberg import GutenbergFetcher
from .sefaria import SefariaFetcher
from .siddur import SiddurFetcher
from .video import VideoFetcher
from .weekly import WeeklyFetcher
from .wikisource import WikisourceFetcher

__all__ = ["FETCHERS", "Fetcher", "is_identifier", "load"]


class Fetcher(Protocol):
    @property
    def name(self) -> str:
        """Name and version, recorded on the document it produces."""

    def load(self, identifier: str) -> Document: ...


FETCHERS: dict[str, Fetcher] = {
    "dialogue": DialogueFetcher(),
    "gutenberg": GutenbergFetcher(),
    "sefaria": SefariaFetcher(),
    "siddur": SiddurFetcher(),
    "wikisource": WikisourceFetcher(),
    "weekly": WeeklyFetcher(),
    "video": VideoFetcher(),
}


def is_identifier(source: str) -> bool:
    scheme, sep, rest = source.partition(":")
    return bool(sep) and scheme.lower() in FETCHERS and bool(rest)


def load(source: str) -> Document:
    scheme, _, rest = source.partition(":")
    fetcher = FETCHERS.get(scheme.lower())
    if fetcher is None:
        raise UnsupportedSource(
            f"No such source: {scheme}", f"Available: {', '.join(sorted(FETCHERS))}"
        )
    return fetcher.load(rest)
