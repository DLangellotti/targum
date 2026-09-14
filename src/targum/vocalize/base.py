"""Hebrew vowel points, and Russian stress marks: removing them, and deciding whose wins.

Nikkud only ever adds combining marks; it never changes a letter. Everything in this
package rests on that, which is why the consonant skeleton is checked rather than
assumed. Three of the four diacritizers surveyed quietly delete a matres lectionis by
default, and one deletes the maqaf and fuses the words either side, which would corrupt
the text and break every token offset the reader draws from.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Sequence
from typing import Protocol

from ..errors import SkeletonChanged
from ..models import BlockKind, Segment

# A label rather than a sentence: never sent to a diacritizer, and never counted when
# deciding whether a document was published with vowels.
_LABELS = frozenset({BlockKind.heading, BlockKind.byline})

# Derived from Unicode rather than written out by hand, because the Hebrew block
# interleaves combining marks with punctuation: maqaf, paseq, sof pasuq and nun hafukha
# all sit inside this range and are a word's neighbours, not its marks. Stripping one of
# them would change the text, which is the one thing this module must never do.
MARKS = frozenset(cp for cp in range(0x0591, 0x05C8) if unicodedata.category(chr(cp)) == "Mn")

# Alef through tav, final forms included.
LETTERS = frozenset(range(0x05D0, 0x05EB))

# Russian stress (targum-internal#260): the combining acute over a stressed vowel, and the
# diaeresis that writes a restored ё as е plus a mark. Both are marks only after a Cyrillic
# letter — the same two code points are how a decomposed é or ü is spelled, and a French
# word must never lose its accent to a Russian rule. So these are not in MARKS, which is
# Hebrew's alone and mirrored by the reader; `is_mark` asks with the letter before.
STRESS = frozenset({0x0301, 0x0308})


def cyrillic(char: str) -> bool:
    return "\u0400" <= char <= "\u04ff"


def is_mark(char: str, before: str) -> bool:
    """Whether `char` is a mark on the base character `before`, rather than text."""
    return ord(char) in MARKS or (ord(char) in STRESS and cyrillic(before))


# The te'amim, U+0591-U+05AF: the chanting marks a Masoretic edition carries above and
# below its vowels, and the one part of the pointing a reader may reasonably want out of
# the way. Derived from Unicode the same way MARKS is, and a strict subset of it.
#
# Meteg is deliberately not in here. U+05BD is meteg and silluq both — Unicode gives the
# two one codepoint — so no rule can tell them apart, and a rule that guessed would delete
# the meteg that separates a qamats gadol from a qamats qatan. That deletion is the bug
# this whole feature exists to undo, so the ambiguous mark stays on the vowels' side.
TAAMIM = frozenset(cp for cp in range(0x0591, 0x05B0) if unicodedata.category(chr(cp)) == "Mn")


def strip_nikkud(text: str) -> tuple[str, list[int]]:
    """The bare text, and where each index in `text` lands in it.

    The map carries one entry more than the text, so an exclusive end offset is looked
    up exactly like a start offset and a span reaching the end still maps.
    """
    bare: list[str] = []
    index: list[int] = []
    for char in text:
        index.append(len(bare))
        if not is_mark(char, bare[-1] if bare else ""):
            bare.append(char)
    index.append(len(bare))
    return "".join(bare), index


def strip_taamim(text: str) -> str:
    """The text with its chanting marks gone and every vowel where it was.

    No index map, unlike `strip_nikkud`: nothing is ever measured against this form.
    Offsets live in the bare text, and the reader maps onto whichever form it is showing
    from that form's own characters.
    """
    return "".join(char for char in text if ord(char) not in TAAMIM)


def pointed_positions(text: str) -> list[int]:
    """Where each index of the bare text sits in `text`. The inverse of the map above.

    Same length convention, and the same reason for it. A bare index maps to the base
    character itself, so a span's end lands past the marks belonging to the character
    before it — which is what makes a word's marks travel with the word.
    """
    positions: list[int] = []
    base = ""
    for i, char in enumerate(text):
        if not is_mark(char, base):
            positions.append(i)
            base = char
    positions.append(len(text))
    return positions


def map_span(start: int, end: int, index: list[int]) -> tuple[int, int]:
    """Move one [start, end) span through either map above."""
    return index[start], index[end]


def js_span(text: str, start: int, end: int) -> tuple[int, int]:
    """The same span as the browser counts it.

    Python counts characters; JavaScript counts UTF-16 units, and every character
    outside the Basic Multilingual Plane — an emoji, mostly — is two of them. A page
    marks its words by slicing a string in the browser, so a span measured here lands
    one unit short for every emoji before it: a calendar glyph in a community notice
    put the word mark on half of שחרית and the other half on the time beside it
    (2026-09-07). Every offset that ships to a page goes through this.
    """
    return _js_units(text, start), _js_units(text, end)


def _js_units(text: str, index: int) -> int:
    return index + sum(1 for char in text[:index] if ord(char) > 0xFFFF)


def has_nikkud(text: str) -> bool:
    return any(is_mark(char, text[i - 1] if i else "") for i, char in enumerate(text))


def has_taamim(text: str) -> bool:
    return any(ord(char) in TAAMIM for char in text)


def _units(text: str) -> list[tuple[str, str]]:
    """Each non-mark character paired with the marks that follow it."""
    units: list[tuple[str, list[str]]] = []
    for char in text:
        if is_mark(char, units[-1][0] if units else ""):
            # A mark before any base character has nothing to attach to. Real text does
            # not do this, but a truncated extraction can, and dropping it silently is
            # better than indexing off the front of the list.
            if units:
                units[-1][1].append(char)
        else:
            units.append((char, []))
    return [(base, "".join(marks)) for base, marks in units]


def _word_spans(
    units: list[tuple[str, str]], letter: Callable[[str], bool] | None = None
) -> list[tuple[int, int]]:
    """The [start, end) runs of letters.

    Everything else ends a word: whitespace, punctuation, digits, Latin runs, and the
    maqaf. So 'אל־חלוני' is two words and each side is pointed on its own merits.
    Hebrew letters only unless `letter` says otherwise: whether a Hebrew text is fully
    pointed must not turn on a Russian word quoted in it.
    """
    letter = letter or _hebrew
    spans: list[tuple[int, int]] = []
    start = 0
    while start < len(units):
        if not letter(units[start][0]):
            start += 1
            continue
        end = start
        while end < len(units) and letter(units[end][0]):
            end += 1
        spans.append((start, end))
        start = end
    return spans


def _hebrew(char: str) -> bool:
    return ord(char) in LETTERS


def _letter(char: str) -> bool:
    return ord(char) in LETTERS or (cyrillic(char) and char.isalpha())


def is_fully_pointed(text: str) -> bool:
    """Whether every Hebrew word here already carries marks.

    When this holds for a whole document there is nothing for a diacritizer to add, so
    the build never loads one.
    """
    units = _units(text)
    spans = _word_spans(units)
    if not spans:
        return False
    return all(any(marks for _, marks in units[start:end]) for start, end in spans)


# Below this share of bare prose, a document is a pointed edition rather than a bare one,
# and its own pointing is the authority. Half is a wide margin on purpose: the question
# is not "is anything missing" but "was this published with vowels".
MOSTLY_POINTED = 0.5


def wants_pointing(segments: Sequence[Segment]) -> bool:
    """Whether a diacritizer has anything useful to add to this document.

    Not "is every word pointed", which a Tanakh never is and never should be. The
    Masoretic text carries ketiv/qere — a written form left deliberately consonantal
    beside the pointed form it is read as, like `מידע [מוֹדַע]` in Ruth 2:1. Treating
    those bare words as an omission would have a model invent vowels for the one form
    tradition insists is unvowelled, and print the guess as if it were the text.

    So the question is asked of the document rather than the word: a text that is mostly
    pointed was published pointed, and what is bare in it is the editor's doing.
    """
    prose = [segment for segment in segments if segment.kind not in _LABELS]
    if not prose:
        return False
    bare = sum(1 for segment in prose if not is_fully_pointed(segment.text))
    return bare / len(prose) > MOSTLY_POINTED


def splice(source: str, model: str) -> tuple[str, bool]:
    """Merge two pointings of one text, word by word. The source's own pointing wins.

    A word the source already points is kept exactly as written, because an editor's
    vocalization is a fact and a diacritizer is 55-73% right on classical Hebrew. Only
    words the source left bare are taken from the model.

    Real sources are partly pointed, which is why this is decided per word rather than
    per segment: the Wikisource Mishnah opens each unit with a bare 'משנה א' label above
    fully pointed text.

    Returns the merged text, and whether the model actually contributed any pointing.
    """
    src, mod = _units(source), _units(model)
    if [base for base, _ in src] != [base for base, _ in mod]:
        raise SkeletonChanged(
            "A vocalizer changed the letters, not just the marks above them.",
            f"{strip_nikkud(source)[0][:60]!r} became {strip_nikkud(model)[0][:60]!r}",
        )

    out: list[str] = []
    machine = False
    cursor = 0
    for start, end in _word_spans(src, _letter):
        out.extend(base + marks for base, marks in src[cursor:start])
        if any(marks for _, marks in src[start:end]):
            out.extend(base + marks for base, marks in src[start:end])
        else:
            out.extend(base + marks for base, marks in mod[start:end])
            # Only a word the model actually pointed makes a segment machine-pointed.
            # Where it had nothing to offer either, nothing was added and nothing is
            # claimed.
            machine = machine or any(marks for _, marks in mod[start:end])
        cursor = end
    out.extend(base + marks for base, marks in src[cursor:])
    return "".join(out), machine


class Vocalizer(Protocol):
    """One way of adding vowel points to text that has none.

    Only ever asked about segments the source left partly bare, and only ever trusted
    for the words inside them the source did not point itself.
    """

    name: str

    @property
    def model(self) -> str | None:
        """Model identity, recorded on the artifact."""

    def available(self) -> tuple[bool, str]: ...

    def vocalize(self, segments: list[Segment], language: str) -> dict[str, str]:
        """Pointed text per segment id. Segments it cannot handle are left out."""


# Hebrew, including the retired tag that Wikisource subdomains and Stanza still use.
_HEBREW = frozenset({"he", "iw"})


def supports(language: str) -> bool:
    """Whether vowel points are a thing this language has at all."""
    return language.split("-")[0].lower() in _HEBREW
