"""The Instagram door: one reel at a time, through the binary and the egress YouTube uses.

Everything `video/youtube.py` says about a second outbound door holds here: nothing in
this module fetches anything itself, the address is handed to yt-dlp only once the host
table (`video/hosts.py`) has named it one reel, and the fetch leaves through the same
residential proxy. No cookies and no account, for the reason `youtube.YTDLP_PROXY_ENV`
gives — a proxy is an egress and nothing else, and a session on the box fetching for
strangers is a ban waiting to happen. Measured 2026-09-18: logged out is enough.

Two things differ, and they are the whole of this module.

**Instagram does not say how long a reel runs.** `yt-dlp -J` answers with formats, a
caption and an uploader, and `duration` is None. The price and the hours both lean on
it, so the length is read from the video's own header with ffprobe — a few kilobytes of
the file at Instagram's CDN, which answered from the box directly in under a second. That
is the one request this module causes that yt-dlp does not make, so it is fenced the way
`ingest/url.py` fences everything: https only, and only to Meta's CDN.

**Instagram's refusals are written for somebody logged in.** "Check if this post is
accessible in your browser without being logged-in" is not a sentence a reader can act on.
So the reader is told targum's sentence and the way that does work: download the reel in
Instagram and bring the file.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..errors import TargumError
from . import hosts
from .youtube import fetch_through, run_ytdlp

log = logging.getLogger(__name__)

#: What yt-dlp says when the exit it left through was refused a reel another exit is
#: shown. Seen on 2026-09-17 from the box and not on the five runs the next day, so it is
#: worth a second exit and never a third.
AGAIN = ("empty media response",)

#: Where Instagram keeps the video itself. The one place the duration probe may go.
CDN = (".fbcdn.net", ".cdninstagram.com")

#: What a reel is priced at when its own header will not say. Reels run to a few minutes;
#: erring long is the side the budget wants, as a silent podcast feed's hour does.
GUESS_S = 180.0

#: How many of the reel's formats are asked before giving up. Every one is the same film,
#: so a second is for a flaky edge server and a third would be asking the same question.
PROBES = 2

#: The reel's name, taken from the first line of its caption. yt-dlp calls every reel
#: "Video by <account>", which is a byline and not a title: a shelf of them would be a
#: shelf of one name. Set before `--embed-metadata` writes the tag the ingester reads, so
#: the quote and the reader say the same thing. Instagram opens captions with directional
#: isolates and tabs, which are skipped; a reel with no caption keeps yt-dlp's name.
TITLED = (
    "--parse-metadata",
    "description:(?s)^[\\s\\u2066-\\u2069\\u200e\\u200f]*(?P<title>[^\\n]{1,120})",
)

#: What a reader who pasted a reel we could not fetch can do instead, in their terms.
OTHER_DOOR = "Download it in Instagram (Share, then Download) and drop the file here."


def is_reel(url: str) -> bool:
    """Whether this address names one Instagram video.

    Raises `TargumError` for a profile's grid or the explore page, the way a YouTube
    channel does: one video at a time.
    """
    return hosts.host_for(url) is hosts.INSTAGRAM and bool(hosts.video_id(url))


def home_url(url: str) -> str:
    """The reel's one canonical address, or "" for anything that is not a reel."""
    return hosts.home_url(url) if hosts.host_for(url) is hosts.INSTAGRAM else ""


def _vetted(url: str) -> None:
    if not is_reel(url):
        raise TargumError("We couldn't find an Instagram reel at that address.")


def describe(url: str) -> dict[str, Any]:
    """What yt-dlp knows about the reel, with the length it leaves out filled in.

    `duration` is read off the header where yt-dlp gave none, and left at 0 where the
    header would not say either — the caller prices that on `GUESS_S` rather than
    refusing it as a live stream, which a reel never is.
    """
    _vetted(url)
    done = run_ytdlp(
        ["yt-dlp", "-J", "--no-playlist", "--skip-download", *TITLED, url],
        timeout=120,
        refused="Instagram wouldn't show us that reel.",
        minter=False,
        again=AGAIN,
        door=OTHER_DOOR,
        carry=False,
    )
    try:
        answer: dict[str, Any] = json.loads(done.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError as error:
        raise TargumError("yt-dlp answered with something that is not JSON.") from error
    if not answer.get("duration"):
        answer["duration"] = measured(answer)
    return answer


def fetch(url: str, into: Path) -> Path:
    """The reel, fetched by yt-dlp into the workspace as `source.mp4`."""
    _vetted(url)
    return fetch_through(
        url,
        into,
        refused="Instagram wouldn't give us that reel.",
        minter=False,
        again=AGAIN,
        door=OTHER_DOOR,
        carry=False,
        asking=TITLED,
    )


def on_the_cdn(address: str) -> bool:
    """Whether an address yt-dlp handed back is Instagram's own video store.

    It arrived inside JSON a platform wrote, and ffprobe is not behind the SSRF guard —
    so a format pointing anywhere else is not followed, however it got there.
    """
    parsed = urlparse(address)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and host.endswith(CDN)


def measured(info: dict[str, Any]) -> float:
    """The reel's length from its own header, or 0.0 where no header would say."""
    addresses = [str(fmt.get("url") or "") for fmt in info.get("formats") or []]
    for address in [one for one in addresses if on_the_cdn(one)][:PROBES]:
        try:
            done = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    # https and what it rides on, and nothing a response could redirect
                    # the probe into.
                    "-protocol_whitelist",
                    "https,tls,tcp",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    address,
                ],
                capture_output=True,
                check=True,
                timeout=20,
            )
            return float(done.stdout.decode("utf-8", "replace").strip())
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            log.info("ffprobe could not time a reel format: %s", type(error).__name__)
    return 0.0
