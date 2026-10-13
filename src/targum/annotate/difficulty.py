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

**Sentence length is measured beside it now, and separately** (`sentence_length`,
targum-internal#382). Not folded into the share: the two answer different questions, and
the weekly learned that only the second one separates its first two levels — the easy
edition measured 15% and the simplified one 14%, the wrong way round, while their
sentences came out at 6.7 and 11.4 words. It lived inside the weekly's gauge until the
library needed the same number to say which of its texts a beginner could finish.
"""

from __future__ import annotations

import math
from collections import Counter
from functools import lru_cache
from typing import Any

from ..models import Annotation, BlockKind, SegmentedDocument
from .base import BAND_COUNT, not_vocabulary
from .frequency import CUTS, FrequencyBands

#: Where a word stops being one a reader knows and starts being one they look up.
LOOKED_UP = 4

_bands = FrequencyBands()

#: Blocks that are nobody's sentence. A title and a byline are the same few words in
#: every text, so counting them pulls every mean toward every other; the weekly drops its
#: headlines for the same reason before it segments.
NOT_SENTENCES = frozenset({BlockKind.heading, BlockKind.byline})


@lru_cache(maxsize=200_000)
def band_of(lemma: str, language: str) -> int:
    if language.split("-")[0].lower() == "ru":
        summed = russian_zipf(lemma)
        if summed is not None:
            return band_for(summed)
    return _bands.band(lemma, language)


def band_for(score: float) -> int:
    """The band a Zipf score falls in, on the reader's own cuts."""
    for index, cut in enumerate(CUTS, start=1):
        if score >= cut:
            return index
    return BAND_COUNT


#: The parses whose forms are counted for one lemma, at most: a word with many readings
#: is summed for its likeliest few, which is where its frequency is.
_PARSES = 4


@lru_cache(maxsize=200_000)
def russian_zipf(lemma: str) -> float | None:
    """A Russian lemma's frequency as the sum of all its forms, or None where this machine
    cannot inflect Russian (no `russian` extra) or the lemma is no word pymorphy3 knows.

    **Why** (2026-10-13): wordfreq counts written forms, and the difficulty looked up the
    dictionary form alone. A Russian lemma's use is spread over a dozen forms or more, so
    its citation form looks rare — мочь at Zipf 2.63 against могу and может everywhere,
    хотеть 3.80, кошка 4.07 — and Russian measured 12 to 15 points too hard: 4 of 20
    level 1–2 Global Storybooks and none of 15 Bloom grade-1 readers placed Easy, and
    Bloom's "Почему жужжат пчелы?" scored 36 against 19 for the same book in Italian.
    Summed over its forms (and the ё-less spellings, which wordfreq keeps apart), 18 of
    the 20 place Easy and Russian sits beside Italian (scratchpad ruler report,
    targum-internal languages/ru.md).

    Only the difficulty measure: the bands a reader's card shows are the annotation's
    and are left alone, so nothing is re-annotated and only the catalogue needs a sweep.
    The parse whose forms sum highest is taken, so мочь counts as the verb.
    """
    try:
        import pymorphy3
        from wordfreq import word_frequency
    except ImportError:
        return None
    analyser = _morph(pymorphy3)
    word = lemma.lower()
    best = 0.0
    for parse in analyser.parse(word)[:_PARSES]:
        if parse.normal_form.replace("ё", "е") != word.replace("ё", "е"):
            continue
        forms = {form.word for form in parse.lexeme}
        forms |= {form.replace("ё", "е") for form in forms}
        best = max(best, sum(word_frequency(form, "ru") for form in forms))
    if best <= 0:
        return None
    return math.log10(best * 1e9)


@lru_cache(maxsize=1)
def _morph(pymorphy3: Any) -> Any:
    return pymorphy3.MorphAnalyzer()


def hard_share(annotation: Annotation, language: str) -> int:
    """The percentage of running words a learner would have to look up."""
    counts: Counter[int] = Counter()
    # A block in another language than the document's has no tokens at all — the
    # annotator leaves it unread rather than reading Aramaic as Hebrew — so it counts for
    # nothing here, and Daniel is measured on its Hebrew. Not a rule of this function
    # but of the annotation, and said here because a reader of this number would
    # otherwise wonder where the Aramaic went.
    for tokens in annotation.tokens.values():
        for token in tokens:
            # The same rule the server applies to an upload: a name is a token the
            # reader can tap, not a word they have to learn. News is full of them, which
            # is why real journalism measures low on this scale despite reading hard.
            if not_vocabulary(token.pos, token.entity):
                continue
            counts[band_of(token.lemma, language)] += 1
    total = sum(counts.values())
    if not total:
        return 0
    return round(sum(n for band, n in counts.items() if band >= LOOKED_UP) / total * 100)


def sentence_length(segmented: SegmentedDocument) -> float:
    """Mean words per sentence, to one place, or 0.0 where there is no sentence at all.

    Words are split on whitespace, the way the weekly has always counted them, so a
    Hebrew prefix stays part of its word and the number is comparable across languages
    only roughly — which is enough for a band four words wide. Off the segmentation a
    build already made, so it is free: nothing is fetched and no model is asked.
    """
    sentences = [
        segment
        for segment in segmented.segments
        if segment.kind not in NOT_SENTENCES and segment.text.strip()
    ]
    if not sentences:
        return 0.0
    words = sum(len(segment.text.split()) for segment in sentences)
    return round(words / len(sentences), 1)
