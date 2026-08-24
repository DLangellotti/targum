"""A web page, reduced to the text a reader came for."""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

from ..errors import TargumError
from ..models import Document
from .base import (
    Paragraph,
    blocks_from_paragraphs,
    build_document,
    normalize,
    with_front_matter,
)
from .htmltext import paragraphs_from_html

USER_AGENT = "targum/0.1 (+https://github.com/DLangellotti/targum)"
TIMEOUT = 30.0

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
    import httpx

    target = url
    with httpx.Client(
        timeout=TIMEOUT,
        follow_redirects=False,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            _reachable(target)
            try:
                with client.stream("GET", target, params=params) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise TargumError(
                                f"Could not fetch {url}", "Redirect with nowhere to go"
                            )
                        # Relative locations are legal, and the query belongs to the
                        # address it was written for, not to wherever it points.
                        target, params = urljoin(target, location), None
                        continue
                    response.raise_for_status()
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
                        raise TargumError(f"{url} is too big to read.", "Try a single article.")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body += chunk
                        if len(body) > MAX_BYTES:
                            raise TargumError(
                                f"{url} is too big to read.",
                                "targum stops at 8 MB. Try a single article.",
                            )
                    return body.decode(response.charset_encoding or "utf-8", errors="replace")
            except TargumError:
                raise
            except Exception as exc:
                raise TargumError(f"Could not fetch {url}", str(exc)) from exc
    raise TargumError(f"Could not fetch {url}", f"More than {MAX_REDIRECTS} redirects")


class UrlIngester:
    name = "url/2"

    def load(self, source: str) -> Document:
        import trafilatura

        html = get(source)
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
