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

**And there is a second way in, which is Instagram's own.** The embed page — what a blog
shows when it embeds a post, `/p/<code>/embed/captioned/` — is served logged out, and it
carries the post itself: a reel's film and length, a carousel's every picture, and the
caption and author of all of them (measured from the box, direct and through the proxy,
2026-09-18). It is fetched through `ingest/url.py`'s guarded door like any page, and it
is two things here. For a reel, the backup: when yt-dlp is refused or has fallen behind
Instagram, the film is taken from there instead, so one broken extractor is not one
broken door. For a photo post, the only way: yt-dlp answers "There is no video in this
post", and a post's words are its caption.
"""

from __future__ import annotations

import html
import json
import logging
import re
import subprocess
from dataclasses import dataclass
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


#: Instagram's embed page for one post, served logged out. The one address this module
#: asks for itself rather than handing to yt-dlp.
EMBED = "https://www.instagram.com/p/{code}/embed/captioned/"

#: The most a picture of a post may be. A post's image is a few hundred kilobytes; this is
#: a ceiling against a CDN answer that is not one, never a size anybody expects.
MAX_PICTURE_BYTES = 20 * 1024 * 1024

#: Directional isolates and marks Instagram wraps captions in, and the tabs beside them.
_MARKS = "\u2066\u2067\u2068\u2069\u200e\u200f\t "


@dataclass(frozen=True)
class Post:
    """One Instagram post, as its embed page tells it."""

    code: str
    #: The account's handle, which is what the page shows as its author.
    author: str
    caption: str
    #: The film's address on Meta's CDN, where the post is a reel.
    video: str = ""
    duration: float = 0.0
    #: Every picture's address on Meta's CDN, in the post's own order, where it is not.
    pictures: tuple[str, ...] = ()

    @property
    def title(self) -> str:
        """The caption's first line, which is what a post calls itself."""
        return title_of(self.caption)


def title_of(caption: str) -> str:
    for line in caption.splitlines():
        if line := line.strip(_MARKS):
            return line[:120].strip()
    return ""


def is_reel(url: str) -> bool:
    """Whether this address names one Instagram video.

    Raises `TargumError` for a profile's grid or the explore page, the way a YouTube
    channel does: one video at a time.
    """
    return hosts.host_for(url) is hosts.INSTAGRAM and bool(hosts.video_id(url))


def is_post(url: str) -> bool:
    """Whether this address is a `/p/` post — a film or pictures, which only the post
    itself can say. A reel's address is always a film and is not asked this."""
    if hosts.host_for(url) is not hosts.INSTAGRAM:
        return False
    steps = [step for step in urlparse(url).path.split("/") if step]
    try:
        return "p" in steps and bool(hosts.video_id(url))
    except TargumError:
        return False


def home_url(url: str) -> str:
    """The reel's one canonical address, or "" for anything that is not a reel."""
    return hosts.home_url(url) if hosts.host_for(url) is hosts.INSTAGRAM else ""


def _vetted(url: str) -> None:
    if not is_reel(url):
        raise TargumError(
            "We couldn't find an Instagram reel at that address.", key="video.no-instagram-reel"
        )


def describe(url: str) -> dict[str, Any]:
    """What yt-dlp knows about the reel, with the length it leaves out filled in.

    `duration` is read off the header where yt-dlp gave none, and left at 0 where the
    header would not say either — the caller prices that on `GUESS_S` rather than
    refusing it as a live stream, which a reel never is.
    """
    _vetted(url)
    try:
        done = run_ytdlp(
            ["yt-dlp", "-J", "--no-playlist", "--skip-download", *TITLED, url],
            timeout=120,
            refused="Instagram wouldn't show us that reel.",
            minter=False,
            again=AGAIN,
            door=OTHER_DOOR,
            carry=False,
        )
    except TargumError as refusal:
        # yt-dlp refused, or is not here at all. The embed page is the second way in.
        post = backup(url)
        if post is None or not post.video:
            raise refusal from None
        return described_from(post)
    try:
        answer: dict[str, Any] = json.loads(done.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError as error:
        raise TargumError("yt-dlp answered with something that is not JSON.") from error
    if not answer.get("duration"):
        answer["duration"] = measured(answer)
    return answer


def described_from(post: Post) -> dict[str, Any]:
    """What `describe` would have said, from the embed page instead: the four things
    `screen.from_ytdlp` reads, in yt-dlp's own keys."""
    return {
        "id": post.code,
        "title": post.title or f"Video by {post.author}",
        "duration": post.duration,
        "uploader": post.author,
        "webpage_url": hosts.home_url(f"https://www.instagram.com/reel/{post.code}/"),
        "formats": [{"url": post.video}],
    }


def fetch(url: str, into: Path) -> Path:
    """The reel, fetched by yt-dlp into the workspace as `source.mp4` — or, where yt-dlp
    was refused, taken from the embed page's film instead."""
    _vetted(url)
    try:
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
    except TargumError as refusal:
        post = backup(url)
        if post is None or not post.video:
            raise refusal from None
        return _fetched_from(post, into)


def backup(url: str) -> Post | None:
    """The post as its embed page tells it, or None — quietly, because a backup that
    fails is the first refusal standing, and that is the sentence the reader is owed."""
    try:
        return embedded(url)
    except Exception as error:  # noqa: BLE001 - the first refusal is the answer
        log.warning("the Instagram embed page did not answer either: %s", error)
        return None


def _fetched_from(post: Post, into: Path) -> Path:
    """The embed page's film, downloaded through the guarded door and tagged the way
    `--embed-metadata` would have tagged it: the ingester reads the title and the byline
    off the container and nothing else."""
    from ..ingest.url import download
    from . import MAX_VIDEO_BYTES

    log.warning("yt-dlp was refused %s; taking the film from the embed page", post.code)
    into.mkdir(parents=True, exist_ok=True)
    raw = into / "embedded.mp4"
    download(post.video, raw, max_bytes=MAX_VIDEO_BYTES)
    target = into / "source.mp4"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(raw),
                "-c",
                "copy",
                "-metadata",
                f"title={post.title}",
                "-metadata",
                f"artist={post.author}",
                str(target),
            ],
            capture_output=True,
            check=True,
            timeout=600,
        )
    except (OSError, subprocess.SubprocessError):
        # Untagged is still the film. Titled after its file, but not lost.
        raw.replace(target)
    raw.unlink(missing_ok=True)
    return target


def embedded(url: str) -> Post:
    """The post this address names, read off Instagram's embed page."""
    from ..ingest.url import fetch as fetch_page

    code = hosts.video_id(url) if hosts.host_for(url) is hosts.INSTAGRAM else ""
    if not code:
        raise TargumError(
            "We couldn't find an Instagram post at that address.", key="video.no-instagram-post"
        )
    return read_embed(fetch_page(EMBED.format(code=code)).text, code)


#: The post's own data, a JSON document inside a JSON string inside the page's script.
_CONTEXT = re.compile(r'"contextJSON":("(?:[^"\\]|\\.)*")')


def read_embed(page: str, code: str) -> Post:
    """An embed page, read. Instagram writes it two ways: a reel or a carousel carries its
    post as data, and a single picture carries it only as markup. Both are read, and
    every address in the answer is one on Meta's CDN or it is left out."""
    found = _CONTEXT.search(page)
    media: dict[str, Any] = {}
    if found:
        try:
            context = json.loads(json.loads(found.group(1)))
            media = ((context or {}).get("gql_data") or {}).get("shortcode_media") or {}
        except (ValueError, AttributeError):
            media = {}
    if media:
        return _from_data(media, code)
    return _from_markup(page, code)


def _from_data(media: dict[str, Any], code: str) -> Post:
    edges = (media.get("edge_media_to_caption") or {}).get("edges") or []
    caption = str(((edges[0] if edges else {}).get("node") or {}).get("text") or "")
    author = str((media.get("owner") or {}).get("username") or "")
    if media.get("is_video") and on_the_cdn(str(media.get("video_url") or "")):
        return Post(
            code,
            author,
            caption,
            video=str(media["video_url"]),
            duration=float(media.get("video_duration") or 0.0),
        )
    slides = [
        edge.get("node") or {}
        for edge in (media.get("edge_sidecar_to_children") or {}).get("edges") or []
    ] or [media]
    pictures = tuple(
        str(slide.get("display_url") or "")
        for slide in slides
        if not slide.get("is_video") and on_the_cdn(str(slide.get("display_url") or ""))
    )
    return Post(code, author, caption, pictures=pictures)


_CAPTION = re.compile(
    r'<div class="Caption">\s*<a class="CaptionUsername"[^>]*>([^<]*)</a>(.*?)'
    r'(?:<div class="CaptionComments"|</div>)',
    re.S,
)
_IMAGE = re.compile(r'<img class="EmbeddedMediaImage"[^>]*>', re.S)
_SRCSET = re.compile(r'srcset="([^"]*)"')
_SRC = re.compile(r'\ssrc="([^"]*)"')


def _from_markup(page: str, code: str) -> Post:
    author, caption = "", ""
    if found := _CAPTION.search(page):
        author = html.unescape(found.group(1)).strip()
        text = re.sub(r"<br\s*/?>", "\n", found.group(2))
        caption = html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
    pictures: list[str] = []
    for tag in _IMAGE.findall(page):
        best = ""
        if srcset := _SRCSET.search(tag):
            # The widest rendition the page offers: "url 150w, url 1080w".
            offered = []
            for entry in html.unescape(srcset.group(1)).split(","):
                address, _, width = entry.strip().rpartition(" ")
                if address and width.rstrip("w").isdigit():
                    offered.append((int(width.rstrip("w")), address))
            best = max(offered)[1] if offered else ""
        if not best and (src := _SRC.search(tag)):
            best = html.unescape(src.group(1))
        if on_the_cdn(best) and best not in pictures:
            pictures.append(best)
    return Post(code, author, caption, pictures=tuple(pictures))


def pictures_into(post: Post, folder: Path) -> list[Path]:
    """A post's pictures, downloaded in order as `01.jpg`, `02.jpg`… — the order the
    picture reader reads a folder in — through the guarded door, capped at `MAX_PAGES`."""
    from ..ingest.url import download
    from ..vision import MAX_PAGES

    if len(post.pictures) > MAX_PAGES:
        raise TargumError(
            f"That post has more than {MAX_PAGES} pictures.",
            key="video.post-too-many-pictures",
            most=MAX_PAGES,
        )
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for n, address in enumerate(post.pictures, start=1):
        target = folder / f"{n:02d}.jpg"
        download(address, target, max_bytes=MAX_PICTURE_BYTES)
        written.append(target)
    return written


def caption_text(post: Post) -> str:
    """The caption as a text targum reads: front matter naming the title and the author,
    then the caption with the marks Instagram wraps it in taken off each line."""
    lines = [line.strip(_MARKS) for line in post.caption.splitlines()]
    body = "\n".join(lines).strip()
    title = (post.title or f"Post by {post.author}").replace("\n", " ")
    # Plain, not quoted: `parse_frontmatter` takes everything after the first colon and
    # trims quotes off the ends, so quoting would only put backslashes into a title.
    head = ["---", f"title: {title}"]
    if post.author:
        head.append(f"author: @{post.author}")
    return "\n".join([*head, "---", "", body, ""])


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
