"""Aligning existing translations."""

from __future__ import annotations

from collections.abc import Sequence

from ..models import (
    Alignment,
    Link,
    Segment,
    SegmentedDocument,
    Translation,
)
from .base import (
    CONFIDENCE_FLOOR,
    Candidate,
    Encoder,
    align_sequences,
    length_ratio,
    to_links,
)
from .embedding import DEFAULT_MODEL, SentenceTransformerEncoder
from .score import Score, as_indices, load_gold, score

__all__ = [
    "CONFIDENCE_FLOOR",
    "DEFAULT_MODEL",
    "Aligner",
    "Encoder",
    "SentenceTransformerEncoder",
    "Score",
    "align",
    "as_indices",
    "load_gold",
    "score",
    "to_translation",
]


class Aligner:
    """Two passes: blocks first, then sentences inside each block pairing.

    Anchoring on structure before sentences is what keeps one bad match from cascading.
    A translator who merges two chapters shifts everything after it; aligning blocks
    first absorbs that shift in one link instead of dragging it through the book.
    """

    def __init__(
        self,
        encoder: Encoder | None = None,
        *,
        confidence_floor: float = CONFIDENCE_FLOOR,
    ) -> None:
        self.encoder: Encoder = encoder or SentenceTransformerEncoder()
        self.confidence_floor = confidence_floor

    @property
    def name(self) -> str:
        return f"blocks+sentences/{self.encoder.name}"

    def align(self, source: SegmentedDocument, target: SegmentedDocument, name: str) -> Alignment:
        ratio = length_ratio(
            [segment.text for segment in source.segments],
            [segment.text for segment in target.segments],
        )
        source_blocks = _blocks(source.segments)
        target_blocks = _blocks(target.segments)

        if comparable_structure(len(source_blocks), len(target_blocks)):
            block_links = self._pass(
                [_joined(block) for block in source_blocks],
                [_joined(block) for block in target_blocks],
                ratio,
            )
        else:
            # One side has paragraph structure the other does not, which happens
            # whenever an edition is transcribed as a single run of text. Anchoring on
            # blocks here is worse than not anchoring at all: the shapes cannot express
            # "one block against twenty", so most of the text would be dropped as null
            # links. Treat the document as one window and let the sentences speak.
            source_blocks = [list(source.segments)]
            target_blocks = [list(target.segments)]
            block_links = [Candidate([0], [0], 0.0)]

        links: list[Link] = []
        for candidate in block_links:
            source_segments = [s for index in candidate.source for s in source_blocks[index]]
            target_segments = [s for index in candidate.target for s in target_blocks[index]]
            links.extend(
                self._sentences(source_segments, target_segments, candidate.confidence, ratio)
            )

        return Alignment(
            name=name,
            document_hash=source.document_hash,
            translation_hash=target.document_hash,
            source_language=source.language,
            target_language=target.language,
            aligner=self.name,
            length_ratio=round(ratio, 4),
            links=links,
        )

    def _pass(self, source: Sequence[str], target: Sequence[str], ratio: float) -> list[Candidate]:
        similarity = self.encoder.similarity(source, target)
        return align_sequences(source, target, similarity, ratio)

    def _sentences(
        self,
        source: list[Segment],
        target: list[Segment],
        block_confidence: float,
        ratio: float,
    ) -> list[Link]:
        if not source or not target:
            # One side is missing entirely: a dropped or added block, recorded as such.
            return to_links(
                [Candidate(list(range(len(source))), list(range(len(target))), 0.0)],
                source,
                target,
            )
        if len(source) == 1 and len(target) == 1:
            return to_links([Candidate([0], [0], block_confidence)], source, target)

        candidates = self._pass(
            [segment.text for segment in source], [segment.text for segment in target], ratio
        )
        weak = [c for c in candidates if c.confidence < self.confidence_floor]
        if weak and len(weak) * 2 >= len(candidates):
            # Most of this block is guesswork. A visibly coarser pairing is better than
            # a confidently wrong one, so pair the whole block and say so.
            return to_links(
                [Candidate(list(range(len(source))), list(range(len(target))), block_confidence)],
                source,
                target,
                coarse=True,
            )
        return to_links(candidates, source, target)


# Block anchoring only helps when both sides were laid out in comparable units.
MAX_STRUCTURE_SKEW = 2.0
MIN_BLOCKS = 3


def comparable_structure(source_blocks: int, target_blocks: int) -> bool:
    if source_blocks < MIN_BLOCKS or target_blocks < MIN_BLOCKS:
        return False
    smaller, larger = sorted((source_blocks, target_blocks))
    return larger / smaller <= MAX_STRUCTURE_SKEW


def _blocks(segments: Sequence[Segment]) -> list[list[Segment]]:
    """Segments regrouped into the blocks they came from."""
    out: list[list[Segment]] = []
    current_index: int | None = None
    for segment in segments:
        if segment.block_index != current_index:
            out.append([])
            current_index = segment.block_index
        out[-1].append(segment)
    return out


def _joined(block: Sequence[Segment]) -> str:
    return " ".join(segment.text for segment in block)


def align(
    source: SegmentedDocument,
    target: SegmentedDocument,
    name: str,
    aligner: Aligner | None = None,
) -> Alignment:
    return (aligner or Aligner()).align(source, target, name)


def to_translation(
    alignment: Alignment, target: SegmentedDocument, *, style_note: str = "aligned"
) -> Translation:
    """Project an alignment into what the reader renders.

    The reader draws from a segment-id to text mapping whether the text came from a
    provider or from a published translation, so both arrive the same way and the
    in-reader switcher does not care which is which.
    """
    text_by_id = {segment.id: segment.text for segment in target.segments}
    segments: dict[str, str] = {}
    coarse: list[str] = []
    confidence: dict[str, float] = {}

    for link in alignment.links:
        if not link.source:
            continue
        rendered = " ".join(text_by_id.get(target_id, "") for target_id in link.target).strip()
        for source_id in link.source:
            segments[source_id] = rendered
            confidence[source_id] = link.confidence
            if link.coarse:
                coarse.append(source_id)

    return Translation(
        name=alignment.name,
        document_hash=alignment.document_hash,
        source_language=alignment.source_language,
        target_language=alignment.target_language,
        provider=style_note,
        model=alignment.aligner,
        kind="aligned",
        segments=segments,
        coarse=coarse,
        confidence=confidence,
    )
