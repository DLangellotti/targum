"""A Hebrew noun's or adjective's headword, where the annotator gave another of its forms.

DICTA sometimes files a plural or a feminine under itself: עצים under עצים, לירות under
לירות, צעירות under צעירה rather than צעיר (ling-he's analyser read, targum-internal#697e).
The meaning is bought and looked up under the lemma, so such a card says it has no
meaning. Taking the ending off by rule would be wrong as often as right, because a great
many singulars end the way plurals do (חנות, מלכות, חיים, מים), so the answer is looked up.

The table is Wikidata's lexemes, CC0, the same source as the verb tables
(`paradigms.py`), written by `scripts/hebrew_nouns.py`. Each part of speech's forms map
to their one headword, bare, and a spelling that is itself a headword is never in it.
A build with no table reduces nothing rather than failing.

Two checks stand between the table and a token (targum-internal#755, from ling-he's read
of #1323). An adjective's headword must be an adjective: Wikidata files a people's
adjectives under its country (אירופאיות under אירופה), and an adjective whose masculine
plural ends in יים has a masculine singular in י, so a headword with no י that the table
gives such a plural is a place, not the adjective (`nouns_of_nisbas`). And the spelling
on the page must be a form of the headword it is filed under (`spelled_as`): where DICTA's
lemma was already another word (הַדַּיָּנִים under דינים, שְׁמֹנָה under שמנה), the table
would otherwise carry it on to a third (דין, שמן).
"""

from __future__ import annotations

import gzip
import json
import unicodedata
from functools import lru_cache
from pathlib import Path

#: Beside this module, so the wheel carries it and a reader never fetches it.
TABLE = Path(__file__).parent / "nouns.json.gz"

#: The parts of speech the table answers for, in the tagger's own names.
PARTS = frozenset({"NOUN", "ADJ"})

#: Spellings the table files under a headword they are seldom the form of, found by
#: reading every change it made over the laptop's 483 Hebrew texts (2026-11-18): each is
#: kept as DICTA gave it. ימות is יום's ("ימות המשיח") and not ימה's; אמהות "mothers"
#: and אמות, which is as often the Talmud's cubits, are no אמה's or אם's to guess at;
#: שניים and שנים are the number as often as not; רבות is mostly "many"; לחיים is
#: "cheers" as often as "cheeks"; בעלים "owner", עשירות "wealth", בכירות "seniority" and
#: קרות "coldness" are words of their own; a people is not its country (אירופאים,
#: ונצואלית), and הגויות is no הגות's. ling-he's read of the same list (2026-11-20)
#: kept the rest the table files under another word: בימות is ב + ימות ("בימות
#: החמה"), not stages; שתות is the Mishnah's "a sixth"; ארבות are skylights, not
#: locusts; שבלים are ears of grain; חטים is wheat (and DICTA's lemma for חוטם);
#: טליות are tallitot; כנים are lice; חכים is "wise"; חיצים and חצים are arrows and
#: halves, not partitions; גבים are Isaiah's locusts more than backs; הלנות "that lodge";
#: עונות is עוונות; and a row of singles (הפרכות, אמניות, סרטיות, צינית,
#: טירוניות, ספציפיות, אדמומיות, אירופאיות) whose headword is another word.
KEPT = frozenset(
    {
        "ימות",
        "אמהות",
        "אמות",
        "שניים",
        "שנים",
        "רבות",
        "לחיים",
        "בעלים",
        "עשירות",
        "בכירות",
        "קרות",
        "אירופאים",
        "ונצואלית",
        "הגויות",
        "בימות",
        "שתות",
        "ארבות",
        "שבלים",
        "חטים",
        "טליות",
        "כנים",
        "חכים",
        "חיצים",
        "חצים",
        "גבים",
        "הלנות",
        "עונות",
        "הפרכות",
        "אמניות",
        "סרטיות",
        "צינית",
        "טירוניות",
        "ספציפיות",
        "אדמומיות",
        "אירופאיות",
    }
)


#: The letters a word may carry in front of it on the page: ו, ה, the prepositions and ש.
PREFIXES = frozenset("והבכלמש")

#: The most of them one word carries (וכשה, ומשה).
MOST_PREFIXES = 4

#: A final letter, as it is written when an ending follows: ארוך, ארוכה.
FINALS = str.maketrans("ךםןףץ", "כמנפצ")

#: A possessive suffix, on a singular or on a plural (אזנו, אזניו).
_MINE = ("י", "ך", "ו", "ה", "נו", "כם", "כן", "ם", "ן", "הם", "הן")
_MINE_ON_PLURAL = ("יו", "יה", "יך", "ינו", "יכם", "יכן", "יהם", "יהן")

#: What may follow a noun's headword on the page: a plural or a dual, a construct's ת or
#: י, and a possessive suffix on any of them (אסונותיו, גדותם, בשולי). Written with no
#: final letters, as `FINALS` writes the page's word.
NOUN_TAILS = frozenset(
    tail.translate(FINALS)
    for tail in (
        "",
        "ים",
        "יים",
        # The Mishnah's plural, and the Aramaic's (במומין, נסכין, מיתותא).
        "ין",
        "ותא",
        *_MINE,
        *_MINE_ON_PLURAL,
        *("ות" + one for one in ("", *_MINE, *_MINE_ON_PLURAL)),
        *("ת" + one for one in ("", *_MINE)),
    )
)

#: What may follow an adjective's headword: its feminine and its plurals (מלאה, מלאת,
#: ארוכים, יפות; חופשית is חופשי + ת).
ADJECTIVE_TAILS = frozenset(tail.translate(FINALS) for tail in ("", "ה", "ת", "ים", "ות"))


@lru_cache(maxsize=1)
def _forms() -> dict[str, dict[str, str]]:
    try:
        with gzip.open(TABLE, "rt", encoding="utf-8") as raw:
            loaded = json.load(raw)
    except (OSError, ValueError):
        return {}
    forms = loaded.get("forms") if isinstance(loaded, dict) else None
    if not isinstance(forms, dict):
        return {}
    return {
        str(pos): {str(k): str(v) for k, v in table.items()}
        for pos, table in forms.items()
        if isinstance(table, dict)
    }


@lru_cache(maxsize=1)
def nouns_of_nisbas() -> frozenset[str]:
    """The headwords the adjective table files a nisba under that is not theirs: a
    headword with no final י whose forms include a masculine plural in יים, the plural of
    an adjective in י. אירופה, for אירופאיים, אירופאיות; צרפת, for צרפתיים, צרפתית. A
    loan adjective's own plural is in ים (אגואיסט, אגואיסטים), so it stays, and so does
    an adjective in ה with its plural in ות beside one in יים (פורה: פורות, פוריים)."""
    table = _forms().get("ADJ", {})
    return frozenset(
        head
        for form, head in table.items()
        if form.endswith("יים")
        and not head.endswith("י")
        and not (head.endswith("ה") and table.get(head[:-1] + "ות") == head)
    )


def _skeleton_tails(rest: str, stem: str) -> set[str]:
    """What follows `stem` at the start of `rest`, where `rest` may leave out a ו or a י
    the stem spells (אזנו for אוזנו, חפשית for חופשית) but never adds one."""
    if not stem:
        return {rest}
    out: set[str] = set()
    if rest and rest[0] == stem[0]:
        out |= _skeleton_tails(rest[1:], stem[1:])
    if stem[0] in "וי":
        out |= _skeleton_tails(rest, stem[1:])
    return out


def _inflected(rest: str, head: str, pos: str | None) -> bool:
    """Whether `rest` is `head` with a noun's or an adjective's ending, its matres lectionis
    perhaps left out: באזניו of אוזן, בשולי of שול, החפשית of חופשי."""
    stem = head.translate(FINALS)
    # A feminine's ה or ת gives way to its plural's ות: גדה, גדות; דלית, דליות.
    stems = {stem, stem[:-1]} if stem.endswith(("ה", "ת")) and len(stem) > 2 else {stem}
    tails = ADJECTIVE_TAILS if pos == "ADJ" else NOUN_TAILS
    word = rest.translate(FINALS)
    return any(tail in tails for one in stems for tail in _skeleton_tails(word, one))


HOLAM = "\u05b9"
QUBUTS = "\u05bb"
DAGESH = "\u05bc"
#: The vowels a consonantal ו carries mid-word, which plene spelling writes וו (מצווה).
VOWELS = frozenset(chr(code) for code in range(0x05B0, 0x05BC)) - {HOLAM, "\u05ba"}


def plene(surface: str) -> str:
    """A pointed word in plene spelling, the way the table's forms are written: the
    letters, a ו for a holam or a qubuts, יי for a doubled י, וו for a consonantal ו
    mid-word. So the pointing that tells הַדַּיָּנִים (judges) from דִּינִים (laws), and
    שְׁמֹנָה (eight) from שְׁמֵנָה (fat), is not lost when the points come off. An
    unpointed word is its letters."""
    clusters: list[tuple[str, set[str]]] = []
    for ch in unicodedata.normalize("NFD", surface):
        if "א" <= ch <= "ת":
            clusters.append((ch, set()))
        elif clusters and unicodedata.combining(ch):
            clusters[-1][1].add(ch)
    out: list[str] = []
    for at, (letter, marks) in enumerate(clusters):
        following = clusters[at + 1][0] if at + 1 < len(clusters) else ""
        inside = 0 < at < len(clusters) - 1
        before = clusters[at - 1][0] if at else ""
        if letter == "י" and DAGESH in marks and inside and "ו" not in (before, following):
            out.append("יי")
        elif letter == "ו" and marks & VOWELS and inside and following != "ו":
            out.append("וו")
        else:
            out.append(letter)
        if letter != "ו" and following not in ("ו", "א") and marks & {HOLAM, QUBUTS}:
            out.append("ו")
    return "".join(out)


def spelled_as(surface: str, head: str, pos: str | None = None) -> bool:
    """Whether the spelling on the page, its prefixes taken off, is `head`, a form the
    table files under it, or `head` with an ending: הדיינים is no form of דין, nor שמונה
    of שמן (targum-internal#755)."""
    letters = plene(surface)
    tables = _forms().values()
    for cut in range(min(MOST_PREFIXES, len(letters) - 1) + 1):
        if cut and letters[cut - 1] not in PREFIXES:
            break
        rest = letters[cut:]
        if rest == head or any(table.get(rest) == head for table in tables):
            return True
        # A possessive on a plural the table files under it: גבירותי of גברת.
        if any(
            table.get(rest[: -len(mine)]) == head
            for mine in _MINE + _MINE_ON_PLURAL
            if rest.endswith(mine) and len(rest) > len(mine) and rest[: -len(mine)].endswith("ות")
            for table in tables
        ):
            return True
        if _inflected(rest, head, pos):
            return True
    return False


def headword(lemma: str, pos: str | None, surface: str | None = None) -> str | None:
    """The headword `lemma` is a form of, for a noun or an adjective; None where the
    lemma is a headword already, where the table does not say, where an adjective's
    headword is no adjective, or where `surface`, the spelling on the page, is no form of
    that headword."""
    if pos not in PARTS or not lemma or lemma in KEPT:
        return None
    found = _forms().get(pos, {}).get(lemma)
    if not found or found == lemma:
        return None
    if pos == "ADJ" and found in nouns_of_nisbas():
        return None
    if surface is not None and not spelled_as(surface, found, pos):
        return None
    return found


__all__ = ["KEPT", "PARTS", "TABLE", "headword", "nouns_of_nisbas", "spelled_as"]
