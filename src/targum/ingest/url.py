"""A web page, reduced to the text a reader came for."""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import socket
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from ..errors import TargumError, Unreachable
from ..models import Document
from .base import (
    Paragraph,
    blocks_from_paragraphs,
    build_document,
    normalize,
    with_front_matter,
)
from .htmltext import paragraphs_from_html

log = logging.getLogger(__name__)

#: What targum is, kept for the record and for `robots.txt` — but no longer what the
#: wire sees. Decided 2026-09-08: the door presents a browser, fingerprint and
#: User-Agent alike. Six of the seven Hebrew hosts recorded as unreachable were not
#: refusing an address; they were serving Cloudflare's bot check to anything whose TLS
#: handshake did not look like a browser's, and `httpx` never will. A reader asking for
#: one page is a reader, not a crawler, and this door opens what their own browser opens.
USER_AGENT = "targum/0.1 (+https://github.com/DLangellotti/targum)"
#: The browser the handshake imitates. `curl_cffi` sends the matching User-Agent
#: itself; setting our own on top would give a fingerprint that disagrees with its
#: headers, which is its own tell — israelhayom.co.il refused exactly that.
BROWSER = "chrome"
TIMEOUT = 30.0

#: The least time between two knocks on one host, in seconds. The fetch door is polite
#: because it has to be: one afternoon of careless probing from a laptop on 2026-09-08
#: had that address served a bot check by hosts that answered it in the morning, and
#: the box's address is the product's. A reader never notices a second and a half.
POLITE_S = 1.5

#: Where a refused fetch is retried from. `TARGUM_FETCH_PROXY`, else the YouTube
#: egress (targum-internal#205), so a box with one proxy stays a one-knob box; two knobs
#: because geo-targeting on a residential provider is a parameter on the same account,
#: and articles can ask for an Israeli exit while video takes whatever YouTube tolerates.
FETCH_PROXY_ENV = "TARGUM_FETCH_PROXY"

# An article a reader wants is hundreds of kilobytes. There was a timeout but no size
# limit, so a server that answers slowly and forever could take the machine down
# without ever timing out.
MAX_BYTES = 8 * 1024 * 1024

# Redirects are followed by hand rather than by httpx, because every hop has to be
# checked. Following them automatically is what turns one safe-looking address into a
# request to somewhere else entirely.
MAX_REDIRECTS = 5


def _reachable(url: str) -> None:
    """Refuse a URL that is not a public web page.

    The address being fetched is whatever a reader typed, and hosted, this runs on a
    server with a private network around it and a metadata endpoint sitting on
    169.254.169.254 handing out credentials to anything that asks. So the scheme is
    restricted, and every address the host resolves to has to be a public one.

    Checked on every hop rather than once: a public URL that redirects to a private
    address is the ordinary shape of this, and it defeats checking only the first.

    What this does not stop is a name that answers with a public address here and a
    private one when httpx connects a moment later. Closing that means pinning the
    connection to the address that was checked, which is a bigger change than this;
    the window is small and every other route in is shut.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise TargumError(
            f"We only read web pages, and {url} isn't one.",
            "Paste an http:// or https:// address, or drop in a file.",
            key="fetch.not-a-web-page",
            url=url,
        )
    host = parsed.hostname
    if not host:
        raise TargumError(
            f"We couldn't find a site name in {url}.",
            "Check the address and try again.",
            key="fetch.no-site-name",
            url=url,
        )
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        found = socket.getaddrinfo(host, port)
    except socket.gaierror as exc:
        raise TargumError(
            f"We couldn't find {host}.", str(exc), key="fetch.no-such-site", host=host
        ) from exc
    for info in found:
        address = ipaddress.ip_address(info[4][0])
        # is_global is false for loopback, private, link-local, reserved and
        # multicast in one check, on both IPv4 and IPv6.
        if not address.is_global:
            raise TargumError(
                f"{host} is on a private network, so we won't fetch it.",
                "Paste a public web address, or save the page and drop in the file.",
                key="fetch.private-network",
                host=host,
            )


def get(url: str, params: dict[str, str] | None = None) -> str:
    """One place for every outbound request, so the checks cannot be gone around."""
    return fetch(url, params).text


@dataclass(frozen=True)
class Fetched:
    """What came back, and what it says it is."""

    text: str
    content_type: str
    #: The undecoded body. An XML document declares its own encoding in its prolog, and
    #: a Hebrew feed served as windows-1255 without saying so in a header would come out
    #: of `text` as mojibake — decoded here as UTF-8 because that is all the header said.
    #: A parser given the bytes honours the declaration instead.
    raw: bytes = b""
    #: How it was got: `direct`, or `proxy` after a direct knock was refused. Recorded
    #: beside the host (`accounts.Store.reach`) so the memory of a shut door says which.
    #: `feed` for an article read from its publisher's feed (`page`, 2026-10-07), which
    #: is no knock on the host at all and so is never recorded as one.
    via: str = "direct"
    #: The title and language the feed gave, set only where `via` is `feed`: a page
    #: has its own `<title>`, and the feed knows the language its publisher writes in.
    title: str = ""
    language: str = ""

    @property
    def is_html(self) -> bool:
        # Absent or unrecognised is treated as HTML, which is what the web mostly is and
        # what the extractor copes with best.
        kind = self.content_type.split(";")[0].strip().lower()
        return not kind or "html" in kind or "xml" in kind


#: Statuses that mean the host refused this caller, not that a page is missing. A 404
#: is the opposite news: the server answered, so the door is open and the address was
#: wrong. 5xx is counted as shut because the effect is the same — nothing opens — and a
#: site that is down today is not worth offering a reader today.
REFUSED = frozenset({401, 403, 407, 429, 451})


#: The `server` a bot check answers from where it does not say `cf-mitigated`. Russian
#: publishers sit behind their own vendors rather than Cloudflare, and they answer a
#: client that runs no script with a status and an empty page that loads one. Measured
#: 2026-10-06: www.rbc.ru answers every article with `401`, `server: QRATOR` and a
#: 290-byte page that loads `/__qrator/…js` — not a sign-in wall, so it must not be
#: called one, and the reader's account would not open it.
CHALLENGE_SERVERS = ("qrator", "ddos-guard")


def _challenged(response: Any) -> bool:
    """Whether a refusal is a bot check: Cloudflare's header, or a vendor that says so in
    `server`."""
    headers = response.headers
    if (headers.get("cf-mitigated") or "").lower() == "challenge":
        return True
    server = (headers.get("server") or "").lower()
    return any(server.startswith(name) for name in CHALLENGE_SERVERS)


def shut(error: Unreachable) -> bool:
    """Whether a failed fetch says the host will refuse the next knock too."""
    if error.status is None:
        # Never got an answer at all: a timeout, a refused connection, a name that does
        # not resolve. Measured on 2026-09-07, this and 403 are what an Israeli site
        # does to an address outside Israel.
        return True
    return error.status in REFUSED or error.status >= 500


def egress() -> str:
    """Where a refused fetch is retried from, or "" for nowhere."""
    from ..video.youtube import proxy as youtube_proxy

    return os.environ.get(FETCH_PROXY_ENV, "").strip() or youtube_proxy()


_last_knock: dict[str, float] = {}
_knock_lock = threading.Lock()


def _polite(host: str) -> None:
    """Wait out `POLITE_S` since the last knock on `host`, if it was that recent."""
    with _knock_lock:
        wait = POLITE_S - (time.monotonic() - _last_knock.get(host, -POLITE_S))
        _last_knock[host] = time.monotonic() + max(0.0, wait)
    if wait > 0:
        time.sleep(wait)


def _session(proxy: str = "") -> Any:
    """One browser-shaped client. A function so a test can hand back a fake."""
    from curl_cffi import requests

    # Annotated because `curl_cffi` ships no stubs, so mypy cannot infer what a Session
    # is and asks rather than guessing.
    session: Any = requests.Session()
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    return session


def _open(url: str, params: dict[str, str] | None, *, via: str, proxy: str = "") -> tuple[Any, str]:
    """Walk to the page, checking every hop, and return the streaming response.

    Redirects are followed by hand rather than by the client, because every hop has to
    pass `_reachable`: a public URL that redirects to a private address is the ordinary
    shape of an SSRF, and it defeats checking only the first. Behind a proxy that check
    is advisory — the proxy resolves the name — and what stands in for it is that only
    https is ever retried that way: TLS is end-to-end through CONNECT, so the proxy
    cannot substitute an origin without failing certificate validation.
    """
    target = url
    session = _session(proxy)
    for _ in range(MAX_REDIRECTS + 1):
        _reachable(target)
        host = urlparse(target).hostname or ""
        _polite(host)
        try:
            response = session.get(
                target,
                params=params,
                timeout=TIMEOUT,
                allow_redirects=False,
                impersonate=BROWSER,
                stream=True,
            )
        except Exception as exc:
            # Never got an answer at all: a timeout, a refused connection, a name that
            # does not resolve. No status, so `shut()` reads it as a shut door.
            raise Unreachable(
                f"We couldn't open {url}.",
                str(exc),
                host=host,
                via=via,
                key="fetch.would-not-open",
                url=url,
            ) from exc
        status = int(response.status_code)
        if 300 <= status < 400:
            location = response.headers.get("location")
            response.close()
            if not location:
                raise TargumError(f"We couldn't open {url}.", "Redirect with nowhere to go")
            # Relative locations are legal, and the query belongs to the address it
            # was written for, not to wherever it points.
            target, params = urljoin(target, location), None
            continue
        if status >= 400:
            challenge = _challenged(response)
            response.close()
            if status == 401 and not challenge:
                # A sign-in wall, named rather than counted (targum-internal#252). Only
                # 401, which means exactly this. 403 is left where it was: it is what a
                # geo-block, a bot check and a permissions rule all answer with, and an
                # Israeli site returns it to any address outside Israel (2026-09-07), so
                # telling that reader to sign in would send them after a door that is not
                # there. Here the hint is a sentence and does travel: the way in is to
                # paste the text, which is the whole point of naming the refusal.
                raise Unreachable(
                    f"{host} asks you to sign in, so we can't open it.",
                    "Open it yourself and paste the text into the box instead.",
                    status=status,
                    host=host,
                    challenge=challenge,
                    via=via,
                    key="fetch.needs-a-sign-in",
                    # `site`, not `host`: `Unreachable` takes `host` as a field of its
                    # own, so it never reaches `fill` and a translation naming `{host}`
                    # would quietly fall back to English — the failure is silent, which
                    # is why a test pins the Russian interpolating rather than the key
                    # merely existing. The same reason `fetch.would-not-open` passes
                    # `url=` beside the `host=` it also takes.
                    site=host,
                )
            raise Unreachable(
                f"We couldn't open {url}.",
                "a bot check, not a page" if challenge else f"HTTP {status}",
                status=status,
                host=host,
                challenge=challenge,
                via=via,
                # The hint is the status or the bot check, which is not a sentence to
                # translate — so the key says the sentence and the hint rides as it is.
                key="fetch.would-not-open",
                url=url,
            )
        return response, target
    raise Unreachable(
        f"We couldn't open {url}.",
        f"More than {MAX_REDIRECTS} redirects",
        host=urlparse(target).hostname or "",
        via=via,
        key="fetch.would-not-open",
        url=url,
    )


def _retry_through_proxy(url: str, error: Unreachable) -> str:
    """The proxy to try next, or "" — only for a shut door, only over https."""
    where = egress()
    if not where or error.via != "direct" or not shut(error):
        return ""
    if urlparse(url).scheme != "https":
        # Plain http through a proxy has no origin authentication at all: a hostile
        # or compromised exit could serve anything for any address, and targum would
        # build it onto a reader's shelf.
        return ""
    return where


def fetch(url: str, params: dict[str, str] | None = None) -> Fetched:
    """A page, direct; then once through the proxy if the direct knock was refused.

    A fallback and not a route, which makes it selective by construction: a host only
    ever leaves through the proxy after a direct attempt refused it, so Gutenberg,
    Wikisource and every feed poll stay off a metered exit that none of them need.

    The proxied knock is the same walk as the direct one (`_open`, `_read`): every hop
    passes `_reachable` and the body stops at `MAX_BYTES`. What it costs is the page's
    bytes on the wire, compressed: 43 KB for the median of sixteen Russian articles
    measured 2026-10-06, 74 KB the largest, which at the residential exit's $1 a gigabyte
    is a twentieth of a thousandth of a dollar a page.

    Said in the log when it worked, by host alone — no path, no reader — so the box's
    journal shows which hosts only open this way (2026-10-06).
    """
    try:
        return _read(url, params, via="direct")
    except Unreachable as error:
        proxy = _retry_through_proxy(url, error)
        if not proxy:
            raise
        got = _read(url, params, via="proxy", proxy=proxy)
        log.info("fetched %s through the proxy", urlparse(url).hostname or "")
        return got


#: How long a page read through `page` is taken as what is there, in seconds.
PAGE_KEEP_S = 600.0
#: The most pages held at once, and the most bytes. A page is at most `MAX_BYTES` raw and
#: about as much again decoded, so the byte bound is what holds; a news article is a few
#: hundred kilobytes, and sixty-four megabytes is a busy hour's worth of them.
PAGE_MOST = 64
PAGE_MOST_BYTES = 64 * 1024 * 1024


class Pages:
    """Pages read through the door in the last ten minutes, by address (2026-10-06).

    An article a host asks about was fetched four times before it was priced: by
    `episode.find` in `describe_source`, to rule out a podcast page, then by
    `describe_source` itself to count its words; and the same two again inside the
    quote, by `episode.find` and the ingester. Each knock after the first on one host
    also waited out `POLITE_S`. On the box on 2026-10-06 that was 1.6 s a describe and
    most of a 4.1 s quote, for one page read four times within the minute.

    **Only what came through the door.** A page is kept after `fetch` returned it, so it
    passed the SSRF check at every hop and the size cap; a refusal is never kept, so a
    shut host is knocked on again and `Store.reach` hears about it each time. The one
    other thing kept is an article read from its feed in place of a page behind a bot
    check (`page`, 2026-10-07), which came through the door as the feed did.

    **Ten minutes**, because what is kept is what the reader is about to be quoted for
    and then build: the quote prices the text it read, and a build pressed a few minutes
    later reads the same text rather than a page edited in between, which is the text
    they agreed to. A page asked about again after that is read fresh. Not a cache of
    the web: feeds, robots and every other fetch go straight to `fetch`, and only the
    three readers of one article page above come through here.

    In-process, bounded by count and by bytes, the least recently asked dropped first.
    """

    def __init__(
        self,
        *,
        keep_s: float = PAGE_KEEP_S,
        most: int = PAGE_MOST,
        most_bytes: int = PAGE_MOST_BYTES,
        clock: Any = time.monotonic,
    ) -> None:
        self.keep_s = keep_s
        self.most = most
        self.most_bytes = most_bytes
        self.clock = clock
        self._lock = threading.Lock()
        #: key -> (clock time it lapses, the page, its size)
        self._held: OrderedDict[str, tuple[float, Fetched, int]] = OrderedDict()
        self._bytes = 0

    @staticmethod
    def key(url: str) -> str:
        """The address as the server sees it: scheme and host in lower case, no fragment."""
        parsed = urlparse(url.strip())
        return parsed._replace(
            scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower(), fragment=""
        ).geturl()

    def clear(self) -> None:
        with self._lock:
            self._held.clear()
            self._bytes = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._held)

    def _drop(self, key: str) -> None:
        held = self._held.pop(key, None)
        if held is not None:
            self._bytes -= held[2]

    def held(self, url: str) -> Fetched | None:
        """The page read through here within `keep_s`, or None."""
        key = self.key(url)
        with self._lock:
            held = self._held.get(key)
            if held is not None and self.clock() < held[0]:
                self._held.move_to_end(key)
                return held[1]
            self._drop(key)
        return None

    def get(self, url: str) -> Fetched:
        """`fetch(url)`, or the same page read through here within `keep_s`."""
        held = self.held(url)
        if held is not None:
            return held
        got = fetch(url)
        self.keep(url, got)
        return got

    def keep(self, url: str, got: Fetched) -> None:
        """Hold `got` as what is at `url` for `keep_s`: a page `fetch` returned, or an
        article read from its feed (`page`)."""
        key = self.key(url)
        size = len(got.raw or b"") + len(got.text.encode("utf-8", errors="replace"))
        if size > self.most_bytes:
            return
        with self._lock:
            self._drop(key)
            self._held[key] = (self.clock() + self.keep_s, got, size)
            self._bytes += size
            while self._held and (len(self._held) > self.most or self._bytes > self.most_bytes):
                self._drop(next(iter(self._held)))


PAGES = Pages()

#: How long a host that refused a page is taken as refusing the next, in seconds, for
#: `page`'s choice to read an article from its feed without knocking (2026-10-07). An
#: hour: a bot check is the site's policy and does not lift by the minute, and a host
#: that has lifted it is knocked on again after this.
SHUT_KEEP_S = 3600.0


class Shut:
    """Hosts that refused this process lately, for `page` and nothing else (2026-10-07).

    Not `accounts.Store.reached`, which this door cannot see: what a caller that holds a
    store knows is handed in (`note`), and a refusal `page` meets itself is noted here.
    Nothing is refused because of it — a link with no feed text behind it is knocked on
    whatever this says.
    """

    def __init__(self, keep_s: float = SHUT_KEEP_S, clock: Any = time.monotonic) -> None:
        self.keep_s = keep_s
        self.clock = clock
        self._lock = threading.Lock()
        self._until: dict[str, float] = {}

    def note(self, host: str) -> None:
        with self._lock:
            self._until[host.lower()] = self.clock() + self.keep_s

    def knows(self, host: str) -> bool:
        with self._lock:
            until = self._until.get(host.lower())
            if until is not None and self.clock() >= until:
                del self._until[host.lower()]
                return False
            return until is not None

    def clear(self) -> None:
        with self._lock:
            self._until.clear()


SHUT = Shut()


def remember_shut(url: str, closed: Callable[..., list[str]]) -> None:
    """Hand `SHUT` what a store remembers of `url`'s host, where `url` is an article a
    followed feed carries whole (2026-10-07).

    `closed` is `accounts.Store.closed`, asked only for such a link, so describing or
    quoting any other link costs no query. Without this, the first article of a shut host
    after a restart is knocked on once before the feed is read; with it, not at all.
    """
    from ..weekly import feeds

    if feeds.HELD.find(url) is None:
        return
    host = (urlparse(url).hostname or "").lower()
    if host and host in closed(limit=500):
        SHUT.note(host)


def from_feed(url: str) -> Fetched | None:
    """The article at `url` as its publisher's feed carries it, or None (2026-10-07).

    None unless `url` is an item of a feed this box follows and that feed carries the
    item's whole text (`weekly.feeds.HELD`, targum-internal#424). Handed back as a page
    the article's readers already read — a `<title>` and a `<p>` a paragraph — so
    `describe_source` counts it and the ingester builds it the way it would a fetched
    article, and marked `via="feed"` so neither records it as a knock on the host.
    """
    import html

    from ..weekly import feeds

    held = feeds.HELD.find(url)
    if held is None:
        return None
    item, language = held
    body = "".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in item.full_text.split("\n\n"))
    lang = f' lang="{html.escape(language)}"' if language else ""
    text = (
        f'<!doctype html><html{lang}><head><meta charset="utf-8">'
        f"<title>{html.escape(item.title)}</title></head><body>{body}</body></html>"
    )
    return Fetched(
        text=text,
        content_type="text/html; charset=utf-8",
        via="feed",
        title=item.title,
        language=language,
    )


def page(url: str) -> Fetched:
    """One page, read through the door and kept ten minutes (`Pages`). For an article's
    readers — `describe_source`, `episode.find` and the ingester — and nobody else.

    **Or read from its feed, where the page is behind a bot check** (2026-10-07,
    targum-internal#424). www.rbc.ru answers every article with `401`,
    `server: QRATOR` and a page that loads a script, which neither the direct door nor
    the proxy runs, and its feed carries each article whole. Where `url` is a followed
    feed's item with its full text (`from_feed`), a host known to refuse (`SHUT`) is not
    knocked on at all, and a page that refuses when knocked is replaced by the feed's
    text. Kept like any page, so the quote and the build after it read the same text.
    Every other link is fetched exactly as it was, and a refusal of one is still raised.
    """
    held = PAGES.held(url)
    if held is not None:
        return held
    standin = from_feed(url)
    if standin is None:
        return PAGES.get(url)
    host = (urlparse(url).hostname or "").lower()
    if not SHUT.knows(host):
        try:
            return PAGES.get(url)
        except Unreachable as error:
            if not shut(error):
                raise
            SHUT.note(host)
    PAGES.keep(url, standin)
    return standin


def _read(url: str, params: dict[str, str] | None, *, via: str, proxy: str = "") -> Fetched:
    response, _ = _open(url, params, via=via, proxy=proxy)
    try:
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_BYTES:
            raise TargumError(
                f"{url} is too big for us to read.",
                "Try a single article.",
                key="fetch.too-big-to-read",
                url=url,
            )
        body = bytearray()
        for chunk in response.iter_content():
            body += chunk
            if len(body) > MAX_BYTES:
                raise TargumError(
                    f"{url} is too big for us to read.",
                    "We stop at 8 MB. Try a single article.",
                    key="fetch.over-the-page-cap",
                    url=url,
                )
        encoding = response.charset or response.encoding or "utf-8"
        return Fetched(
            body.decode(encoding, errors="replace"),
            response.headers.get("content-type", ""),
            bytes(body),
            via=via,
        )
    finally:
        response.close()


@dataclass(frozen=True)
class Opening:
    """The first bytes of a file, and what the wire said about the whole of it."""

    head: bytes
    content_type: str
    #: What `content-length` declared, or 0 where the host would not say.
    length: int


#: How much of a media file's front is read to find out what it is. A container puts its
#: header first — enough for ffprobe to name the codec and the bit rate — and a megabyte
#: is generous for that while being nothing beside the file itself.
OPENING_BYTES = 1024 * 1024


def opening(url: str, most: int = OPENING_BYTES) -> Opening:
    """The front of a file, through the same door and past the same checks as any fetch.

    For saying what a link *is* without pulling what it holds (targum-internal#256): a
    reader pastes a direct link to an hour of audio and the page should be able to say
    so without a gigabyte moving. The connection is closed as soon as enough has been
    read, so a server that would have streamed the rest never does.
    """
    try:
        return _opened(url, most, via="direct")
    except Unreachable as error:
        proxy = _retry_through_proxy(url, error)
        if not proxy:
            raise
        return _opened(url, most, via="proxy", proxy=proxy)


def _opened(url: str, most: int, *, via: str, proxy: str = "") -> Opening:
    response, _ = _open(url, None, via=via, proxy=proxy)
    try:
        declared = response.headers.get("content-length")
        body = bytearray()
        for chunk in response.iter_content():
            body += chunk
            if len(body) >= most:
                break
        return Opening(
            bytes(body[:most]),
            response.headers.get("content-type", ""),
            int(declared) if declared and declared.isdigit() else 0,
        )
    finally:
        response.close()


@dataclass(frozen=True)
class Downloaded:
    """A file pulled to disk, and what the wire said about it."""

    path: Path
    content_type: str
    final_url: str
    via: str = "direct"


#: A podcast episode or an audiobook chapter, not an article. Streamed to disk rather
#: than held in memory, with its own ceiling.
MAX_AUDIO_BYTES = 1024 * 1024 * 1024


def download(url: str, into: Path, max_bytes: int = MAX_AUDIO_BYTES) -> Downloaded:
    """A large file, through the same door and past the same checks as every fetch.

    Retried through the proxy on the same terms as a page. Decided 2026-09-08, having
    first been left out for the size of the bill: a recording is metered against the
    reader's hours before it is fetched (`serve._prepare_*` sets `job.audio` and
    `job.seconds`), so the allowance already bounds what a proxied episode can cost.
    """
    into.parent.mkdir(parents=True, exist_ok=True)
    try:
        return _pull(url, into, max_bytes, via="direct")
    except Unreachable as error:
        proxy = _retry_through_proxy(url, error)
        if not proxy:
            raise
        return _pull(url, into, max_bytes, via="proxy", proxy=proxy)


def _pull(url: str, into: Path, max_bytes: int, *, via: str, proxy: str = "") -> Downloaded:
    try:
        response, target = _open(url, None, via=via, proxy=proxy)
    except TargumError:
        into.unlink(missing_ok=True)
        raise
    try:
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise TargumError(
                f"{url} is too big for us to fetch.", key="fetch.too-big-to-fetch", url=url
            )
        written = 0
        with into.open("wb") as out:
            for chunk in response.iter_content():
                written += len(chunk)
                if written > max_bytes:
                    raise TargumError(
                        f"{url} is too big for us to fetch.",
                        f"We stop at {max_bytes // (1024 * 1024)} MB.",
                    )
                out.write(chunk)
        return Downloaded(into, response.headers.get("content-type", ""), target, via=via)
    except TargumError:
        into.unlink(missing_ok=True)
        raise
    finally:
        response.close()


#: What a Global Voices translator writes after a link to say the page it opens is in
#: another language: `[en]`, or `[en, come tutti i link successivi, salvo diversa
#: indicazione]` for the first of several. A note about the links, which the extractor
#: drops, left in the prose it sat in. Narrow on purpose: a two-letter code, or one of
#: the three-letter codes the edition uses, and a longer note only where it says
#: "link", so `[sic]`, `[ndr]` and `[…]` stay.
#:
#: The Russian edition writes the same notes as Cyrillic abbreviations: `[анг]`, `[рус]`,
#: `[мао/анг]` where a page has two, `[анг, pdf, 51 КБ]` for a document. Those come from a
#: list rather than any short Cyrillic word, because `[не был]` and `[в 2017 году]` are an
#: editor's words inside a quotation and have to stay.
_CYRILLIC_CODES = (
    "англ?|рус|укр|бел|белор|каз|казах|кыр|кырг|кирг|узб|узбек|тадж|таджик|тат|туркм|азерб|"
    "арм|груз|мао|гит|фр|франц|исп|испан|нем|немец|ит|итал|кит|китай|яп|япон|кор|корей|"
    "араб|перс|фарси|тур|пол|чеш|болг|серб|порт|хин|монг"
)
_LINK_LANGUAGE = re.compile(
    r"\s?\[(?:"
    r"(?:[a-z]{2}|uzb|kaz|kir|tgk|tuk|tat|fil|yue)(?:-[A-Z]{2})?"
    r"(?:, [^\[\]]{0,60}\b(?:link|liens?|enlaces?)\b[^\[\]]{0,60})?"
    rf"|(?:{_CYRILLIC_CODES})(?:/(?:{_CYRILLIC_CODES}))*"
    r"(?:, (?:pdf|docx?|xlsx?|pptx?)(?:, [\d.,]+ ?(?:КБ|МБ|Кб|Мб))?)?"
    r")\]"
)


def _translated_edition(source: str) -> bool:
    """A Global Voices edition in a language other than English.

    Not the English site: its links go to English pages, and there a bracketed `[it]` is
    far more often a word an editor put into a quotation.
    """
    host = (urlparse(source).hostname or "").lower()
    edition = host.removesuffix(".globalvoices.org")
    return edition != host and len(edition) in (2, 3) and edition.isalpha() and edition != "en"


def drop_link_languages(text: str) -> str:
    return _LINK_LANGUAGE.sub("", text).strip()


class UrlIngester:
    # 5: a line break reads as a space (`htmltext`), which moved one catalogue text of 54
    # measured — a he.wikinews reference line, "2022מסכי" — and a Global Voices edition
    # loses its translators' link-language notes, so the pages already on a shelf are read
    # again rather than kept as though somebody had edited them.
    name = "url/5"

    # An article read from its publisher's feed because its page is behind a bot check
    # (`page`, 2026-10-07): the same article, but not what a page's extractor found, and
    # what a text arrived as is recorded the way `plain_name` records a text file.
    feed_name = "url-feed/1"

    # A .txt served over http is a text file that happens to live on the web, and the
    # artifact says so: what a text arrived as decides what may later be inferred about
    # it. A page's markup states its structure; a plain file has none to state.
    plain_name = "url-text/1"

    def _plain(self, source: str, body: str) -> Document:
        """A text file fetched over http, read the way a text file on disk is read."""
        from .base import classify_plain_paragraph, parse_frontmatter

        fields, text = parse_frontmatter(normalize(body))
        paragraphs: list[Paragraph] = [
            classify_plain_paragraph(chunk) for chunk in text.split("\n\n") if chunk.strip()
        ]
        if not paragraphs:
            raise TargumError(
                f"We couldn't find any text at {source}.",
                "The address answered with an empty file.",
            )
        return build_document(
            source,
            blocks_from_paragraphs(paragraphs),
            ingester=self.plain_name,
            language=fields.get("language") or fields.get("lang"),
            title=fields.get("title"),
            author=fields.get("author"),
            structure=True,
        )

    def _from_feed(self, source: str, got: Fetched) -> Document:
        """An article its feed carried whole (`from_feed`): its paragraphs are already
        the article, so no extractor decides what on a page is the article."""
        paragraphs: list[Paragraph] = [
            (kind, level, normalize(text)) for kind, level, text in paragraphs_from_html(got.text)
        ]
        if not paragraphs:
            raise TargumError(
                f"We couldn't find any text at {source}.",
                "Save the page as .txt or .md and drop the file in.",
            )
        return build_document(
            source,
            blocks_from_paragraphs(with_front_matter(paragraphs, got.title or None, None)),
            ingester=self.feed_name,
            language=got.language or None,
            title=got.title or source,
        )

    def load(self, source: str) -> Document:
        import trafilatura

        # Through `page`, so the quote that follows a `describe_source` reads the page
        # that was described rather than fetching it again (2026-10-06).
        got = page(source)
        if got.via == "feed":
            return self._from_feed(source, got)
        if not got.is_html:
            # A URL that answers with plain text is a text file that happens to live on
            # the web, and running an article extractor over it finds no article and
            # reports that the page has no readable text — which is exactly wrong. Ben
            # Yehuda serves its whole library this way, at /download/<id>.txt.
            return self._plain(source, got.text)
        html = got.text
        # trafilatura decides what on the page is the article. Asking it for HTML
        # rather than text keeps the headings and paragraph boundaries.
        extracted: Any = trafilatura.extract(
            html,
            output_format="html",
            include_comments=False,
            include_tables=False,
            include_formatting=False,
            favor_recall=True,
        )
        paragraphs: list[Paragraph] = (
            paragraphs_from_html(extracted) if extracted else paragraphs_from_html(html)
        )
        if not paragraphs:
            raise TargumError(
                f"We couldn't find any text at {source}.",
                "Save the page as .txt or .md and drop the file in.",
            )
        paragraphs = [(kind, level, normalize(text)) for kind, level, text in paragraphs]
        if _translated_edition(source):
            paragraphs = [
                (kind, level, kept)
                for kind, level, text in paragraphs
                if (kept := drop_link_languages(text))
            ]

        metadata = trafilatura.extract_metadata(html)
        title = getattr(metadata, "title", None)
        author = getattr(metadata, "author", None)

        return build_document(
            source,
            blocks_from_paragraphs(with_front_matter(paragraphs, title, author)),
            ingester=self.name,
            title=title or source,
            author=author,
        )
