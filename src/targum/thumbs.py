"""A thumbnail for every text: its own picture where it has one, a drawn tile where not
(targum-internal#429, David 2026-10-08; design.md §12, "Every text has a picture").

Three places a picture comes from, in this order:

1. **The text's own.** An article's lead image (`og:image`), a book's cover in its EPUB,
   the first page of a PDF, the first of the pictures a reader brought, a video's frame.
   Captured once, when the text is added, and kept beside its reader as `THUMB` — in the
   reader's own home, because **a publisher's picture is kept only with the reader who
   added it** and never reaches the shared shelf. `capture` does this; it never stops a
   build, and a text with nothing of its own simply has nothing.
2. **The library's, filled in a batch.** `targum thumbs` gives each catalogue row a
   picture where its licence lets one be made: a video's own poster, a picture book's own
   cover. Saved under `thumbs/<entry id>.webp`, the directory the drawn covers already
   use, with where each came from written to `thumbs/sources.json`.
3. **Drawn, here, for nothing.** The text's first letter on a colour that says what kind
   of thing it is (`tone`): no model, no network, no file. `drawn` writes it as SVG.

Readers fetch nothing: every picture is fetched at most once, by the server, and served
from its own disk (`/thumb/<name>`) or carried inside the page as data.
"""

from __future__ import annotations

import io
import json
import logging
import posixpath
import re
import unicodedata
import zipfile
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

log = logging.getLogger(__name__)

#: An upload's own picture, beside its reader. One name whatever it was captured from,
#: so serving it is one lookup.
THUMB = "thumb.webp"

#: Where the batch writes down what each library picture is and where it came from.
SOURCES = "sources.json"

#: The fallback tile's colours, by what a text is (David, 2026-10-08; the calm-surfaces
#: board's tiles): teal news, iris sets, clay things said, muted books. Each is a working
#: cut of design.md §4 with `ON_TONE` above it at AA.
TONES = {
    "news": "#1f6f6b",
    "set": "#6b5a8e",
    "spoken": "#b4553f",
    "book": "#6b645c",
}

#: The letter on a tile: the desk's card colour, which reads on every tone above.
ON_TONE = "#fffdf9"

#: Kinds by tone. Anything not named is a book, which is what most of the shelf is.
_KIND_TONES = {
    "article": "news",
    "talk": "spoken",
    "dialogue": "set",
    "liturgy": "set",
}

#: The faces a tile's letter asks for. An SVG shown as an image cannot reach the page's
#: own fonts, so this names faces a machine has: a serif with Hebrew, Cyrillic and Latin
#: is on every system a reader uses.
_FACES = (
    "'Frank Ruhl Libre', 'Noto Sans Hebrew', 'Iowan Old Style', Georgia, 'Times New Roman', serif"
)


def tone(kind: str, register: str = "") -> str:
    """The tile colour for a text of this kind. The rabbinic shelf is sets: tractates,
    chapters of a code, a siddur's services."""
    if register == "rabbinic" and kind not in _KIND_TONES:
        return TONES["set"]
    return TONES[_KIND_TONES.get(kind, "book")]


def kind_of_upload(source: str, folder: Path) -> str:
    """What a reader's own text is, as far as its tile cares: the library's own answer
    (`Library._shape`) without the reading it does to count difficulty."""
    from .audio.manifest import keeps_video

    if source.endswith(".chat"):
        return "dialogue"
    if keeps_video(folder):
        return "talk"
    if urlparse(source).scheme in ("http", "https"):
        return "article"
    return ""


def letter(title: str) -> str:
    """The first letter of a title: not a quotation mark or a bracket. Pointing goes with
    it, because a tile is a letter and not a word."""
    for character in unicodedata.normalize("NFC", title or ""):
        if character.isalpha():
            return character.upper()
    return "?"


def drawn(title: str, kind: str = "", register: str = "", language: str = "") -> str:
    """The drawn tile, as an SVG document. Two by three, as a cover is."""
    shown = escape(letter(title))
    lang = f' xml:lang="{escape(language)}"' if language else ""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 300" width="200" height="300"'
        f'{lang} aria-hidden="true">'
        f'<rect width="200" height="300" fill="{tone(kind, register)}"/>'
        f'<text x="100" y="150" dy="0.35em" text-anchor="middle" font-family="{escape(_FACES)}"'
        f' font-size="128" fill="{ON_TONE}">{shown}</text></svg>'
    )


# -- keeping a picture -------------------------------------------------------------------


def can_keep() -> bool:
    from .covers import can_shrink

    return can_shrink()


def shrunk(image: bytes) -> bytes | None:
    """A picture down to a thumbnail's size, as WEBP, or None for anything that is not a
    picture Pillow can read. Read rather than trusted: a page's `og:image` can name
    anything, and what comes back is checked by decoding it, not by what it said it was."""
    if not image:
        return None
    try:
        from PIL import Image

        from .covers import shrink

        with Image.open(io.BytesIO(image)) as opened:
            opened.verify()
        return shrink(image)
    except Exception:  # noqa: BLE001 - anything Pillow cannot read is not a picture
        return None


def keep(image: bytes, target: Path) -> bool:
    """Shrink `image` and write it to `target` whole, or write nothing."""
    small = shrunk(image)
    if small is None:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.part")
    partial.write_bytes(small)
    partial.replace(target)
    return True


# -- the text's own picture --------------------------------------------------------------


_IMAGE_META = (
    ("property", "og:image:secure_url"),
    ("property", "og:image"),
    ("name", "og:image"),
    ("name", "twitter:image"),
    ("property", "twitter:image"),
    ("name", "twitter:image:src"),
)


def page_image(html: str, base: str) -> str:
    """The picture a page names as its own, as an absolute https address, or "".

    `og:image` first, which is what a publisher sets for exactly this, then the Twitter
    card's, then `link rel=image_src`. Only http(s): a `data:` or `javascript:` value is
    nothing to fetch."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    found = ""
    for attribute, value in _IMAGE_META:
        tag = soup.find("meta", attrs={attribute: value})
        content = tag.get("content") if tag is not None and hasattr(tag, "get") else None
        if isinstance(content, str) and content.strip():
            found = content.strip()
            break
    if not found:
        link = soup.find("link", attrs={"rel": "image_src"})
        href = link.get("href") if link is not None and hasattr(link, "get") else None
        found = href.strip() if isinstance(href, str) else ""
    if not found:
        return ""
    absolute = urljoin(base, found)
    return absolute if urlparse(absolute).scheme in ("http", "https") else ""


def epub_cover(path: Path) -> bytes | None:
    """The cover an EPUB declares: `properties="cover-image"` (EPUB 3), the item a
    `<meta name="cover">` names (EPUB 2), or an image item called cover."""
    from .ingest.epub import _soup

    try:
        with zipfile.ZipFile(path) as archive:
            container = _soup(archive.read("META-INF/container.xml").decode("utf-8", "replace"))
            rootfile = container.find("rootfile")
            opf_name = rootfile.get("full-path") if rootfile is not None else None
            if not isinstance(opf_name, str):
                return None
            opf = _soup(archive.read(opf_name).decode("utf-8", "replace"))
            base = posixpath.dirname(opf_name)
            images: dict[str, str] = {}
            chosen = ""
            for item in opf.find_all("item"):
                kind = str(item.get("media-type") or "").lower()
                href = str(item.get("href") or "")
                if not kind.startswith("image/") or not href:
                    continue
                where = posixpath.normpath(posixpath.join(base, unquote(href)))
                images[str(item.get("id") or "")] = where
                if "cover-image" in str(item.get("properties") or "").split():
                    chosen = where
            if not chosen:
                meta = opf.find("meta", attrs={"name": "cover"})
                named = meta.get("content") if meta is not None else None
                chosen = images.get(str(named or ""), "")
            if not chosen:
                chosen = next(
                    (where for key, where in images.items() if "cover" in key.lower()), ""
                )
            return archive.read(chosen) if chosen else None
    except (zipfile.BadZipFile, KeyError, OSError):
        return None


def pdf_first_page(path: Path) -> bytes | None:
    """A PDF's first page as a PNG, where PyMuPDF is installed (the `bring` extra)."""
    import importlib

    try:
        # As `Any`, the way `ingest.pdf._pymupdf` holds it: the library ships no types.
        pymupdf: Any = importlib.import_module("pymupdf")
    except ImportError:
        return None
    try:
        with pymupdf.open(path) as document:
            if document.page_count < 1:
                return None
            image: bytes = document[0].get_pixmap(dpi=72).tobytes("png")
            return image
    except Exception:  # noqa: BLE001 - a PDF PyMuPDF cannot draw has no first page
        return None


def _post_picture(folder: Path) -> bytes | None:
    """The first picture of a post a reader brought, which is already beside its reader."""
    from .ingest import post as post_module

    manifest = post_module.read(folder)
    for item in (manifest or {}).get("items") or []:
        for media in item.get("media") or []:
            if media.get("kind") != "image" or not media.get("path"):
                continue
            try:
                found = (folder / str(media["path"])).resolve()
                found.relative_to(folder.resolve())
                return found.read_bytes()
            except (OSError, ValueError):
                return None
    return None


def _from_link(source: str) -> bytes | None:
    """An article's `og:image`, read off the page the build has just read (held for ten
    minutes by `url.page`, so this is not a second fetch of it) and fetched once through
    the same door as the page."""
    from .ingest import url as url_module

    got = url_module.page(source)
    if got.via == "feed" or not got.is_html:
        return None
    image = page_image(got.text, source)
    if not image:
        return None
    return url_module.fetch(image).raw or None


def own_picture(source: str, folder: Path) -> bytes | None:
    """The picture a text brought with it, or None."""
    from .ingest import picture as picture_module

    from_post = _post_picture(folder)
    if from_post:
        return from_post
    if urlparse(source).scheme in ("http", "https"):
        return _from_link(source)
    path = Path(source)
    if not path.exists():
        return None
    suffix = path.suffix.lower()
    if suffix == ".epub":
        return epub_cover(path)
    if suffix == ".pdf":
        return pdf_first_page(path)
    if picture_module.is_pictures(source):
        pages = picture_module.pages_of(source)
        return pages[0].read_bytes() if pages else None
    return None


def capture(source: str, folder: Path) -> bool:
    """Keep an upload's own picture beside its reader, once, and say whether it has one.

    Best effort, like a video's poster: a page with no `og:image`, a host that refuses
    the picture, a file Pillow cannot read — each leaves the text to the drawn tile and
    never fails the build that asked. Never for a library text: those are the batch's,
    and their pictures are chosen by licence (`targum thumbs`).
    """
    from . import catalogue as catalogue_module

    target = folder / THUMB
    if target.is_file():
        return True
    if catalogue_module.matching(source) is not None or not can_keep():
        return False
    try:
        image = own_picture(source, folder)
    except Exception as error:  # noqa: BLE001 - a picture is never worth a failed build
        log.info("thumb: nothing kept for %s: %s", source, error)
        return False
    return bool(image) and keep(image or b"", target)


# -- the library's batch -----------------------------------------------------------------


#: YouTube's own poster for a video, the size the shelf keeps. The `mq` cut is 16:9 with
#: no letterbox bars, where `hq` has them.
YOUTUBE_POSTER = "https://i.ytimg.com/vi/{id}/mqdefault.jpg"
STORYWEAVER_STORY = "https://storyweaver.org.in/api/v1/stories/{id}"
GSN_IMAGEBANK = "https://raw.githubusercontent.com/global-asp/gsn-imagebank/master/{number}/01.jpg"
GSN_LICENCES = "https://raw.githubusercontent.com/global-asp/gsn-imagebank/master/README.md"

_GSN_ROW = re.compile(r"^\s*(\d{4})\s*\|.*\|\s*\[([^\]]+)\]\(([^)]+)\)\s*$")


def gsn_licences(readme: str) -> dict[str, str]:
    """The Global Storybooks image bank's licence for each story's pictures, by number.

    The bank keeps its own table, and it is not the text's: a story whose words are CC BY
    can have NonCommercial pictures, so the picture is checked against this and never
    assumed from the row."""
    found: dict[str, str] = {}
    for line in readme.splitlines():
        row = _GSN_ROW.match(line)
        if row:
            number, family, url = row.groups()
            version = re.search(r"/(\d\.\d)/", url)
            found[number] = f"CC {family}" + (f" {version.group(1)}" if version else "")
    return found


def may_show(licence: str) -> bool:
    """Whether a picture under these terms may be shrunk and shown on the shared shelf:
    derivatives allowed and no NonCommercial term."""
    from .licensing import Standing, verdict

    said = verdict(licence)
    return said.derivatives and said.standing in (Standing.free, Standing.owed)


def remote_picture(entry: Any, fetch: Any, gsn: dict[str, str]) -> tuple[str, str, str] | None:
    """Where the library's own picture of `entry` is, its licence, and what it is, or None
    where the row has none this may fetch.

    Three kinds of row have a picture of their own that their licence covers: a video's
    poster, a StoryWeaver book's cover, and a Storybooks Canada story's first page from
    the image bank. Anything else is either a page of text with no picture (Sefaria, Ben
    Yehuda, Wikisource, the scenes) or a publisher's article, whose picture is not ours to
    put on a shared shelf whatever the article's own terms are.
    """
    scheme, _, rest = entry.source.partition(":")
    if scheme == "video" and rest and may_show(entry.licence):
        return YOUTUBE_POSTER.format(id=rest), entry.licence, "video poster"
    if scheme == "storyweaver" and rest.isdigit() and may_show(entry.licence):
        story = json.loads(fetch(STORYWEAVER_STORY.format(id=rest)).text)
        sizes = ((story.get("data") or {}).get("coverImage") or {}).get("sizes") or []
        wide = [size for size in sizes if isinstance(size, dict) and size.get("url")]
        if not wide:
            return None
        # The smallest at least as wide as what is kept, or the largest there is.
        wide.sort(key=lambda size: float(size.get("width") or 0))
        pick = next((size for size in wide if float(size.get("width") or 0) >= 320), wide[-1])
        return str(pick["url"]), entry.licence, "book cover"
    if scheme == "globalstorybooks":
        site, _, tail = rest.partition("/")
        number = tail.split("/")[0]
        licence = gsn.get(number, "")
        if site == "sbc" and licence and may_show(licence):
            return GSN_IMAGEBANK.format(number=number), licence, "book cover"
    return None


def read_sources(where: Path) -> dict[str, dict[str, str]]:
    try:
        data = json.loads((where / SOURCES).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def has_picture(where: Path, name: str) -> bool:
    return any((where / f"{name}{suffix}").is_file() for suffix in (".webp", ".png", ".jpg"))
