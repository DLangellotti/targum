"""robots.txt, for the fetches targum makes on its own (plan §5.2).

A reader's paste is a reader, not a crawler (`ingest/url.py`), and that stays true when
they press a find: the press is theirs. Finding is targum acting alone, so before the
first fetch on a host each day it reads `/robots.txt` through the one door and keeps
the answer for a day, read for `*` and for `targum`. A path it disallows is never
fetched, so never scored and never offered.

A robots.txt that is missing (a 404) allows everything, as the convention says. One that
will not answer at all — refused, timed out, unreadable — disallows the host for the day:
when a site cannot say, targum does not guess.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

#: How long one host's answer is kept, in seconds.
KEEP_S = 24 * 60 * 60.0

#: The name targum's own fetches go by, beside `*`.
AGENT = "targum"


class Robots:
    """Each host's robots.txt, read once a day."""

    def __init__(
        self,
        read: Callable[[str], str | None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._read = read or _read
        self.clock = clock
        self._lock = threading.Lock()
        #: scheme://host -> (clock time it goes stale, its parser or None for "no")
        self._kept: dict[str, tuple[float, RobotFileParser | None]] = {}

    def _parser(self, origin: str) -> RobotFileParser | None:
        with self._lock:
            kept = self._kept.get(origin)
            if kept is not None and self.clock() < kept[0]:
                return kept[1]
        body = self._read(origin + "/robots.txt")
        parser: RobotFileParser | None
        if body is None:
            parser = None
        else:
            parser = RobotFileParser()
            parser.parse(body.splitlines())
        with self._lock:
            self._kept[origin] = (self.clock() + KEEP_S, parser)
        return parser

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return False
        parser = self._parser(f"{parsed.scheme}://{parsed.netloc.lower()}")
        if parser is None:
            return False
        return parser.can_fetch(AGENT, url) and parser.can_fetch("*", url)

    def clear(self) -> None:
        with self._lock:
            self._kept.clear()


def _read(url: str) -> str | None:
    """A robots.txt through the door: its text, "" where there is none, None where the
    host would not say."""
    from ..errors import Unreachable
    from ..ingest.url import fetch

    try:
        return fetch(url, proxy=False).text
    except Unreachable as error:
        return "" if error.status in (404, 410) else None
    except Exception:  # noqa: BLE001 - a host that cannot say is a host not fetched
        return None


ROBOTS = Robots()
