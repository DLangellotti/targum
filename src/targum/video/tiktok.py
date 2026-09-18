"""The TikTok door: one video at a time, through yt-dlp — and, unlike every other door,
not through the proxy.

Measured from the box on 2026-09-18: four public videos and five runs in a row answered
`yt-dlp -J` directly, and the video downloaded; the same request through the residential
proxy came back `HTTP Error 403`. TikTok refuses the exits a residential pool hands out and
serves the datacenter address, which is the reverse of YouTube and the reason #255 read
this door as shut: the one test that went direct named a single post TikTok had blocked,
and the rest went through the proxy. So the route here is direct, direct once more, and
the proxy last only because it costs nothing to ask.

Everything else is the YouTube door's (`video/youtube.py`): the address is handed to
yt-dlp only once the host table (`video/hosts.py`) has named it one video, and no account
and no cookie is ever involved.

**A shared link is a short link.** The app's Copy link gives `vm.tiktok.com/ZM…/` or
`www.tiktok.com/t/ZT…/`, which name no video until TikTok redirects them. yt-dlp follows
the redirect; the quote then carries the video's one canonical address (`home_url`) so
the build fetches, and the reader links home to, the same video.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..errors import TargumError
from . import hosts
from .youtube import _extra_args, fetch_through, run_ytdlp

#: The hosts that only ever redirect: a shared link, with no video id in it.
SHORT = frozenset({"vm.tiktok.com", "vt.tiktok.com"})

#: What a reader whose TikTok we could not fetch can do instead, in their terms.
OTHER_DOOR = "Save it in TikTok (Share, then Save video) and drop the file here."


def _routes() -> list[list[str]]:
    """Direct, direct again, then the proxy if there is one (see the module's note)."""
    routes: list[list[str]] = [[], []]
    if proxied := _extra_args(minter=False):
        routes.append(proxied)
    return routes


def is_short(url: str) -> bool:
    """Whether this is a shared link that names no video until it is followed."""
    parsed = urlparse(url)
    name = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https"):
        return False
    return name in SHORT or (hosts.host_for(url) is hosts.TIKTOK and parsed.path.startswith("/t/"))


def is_tiktok(url: str) -> bool:
    """Whether this address names one TikTok video, or is a shared link to one.

    Raises `TargumError` for a tag, a sound or a discover page: one video at a time.
    """
    if hosts.host_for(url) is not hosts.TIKTOK:
        return False
    return is_short(url) or bool(hosts.video_id(url))


def home_url(url: str) -> str:
    """The video's one canonical address, or "" — including for a short link, which
    names no video until it is followed."""
    return hosts.home_url(url) if hosts.host_for(url) is hosts.TIKTOK else ""


def _vetted(url: str) -> None:
    if not is_tiktok(url):
        raise TargumError("We couldn't find a TikTok video at that address.")


def describe(url: str) -> dict[str, Any]:
    """What yt-dlp knows about the video without fetching it: `yt-dlp -J`."""
    _vetted(url)
    done = run_ytdlp(
        ["yt-dlp", "-J", "--no-playlist", "--skip-download", url],
        timeout=120,
        refused="TikTok wouldn't show us that video.",
        door=OTHER_DOOR,
        # TikTok's own sentences are about IP addresses and logging in, neither of which
        # a reader can do anything about.
        carry=False,
        routes=_routes(),
    )
    try:
        answer: dict[str, Any] = json.loads(done.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError as error:
        raise TargumError("yt-dlp answered with something that is not JSON.") from error
    return answer


def fetch(url: str, into: Path) -> Path:
    """The video, fetched by yt-dlp into the workspace as `source.mp4`."""
    _vetted(url)
    return fetch_through(
        url,
        into,
        refused="TikTok wouldn't give us that video.",
        door=OTHER_DOOR,
        carry=False,
        routes=_routes(),
    )
