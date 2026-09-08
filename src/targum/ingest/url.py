"""A web page, reduced to the text a reader came for."""

from __future__ import annotations

import ipaddress
import os
import socket
import threading
import time
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
            f"targum only reads web pages, and {url} is not one.",
            "Give an http:// or https:// address, or a file.",
        )
    host = parsed.hostname
    if not host:
        raise TargumError(f"There is no site name in {url}.", "Check the address.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        found = socket.getaddrinfo(host, port)
    except socket.gaierror as exc:
        raise TargumError(f"Could not find {host}.", str(exc)) from exc
    for info in found:
        address = ipaddress.ip_address(info[4][0])
        # is_global is false for loopback, private, link-local, reserved and
        # multicast in one check, on both IPv4 and IPv6.
        if not address.is_global:
            raise TargumError(
                f"{host} is on a private network, so targum will not fetch it.",
                "Give a public web address, or save the page and open the file.",
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
    via: str = "direct"

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
            raise Unreachable(f"Could not fetch {url}", str(exc), host=host, via=via) from exc
        status = int(response.status_code)
        if 300 <= status < 400:
            location = response.headers.get("location")
            response.close()
            if not location:
                raise TargumError(f"Could not fetch {url}", "Redirect with nowhere to go")
            # Relative locations are legal, and the query belongs to the address it
            # was written for, not to wherever it points.
            target, params = urljoin(target, location), None
            continue
        if status >= 400:
            challenge = (response.headers.get("cf-mitigated") or "").lower() == "challenge"
            response.close()
            raise Unreachable(
                f"Could not fetch {url}",
                "a bot check, not a page" if challenge else f"HTTP {status}",
                status=status,
                host=host,
                challenge=challenge,
                via=via,
            )
        return response, target
    raise Unreachable(
        f"Could not fetch {url}",
        f"More than {MAX_REDIRECTS} redirects",
        host=urlparse(target).hostname or "",
        via=via,
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
    """
    try:
        return _read(url, params, via="direct")
    except Unreachable as error:
        proxy = _retry_through_proxy(url, error)
        if not proxy:
            raise
        return _read(url, params, via="proxy", proxy=proxy)


def _read(url: str, params: dict[str, str] | None, *, via: str, proxy: str = "") -> Fetched:
    response, _ = _open(url, params, via=via, proxy=proxy)
    try:
        declared = response.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_BYTES:
            raise TargumError(f"{url} is too big to read.", "Try a single article.")
        body = bytearray()
        for chunk in response.iter_content():
            body += chunk
            if len(body) > MAX_BYTES:
                raise TargumError(
                    f"{url} is too big to read.",
                    "targum stops at 8 MB. Try a single article.",
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
            raise TargumError(f"{url} is too big to fetch.")
        written = 0
        with into.open("wb") as out:
            for chunk in response.iter_content():
                written += len(chunk)
                if written > max_bytes:
                    raise TargumError(
                        f"{url} is too big to fetch.",
                        f"targum stops at {max_bytes // (1024 * 1024)} MB.",
                    )
                out.write(chunk)
        return Downloaded(into, response.headers.get("content-type", ""), target, via=via)
    except TargumError:
        into.unlink(missing_ok=True)
        raise
    finally:
        response.close()


class UrlIngester:
    name = "url/4"

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
                f"No readable text found at {source}",
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

    def load(self, source: str) -> Document:
        import trafilatura

        got = fetch(source)
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
                f"No readable text found at {source}",
                "Save the page as .txt or .md and point targum at the file.",
            )
        paragraphs = [(kind, level, normalize(text)) for kind, level, text in paragraphs]

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
