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


class Episode(BaseModel):
    audio_url: str
    title: str = ""
    transcript_url: str = ""
    transcript_type: str = ""
    #: From the feed's own claim, for pricing before a byte of audio arrives.
    seconds: float = 0.0


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
    from ..ingest.url import fetch

    if sounds_like_audio(url):
        return Episode(audio_url=url)
    host = (urlparse(url).hostname or "").lower()
    if host.endswith("spotify.com"):
        # Spotify's page offers a one-minute preview as og:audio, and a reader handed
        # a minute titled as the episode has been lied to. The show exists elsewhere.
        raise UnsupportedSource(
            "Spotify keeps its audio to itself.",
            "Paste the show's page on Apple Podcasts, its RSS feed, or the episode's "
            "own site instead.",
        )
    apple = _APPLE.search(url)
    if apple:
        wanted = parse_qs(urlparse(url).query).get("i", [""])[0]
        found = _from_apple(apple.group(1), wanted)
        if found is not None:
            return found
    got = fetch(url)
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


def _bare(url: str) -> str:
    """An address as a feed and a browser would both spell it: no query, no scheme."""
    parsed = urlparse(url)
    return f"{parsed.netloc}{parsed.path}".rstrip("/").lower()


def _from_feed(xml: bytes, base: str, *, page: str = "") -> Episode | None:
    """The feed's episode for `page` where the feed says which, else its newest.

    A player page often carries no audio of its own, only the feed it belongs to —
    and the feed's newest episode is not the one whose page somebody pasted. The
    items name their own pages, so the match is asked for before the newest stands.
    """
    from ..weekly import feeds

    items = [item for item in feeds.parse(xml) if item.enclosure]
    chosen = None
    if page:
        wanted = _bare(page)
        chosen = next((item for item in items if _bare(item.link) == wanted), None)
    if chosen is None:
        chosen = next(iter(items), None)
    if chosen is None:
        return None
    return Episode(
        audio_url=urljoin(base, chosen.enclosure),
        title=chosen.title,
        transcript_url=urljoin(base, chosen.transcript) if chosen.transcript else "",
        transcript_type=chosen.transcript_type,
        seconds=chosen.seconds,
    )


def _from_page(html: str, base: str) -> Episode | None:
    from bs4 import BeautifulSoup

    page = BeautifulSoup(html, "html.parser")

    # The page's own player.
    for sound in page.find_all("audio"):
        src = sound.get("src") or next(
            (
                inner.get("src")
                for inner in sound.find_all("source")
                if str(inner.get("type", "")).startswith("audio/") or inner.get("src")
            ),
            None,
        )
        if src:
            return Episode(audio_url=urljoin(base, str(src)), title=_title(page))

    # Open Graph's word for the same thing.
    for name in ("og:audio", "og:audio:url", "og:audio:secure_url"):
        meta = page.find("meta", property=name) or page.find("meta", attrs={"name": name})
        if meta and meta.get("content"):
            return Episode(audio_url=urljoin(base, str(meta["content"])), title=_title(page))

    # A player page that draws itself usually still carries the enclosure in its
    # embedded JSON. The address is enough; the markup around it is not consulted.
    for match in _ASSET.finditer(html):
        try:
            # The value is a JSON string and is unescaped as one: unicode_escape does
            # not know about \/ and would leave the address broken.
            address = str(json.loads(f'"{match.group(1)}"'))
        except json.JSONDecodeError:
            continue
        if sounds_like_audio(address):
            return Episode(audio_url=urljoin(base, address), title=_title(page))

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
        found = _from_feed(got.raw or got.text.encode("utf-8"), base, page=base)
        if found is not None:
            return found
    return None


def _title(page: object) -> str:
    from bs4 import BeautifulSoup

    assert isinstance(page, BeautifulSoup)
    meta = page.find("meta", property="og:title")
    if meta and meta.get("content"):
        return str(meta["content"]).strip()
    return page.title.get_text().strip() if page.title else ""
