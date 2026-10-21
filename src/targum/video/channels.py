"""A YouTube channel subscribed to: what it is, and what it put out lately.

design.md §12, "A channel or a podcast is subscribed to, never built from its address"
(2026-10-09). `youtube.is_youtube` still refuses a channel address at every door that
builds — the Upload page, `quote_build`, a set — because an address names somebody else's
whole shelf. This is the one door that reads it, and it reads it only as a subscription:
which channel it is, how often it puts something out and how long that usually runs, and
its newest uploads, so the confirm page can say what a new one uses and the poll can find
what came out since.

**Through the Data API, never scraped.** The same key and the same one host
`video/discover.py` asks (`discover.fetch`), three cheap calls: `channels.list` (1 unit),
`playlistItems.list` on the channel's uploads (1 unit) and `videos.list` for their lengths
(1 unit). Nothing here fetches a video or spends: building one is a job like any pasted
link's, made later through `Library.press`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import unquote, urlparse

from ..errors import TargumError
from . import discover
from .youtube import HOSTS

CHANNELS = f"{discover.API}/channels"
PLAYLIST_ITEMS = f"{discover.API}/playlistItems"

#: How many of a channel's newest uploads are read: enough to say how often it puts
#: something out over a month, and to list what was out before a reader subscribed.
NEWEST = 25

Fetch = Callable[[str, Mapping[str, str]], dict[str, Any]]


@dataclass(frozen=True)
class Channel:
    id: str
    title: str
    #: The playlist every upload lands in (`UU…`), which is what is read for new ones.
    uploads: str
    language: str = ""


@dataclass(frozen=True)
class Upload:
    id: str
    title: str
    #: When it went up, in milliseconds.
    published: int
    seconds: int

    @property
    def link(self) -> str:
        return f"https://www.youtube.com/watch?v={self.id}"


def named(url: str) -> tuple[str, str] | None:
    """What a channel address names it by: `("id", "UC…")`, `("handle", "@name")` or
    `("username", "name")`. None for anything that is not a channel's address."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return None
    if (parsed.hostname or "").lower() not in HOSTS:
        return None
    steps = [unquote(step) for step in parsed.path.split("/") if step]
    if not steps:
        return None
    if steps[0] == "channel" and len(steps) > 1 and steps[1].startswith("UC"):
        return ("id", steps[1])
    if steps[0].startswith("@") and len(steps[0]) > 1:
        return ("handle", steps[0])
    if steps[0] == "user" and len(steps) > 1:
        return ("username", steps[1])
    if steps[0] == "c" and len(steps) > 1:
        # A custom address has no lookup of its own; it is the handle more often than not.
        return ("handle", "@" + steps[1])
    return None


def find(url: str, get: Fetch | None = None, api_key: str = "") -> Channel:
    """The channel an address names, or a refusal that says what to paste instead."""
    ask = get or discover.fetch
    which = named(url)
    if which is None:
        raise TargumError(
            "That isn't a YouTube channel's address.",
            "Paste the channel's own page, the one with its name after youtube.com/.",
            key="subscribe.not-a-channel",
        )
    field = {"id": "id", "handle": "forHandle", "username": "forUsername"}[which[0]]
    answer = ask(
        CHANNELS,
        {"key": api_key or discover.key(), "part": "snippet,contentDetails", field: which[1]},
    )
    items = answer.get("items") or []
    if not items:
        raise TargumError(
            "We couldn't find that channel on YouTube.",
            "Check the address and try again.",
            key="subscribe.no-channel",
        )
    item = items[0]
    snippet = item.get("snippet") or {}
    uploads = str(
        ((item.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads") or ""
    )
    if not uploads:
        raise TargumError(
            "That channel has no uploads we can read.",
            key="subscribe.no-uploads",
        )
    language = str(snippet.get("defaultLanguage") or "").split("-")[0].lower()
    return Channel(
        id=str(item.get("id") or ""),
        title=str(snippet.get("title") or ""),
        uploads=uploads,
        language=language,
    )


def _ms(stamp: str) -> int:
    try:
        return int(datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() * 1000)
    except (TypeError, ValueError):
        return 0


def newest(
    channel: Channel, get: Fetch | None = None, api_key: str = "", limit: int = NEWEST
) -> list[Upload]:
    """The channel's newest uploads, newest first, each with its length. A live stream or
    a premiere still to come has no length yet and is left out: it is not a video yet."""
    ask = get or discover.fetch
    held = api_key or discover.key()
    listed = ask(
        PLAYLIST_ITEMS,
        {
            "key": held,
            "part": "contentDetails,snippet",
            "playlistId": channel.uploads,
            "maxResults": str(min(limit, discover.PAGE)),
        },
    )
    order: list[str] = []
    titles: dict[str, str] = {}
    for item in listed.get("items") or []:
        video = str((item.get("contentDetails") or {}).get("videoId") or "")
        if not video or video in titles:
            continue
        order.append(video)
        titles[video] = str((item.get("snippet") or {}).get("title") or "")
    if not order:
        return []
    details = ask(
        discover.VIDEOS,
        {"key": held, "part": "contentDetails,snippet", "id": ",".join(order)},
    )
    found: dict[str, Upload] = {}
    for item in details.get("items") or []:
        snippet = item.get("snippet") or {}
        if str(snippet.get("liveBroadcastContent") or "none") != "none":
            continue
        seconds = discover.seconds(str((item.get("contentDetails") or {}).get("duration") or ""))
        if seconds <= 0:
            continue
        video = str(item.get("id") or "")
        found[video] = Upload(
            id=video,
            title=str(snippet.get("title") or titles.get(video, "")),
            published=_ms(str(snippet.get("publishedAt") or "")),
            seconds=seconds,
        )
    out = [found[video] for video in order if video in found]
    out.sort(key=lambda upload: upload.published, reverse=True)
    return out
