"""A pronoun on the end of an Aramaic word, read off the pointing: Aramaic's third hard spot
(design.md §12, "Aramaic has a hard-spot list" and "Aramaic's lenses", 2026-10-25).

Aramaic writes "his", "your" and "their" onto the noun, the preposition and ית: עֲלוֹהִי is
"on him", בְּנָךְ "your son", יָתְהוֹן "them". A reader who looks the word up finds the noun
and loses whose it is, so the lens lights the ending and leaves the stem plain, which is
why this says how many letters the ending is rather than only that there is one.

**What is read**, second and third person only:

- a final ה with a mappiq (־ֵהּ, ־ַהּ, ־ֵיהּ): his, her. The one root that ends so, אֱלָהּ, is
  left out;
- ־וֹהִי, his, on a plural noun or a preposition (אֲחוֹהִי, עֲלוֹהִי);
- ־הוֹן, ־הֵין, ־כוֹן, ־כֵין: their, your (plural), and Daniel's ־הֹם, ־כֹם;
- a final ך after a qamats or a hiriq (־ָךְ, ־ִךְ), or ־ָיךְ: your (singular). A ך after any
  other vowel is the root's (מֶלֶךְ, סְמַךְ).

And none where all that stands before the ending is a prefix letter: יְהוֹן is "they will
be", not "their". The first person is not read: ־ִי and ־נָא are too often something else,
and a lens that lights wrongly teaches the wrong thing.

Scored against Open Scriptures' `Sp2`/`Sp3` codes in Daniel and Ezra
(`scripts/eval_aramaic_suffixes.py`); not held out, so a guard.
"""

from __future__ import annotations

from .vav_consecutive import pointed_letters

NAME = "arc-suffixes/1"

MAPPIQ = "ּ"
TSERE = "ֵ"
HOLAM = "ֹ"
HIRIQ = "ִ"
QAMATS = "ָ"
PATAH = "ַ"

#: Words whose final ה with a mappiq is the root's, folded.
ROOT_HE = frozenset({"אלה"})


def suffix_letters(word: str) -> int:
    """How many letters at the end of a pointed word are a pronoun, or 0 for none."""
    letters = pointed_letters(word)
    if len(letters) < 2:
        return 0
    spelled = [letter for letter, _ in letters]
    marks = [mark for _, mark in letters]
    whole = "".join(spelled)
    core = whole[1:] if whole[0] == "ו" and len(whole) > 2 else whole
    n = 0
    if spelled[-1] == "ה" and MAPPIQ in marks[-1]:
        if core in ROOT_HE or core.lstrip("דבלכמ") in ROOT_HE:
            return 0
        n = 2 if len(spelled) > 2 and spelled[-2] == "י" else 1
    elif len(spelled) >= 4 and spelled[-3:] == ["ו", "ה", "י"] and HIRIQ in marks[-2]:
        n = 3
    elif (
        len(spelled) >= 3
        and spelled[-3] in "הכ"
        and spelled[-1] == "ן"
        and spelled[-2] in "וי"
        and (HOLAM in marks[-2] or HOLAM in marks[-3] or TSERE in marks[-3])
    ):
        n = 3
    elif len(spelled) >= 2 and spelled[-2] in "הכ" and spelled[-1] == "ם" and HOLAM in marks[-2]:
        n = 2
    elif spelled[-1] == "ך":
        if QAMATS in marks[-2] or HIRIQ in marks[-2]:
            n = 1
        elif len(spelled) >= 3 and spelled[-2] == "י" and marks[-3] & {QAMATS, PATAH}:
            n = 2
    if not n:
        return 0
    if core[: len(core) - n] in ("י", "ת", "נ", "א"):
        return 0
    return n
