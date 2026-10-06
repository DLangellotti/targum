"""What a video link was found to be, remembered for an hour (2026-10-06).

A host asks `describe_source` about a link, the reader says yes, and the host asks
`quote_build` for the same link a few seconds later. Both ask the video's door what is
there, and until this module both paid for the asking in full: on the box a YouTube
answer is a `yt-dlp -J` through the residential proxy, seconds at best and a minute when
an exit is flagged, so the quote waited as long again for an answer it had just been
given. Measured on a laptop, which YouTube trusts and the box is not: 2.7–4.6 s a run
with no proxy at all. The quote now answers from here.

**Keyed by what the link names, not how it is spelt.** youtu.be, /shorts/ and a watch
address with `&t=` are one video, and the host quotes the `quote_with` address
`describe_source` handed it, which is the canonical one — so a key on the raw string
would miss on exactly the pair this exists for.

**An hour**, because what is remembered is a length, a title, a licence and which
subtitle tracks somebody wrote, and none of those moves within a conversation. A
subtitle track added in the meantime is priced at the next hour; the build fetches the
track itself and does not lean on this.

**A refusal for a minute.** "Private video" will be the answer again, and so will a
flagged exit a few seconds later; the quote that follows a refused describe would only
spend another twenty seconds being told the same thing. A minute is the time the reader
is told to wait ("Try again in a minute"), so the second try after that asks again.
`OffHere` — this machine has no yt-dlp — is not remembered: it is fixed by an operator,
not by waiting, and the next ask should see the fix.

**Bounded**: a few hundred answers, the least recently asked dropped first. One
`yt-dlp -J` answer is a few hundred kilobytes, so the bound is what keeps a busy hour
from becoming a memory leak.

In-process on purpose. The box runs one process; a second worker or a restart starts
cold and loses nothing but time.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from ..errors import OffHere, TargumError

#: How long an answer stands, in seconds.
KEEP_S = 3600.0
#: How long a refusal stands, in seconds.
REFUSED_S = 60.0
#: The most answers held at once.
MOST = 256


class Remembered:
    """A bounded, thread-safe map from a link's key to its answer, or its refusal."""

    def __init__(
        self,
        *,
        keep_s: float = KEEP_S,
        refused_s: float = REFUSED_S,
        most: int = MOST,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.keep_s = keep_s
        self.refused_s = refused_s
        self.most = most
        self.clock = clock
        self._lock = threading.Lock()
        #: key -> (clock time it lapses, the answer, or the refusal)
        self._held: OrderedDict[str, tuple[float, dict[str, Any] | TargumError]] = OrderedDict()

    def clear(self) -> None:
        with self._lock:
            self._held.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._held)

    def _get(self, key: str) -> dict[str, Any] | TargumError | None:
        with self._lock:
            held = self._held.get(key)
            if held is None:
                return None
            if self.clock() >= held[0]:
                del self._held[key]
                return None
            self._held.move_to_end(key)
            return held[1]

    def _put(self, key: str, value: dict[str, Any] | TargumError, lasts: float) -> None:
        with self._lock:
            self._held[key] = (self.clock() + lasts, value)
            self._held.move_to_end(key)
            while len(self._held) > self.most:
                self._held.popitem(last=False)

    def through(self, key: str, ask: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        """The remembered answer for `key`, or `ask()`'s, remembered on the way past.

        A copy each time, one level deep: a caller that fills in a field it was not
        given (`instagram.describe` does, for a reel's length) must not change what the
        next caller is handed.
        """
        if not key:
            return ask()
        held = self._get(key)
        if isinstance(held, TargumError):
            raise held
        if held is not None:
            return dict(held)
        try:
            answer = ask()
        except OffHere:
            raise
        except TargumError as refusal:
            self._put(key, refusal, self.refused_s)
            raise
        self._put(key, dict(answer), self.keep_s)
        return dict(answer)


#: The one shared by every door and both callers: `describe_source` and the quote.
DESCRIBED = Remembered()
