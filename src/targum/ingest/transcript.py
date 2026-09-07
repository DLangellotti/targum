"""A written-down conversation (`.chat`), read as a text with a speaker per line.

The file is `chat/transcript.py`'s: Hebrew lines with their English, each with who said
it. One line is one block is one segment — `BlockKind.turn` is in the segmenter's
`UNSPLIT`, the guarantee the dialogue shelf already leans on — and `Build.authored` reads
the same file for the English, by the same block ids this assigns, so the two cannot
disagree about which line a translation belongs to.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..models import Block, BlockKind, Document
from .base import build_document

NAME = "transcript/1"


def _lines(path: Path) -> list[dict[str, Any]]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    rows = loaded.get("lines", []) if isinstance(loaded, dict) else []
    # A line without its English is not written down: the carried translation is taken
    # whole and buys nothing, so such a line would open as a blank.
    return [
        row for row in rows if isinstance(row, dict) and row.get("hebrew") and row.get("english")
    ]


def english_by_block(path: Path) -> dict[str, str]:
    """Each block's English, by the id `load` gives the block. The one enumeration."""
    return {f"b{n:04d}": str(row["english"]) for n, row in enumerate(_lines(path))}


def title_of(path: Path) -> str:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    return str(loaded.get("title") or "") if isinstance(loaded, dict) else ""


class TranscriptIngester:
    name = NAME

    def load(self, source: str) -> Document:
        path = Path(source)
        blocks = [
            Block(
                id=f"b{n:04d}",
                kind=BlockKind.turn,
                text=str(row["hebrew"]),
                speaker=str(row.get("speaker") or ""),
            )
            for n, row in enumerate(_lines(path))
        ]
        return build_document(
            str(path),
            blocks,
            ingester=self.name,
            language="he",
            title=title_of(path) or path.stem,
        )
