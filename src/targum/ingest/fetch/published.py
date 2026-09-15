"""A published translation held as a file of verses, paired with Sefaria's Hebrew by verse.

    published:ru:Genesis

Some translations worth reading beside the Hebrew exist only as scans: the Russian Torah
of Gerstein & Gordon (Vilna, 1875, public domain) is one, read off the page twice and
checked by a person (targum-internal#187). What comes out of that work is a file of verses
keyed the way Sefaria names them, `{"Genesis 1:1": "В начале сотворил Бог небо и землю."}`,
and this turns one book of it into the document Sefaria's own renderings are: a heading per
chapter, a verse block per verse, every verse carrying its ref. That shape is what
`align/parallel.py` pairs by construction, so the published text sits beside the Hebrew
verse for verse and nothing is bought or guessed.

The files are content, not code, and live where the catalogue does
(`catalogue.json`'s rule): the first of `TARGUM_PUBLISHED`, `~/.targum/published`,
`/etc/targum/published`, holding `<language>.json` as
`{"title": …, "verses": {"Genesis 1:1": …}}`.
"""

from __future__ import annotations

import json
import os
import re
from functools import cache
from pathlib import Path
from typing import Any

from ...errors import TargumError
from ...ids import block_id
from ...models import BlockKind, Document
from ..base import Paragraph, blocks_from_paragraphs, build_document, normalize

_REF = re.compile(r"^(?P<book>.+?) (?P<chapter>\d+):(?P<verse>\d+)$")


def home() -> Path | None:
    """Where the published files are, or None on a machine that has none."""
    named = os.environ.get("TARGUM_PUBLISHED")
    places = [Path(named)] if named else []
    places += [Path.home() / ".targum" / "published", Path("/etc/targum/published")]
    return next((place for place in places if place.is_dir()), None)


@cache
def edition(language: str) -> dict[str, Any]:
    """One language's published file, as read."""
    where = home()
    path = where / f"{language}.json" if where else None
    if path is None or not path.is_file():
        raise TargumError(
            f"No published {language} translation on this machine.",
            "Put it at ~/.targum/published/<language>.json or name the folder in TARGUM_PUBLISHED.",
        )
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def split(identifier: str) -> tuple[str, str]:
    """`published:ru:Genesis` -> ("ru", "Genesis")."""
    rest = (
        identifier.split(":", 1)[1] if identifier.lower().startswith("published:") else identifier
    )
    language, sep, book = rest.partition(":")
    if not sep or not language.isalpha() or not book.strip():
        raise TargumError(
            "A published translation names its language and its book.", "Try: published:ru:Genesis"
        )
    return language.lower(), book.replace("_", " ").strip()


def document_for(language: str, book: str, verses: dict[str, str], title: str) -> Document:
    """One book's verses as Sefaria's renderings are shaped: every chapter from the first
    to the last, every verse from the first to the last in its chapter, an empty one kept
    as "—" so the two sides count the same."""
    chapters: dict[int, dict[int, str]] = {}
    for ref, text in verses.items():
        found = _REF.match(ref)
        if found and found.group("book") == book:
            chapters.setdefault(int(found.group("chapter")), {})[int(found.group("verse"))] = text
    if not chapters:
        raise TargumError(f"The published {language} translation has no {book}.")
    paragraphs: list[Paragraph] = []
    refs: dict[int, str] = {}
    for number in range(1, max(chapters) + 1):
        paragraphs.append((BlockKind.heading, 2, f"{book} {number}"))
        held = chapters.get(number, {})
        for count in range(1, (max(held) if held else 0) + 1):
            refs[len(paragraphs)] = f"{book} {number}:{count}"
            paragraphs.append(
                (BlockKind.verse, None, normalize(held.get(count, "")).strip() or "—")
            )
    blocks = blocks_from_paragraphs(paragraphs)
    by_id = {block_id(index): ref for index, ref in refs.items()}
    for block in blocks:
        block.ref = by_id.get(block.id, "")
    return build_document(
        f"published:{language}:{book}",
        blocks,
        ingester=PublishedFetcher.name,
        language=language,
        title=f"{title}, {book}" if title else book,
    )


class PublishedFetcher:
    name = "published/1"

    def load(self, identifier: str) -> Document:
        language, book = split(identifier)
        held = edition(language)
        return document_for(
            language, book, dict(held.get("verses") or {}), str(held.get("title") or "")
        )
