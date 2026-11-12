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
import threading
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
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


def band_of(lemma: str, language: str) -> int:
    """The band a lemma falls in, in a language.

    French is keyed on whether Morphalou was there to sum it (targum-internal#682): a band
    measured without the lexicon is never the answer once the lexicon has arrived, so a
    service that started before `targum models fetch morphalou` finished picks it up on
    its next French word, without a restart.
    """
    french_summed = language.split("-")[0].lower() == "fr" and _french_sums() is not None
    return _band_of(lemma, language, french_summed)


@lru_cache(maxsize=200_000)
def _band_of(lemma: str, language: str, french_summed: bool) -> int:
    code = language.split("-")[0].lower()
    if code == "arc":
        # wordfreq has no Aramaic, so every Aramaic text measured 0. The shelf's own
        # Aramaic is counted instead (targum-internal G1); without the list on disk a
        # word is unrated, as before.
        from . import aramaic_frequency

        if aramaic_frequency.available():
            return aramaic_frequency.band(lemma)
    if code == "ru":
        summed = russian_zipf(lemma)
        if summed is not None:
            return band_for(summed)
    if code == "fr" and french_summed:
        total = french_zipf(lemma)
        if total is not None:
            # Never harder than the dictionary form alone: a share of a form another
            # lemma also owns can leave a lemma below its own spelling (été the summer,
            # whose été is mostly être's), and the sum is here to undo an undercount.
            return min(band_for(total), _bands.band(lemma, language))
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


def french_zipf(lemma: str) -> float | None:
    """A French lemma's frequency as the sum of its forms in Morphalou, or None where this
    machine has not fetched Morphalou or the lemma is not in it.

    **Why** (targum-internal#562, measured 2026-11-05): the same undercount Russian had.
    wordfreq counts written forms, and a French verb is read as était, fait, dit, vient,
    so its infinitive looks rarer than the verb is — sembler and demeurer at band 4,
    falloir at 3. On the fourteen texts of the French shelf 23.5% of verb tokens counted
    as looked up by the infinitive and 11.6% by the sum, and every text read 1 to 5
    points easier, the Maupassant tales most. No text there changes level, since all
    fourteen are under the Simplified ceiling and are placed by sentence length; an Easy
    French text, under a ceiling of 15, is where the undercount would have bitten, as it
    did for the Russian Storybooks.

    **A form two lemmas own is shared by how common each lemma is**, not given whole to
    each: Morphalou lists lui under luire and tu under taire, and summed whole those two
    rare verbs came out as common as the pronouns. Each owner takes the form's frequency
    in proportion to its own dictionary form's, so luire keeps almost none of lui and
    suivre a few percent of suis. Where wordfreq saw none of the owners' spellings, they
    split it evenly.

    **A form one lemma owns can still be another word's**: luis is mostly the name Luis,
    and taken whole it put luire at band 4. A form more than `ANOTHER_WORDS` times
    commoner than anything else its lemma is read as is left out, so luire is band 5,
    from its luit and its share of lui.

    A lookup only (LGPL-LR, David 2026-09-14): the table is read where
    `targum models fetch morphalou` put it, nothing is trained on it, and no row of it
    is in the repository. Only the difficulty measure, as for Russian: the bands a
    reader's card shows are the annotation's and are left alone.
    """
    sums = _french_sums()
    if sums is None:
        return None
    total = sums.get(_french_key(lemma))
    if not total:
        return None
    return math.log10(total * 1e9)


def _french_key(word: str) -> str:
    from . import morphalou

    return morphalou._bare_lemma(word)


#: The sums, once they are made: never None, so a lexicon that was missing is looked for
#: again on the next call rather than remembered as missing (targum-internal#682).
_FRENCH_SUMS: dict[str, float] | None = None
_FRENCH_SUMS_LOCK = threading.Lock()


def _french_sums() -> dict[str, float] | None:
    """Every French lemma's summed frequency, or None where this machine has no Morphalou
    (or no wordfreq) yet.

    Only a table that was read is kept. deploy.sh restarts the service before it fetches
    Morphalou, so on a fresh or restored box the first French texts are measured before
    the table lands; remembering that absence kept French without Morphalou until the
    next restart. A miss costs one `stat` per call.
    """
    global _FRENCH_SUMS
    if _FRENCH_SUMS is not None:
        return _FRENCH_SUMS
    from . import morphalou

    if not morphalou.available():
        return None
    try:
        from wordfreq import get_frequency_dict
    except ImportError:
        return None
    path = morphalou.directory() / morphalou.TABLE

    def lines() -> Iterable[str]:
        with path.open(encoding="utf-8", newline="") as handle:
            yield from (line.rstrip("\r\n") for line in handle)

    # One reading of the table at a time: two threads that both found it missing a moment
    # ago would otherwise each read 106 MB twice over.
    with _FRENCH_SUMS_LOCK:
        if _FRENCH_SUMS is None:
            _FRENCH_SUMS = french_sums(lines, get_frequency_dict("fr"))
        return _FRENCH_SUMS


def french_sums(
    lines: Callable[[], Iterable[str]], frequency: Mapping[str, float]
) -> dict[str, float]:
    """Each lemma's share of the frequency of every form Morphalou lists for it.

    `lines` is called twice, once to weigh who owns each form and once to share it out,
    so the table is never held in memory: only a weight per form, and a sum per lemma.
    Reflexive lemmas are counted with their bare verb (se taire is taire), and a form of
    more than one word (se taire itself) is left out, wordfreq having no such word.
    """
    owners: dict[str, float] = {}
    counted: dict[str, int] = {}
    for key, forms in _french_blocks(lines()):
        weight = frequency.get(key, 0.0)
        for form in forms:
            owners[form] = owners.get(form, 0.0) + weight
            counted[form] = counted.get(form, 0) + 1
    sums: dict[str, float] = {}
    for key, forms in _french_blocks(lines()):
        weight = frequency.get(key, 0.0)
        alone = {form: frequency.get(form, 0.0) for form in forms if counted[form] == 1}
        share = 0.0
        for form in forms:
            used = frequency.get(form, 0.0)
            if not used:
                continue
            if form != key and form in alone:
                # A form only this lemma owns, far commoner than anything else the lemma
                # is read as, is another word's: luis is the name Luis, not luire's, and
                # minutes the noun's plural, not minuter's. It is left out, and so is one
                # where wordfreq saw nothing else of the lemma at all (hui is not huir's).
                rest = max((n for other, n in alone.items() if other != form), default=weight)
                rest = max(rest, weight)
                if used > ANOTHER_WORDS * rest:
                    continue
            # A form two lemmas own is shared by each one's own frequency; where wordfreq
            # saw none of their spellings, it is split evenly, never counted whole twice.
            whole = owners[form]
            share += used * (weight / whole if whole else 1.0 / counted[form])
        if share:
            sums[key] = sums.get(key, 0.0) + share
    return sums


#: How much commoner than the rest of its lemma's own forms a form may be and still be
#: taken as that lemma's (`french_sums`). semble is 5.4 times semblent, fallait 2.9
#: times falloir and suffit 13 times suffire's next form; luis is 33 times luit, importe
#: 53 times importer (n'importe) and minutes 3,000 times minuter (wordfreq, 2026-11-05).
ANOTHER_WORDS = 20.0


def _french_blocks(lines: Iterable[str]) -> Iterable[tuple[str, set[str]]]:
    """(lemma, its distinct one-word forms in lower case), one per lemma of the table."""
    from . import morphalou

    current, key = "", ""
    forms: set[str] = set()
    for lemma, _category, form, _grammar, _phonetic in morphalou.rows(lines):
        if lemma != current:
            if forms:
                yield key, forms
            current, key = lemma, _french_key(lemma)
            forms = {key} if " " not in key else set()
        written = form.lower().translate(_APOSTROPHES)
        if written and " " not in written:
            forms.add(written)
    if forms:
        yield key, forms


_APOSTROPHES = str.maketrans({"’": "'", "ʼ": "'"})


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
