"""Public domain sources, addressed by identifier rather than by URL."""

from __future__ import annotations

from typing import Protocol

from ...errors import UnsupportedSource
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


#: Fetchers that read a reader's own file rather than a public source, and so answer only
#: a build that names them: never a link pasted into the Add page, the chat or Telegram,
#: where an identifier would read whatever the server holds under that name. A course
#: book's extract is somebody's copy of a book in copyright (targum-internal#652).
PRIVATE = frozenset({"course"})


def is_identifier(source: str) -> bool:
    scheme, sep, rest = source.partition(":")
    return bool(sep) and scheme.lower() in FETCHERS and bool(rest)


def addressable(source: str) -> bool:
    """Whether a request may name this identifier: a fetcher's, and not a private one."""
    return is_identifier(source) and source.partition(":")[0].lower() not in PRIVATE


def private_source(source: str, ingester: str = "") -> bool:
    """Whether a built text is private by what it is, wherever it was built.

    Where a text sits decides most of it (`ledger.home_of`); this is the rest, so a
    course book built into the library's own folder, or by `targum build` into
    `./targum-out`, is still never counted, pooled or exported (qa-claude on #1121).
    Asked of the source's kind and of the ingester's name both, so a source renamed, or
    written by hand into `document.json`, is still caught by what read it.

    Not every kind this module does not know: the library's own texts carry kinds no
    fetcher reads (`parasha:`, a catalogue row's), and calling those private would flip
    the corpus ledger's rows for the shelf.
    """
    kind = source.strip().partition(":")[0].lower() if ":" in source else ""
    return kind in PRIVATE or ingester.strip().partition("/")[0].lower() in PRIVATE


def load(source: str) -> Document:
    scheme, _, rest = source.partition(":")
    fetcher = FETCHERS.get(scheme.lower())
    if fetcher is None:
        raise UnsupportedSource(
            f"No such source: {scheme}", f"Available: {', '.join(sorted(FETCHERS))}"
        )
    return fetcher.load(rest)
