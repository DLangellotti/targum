"""Which video addresses targum will read, and the one shape each is written in.

The front door's mediums list has always named Reels, Shorts and TikToks. Only YouTube
was ever wired up (`video/youtube.py`), so two thirds of that line was untrue — see
targum-internal#255.

**A closed list, and that is the point.** `youtube.HOSTS` says it plainly: yt-dlp "would
happily fetch a thousand other sites, and each of those is a decision nobody made." This
adds five decisions, one host at a time, and nothing else comes with them.

**Each host needs three things and gets no further.** Whether an address is one of its
videos; the id of that video; and the single canonical address the reader's page links
home to. That last one is why a host cannot simply be added to a set: `tests/test_render`
pins outbound links *by prefix*, so every host must reduce every spelling of a video to
one prefix — the way `youtube.WATCH` does — or the allowlist means nothing.

**Named is not open.** `KNOWN` is every host whose addresses targum can read; `OPEN` is
the ones a platform has actually answered for, from the box, through the egress. Tested
2026-09-17 and 2026-09-18 (targum-internal#255):

* **YouTube** — open since #126, through the residential proxy.
* **Instagram** — open. A public reel answered `yt-dlp -J` five times of five from the box
  through the proxy, logged out, no cookies; the "empty media response" of the day before
  did not come back. `video/instagram.py` is its door.
* **TikTok** — open, direct and not through the proxy, which it refuses with a 403.
  Four public videos and five runs in a row answered from the box on 2026-09-18.
  `video/tiktok.py` is its door.
* **Vimeo, Reddit** — want a logged-in account, which a proxy cannot give.
* **Facebook** — untested with a real address.

A host moves from one list to the other only with a measurement like those, and the rest
are named so the refusal can say what to do instead of pretending not to recognise them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from ..errors import TargumError


@dataclass(frozen=True)
class Host:
    """One video service targum will read from."""

    #: What the reader is told it is, in the one line the Add box says back to them.
    name: str
    #: The hostnames that are plainly this service's.
    hosts: frozenset[str]
    #: The canonical address a video of this service lives at, with the id appended.
    #: One prefix per host, because the outbound allowlist is a prefix.
    home: str
    #: Path shapes that carry a video id, and where in the path it sits.
    paths: tuple[str, ...] = ()
    #: A path that is somebody's whole shelf rather than one video.
    shelves: tuple[str, ...] = ()


#: The id in a path like `/video/7123…` or `/p/Cx3…/`: the last step that looks like an
#: id rather than a word. Deliberately strict — a path segment of punctuation is not an
#: id, and neither is an empty one.
ID = re.compile(r"^[A-Za-z0-9_-]{5,}$")

YOUTUBE = Host(
    name="YouTube",
    hosts=frozenset(
        {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
    ),
    home="https://www.youtube.com/watch?v=",
    paths=("/watch", "/shorts/", "/live/"),
    shelves=("/playlist", "/feed", "/channel", "/@", "/c/", "/user/"),
)

VIMEO = Host(
    name="Vimeo",
    hosts=frozenset({"vimeo.com", "www.vimeo.com", "player.vimeo.com"}),
    # Numeric ids, and the canonical page is the bare number under the domain.
    home="https://vimeo.com/",
    paths=("/",),
    shelves=("/channels", "/groups", "/ondemand", "/categories"),
)

TIKTOK = Host(
    name="TikTok",
    hosts=frozenset(
        {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}
    ),
    # `/@someone/video/<id>` is the shape that survives sharing; the short `vm.` links
    # redirect to it, and a redirect is yt-dlp's to follow rather than ours to guess.
    # The account may be left empty — `/@/video/<id>` opens the video — and must be,
    # because one prefix is the whole allowlist. `/video/<id>` without the `@` is a 404
    # (checked 2026-09-18).
    home="https://www.tiktok.com/@/video/",
    paths=("/video/",),
    shelves=("/tag/", "/music/", "/discover"),
)

INSTAGRAM = Host(
    name="Instagram",
    hosts=frozenset({"instagram.com", "www.instagram.com"}),
    home="https://www.instagram.com/reel/",
    paths=("/reel/", "/reels/", "/p/", "/tv/"),
    shelves=("/explore", "/stories"),
)

FACEBOOK = Host(
    name="Facebook",
    hosts=frozenset({"facebook.com", "www.facebook.com", "m.facebook.com", "fb.watch"}),
    home="https://www.facebook.com/watch/?v=",
    paths=("/watch", "/videos/", "/reel/"),
    shelves=("/groups", "/marketplace"),
)

REDDIT = Host(
    name="Reddit",
    hosts=frozenset({"reddit.com", "www.reddit.com", "old.reddit.com", "v.redd.it"}),
    # A comments permalink is the shape a reader copies; the canonical form keeps the
    # post id alone, which is what identifies the video.
    home="https://www.reddit.com/comments/",
    paths=("/comments/",),
    shelves=("/r/", "/user/", "/u/"),
)

#: Where an Instagram post that is pictures lives. `/reel/<code>` opens a film and
#: nothing else, so a post keeps the `/p/` it was pasted with. A second prefix for one
#: host, pinned in `tests/test_render` beside the rest.
INSTAGRAM_POST = "https://www.instagram.com/p/"

#: Every host targum will read a video from. YouTube first, because it is the one that
#: has been proven to work end to end.
KNOWN: tuple[Host, ...] = (YOUTUBE, VIMEO, TIKTOK, INSTAGRAM, FACEBOOK, REDDIT)

#: The hosts targum fetches from. Each has its own door module, and each was measured from
#: the box before it was put here — see the module's docstring.
OPEN: tuple[Host, ...] = (YOUTUBE, INSTAGRAM, TIKTOK)

#: The prefixes a reader page may link home to. `tests/test_render` pins these. Every named
#: host's, not only the open ones: a TikTok the reader downloaded and dropped in still has
#: a home, and the link is how the page says whose film it is.
HOMES: tuple[str, ...] = (*(host.home for host in KNOWN), INSTAGRAM_POST)


def host_for(url: str) -> Host | None:
    """The service this address belongs to, or None for anything else."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    name = (parsed.hostname or "").lower()
    for host in KNOWN:
        if name in host.hosts:
            return host
    return None


def _shelf(host: Host, path: str) -> bool:
    """Whether this path is a collection rather than one video.

    Asked only *after* no video id was found, which is the whole subtlety: Reddit's
    shelf prefix is `/r/` and every valid Reddit video permalink begins `/r/<sub>/
    comments/…`. Checking first refused every one of them. A path that yields an id is a
    video whatever else it looks like; a path that yields none and looks like a shelf is
    a reader to talk to.
    """
    return path.startswith(host.shelves) if host.shelves else False


def video_id(url: str) -> str:
    """The video's own id, or "" where the address does not name one.

    Raises `TargumError` for an address that names a collection: that is a reader to
    talk to, not a URL to reject silently.
    """
    host = host_for(url)
    if host is None:
        return ""
    found = _id_in(host, url)
    if found:
        return found
    if _shelf(host, urlparse(url).path):
        raise TargumError(
            "We can take one video at a time.", "Paste the address of a single video."
        )
    return ""


def _id_in(host: Host, url: str) -> str:
    """The id this address carries, or "" — with no opinion about shelves."""
    parsed = urlparse(url)
    path = parsed.path
    name = (parsed.hostname or "").lower()

    if host is YOUTUBE:
        if name == "youtu.be":
            found = path.rstrip("/").rsplit("/", 1)[-1]
            return found if ID.match(found) else ""
        if path.startswith("/watch"):
            return (parse_qs(parsed.query).get("v") or [""])[0]
        if path.startswith(("/shorts/", "/live/")):
            return path.rstrip("/").rsplit("/", 1)[-1]
        return ""

    if host is VIMEO:
        # vimeo.com/76979871, player.vimeo.com/video/76979871, and an unlisted video's
        # vimeo.com/76979871/abcdef — the first number is the video.
        for step in path.strip("/").split("/"):
            if step.isdigit():
                return step
        return ""

    if host is FACEBOOK:
        if path.startswith("/watch"):
            return (parse_qs(parsed.query).get("v") or [""])[0]
        # /<page>/videos/<id> and /reel/<id>
        steps = [s for s in path.strip("/").split("/") if s]
        for at, step in enumerate(steps):
            if step in ("videos", "reel") and at + 1 < len(steps):
                return steps[at + 1]
        # fb.watch/<id>
        if name == "fb.watch":
            found = path.strip("/")
            return found if ID.match(found) else ""
        return ""

    if host is REDDIT:
        # /r/<sub>/comments/<id>/<slug> — the id follows "comments". `v.redd.it/<id>` is
        # the media host and carries the id alone.
        if name == "v.redd.it":
            found = path.strip("/")
            return found if ID.match(found) else ""
        steps = [s for s in path.strip("/").split("/") if s]
        if "comments" in steps:
            at = steps.index("comments")
            if at + 1 < len(steps):
                return steps[at + 1]
        return ""

    # TikTok and Instagram: the id is the step after the shape word.
    steps = [s for s in path.strip("/").split("/") if s]
    for want in host.paths:
        word = want.strip("/")
        if word in steps:
            at = steps.index(word)
            if at + 1 < len(steps) and ID.match(steps[at + 1]):
                return steps[at + 1]
    return ""


def is_video(url: str) -> bool:
    """Whether this address names one video on a host targum reads."""
    return bool(video_id(url))


def home_url(url: str) -> str:
    """The canonical address of the video this one names, or "".

    What the reader's page links home to. One shape for every spelling, so the page's
    one outbound address is the prefix the allowlist pins.
    """
    host = host_for(url)
    if host is None:
        return ""
    try:
        found = video_id(url)
    except TargumError:
        return ""
    if found and host is INSTAGRAM and "p" in urlparse(url).path.split("/"):
        return f"{INSTAGRAM_POST}{found}"
    return f"{host.home}{found}" if found else ""


def is_open(url: str) -> bool:
    """Whether targum fetches from the host this address belongs to."""
    return host_for(url) in OPEN


def named(url: str) -> str:
    """What to call the service in a line said to the reader, or ""."""
    host = host_for(url)
    return host.name if host else ""
