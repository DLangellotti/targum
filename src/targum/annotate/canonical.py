"""One spelling per word, so a vocabulary key does not depend on which sentence it was met in.

A saved word is stored under its dictionary form, and that string is the key. So the
lemma is not only something a reader reads — it is an identity. Two spellings of one word
are two entries, two counts, and two things to mark known.

This is not hypothetical. Measured over Genesis 1, `dictabert-lex` returns `כל` four times
and `כול` four times, for the same word, in the same chapter. Under a modern-normalised
key that splits the commonest word in Hebrew into two vocabulary entries before a reader
has finished the first page of the Torah.

**Two different jobs, and only one of them is mechanical.**

*Stripping the pointing* is mechanical and always right: `שָׁמַ֖יִם` and `שמים` are the same
letters and the marks are a reading aid. `vocalize.strip_nikkud` already does exactly this
and is reused rather than reimplemented — one definition of which codepoints are marks.

*Folding ktiv variants* is not mechanical, because the difference is in the letters
themselves. `שמים` and `שמיים` differ by a yod; so do `ספר` and `ספור`, which are two
different words. There is no rule that separates the first pair from the second without
knowing what the words are, and a rule that guesses would quietly merge unrelated
vocabulary — which is worse than splitting one word, because a reader cannot see it happen.

So the folding is a table, it holds only pairs there is evidence for, and it grows by
measurement. `candidates()` is how the evidence is found; nothing is added to `SAME_WORD`
because it looked plausible.

This also does the second job the corpus needs. A biblical headword out of the Open
Scriptures morphology (`שָׁמַיִם`) and a modern lemma out of DICTA (`שמיים`) have to land on
the same key or the one-vocabulary-across-registers claim is not true. Both go through
here, which is what makes them meet.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable

from ..vocalize.base import LETTERS, strip_nikkud

#: Written between words in the Masoretic text and inside some compounds. Not a letter,
#: and a lemma is never one.
MAQAF = "־"

#: Ktiv variants that are the same word, kept as a table because nothing distinguishes
#: them from a genuine pair by shape alone.
#:
#: Each entry is `variant -> canonical`, and the canonical side is the spelling a reader
#: is more likely to meet, decided on written frequency rather than on the Academy's
#: rules: a vocabulary page is a place somebody recognises a word, not a place they are
#: taught to spell it.
#:
#: Seeded from what the annotator actually produced on the shelf rather than from a list
#: of things that might happen. `כול` is here because Genesis 1 alone yielded it four
#: times beside four of `כל`.
SAME_WORD: dict[str, str] = {
    "כול": "כל",
}


def bare(lemma: str) -> str:
    """The letters, with the pointing and everything that is not a letter removed.

    Mechanical and always safe. The maqaf goes because it joins words rather than
    belonging to one; the geresh and gershayim go because they mark an abbreviation or a
    foreign sound and never distinguish two lemmas from each other.
    """
    stripped, _ = strip_nikkud(unicodedata.normalize("NFC", lemma or ""))
    return "".join(ch for ch in stripped if ord(ch) in LETTERS)


def canonical(lemma: str) -> str:
    """The one spelling this word is filed under.

    An empty answer where there is nothing to file — a lemma of pure punctuation, or the
    empty string — so a caller can tell "no word here" from "a word spelled oddly".
    """
    letters = bare(lemma)
    return SAME_WORD.get(letters, letters)


def candidates(pairs: Iterable[tuple[str, str]]) -> dict[str, set[str]]:
    """Surfaces that were given more than one lemma, and what they were given.

    How `SAME_WORD` earns a new row. Feed it every `(surface, lemma)` an annotator
    produced over a corpus; what comes back is every word the annotator could not spell
    the same way twice. Each one is then a judgement somebody makes, not a rule this
    file applies — the same surface can honestly take two lemmas where the word really is
    ambiguous, and telling that apart is what a person is for.
    """
    seen: dict[str, set[str]] = {}
    for surface, lemma in pairs:
        key = bare(surface)
        value = canonical(lemma)
        if not key or not value:
            continue
        seen.setdefault(key, set()).add(value)
    return {surface: forms for surface, forms in seen.items() if len(forms) > 1}
