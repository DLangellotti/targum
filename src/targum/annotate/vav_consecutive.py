"""The vav-consecutive, read off the pointing: Hebrew's eighth hard spot (targum-internal#449).

In Biblical narrative וַיֹּאמֶר is "and he said", though without its vav יֹאמַר is "he will
say". The Masoretes point the narrative vav differently from the plain "and": a patah, and
a doubled prefix letter after it (וַיִּ, וַתִּ, וַנִּ), or a qamats before the א of the first
person, which cannot double (וָאֹמַר). The plain conjunction is a shva or a shureq
(וְיֹאמַר, וּתְדַבֵּר), so the pointing says which is which.

Open Scriptures tags the form (`Vqw3ms`, `annotate/scripture.py`), and where it lines up
with a verse it is the answer. This rule is what reads the form everywhere else, and it is
what the build reads, so a text annotated before 2026-10-21 shows the form without being
annotated again: the rule reads the pointed text the page already carries. It is measured
against Open Scriptures' own `w` on a held-out slice (`scripts/eval_vav_consecutive.py`)
rather than trusted, and its floor is in `evals/floors.json`.

Biblical only, by declaration (design.md §12, 2026-10-14): modern Hebrew does not use the
form, and a modern text quoting a verse is quoting, so the build asks this of Biblical text
and nothing else.
"""

from __future__ import annotations

import unicodedata

VAV = "ו"
PATAH = "\u05b7"
QAMATS = "\u05b8"
SHVA = "\u05b0"
DAGESH = "\u05bc"
ALEF = "א"

#: The prefix letters of the future form: he, she or you, we, I.
PREFIXES = frozenset("יתנ")


def pointed_letters(word: str) -> list[tuple[str, frozenset[str]]]:
    """Each letter with its points, the accents and the meteg left out: they mark where a
    word is sung and stressed, and say nothing about which vav this is."""
    out: list[tuple[str, set[str]]] = []
    for char in unicodedata.normalize("NFD", word or ""):
        if "\u0591" <= char <= "\u05af" or char == "\u05bd":
            continue
        if unicodedata.combining(char):
            if out:
                out[-1][1].add(char)
            continue
        if "א" <= char <= "ת":
            out.append((char, set()))
    return [(letter, frozenset(marks)) for letter, marks in out]


def consecutive(word: str) -> bool:
    """Whether a pointed word opens with the narrative vav on a future form.

    וַיִּ, וַתִּ, וַנִּ with the prefix letter doubled; וַיְ, where the yod drops its dagesh
    under a shva (וַיְהִי, the commonest of them all); and וָא for the first person.
    An unpointed word says nothing, and answers no."""
    letters = pointed_letters(word)
    if len(letters) < 3 or letters[0][0] != VAV:
        return False
    vowel = letters[0][1]
    second, marks = letters[1]
    if PATAH in vowel and second in PREFIXES:
        return DAGESH in marks or (second == "י" and SHVA in marks)
    return QAMATS in vowel and second == ALEF
