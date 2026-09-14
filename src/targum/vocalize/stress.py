"""Russian stress marks, placed only where two sources agree.

Russian writes no stress, and a learner cannot read it off the letters: рука́ is ру́ку in
the accusative, and за́мок and замо́к are two words spelled the same. Textbooks print an
acute over the stressed vowel, and a reader that does the same takes away the half of
pronunciation the spelling hides.

**A wrong mark is worse than none.** At least one word in thirteen of running Russian has
ambiguous stress, and learners take a printed mark as settled (Reynolds & Tyers 2015,
targum-internal#260). So nothing here is marked on one source's say-so:

- **silero-stress** proposes, for every word of the sentence, homographs included
  (MIT, weights in its wheel; its training data is not disclosed, which `LICENSING.md`
  records, and David accepted on 2026-09-14).
- **OpenRussian's tables** confirm (`annotate/openrussian.py`): the stressed spellings the
  dictionary gives the same letters. Where the word was tagged, only the spellings its
  own table gives for its case and number count, which is what settles руки́ from ру́ки.
- A word is marked only where the tables allow one stress for it and silero put the
  stress there. A word of one vowel is never marked, as no textbook marks one, and a word
  with ё needs none. Everything else — a name, a word the tables do not have, a homograph
  the tagging did not settle — is left as it was written.

**The letters never change.** The acute is U+0301, a combining mark after the vowel; ё
restored where both sources agree is е followed by U+0308, which renders as ё and strips
back to е. That is what lets the reader's vowel toggle carry stress unchanged: every
offset is measured against the bare text, and the marked form is the same letters with
marks between them. Nothing after this stage may normalise to NFC, which would fuse е and
U+0308 into one letter.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from ..annotate.openrussian import ACUTE, Lexicon, fold, stressed_syllable
from ..models import Token

DIAERESIS = "̈"
#: The marks this stage writes. A Russian source may carry the acute itself, and those
#: are the source's own stress, kept.
MARKS = frozenset({ACUTE, DIAERESIS})
VOWELS = frozenset("аеёиоуыэюяАЕЁИОУЫЭЮЯ")
#: A Cyrillic word, without the marks that may sit inside one.
WORD = re.compile(r"[А-Яа-яЁё" + ACUTE + DIAERESIS + r"]+")


@dataclass(frozen=True)
class Proposal:
    """What silero said about one word: the stressed vowel's position in the word, and
    where it would write ё. Positions are character offsets into the word as written."""

    stress: int | None
    yo: tuple[int, ...] = ()


def read_proposal(original: str, accented: str) -> dict[int, Proposal] | None:
    """silero's sentence, `+` before each stressed vowel and ё where it restored one,
    read back onto the original text's words by position.

    None where the two do not line up letter for letter — silero is asked about the
    sentence exactly as written and must hand back exactly those letters, and a sentence
    where it did not is left unmarked rather than marked in the wrong places.
    """
    letters: list[str] = []
    stressed: set[int] = set()
    for char in accented:
        if char == "+":
            stressed.add(len(letters))
        else:
            letters.append(char)
    if len(letters) != len(original):
        return None
    for mine, theirs in zip(original, letters, strict=True):
        if mine != theirs and not (mine in "еЕ" and theirs in "ёЁ"):
            return None
    out: dict[int, Proposal] = {}
    for match in WORD.finditer(original):
        start, end = match.span()
        stress = next((at - start for at in sorted(stressed) if start <= at < end), None)
        yo = tuple(
            at - start for at in range(start, end) if original[at] in "еЕ" and letters[at] in "ёЁ"
        )
        out[start] = Proposal(stress, yo)
    return out


def _vowel_index(word: str, position: int) -> int:
    return sum(char in VOWELS for char in word[:position])


def _candidates(
    word: str, lexicon: Lexicon, token: Token | None
) -> tuple[set[int | None], set[tuple[int, ...]]]:
    """The stressed syllables, and the ё positions, the tables allow these letters."""
    spellings: Iterable[str] = lexicon.spellings.get(fold(word), set())
    if token is not None and token.feats and "Case=" in token.feats:
        # Tagged: only what the word's own table gives for its case and number. An
        # untagged or unfound form falls back to every spelling of the letters.
        own = [form.replace(ACUTE, "'") for form in lexicon.form(token.lemma, token.feats)]
        own = [form for form in own if fold(form) == fold(word)]
        if own:
            spellings = own
    syllables: set[int | None] = set()
    yos: set[tuple[int, ...]] = set()
    for written in spellings:
        syllables.add(stressed_syllable(written))
        yos.add(tuple(i for i, char in enumerate(written.replace("'", "")) if char in "ёЁ"))
    return syllables, yos


def mark(
    text: str,
    proposals: dict[int, Proposal],
    lexicon: Lexicon,
    tokens: Sequence[Token] = (),
) -> str:
    """The text with a stress mark on every word both sources agree about, and nothing
    else changed."""
    by_start = {token.start: token for token in tokens}
    out: list[str] = []
    cursor = 0
    for match in WORD.finditer(text):
        start, end = match.span()
        out.append(text[cursor:start])
        cursor = end
        word = text[start:end]
        proposal = proposals.get(start)
        vowels = sum(char in VOWELS for char in word)
        token = by_start.get(start)
        # A name is not in a dictionary's sense of a word — Кале the town is not кале — and
        # the first half of светло-фиолетовый carries no stress of its own.
        named = token is not None and token.pos == "PROPN"
        halved = text[end : end + 1] == "-"
        if proposal is None or named or halved or any(c in MARKS for c in word) or not vowels:
            out.append(word)
            continue
        syllables, yos = _candidates(word, lexicon, token)
        if not syllables:
            out.append(word)
            continue
        letters = list(word)
        # ё, where the word has none written, the tables allow exactly one placement of
        # it, and silero put it there.
        restored = False
        if "ё" not in word and "Ё" not in word and proposal.yo and yos == {proposal.yo}:
            for at in proposal.yo:
                letters[at] = letters[at] + DIAERESIS
            restored = True
        has_yo = restored or "ё" in word or "Ё" in word
        if (
            vowels > 1
            and not has_yo
            and proposal.stress is not None
            and len(syllables) == 1
            and syllables == {_vowel_index(word, proposal.stress)}
        ):
            letters[proposal.stress] = letters[proposal.stress] + ACUTE
        out.append("".join(letters))
    out.append(text[cursor:])
    return "".join(out)
