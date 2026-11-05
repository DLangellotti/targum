"""The words to know first on Home's one card (design.md §12, "Home's one card offers the
words to learn first, and a pick moves easier or harder", 2026-11-05; targum-internal#614).

A pick near the floor is easier to read with a few of its words met before it. ling-he's
research (2026-10-31) puts the useful number at three to five, and the useful words at
the ones that come back: a word met once in a text is not worth the reader's minute, and
a word met five times is the one they will be stuck on five times.

So the list is the pick's own words the reader does not know that come up at least
`LEAST_TIMES` times in it, most often first, at most `MOST`. Fewer than `LEAST_WORDS` and
there is no list. Its counts are the text's own running words (`coverage.Index.counts`
for a library text, `finds.pool.Find.bag` for a web find), and "does not know" is the
chooser's own reading of the reader (`estimate.Estimate.p_known`): a mark wins, and an
unmarked word counts as unknown where its chance of being known is under a half.

Two kinds of noise are left out, which the mocks met on real texts: a name the tagger
missed (שיבא, the hospital, in the Sharon obituary) and a misread lemma. Neither has a
meaning a reader can learn, so a word goes on the list only with a meaning beside it,
and a meaning that reads as a name (a capital first letter, in a reading language that
writes common words in lower case) is taken for one.

Nothing here spends: a meaning is one the glossary already holds, never one bought.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

#: A word comes up at least this often in the pick to be worth learning first.
LEAST_TIMES = 3
#: The most the list shows.
MOST = 5
#: Fewer than this, and there is no list at all.
LEAST_WORDS = 3
#: "Near the floor": a pick whose share known is under this, in whole points. It is the
#: bottom of the band's harder aim, and every Harder pick is under it.
UNDER = 93
#: An unmarked word whose chance of being known is under this counts as unknown.
UNKNOWN_UNDER = 0.5


@dataclass(frozen=True, slots=True)
class Word:
    """One line of the list: the dictionary form the reader's ledger files it under, its
    meaning in the reader's language, and how often it comes up in the pick."""

    lemma: str
    meaning: str
    count: int

    def state(self) -> dict[str, object]:
        return {"lemma": self.lemma, "meaning": self.meaning, "count": self.count}


def recurring(
    counts: Mapping[str, int],
    p_known: Callable[[str], float | None],
    a_word: Callable[[str], bool] = lambda lemma: True,
) -> list[tuple[str, int]]:
    """The pick's unknown forms that come up at least `LEAST_TIMES` times, most often
    first, the form breaking a tie so the order is the same on every ask."""
    out: list[tuple[str, int]] = []
    for lemma, n in counts.items():
        if n < LEAST_TIMES or not lemma or not a_word(lemma):
            continue
        chance = p_known(lemma)
        # None is a word the reader ignored: out of every list, as it is out of every count.
        if chance is None or chance >= UNKNOWN_UNDER:
            continue
        out.append((lemma, int(n)))
    out.sort(key=lambda one: (-one[1], one[0]))
    return out


def looks_like_a_name(meaning: str) -> bool:
    """Whether a meaning reads as a name: its first letter a capital. The glossary writes
    a common word's sense in lower case in English and Russian alike ("to command",
    "командовать"), and a name's with its capital ("Sheba Medical Center")."""
    for char in meaning.strip():
        if char.isalpha():
            return char.isupper()
    return False


def words(
    counts: Mapping[str, int],
    p_known: Callable[[str], float | None],
    meaning_of: Callable[[str], str],
    a_word: Callable[[str], bool] = lambda lemma: True,
) -> list[Word]:
    """The list for one pick: at most `MOST` words with a meaning that is not a name, or
    nothing where fewer than `LEAST_WORDS` are left."""
    out: list[Word] = []
    for lemma, n in recurring(counts, p_known, a_word):
        meaning = (meaning_of(lemma) or "").strip()
        if not meaning or looks_like_a_name(meaning):
            continue
        out.append(Word(lemma, meaning, n))
        if len(out) >= MOST:
            break
    return out if len(out) >= LEAST_WORDS else []
