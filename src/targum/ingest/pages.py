"""A text that arrived as pages — pictures read by the model, or a PDF's own text layer.

Both hand over the same thing: for each page, its lines. This turns that into a
Document the pipeline reads like any other, and it is one place rather than two so a
screenshot and a handout come out the same shape.

A page's lines are grouped into paragraphs at blank lines, and the lines of one
paragraph are joined with a space — a printed page wraps its paragraphs, and a
segmenter given one line per wrapped line would cut every sentence at the margin.
Each block carries the page it came from as its `ref` ("p3"), which is what a
facsimile could stand on later and what the reader can show now. A block with no
Hebrew letters and some Latin ones is marked English, so the Hebrew lemmatizer leaves
it alone rather than tagging it (`annotate.base.unread`).
"""

from __future__ import annotations

import re
from pathlib import Path

from ..ids import block_id
from ..models import Block, Document
from .base import build_document, classify_plain_paragraph, detect_language, normalize

_HEBREW = re.compile(r"[א-ת]")
_LATIN = re.compile(r"[A-Za-z]")

#: How much of a title is a title. The first line of a page names it well enough for a
#: shelf; a whole first paragraph does not.
TITLE_CHARS = 60


def paragraphs_of(lines: list[str]) -> list[str]:
    """Blank-line groups, each joined into one line of prose."""
    out: list[str] = []
    held: list[str] = []
    for line in [*lines, ""]:
        if line.strip():
            held.append(" ".join(line.split()))
            continue
        if held:
            out.append(" ".join(held))
            held = []
    return out


def mixed(line: str) -> bool:
    """Whether a line carries both scripts, which is where a text layer scrambles."""
    return bool(_HEBREW.search(line)) and bool(_LATIN.search(line))


def title_of(pages: list[list[str]]) -> str:
    for lines in pages:
        for line in lines:
            words = line.split()
            if not words:
                continue
            title = " ".join(words)
            if len(title) <= TITLE_CHARS:
                return title
            short: list[str] = []
            for word in words:
                if len(" ".join([*short, word])) > TITLE_CHARS:
                    break
                short.append(word)
            return " ".join(short) or title[:TITLE_CHARS]
    return ""


def document_from_pages(
    source: str,
    pages: list[list[str]],
    *,
    ingester: str,
    source_hash: str,
    title: str | None = None,
    language: str | None = None,
) -> Document:
    """One Document from pages of lines. Raises nothing; an empty text is the caller's
    to refuse, since what to say about it depends on where it came from."""
    blocks: list[Block] = []
    for number, lines in enumerate(pages, start=1):
        for text in paragraphs_of([normalize(line) for line in lines]):
            kind, level, line = classify_plain_paragraph(text)
            own = "en" if not _HEBREW.search(line) and _LATIN.search(line) else None
            blocks.append(
                Block(
                    id=block_id(len(blocks)),
                    kind=kind,
                    level=level,
                    text=line,
                    ref=f"p{number}",
                    language=own,
                )
            )
    hebrew = "\n".join(block.text for block in blocks if block.language is None)
    document = build_document(
        source,
        blocks,
        ingester=ingester,
        language=language or (detect_language(hebrew) if hebrew.strip() else None),
        title=title if title is not None else (title_of(pages) or Path(source).stem),
    )
    # The pipeline's own fallback hashes the source decoded as UTF-8, which for a
    # picture says nothing. The bytes, then — set by the ingester that read them.
    # `ref` and `language` ride on the blocks handed over, and `build_document` copies
    # blocks rather than rebuilding them from paragraph tuples, so both survive.
    document.source_hash = source_hash
    return document
