"""Turning a source into a normalized Document."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from typing import Protocol

from ..ids import block_id
from ..models import Block, BlockKind, Document

# Enough to tell the v1 languages apart without a detection dependency. Anything else
# falls back to English, and --from overrides it.
_SCRIPT_RANGES: list[tuple[str, range]] = [
    ("he", range(0x0590, 0x0600)),
    ("ru", range(0x0400, 0x0530)),
    ("ar", range(0x0600, 0x0700)),
]


Paragraph = tuple[BlockKind, int | None, str]

# A chapter marker on a line of its own. Gutenberg and most plain-text editions write
# these as bare numerals or roman numerals, which carry no markup at all. Without
# recognising them, structural alignment has nothing to anchor on.
_CHAPTER = re.compile(
    r"^(?:(?:chapter|part|book|глава|часть|פרק)\s+)?"
    r"(?:[IVXLC]{1,7}|\d{1,3}|[\u0590-\u05EA]{1,3})\.?$",
    re.I,
)
_MAX_HEADING_WORDS = 8


def with_front_matter(
    paragraphs: list[Paragraph], title: str | None, author: str | None
) -> list[Paragraph]:
    """Put the title and the byline into the text itself.

    A headline is part of what you are reading, not a label on the window, and it
    should be translated and tappable like everything else. Every source does this the
    same way so a news article and a novel come out with the same shape.
    """
    out = list(paragraphs)
    own_title = next(
        (i for i, (kind, level, _) in enumerate(out) if kind is BlockKind.heading and level == 1),
        None,
    )
    if title and own_title is None:
        out.insert(0, (BlockKind.heading, 1, title))
        own_title = 0
    if author:
        # Under the title where there is one, at the top otherwise.
        out.insert(0 if own_title is None else own_title + 1, (BlockKind.byline, None, author))
    return out


def classify_plain_paragraph(chunk: str) -> Paragraph:
    """Tell a chapter marker from a paragraph in text that carries no markup.

    Gutenberg and most plain-text editions write chapter numbers as a bare line. Left
    as paragraphs they are noise, and worse, structural alignment loses the landmarks
    it anchors on.
    """
    line = " ".join(chunk.split())
    if len(line.split()) <= _MAX_HEADING_WORDS and _CHAPTER.match(line):
        return (BlockKind.heading, 2, line)
    return (BlockKind.paragraph, None, line)


def normalize(text: str) -> str:
    """NFC, and nothing else.

    Hebrew arrives in inconsistent normalization, which breaks alignment and lookup in
    ways that are miserable to debug. Niqqud is left alone: absent in most texts, and
    meaningful when present.
    """
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    return re.sub(r"[ \t ]+", " ", text)


def detect_language(text: str) -> str:
    """Guess a BCP-47 tag from the dominant script."""
    counts = dict.fromkeys((tag for tag, _ in _SCRIPT_RANGES), 0)
    latin = 0
    for char in text:
        point = ord(char)
        if not char.isalpha():
            continue
        for tag, span in _SCRIPT_RANGES:
            if point in span:
                counts[tag] += 1
                break
        else:
            if point < 0x0250:
                latin += 1
    best = max(counts, key=lambda tag: counts[tag])
    return best if counts[best] > latin else "en"


def build_document(
    source: str,
    blocks: list[Block],
    *,
    ingester: str,
    language: str | None = None,
    title: str | None = None,
    author: str | None = None,
) -> Document:
    document = Document(
        source=source,
        title=title,
        author=author,
        language=language or detect_language("\n\n".join(b.text for b in blocks)),
        blocks=blocks,
        ingester=ingester,
    )
    document.content_hash = document.recompute_hash()
    return document


def blocks_from_paragraphs(paragraphs: Sequence[Paragraph]) -> list[Block]:
    return [
        Block(id=block_id(index), kind=kind, level=level, text=text)
        for index, (kind, level, text) in enumerate(paragraphs)
        if text.strip()
    ]


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Pull a leading --- block off a file, if there is one.

    Deliberately small: title, author and language are the only keys that change what
    the reader shows, and a real YAML parser is a dependency for no gain.
    """
    if not text.startswith("---\n"):
        return {}, text
    _, _, rest = text.partition("---\n")
    block, sep, body = rest.partition("\n---")
    if not sep:
        return {}, text
    fields: dict[str, str] = {}
    for line in block.split("\n"):
        key, colon, value = line.partition(":")
        if colon and key.strip():
            fields[key.strip().lower()] = value.strip().strip("\"'")
    return fields, body.lstrip("\n")


class Ingester(Protocol):
    """Every ingester turns one kind of source into a Document."""

    @property
    def name(self) -> str:
        """Name and version. A change here re-ingests rather than looking like an edit."""

    def load(self, source: str) -> Document: ...


def to_markdown(document: Document) -> str:
    """The inverse of ingest, so a fetched text can be edited before it is built.

    The author is written as frontmatter rather than as a byline block, so reading the
    result back produces the same document.
    """
    front: list[str] = []
    if document.title:
        front.append(f"title: {document.title}")
    if document.author:
        front.append(f"author: {document.author}")
    front.append(f"language: {document.language}")

    lines = ["---", *front, "---", ""]
    for block in document.blocks:
        if block.kind is BlockKind.byline:
            continue
        if block.kind is BlockKind.heading:
            lines.append("#" * (block.level or 1) + " " + block.text)
        elif block.kind is BlockKind.blockquote:
            lines.append("> " + block.text)
        else:
            lines.append(block.text)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
