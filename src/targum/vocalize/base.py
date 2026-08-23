"""Hebrew vowel points: removing them, and deciding whose pointing wins.

Nikkud only ever adds combining marks; it never changes a letter. Everything in this
package rests on that, which is why the consonant skeleton is checked rather than
assumed. Three of the four diacritizers surveyed quietly delete a matres lectionis by
default, and one deletes the maqaf and fuses the words either side, which would corrupt
the text and break every token offset the reader draws from.
"""

from __future__ import annotations

import unicodedata
from typing import Protocol

from ..errors import SkeletonChanged
from ..models import Segment

# Derived from Unicode rather than written out by hand, because the Hebrew block
# interleaves combining marks with punctuation: maqaf, paseq, sof pasuq and nun hafukha
# all sit inside this range and are a word's neighbours, not its marks. Stripping one of
# them would change the text, which is the one thing this module must never do.
MARKS = frozenset(cp for cp in range(0x0591, 0x05C8) if unicodedata.category(chr(cp)) == "Mn")

# Alef through tav, final forms included.
LETTERS = frozenset(range(0x05D0, 0x05EB))


def strip_nikkud(text: str) -> tuple[str, list[int]]:
    """The bare text, and where each index in `text` lands in it.

    The map carries one entry more than the text, so an exclusive end offset is looked
    up exactly like a start offset and a span reaching the end still maps.
    """
    bare: list[str] = []
    index: list[int] = []
    for char in text:
        index.append(len(bare))
        if ord(char) not in MARKS:
            bare.append(char)
    index.append(len(bare))
    return "".join(bare), index


def pointed_positions(text: str) -> list[int]:
    """Where each index of the bare text sits in `text`. The inverse of the map above.

    Same length convention, and the same reason for it. A bare index maps to the base
    character itself, so a span's end lands past the marks belonging to the character
    before it — which is what makes a word's marks travel with the word.
    """
    positions = [i for i, char in enumerate(text) if ord(char) not in MARKS]
    positions.append(len(text))
    return positions


def map_span(start: int, end: int, index: list[int]) -> tuple[int, int]:
    """Move one [start, end) span through either map above."""
    return index[start], index[end]


def has_nikkud(text: str) -> bool:
    return any(ord(char) in MARKS for char in text)


def _units(text: str) -> list[tuple[str, str]]:
    """Each non-mark character paired with the marks that follow it."""
    units: list[tuple[str, list[str]]] = []
    for char in text:
        if ord(char) in MARKS:
            # A mark before any base character has nothing to attach to. Real text does
            # not do this, but a truncated extraction can, and dropping it silently is
            # better than indexing off the front of the list.
            if units:
                units[-1][1].append(char)
        else:
            units.append((char, []))
    return [(base, "".join(marks)) for base, marks in units]


def _word_spans(units: list[tuple[str, str]]) -> list[tuple[int, int]]:
    """The [start, end) runs of Hebrew letters.

    Everything else ends a word: whitespace, punctuation, digits, Latin runs, and the
    maqaf. So 'אל־חלוני' is two words and each side is pointed on its own merits.
    """
    spans: list[tuple[int, int]] = []
    start = 0
    while start < len(units):
        if ord(units[start][0]) not in LETTERS:
            start += 1
            continue
        end = start
        while end < len(units) and ord(units[end][0]) in LETTERS:
            end += 1
        spans.append((start, end))
        start = end
    return spans


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
    for start, end in _word_spans(src):
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
