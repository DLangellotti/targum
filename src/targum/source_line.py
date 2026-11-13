"""Where a suggested text comes from, said plainly (David, 2026-11-02; design.md §12).

Home's pick card and the "More that fit you" rows carry one line under each title: the
outlet, and for news and other dated items the day ("Kan 11 · 2 Nov"). The outlet's name
is the link, and it opens the original in a new tab, so a reader can always go and see
the thing itself. The name is always one a row already carries — a find's publisher, a
channel, a site, a catalogue credit — and never one a model wrote.

A dict rather than a sentence: the page says the day in its own language, and the server
knows only the instant.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlparse

from . import catalogue as catalogue_module

#: The one shape of a YouTube video's home, as the reader links it (`video.youtube.WATCH`,
#: written out so this module imports nothing heavy).
WATCH = "https://www.youtube.com/watch?v="


def _site(address: str) -> str:
    host = urlparse(address).hostname or ""
    return host.removeprefix("www.")


def _web(address: str) -> str:
    """An address a reader may be sent to: http(s) only, and never a licence's terms page,
    which is where a credit's terms are read, not where its text lives."""
    address = (address or "").strip()
    if not address.startswith(("https://", "http://")):
        return ""
    if _site(address) in ("creativecommons.org",):
        return ""
    return address


def for_find(row: dict[str, Any]) -> dict[str, Any] | None:
    """A web find's line: its publisher (or site) and its day, linking to the find.

    A podcast episode's line names its show, who makes it where that is another name
    (`by`), and links the episode's own page where the feed gave one rather than its
    audio file, which opens as a bare player (targum-internal#691)."""
    url = _web(str(row.get("page") or "")) or _web(str(row.get("url") or ""))
    name = str(row.get("publisher") or "").strip() or _site(url) or _site_of_host(row)
    if not name:
        return None
    line: dict[str, Any] = {"name": name, "url": url, "date": int(row.get("published") or 0)}
    by = str(row.get("author") or "").strip()
    if by and by.casefold() != name.casefold():
        line["by"] = by
    return line


def _site_of_host(row: dict[str, Any]) -> str:
    return str(row.get("host") or "").removeprefix("www.")


def page_of(entry: catalogue_module.Entry) -> str:
    """Where a shelf text lives on the web, or "" where nowhere can be named."""
    source = entry.source or ""
    scheme, _, rest = source.partition(":")
    if scheme in ("https", "http"):
        # A Project Ben-Yehuda row is built off its plain-text download; its page to read
        # is the same number under /read.
        if _site(source) == "benyehuda.org" and "/download/" in source:
            number = source.rsplit("/", 1)[-1].removesuffix(".txt")
            if number.isdigit():
                return f"https://benyehuda.org/read/{number}"
        return _web(source)
    if scheme == "video" and rest:
        return WATCH + quote(rest, safe="")
    if scheme == "sefaria" and rest:
        book = rest.removeprefix("arc:")
        return "https://www.sefaria.org/" + quote(book.replace(" ", "_"), safe="_,")
    # The rest (Wikisource, StoryWeaver, the siddur) name their page where the licence
    # was read, which is the page itself unless it is a licence's terms.
    return _web(entry.licence_url)


def outlet_of(credit: str) -> str:
    """The outlet a catalogue credit names. A credit that ends "via Sefaria", or one that
    is a whole attribution sentence ending "Via StoryWeaver, Pratham Books.", names its
    outlet last; the line says that one. Any other credit is the outlet itself."""
    credit = (credit or "").strip()
    lowered = credit.lower()
    at = max(lowered.rfind(", via "), lowered.rfind(". via "))
    if at < 0 and lowered.startswith("via "):
        at = -2
    if at == -1:
        return credit
    tail = credit[at + 6 :] if at >= 0 else credit[4:]
    return tail.split(",")[0].strip().rstrip(".").strip() or credit


def for_entry(entry: catalogue_module.Entry) -> dict[str, Any] | None:
    """A shelf text's line: the outlet its catalogue credit names, undated, linking to its
    page where it has one. None for what targum wrote itself, which has no outlet."""
    name = outlet_of(entry.credit)
    if not name:
        return None
    return {"name": name, "url": page_of(entry), "date": 0}


def attach(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """`row` with its `source` line, where one can be said. Rows already carrying one, and
    rows naming nothing it can place, pass through."""
    if not row or row.get("source_line"):
        return row
    line: dict[str, Any] | None
    if row.get("find"):
        line = for_find(row)
    else:
        entry = catalogue_module.by_id(str(row.get("id") or ""))
        line = for_entry(entry) if entry is not None else None
    if line is None:
        return row
    return {**row, "source_line": line}
