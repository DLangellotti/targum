"""Plain .txt: blank lines separate paragraphs, and that is the whole format."""

from __future__ import annotations

from pathlib import Path

from ..models import BlockKind, Document
from .base import (
    blocks_from_paragraphs,
    build_document,
    classify_plain_paragraph,
    normalize,
    parse_frontmatter,
    with_front_matter,
)


class PlainTextIngester:
    name = "text/4"

    def load(self, source: str) -> Document:
        path = Path(source)
        fields, text = parse_frontmatter(normalize(path.read_text(encoding="utf-8")))
        paragraphs: list[tuple[BlockKind, int | None, str]] = [
            classify_plain_paragraph(chunk) for chunk in text.split("\n\n") if chunk.strip()
        ]
        title = fields.get("title") or path.stem.replace("-", " ").replace("_", " ")
        author = fields.get("author")
        return build_document(
            str(path),
            blocks_from_paragraphs(
                with_front_matter(paragraphs, title if fields.get("title") else None, author)
            ),
            ingester=self.name,
            language=fields.get("language") or fields.get("lang"),
            title=title,
            author=author,
        )
