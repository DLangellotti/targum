"""Difficulty bands for the Tanakh, counted from the Tanakh.

The ordinary bands come from wordfreq, whose Hebrew corpus is contemporary Israeli
media — Wikipedia, subtitles, news, the web. That is the right question for somebody
reading a newspaper and the wrong one for somebody reading Torah, and the answers are
wrong in both directions. Vocabulary that is everywhere in the Tanakh but has dropped out
of modern usage bands as "hard" or "very hard"; modern words that happen to appear once in
scripture inherit a commonness they do not have there. Worst of all it looks authoritative
while doing it, because the band names say "easy" and "moderate" without saying easy for
whom.

So this counts the corpus the reader is actually in. `frequency.py` says as much itself —
*"Where a curated level list does exist for a language it should be used instead and
labelled as such"* — and the artifact records `curated:tanakh`, which the reader renders
as "from the tanakh word list" rather than "by how common each word is".

**Bands are coverage, not raw counts.** A band answers "how much of the Tanakh can I read
if I know this much", which is the question a learner actually has. Band 1 is the handful
of lemmas that carry half of all running text; band 6 is the long tail, where most of the
hapax legomena live.

**Counted with the same lemmatizer that reads the book, and that matters more than
linguistic perfection.** Stanza's Hebrew models are trained on modern unpointed text and
will mishandle some Biblical morphology — waw-consecutive, pausal forms, archaic suffixes.
But the table is built by running the same pipeline over the same corpus, so a lemma's
count is a true count of that lemma *as the reader will meet it*. A more scholarly
lemmatizer that disagreed with the one doing the reading would be worse, not better.
"""

from __future__ import annotations

import json
from bisect import bisect_left
from functools import cache
from pathlib import Path

from .base import BAND_COUNT, UNRATED

NAME = "tanakh/1"
METHOD = "curated:tanakh"

# Where each band ends, as a share of all running text. Band 1 is whatever it takes to
# cover half the corpus; the last band is everything left. Chosen so the early bands are
# genuinely worth learning and the tail does not swallow the middle: in a corpus this
# shape, half the running text is a few hundred lemmas and the last two per cent is
# thousands of them.
COVERAGE = (0.50, 0.70, 0.85, 0.93, 0.98)

# Hebrew only. A Latin word in a Tanakh — a name in a heading, say — has no place in a
# table counted from Hebrew scripture, and rating it from one would be an invention.
LANGUAGES = frozenset({"he", "iw"})


@cache
def _table() -> tuple[dict[str, int], int]:
    """Lemma -> band, and how many lemmas the table knows.

    Read once. The file ships with the package because building it means running Stanza
    over a hundred and fifty thousand words, which is not something to do at build time
    for every reader.
    """
    path = Path(__file__).with_name("tanakh.json")
    if not path.is_file():
        return {}, 0
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {str(lemma): int(band) for lemma, band in raw.get("bands", {}).items()}, int(
        raw.get("lemmas", 0)
    )


def bands_from_counts(counts: dict[str, int]) -> dict[str, int]:
    """Turn lemma counts into bands by cumulative coverage.

    Kept beside the reader rather than in the script that built the table, so the rule
    that produced the file is the rule this module documents, and a rebuild cannot
    quietly use a different one.
    """
    ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    total = sum(counts.values())
    if not total:
        return {}
    cuts = [share * total for share in COVERAGE]
    out: dict[str, int] = {}
    running = 0
    for lemma, count in ordered:
        # The band this lemma falls in is decided by how much text has been covered
        # before it, so the commonest word is always band 1 whatever its share.
        band = bisect_left(cuts, running + 1) + 1
        out[lemma] = min(band, BAND_COUNT)
        running += count
    return out


class BiblicalBands:
    """Bands counted from the Tanakh itself."""

    name = NAME

    @property
    def method(self) -> str:
        return METHOD

    @property
    def note(self) -> str:
        return (
            "Levels come from how often a word is used in the Tanakh itself, not from "
            "modern Hebrew and not from a graded syllabus."
        )

    def supports(self, language: str) -> bool:
        return language.split("-")[0].lower() in LANGUAGES and bool(_table()[0])

    def band(self, lemma: str, language: str) -> int:
        if not self.supports(language):
            return UNRATED
        # A lemma the Tanakh does not contain, in a text that is the Tanakh, is almost
        # always the lemmatizer having produced something the table was built without.
        # The hardest band is the honest answer: it is not a word this corpus teaches.
        return _table()[0].get(lemma, BAND_COUNT)


def for_source(source: str) -> BiblicalBands | None:
    """Biblical bands for a Biblical text, and nothing else.

    Deliberately narrow. Applying a Tanakh word list to a novel would be the same mistake
    in the other direction, and doing it by guessing at the content rather than by
    knowing where the text came from would be worse again.
    """
    return BiblicalBands() if str(source).startswith("sefaria:") else None
