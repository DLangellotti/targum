"""The Facebook door: one video at a time, through yt-dlp, direct once and then the proxy.

Measured from the box on 2026-09-30, twice, and the two disagree. In the morning, on five
public reels from כאן חדשות, `yt-dlp -J` answered five of five directly and four of five
through the residential proxy, where one came back `null`. Logged out, no cookies. Hours
later every reel tried failed directly with `[facebook] Cannot parse data` (yt-dlp
2026.08.19), and the same addresses answered through the proxy. So neither route is
the one: the direct ask is free and fails fast when it fails, and the proxy is where a
failure goes next — twice, because the proxy hands out a fresh exit per process.
"Cannot parse data" is a tell for the next route (`AGAIN`), and so is a `null` answer.

Everything else is the YouTube door's (`video/youtube.py`): the address is handed to
yt-dlp only once the host table (`video/hosts.py`) has named it one video, and no account
and no cookie is ever involved.

**Facebook's videos have no subtitles.** None of the five carried a track, written or
generated, so a Facebook video is heard and priced as a reel is: transcribed.

**A shared link is a short link.** The app's Copy link gives `facebook.com/share/r/…/`
for a reel and `…/share/v/…/` for a video, which name no video until Facebook redirects
them; both were followed from the box on 2026-09-30, to `/reel/<id>`, to
`/<page>/videos/<id>`, and once to a group's post, whose address names the post and not
its film. So the video's one canonical address is taken from the id in yt-dlp's answer
(`home_from`), not from the address it ended on. `fb.watch/<code>` is the older short
link and is taken the same way; the three found to try redirected the box to a login
page, which reads as links that have gone stale, and a live one could not be found.

**Facebook's title is a count.** yt-dlp names a reel "2.1K views · 43 reactions | <the
caption> | <the page>", which is a shelf of numbers that change. `TITLED` takes the
caption's first line instead, as the Instagram door does, and failing a caption strips the
counts. It is asked at the quote and at the fetch, where `--embed-metadata` writes the tag
the ingester reads, so the quote and the reader say the same thing.

**And a Facebook video arrives as a post** (targum-internal#158): the quote keeps the
page's name, the day and the caption off this door's answer for `post.json`
(`Library._prepare_facebook`), so the reader opens under the post's head, "On Facebook",
with the film beneath it. Facebook gives no handle a reader would recognise — only a
number — so the head carries the name alone.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..errors import TargumError
from . import hosts
from .youtube import _extra_args, fetch_through, run_ytdlp

#: The host that only ever redirects: a shared link, with no video id in it.
SHORT = frozenset({"fb.watch"})

#: What Facebook says when it has served this exit a page yt-dlp cannot read — the
#: afternoon of 2026-09-30, on every reel, directly. Worth another route, not a refusal.
AGAIN = ("Cannot parse data",)

#: The paths on facebook.com that only ever redirect: the app's Copy link, for a reel and
#: for a video.
SHARED = ("/share/r/", "/share/v/")

#: What a reader whose Facebook video we could not fetch can do instead, in their terms.
#: Facebook offers no download of somebody else's video, only Save, which keeps a link;
#: a phone's screen recording is the way a reader has.
OTHER_DOOR = "Record it on your phone and drop the file here."

#: The video's name. First the counts come off the front of yt-dlp's title ("1K views ·
#: 17 reactions | "); then, where the video has a caption, its first line stands instead,
#: cut at a word and no longer than 120 characters. A step that does not match leaves the
#: title as the one before it made it. Facebook opens captions with the same directional
#: marks Instagram does, which are skipped.
TITLED = (
    "--parse-metadata",
    "title:(?s)^(?:[\\d.,]+[KMB]?\\s(?:views?|reactions?|shares?|comments?|plays?)"
    "(?:\\s·\\s)?)+\\s\\|\\s(?P<title>.+)$",
    "--parse-metadata",
    "description:(?s)^[\\s\\u2066-\\u2069\\u200e\\u200f]*(?P<title>[^\\n]{1,120})(?=\\s|$)",
)


def _routes() -> list[list[str]]:
    """Direct once, then the proxy twice if there is one; direct twice where there is none
    (see the module's note)."""
    if proxied := _extra_args(minter=False):
        return [[], proxied, proxied]
    return [[], []]


def is_short(url: str) -> bool:
    """Whether this is a shared link that names no video until it is followed."""
    parsed = urlparse(url)
    name = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https"):
        return False
    if name in SHORT:
        return bool(parsed.path.strip("/"))
    return hosts.host_for(url) is hosts.FACEBOOK and parsed.path.startswith(SHARED)


def is_facebook(url: str) -> bool:
    """Whether this address names one Facebook video, or is a shared link to one.

    Raises `TargumError` for a group or the marketplace: one video at a time.
    """
    if hosts.host_for(url) is not hosts.FACEBOOK:
        return False
    return is_short(url) or bool(hosts.video_id(url))


def home_url(url: str) -> str:
    """The video's one canonical address, or "" — including for a short link, which
    names no video until it is followed."""
    return hosts.home_url(url) if hosts.host_for(url) is hosts.FACEBOOK else ""


def home_from(info: dict[str, Any]) -> str:
    """The canonical address of the video yt-dlp described, or "".

    The id first: a shared link can land on a group's post, whose address names the post
    and not the film, while the answer's `id` is the film's own and opens at the one
    prefix (measured 2026-09-30). The address it ended on only where the id is not a
    video's number.
    """
    found = str(info.get("id") or "")
    if found.isdigit():
        return f"{hosts.FACEBOOK.home}{found}"
    return home_url(str(info.get("webpage_url") or ""))


def _vetted(url: str) -> None:
    if not is_facebook(url):
        raise TargumError(
            "We couldn't find a Facebook video at that address.", key="video.no-facebook-video"
        )


def describe(url: str) -> dict[str, Any]:
    """What yt-dlp knows about the video without fetching it: `yt-dlp -J`."""
    _vetted(url)
    routes = _routes()
    for start in range(len(routes)):
        done = run_ytdlp(
            ["yt-dlp", "-J", "--no-playlist", "--skip-download", *TITLED, url],
            timeout=120,
            refused="Facebook wouldn't show us that video.",
            again=AGAIN,
            door=OTHER_DOOR,
            # Facebook's own sentences are about logging in, which a reader cannot do.
            carry=False,
            routes=routes[start:],
        )
        try:
            answer: dict[str, Any] | None = json.loads(done.stdout.decode("utf-8", "replace"))
        except json.JSONDecodeError as error:
            raise TargumError("yt-dlp answered with something that is not JSON.") from error
        if isinstance(answer, dict):
            return answer
        # The proxy's one miss on 2026-09-30 was not a refusal but a `null`: yt-dlp
        # finished and had nothing to say. The next route is asked, as it would be for a
        # refusal; where a refusal moved the ask along first, a route may be asked twice.
    raise TargumError("Facebook wouldn't show us that video.", OTHER_DOOR)


def fetch(url: str, into: Path) -> Path:
    """The video, fetched by yt-dlp into the workspace as `source.mp4`."""
    _vetted(url)
    return fetch_through(
        url,
        into,
        refused="Facebook wouldn't give us that video.",
        again=AGAIN,
        door=OTHER_DOOR,
        carry=False,
        asking=TITLED,
        routes=_routes(),
    )
