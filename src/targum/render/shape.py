"""A text in the shape its edition gives it (design.md §12, "A text keeps the shape its
edition gives it", 2026-11-04).

Everything here is drawn from what a reader already carries: the chapter heading the
ingest wrote, the (פ) and (ס) a scribe left at the end of a verse, the etnachta in a
verse of Psalms. Nothing is stored and nothing is bought. What it produces is markup
around the text, never a change to it: a `<span>` or a `<br>` adds no character, so a
word's offsets, its card and every count are exactly what they were. `reader.js` walks
text nodes, and an element between them is invisible to it.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache

from markupsafe import Markup, escape

from ..models import BlockKind, Segment

#: The languages written in Hebrew letters, whose own numbering is in letters too.
HEBREW_SCRIPT = frozenset({"he", "arc"})

#: The end of a verse a scribe closed with an open (פ) or a closed (ס) parasha. The
#: accented edition writes them in brackets after the sof pasuq.
_PARASHA = re.compile(r"\((פ|ס)\)\s*$")

#: The poetic books, whose accents divide a verse in their own system. The etnachta is
#: the main division in all three wherever it stands; where a verse has none it is one
#: line, which is what a printed Tehillim does with a verse that short.
_POETIC = re.compile(r"^(?:Psalms|Proverbs|Job) \d+:\d+$")
_ETNACHTA = "֑"

#: A word, for counting words across the forms of one line: a run with a letter in it.
#: A paseq (׀) or a dash standing alone is not one, so the vowelled line and the bare
#: one count the same however each writes its punctuation.
_WORD = re.compile(r"\S*[א-ת]\S*")


def in_letters(language: str) -> bool:
    """Whether a text in this language numbers itself in Hebrew letters."""
    return (language or "").split("-")[0].lower() in HEBREW_SCRIPT


def numeral(number: int) -> str:
    """1 -> א׳, 15 -> ט״ו: the ingest's own numerals, so a heading and a margin agree."""
    from ..ingest.fetch.sefaria import hebrew_numeral

    return hebrew_numeral(number)


@cache
def _numerals() -> Mapping[str, int]:
    return {numeral(n): n for n in range(1, 1000)}


def verse_label(address: str, letters: bool) -> str:
    """What the margin says beside a verse: "2:7" is ז׳ in letters, 7 in digits."""
    verse = address.split(":")[-1]
    if letters and verse.isdigit():
        return numeral(int(verse))
    return verse


@dataclass(frozen=True, slots=True)
class Plate:
    """A chapter's heading, named as a chapter: the work once, then פרק and its numeral."""

    work: str
    chapter: str
    number: int

    @property
    def said(self) -> str:
        """ "פרק ב׳": the word a printed edition heads a chapter with, in its letters."""
        return f"\u05e4\u05e8\u05e7 {self.chapter}"


def plates(title: str | None, language: str, segments: Iterable[Segment]) -> dict[str, Plate]:
    """The headings that are the work's name and a chapter's numeral, by segment id.

    Only those: "משנה תורה, הלכות יסודי התורה ב׳" under a title that already says
    "משנה תורה, הלכות יסודי התורה", "בראשית א׳" under "בראשית". A heading that says
    anything else — a portion's name, a section's title — is the edition's own words and
    stays as it was.
    """
    work = (title or "").strip()
    if not work or not in_letters(language):
        return {}
    found: dict[str, Plate] = {}
    for segment in segments:
        if segment.kind is not BlockKind.heading:
            continue
        text = segment.text.strip()
        if not text.startswith(work + " "):
            continue
        rest = text[len(work) + 1 :].strip()
        number = _numerals().get(rest)
        if number:
            found[segment.id] = Plate(work=work, chapter=rest, number=number)
    return found


def parasha(text: str) -> str:
    """ "open" or "closed" where a verse ends a parasha, and "" where it does not."""
    found = _PARASHA.search(text)
    if not found:
        return ""
    return "open" if found.group(1) == "פ" else "closed"


#: One piece of shape over a line of text: a span from `start` to `end` with a class, or
#: a line break at `start` where `end` equals it.
Cut = tuple[int, int, str]


def parasha_cut(text: str) -> list[Cut]:
    found = _PARASHA.search(text)
    if not found:
        return []
    return [(found.start(), found.end(), "pmark")]


def half_line(ref: str, accented: str) -> int | None:
    """Which word a verse of the poetic books breaks after, counting words from 0."""
    if not _POETIC.match(ref.strip()) or _ETNACHTA not in accented:
        return None
    words = _WORD.findall(accented)
    for index, word in enumerate(words):
        if _ETNACHTA in word:
            # A verse whose etnachta stands on its last word has nothing to set in.
            return index if index < len(words) - 1 else None
    return None


def break_after(text: str, word: int, words: int) -> list[Cut]:
    """A line break after the `word`th word of this form of the line.

    Only where this form counts the same words as the form the break was read from: a
    break placed by counting a different number of words would cut the wrong one.
    """
    found = list(_WORD.finditer(text))
    if len(found) != words or word >= len(found):
        return []
    at = found[word].end()
    return [(at, at, "stich")]


def found_in(text: str, pieces: Iterable[str], kind: str) -> list[Cut]:
    """Each piece where it stands in this form of the line, each after the last.

    An edition's marks are kept against its own text (`models.Mark`), and a page draws
    the line in up to three forms. A citation is printed without vowels in every one of
    them, so it is found by its words rather than carried by offset; a piece this form
    does not hold is left unmarked.
    """
    cuts: list[Cut] = []
    cursor = 0
    for piece in pieces:
        if not piece:
            continue
        at = text.find(piece, cursor)
        if at < 0:
            continue
        cuts.append((at, at + len(piece), kind))
        cursor = at + len(piece)
    return cuts


#: A translation's own reference in brackets: "(Deut. 6,5)", "(Ibid. 6, 13)", "(Ps. 42,2)".
#: Drawn as an edition's citation only beside a text whose edition marks its own.
_ENGLISH_CITATION = re.compile(
    r"\((?:Ibid\.?|[A-Z][a-z]+\.?(?: [A-Z][a-z]+\.?)?)\s*\d+[\d,:\s\u2013-]*\)"
)


def english_citations(text: str) -> list[Cut]:
    return [(m.start(), m.end(), "cite") for m in _ENGLISH_CITATION.finditer(text)]


def word_count(text: str) -> int:
    return len(_WORD.findall(text))


def dress(
    text: str,
    direction: str,
    cuts: Sequence[Cut] | None,
    isolate: Callable[[str, str], Markup],
) -> Markup:
    """The text, isolated as ever, with its pieces of shape around it.

    With no cuts this is `isolate` exactly, so a text with nothing to dress is the page it
    was to the byte. Overlapping spans keep the first; a break inside a span is dropped.
    """
    if not cuts:
        return isolate(text, direction)
    ordered = sorted(cuts, key=lambda cut: (cut[0], cut[1]))
    parts: list[str] = []
    position = 0
    for start, end, kind in ordered:
        if start < position or end > len(text) or start > end:
            continue
        parts.append(str(isolate(text[position:start], direction)))
        if start == end and kind.startswith("note:"):
            numeral = escape(kind.split(":", 1)[1])
            parts.append(f'<sup class="note-mark">{numeral}</sup>')
        elif start == end:
            parts.append(f'<br class="{kind}">')
        else:
            parts.append(f'<span class="{kind}">{isolate(text[start:end], direction)}</span>')
        position = end
    parts.append(str(isolate(text[position:], direction)))
    return Markup("".join(parts))
