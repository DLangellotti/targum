"""Project Gutenberg, by ebook number.

    targum build gutenberg:1

Gutenberg wraps every text in a licence header and footer. Those are not the book, and
leaving them in would put a paragraph of American copyright law through a translator.
"""

from __future__ import annotations

import re

from ...errors import TargumError
from ...models import Document
from ..base import (
    Paragraph,
    blocks_from_paragraphs,
    build_document,
    classify_plain_paragraph,
    normalize,
    with_front_matter,
)
from ..url import get

TEXT_URLS = (
    "https://www.gutenberg.org/cache/epub/{id}/pg{id}.txt",
    "https://www.gutenberg.org/files/{id}/{id}-0.txt",
    "https://www.gutenberg.org/ebooks/{id}.txt.utf-8",
)

_START = re.compile(r"^\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG.*$", re.M | re.I)
_END = re.compile(r"^\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG.*$", re.M | re.I)
_TITLE = re.compile(r"^Title:\s*(.+)$", re.M)
_AUTHOR = re.compile(r"^Author:\s*(.+)$", re.M)
_LANGUAGE = re.compile(r"^Language:\s*(.+)$", re.M)

# Gutenberg names languages; targum speaks BCP-47.
_LANGUAGE_TAGS = {
    "english": "en",
    "hebrew": "he",
    "russian": "ru",
    "french": "fr",
    "german": "de",
    "spanish": "es",
    "italian": "it",
    "latin": "la",
}


def strip_boilerplate(text: str) -> str:
    if start := _START.search(text):
        text = text[start.end() :]
    if end := _END.search(text):
        text = text[: end.start()]
    return text.strip("\n")


class GutenbergFetcher:
    name = "gutenberg/3"

    def load(self, identifier: str) -> Document:
        book_id = identifier.strip()
        if not book_id.isdigit():
            raise TargumError(
                f"Gutenberg wants an ebook number, not '{book_id}'.",
                "The number in the URL: gutenberg.org/ebooks/1342 is gutenberg:1342",
            )

        raw = ""
        for template in TEXT_URLS:
            try:
                raw = get(template.format(id=book_id))
                break
            except TargumError:
                continue
        if not raw:
            raise TargumError(
                f"Gutenberg has no plain text for ebook {book_id}.",
                "Some entries are scans only. Check gutenberg.org/ebooks/" + book_id,
            )

        header = raw[: raw.find("*** START") if "*** START" in raw else 4000]
        title = _match(_TITLE, header)
        author = _match(_AUTHOR, header)
        language = _LANGUAGE_TAGS.get((_match(_LANGUAGE, header) or "").lower())

        body = normalize(strip_boilerplate(raw))
        paragraphs: list[Paragraph] = [
            classify_plain_paragraph(chunk) for chunk in re.split(r"\n\s*\n", body) if chunk.strip()
        ]
        if not paragraphs:
            raise TargumError(f"Gutenberg ebook {book_id} came back empty.")

        return build_document(
            f"gutenberg:{book_id}",
            blocks_from_paragraphs(with_front_matter(paragraphs, title, author)),
            ingester=self.name,
            language=language,
            title=title,
            author=author,
        )


def _match(pattern: re.Pattern[str], text: str) -> str | None:
    found = pattern.search(text)
    return found.group(1).strip() if found else None
