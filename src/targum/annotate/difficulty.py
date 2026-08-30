"""How hard a text is, counted rather than judged.

The share of running words whose dictionary form is uncommon in the language as it is
written today — bands 4 to 6 of the reader's own six-band scale, which is where a learner
starts looking things up. Psalms comes out at 35, Genesis at 23, Esther at 17, and that
is the order any Hebrew reader would put them in.

This was `scripts/measure_difficulty.py` and is here because the weekly needs it: an
issue is measured before it may be published, that runs from the installed package, and
a script outside the wheel cannot be imported from one. The script still owns the
catalogue sweep — minutes of Stanza over a hundred thousand words, which no reader should
ever wait for — and now imports the counting from here so there is one definition of the
number the library filters on.

**One ruler for everything.** A Tanakh is banded against the Tanakh when it is read —
that is the honest question for somebody reading scripture, and `biblical.py` explains
why. It is the wrong ruler here: a library that mixes Samuel with a news article cannot
rank them on two scales and call the result a difficulty. So every text is re-banded
against modern frequency, and the register filter is what says which Hebrew it is in.

**Two things it does not measure:** sentence length and syntax, both of which make
Brenner read harder than his vocabulary suggests. The number is about words, and the
library's column is labelled "Looked up" rather than "Difficulty" for exactly that
reason.
"""

from __future__ import annotations

from collections import Counter
from functools import lru_cache

from ..models import Annotation
from .base import NOT_VOCABULARY
from .frequency import FrequencyBands

#: Where a word stops being one a reader knows and starts being one they look up.
LOOKED_UP = 4

_bands = FrequencyBands()


@lru_cache(maxsize=200_000)
def band_of(lemma: str, language: str) -> int:
    return _bands.band(lemma, language)


def hard_share(annotation: Annotation, language: str) -> int:
    """The percentage of running words a learner would have to look up."""
    counts: Counter[int] = Counter()
    for tokens in annotation.tokens.values():
        for token in tokens:
            # The same rule the server applies to an upload: a name is a token the
            # reader can tap, not a word they have to learn. News is full of them, which
            # is why real journalism measures low on this scale despite reading hard.
            if token.pos in NOT_VOCABULARY:
                continue
            counts[band_of(token.lemma, language)] += 1
    total = sum(counts.values())
    if not total:
        return 0
    return round(sum(n for band, n in counts.items() if band >= LOOKED_UP) / total * 100)
