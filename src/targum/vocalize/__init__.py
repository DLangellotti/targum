"""Hebrew vowel points for the reader.

Precedence lives here rather than in a provider, because which pointing wins is not a
strategy anyone should be able to swap: where the source points a word, that pointing is
what the reader shows.
"""

from __future__ import annotations

import logging

from ..errors import SkeletonChanged, TargumError
from ..models import BlockKind, SegmentedDocument, Vocalization, is_biblical
from .base import (
    LETTERS,
    MARKS,
    TAAMIM,
    Vocalizer,
    has_nikkud,
    has_taamim,
    is_fully_pointed,
    map_span,
    pointed_positions,
    splice,
    strip_nikkud,
    strip_taamim,
    supports,
    wants_pointing,
)
from .nakdimon import NakdimonVocalizer

LOG = logging.getLogger(__name__)

__all__ = [
    "NakdimonVocalizer",
    "LETTERS",
    "MARKS",
    "TAAMIM",
    "Vocalizer",
    "has_nikkud",
    "has_taamim",
    "is_fully_pointed",
    "map_span",
    "pointed_positions",
    "splice",
    "strip_nikkud",
    "strip_taamim",
    "build",
    "names",
    "supports",
    "vocalize_document",
    "wants_pointing",
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


# A label rather than a sentence: never sent to a diacritizer.
LABELS = frozenset({BlockKind.heading, BlockKind.byline})


def vocalize_document(
    segmented: SegmentedDocument, engine: Vocalizer | None = None, source: str = ""
) -> Vocalization:
    """The pointed form of every segment: the source's own pointing first, then a model.

    A diacritizer is only asked about segments that still have bare words, and only
    trusted for those words. Where a source is pointed throughout, no model is consulted
    at all — which is what lets a Tanakh build work with no engine installed.
    """
    # Scripture is never guessed at. Where a Masoretic edition leaves a word bare it is
    # bare on purpose — a ketiv, or an editor reading it as something else — and a
    # diacritizer filling it in prints an invention in the one place a reader has no way
    # to doubt it. The refusal sits here rather than at the call site because `targum
    # repair` builds an engine of its own, and a rule that can be walked around is not a
    # rule. Not "mostly pointed, so nothing to add": never, whatever shape it arrives in.
    if is_biblical(source):
        engine = None
    # Headings and bylines are labels, not prose. Nobody wants vowel points on a chapter
    # number, and asking for them is how a Tanakh — pointed throughout, and the one case
    # this is meant to need no engine for — ends up loading one anyway. Sefaria's
    # "רות א׳" was enough to make Nakdimon assert and take the whole build down with it.
    unfinished = [
        segment
        for segment in segmented.segments
        if segment.kind not in LABELS and not is_fully_pointed(segment.text)
    ]
    guesses: dict[str, str] = {}
    if engine is not None and unfinished:
        try:
            guesses = engine.vocalize(unfinished, segmented.language)
        except Exception as error:  # noqa: BLE001 - a third-party model, not our code
            # Losing the vowels is a disappointment; losing the build is an afternoon.
            # Nakdimon raises bare AssertionErrors on input it dislikes, so this cannot
            # be narrowed to a useful exception type.
            LOG.warning("the diacritizer failed, leaving the source's own pointing: %s", error)
            guesses = {}

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
