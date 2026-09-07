"""Hebrew vowel points for the reader.

Precedence lives here rather than in a provider, because which pointing wins is not a
strategy anyone should be able to swap: where the source points a word, that pointing is
what the reader shows.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from ..catalogue import Register
from ..errors import SkeletonChanged, TargumError
from ..models import BlockKind, SegmentedDocument, Vocalization, keeps_its_own_pointing
from .base import (
    LETTERS,
    MARKS,
    TAAMIM,
    Vocalizer,
    has_nikkud,
    has_taamim,
    is_fully_pointed,
    js_span,
    map_span,
    pointed_positions,
    splice,
    strip_nikkud,
    strip_taamim,
    supports,
    wants_pointing,
)
from .dicta import DictaVocalizer
from .nakdimon import NakdimonVocalizer

LOG = logging.getLogger(__name__)

__all__ = [
    "DictaVocalizer",
    "NakdimonVocalizer",
    "LETTERS",
    "MARKS",
    "TAAMIM",
    "Vocalizer",
    "has_nikkud",
    "has_taamim",
    "is_fully_pointed",
    "js_span",
    "map_span",
    "pointed_positions",
    "splice",
    "strip_nikkud",
    "strip_taamim",
    "build",
    "for_source",
    "name_for",
    "names",
    "register_of",
    "supports",
    "vocalize_document",
    "wants_pointing",
]

SOURCE_ONLY = "source"

_BUILDERS: dict[str, Callable[[], Vocalizer]] = {
    NakdimonVocalizer.name: NakdimonVocalizer,
    DictaVocalizer.name: DictaVocalizer,
}
DEFAULT = NakdimonVocalizer.name

#: The shelves the menaked's card says it is not for — biblical, rabbinic, premodern —
#: and which stay on Nakdimon. Scripture and the pinned editions never reach either
#: model (`keeps_its_own_pointing`); this is for the Mishnah that arrives bare, and for
#: the Kuzari. The revival shelf is not here on purpose: the Ben-Yehuda measurement was
#: of exactly that Hebrew, and the menaked won on it (targum-internal#148).
CLASSICAL = frozenset({Register.biblical, Register.rabbinic, Register.medieval})


def names() -> list[str]:
    return sorted(_BUILDERS)


def build(name: str = DEFAULT) -> Vocalizer:
    builder = _BUILDERS.get(name)
    if builder is None:
        raise TargumError(f"No vocalizer named '{name}'.", f"Available: {', '.join(names())}")
    return builder()


def register_of(source: object) -> Register:
    """Which Hebrew a text is in, off the catalogue. A text the catalogue does not know —
    an upload, an address somebody pasted — is `none`, and is read as today's Hebrew."""
    from ..catalogue import matching

    entry = matching(str(source or ""))
    return entry.register if entry is not None else Register.none


def name_for(source: object, register: Register | None = None) -> str:
    """The vocalizer a text gets, by register: the menaked for modern Hebrew, Nakdimon
    for the study house. Decided before anything is loaded, because the name is what a
    stored pointing is compared with to know whether it is stale."""
    which = register if register is not None else register_of(source)
    return NakdimonVocalizer.name if which in CLASSICAL else DictaVocalizer.name


def for_source(
    source: object,
    *,
    register: Register | None = None,
    notify: Callable[[str], None] | None = None,
) -> Vocalizer:
    """The vocalizer that will actually run for a text, on this machine.

    The register picks; what is on disk decides. A machine without the menaked's
    weights points with Nakdimon and says so once, and the pointing it writes names
    Nakdimon, so the day the weights arrive the text is pointed again rather than kept.
    """
    engine = build(name_for(source, register))
    usable, why = engine.available()
    if usable:
        return engine
    if notify is not None:
        notify(f"{why} Pointing with Nakdimon instead.")
    return NakdimonVocalizer()


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
    # A published pointed edition is never guessed at. Where one leaves a word bare it is
    # bare on purpose — a ketiv, a scriptural citation, a chapter numeral — and a
    # diacritizer filling it in prints an invention in the one place a reader has no way
    # to doubt it. The refusal sits here rather than at the call site because `targum
    # repair` builds an engine of its own, and a rule that can be walked around is not a
    # rule. Not "mostly pointed, so nothing to add": never, whatever shape it arrives in.
    if keeps_its_own_pointing(source):
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
