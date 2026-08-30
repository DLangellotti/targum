"""Splitting blocks into sentences."""

from __future__ import annotations

from typing import Protocol

from ..ids import segment_id
from ..models import Block, BlockKind, Document, Segment, SegmentedDocument

# A title or a byline is one unit however it punctuates. So is a verse: scripture is
# numbered by verse and the published translations are numbered the same way, so a verse
# is the unit both sides agree on. Let the segmenter split one long verse into two and
# that agreement is gone — which is the whole basis on which a Tanakh pairs for nothing.
# A turn joins these: one line is one thing a person said, and splitting it into
# sentences would break the only mapping the audio has — a span per turn — and put
# the speaker's name beside half of what they said.
UNSPLIT = frozenset({BlockKind.heading, BlockKind.byline, BlockKind.verse, BlockKind.turn})


class Segmenter(Protocol):
    @property
    def name(self) -> str:
        """Identifies the segmenter and its version in the artifact."""

    def split(self, texts: list[str], language: str) -> list[list[str]]: ...


def segment_document(document: Document, segmenter: Segmenter) -> SegmentedDocument:
    """Titles and bylines stay whole. Everything else goes to the segmenter at once."""
    splittable = [
        (index, block) for index, block in enumerate(document.blocks) if block.kind not in UNSPLIT
    ]
    sentences = segmenter.split([block.text for _, block in splittable], document.language)
    by_block: dict[int, list[str]] = {
        index: found for (index, _), found in zip(splittable, sentences, strict=True)
    }

    segments: list[Segment] = []
    for index, block in enumerate(document.blocks):
        pieces = [block.text] if block.kind in UNSPLIT else by_block.get(index, [])
        for order, text in enumerate(piece for piece in pieces if piece.strip()):
            segments.append(_segment(index, order, block, text.strip()))

    return SegmentedDocument(
        document_hash=document.content_hash,
        language=document.language,
        segmenter=segmenter.name,
        segments=segments,
    )


def _segment(block_index: int, order: int, block: Block, text: str) -> Segment:
    return Segment(
        id=segment_id(block_index, order, text),
        block_id=block.id,
        block_index=block_index,
        index=order,
        kind=block.kind,
        level=block.level,
        text=text,
        ref=block.ref,
    )
