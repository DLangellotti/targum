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

import html
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
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

#: The elements a feed carries an article's whole text in, by local name (2026-10-07).
#: `content:encoded` is RSS's common one, and nothing here read it before; РБК writes
#: `rbc_news:full-text`. Folded into one path, so the next publisher that spells it its
#: own way is one more name here.
FULL_TEXT = ("encoded", "full-text")

#: The most of a full text kept, in characters. A news article is a few thousand; a
#: WordPress feed's `content:encoded` can carry a long read, and the box holds fifteen
#: items of every followed feed in memory.
MAX_FULL_TEXT = 64_000


@dataclass(frozen=True)
class Item:
    title: str
    link: str
    summary: str = ""
    published: datetime | None = None
    guid: str = ""
    #: The audio a podcast feed attaches, where it attaches one. RSS writes an
    #: <enclosure url type>; Atom writes a link with rel="enclosure".
    enclosure: str = ""
    #: A transcript the feed points at (Podcasting 2.0's <podcast:transcript>), which
    #: makes an import free of transcription. The url and its stated type.
    transcript: str = ""
    transcript_type: str = ""
    #: Seconds, from itunes:duration, or 0 where the feed does not say.
    seconds: float = 0.0
    #: The article's whole text, where the feed carries it (`FULL_TEXT`), as plain
    #: paragraphs separated by a blank line (2026-10-07, targum-internal#424). Never the
    #: weekly's: it writes from `summary` and nothing else, and this is here for one
    #: reader importing one article whose page is behind a bot check (`HELD`).
    full_text: str = ""
    #: The sections the feed files the item under, as it spells them (2026-10-07):
    #: RSS's `<category>`, Atom's `<category term>`, Dublin Core's `<dc:subject>`. Raw,
    #: in the publisher's language; `chat.sources.topics_of` reads them as topics.
    categories: tuple[str, ...] = ()


def _name(tag: str) -> str:
    return _LOCAL.sub("", tag).lower()


def _text(element: ElementTree.Element | None) -> str:
    if element is None:
        return ""
    return " ".join((element.text or "").split())


#: A tag inside a title or a summary, where a feed put markup into CDATA.
_TAG = re.compile(r"<[^>]*>")


def _plain(raw: str) -> str:
    """Words, where a feed sent markup (2026-10-06).

    Meduza, Novaya Gazeta Europe and Teplitsa put paragraphs and links into a CDATA
    description (`<p>…</p>`, `<br/>`, `<a href=…>`), and OVD-Info writes `&nbsp;` there,
    which CDATA leaves as six characters. Kept as it came, a summary carried `href`,
    `https` and `nbsp` as words: in the hook the weekly writes from, and in the tokens
    `search_sources` measures a reader's known share over. A tag is a space, an entity
    is its character, and the spaces are folded.
    """
    if "<" not in raw and "&" not in raw:
        return raw
    return " ".join(html.unescape(_TAG.sub(" ", raw)).split())


#: Where one paragraph of a full text ends, in the markup a feed puts into it.
_BLOCK = re.compile(r"<\s*(?:br|/?p|/?div|/?h[1-6]|/?li|/?blockquote)\b[^>]*>", re.I)
#: What is never text: a script, a style sheet, a figure's caption furniture.
_NOT_TEXT = re.compile(r"<(script|style|figure)\b.*?</\1\s*>", re.I | re.S)


def _full(element: ElementTree.Element | None) -> str:
    """An article's whole text, as paragraphs a blank line apart (2026-10-07).

    Cleaned the way `_plain` cleans a summary — a tag is a space, an entity is its
    character — after the markup that ends a paragraph has said where it ends. Where
    there is no markup at all, a line is a paragraph, which is how a feed that sends
    plain text (РБК's `full-text`) separates them.
    """
    if element is None:
        return ""
    raw = "".join(element.itertext())
    raw = _NOT_TEXT.sub(" ", raw)
    if _BLOCK.search(raw):
        chunks = _BLOCK.split(raw)
    else:
        chunks = raw.splitlines()
    paragraphs = [_plain(" ".join(chunk.split())) for chunk in chunks]
    text = "\n\n".join(paragraph for paragraph in paragraphs if paragraph)
    return text[:MAX_FULL_TEXT]


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


def _enclosure(entry: ElementTree.Element) -> str:
    """The audio attached to one entry, in whichever spelling the feed uses."""
    for child in entry:
        name = _name(child.tag)
        kind = child.get("type", "")
        if name == "enclosure" and (not kind or kind.startswith("audio/")):
            return child.get("url", "") or _text(child)
        if name == "link" and child.get("rel") == "enclosure" and kind.startswith("audio/"):
            return child.get("href", "")
    return ""


def _transcript(entry: ElementTree.Element) -> tuple[str, str]:
    """A <podcast:transcript url type>, matched on the local name like everything here."""
    for child in entry:
        if _name(child.tag) == "transcript":
            return child.get("url", ""), child.get("type", "")
    return "", ""


def _seconds(raw: str) -> float:
    """itunes:duration arrives as seconds, M:SS or H:MM:SS, and misspelt."""
    raw = raw.strip()
    if not raw:
        return 0.0
    try:
        pieces = [float(piece) for piece in raw.split(":")]
    except ValueError:
        return 0.0
    total = 0.0
    for piece in pieces:
        total = total * 60 + piece
    return total


def _categories(entry: ElementTree.Element) -> tuple[str, ...]:
    """Every section one entry is filed under, in the feed's order, each once.

    Lenta, TASS, РБК, Novaya Gazeta Europe, Israel Hayom, Globes and Global Voices write
    them; Ynet, Walla, Mako, Haaretz, Meduza, the BBC and OVD-Info write none (measured
    2026-10-07), and their items are filed by the publisher row's `topic` where the feed
    is one section.
    """
    out: list[str] = []
    for child in entry:
        if _name(child.tag) not in {"category", "subject"}:
            continue
        said = _plain(_text(child) or " ".join(child.get("term", "").split()))
        if said and said not in out:
            out.append(said)
    return tuple(out)


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
        title = _plain(_text(fields.get("title")))
        if not title:
            continue
        summary = _plain(_text(fields.get("description")) or _text(fields.get("summary")))
        stamp = (
            _text(fields.get("pubdate"))
            or _text(fields.get("published"))
            or _text(fields.get("updated"))
        )
        spoken, spoken_type = _transcript(element)
        whole = next((_full(fields[name]) for name in FULL_TEXT if name in fields), "")
        items.append(
            Item(
                title=title,
                link=_link(element),
                summary=summary[:MAX_SUMMARY],
                published=_when(stamp),
                guid=_text(fields.get("guid")) or _text(fields.get("id")),
                enclosure=_enclosure(element),
                transcript=spoken,
                transcript_type=spoken_type,
                seconds=_seconds(_text(fields.get("duration"))),
                full_text=whole,
                categories=_categories(element),
            )
        )
    return items


def title(xml: bytes) -> str:
    """What a feed calls itself: RSS's `<channel><title>`, Atom's `<feed><title>`. "" for
    a feed that says nothing, or for anything that is not one. A podcast subscribed to is
    named by it (design.md §12, 2026-10-09)."""
    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError:
        return ""
    holder = root
    for element in root:
        if _name(element.tag) == "channel":
            holder = element
            break
    for element in holder:
        if _name(element.tag) == "title":
            return _plain(_text(element))
    return ""


def pull(url: str, *, limit: int = 30) -> list[Item]:
    """One feed, through the only outbound door there is."""
    from ..ingest.url import fetch

    got = fetch(url)
    return parse(got.raw or got.text.encode("utf-8"))[:limit]


def link_key(url: str) -> str:
    """An address as a server sees it: scheme and host in lower case, no fragment. The
    same rule as `ingest.url.Pages.key`, so a link copied out of a search finds its item."""
    parsed = urlparse(url.strip())
    return parsed._replace(
        scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower(), fragment=""
    ).geturl()


class Held:
    """The full texts the box's followed feeds carry right now, by link (2026-10-07).

    targum-internal#424: www.rbc.ru answers every article with a bot check
    (`401`, `server: QRATOR`) that neither the direct door nor the residential proxy
    passes, while its own feed carries each article whole. A reader handed an РБК link by
    `search_sources` was refused it. What is here lets `ingest.url.page` read such an
    article from the feed instead — and only such an article: an item of a feed this box
    follows, pulled by us from the publisher's own feed, whose page is behind a check or
    whose host is shut. Any other link is fetched exactly as before.

    Written by `chat.tools.Feeds` after each pull that answered, one feed's items
    replacing that feed's last ones, so an item leaves when the publisher drops it. A
    pull that failed leaves the last answer standing, as `Feeds` does.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        #: feed url -> (its publisher's language, {link key: item})
        self._by_feed: dict[str, tuple[str, dict[str, Item]]] = {}

    def keep(self, feed: str, items: list[Item], language: str = "") -> None:
        whole = {link_key(item.link): item for item in items if item.full_text and item.link}
        with self._lock:
            if whole:
                self._by_feed[feed] = (language, whole)
            else:
                self._by_feed.pop(feed, None)

    def find(self, link: str) -> tuple[Item, str] | None:
        """The item at `link` with its language, where a followed feed carries it whole."""
        key = link_key(link)
        with self._lock:
            for language, whole in self._by_feed.values():
                item = whole.get(key)
                if item is not None:
                    return item, language
        return None

    def clear(self) -> None:
        with self._lock:
            self._by_feed.clear()


HELD = Held()
