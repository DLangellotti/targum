"""A verb's root as the page and the language tables give it: the annotation's, less the
ones known to be wrong, and filled from the CC0 paradigm table where the annotation had
none and every verb the table finds agrees (sublexical slice 1, targum-internal#589).

Page-build and table-count time only, like `hebrew.weak_roots` and the families. The
annotation keeps what the annotator said; nothing here renames an annotator, moves
`SCHEMA_VERSION` or runs a model. The real fix to the annotator rides the next rename
that is happening anyway.

Two guards before anything is shown:

- `WRONG`, the roots measured wrong against Wiktionary (used only to find them, never
  shipped) and read one by one (ling-he reviews the list), each filed under the one
  lemma it is wrong for. Most are a three-letter lemma that is not a qal (הקל, הכה)
  whose "root" came back as the lemma itself, or an adjective spelled like a nif'al
  (נזיר) whose נ was stripped as a prefix.
- a root that begins with ו, which Hebrew all but never has: a conjunction left on the
  lemma, or a hof'al's vowel letter read as a radical. The few modern verbs on one
  (ויתר, וידא) write it as a four-letter pi'el with a י, and only those keep it.

A wrong root is a lie told with confidence; a missing one is a gap. Both guards give a
gap.
"""

from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING

from .hebrew import FINALS

if TYPE_CHECKING:
    from .paradigms import Table

#: The version of what this module answers. A change to `WRONG`, the ו rule or the fill
#: is a new number, so the `roots` table counts every text again under it.
VERSION = 1


def _letters(text: str) -> str:
    """The Hebrew letters alone, points dropped and final forms folded."""
    bare = "".join(
        ch for ch in unicodedata.normalize("NFD", text or "") if not unicodedata.combining(ch)
    )
    return "".join(ch for ch in bare if "א" <= ch <= "ת").translate(FINALS)


def _table(rows: dict[str, str]) -> dict[str, frozenset[str]]:
    return {
        _letters(lemma): frozenset(_letters(root) for root in roots.split())
        for lemma, roots in rows.items()
    }


#: {lemma: the roots it was given that are wrong for it}. Single words, read one by one.
WRONG: dict[str, frozenset[str]] = _table(
    {
        # The lemma itself, a three-letter word that is not a qal.
        "דעת": "דעת",  # י־ד־ע
        "הקל": "הקל",  # ק־ל־ל
        "החל": "החל",  # ח־ל־ל
        "הפר": "הפר",  # פ־ר־ר
        "הכה": "הכה",  # נ־כ־ה
        "מכה": "מכה",  # נ־כ־ה
        "הטה": "הטה",  # נ־ט־ה
        "מטה": "מטה",  # נ־ט־ה
        "הסב": "הסב",  # ס־ב־ב
        "הגן": "הגן",  # ג־נ־ן
        "מגן": "מגן",  # ג־נ־ן
        "נצב": "נצב",  # י־צ־ב
        "העז": "העז",  # ע־ז־ז
        "מצר": "מצר",  # צ־ר־ר
        "מקל": "מקל",  # ק־ל־ל
        "נמס": "נמס",  # מ־ס־ס
        "הרע": "הרע",  # ר־ע־ע
        "נדם": "נדם",  # ד־מ־ם
        "הצל": "הצל",  # נ־צ־ל
        "האט": "האט",  # א־ט־ט
        "שמה": "שמה",  # שׁ־מ־ם
        # Nouns and words tagged a verb, given themselves as a root.
        "אוי": "אוי",
        "מעש": "מעש",
        "שבי": "שבי",
        "דיר": "דיר",
        "משא": "משא",
        "חוב": "חוב",
        "גדי": "גדי",
        "מצע": "מצע",
        "חלי": "חלי",
        "שאת": "שאת",
        "מבט": "מבט",
        "ציינת": "ציין",  # צ־י־ן
        # An adjective or noun spelled like a nif'al, its root's own נ stripped.
        "נזיר": "זיר",  # נ־ז־ר
        "נשוא": "שוא",  # נ־שׂ־א
        "נשוי": "שוי",  # נ־שׂ־א
        "נקוב": "קוב",  # נ־ק־ב
        "נקבה": "קבה",  # נ־ק־ב
        "נסוך": "סוך",  # נ־ס־ך
        "נעים": "עים",  # נ־ע־ם
        "נטול": "טול",  # נ־ט־ל
        "נשמה": "שמה",  # נ־שׁ־ם
        # A weak root read as the wrong one.
        "הטיל": "נטל",  # ט־ו־ל
        "הגיח": "גיח",  # נ־ג־ח
        "אפשר": "פשר",  # א־פ־שׁ־ר
        "שכנע": "כנע",  # שׁ־כ־נ־ע
        "מימש": "מממש",  # מ־מ־שׁ
        # What the CC0 fill would give and is wrong: a lemma spelled like another verb's
        # form, or a weak root the table files under another.
        "מפלה": "פלה",  # נ־פ־ל
        "מונח": "הנח",  # נ־ו־ח
        "מכונה": "כנה",  # כ־ו־ן
        "הוליך": "ילך",  # ה־ל־ך
        "הרהר": "רהר",  # ה־ר־ה־ר
        "פג": "פגג",  # פ־ו־ג
        "טח": "טחח",  # ט־ו־ח
        "הוצע": "הצע",  # י־צ־ע
        "הוקף": "הקף",  # נ־ק־ף
        "שורה": "שרה",  # שׁ־ו־ר
        "המרה": "מרה",  # מ־ו־ר
        "אישר": "ישר",  # א־שׁ־ר
        "איחל": "יחל",  # א־ח־ל
        "איחד": "יחד",  # א־ח־ד
        "איתר": "יתר",  # א־ת־ר
        "ניבא": "יבא",  # נ־ב־א
        "ניער": "יער",  # נ־ע־ר
        "ניקר": "יקר",  # נ־ק־ר
        "תחוב": "חוב",  # ת־ח־ב
        "יריב": "רבב",  # ר־י־ב
        "אישה": "איש",  # א־נ־שׁ
        "חנות": "חנן",  # ח־נ־ה
        "ארון": "רנן",  # א־ר־ן
        "תשעה": "שעה",  # ת־שׁ־ע
        "יחוס": "חוס",  # י־ח־ס
    }
)


def denied(lemma: str, root: str) -> bool:
    """Whether `root` is known to be wrong for `lemma`."""
    word, letters = _letters(lemma), _letters(root)
    if not letters:
        return False
    if letters in WRONG.get(word, ()):
        return True
    return letters[0] == "ו" and not (len(word) == 4 and word.startswith("וי"))


#: The two forms a lemma is: the citation form (third person masculine singular past),
#: and the present participle, which DICTA lemmatises as itself (מטמא, מגיע).
_CITED = (
    frozenset({"3rd", "masculine", "past", "singular"}),
    frozenset({"masculine", "present", "singular"}),
)


#: Every root the CC0 table files each of its verbs under (`Table._root_index`), and
#: the fills worked out from it, kept for the one table they were worked out from: a
#: table swapped in (a test's, a rebuilt one) is never answered from another's.
_HELD: dict[int, tuple[object, dict[str, frozenset[str]], dict[str, str]]] = {}


def _held(book: Table) -> tuple[dict[str, frozenset[str]], dict[str, str]]:
    found = _HELD.get(id(book))
    if found is not None and found[0] is book:
        return found[1], found[2]
    by_verb: dict[str, set[str]] = {}
    for (root, _binyan), verbs in book._root_index().items():
        for lid in verbs:
            by_verb.setdefault(lid, set()).add(root)
    roots = {lid: frozenset(found) for lid, found in by_verb.items()}
    fills: dict[str, str] = {}
    _HELD.clear()
    _HELD[id(book)] = (book, roots, fills)
    return roots, fills


def filled(lemma: str) -> str:
    """The root the CC0 paradigm table gives a verb lemma, or "".

    Only where every verb the table finds for the lemma is filed under one root and the
    same one. A verb is found by its citation form, or by a form a lemma can be: the
    lemma matching only another verb's future or second person (אישר is also "I will
    straighten") is not that verb.
    """
    from .paradigms import table

    book = table()
    by_verb, fills = _held(book)
    if lemma not in fills:
        fills[lemma] = _fill(lemma, book, by_verb)
    return fills[lemma]


def _fill(lemma: str, book: Table, by_verb: dict[str, frozenset[str]]) -> str:
    from .paradigms import bare

    word = _letters(lemma)
    if not word:
        return ""
    found: set[str] = set()
    # The table is keyed on the letters as written, final forms and all.
    for lid in book.candidates(bare(lemma)):
        verb = book.verbs.get(lid)
        if verb is None:
            return ""
        if _letters(verb.lemma) != word:
            hits = [form for form in verb.forms if _letters(bare(form.written)) == word]
            if hits and not any(one <= set(form.features) for form in hits for one in _CITED):
                continue
        roots = by_verb.get(lid)
        if not roots or len(roots) != 1:
            return ""
        found |= roots
    return next(iter(found)) if len(found) == 1 else ""


def root_for(lemma: str, root: str | None, pos: str | None, language: str = "he") -> str:
    """The root the page draws and the tables count for one token, or "".

    The annotation's root where it is not known to be wrong. Where it gave none, a
    Hebrew verb's root from the CC0 table (`filled`), under the same guard.
    """
    if root:
        return "" if denied(lemma, root) else root
    if pos != "VERB" or language.split("-")[0].lower() != "he":
        return ""
    found = filled(lemma)
    return "" if not found or denied(lemma, found) else found
