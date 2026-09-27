"""The X door: a post, or the thread its author wrote up to it, read off X's syndication
endpoint (targum-internal#158). **Off unless the deployment arms it** (`ENV`).

**Why it is off.** X's terms forbid collecting its content by automated means without
its written consent, and the epic (#157) is plain that the box fetching a post for a
subscriber is targum's act, not the reader's. The endpoint used here is the one X's own
embed widget reads, served logged out and asked for one post at a time, which is a
narrower act than a crawl — but it is not an API X has licensed to targum, and whether
to rely on it is David's call, not this module's. So it is written, tested and shut.
Nothing here uses a cookie, a login or a token of anybody's: the `token` below is not a
credential but a number the widget derives from the post's id.

**What it reads.** `cdn.syndication.twimg.com/tweet-result?id=<id>&token=<t>` answers a
post as JSON: its text and where the displayed part of it runs, the author's handle, name
and picture, the moment it was posted, its photos, and — for a reply — which post it
answers and whose, and how many replies it has. `token(id)` is the widget's own
derivation: `((Number(id) / 1e15) * Math.PI).toString(36).replace(/(0+|\\.)/g, '')`, as
X's own embed bundle writes it (`platform.twitter.com/embed/embed.Tweet.*.js`:
`toString(Math.pow(6,2))` and `replace(/(0+|\\.)/g,"")`, read 2026-09-27) and as Vercel's
`react-tweet` does (`fetch-tweet.ts`, `getToken`). The endpoint answered without one on
2026-09-27; it is sent anyway, as the widget does.

**A thread is walked back, then on.** The endpoint says which post a post answers and
never what answers it. So the walk goes back first, from the post pasted through each
parent by the same author to where the thread starts, and stops at the first post by
anyone else, which is not kept (#158: "other accounts' replies are out of scope"). Then
on: the author's timeline as X's embedded-timeline widget shows it (`TIMELINE`) is read
once for the author's own replies, and each whose parent is the last post kept is kept
after it. That timeline is not the whole of anybody's: about twenty of the latest posts
for one account, a hundred of the most-engaged for another (measured 2026-09-27), so a
thread's later posts are found only where they are among those. Whether anything may be
missing is said, not guessed (`Thread.more`): only a last post with no reply at all is
proof the thread ends there. The timeline is not asked when it is.

**Photos are kept, a video is not.** Photos come from `pbs.twimg.com`, and only from
there; they are kept as webp by `ingest.post` like any post's pictures. A post's video is
not fetched: that would be a second, heavier act of the same kind, and a post's words are
its text.
"""

from __future__ import annotations

import html
import json
import math
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from ..errors import TargumError
from .post import lines_of

#: The switch. Anything but 1, true or yes leaves the door shut.
ENV = "TARGUM_X"

#: The hostnames that are plainly X's. `t.co` is not one: it names no post.
HOSTS = frozenset(
    {"x.com", "www.x.com", "mobile.x.com", "twitter.com", "www.twitter.com", "mobile.twitter.com"}
)

#: A post's one canonical address, with the id appended: what the head's "On X" links to.
#: `/i/status/<id>` opens any post whoever wrote it, so every spelling of a post reduces
#: to one prefix, which is what `tests/test_render` pins.
HOME = "https://x.com/i/status/"

#: The widget's endpoint. The one address this module asks for.
SYNDICATION = "https://cdn.syndication.twimg.com/tweet-result"

#: Where X keeps its pictures. A photo or a face anywhere else is not followed.
MEDIA_HOST = "pbs.twimg.com"

#: The most posts a thread is walked back through: each is a request, and a thread longer
#: than this is a book the reader can bring another way.
MOST = 25

#: A post id: digits, and never more than forty of them (the widget's own check).
_ID = re.compile(r"^[0-9]{1,40}$")

_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def is_open() -> bool:
    """Whether this deployment fetches from X. Off by default — see the module's note."""
    return os.environ.get(ENV, "").strip().lower() in {"1", "true", "yes"}


def is_x(url: str) -> bool:
    """Whether this address is X's at all: a post, a profile or anything else there."""
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https") and (parsed.hostname or "").lower() in HOSTS


def status_id(url: str) -> str:
    """The post this address names, or "" — `/<handle>/status/<id>`, `/i/status/<id>` and
    `/i/web/status/<id>`, with anything after the id (`/photo/1`) ignored."""
    if not is_x(url):
        return ""
    steps = [step for step in urlparse(url).path.split("/") if step]
    for at, step in enumerate(steps[:-1]):
        if step in ("status", "statuses") and _ID.match(steps[at + 1]):
            return steps[at + 1]
    return ""


def home_url(url: str) -> str:
    """The post's one canonical address, or "" for anything that names no post."""
    found = status_id(url)
    return f"{HOME}{found}" if found else ""


def _radix(value: float, base: int) -> str:
    """`Number.prototype.toString(base)` for a positive number, as V8 writes it: the
    fraction digit by digit until the next digit is below the double's own precision,
    rounded half to even with the carry run back through the digits already written.
    Checked against node on three thousand ids when it was written."""
    integer = math.floor(value)
    fraction = value - integer
    delta = max(0.5 * (math.nextafter(value, math.inf) - value), math.nextafter(0.0, 1.0))
    digits: list[str] = []
    if fraction >= delta:
        while True:
            fraction *= base
            delta *= base
            digit = int(fraction)
            digits.append(_DIGITS[digit])
            fraction -= digit
            if (fraction > 0.5 or (fraction == 0.5 and digit & 1)) and fraction + delta > 1:
                while True:
                    if not digits:
                        integer += 1
                        break
                    last = _DIGITS.index(digits.pop())
                    if last + 1 < base:
                        digits.append(_DIGITS[last + 1])
                        break
                break
            if fraction < delta:
                break
    whole: list[str] = []
    rest = float(integer)
    while True:
        remainder = math.fmod(rest, base)
        whole.append(_DIGITS[int(remainder)])
        rest = (rest - remainder) / base
        if rest <= 0:
            break
    written = "".join(reversed(whole))
    return f"{written}.{''.join(digits)}" if digits else written


def token(post: str) -> str:
    """The number X's embed widget sends beside a post's id (see the module's note)."""
    if not _ID.match(post):
        raise ValueError(f"not a post id: {post!r}")
    return re.sub(r"(0+|\.)", "", _radix(int(post) / 1e15 * math.pi, 36))


@dataclass(frozen=True)
class Picture:
    url: str
    width: int
    height: int


@dataclass(frozen=True)
class Post:
    """One post, as the endpoint tells it."""

    id: str
    handle: str
    name: str
    #: The author's picture on `MEDIA_HOST`, or "".
    avatar: str
    #: What the post says, as displayed: a reply's leading mentions and the links to its
    #: own photos taken off, and every shortened link written out as where it goes.
    text: str
    #: ISO 8601 in UTC, or "".
    posted: str
    pictures: tuple[Picture, ...] = ()
    #: The post this one answers, and its author's handle; "" where it answers none.
    parent: str = ""
    parent_handle: str = ""
    #: How many replies the post has, anybody's; -1 where the answer did not say.
    replies: int = -1


def on_media_host(address: str) -> bool:
    parsed = urlparse(address)
    return parsed.scheme == "https" and (parsed.hostname or "").lower() == MEDIA_HOST


def read(data: dict[str, Any]) -> Post | None:
    """A `tweet-result` answer, read; None for a tombstone, an empty answer, or anything
    that is not a post."""
    if not isinstance(data, dict) or data.get("__typename") not in (None, "Tweet"):
        return None
    ident = str(data.get("id_str") or "")
    user = data.get("user") or {}
    handle = str(user.get("screen_name") or "")
    if not _ID.match(ident) or not handle:
        return None
    avatar = str(user.get("profile_image_url_https") or "")
    # The address names the smallest size; the same picture at 200 is what a disc of 48
    # at 2x wants.
    avatar = avatar.replace("_normal.", "_200x200.") if on_media_host(avatar) else ""
    pictures = tuple(
        Picture(str(photo.get("url")), int(photo.get("width") or 0), int(photo.get("height") or 0))
        for photo in data.get("photos") or []
        if on_media_host(str(photo.get("url") or ""))
    )
    parent = data.get("parent") or {}
    return Post(
        id=ident,
        handle=handle,
        name=str(user.get("name") or ""),
        avatar=avatar,
        text=_displayed(data),
        posted=_when(str(data.get("created_at") or "")),
        pictures=pictures,
        parent=str(data.get("in_reply_to_status_id_str") or parent.get("id_str") or ""),
        parent_handle=str(
            data.get("in_reply_to_screen_name")
            or (parent.get("user") or {}).get("screen_name")
            or ""
        ),
        replies=_count(data.get("conversation_count")),
    )


def _count(said: object) -> int:
    try:
        count: int = int(said)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return -1
    return max(-1, count)


def _displayed(data: dict[str, Any]) -> str:
    """The part of a post's text X displays, with its links written out."""
    text = str(data.get("text") or "")
    shown = data.get("display_text_range") or []
    if len(shown) == 2 and all(isinstance(n, int) for n in shown):
        text = text[shown[0] : shown[1]]
    entities = data.get("entities") or {}
    for link in entities.get("urls") or []:
        short, full = str(link.get("url") or ""), str(link.get("expanded_url") or "")
        if short and full:
            text = text.replace(short, full)
    for media in entities.get("media") or []:
        if short := str(media.get("url") or ""):
            text = text.replace(short, "")
    text = html.unescape(text).strip()
    # A post longer than a post is cut short by the endpoint, which says so and gives no
    # more. What it gives is kept, marked as going on, rather than passed off as whole.
    if data.get("note_tweet") and not text.endswith("…"):
        text += "…"
    return text


def _when(stamp: str) -> str:
    from datetime import UTC, datetime

    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(post: str) -> dict[str, Any]:
    """One post's answer, through the guarded door every page is fetched through."""
    from .url import fetch as fetch_page

    answer = fetch_page(SYNDICATION, {"id": post, "lang": "en", "token": token(post)})
    try:
        data = json.loads(answer.text)
    except json.JSONDecodeError as error:
        raise TargumError("X answered with something that is not a post.") from error
    return data if isinstance(data, dict) else {}


@dataclass(frozen=True)
class Thread:
    """A thread as far as X would show it, oldest first."""

    posts: list[Post]
    #: Whether some of it may not be here: the walk hit `MOST`, or the last post kept has
    #: replies and the author's timeline showed none of theirs. False only where the last
    #: post kept has no reply at all, which is the one proof a thread ends there.
    more: bool = False


def thread(url: str) -> Thread:
    """The post this address names and the rest of its author's thread around it: back to
    where the thread starts, then on through the author's own replies as far as their
    timeline shows. Raises `TargumError` for an address that names no post and for a post
    X will not show."""
    first = status_id(url)
    if not first:
        raise TargumError(
            "We can take one post at a time.",
            "Paste the address of a single post.",
            key="x.one-post",
        )
    found = read(fetch(first))
    if found is None:
        raise TargumError(
            "X wouldn't show us that post.",
            "It may be deleted, private or age-restricted. Copy its words and paste them here.",
            key="x.not-shown",
        )
    earlier = [found]
    while len(earlier) < MOST and found.parent and _same(found.parent_handle, found.handle):
        try:
            parent = read(fetch(found.parent))
        except TargumError:
            break
        if parent is None or not _same(parent.handle, found.handle):
            break
        earlier.append(parent)
        found = parent
    posts = list(reversed(earlier))
    capped = len(posts) >= MOST
    if not capped and posts[-1].replies != 0:
        posts = _onward(posts)
        capped = len(posts) >= MOST
    return Thread(posts, more=capped or posts[-1].replies != 0)


def _onward(posts: list[Post]) -> list[Post]:
    """The author's own replies after the last post, one after another, as far as their
    timeline shows them. A reply by anybody else breaks the chain by itself: the author's
    next post would answer that one, not theirs."""
    author = posts[0].handle
    after: dict[str, str] = {}
    for entry in timeline(author):
        user = (entry.get("user") or {}).get("screen_name") or ""
        answers = str(entry.get("in_reply_to_status_id_str") or "")
        replying_to = str(entry.get("in_reply_to_screen_name") or "")
        ident = str(entry.get("id_str") or "")
        if _same(user, author) and _same(replying_to, author) and answers and _ID.match(ident):
            after.setdefault(answers, ident)
    kept = list(posts)
    while len(kept) < MOST and (following := after.get(kept[-1].id)):
        try:
            found = read(fetch(following))
        except TargumError:
            break
        if found is None or not _same(found.handle, author) or found.parent != kept[-1].id:
            break
        kept.append(found)
    return kept


#: The author's timeline as X's embedded-timeline widget reads it, logged out. Measured on
#: 2026-09-27: a page whose `__NEXT_DATA__` carries `props.pageProps.timeline.entries`, each
#: a post with `in_reply_to_status_id_str` and `conversation_id_str`. What it holds is not
#: the whole timeline: about twenty of the latest posts for one account, a hundred of the
#: most-engaged for another, replies among them only as those happen to be. And it is
#: counted: thirty requests a quarter of an hour from one address.
TIMELINE = "https://syndication.twitter.com/srv/timeline-profile/screen-name/{handle}"

#: A handle as X allows one, and so the only thing put into `TIMELINE`'s path.
_HANDLE = re.compile(r"^[A-Za-z0-9_]{1,15}$")
_NEXT = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


def timeline(handle: str) -> list[dict[str, Any]]:
    """The posts X's timeline widget shows for this account, or [] — quietly, because a
    timeline that will not answer only means the thread stops at what was already found."""
    from .url import fetch as fetch_page

    if not _HANDLE.match(handle):
        return []
    try:
        page = fetch_page(TIMELINE.format(handle=handle)).text
    except TargumError:
        return []
    return timeline_entries(page)


def timeline_entries(page: str) -> list[dict[str, Any]]:
    """The posts in a timeline page, read off its data."""
    found = _NEXT.search(page)
    if not found:
        return []
    try:
        data = json.loads(found.group(1))
        entries = data["props"]["pageProps"]["timeline"]["entries"]
    except (ValueError, KeyError, TypeError):
        return []
    return [
        dict((entry.get("content") or {}).get("tweet") or {})
        for entry in entries or []
        if isinstance(entry, dict) and entry.get("type") == "tweet"
    ]


def _same(one: str, other: str) -> bool:
    return bool(one) and one.lower() == other.lower()


def text_of(posts: list[Post]) -> str:
    """The thread as a text targum reads: front matter naming the title and the author,
    then each post's lines, a line a paragraph (#158's rule 1), in order."""
    lines = [line for post in posts for line in lines_of(post.text)]
    first = posts[0]
    title = (lines[0][:120].strip() if lines else "") or f"Post by @{first.handle}"
    head = ["---", f"title: {title}", f"author: @{first.handle}", "---", ""]
    return "\n".join([*head, "\n\n".join(lines), ""])


__all__ = [
    "ENV",
    "HOME",
    "HOSTS",
    "MEDIA_HOST",
    "MOST",
    "SYNDICATION",
    "Picture",
    "Post",
    "TIMELINE",
    "Thread",
    "fetch",
    "home_url",
    "is_open",
    "is_x",
    "read",
    "status_id",
    "text_of",
    "thread",
    "timeline",
    "timeline_entries",
    "token",
]
