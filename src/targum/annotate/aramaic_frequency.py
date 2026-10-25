"""How common an Aramaic word is, counted from targum's own Aramaic (targum-internal G1).

wordfreq has no Aramaic list, so the difficulty measure said 0 of every Aramaic text,
which is false, and Aramaic got no ladder (design.md, 2026-10-08). The list here is
counted from the shelf instead — Onkelos, Jonathan, the Targums of the Writings, and the
Aramaic of Daniel and Ezra, all public domain — by `scripts/count_aramaic.py`, under the
same name the annotator files each word under (`aramaic.tokens`): the hand table's
headword where it knows the form, the word's own letters where it does not.

**The same ruler as every other language.** A count is turned into a Zipf score — the
log of how many times in a billion words — and banded on the reader's own cuts
(`frequency.CUTS`), so a band means the same share of running text in Aramaic as in
Hebrew. The corpus is half a million words rather than billions, so the bottom of the
scale is coarse: a word met once is in band 5, among the words a learner looks up,
which is where it belongs.

**What it errs on.** Words the hand table does not know are counted by spelling, with
their prefixes and suffixes on, so one word can be counted as several rare ones until the
table grows (G2). A text's measure errs hard, never easy.

**What this feeds, and what it does not.** The catalogue's difficulty (`difficulty.band_of`)
and so the ladder. Not the card: `FrequencyBands.supports` is still false for Aramaic, so a
word of Onkelos keeps saying it is not rated, and nothing is re-annotated for this.
"""

from __future__ import annotations

import json
import math
from functools import cache
from pathlib import Path

from .base import BAND_COUNT
from .frequency import CUTS

#: The table, beside this module, written by `scripts/count_aramaic.py`.
TABLE = Path(__file__).with_name("aramaic_frequency.json")

#: Only words met this often are written; anything rarer is absent and scored as met once.
MIN_COUNT = 2


@cache
def _table() -> tuple[dict[str, int], int]:
    if not TABLE.is_file():
        return {}, 0
    loaded = json.loads(TABLE.read_text(encoding="utf-8"))
    return dict(loaded.get("counts", {})), int(loaded.get("tokens", 0))


def available() -> bool:
    """Whether the list is on disk: a checkout without it measures Aramaic as before."""
    return bool(_table()[1])


def count(lemma: str) -> int:
    """How many times the corpus has this word, or 0 below `MIN_COUNT`."""
    return _table()[0].get(lemma, 0)


def zipf(lemma: str) -> float:
    """A word's Zipf score in the corpus: log10 of its count per billion words.

    A word the list does not have is scored as though met once, which is at most what it
    was: rare, and never 0, which would read as "not measured".
    """
    counts, total = _table()
    if not total:
        return 0.0
    return math.log10(max(counts.get(lemma, 0), 1) / total * 1e9)


def band(lemma: str) -> int:
    """The band a word falls in, on the reader's own cuts: 5 for a word met once or never."""
    score = zipf(lemma)
    for index, cut in enumerate(CUTS, start=1):
        if score >= cut:
            return index
    return BAND_COUNT


@cache
def ranks() -> dict[str, int]:
    """Each word of the list and its place in it, commonest first, from 1."""
    counts, _ = _table()
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return {word: place for place, (word, _) in enumerate(ordered, start=1)}


def rank(lemma: str) -> int | None:
    """Where a word stands in the list, or None where it is not in it."""
    return ranks().get(lemma)
