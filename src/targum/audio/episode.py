"""One podcast episode, found from whatever address a reader had in hand.

Three shapes arrive: the enclosure itself (an address ending in .mp3), the episode's
page, and the feed. Each is walked back to one audio URL — and, where the feed offers
one, a transcript, which makes the import free of transcription. Every fetch goes
through `ingest.url`, the only outbound door there is.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from pydantic import BaseModel

from ..errors import UnsupportedSource
from . import AUDIO_SUFFIXES

#: An Apple Podcasts page is a script that draws itself: no <audio>, no og:audio, no
#: feed link — pasting one used to hand the show notes to the article path. The show id
#: is in the address, and Apple's public lookup API answers with every episode's real
#: enclosure, so the page itself is never needed.
_APPLE = re.compile(r"podcasts\.apple\.com/.+?/id(\d+)")
_LOOKUP = "https://itunes.apple.com/lookup"

#: A feed named in a page's scripts rather than its markup — omny writes its
#: omnycontent address into embedded JSON and nowhere a parser of elements looks.
_RSS_IN_TEXT = re.compile(r'https?://[^"\'\s<>\\]+?\.rss\b')

#: The same escape hatch for every other player page that draws itself: the enclosure
#: usually sits in the page's embedded JSON under this name.
_ASSET = re.compile(r'"assetUrl"\s*:\s*"((?:[^"\\]|\\.)+)"')

#: What a page says it is, in schema.org's words (`"@type"` in its ld+json, a list or one
#: name). Matched lowercased.
_LD_TYPE = re.compile(r'"@type"\s*:\s*\[?\s*"([A-Za-z]+)"')
_ARTICLE_TYPES = frozenset(
    {
        "article",
        "newsarticle",
        "opinionnewsarticle",
        "analysisnewsarticle",
        "reportagenewsarticle",
        "backgroundnewsarticle",
        "reviewnewsarticle",
        "blogposting",
        "report",
    }
)
_EPISODE_TYPES = frozenset(
    {"podcastepisode", "radioepisode", "episode", "audioobject", "podcastseries"}
)

#: An article's own words, at least, before its player is taken for a read-aloud of it
#: rather than the point of the page (targum-internal#736). Show notes run shorter.
ARTICLE_WORDS = 200

#: An enclosure a news feed hangs on its items is a picture as often as not, and an
#: untyped one passes `feeds._enclosure` (targum-internal#736).
_NOT_AUDIO = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".mp4", ".mov", ".webm"}
)


class Episode(BaseModel):
    audio_url: str
    title: str = ""
    transcript_url: str = ""
    transcript_type: str = ""
    #: From the feed's own claim, for pricing before a byte of audio arrives.
    seconds: float = 0.0
    #: The episode's picture as its feed names it (the item's `itunes:image`, else the
    #: show's), and the feed that named it, for `thumbs.capture` to keep beside the
    #: reader of whoever added it (targum-internal#429). "" where there is none.
    artwork_url: str = ""
    feed_url: str = ""


def sounds_like_audio(url: str) -> bool:
    """Whether the address itself names an audio file."""
    return Path(urlparse(url).path).suffix.lower() in AUDIO_SUFFIXES


def find(url: str) -> Episode | None:
    """The episode this address means, or None where it is an ordinary page.

    A feed answers with its newest episode that has audio — the single-episode import
    has to pick one, and the newest is the one the address was almost certainly copied
    for. An episode page is searched for its own audio, then for the feed it belongs
    to, followed one hop.
    """
    from ..ingest.url import page

    if sounds_like_audio(url):
        return Episode(audio_url=url)
    host = (urlparse(url).hostname or "").lower()
    if host.endswith("spotify.com"):
        # Spotify's page offers a one-minute preview as og:audio, and a reader handed
        # a minute titled as the episode has been lied to. The show exists elsewhere.
        # The way on names the description box since targum-internal#253 built it:
        # saying what the episode is and pressing Continue looks for it where it can be
        # had. Offered, never run — the press is the reader's (targum-internal#252).
        raise UnsupportedSource(
            "Spotify doesn't let us bring in its audio.",
            "Paste the show's page on Apple Podcasts, its RSS feed or the episode's own "
            "site — or say what the episode is and press Continue, and we'll look.",
            key="episode.spotify",
        )
    apple = _APPLE.search(url)
    if apple:
        wanted = parse_qs(urlparse(url).query).get("i", [""])[0]
        found = _from_apple(apple.group(1), wanted)
        if found is not None:
            return found
    # Through `page`: an article is asked about here first and read by the ingester next,
    # and the second read is the first one kept (`ingest.url.Pages`, 2026-10-06).
    got = page(url)
    kind = got.content_type.split(";")[0].strip().lower()
    if kind.startswith("audio/"):
        return Episode(audio_url=url)
    if "xml" in kind or got.text.lstrip()[:100].startswith(("<?xml", "<rss", "<feed")):
        return _from_feed(got.raw or got.text.encode("utf-8"), url)
    if "html" in kind or not kind:
        return _from_page(got.text, url)
    return None


def _from_apple(show_id: str, episode_id: str) -> Episode | None:
    """One episode, from Apple's own lookup API rather than its unreadable page.

    With an episode id (`?i=` in the address) the match is exact; without one the
    address names the show, and its feed answers the way any feed does. Through the
    ordinary fetch door: the API is public JSON, well under the page ceiling.
    """
    from ..ingest.url import fetch

    try:
        got = fetch(
            _LOOKUP,
            {
                "id": show_id,
                "media": "podcast",
                "entity": "podcastEpisode",
                "limit": "200",
            },
        )
        answer = json.loads(got.text)
    except Exception:  # noqa: BLE001 - an unreachable API falls through to the page
        return None
    results = answer.get("results") or []
    feed = next((str(r["feedUrl"]) for r in results if r.get("feedUrl")), "")
    episodes = [r for r in results if r.get("episodeUrl")]
    chosen = None
    if episode_id:
        chosen = next((r for r in episodes if str(r.get("trackId") or "") == episode_id), None)
    if chosen is None and not episode_id and feed:
        # The address names the show; the feed's newest episode stands, as for any feed.
        try:
            fetched = fetch(feed)
        except Exception:  # noqa: BLE001
            return None
        return _from_feed(fetched.raw or fetched.text.encode("utf-8"), feed)
    if chosen is None:
        return None
    return Episode(
        audio_url=str(chosen["episodeUrl"]),
        title=str(chosen.get("trackName") or ""),
        seconds=float(chosen.get("trackTimeMillis") or 0) / 1000,
    )


#: A page's own pointer to its feed: `<link rel="alternate" type="application/rss+xml">`.
_FEED_TYPES = ("application/rss+xml", "application/atom+xml", "application/xml", "text/xml")


def feed_of(url: str) -> str:
    """The feed a podcast's address belongs to, or "" where there is none to be found.

    For a subscription (design.md §12, "A channel or a podcast is subscribed to, never built
    from its address", 2026-10-09): the address a reader has is the feed itself, the show's
    page on Apple Podcasts — whose lookup names the feed — or the show's own site, whose
    head points at it. Through the one outbound door, as everything here is.
    """
    from bs4 import BeautifulSoup

    from ..ingest.url import fetch, page

    apple = _APPLE.search(url)
    if apple:
        try:
            got = fetch(_LOOKUP, {"id": apple.group(1), "media": "podcast"})
            results = json.loads(got.text).get("results") or []
        except Exception:  # noqa: BLE001 - an unreachable API is no feed
            return ""
        return next((str(r["feedUrl"]) for r in results if r.get("feedUrl")), "")
    got = page(url)
    kind = got.content_type.split(";")[0].strip().lower()
    if "xml" in kind or got.text.lstrip()[:100].startswith(("<?xml", "<rss", "<feed")):
        return url
    if "html" in kind or not kind:
        soup = BeautifulSoup(got.text, "html.parser")
        for link in soup.find_all("link"):
            rel = " ".join(link.get("rel") or []).lower()
            if "alternate" in rel and str(link.get("type") or "").lower() in _FEED_TYPES:
                href = str(link.get("href") or "")
                if href:
                    return urljoin(url, href)
        found = _RSS_IN_TEXT.search(got.text)
        if found:
            return found.group(0)
    return ""


def episodes(feed: str, limit: int = 60) -> tuple[str, list[Any]]:
    """A podcast feed's name and its episodes that carry audio, in the feed's order —
    newest first, as feeds put them. Every one, not the newest alone, so a subscription
    can list everything since the last one it saw."""
    from ..ingest.url import fetch
    from ..weekly import feeds

    got = fetch(feed)
    body = got.raw or got.text.encode("utf-8")
    items = [item for item in feeds.parse(body) if item.enclosure][:limit]
    return feeds.title(body), items


def _bare(url: str) -> str:
    """An address as a feed and a browser would both spell it: no query, no scheme."""
    parsed = urlparse(url)
    return f"{parsed.netloc}{parsed.path}".rstrip("/").lower()


def _from_feed(
    xml: bytes, base: str, *, page: str = "", feed: str = "", exact: bool = False
) -> Episode | None:
    """The feed's episode for `page` where the feed says which, else its newest.

    A player page often carries no audio of its own, only the feed it belongs to —
    and the feed's newest episode is not the one whose page somebody pasted. The
    items name their own pages, so the match is asked for before the newest stands.
    `exact` asks for the match alone: an article's site feed has a newest item too,
    and it is somebody else's (targum-internal#736).
    """
    from ..weekly import feeds

    items = [
        item
        for item in feeds.parse(xml)
        if item.enclosure and Path(urlparse(item.enclosure).path).suffix.lower() not in _NOT_AUDIO
    ]
    chosen = None
    if page:
        wanted = _bare(page)
        chosen = next((item for item in items if _bare(item.link) == wanted), None)
    if chosen is None and not exact:
        chosen = next(iter(items), None)
    if chosen is None:
        return None
    named = chosen.artwork or feeds.artwork(xml)
    artwork = urljoin(base, named) if named else ""
    if urlparse(artwork).scheme not in ("http", "https"):
        artwork = ""
    return Episode(
        audio_url=urljoin(base, chosen.enclosure),
        title=chosen.title,
        transcript_url=urljoin(base, chosen.transcript) if chosen.transcript else "",
        transcript_type=chosen.transcript_type,
        seconds=chosen.seconds,
        artwork_url=artwork,
        feed_url=(feed or base) if artwork else "",
    )


def _from_page(html: str, base: str) -> Episode | None:
    from bs4 import BeautifulSoup

    page = BeautifulSoup(html, "html.parser")

    # An article is read, whatever player sits beside it (targum-internal#736). Israel
    # Hayom puts an <audio> of a machine reading the article aloud on every opinion
    # piece, and that player was quoted as an hour-long podcast episode. Only the
    # article's own feed can still say otherwise: an item for this very page, with audio.
    article = _is_article(page, html)

    # The page's own player.
    for sound in [] if article else page.find_all("audio"):
        src = sound.get("src") or next(
            (
                inner.get("src")
                for inner in sound.find_all("source")
                if str(inner.get("type", "")).startswith("audio/") or inner.get("src")
            ),
            None,
        )
        if src:
            return _played(urljoin(base, str(src)), page)

    # Open Graph's word for the same thing.
    for name in ("og:audio", "og:audio:url", "og:audio:secure_url"):
        if article:
            break
        meta = page.find("meta", property=name) or page.find("meta", attrs={"name": name})
        if meta and meta.get("content"):
            return _played(urljoin(base, str(meta["content"])), page)

    # A player page that draws itself usually still carries the enclosure in its
    # embedded JSON. The address is enough; the markup around it is not consulted.
    for match in [] if article else _ASSET.finditer(html):
        try:
            # The value is a JSON string and is unescaped as one: unicode_escape does
            # not know about \/ and would leave the address broken.
            address = str(json.loads(f'"{match.group(1)}"'))
        except json.JSONDecodeError:
            continue
        if sounds_like_audio(address):
            return _played(urljoin(base, address), page)

    # The feed this page belongs to, one hop, never more. Player pages that draw
    # themselves — omny and its cousins — often name the feed only inside a script,
    # so the page's text is searched when its markup says nothing.
    from ..ingest.url import fetch

    feed = page.find("link", type="application/rss+xml")
    addresses = [str(feed["href"])] if feed and feed.get("href") else []
    if not addresses:
        addresses = _RSS_IN_TEXT.findall(html)[:2]
    for address in addresses:
        try:
            got = fetch(urljoin(base, address))
        except Exception:  # noqa: BLE001 - a dead feed link is not the page's fault
            continue
        found = _from_feed(
            got.raw or got.text.encode("utf-8"),
            base,
            page=base,
            feed=urljoin(base, address),
            exact=article,
        )
        if found is not None:
            return found
    return None


def _is_article(page: object, html: str) -> bool:
    """Whether a page is an article first, and any audio on it is beside the point.

    It says so (Open Graph's `article`, or schema.org's Article or one of its news kinds),
    it does not also say it is an episode, and its article runs to `ARTICLE_WORDS` words as
    the ingester reads it — so a podcast's own page, which usually calls itself an article
    too, still plays where its show notes are a paragraph.
    """
    from bs4 import BeautifulSoup

    from ..ingest.url import article_paragraphs

    assert isinstance(page, BeautifulSoup)
    meta = page.find("meta", property="og:type") or page.find("meta", attrs={"name": "og:type"})
    said = str(meta.get("content") or "").strip().lower() if meta else ""
    kinds = {kind.lower() for kind in _LD_TYPE.findall(html)}
    if kinds & _EPISODE_TYPES or said.startswith(("music", "video")):
        return False
    if said != "article" and not kinds & _ARTICLE_TYPES:
        return False
    words = sum(len(text.split()) for _, _, text in article_paragraphs(html))
    return words >= ARTICLE_WORDS


def _played(address: str, page: object) -> Episode:
    """A page's own recording, timed from its front where nothing on the page says how
    long it runs — a length read is a price that is true, and the hour `Library.
    _prepare_episode` stands in with is for a recording nobody could time
    (targum-internal#736)."""
    return Episode(audio_url=address, title=_title(page), seconds=_timed(address))


def _timed(address: str) -> float:
    """How long the recording at `address` runs, from its first bytes; 0.0 where that
    cannot be read. Through the one outbound door, and never the whole file."""
    from ..ingest.url import opening
    from .probe import timed

    try:
        front = opening(address)
    except Exception:  # noqa: BLE001 - an untimed recording is still a recording
        return 0.0
    return timed(front.head, front.length)


def _title(page: object) -> str:
    from bs4 import BeautifulSoup

    assert isinstance(page, BeautifulSoup)
    meta = page.find("meta", property="og:title")
    if meta and meta.get("content"):
        return str(meta["content"]).strip()
    return page.title.get_text().strip() if page.title else ""
