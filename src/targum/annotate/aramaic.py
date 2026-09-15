"""The words of a Targum, read without a tagger (targum-internal#64).

No tagger reads Targumic Aramaic. Stanza has no model for it, DICTA's is trained on
Hebrew, and both answer confidently when handed it anyway: #63 found half of Onkelos
Genesis 1 called proper names, "light" a verb, and the object marker the verb "to give".
So a word of Onkelos is not tagged here. It is answered only where the answer is known,
and **claims no part of speech, no root, no binyan and no difficulty band** where it is
not: `Bands.supports()` is already false for Aramaic, so the reader says a word is not
rated and why.

**Two things answer, and nothing else does.**

1. `closed.TARGUM`, written by hand: the commonest forms of Onkelos, with the headword
   each is filed under and what it means. 549 forms, and with ו and one of ד ב ל כ מ
   taken off the front they answer 58.9% of the 82,914 running words of the Torah.
2. The verse's own names. A Targum of the Torah translates a Hebrew verse, and the Open
   Scriptures tagging of that verse marks its proper names, so `אברם` in Onkelos Genesis
   12:1 is a name because `אַבְרָם` is one in Genesis 12:1. Another 6.8%, and a tenth of
   Genesis, where the genealogies are.

**Jastrow was measured and is not asked** (targum-internal#64). The issue proposed looking
every word up in Jastrow's dictionary by spelling, and #63 measured that 81% of Onkelos
reaches a headword that way. Reaching one was not the question. Read against the verses
they came from, 210 of those answers were right about half the time — 60% where the
spelling matched exactly, 42% to 50% where a prefix or a suffix had to come off, 70% even
under the strictest rule that kept any volume at all (one entry for the spelling, cited
from a Targum at least three times). "Twilight" came back "prostitute", "shall die"
"poison", "your name" "service". A card that says those is worse than a card that says
nothing, so what the table and the names do not answer is left unanswered.

**What is not answered is still a word.** It is tapped, kept and counted like any other,
filed under its own letters, and a reader who wants its meaning asks for it the way they
ask for any word's — with the sentence, which is what tells the Targum's words apart.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from functools import cache
from typing import Any, NamedTuple

from ..models import Segment, Token

NAME = "aramaic/1"

#: What a lexeme looks like when the hand table answered: `targum:אַרְעָא`. A lexeme is
#: where a word's meaning is found (`gloss.from_the_tagging`), and a Strong's number is the
#: other kind, so the two cannot be mistaken for each other.
HAND = "targum:"

#: One-letter words Aramaic writes onto the next one: and, of or which, in, to, as, from.
PREFIXES = "ודבלכמ"

_POINTS = re.compile(r"[֑-ׇ]")
_FINALS = str.maketrans("ךםןףץ", "כמנפצ")
_WORD = re.compile(r"[^\s־]+")


def bare(text: str) -> str:
    """The letters, with the points and the accents taken off."""
    return _POINTS.sub("", unicodedata.normalize("NFC", text or ""))


def key(text: str) -> str:
    """A spelling as the table files it: bare, letters only, final forms folded."""
    return re.sub(r"[^א-ת]", "", bare(text)).translate(_FINALS)


@cache
def _hand() -> dict[str, str]:
    from .closed import TARGUM

    return {key(form): headword for form, headword in TARGUM.items()}


class Found(NamedTuple):
    """What one Aramaic word was read as."""

    #: The headword, pointed, or "" for a name.
    headword: str
    #: The one-letter words taken off the front, in order.
    prefixes: str = ""
    #: A proper name of the verse.
    name: bool = False


def _stems(form: str) -> list[tuple[str, str]]:
    """The form, then with a ו off the front, then with one more of `PREFIXES` off that."""
    out = [(form, "")]
    if len(form) > 2 and form[0] == "ו":
        out.append((form[1:], "ו"))
    for stem, taken in list(out):
        if len(stem) > 2 and stem[0] in PREFIXES and stem[0] != "ו":
            out.append((stem[1:], taken + stem[0]))
    return out


def look_up(form: str, names: frozenset[str] = frozenset()) -> Found | None:
    """One Aramaic word, or None where nothing here knows it.

    In this order, and the order is the finding: the form whole in the table, then a name
    of the verse, then the table with prefixes taken off. A name before a peeled form,
    because `מדין` is Midian where the verse names Midian, and מ + "this" nowhere.
    """
    folded = key(form)
    if not folded:
        return None
    hand = _hand()
    stems = _stems(folded)
    if folded in hand:
        return Found(hand[folded])
    for stem, taken in stems:
        if stem in names:
            return Found("", taken, name=True)
    for stem, taken in stems[1:]:
        if stem in hand:
            return Found(hand[stem], taken)
    return None


def sense(lexeme: str | None) -> str:
    """What the hand table says a word means, or ""."""
    if not lexeme or not lexeme.startswith(HAND):
        return ""
    from .closed import TARGUM_GLOSSES

    return TARGUM_GLOSSES.get(lexeme[len(HAND) :], "")


def verse_names(ref: str) -> frozenset[str]:
    """The proper names of the Hebrew verse a Targum verse translates, folded.

    `Onkelos Genesis 12:1` translates `Genesis 12:1`. Nothing for a reference that is not
    a Targum of a tagged book, and nothing where the tagging is not on disk: a box without
    it reads the names as unanswered words, which is less and is not wrong.
    """
    if not ref.startswith("Onkelos "):
        return frozenset()
    from . import oshb

    if not oshb.available():
        return frozenset()
    found: set[str] = set()
    for word in oshb.words(ref.removeprefix("Onkelos ")) or ():
        for piece, code in zip(word.pieces, word.morph, strict=False):
            if code.startswith("Np"):
                found.add(key(piece))
    return frozenset(found)


def _spans(text: str) -> Iterator[tuple[int, int]]:
    """Each run of text between spaces and maqafs, as the span of its letters."""
    for found in _WORD.finditer(text):
        start, end = found.start(), found.end()
        while start < end and not ("א" <= text[start] <= "ת"):
            start += 1
        while end > start and not ("א" <= text[end - 1] <= "ת"):
            end -= 1
        if start < end:
            yield start, end


def is_aramaic(segment: Segment, language: str) -> bool:
    """Whether a segment is Aramaic: said so on the block, or by the document."""
    return (segment.language or language or "").split("-")[0].lower() == "arc"


class AramaicLemmatizer:
    """Aramaic read here; everything else handed to the lemmatizer it wraps."""

    def __init__(self, fallback: Any) -> None:
        self.fallback = fallback

    @property
    def name(self) -> str:
        """`aramaic/1` before the name of what it wraps, the way `oshb/5` sits before
        DICTA's. Wrapped only around a text written in Aramaic (`lemma.for_source`), so
        every Hebrew text's annotator is named exactly as it was and nothing on the shelf
        is read again for this."""
        return f"{NAME}+{self.fallback.name}"

    @property
    def scripture_share(self) -> float | None:
        return getattr(self.fallback, "scripture_share", None)

    def reads(self, segment: Segment) -> bool:
        """Any Aramaic block: every word of one is either answered or left unanswered,
        and neither is a Hebrew model guessing."""
        if (segment.language or "").split("-")[0].lower() == "arc":
            return True
        from .base import reads

        return reads(self.fallback, segment)

    def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
        mine = [segment for segment in segments if is_aramaic(segment, language)]
        rest = [segment for segment in segments if not is_aramaic(segment, language)]
        out = self.fallback.lemmas(rest, language) if rest else {}
        for segment in mine:
            out[segment.id] = tokens(segment)
        return out


def tokens(segment: Segment) -> list[Token]:
    """Every word of one Aramaic segment, answered or not, with offsets into its bare text."""
    text = bare(segment.text)
    names = verse_names(segment.ref or "")
    out: list[Token] = []
    for start, end in _spans(text):
        surface = text[start:end]
        letters = re.sub(r"[^א-ת]", "", surface)
        found = look_up(surface, names)
        if found is None:
            # Nothing known. Still a word — tappable, keepable, counted — filed under its
            # own letters, with nothing on its card that could be wrong.
            out.append(Token(start=start, end=end, surface=surface, lemma=letters, band=0))
            continue
        stem = letters[len(found.prefixes) :] or letters
        # How it is put together, said the way the scripture path says it: "ו + ארעא".
        built = " + ".join([*found.prefixes, stem]) if found.prefixes else None
        if found.name:
            out.append(
                Token(
                    start=start,
                    end=end,
                    surface=surface,
                    lemma=stem,
                    band=0,
                    pos="PROPN",
                    split=bool(found.prefixes),
                    built=built,
                )
            )
            continue
        headword = unicodedata.normalize("NFC", found.headword)
        out.append(
            Token(
                start=start,
                end=end,
                surface=surface,
                lemma=bare(headword),
                band=0,
                split=bool(found.prefixes),
                built=built,
                headword=headword,
                lexeme=f"{HAND}{headword}",
            )
        )
    return out


def rendering_tokens(text: str, ref: str = "") -> list[Token]:
    """The words of an Aramaic rendering read beside a Hebrew text — Onkelos beside the
    Torah — with offsets into the rendering's bare text as the reader counts it
    (`vocalize.base.strip_nikkud`), not into `bare` above.

    The two bare forms differ: `bare` drops the maqaf and the sof pasuq with the points,
    and the reader keeps them, so a word after a maqaf would be marked a letter early.
    Every letter survives both, so each word is carried across by its first and last
    letter (targum-internal#202). `ref` is the Hebrew verse's, prefixed `Onkelos `, which
    is what lets the verse's own names answer.
    """
    from ..vocalize.base import strip_nikkud

    _, to_bare = strip_nikkud(text)
    # The points go; the maqaf, the sof pasuq and the paseq — punctuation inside the same
    # range — stand as a space instead. Dropped with the points, על־אפי read as one word.
    kept: list[int] = []
    letters: list[str] = []
    for i, char in enumerate(text):
        if _POINTS.match(char):
            if unicodedata.category(char) == "Mn":
                continue
            char = " "
        kept.append(i)
        letters.append(char)
    stripped = "".join(letters)
    segment = Segment(
        id="beside", block_id="beside", block_index=0, index=0, text=stripped, ref=ref
    )
    out: list[Token] = []
    for token in tokens(segment):
        start = to_bare[kept[token.start]]
        end = to_bare[kept[token.end - 1]] + 1
        out.append(token.model_copy(update={"start": start, "end": end}))
    return out
