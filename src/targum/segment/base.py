"""Splitting blocks into sentences."""

from __future__ import annotations

import re
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


def _unsplit(block: Block, document: Document) -> bool:
    """Whether this block is handed on whole rather than to the segmenter.

    The kinds in `UNSPLIT`, and any block in a language other than the document's. The
    segmenter routes by the document's language — rules for Hebrew, a Stanza model per
    language for the rest, and nothing at all for `arc` — so a block that says it is in
    another is not something it can be asked about. Today the only such blocks are
    verses, which are whole anyway; the rule is here so that a paragraph of Aramaic,
    when one arrives, is kept whole rather than cut by rules or a model meant for a
    different language.
    """
    return block.kind in UNSPLIT or bool(block.language and block.language != document.language)


def segment_document(document: Document, segmenter: Segmenter) -> SegmentedDocument:
    """Titles and bylines stay whole. Everything else goes to the segmenter at once."""
    splittable = [
        (index, block)
        for index, block in enumerate(document.blocks)
        if not _unsplit(block, document)
    ]
    sentences = segmenter.split([block.text for _, block in splittable], document.language)
    by_block: dict[int, list[str]] = {
        index: found for (index, _), found in zip(splittable, sentences, strict=True)
    }

    segments: list[Segment] = []
    for index, block in enumerate(document.blocks):
        pieces = [block.text] if _unsplit(block, document) else by_block.get(index, [])
        for order, text in enumerate(piece for piece in pieces if piece.strip()):
            segments.append(_segment(_index_of(index, block), order, block, text.strip()))

    return SegmentedDocument(
        document_hash=document.content_hash,
        language=document.language,
        segmenter=segmenter.name,
        segments=segments,
    )


# Every ingester so far writes b0000, b0001… — the block's position, zero-padded. An
# audio document numbers its blocks by part instead (see `ids.audio_block_id`), so the
# index a segment id is built from is read off the block's own id wherever the id
# carries one. For every existing document the two are equal, byte for byte, which a
# test pins: this must never re-key a text somebody has paid to translate.
_NUMBERED = re.compile(r"b(\d+)$")


def _index_of(position: int, block: Block) -> int:
    found = _NUMBERED.fullmatch(block.id)
    return int(found.group(1)) if found else position


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
        language=block.language,
    )
