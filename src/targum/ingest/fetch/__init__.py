"""Public domain sources, addressed by identifier rather than by URL."""

from __future__ import annotations

from typing import Protocol

from ...errors import UnsupportedSource
from ...kinds import PRIVATE, private_source
from ...models import Document
from .course import CourseFetcher
from .dialogue import DialogueFetcher
from .globalstorybooks import GlobalStorybooksFetcher
from .gutenberg import GutenbergFetcher
from .published import PublishedFetcher
from .sefaria import SefariaFetcher
from .siddur import SiddurFetcher
from .storyweaver import StoryWeaverFetcher
from .video import VideoFetcher
from .weekly import WeeklyFetcher
from .wikisource import WikisourceFetcher

__all__ = [
    "FETCHERS",
    "PRIVATE",
    "Fetcher",
    "addressable",
    "is_identifier",
    "load",
    "private_source",
]


class Fetcher(Protocol):
    @property
    def name(self) -> str:
        """Name and version, recorded on the document it produces."""

    def load(self, identifier: str) -> Document: ...


FETCHERS: dict[str, Fetcher] = {
    "course": CourseFetcher(),
    "dialogue": DialogueFetcher(),
    "globalstorybooks": GlobalStorybooksFetcher(),
    "gutenberg": GutenbergFetcher(),
    "published": PublishedFetcher(),
    "sefaria": SefariaFetcher(),
    "siddur": SiddurFetcher(),
    "storyweaver": StoryWeaverFetcher(),
    "wikisource": WikisourceFetcher(),
    "weekly": WeeklyFetcher(),
    "video": VideoFetcher(),
}


def is_identifier(source: str) -> bool:
    scheme, sep, rest = source.partition(":")
    return bool(sep) and scheme.lower() in FETCHERS and bool(rest)


def addressable(source: str) -> bool:
    """Whether a request may name this identifier: a fetcher's, and not one whose kind is
    private (`kinds.PRIVATE`): a private fetcher reads a reader's own file, and a link
    pasted into the Add page, the chat or Telegram would read whatever the server holds
    under that name (targum-internal#652)."""
    return is_identifier(source) and source.partition(":")[0].lower() not in PRIVATE


def load(source: str) -> Document:
    scheme, _, rest = source.partition(":")
    fetcher = FETCHERS.get(scheme.lower())
    if fetcher is None:
        raise UnsupportedSource(
            f"No such source: {scheme}", f"Available: {', '.join(sorted(FETCHERS))}"
        )
    return fetcher.load(rest)
