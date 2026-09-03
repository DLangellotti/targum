"""Which Hebrew a word belongs to.

`lexicon.py` reads two corpora — wordfreq's contemporary Israeli media and the Tanakh
lemma table — and `strength()` returns whichever of them thinks better of a word. That
is the right answer for banding a text and it throws away the more interesting half of
what was learned: וְעִקֵּשׁ and מקרר come back as the same kind of hard, and the reader
is told nothing about why.

So this asks the question `strength()` collapses. A word that is everywhere in
scripture and gone from the street is worth knowing about, and so is a word that is
everywhere on the street and absent from scripture, because a learner reading both
carries one vocabulary and does not otherwise find out which half of it a word came
from.

**Only where the two disagree.** A word ordinary in both registers is just a word, and
a word rare in both is a hard word, which the level already says. Saying so a second
time on every card would spend a line to add nothing.

Free to add, and free to reach texts already built: this runs beside the lemmatizer on
whatever machine is doing the reading, so the annotator's name changing is the whole
cost of the migration. Never `SCHEMA_VERSION`, which keys every stage and would buy the
same translations twice.
"""

from __future__ import annotations

from ..lexicon import biblical_strength, modern_strength

# `/2`: the Tanakh table behind `biblical_strength` was recounted from the hand tagging
# rather than from Stanza, and a word read off scripture is no longer called modern for
# being spelled a way the count had not seen (targum-internal#156). Renamed together with
# `tanakh/2`, which reads the same table, so the shelf is re-annotated once and not twice.
NAME = "register/2"

# In the Tanakh and out of use since — "ordinary in the Tanakh, rare today".
BIBLICAL = "biblical"
# In use and never in the Tanakh — "modern; not in the Tanakh".
MODERN = "modern"

# Where ordinary starts, on the zipf scale both halves of the lexicon are measured
# against. Set so that Tanakh bands 1 to 4 clear it and bands 5 and 6 do not: a word in
# the last two bands is at the hapax end of the corpus, and one appearance in scripture
# is not evidence that scripture is where the word lives.
ORDINARY = 4.0

# Hebrew only. The two corpora behind this are a Hebrew frequency list and the Tanakh,
# and there is no register question to ask of a language neither one covers.
LANGUAGES = frozenset({"he", "iw"})


def supports(language: str) -> bool:
    return language.split("-")[0].lower() in LANGUAGES


def of(lemma: str, language: str, *, scripture: bool = False) -> str | None:
    """Which register this dictionary form belongs to, where the two disagree.

    `None` is the common answer and the honest one: ordinary in both registers, or rare
    in both, are not facts worth a line on the card.

    `scripture` says the word was read off the Tanakh. Then "not in the Tanakh" is not
    an answer the table can give: the word is on the page of the Tanakh the reader is
    looking at, and a headword the table lacks is a disagreement between whatever read
    the word and whatever counted the table — DICTA writes ניצב where the tagging writes
    נצב — not evidence about scripture. The honest line there is no line.
    """
    if not lemma or not supports(language):
        return None
    modern = modern_strength(lemma)
    # Both halves asked of the dictionary form as it stands, without peeling. The
    # generous reading is for running text; here it would answer the wrong question in
    # both directions — מקרר peels down to קר, which is in Proverbs, and a refrigerator
    # is not a biblical word for it.
    biblical = biblical_strength(lemma)
    if biblical is not None and biblical >= ORDINARY and modern < ORDINARY:
        return BIBLICAL
    if biblical is None and modern >= ORDINARY and not scripture:
        return MODERN
    return None
