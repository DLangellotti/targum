"""Hebrew vowel points for the reader.

Precedence lives here rather than in a provider, because which pointing wins is not a
strategy anyone should be able to swap: where the source points a word, that pointing is
what the reader shows.
"""

from __future__ import annotations

from ..errors import SkeletonChanged, TargumError
from ..models import SegmentedDocument, Vocalization
from .base import (
    LETTERS,
    MARKS,
    Vocalizer,
    has_nikkud,
    is_fully_pointed,
    map_span,
    pointed_positions,
    splice,
    strip_nikkud,
    supports,
)
from .nakdimon import NakdimonVocalizer

__all__ = [
    "NakdimonVocalizer",
    "LETTERS",
    "MARKS",
    "Vocalizer",
    "has_nikkud",
    "is_fully_pointed",
    "map_span",
    "pointed_positions",
    "splice",
    "strip_nikkud",
    "build",
    "names",
    "supports",
    "vocalize_document",
]

SOURCE_ONLY = "source"

_BUILDERS = {NakdimonVocalizer.name: NakdimonVocalizer}
DEFAULT = NakdimonVocalizer.name


def names() -> list[str]:
    return sorted(_BUILDERS)


def build(name: str = DEFAULT) -> Vocalizer:
    builder = _BUILDERS.get(name)
    if builder is None:
        raise TargumError(f"No vocalizer named '{name}'.", f"Available: {', '.join(names())}")
    return builder()


def vocalize_document(
    segmented: SegmentedDocument, engine: Vocalizer | None = None
) -> Vocalization:
    """The pointed form of every segment: the source's own pointing first, then a model.

    A diacritizer is only asked about segments that still have bare words, and only
    trusted for those words. Where a source is pointed throughout, no model is consulted
    at all — which is what lets a Tanakh build work with no engine installed.
    """
    unfinished = [segment for segment in segmented.segments if not is_fully_pointed(segment.text)]
    guesses: dict[str, str] = {}
    if engine is not None and unfinished:
        guesses = engine.vocalize(unfinished, segmented.language)

    pointed: dict[str, str] = {}
    machine: list[str] = []
    rejected: list[str] = []
    for segment in segmented.segments:
        guess = guesses.get(segment.id)
        if guess is None:
            merged, from_model = segment.text, False
        else:
            try:
                merged, from_model = splice(segment.text, guess)
            except SkeletonChanged:
                # One mangled sentence falls back to the source's own text. The rest of
                # the document keeps its vowels, and the id is recorded so the damage is
                # findable rather than merely counted.
                rejected.append(segment.id)
                merged, from_model = segment.text, False
        # A segment with no marks at all has nothing to toggle, so it never reaches the
        # artifact and never doubles a cell in the rendered page.
        if has_nikkud(merged):
            pointed[segment.id] = merged
            if from_model:
                machine.append(segment.id)

    return Vocalization(
        document_hash=segmented.document_hash,
        language=segmented.language,
        vocalizer=engine.name if engine is not None else SOURCE_ONLY,
        model=engine.model if engine is not None else None,
        segments=pointed,
        machine=machine,
        rejected=rejected,
    )
