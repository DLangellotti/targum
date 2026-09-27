"""A post, kept as a post: `post.json` beside the reader (targum-internal#158).

A post from Instagram — and from X and TikTok when their doors open — has a shape a
paragraph does not: who wrote it, when, and which pictures sat where. The text path reads
its caption like any other text, and until this nothing kept the rest, so a post came back
as three paragraphs with a title. design.md §12, "A post keeps its shape" (2026-09-27),
says how it is drawn; this is what is kept for the drawing.

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
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..paths import write_atomic

log = logging.getLogger(__name__)

NAME = "post.json"

#: The platforms a post may come from. An enum rather than free text, so a card can draw
#: each one it knows and refuse one it does not.
PLATFORMS = ("instagram", "x", "tiktok")

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


@dataclass(frozen=True)
class Media:
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


def keep_pictures(pictures: list[Path], folder: Path) -> list[Media]:
    """A post's pictures, in its order, as webp under `<folder>/post/`, long edge at most
    `LONG_EDGE`. Never cropped: a 4:5 post stays 4:5 (§12). A picture that will not open
    is left out rather than failing the post; the caption is still the text."""
    import io

    from PIL import Image

    kept = folder / "post"
    kept.mkdir(parents=True, exist_ok=True)
    media: list[Media] = []
    for n, source in enumerate(pictures, start=1):
        try:
            image = Image.open(source)
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
    "PLATFORMS",
    "Author",
    "Item",
    "Manifest",
    "Media",
    "keep_avatar",
    "keep_pictures",
    "read",
    "write",
]
