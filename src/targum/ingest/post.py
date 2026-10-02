"""A post, kept as a post: `post.json` beside the reader (targum-internal#158).

A post from Instagram — and from X, TikTok and Facebook, whose doors have opened since —
has a shape a paragraph does not: who wrote it, when, and which pictures sat where. The
text path reads its caption like any other text, and until this nothing kept the rest, so
a post came back as three paragraphs with a title. design.md §12, "A post keeps its
shape" (2026-09-27), says how it is drawn; this is what is kept for the drawing.

**Beside the reader, like `audio.json`**, and not a change to `Document`: no cache key
moves and nothing is re-translated. A folder without one is a plain text reader, and
deleting it returns a post's folder to one.

**Nothing is fetched to draw it.** The pictures are kept in the folder as webp at a long
edge of `LONG_EDGE`, as covers are, and the author's own picture at `AVATAR_EDGE`.

**The three licence fields are always "", false, false for a post.** A post is its
author's, with no licence granted. They are here because the 2026-09-01 corpus decision
asked every source to carry them, and a post is the first source where every item is
unknown-licensed.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..paths import write_atomic

log = logging.getLogger(__name__)

NAME = "post.json"

#: The platforms a post may come from. An enum rather than free text, so a card can draw
#: each one it knows and refuse one it does not. Facebook since 2026-09-30, for its
#: videos: a pasted one arrives as a post, as a TikTok does.
PLATFORMS = ("instagram", "x", "tiktok", "facebook")

#: The platforms the Add page's form takes a post by hand from. Not Facebook's yet: most
#: of what is posted there is words, at addresses the host table does not read, so the
#: form would refuse the link to nearly every Facebook post a reader brought.
BROUGHT_FROM = ("instagram", "x", "tiktok")

#: How a post reached targum. `paste`: a link the reader pasted, fetched by the box when
#: they pressed (the hosted door, open since targum#304). `cli`: the command line on the
#: reader's own machine. `brought`: the reader typed the post and brought its pictures.
#: #158 was written when the hosted paste was refused, and named only the last two.
FETCHED_BY = ("paste", "cli", "brought")

#: A kept picture's long edge, in pixels. What a phone at 2x draws a full-width picture
#: at, and the ceiling #158 set.
LONG_EDGE = 1280

#: The author's picture, which the card draws as a small disc: twice its 48px at 2x.
AVATAR_EDGE = 96

#: A handle as the three platforms write one: Instagram's thirty letters, digits, dots
#: and underscores hold TikTok's and X's too. A brought post's handle is typed by the
#: reader, and it is drawn after an `@` in the head, so it is held to the one shape.
HANDLE = re.compile(r"[A-Za-z0-9._]{1,30}")

#: The most a brought post's words may be. X's longest post is 25,000 characters and a
#: caption 2,200; ten thousand is a long post and not yet an article, which the box
#: above the form takes as a text.
TEXT_MOST = 10_000

#: A brought post's title where its first line will not do, as the pasted post's is.
TITLE_MOST = 80


@dataclass(frozen=True)
class Media:
    #: `image`, kept as webp under `post/`; or `video`, which is the recording's own cut
    #: named by the audio manifest and never a copy of it.
    kind: str
    #: Relative to the reader's folder.
    path: str
    width: int
    height: int
    alt: str = ""


@dataclass(frozen=True)
class Author:
    handle: str
    name: str = ""
    #: Their own picture, kept small beside the reader, relative to its folder; "" where
    #: the platform's page did not give one and the card draws their first letter.
    avatar: str = ""


@dataclass(frozen=True)
class Item:
    """One post. A thread is one item per post, in order; a single post is one item."""

    block_ids: list[str]
    media: list[Media] = field(default_factory=list)
    #: `post`: a post's own text and pictures. A film is two items (#158's rule 7): the
    #: `clip`, whose text is its transcript and whose media is the film, and the `caption`
    #: the author typed, which is a separate item's text drawn under it.
    kind: str = "post"
    #: None where the item is the thread's author's own; a reply by another account
    #: carries its own.
    author: Author | None = None


@dataclass(frozen=True)
class Manifest:
    platform: str
    author: Author
    items: list[Item]
    fetched_by: str = "paste"
    #: Whether some of a thread may not be here: X shows a thread only in part to
    #: somebody signed out (`ingest.x.Thread.more`), and the card says so.
    more: bool = False
    #: The post's own address, or None where the reader brought it without one.
    url: str | None = None
    #: ISO 8601, or "" where the platform's page did not say.
    posted_at: str = ""
    fetched_at: str = ""
    licence: str = ""
    reader_publishable: bool = False
    corpus_exportable: bool = False

    def __post_init__(self) -> None:
        if self.platform not in PLATFORMS:
            raise ValueError(f"not a platform a post comes from: {self.platform!r}")
        if self.fetched_by not in FETCHED_BY:
            raise ValueError(f"not a way a post arrives: {self.fetched_by!r}")


def write(folder: Path, manifest: Manifest) -> Path:
    """Write `post.json` into a reader's folder, whole or not at all."""
    body = asdict(manifest)
    if not body["fetched_at"]:
        body["fetched_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    # The three licence fields are what they are for every post, whatever a caller passed.
    body.update(licence="", reader_publishable=False, corpus_exportable=False)
    return write_atomic(folder / NAME, json.dumps(body, ensure_ascii=False, indent=2) + "\n")


def read(folder: Path) -> dict[str, Any] | None:
    """A reader's post, or None where it is not one or the file is not one we wrote."""
    try:
        data = json.loads((folder / NAME).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("platform") not in PLATFORMS:
        return None
    return data


#: What in a post's text names something rather than says it: a hashtag, a mention, an
#: address. They stay where the author put them and are drawn as written, but they are
#: names, not words (design.md §12, "A post keeps its shape"): not tapped as vocabulary and
#: not counted in what a reader knows of the text. Done here, at render and count, rather
#: than in the annotator, whose name is every text's cache key (David, 2026-09-27). A
#: hashtag's letters may carry points, which are not `\w`; a mention may carry dots, but
#: never ends on one.
UNWORDLY = re.compile(
    r"(?:https?://|www\.)\S+"
    r"|#[\w\u0591-\u05c7\u05f3\u05f4]+"
    r"|@[\w.]*\w"
)


def posted_from(stamp: object) -> str:
    """A Unix time a platform gave, as ISO 8601 in UTC, or "" for anything that is not
    one — `posted_at`'s own form."""
    try:
        seconds = int(stamp)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return ""
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


#: Directional isolates and marks a platform wraps a caption's lines in, and the tabs and
#: spaces beside them.
_MARKS = "\u2066\u2067\u2068\u2069\u200e\u200f\t "


def home_of(link: str) -> tuple[str, str] | None:
    """The platform a post's own address names, and that address in its one canonical
    shape — the shape the card links home to and `test_render.py` pins — or None for an
    address that names no post on Instagram, TikTok or X. A brought post's link is typed
    by the reader, so it is kept only in that shape and never as it was typed."""
    from ..errors import TargumError
    from ..video import hosts as hosts_module
    from . import x as x_module

    found = x_module.home_url(link)
    if found:
        return "x", found
    host = hosts_module.host_for(link)
    if host is not hosts_module.INSTAGRAM and host is not hosts_module.TIKTOK:
        return None
    try:
        found = hosts_module.home_url(link)
    except TargumError:
        return None
    if not found:
        return None
    return ("instagram" if host is hosts_module.INSTAGRAM else "tiktok"), found


def brought_text(handle: str, words: str) -> str:
    """A brought post's words as a text targum reads, the way a pasted post's caption is
    (`video.instagram.caption_text`): front matter naming the title and the author, then
    a line a paragraph (#158's rule 1). The title is the first line where it is short
    enough to be one, cut at a word where it is not, and "Post by @handle" where the post
    is only pictures."""
    lines = lines_of(words)
    title = " ".join(lines[0].split()) if lines else ""
    if len(title) > TITLE_MOST:
        cut = title[: TITLE_MOST + 1]
        title = cut.rsplit(" ", 1)[0] if " " in cut else cut[:TITLE_MOST]
    title = title or f"Post by @{handle}"
    head = ["---", f"title: {title}", f"author: @{handle}", "---", ""]
    return "\n".join([*head, "\n\n".join(lines), ""])


def lines_of(caption: str) -> list[str]:
    """A caption's lines, each a paragraph (#158's rule 1: a line is how it was written),
    with the marks a platform wraps them in taken off and the blank ones left out."""
    return [kept for line in caption.splitlines() if (kept := line.strip(_MARKS))]


def unwordly(text: str) -> list[tuple[int, int]]:
    """Where the hashtags, mentions and addresses are in `text`, as (start, end)."""
    return [match.span() for match in UNWORDLY.finditer(text)]


def without_unwordly(text: str) -> str:
    """`text` with its hashtags, mentions and addresses taken out, for a count that reads
    the words and not the tokens (`level.known_share`)."""
    return UNWORDLY.sub(" ", text)


def inside(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    """Whether the word at (start, end) falls in any of `spans`. Overlap is enough: an
    annotator that took the `#` off a hashtag still found a word that is in one."""
    return any(start < stop and end > begin for begin, stop in spans)


def left_out(folder: Path) -> dict[str, list[tuple[int, int]]] | None:
    """For a post's folder, where each segment's hashtags, mentions and addresses are,
    measured in the segment's own text as the annotation's offsets are; None for a folder
    that is not a post, whose words are all counted as they always were.

    Read from `segments.json` beside the reader, so a count asked after the build needs
    nothing but the folder.
    """
    if read(folder) is None:
        return None
    from ..models import SegmentedDocument, read_artifact

    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    if segmented is None:
        return {}
    return {
        segment.id: spans for segment in segmented.segments if (spans := unwordly(segment.text))
    }


def keep_pictures(pictures: list[Path], folder: Path, first: int = 1) -> list[Media]:
    """A post's pictures, in its order, as webp under `<folder>/post/`, long edge at most
    `LONG_EDGE`. Never cropped: a 4:5 post stays 4:5 (§12). A picture that will not open
    is left out rather than failing the post; the caption is still the text. `first` is
    the number the first is kept under, so a thread's posts keep theirs apart."""
    import io

    from PIL import Image, ImageOps

    if any(Path(source).suffix.lower() in (".heic", ".heif") for source in pictures):
        # A phone's own photos, brought by hand: Pillow opens them once `pillow-heif` is
        # registered, which the picture reader does and nothing else here would.
        from ..vision import _pillow

        _pillow()
    kept = folder / "post"
    kept.mkdir(parents=True, exist_ok=True)
    media: list[Media] = []
    for n, source in enumerate(pictures, start=first):
        try:
            # Upright first: a phone stores a photo sideways with its turn in a tag, and a
            # picture brought by hand is a phone's photo more often than not.
            image = ImageOps.exif_transpose(Image.open(source))
            image.thumbnail((LONG_EDGE, LONG_EDGE), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            image.convert("RGB").save(out, format="WEBP", quality=82, method=6)
        except Exception as why:  # noqa: BLE001 - one bad picture is not a bad post
            log.warning("left a post's picture out: %s (%s)", source.name, why)
            continue
        name = f"media-{n:03d}.webp"
        (kept / name).write_bytes(out.getvalue())
        media.append(Media("image", f"post/{name}", image.width, image.height))
    return media


def keep_avatar(picture: Path, folder: Path) -> str:
    """The author's picture as a small square webp under `<folder>/post/`, or "" where it
    will not open — the card then draws their first letter."""
    import io

    from PIL import Image, ImageOps

    try:
        image = ImageOps.fit(
            Image.open(picture).convert("RGB"), (AVATAR_EDGE, AVATAR_EDGE), Image.Resampling.LANCZOS
        )
        out = io.BytesIO()
        image.save(out, format="WEBP", quality=82, method=6)
    except Exception as why:  # noqa: BLE001 - a missing face is not a missing post
        log.warning("left a post's author picture out: %s", why)
        return ""
    kept = folder / "post"
    kept.mkdir(parents=True, exist_ok=True)
    (kept / "avatar.webp").write_bytes(out.getvalue())
    return "post/avatar.webp"


__all__ = [
    "AVATAR_EDGE",
    "FETCHED_BY",
    "LONG_EDGE",
    "NAME",
    "BROUGHT_FROM",
    "PLATFORMS",
    "Author",
    "Item",
    "Manifest",
    "Media",
    "HANDLE",
    "TEXT_MOST",
    "TITLE_MOST",
    "UNWORDLY",
    "brought_text",
    "home_of",
    "inside",
    "keep_avatar",
    "keep_pictures",
    "left_out",
    "lines_of",
    "posted_from",
    "read",
    "unwordly",
    "without_unwordly",
    "write",
]
