"""The emphatic state, read off the pointing: Aramaic's second hard spot (design.md §12,
"Aramaic has a hard-spot list" and "Aramaic's lenses", 2026-10-25).

Aramaic says "the" with an ending, not a prefix: אַרְעָא is הָאָרֶץ, מַיָּא is הַמַּיִם, and
the plural's ־יָּא is the stars of כּוֹכְבַיָּא. A reader who comes from Hebrew looks for ה־
at the front and finds nothing, so the state lens lights the words that carry the ending.

**The rule.** A word ends in א, and the letter before it is pointed with a qamats. That is
the emphatic of every noun, adjective and participle in Onkelos, singular (־ָא), plural
(־יָּא) and feminine (־תָא). It also catches words that only look the part, and three
checks take them out:

- **The particles** that end in ־ָא: לָא, הָא, דָא, הֲדָא, חֲדָא, דִּלְמָא and the rest of
  `NOT_EMPHATIC`, with ו or another of the prefix letters on the front or not.
- **A verb the hand table knows** (`closed.TARGUM`): its gloss says "to …" (קְרָא, חֲזָא),
  and a verb has no state.
- **The perfect of a weak verb**, CְCָא: three letters, a shva or hataf on the first and
  no dagesh in the second (בְּרָא, רְמָא, בְּנָא), and the same behind ו or ב. Nouns of three
  letters double their middle letter or carry a full vowel first (יַמָּא, חַיָּא, דְּמָא is
  the one loss).

Biblical Aramaic writes some emphatics with ה (עִלָּאָה, רָזָה), and Onkelos does not, so the
rule reads א alone: it is the Targum's spelling, and the floor says what it costs in Daniel.

**Measured, not trusted.** `scripts/eval_aramaic_state.py` scores it against Open
Scriptures' state letter (`Ncmsd`) over the Aramaic of Daniel and Ezra, the one Aramaic
with hand-tagged state. It is not held out: the checks above were found reading that text
and Onkelos Genesis 1–3, so the floor is a guard against getting worse rather than an
estimate on unseen text. ling-arc's hand gold on Onkelos is the estimate, and is owed.

An unpointed word says nothing, and answers no: the Gemara is printed unpointed, and the
lens is not offered on it until a rule for it is written and measured.
"""

from __future__ import annotations

from .aramaic import key, look_up
from .vav_consecutive import pointed_letters

NAME = "arc-state/1"

QAMATS = "ָ"
SHVA = "ְ"
HATAF = frozenset({"ֱ", "ֲ", "ֳ"})
DAGESH = "ּ"

#: Words that end in ־ָא and are not a noun in the emphatic: negation, demonstratives,
#: pronouns, "one" in the feminine, "lest", "here" and "there". Folded spellings.
NOT_EMPHATIC = frozenset(
    {
        "לא",
        "הלא",
        "דא",
        "הא",
        "כא",
        "מא",
        "הכא",
        "תמא",
        "מכא",
        "היכא",
        "אנא",
        "אנחנא",
        "אנתא",
        "חדא",
        "הדא",
        "דילמא",
        "דלמא",
        "כדנא",
    }
)


def _weak_perfect(letters: list[tuple[str, frozenset[str]]]) -> bool:
    """CְCָא: the perfect of a verb whose last root letter is weak, "he created"."""
    if len(letters) != 3:
        return False
    first, second = letters[0][1], letters[1][1]
    return (SHVA in first or bool(first & HATAF)) and DAGESH not in second


def emphatic(word: str) -> bool:
    """Whether a pointed Aramaic word is in the emphatic state."""
    letters = pointed_letters(word)
    if len(letters) < 2 or letters[-1][0] != "א" or QAMATS not in letters[-2][1]:
        return False
    folded = key(word)
    if folded in NOT_EMPHATIC:
        return False
    # Before the table: it files הֲוָא, "he was", under the pronoun הוּא.
    if _weak_perfect(letters):
        return False
    # The same behind ו or ב: וּרְמָא, "and he cast".
    if len(letters) == 4 and letters[0][0] in "וב" and _weak_perfect(letters[1:]):
        return False
    found = look_up(word)
    if found is not None:
        from .closed import TARGUM_GLOSSES

        if key(found.headword) in NOT_EMPHATIC:
            return False
        if TARGUM_GLOSSES.get(found.headword, "").startswith("to "):
            return False
    return True
