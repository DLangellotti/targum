"""RSS and Atom, read for the five fields a digest needs.

No feedparser, and the reason is not weight. `ingest/url.py` says it out loud — "one
place for every outbound request, so the checks cannot be gone around" — and feedparser
brings its own fetching, which on a box with a metadata endpoint is a second outbound
door with none of the redirect and address checks on it. Everything here goes through
`ingest.url.fetch`.

Public rather than private, unlike the rest of the generation half. Parsing somebody
else's XML is not content and not a moat; it is where the encoding bugs live, and kept
private it would sit where CI can never run it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

#: RSS 2.0 puts its items in no namespace; Atom namespaces everything. Rather than carry
#: a namespace map and guess which document this is, tags are matched on their local
#: name — the last segment after a `}`.
_LOCAL = re.compile(r"\{[^}]*\}")

#: A summary is a hook, not an article. Tier-2 sources give facts and nothing else, and
#: the shortest way to keep that true is to refuse to hold more than a hook of them.
#:
#: 400 rather than 200, because 200 was starving the writing: a story arrived with one
#: or two facts and every level came out at twenty words, so the three differed in
#: register and not in depth. Still a hook and not an article, and the output is checked
#: against every one of these for lifted wording regardless of how long they are.
MAX_SUMMARY = 400


@dataclass(frozen=True)
class Item:
    title: str
    link: str
    summary: str = ""
    published: datetime | None = None
    guid: str = ""


def _name(tag: str) -> str:
    return _LOCAL.sub("", tag).lower()


def _text(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return " ".join((element.text or "").split())


def _when(raw: str) -> datetime | None:
    """RSS dates are RFC 822 and Atom's are ISO 8601. Both turn up misspelt."""
    raw = raw.strip()
    if not raw:
        return None
    for parse in (parsedate_to_datetime, datetime.fromisoformat):
        try:
            when = parse(raw)
        except (TypeError, ValueError):
            continue
        return when if when.tzinfo else when.replace(tzinfo=UTC)
    return None


def _link(entry: ElementTree.Element) -> str:
    """RSS writes the address as text; Atom writes it as an `href` attribute, and may
    write several with only one of them the article."""
    best = ""
    for child in entry:
        if _name(child.tag) != "link":
            continue
        href = child.get("href", "")
        relation = child.get("rel", "alternate")
        if href and relation == "alternate":
            return href
        best = best or href or _text(child)
    return best


def parse(xml: bytes) -> list[Item]:
    """Every entry in a feed, in the order the feed put them.

    Takes bytes rather than a string so the XML declaration decides the encoding. Handed
    a decoded string, a Hebrew feed served as windows-1255 would already be mojibake by
    the time it arrived.
    """
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return []

    items: list[Item] = []
    for element in root.iter():
        if _name(element.tag) not in {"item", "entry"}:
            continue
        fields: dict[str, ElementTree.Element] = {}
        for child in element:
            fields.setdefault(_name(child.tag), child)
        title = _text(fields.get("title"))
        if not title:
            continue
        summary = _text(fields.get("description")) or _text(fields.get("summary"))
        stamp = (
            _text(fields.get("pubdate"))
            or _text(fields.get("published"))
            or _text(fields.get("updated"))
        )
        items.append(
            Item(
                title=title,
                link=_link(element),
                summary=summary[:MAX_SUMMARY],
                published=_when(stamp),
                guid=_text(fields.get("guid")) or _text(fields.get("id")),
            )
        )
    return items


def pull(url: str, *, limit: int = 30) -> list[Item]:
    """One feed, through the only outbound door there is."""
    from ..ingest.url import fetch

    got = fetch(url)
    return parse(got.raw or got.text.encode("utf-8"))[:limit]
