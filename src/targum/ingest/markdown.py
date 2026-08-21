"""Markdown, read for structure rather than for formatting.

Only the constructs that change how a text is read matter here: headings, paragraphs,
blockquotes, and the title and author from a frontmatter block. Inline emphasis and
links are flattened, because the reader shows sentences beside their translations,
not styled prose.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..models import BlockKind, Document
from .base import (
    blocks_from_paragraphs,
    build_document,
    normalize,
    parse_frontmatter,
)

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_QUOTE = re.compile(r"^>\s?")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_EMPHASIS = re.compile(r"(\*{1,3}|_{1,3}|`)")


def _flatten(text: str) -> str:
    return _EMPHASIS.sub("", _LINK.sub(r"\1", text)).strip()


class MarkdownIngester:
    # Bump this whenever the blocks this produces change. It is what tells a rerun
    # that an old document.json is stale rather than hand-edited.
    name = "markdown/4"

    def load(self, source: str) -> Document:
        path = Path(source)
        fields, body = parse_frontmatter(normalize(path.read_text(encoding="utf-8")))
        lines = body.split("\n")

        paragraphs: list[tuple[BlockKind, int | None, str]] = []
        buffer: list[str] = []
        buffered_kind = BlockKind.paragraph

        def flush() -> None:
            nonlocal buffer, buffered_kind
            if buffer:
                paragraphs.append((buffered_kind, None, _flatten(" ".join(buffer))))
            buffer = []
            buffered_kind = BlockKind.paragraph

        for line in lines:
            stripped = line.strip()
            if not stripped:
                flush()
                continue
            if heading := _HEADING.match(stripped):
                flush()
                paragraphs.append(
                    (BlockKind.heading, len(heading.group(1)), _flatten(heading.group(2)))
                )
                continue
            if _QUOTE.match(stripped):
                if buffered_kind is not BlockKind.blockquote:
                    flush()
                buffered_kind = BlockKind.blockquote
                buffer.append(_QUOTE.sub("", stripped))
                continue
            if buffered_kind is BlockKind.blockquote:
                flush()
            buffer.append(stripped)
        flush()

        title = fields.get("title") or next(
            (text for kind, level, text in paragraphs if kind is BlockKind.heading and level == 1),
            None,
        )
        author = fields.get("author")

        # Title and author become blocks so they run through the same segmentation and
        # translation as the body. A reader wants "Declaration of the Establishment of
        # the State of Israel" above the Hebrew, not the Hebrew twice.
        own_title = next(
            (
                i
                for i, (kind, level, _) in enumerate(paragraphs)
                if kind is BlockKind.heading and level == 1
            ),
            None,
        )
        if title and own_title is None:
            paragraphs.insert(0, (BlockKind.heading, 1, title))
            own_title = 0
        if author:
            # Under the title if there is one, at the top otherwise.
            paragraphs.insert(
                0 if own_title is None else own_title + 1, (BlockKind.byline, None, author)
            )

        return build_document(
            str(path),
            blocks_from_paragraphs(paragraphs),
            ingester=self.name,
            language=fields.get("language") or fields.get("lang"),
            title=title or path.stem.replace("-", " ").replace("_", " "),
            author=author,
        )
