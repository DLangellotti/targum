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

**Counted under the names the readers of it actually use — both of them.** The Tanakh
is a closed corpus that has been morphologically tagged by hand and released openly
(`oshb.py`), and `ScriptureLemmatizer` files every word of a verse it can line up under
the headword that tagging names. The verses it cannot, and every text that is not
scripture, are read by DICTA, which names the same word differently — `הביא` where the
tagging says `בוא`, `אלוהים` for `אלהים` — and those are two vocabularies, not two
spellings a rule could fold. So the table is the Tanakh counted twice, once through
`headword_of` and once through DICTA, each keying banded by its own coverage and the two
merged on the easier band. A lemma's count is then a true count of that lemma *as the
reader will meet it*, whichever of the two met it, and a name either can file a word
under is a name the table has.

It was not always. The first table was counted with Stanza, on the argument that the
same lemmatizer read the book — true on the day and false within a fortnight, when the
lookup replaced Stanza on scripture and DICTA replaced it everywhere else. Half the
headwords in the Tanakh then missed the table, `אתה` and `הם` among them, and every miss
was "modern · not in the Tanakh" on the Tanakh page (targum-internal#156). The count is
`scripts/count_tanakh.py`; run it again only if the tagging, `headword_of` or the DICTA
model changes, and rename this module and `register.py` together when you do.
"""

from __future__ import annotations

import json
from bisect import bisect_left
from functools import cache
from pathlib import Path

from ..models import is_biblical
from .base import BAND_COUNT, UNRATED

# `/2`: recounted from the hand tagging rather than from Stanza (targum-internal#156).
# Renamed together with `register/2`, which reads the same table.
NAME = "tanakh/2"
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

    Read once. The file ships with the package because counting it means reading the
    whole of the tagged Hebrew Bible, which is not something to do at build time for
    every reader — and not something a box can do at all until it has fetched the
    tagging.
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
        # A lemma the Tanakh does not contain, in a text that is the Tanakh, is a verse
        # the lookup could not line up and a model read instead, spelling the word its
        # own way. The hardest band is the honest answer: it is not a word this list
        # teaches under that name.
        return _table()[0].get(lemma, BAND_COUNT)


def for_source(source: str) -> BiblicalBands | None:
    """Biblical bands for a Biblical text, and nothing else.

    Deliberately narrow. Applying a Tanakh word list to a novel would be the same mistake
    in the other direction, and doing it by guessing at the content rather than by
    knowing where the text came from would be worse again.
    """
    return BiblicalBands() if is_biblical(source) else None
