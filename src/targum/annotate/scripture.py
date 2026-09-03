"""Tokens for the Hebrew Bible, taken from the hand tagging rather than worked out.

`ScriptureLemmatizer` is a `Lemmatizer` like any other, so nothing above it knows the
difference: it answers `lemmas()` with tokens carrying offsets, a dictionary form, a part
of speech and how the word is built. What is different is where the answers come from. For
a verse of the Tanakh they are looked up in the Open Scriptures morphology; for everything
else — and for any verse the lookup cannot line up — they come from the lemmatizer this
one wraps.

**Falling through is normal and has to stay cheap.** Most of what targum reads is not the
Hebrew Bible, and the Mishnah on the shelf is Hebrew but not this Hebrew. A wrapper that
made those paths worse to make one path better would be a bad trade, so the fallback is
the whole of the previous behaviour, unchanged, reached by one dictionary miss.

**Why the alignment can fail, and why that is fine.** Measured over 5,436 verses of
Genesis, Isaiah, Psalms and Ruth, 99.34% line up token for token. The rest differ for
reasons that are real rather than mysterious — a verse the editions divide differently, a
word one of them spells with a maqaf and the other without — and on those the model
answers, exactly as it does today. The point of the lookup is not that it is total; it is
that where it applies it is not guessing.
"""

from __future__ import annotations

import collections
import re
import unicodedata
from collections.abc import Iterable

from ..models import Segment, Token
from . import oshb
from .base import Lemmatizer
from .canonical import canonical
from .hebrew import ENDINGS, FINALS

#: Sefaria writes a word the Masoretes read differently as `ketiv [qere]` — both forms,
#: the read one bracketed. The morphology carries one word there, so a comparison that
#: counted both would find every such verse one token too long. It accounted for 139 of
#: the 143 misalignments in the first measurement, and reading it took the shelf from
#: 97.4% aligned to 99.3%.
_QERE = re.compile(r"\S+\s+\[([^\]]+)\]")

#: Paragraph markers, which are typography rather than words.
_SECTION = {"פ", "ס", "פפפ"}


def _bare(text: str) -> str:
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFC", text or "") if not unicodedata.combining(ch)
    )
    return re.sub(r"[^א-ת]", "", stripped)


def _headword(text: str) -> str:
    """A dictionary form with its spaces kept.

    Most headwords are one word and this is `_bare` with extra steps. A few are not:
    Strong's 1035 is `בֵּית לֶחֶם`, one lexeme written as two words, and the tagging gives
    that headword to both halves of the place name. Stripping everything that is not a
    letter turned it into `ביתלחם`, which is not how anybody writes Bethlehem and is what
    a card would have shown.

    One lexeme is one vocabulary entry, so the space stays and the entry is the place.
    """
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFC", text or "") if not unicodedata.combining(ch)
    )
    kept = re.sub(r"[^א-ת ]", "", stripped)
    return re.sub(r"\s+", " ", kept).strip()


#: What the morphology calls a part of speech, as the rest of targum names one. The codes
#: are positional and only the first letter decides the class, which is why this reads one
#: character rather than parsing the whole string.
_PART = {
    "A": "ADJ",
    "C": "CCONJ",
    "D": "ADV",
    "N": "NOUN",
    "P": "PRON",
    "R": "ADP",
    "S": "PRON",
    "T": "PART",
    "V": "VERB",
}

#: A proper noun is a noun whose second letter says so, and targum leaves names out of
#: vocabulary counts — so getting this wrong would rate every name in a chronicle.
_PROPER = "Np"

_GENDER = {"m": "Masc", "f": "Fem", "b": "Masc,Fem", "c": "Masc,Fem"}
_NUMBER = {"s": "Sing", "p": "Plur", "d": "Dual"}
_PERSON = {"1": "1", "2": "2", "3": "3"}

#: The verb stem, which is the binyan, as the reader already names one. The letter sits
#: second in a verb code — `Vqp3ms` is qal — and it is the fact the modern annotator has
#: to guess at from spelling and this one simply has (targum-internal#116).
#:
#: The seven are 98% of the verbs in the corpus. The rest are the rarer stems — polel,
#: pilpel, qal passive and the Aramaic ones the code cannot be told apart from Hebrew
#: once the language letter is stripped — and they are left unmapped rather than pushed
#: into the nearest of the seven. A verb with no binyan still gets its root, because the
#: root here is read from the lexicon and not worked out from the pattern.
_STEMS = {
    "q": "פעל",
    "N": "נפעל",
    "p": "פיעל",
    "P": "פועל",
    "h": "הפעיל",
    "H": "הופעל",
    "t": "התפעל",
}

#: The aspect letter, third in a verb code, as tense and verb form. The waw-consecutive
#: is read as what it means rather than as what it is spelled: `Vqw3ms` — the form that
#: carries biblical narrative — is past, and calling it imperfect would tell a learner
#: that ויאמר is "he will say".
_ASPECTS: dict[str, tuple[str, str]] = {
    "p": ("Past", "Fin"),
    "q": ("Past", "Fin"),
    "i": ("Fut", "Fin"),
    "w": ("Past", "Fin"),
    "h": ("", "Fin"),
    "j": ("", "Fin"),
    "v": ("", "Fin"),
    "r": ("Pres", "Part"),
    "s": ("", "Part"),
    "a": ("", "Inf"),
    "c": ("", "Inf"),
}

#: A participle writes no person, so its gender and number sit two places earlier than a
#: finite verb's — `Vhrmsa` is masculine singular, and reading it on the finite layout
#: found a person where there was none and a gender in the number's place. Every
#: participle in the Tanakh came out with no morphology at all until this was split out.
_PARTICIPLE = frozenset("rs")
_INFINITIVE = frozenset("ac")

#: Where person, gender and number sit inside a code, per class. **Positional, and read
#: positionally**, which is the whole of the difficulty: the letters mean different things
#: in different places and several of them collide.
#:
#: `Vqp3ms` is a verb, qal stem, *perfect* aspect, 3rd masculine singular — and reading it
#: as a bag of letters finds the `p` of "perfect" in the number table and calls the word
#: plural. `Ncfsa` is a noun, *common*, feminine singular absolute, and the same mistake
#: reads the `c` of "common" as a gender. Both were live in the first draft of this file.
#:
#: Index 0 is the class letter, so every offset below counts from there.
_LAYOUT: dict[str, tuple[int | None, int | None, int | None]] = {
    # class:      person, gender, number
    "V": (3, 4, 5),  # finite verb: stem, aspect, then the three. See `_verb_layout`.
    "N": (None, 2, 3),  # noun: type, gender, number, state
    "A": (None, 2, 3),  # adjective, same shape as a noun
    "P": (2, 3, 4),  # pronoun: type, then the three
    "S": (2, 3, 4),  # suffix, same shape as a pronoun
}


def part_of(code: str) -> str | None:
    """The part of speech one morphology code names."""
    if not code:
        return None
    if code.startswith(_PROPER):
        return "PROPN"
    return _PART.get(code[0])


def _at(code: str, index: int | None, table: dict[str, str]) -> str | None:
    if index is None or index >= len(code):
        return None
    return table.get(code[index])


def _verb_layout(code: str) -> tuple[int | None, int | None, int | None]:
    """Where person, gender and number sit in a verb code, which the aspect decides."""
    aspect = code[2] if len(code) > 2 else ""
    if aspect in _INFINITIVE:
        return (None, None, None)
    if aspect in _PARTICIPLE:
        return (None, 3, 4)
    return _LAYOUT["V"]


def binyan_of(code: str) -> str | None:
    """The binyan a verb code names, or None for anything that is not one of the seven.

    The stem is the second letter and is a fact somebody wrote down, which is the whole
    argument for the lookup: on the modern half the same field is derived from how a
    lemma happens to be spelled and is right about one verb in twenty.
    """
    if not code or code[0] != "V" or len(code) < 2:
        return None
    return _STEMS.get(code[1])


def root_of(headword: str) -> str | None:
    """The root of a verb, read off its lexicon entry rather than worked out.

    Strong's numbers a *lexeme*, and for a verb the entry it numbers is the root itself:
    measured over Genesis, Isaiah, Psalms and Ruth, 16,205 of 16,248 verb pieces have a
    three-letter headword, and it is the root whatever pattern the word in front of us is
    in — `מבדיל` is filed under `בדל`, `יקם` under `נקם` with the נ the form does not
    write. Undoing the pattern here, the way the modern path must, would take that apart
    again: `hebrew.root_of("הלך", "התפעל")` strips a ה that belongs to the root and comes
    back two letters short.

    Four letters are kept because Hebrew has quadriliteral roots. Anything else is a
    lexicon entry that is not a root — a phrase, a defective record — and is dropped.
    """
    letters = [ch for ch in _headword(headword).translate(FINALS) if "א" <= ch <= "ת"]
    if len(letters) not in (3, 4):
        return None
    return "".join(letters[:-1]) + letters[-1].translate(ENDINGS)


def features(code: str) -> str | None:
    """The morphology a code carries, in the shape the card reads.

    Person, gender and number, and for a verb its tense and form as well: the reader has
    a line that says "past · he" and it had nothing to say it with on the biblical half.
    Still partial — state and the rest stay in the morphology — but no longer partial in
    a way that leaves a whole register blank.
    """
    if not code:
        return None
    layout = _verb_layout(code) if code[0] == "V" else _LAYOUT.get(code[0])
    if layout is None:
        return None
    person, gender, number = layout
    kept = [
        f"Person={_at(code, person, _PERSON)}" if _at(code, person, _PERSON) else "",
        f"Gender={_at(code, gender, _GENDER)}" if _at(code, gender, _GENDER) else "",
        f"Number={_at(code, number, _NUMBER)}" if _at(code, number, _NUMBER) else "",
    ]
    if code[0] == "V" and len(code) > 2:
        tense, form = _ASPECTS.get(code[2], ("", ""))
        if tense:
            kept.append(f"Tense={tense}")
        if form:
            kept.append(f"VerbForm={form}")
    return "|".join(part for part in kept if part) or None


def _trim(found: re.Match[str], text: str) -> tuple[int, int, str] | None:
    """One run of text as the span of its letters, or None if it holds none."""
    start, end = found.start(), found.end()
    while start < end and not ("א" <= text[start] <= "ת"):
        start += 1
    while end > start and not ("א" <= text[end - 1] <= "ת"):
        end -= 1
    if start >= end:
        return None
    return start, end, _bare(text[start:end])


def built_from(word: oshb.Word) -> str | None:
    """How a split word is put together, said the way the card already says it.

    One piece is not a composition and gets no line, which is the same rule the modern
    path follows.
    """
    if len(word.pieces) < 2:
        return None
    return " + ".join(_bare(piece) for piece in word.pieces if _bare(piece))


class ScriptureLemmatizer:
    """The hand tagging where it reaches, and the wrapped lemmatizer everywhere else."""

    def __init__(self, fallback: Lemmatizer) -> None:
        self.fallback = fallback

    @property
    def name(self) -> str:
        """Both names, because both produced the annotation.

        A text is re-read when this string changes, and a text that was tagged from the
        morphology is a different artefact from one the model guessed at — so the name
        has to say which happened, and the fallback's name has to stay in it because on
        most of the shelf the fallback is what ran.
        """
        return f"oshb/2+{self.fallback.name}"

    def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
        looked_up: dict[str, list[Token]] = {}
        left: list[Segment] = []
        for segment in segments:
            found = self._verse(segment) if language.split("-")[0].lower() == "he" else None
            if found is None:
                left.append(segment)
            else:
                looked_up[segment.id] = found
        if left:
            looked_up.update(self.fallback.lemmas(left, language))
        return looked_up

    def _verse(self, segment: Segment) -> list[Token] | None:
        """One verse from the tagging, or None to let the model have it."""
        tagged = oshb.words(segment.ref)
        if not tagged:
            return None

        # The text as the annotator sees it: bare, because `Annotator` strips the points
        # before it asks. Offsets below are into this string and are mapped back onto the
        # pointed source afterwards by the caller, exactly as they are for the model.
        text = _QERE.sub(lambda found: found.group(1), segment.text)
        # Trimmed to the letters. A verse ends `הָאָרֶץ׃` and the sof pasuq is punctuation:
        # left in, the token's span covers it and the reader highlights a word plus a
        # colon when it is tapped.
        spans = [
            span for span in (_trim(found, text) for found in re.finditer(r"[^\s־]+", text)) if span
        ]
        spans = [span for span in spans if span[2] not in _SECTION]
        wanted = [word for word in tagged if _bare(word.text) not in _SECTION]

        if len(spans) != len(wanted) or any(
            span[2] != _bare(word.text) for span, word in zip(spans, wanted, strict=True)
        ):
            # Different editions of the same verse. Not an error and not worth a line in
            # the log: the model answers, which is what happens today for every verse.
            return None

        out: list[Token] = []
        for (start, end, _), word in zip(spans, wanted, strict=True):
            code = word.code
            lexeme = word.lexeme
            # The headword, not the surface. Where the lexicon has no entry — a handful
            # of prefixes tagged as content — the bare word stands in, so a token always
            # has a dictionary form to be filed under.
            dictionary = oshb.headword(lexeme) or word.pieces[word.content]
            verb = part_of(code) == "VERB"
            out.append(
                Token(
                    start=start,
                    end=end,
                    surface=text[start:end],
                    lemma=_headword(dictionary),
                    band=0,
                    split=len(word.pieces) > 1,
                    pos=part_of(code),
                    binyan=binyan_of(code) if verb else None,
                    root=root_of(dictionary) if verb else None,
                    feats=features(code),
                    built=built_from(word),
                )
            )
        return out


def name_candidates(
    seen: Iterable[tuple[str, str, str]], least: int = 3
) -> dict[tuple[str, str], int]:
    """Spelling pairs worth a person's time, restricted to proper names.

    Feed it `(morphology code, one lemma, the other)` for every word two annotators
    disagreed about. What comes back is the pairs where the word is a **name** and the
    two spellings differ by a single vav or yod.

    **Why only names, and this was learned the expensive way.** A sweep of the whole
    Tanakh for spelling variants produced 2,435 candidates; filtered to "seen three times,
    both forms common, one letter apart" it still produced 193, of which perhaps six were
    real. Among the rejects were `אחות` against `אחת` — sister and one — and `מצוה`
    against `מצה`, commandment and matzah. Both survive every mechanical filter that can
    be written, because both differ by exactly one letter and both forms are ordinary
    Hebrew.

    A name is the one category where that cannot happen. `אהרן` and `אהרון` are Aaron
    either way; there is no second sense hiding behind the vav. So the morphology's own
    proper-noun tag is the safety rail that frequency could not be.

    Still a list for somebody to read, not a set of rows. It is narrower odds, not proof.
    """
    found: dict[tuple[str, str], int] = collections.Counter()
    for code, first, second in seen:
        if not code.startswith(_PROPER):
            continue
        one, two = canonical(first), canonical(second)
        if one == two or not one or not two:
            continue
        if _one_matres(one, two):
            found[tuple(sorted((one, two)))] += 1  # type: ignore[index]
    return {pair: count for pair, count in found.items() if count >= least}


def _one_matres(first: str, second: str) -> bool:
    """Whether two spellings differ by exactly one optional vav or yod."""
    bare_first = first.replace("י", "").replace("ו", "")
    bare_second = second.replace("י", "").replace("ו", "")
    return bare_first == bare_second and bare_first != "" and abs(len(first) - len(second)) == 1
