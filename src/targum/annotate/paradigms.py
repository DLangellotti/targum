"""The conjugations of a Hebrew verb, from a source targum may redistribute.

The front door promises "Conjugations on the card: the full table for any verb, with the
form in front of you picked out." The card showed the root and the binyan and then linked
out to Pealim — an outbound link §11 permits, and not the table the page sells. It also
sends the reader off the page at the moment they were learning.

**CC0, which is the whole reason this source and not another.** Wikidata's lexemes carry
no attribution requirement, no ShareAlike and no terms of service, so a table drawn from
them can be baked into a reader page. DICTA's hosted tools are NonCommercial and Hebrew
Wiktionary is ShareAlike; neither could ride inside a file a reader keeps.

**Looked up by any form, not by the lemma.** Measured on 2026-09-16: matching targum's
verb lemmas against Wikidata's lemma to lemma covers 20.7% of them, because the two
disagree about what a Hebrew verb is called — DICTA says `בוא`, `מות`, `קום`; Wikidata
says the 3ms past `בא`, `מת`, `קם`. Matching a lemma against *any* inflected form covers
51.1% of distinct lemmas and **89.4% of running verb occurrences**. The rest is mostly
biblical, where the Open Scriptures morphology is the better source anyway.

**Bare, always.** Nikkud is where two sources most easily disagree — the same verb is
written with and without points, and with different points by different editors — so
every comparison here is on letters alone. The pointed spelling is kept for showing, never
for matching — with one exception, decided 2026-10-03 (targum-internal#307): where verbs
share a word's letters, the vowel the reader's own pointed text opens it on picks between
them (`Table.pointed_as`), and only where nothing else in the table could be that word.

The table is built by `scripts/hebrew_paradigms.py` out of the lexeme dump and ships
gzipped beside this file: 145,000 forms over 4,700 verbs, 0.9 MB in the wheel. Nothing
here reaches the network, and a build with no table draws no conjugations rather than
failing.

**A stub is filled by rule.** A few dozen lexemes came through with a handful of forms —
`אָכַל` with ten and no `אוכל`. `conjugate` fills what they lack from their root and
binyan, by the patterns the complete tables follow, and refuses wherever the forms the
source has could be some other pattern's. What it adds ships under `filled`, apart from
the source's forms, and every such `Form` says `ruled` (targum-internal#307).
"""

from __future__ import annotations

import gzip
import json
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .conjugate import Filled

#: Beside this module, so the wheel carries it and a reader never fetches it.
TABLE = Path(__file__).parent / "paradigms.json.gz"

#: How targum's own tagging reads a written verb form, counted off its exportable shelf by
#: `scripts/count_binyans.py` (targum-internal#307). Private: gitignored, and packed into
#: the wheel by `artifacts` the way `activity.json` is (decided 2026-09-27). Absent from
#: CI and from every worktree, where `readings()` is empty and the card draws only what
#: the binyan and the pointing settle.
READINGS = Path(__file__).parent / "binyans.json"

#: The most forms a card will draw for one verb. A Hebrew verb has about thirty-three,
#: and a lexeme with far more than that is carrying something a learner did not ask for.
MOST = 60


#: The points, so a lemma can be read as letters-with-vowels rather than a string.
_POINTS = frozenset(
    "\u05b0\u05b1\u05b2\u05b3\u05b4\u05b5\u05b6\u05b7\u05b8"
    "\u05b9\u05ba\u05bb\u05bc\u05bd\u05c1\u05c2\u05c7"
)
_SHVA, _HIRIQ, _TSERE, _PATACH, _QAMATS = "\u05b0", "\u05b4", "\u05b5", "\u05b7", "\u05b8"
#: Qubuts and qamats qatan, the two ways the passive binyanim point their first letter.
_QUBUTS, _QATAN = "\u05bb", "\u05c7"
_SEGOL, _HOLAM, _DAGESH = "\u05b6", "\u05b9", "\u05bc"
#: The reduced vowels a guttural takes where any other letter would take a shva. For
#: the question "is the letter after the prefix quiescent" they are the shva.
_HATAF = frozenset("\u05b1\u05b2\u05b3")
_HE, _TAV, _NUN, _VAV = "\u05d4", "\u05ea", "\u05e0", "\u05d5"
#: The letters that trade places with a הִתְפַּעֵל's ת: הִסְתַּכֵּל, הִשְׁתַּמֵּשׁ, הִצְטָרֵף,
#: הִזְדַּקֵּן. The ת comes after them, and is a ט after צ and a ד after ז.
_SIBILANTS = frozenset("\u05e1\u05e9\u05e6\u05d6")
_SWAPPED_TAV = frozenset("\u05ea\u05d8\u05d3")

#: How few of a lemma's letters may be pointed before it is not a pointed lemma. The
#: dump carries both — `הָלַךְ` and `אוחזר` sit side by side — and an unpointed one says
#: nothing about its binyan, so it is refused rather than read as פעל.
_LEAST_POINTED = 2


def _units(word: str) -> list[tuple[str, str]]:
    """Each Hebrew letter with the points that follow it, in order."""
    out: list[list[str]] = []
    for ch in word:
        if ch in _POINTS:
            if out:
                out[-1][1] += ch
        elif "\u05d0" <= ch <= "\u05ea":
            out.append([ch, ""])
    return [(letter, points) for letter, points in out]


def binyan_of(lemma: str) -> str | None:
    """Which binyan a *pointed* lemma is built in, or None where it cannot be read.

    Wikidata's Hebrew lexemes carry no binyan statement — checked against the dump — so
    the conjugation lookup had no way to tell `הָלַךְ` from `הִלֵּךְ` except by hoping the
    reader's own pointing matched one of them (targum-internal#307). This reads it off
    the lemma instead, which is owned outright and behind no licence door: the lemma is
    the third-person masculine singular past, and that is the form each binyan spells in
    its own pattern. It is `hebrew.root_of` run the other way.

    Only the prefix and the first two vowels are asked, because that is what the seven
    patterns differ in and the rest of the word is the root's business. A lemma with
    fewer than two points is not pointed, and says nothing; a pattern that is not one of
    the seven is None. Both refuse rather than guess, for the reason the card refuses a
    root it could not work out: a wrong conjugation table is worse than none.
    """
    units = _units(lemma)
    if len(units) < 2 or sum(1 for _, points in units if points) < _LEAST_POINTED:
        return None
    (first, points), (second, after) = units[0], units[1]
    third = units[2] if len(units) > 2 else ("", "")
    # A prefix is a prefix only when the letter after it is quiescent. הִפְעִיל and
    # נִפְעַל both put a shva there, and it is the whole of what separates them from a
    # root whose own first letter is ה or נ: הִלֵּךְ is פיעל of ה־ל־ך and נִסָּה is פיעל
    # of נ־ס־ה, and both were read as prefixed until this asked.
    #
    # A guttural takes a hataf where any other letter takes a shva, and is quiescent all
    # the same: נֶאֱמַר, נַעֲשָׂה, הֶעֱמִיד. Those read as no binyan at all until
    # 2026-09-27, and נֶאֱמַר alone is 1,815 verb tokens on the shelf.
    quiescent = _SHVA in after or any(mark in _HATAF for mark in after)
    if first == _HE and _HIRIQ in points and quiescent:
        if second == _TAV:
            # הִתְפַּעֵל keeps its ת — but so does the הִפְעִיל of a root that begins with
            # one: הִתְקִין is ת־ק־ן, not a reflexive, and was read as one until
            # 2026-09-27. The letter after the ת parts them the way it parts every
            # הִפְעִיל from a הִתְפַּעֵל: a hiriq for the one, the root's vowel for the other.
            return "הפעיל" if _HIRIQ in third[1] else "התפעל"
        if second in _SIBILANTS and third[0] in _SWAPPED_TAV:
            # הִסְתַּכֵּל: the ת has traded places with the root's first letter, and was
            # read as a הִפְעִיל. The same vowel test keeps הִסְתִּיר — the הִפְעִיל of
            # ס־ת־ר — where it belongs, and a vowel that is neither says nothing.
            if _PATACH in third[1] or _QAMATS in third[1]:
                return "התפעל"
            if len(units) > 3 and units[3][0] == _VAV and _HOLAM in units[3][1]:
                # A doubled or hollow root's, whose vowel rides on a vav: הִשְׁתּוֹלֵל,
                # הִסְתּוֹבֵב.
                return "התפעל"
            if _HIRIQ in third[1]:
                return "הפעיל"
            return None
        return "הפעיל"
    if first == _HE and _HIRIQ in points:
        # A weak root's הִפְעִיל has no shva to give — הִגִּיד, הִתִּיר — and neither has the
        # פיעל of a root beginning with ה. They part on the vowel the second letter
        # carries: הִפְעִיל's own hiriq, against פיעל's tsere.
        if _HIRIQ in after:
            return "הפעיל"
        if _TSERE in after:
            return "פיעל"
        return None
    if first == _HE and _TSERE in points and _HIRIQ in after:
        # A hollow root's הִפְעִיל: הֵבִיא, הֵקִים, הֵשִׁיב. No other binyan puts a tsere
        # under a first ה and a hiriq after it.
        return "הפעיל"
    if first == _HE and _SEGOL in points and quiescent:
        # A guttural's הִפְעִיל: הֶעֱמִיד, הֶחְלִיט, הֶרְאָה.
        return "הפעיל"
    if first == _HE and quiescent and (_QUBUTS in points or _QATAN in points or _QAMATS in points):
        # A qamats here is a qamats qatan written as a plain one — הָחְלַט, הָעֳמַד — which
        # the dump does as often as not. No פעל puts a shva on its second letter, so the
        # quiescent letter after it is what tells this from הָלַךְ.
        return "הופעל"
    if first == _HE and not points and second == _VAV:
        # A root beginning with י writes its הִפְעִיל and its הֻפְעַל with the vowel on a
        # vav: הוֹלִיךְ, הוֹשִׁיב against הוּצָא, הוּשַׁב. A holam is the one; a shuruk,
        # which is a vav with a dagesh and no vowel, is the other.
        if _HOLAM in after and _HIRIQ in third[1]:
            return "הפעיל"
        if after == _DAGESH and (_QAMATS in third[1] or _PATACH in third[1]):
            return "הופעל"
        return None
    if first == _NUN and quiescent and (_HIRIQ in points or _SEGOL in points or _PATACH in points):
        # נִפְעַל, and not נָתַן — which is פעל and carries a qamats, not a hiriq. A
        # guttural's takes a segol or a patach instead: נֶאֱמַר, נַעֲשָׂה, נֶחְבָּא.
        return "נפעל"
    if first == _NUN and not points and second == _VAV and _HOLAM in after:
        # A root beginning with י: נוֹלַד, נוֹדַע, נוֹסַד. Its own vowel follows the vav;
        # a tsere there is a hollow root's נוֹפֵף, which is not a נִפְעַל at all.
        if _PATACH in third[1] or _QAMATS in third[1]:
            return "נפעל"
        return None
    if first == _NUN and _HIRIQ in points and _TSERE not in after:
        # Refused, 2026-09-27. A root beginning with נ loses it in the נִפְעַל, and what is
        # left is spelled exactly like the פיעל of a root whose own first letter is נ:
        # נִתַּן is the נִפְעַל of נ־ת־ן and נִסָּה the פיעל of נ־ס־ה, letter for letter and
        # point for point. This read נִתַּן as a פיעל until it was asked. Only a tsere —
        # the פיעל's own vowel, נִהֵל — says which it is.
        return None
    if _QUBUTS in points or _QATAN in points:
        return "פועל"
    if _HIRIQ in points and (_TSERE in after or _PATACH in after):
        return "פיעל"
    if _HIRIQ in points and _QAMATS in after and first != _HE:
        # A root ending in ה writes its פיעל with a qamats where the rest take a tsere:
        # צִוָּה, גִּלָּה, שִׁנָּה. No פעל puts a hiriq under its first letter, and the one
        # other binyan that could — a נִפְעַל that has lost its נ — is refused above.
        return "פיעל"
    if _TSERE in points and _TSERE in after and first != _HE:
        # A guttural or ר cannot be doubled, so the פיעל lengthens the vowel before it
        # instead: בֵּרֵךְ, קֵרֵב, גֵּרֵשׁ, מֵאֵן. Not under a first ה, where the same two
        # tseres are a doubled root's הִפְעִיל — הֵפֵר, הֵעֵז, הֵגֵן — and are left alone.
        return "פיעל"
    if _HOLAM in points and (_PATACH in after or _QAMATS in after):
        # And the פועל the same way: בֹּרַךְ, קֹרַב, גֹּרַשׁ.
        return "פועל"
    if _QAMATS in points:
        return "פעל"
    return None


#: The most verbs a card will name beside the one the reader tapped. A root with all
#: seven binyanim exists — כתב has every one — and seven other words under a word is a
#: list rather than a fact about it.
SIBLINGS = 5


@lru_cache(maxsize=1)
def _families() -> dict[str, tuple[tuple[str, str], ...]]:
    """Every root the shipped table can work out, and the verbs built on it.

    Owned outright and computed here rather than fetched: the lemma gives its binyan
    (`binyan_of`) and the two together give the root (`hebrew.root_of`), so a family is
    two rules over a CC0 source and no licence door at all (targum-internal#301).

    A verb whose lemma is unpointed says no binyan, and one whose root will not come out
    at three letters says no root; both are left out rather than guessed at, which is the
    same guard every rule in `hebrew.py` ends at. Of the table's 4,703 verbs, 3,019 have
    a root and 2,579 of those have at least one sibling (2,613 and 2,071 before
    `binyan_of` learned the guttural and weak patterns, 2026-09-27).
    """
    from .hebrew import root_of

    out: dict[str, list[tuple[str, str]]] = {}
    for verb in table().verbs.values():
        binyan = binyan_of(verb.lemma)
        if not binyan:
            continue
        root = root_of(verb.lemma, binyan)
        if not root:
            continue
        out.setdefault(root, []).append((verb.lemma, binyan))
    # In the order a learner meets them, so a family reads the same way every time and
    # not in whatever order the dump happened to list it.
    order = {name: at for at, name in enumerate(BINYAN_ORDER)}
    return {
        root: tuple(sorted(verbs, key=lambda one: (order.get(one[1], 99), one[0])))
        for root, verbs in out.items()
    }


#: The binyanim in the order a grammar book teaches them, which is the order a family is
#: read in. `hebrew.BINYANIM` is keyed on the tagger's names; this is the sequence.
BINYAN_ORDER = ("פעל", "נפעל", "פיעל", "פועל", "הפעיל", "הופעל", "התפעל")


def family_of(lemma: str, binyan: str | None) -> tuple[tuple[str, str], ...]:
    """The other verbs built on this verb's root, each with its own binyan.

    Empty where the root could not be had honestly — the card already hides a root it
    could not work out, and a guessed family is worse than none — and empty where the
    root is this verb's alone. The verb itself is never in its own family.
    """
    from .hebrew import root_of

    root = root_of(lemma, binyan) if binyan else None
    if not root:
        return ()
    # By binyan, not by spelling. A root has one verb per binyan, so the tapped verb's
    # own binyan is the one to drop — and that also drops it where the annotator points
    # its lemma differently from the source, which spelling alone would miss.
    #
    # Spelling cannot do this job: כָּתַב and כִּתֵּב are both written כתב, and a family
    # filtered on the bare form would throw away the פיעל for looking like the פעל —
    # which is the very pair the card exists to show.
    kin = [one for one in _families().get(root, ()) if one[1] != binyan]
    return tuple(kin[:SIBLINGS])


def bare(text: str) -> str:
    """The letters alone, which is the only spelling two sources agree on."""
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text or "") if not unicodedata.combining(ch)
    )


def _letters(text: str) -> str:
    """The Hebrew letters and nothing else: no points, no cantillation, no maqaf, no `!`
    the source puts after an imperative and no `-` it puts after a construct form."""
    return "".join(ch for ch in bare(text) if "\u05d0" <= ch <= "\u05ea")


def written_form(surface: str, built: str | None = None) -> str:
    """The verb as it was written in the text, without the letters clinging to it.

    `Token.built` says how a split word is put together — "ו and + יאמר", "ש that +
    נצטרף" — and the verb is the one piece that is Hebrew and nothing else: a clitic
    carries its gloss, and a suffix is said in English. Where there is nothing to split,
    the surface is the verb. Compared on letters alone, like everything else here.
    """
    if built:
        pieces = [piece.strip() for piece in built.split(" + ")]
        hebrew = [piece for piece in pieces if piece and _letters(piece) == bare(piece)]
        if hebrew:
            return _letters(max(hebrew, key=len))
    return _letters(surface)


def pointed_form(surface: str, built: str | None = None) -> str:
    """The verb as it was written, points and all, without the letters clinging to it.

    `written_form` is the same thing on letters alone. This keeps the vowels and the
    dagesh, which are what tell `אוֹכֵל` from `אוּכַל`, and drops what is not a point —
    cantillation, a maqaf — so it compares the way a grammar spells. The verb is the last
    run of the surface whose letters are `written_form`'s: a clitic comes before it.
    Empty where the surface has no such run.
    """
    letters = written_form(surface, built)
    units = _units(unicodedata.normalize("NFD", surface or ""))
    if not letters:
        return ""
    for start in range(len(units) - len(letters), -1, -1):
        run = units[start : start + len(letters)]
        if "".join(letter for letter, _ in run) == letters:
            return "".join(letter + points for letter, points in run)
    return ""


#: The vowel a word opens on, by the mark that says it. A shuruk is a ו with a dagesh
#: and no vowel of its own. A holam on a ו is told from one on the letter itself
#: (`_vowel_at`): `אוֹכֵל` is a present, and `אֹכַל`, `יֹאכַל` a future.
_VOWELS = {
    _SHVA: "shva",
    _HIRIQ: "hiriq",
    _TSERE: "tsere",
    _SEGOL: "segol",
    _PATACH: "patach",
    _QAMATS: "qamats",
    _HOLAM: "o",
    "ֺ": "o",
    _QUBUTS: "u",
    _QATAN: "qatan",
    "ֱ": "hataf",
    "ֲ": "hataf",
    "ֳ": "hataf",
}


def _vowel_at(units: list[tuple[str, str]], at: int) -> tuple[str | None, int]:
    """The vowel the letter at `at` carries, and where the next letter is. A letter with no
    vowel of its own, followed by a ו with a holam or a shuruk, is said with that ו's —
    "vo" for the holam, because a פעל writes its present that way (`אוֹכֵל`) and never its
    future (`יֹאכַל`), and the future 1st person of `יָכֹל` is spelled `אוכל` too."""
    if at >= len(units):
        return None, at
    marks = [_VOWELS[mark] for mark in units[at][1] if mark in _VOWELS]
    if len(marks) == 1:
        return marks[0], at + 1
    if not marks and at + 1 < len(units) and units[at + 1][0] == _VAV:
        vav = units[at + 1][1]
        if _HOLAM in vav or "\u05ba" in vav:
            return "vo", at + 2
        if vav == _DAGESH:
            return "u", at + 2
    return None, at + 1


def opening_of(pointed: str) -> str | None:
    """The vowel a pointed word opens on, or None where it is not pointed enough to say.

    The first letter's own vowel, or — where it has none and a ו follows — the o or the u
    that ו carries: `אוֹכֵל` opens on an o and `אוּכַל` on a u, and nothing else about the
    two words differs on letters.

    Three openings are told apart by the letter after them, because one vowel there is
    two binyanim's: a hiriq closing its syllable (`יִכְתֹּב`, `נִכְנַס`) against one before
    a doubled letter (`יִכָּתֵב`, `דִּבֵּר`) or an open one (`טִהֵר`); a tsere before a
    qamats, which only a נִפְעַל's future writes (`יֵאָכֵל`, against `יֵשֵׁב`); and a shva
    or hataf before a u, the פֻּעַל's (`מְשֻׁלָּח`, against `מְשַׁלֵּחַ`).
    """
    units = _units(unicodedata.normalize("NFD", pointed or ""))
    opens, after = _vowel_at(units, 0)
    if opens == "hiriq":
        # A י after a hiriq is how the vowel is written in full (`יִיכָּתֵב`), not a letter.
        if after < len(units) and units[after][0] == "\u05d9" and not units[after][1]:
            after += 1
        if after >= len(units):
            return opens
        marks = units[after][1]
        if _SHVA in marks or any(mark in _HATAF for mark in marks):
            return "hiriq"
        return "hiriq-dagesh" if _DAGESH in marks else "hiriq-open"
    following, _ = _vowel_at(units, after)
    if opens == "tsere" and following == "qamats":
        return "tsere-qamats"
    if opens in ("shva", "hataf") and following == "u":
        return f"{opens}-u"
    return opens


#: A final letter as the same letter anywhere else in a word: `קומם` doubles its מ.
_UNFINAL = str.maketrans("\u05da\u05dd\u05df\u05e3\u05e5", "\u05db\u05de\u05e0\u05e4\u05e6")


def binyan_unpointed(lemma: str) -> str | None:
    """The binyan an *unpointed* lemma's letters alone say, where they say only one.

    The source carries `אוכל` and `הוכל` unpointed, and `binyan_of` rightly refuses them.
    Three shapes are a binyan however they are read: a third person past that opens `הת`
    and has no י before its last letter is a הִתְפַּעֵל; one that opens `הו`, has no י and
    does not end in ה is a הֻפְעַל (`הוסף`; with the י, or ending in ה, it is the הִפְעִיל
    of a root beginning with י — `הוליד`, `הודה`); four letters with a ו second and the
    last two not the same is a פֻּעַל written full (`אוכל`; doubled, `קומם` is a פּוֹלֵל).
    Everything else is None.
    """
    if not lemma or bare(lemma) != lemma:
        return None
    letters = _letters(lemma)
    if letters.startswith("הת") and len(letters) >= 5 and letters[-2] != "י":
        return "התפעל"
    if (
        letters.startswith("הו")
        and len(letters) >= 4
        and "י" not in letters
        and not letters.endswith("ה")
    ):
        return "הופעל"
    if (
        len(letters) == 4
        and letters[1] == _VAV
        and letters[0] not in "הנמת"
        and letters[2] != letters[3].translate(_UNFINAL)
    ):
        return "פועל"
    return None


def _tense_of(form: Form) -> str:
    """Which of past, present, future and imperative a form of the table is, or "" for
    anything else."""
    features = set(form.features)
    if not _PRESENT.isdisjoint(features):
        return "present"
    for tense in ("past", "future", "imperative"):
        if tense in features:
            return tense
    return ""


_HIRIQS = frozenset({"hiriq", "hiriq-dagesh", "hiriq-open"})
_NIFAL = frozenset({"hiriq", "hiriq-dagesh", "segol", "patach", "vo", "qamats"})
_HUFAL = frozenset({"u", "qatan", "qamats"})
#: The vowels each binyan opens each tense on (`opening_of`): the first letter's in the
#: past, the prefix's in the present and the future. Wide rather than narrow, because a
#: vowel left out here rules out the right verb: the פעל's future opens on a u for
#: `יוּכַל`, its past on a patach for `קַמְתִּי`, and on a doubled hiriq for `יִגַּשׁ`. A
#: binyan and tense not here — the פעל's imperative, which opens on nearly anything —
#: rules nothing out.
_OPENING: dict[tuple[str, str], frozenset[str]] = {
    ("פעל", "past"): frozenset({"qamats", "patach", "shva", "hataf"}),
    ("פעל", "present"): frozenset({"vo", "o", "qamats"}),
    ("פעל", "future"): frozenset(
        {"hiriq", "hiriq-dagesh", "o", "patach", "segol", "tsere", "qamats", "u"}
    ),
    ("נפעל", "past"): _NIFAL,
    ("נפעל", "present"): _NIFAL,
    ("נפעל", "future"): frozenset({"hiriq-dagesh", "tsere-qamats", "segol"}),
    ("נפעל", "imperative"): frozenset({"hiriq-dagesh", "tsere-qamats"}),
    ("פיעל", "past"): _HIRIQS | {"tsere"},
    ("פיעל", "present"): frozenset({"shva"}),
    ("פיעל", "future"): frozenset({"shva", "hataf"}),
    ("פיעל", "imperative"): frozenset({"patach"}),
    # Not the o a guttural lengthens it to, `בֹּרַךְ`: that is the vowel the פעל's present
    # opens on, and `דֹּבֵר` "speaks" and `יוֹצְאָה` "goes out" were read as פֻּעַל pasts.
    ("פועל", "past"): frozenset({"u", "qatan"}),
    ("פועל", "present"): frozenset({"shva-u"}),
    ("פועל", "future"): frozenset({"shva-u", "hataf-u"}),
    ("הפעיל", "past"): frozenset({"hiriq", "hiriq-dagesh", "segol", "tsere", "vo", "hataf"}),
    ("הפעיל", "present"): frozenset({"patach", "tsere", "vo"}),
    ("הפעיל", "future"): frozenset({"patach", "qamats", "vo", "tsere"}),
    ("הפעיל", "imperative"): frozenset({"patach", "qamats", "vo"}),
    ("הופעל", "past"): _HUFAL,
    ("הופעל", "present"): _HUFAL,
    ("הופעל", "future"): _HUFAL,
    ("התפעל", "past"): frozenset({"hiriq", "hiriq-dagesh"}),
    ("התפעל", "present"): frozenset({"hiriq", "hiriq-dagesh"}),
    ("התפעל", "future"): frozenset({"hiriq", "hiriq-dagesh", "segol"}),
    ("התפעל", "imperative"): frozenset({"hiriq", "hiriq-dagesh"}),
}


@dataclass(frozen=True)
class Form:
    """One inflected form: how it is written, and what it is."""

    written: str
    features: tuple[str, ...]
    #: Spelled by rule from the verb's root and binyan rather than taken from the source,
    #: where the source's table was a stub (`conjugate`, targum-internal#307). Unpointed.
    ruled: bool = False

    def matches(self, surface: str) -> bool:
        """Whether this is the form in front of the reader, compared on letters."""
        return bool(surface) and bare(self.written) == bare(surface)


@dataclass(frozen=True)
class Paradigm:
    """One verb's forms, in the order the source gives them."""

    lemma: str
    forms: tuple[Form, ...]


@dataclass(frozen=True)
class Table:
    """Every verb, and the index from a bare form to the verbs that spell it that way."""

    verbs: dict[str, Paradigm]
    by_form: dict[str, tuple[str, ...]]
    #: A written form, and the verb targum's own tagging reads it as: the bare lemma and
    #: the binyan. See `readings`.
    readings: dict[str, tuple[str, str]] = field(default_factory=dict)
    #: Every present-tense form in the table, by the two spellings it could be written in
    #: (`_orthographies`). Built on first use, so a table nobody asks about costs nothing.
    _present: dict[str, list[tuple[str, Form]]] = field(
        default_factory=dict, repr=False, compare=False
    )
    #: And every form, the same way, for the pointing (`pointed_as`).
    _spelled: dict[str, list[tuple[str, Form]]] = field(
        default_factory=dict, repr=False, compare=False
    )

    def of(
        self,
        word: str,
        seen: str = "",
        binyan: str | None = None,
        written: Iterable[str] = (),
        said: Iterable[tuple[str, str, str]] = (),
    ) -> Paradigm | None:
        """The paradigm for a lemma or any inflected form of it.

        `seen` is a pointed spelling the word actually wore in the text, and it is what
        makes this usable. Unpointed, the commonest verbs in the language are ambiguous —
        `הלך` is both `הָלַךְ` and `הִלֵּךְ`, `נתן` is `נָתַן` and `נִתַּן`, `דבר` is `דִּבֵּר` and
        `דֻּבַּר` — because Hebrew writes two binyanim of one root the same way without
        points. Refusing all of those would leave the table off most of the verbs a reader
        meets, which is not caution, it is uselessness.

        The points break the tie. A form the reader actually saw, spelled out, belongs to
        one of the candidates and not the other, and that is the one.

        `binyan` is the conjugation targum already worked out for the occurrence, and it
        is the stronger of the two signals (targum-internal#307). The source carries no
        binyan statement, so each candidate's is read off its own pointed lemma
        (`binyan_of`); the candidate whose binyan is the one in the text is the verb.
        Measured over 114,291 verb tokens on the built shelf, this is what takes the
        table from 55.4% of them to 72.4%.

        Where both signals decide and they disagree, neither is taken. That is 0.1% of
        tokens and they are real conflicts — a נִפְעַל lemma whose surface form is spelled
        the way its פָּעַל cousin spells one — so the honest answer is the one the card
        has always given for a root it could not work out.

        `written` is the forms the word was written in on the page. Where the occurrence
        has no binyan of its own — 30% of verb tokens in the shelf's current builds on
        2026-09-27 — it can settle the tie (`_by_reading`); wherever anything settles it,
        a form read as one of the other verbs refuses it (`_read_otherwise`).

        `said` is the same forms with the grammar the annotator gave each one and the
        surface it was written as, and it is what settles a participle (`_by_present`):
        `עומד` is the present of `עָמַד` and the past of `עוּמַּד`, and an occurrence
        tagged present is the one and not the other. Where it names a verb, it also
        refuses a table anything else settled on another.

        None where nothing matches at all, and None where nothing settles it: a wrong
        conjugation table is worse than no table, and the way out to Pealim is still on
        the card.
        """
        found = self.by_form.get(bare(word)) or ()
        if not found:
            return None
        if len(found) == 1:
            return self.verbs.get(found[0])
        pointed = self.pointed_as(found, seen)
        built = []
        if binyan:
            built = [
                lid
                for lid in found
                if (verb := self.verbs.get(lid)) and binyan_of(verb.lemma) == binyan
            ]
        written = tuple(written)
        present = self._by_present(found, said)
        chosen: str | None = None
        if len(pointed) == 1 and len(built) == 1:
            chosen = pointed[0] if pointed[0] == built[0] else None
        elif len(built) == 1:
            chosen = built[0]
        elif len(pointed) == 1:
            chosen = pointed[0]
            # The word's own binyan still has a say against the verb its vowel named.
            if binyan and (named := self.binyan_of(chosen)) and named != binyan:
                return None
        else:
            read = self._by_reading(found, written) if not binyan and self.readings else None
            if read is not None:
                lid = next((lid for lid in found if self.verbs.get(lid) is read), None)
                if present is not None and present != lid:
                    return None
                return read
            if present is None:
                return None
            # The word's own binyan, where it has one that no candidate's lemma could be
            # read as: it still has a say against the verb the present names.
            named = binyan_of(self.verbs[present].lemma)
            if binyan and named and named != binyan:
                return None
            chosen = present
        if chosen is None or (present is not None and present != chosen):
            return None
        if self._read_otherwise(found, chosen, written):
            return None
        return self.verbs.get(chosen)

    def binyan_of(self, lid: str) -> str | None:
        """The binyan a verb of the table is built in, from its lemma, pointed or not."""
        verb = self.verbs.get(lid)
        if verb is None:
            return None
        return binyan_of(verb.lemma) or binyan_unpointed(verb.lemma)

    def pointed_as(self, found: tuple[str, ...], seen: str) -> list[str]:
        """The candidates this occurrence's own pointing allows, where it says anything.

        First the spelling itself: a candidate whose lemma or one of whose forms is
        pointed exactly as the word was. The lemma as well as the forms, because a source
        lists a verb's dictionary form once, at the head, and not again among its own
        inflections — checking only the forms missed `הָלַךְ`, the word that made this
        necessary.

        **Then the vowel the word opens with** (targum-internal#307, decided 2026-10-03:
        pass the pointing per occurrence). The source writes its forms without points, so
        an exact match is rare, and `אוכל` — 819 verb tokens on the shelf — is `אָכַל`'s
        present, `אֻכַּל`'s past and `יָכֹל`'s and `הוּכַל`'s future, letter for letter. The
        reader's text is pointed, and `אוֹכֵל` opens on an o, which only the פעל's present
        does. So each candidate is kept only where it has a form spelled with these
        letters (fuller or thinner) whose binyan and tense open on this vowel
        (`_OPENING`); a candidate with no such form is out.

        **Refused wherever anything else could be it.** A form the table does not
        constrain — the פעל's imperative — rules nothing out. A verb whose binyan cannot
        be read off its lemma cannot be checked, so where it has such a form nothing is
        chosen. And any verb *outside* the candidates with such a form refuses too, for
        the verb the word is may not be a candidate at all.

        Measured 2026-10-03 over the shelf's current builds: `אוכל` draws a table for 422
        of its 828 tokens, against 102. Read by hand, the tables it newly settles are
        right but for a handful. `נֶעֱבָד` "is worshipped", filed under `עבד`, is the shape
        of them: `עָבַד` writes its future `נעבוד` in those letters, a פעל future may open on
        a segol (`אֶעֱבֹד`), and the נִפְעַל it is spells nothing `נעבד` in the table.

        Empty where the word is unpointed, or nothing is spelled with its letters: the
        pointing then says nothing, and the other signals are asked as before. What it
        names, `of` still refuses where the word's binyan or the page says otherwise.
        """
        if not seen or bare(seen) == seen:
            # Unpointed, the word says nothing its letters did not already say.
            return []
        exact = [
            lid
            for lid in found
            if (verb := self.verbs.get(lid))
            and (verb.lemma == seen or any(form.written == seen for form in verb.forms))
        ]
        if exact:
            return exact
        opens = opening_of(seen)
        letters = _letters(seen)
        if opens is None or not letters:
            return exact
        # The Mishnah's plural in ין is the table's ים, as for the present (`_plural`).
        spelled = {letters, _plural(letters, "Number=Plur")}
        wanted = {key for one in spelled for key in _orthographies(one)}
        cells: dict[str, list[Form]] = {}
        for key in wanted:
            for lid, form in self._spelling_index().get(key, ()):
                cells.setdefault(lid, []).append(form)
        kept: list[str] = []
        unread: list[str] = []
        rivals = False
        for lid, forms in cells.items():
            binyan = self.binyan_of(lid)
            if binyan is not None and not any(
                (allowed := _OPENING.get((binyan, _tense_of(form)))) is None or opens in allowed
                for form in forms
            ):
                continue
            if lid not in found:
                # **Asked of the whole table**, as the present is (`_by_present`): the verb
                # the word really is may not be one of the lemma's candidates. `נִכְתֹּב`
                # "we shall write" filed under `נכתב` has only `נִכְתַּב` to choose from,
                # whose past opens the same way; `כָּתַב` writes it `נכתוב`, and is a rival.
                rivals = True
            elif binyan is None:
                unread.append(lid)
            else:
                kept.append(lid)
        # A verb whose binyan nobody can read is never ruled out, and never chosen either:
        # the vowel can only vouch for a verb whose pattern it can be checked against.
        if rivals or unread:
            return []
        return kept

    def _spelling_index(self) -> dict[str, list[tuple[str, Form]]]:
        """Every form in the table, under both of its `_orthographies`."""
        if not self._spelled:
            for lid, verb in self.verbs.items():
                for form in verb.forms:
                    for key in _orthographies(_letters(form.written)):
                        self._spelled.setdefault(key, []).append((lid, form))
        return self._spelled

    def _present_index(self) -> dict[str, list[tuple[str, Form]]]:
        """Every present-tense form in the table, under both of its `_orthographies`."""
        if not self._present:
            for lid, verb in self.verbs.items():
                for form in verb.forms:
                    if _PRESENT.isdisjoint(form.features):
                        continue
                    for key in _orthographies(_letters(form.written)):
                        self._present.setdefault(key, []).append((lid, form))
        return self._present

    def _by_present(
        self, found: tuple[str, ...], said: Iterable[tuple[str, str, str]]
    ) -> str | None:
        """The verb a present-tense form on the page belongs to, where only one could.

        **The participle is where the table ran out** (targum-internal#307, 2026-09-27).
        The annotator files a participle under itself — `עומד`, `יוצא`, `כותב` — and seldom
        says its binyan. Wikidata spells that same `עומד` as the past of `עוּמַּד`, the
        פּוּעַל of the same root written in full, and `אומר` as the future of `הוּמַר`. So
        every one of those words had two candidates, and nothing to choose between them.

        The annotator did say the tense. A participle is tagged `Tense=Pres`,
        `VerbForm=Part`, or with every person at once (`Person=1,2,3`), which is how the
        present is marked, having no person of its own. `עומד` in the present is `עָמַד`'s
        and not `עוּמַּד`'s, whose present is `מעומד`. Where it is, the form's grammar settles
        the verb the way the reader would: by what the word is doing in the sentence.

        **Only the present, and only where the whole table agrees it is one verb's.** A
        form votes only if exactly one verb anywhere in the table — not only among this
        word's candidates — writes a present of its gender and number in those letters,
        and that verb is a candidate. Asked of the whole table because the verb the
        reader is looking at may not be a candidate at all: a פּוּעַל `מְפֻזָּר` has the
        letters of the פִּיעֵל's present, and the פּוּעַל is filed elsewhere.

        **Spelled either way.** Hebrew writes a vowel with a ו or a י, or leaves it out,
        and the table and the text need not agree: the Bible's `נֹתֵן` has the letters of
        the נִפְעַל's `נִתָּן`, and the paal's present in the table is `נותן`. So a verb whose
        present could be the same word spelled fuller or thinner is a rival, and a rival
        refuses (`_orthographies`). Past and future forms are not asked at all: that is
        where the full and thin spellings of different binyanim collide most, and a first
        version that asked every tense on letters alone was right 64% of the time against
        the Open Scriptures hand tagging.

        **Every other form of the word on the page must be this verb's.** One table is
        drawn for the word, so a form the present did not settle must be one the chosen
        verb writes, spelled either way, and none the other candidates write. And every
        candidate must have a present in the table at all, or its silence proves nothing.

        Measured 2026-09-27 over the shelf's current builds: 2,186 more verb tokens get a
        table, 75.6% → 77.0%, and 98 of 100 of them read by hand are right; the two wrong
        are an Aramaic participle in Daniel and a noun tagged as a verb. Against the
        tables the binyan and the readings already settle, it names the same verb 97.2%
        of the time (3,352 of 3,448), and every disagreement read by hand was the other
        signal's mistake — `חוֹשֵׁב` "thinks" tagged פּוּעַל, `גָּרִים` "dwell" given `יָגֹר`
        "fear". A disagreement still refuses, as every disagreement here does.
        """
        said = tuple(said)
        if not said:
            return None
        index = self._present_index()
        named: set[str] = set()
        voted: set[str] = set()
        quiet: list[str] = []
        dots: set[str] = set()
        for form, feats, surface in said:
            dots |= shin_of(surface)
            spelled = _plural(_letters(form), feats)
            if not spelled:
                continue
            wanted = present_wanted(feats)
            if wanted is None:
                quiet.append(spelled)
                continue
            cells = {
                (lid, cell.written, cell.features)
                for key in _orthographies(spelled)
                for lid, cell in index.get(key, ())
                if _agrees(cell, wanted)
            }
            rivals = {lid for lid, _, _ in cells}
            exact = {lid for lid, cell, _ in cells if _letters(cell) == spelled}
            if len(exact) == 1 and rivals == exact and exact <= set(found):
                named |= exact
                voted.add(spelled)
            elif rivals & set(found):
                # The present names a candidate, but not alone.
                return None
            else:
                quiet.append(spelled)
        if len(named) != 1:
            return None
        chosen = named.pop()
        # `ש` is two letters that share a shape, and the source is letters alone:
        # `הַפּוֹרֵשׁ` "who parts from" is spelled like `פּוֹרֵשׂ` "who spreads", and the
        # table has only the second. Where the page and the lemma both put the dot and
        # put it on different sides, they are different verbs.
        told = shin_of(self.verbs[chosen].lemma)
        if dots and told and dots.isdisjoint(told):
            return None
        if any(
            (verb := self.verbs.get(lid)) is None
            or not any(not _PRESENT.isdisjoint(form.features) for form in verb.forms)
            for lid in found
        ):
            return None
        others: set[str] = set()
        for lid in found:
            if lid != chosen and (other := self.verbs.get(lid)):
                others |= _spellings(other)
        mine = _spellings(self.verbs[chosen])
        for spelled in quiet:
            if spelled in voted:
                continue
            if not _spelled_by(spelled, mine) or _spelled_by(spelled, others):
                return None
        return chosen

    def _named(self, found: tuple[str, ...], form: str) -> str | None:
        """The one candidate targum's own tagging reads this written form as, if any."""
        reading = self.readings.get(_letters(form))
        if reading is None:
            return None
        lemma, binyan = reading
        hits = [
            lid
            for lid in found
            if (verb := self.verbs.get(lid))
            and bare(verb.lemma) == lemma
            and binyan_of(verb.lemma) == binyan
        ]
        return hits[0] if len(hits) == 1 else None

    def _read_otherwise(
        self, found: tuple[str, ...], chosen: str, written: tuple[str, ...]
    ) -> bool:
        """Whether a form of this word on the page is read as one of the *other* verbs.

        The binyan decides for the whole page, but it is the first occurrence's binyan,
        and the annotator files more than one verb under one lemma: `נעשה` tagged נִפְעַל
        on a page that also writes `עָשְׂתָה` and `לַעֲשׂוֹת`, which are the פעל. Drawing the
        נִפְעַל table over those is the wrong table the card exists not to draw. Measured
        2026-09-27 over the shelf's current builds, this refuses 585 tokens' tables, and
        the rows it refuses are that shape — `נעשה`, `נשמע`, `ענה` under a פיעל beside
        `וַיַּעַן` (targum-internal#307).
        """
        for form in written:
            named = self._named(found, form)
            if named is not None and named != chosen:
                return True
        return False

    def _by_reading(self, found: tuple[str, ...], written: Iterable[str]) -> Paradigm | None:
        """The verb every form on the page is read as, where targum's own tagging says.

        targum-internal#307 decided (2026-09-27) to break the ties Wikidata cannot from
        targum's own `Token.binyan`: the annotator tags a binyan on most verbs, and what
        it tags a written form as, counted over the shelf, is evidence about the same form
        where it tagged nothing. `אוֹמֵר` is the commonest verb in the Mishnah; the annotator
        files it under `אומר` with no binyan, which is both `אָמַר` and `הוּמַר`, and so it
        drew no table. Everywhere it *was* tagged, `אומר` was the פעל of `אמר`.

        **Keyed on the written form, and not on the lemma.** Measured first, keying on the
        lemma was tried and dropped: an untagged occurrence is exactly where the old
        lemmatizer most often filed a word under the wrong lemma — `ויאמר` under `נאמר` —
        so the lemma's usual binyan picked a נִפְעַל for "and he said", and checked
        against the Open Scriptures hand tagging of the same tokens it was right 86% of
        the time. The form is the thing the reader is looking at, and it does not lie.

        **And both halves of a reading must name the same candidate** — the lemma and the
        binyan — so a reading that points outside this word's candidates refuses rather
        than landing on a neighbour: `אוֹכֵל` "eats" is read as `אכל`, and `יָכֹל` "can",
        which also spells a form `אוכל`, is not taken for it.

        **One table per word on the page**, so every form of it on the page has a say. A
        form read as another verb refuses; a form with no reading must be one of the
        chosen verb's own forms and none of the other candidates'.

        Checked against the Open Scriptures hand tagging of the same tokens in an older
        build of the Tanakh, each document's own counts held out, this answer is right
        97.9% of the time (737 of 753), against 95.8% for the tables the binyan already
        settles. Read by hand over the shelf's current builds: 3,155 of the 3,245 tokens
        it settles are `אוֹמֵר`, `אוֹמְרִים`, `לֵאמֹר` and the rest of the פעל of `אמר`, all
        right, and three of the other ninety are wrong.
        """
        named: set[str] = set()
        quiet: list[str] = []
        for form in written:
            spelled = _letters(form)
            if not spelled:
                continue
            if spelled not in self.readings:
                quiet.append(spelled)
                continue
            hit = self._named(found, spelled)
            if hit is None:
                # Read as a verb that is not one of this word's candidates, or as two.
                return None
            named.add(hit)
        if len(named) != 1:
            return None
        chosen = named.pop()
        verb = self.verbs.get(chosen)
        if verb is None:
            return None
        # A form with no reading of its own may ride along only where it could be no
        # other candidate: spelled by the chosen verb, and by none of the others. The
        # annotator files `שֶׁנֶּאֱמַר` and `אָמְרוּ` under one lemma, `נאמר`, and `אָמְרוּ`
        # is read as `אָמַר` — but `נאמר` is also a form of `אָמַר`, "we shall say", so a
        # looser test drew the פעל table over "as it is said" 218 times on the shelf.
        others: set[str] = set()
        for lid in found:
            if lid != chosen and (other := self.verbs.get(lid)):
                others |= _spellings(other)
        mine = _spellings(verb)
        if any(spelled not in mine or spelled in others for spelled in quiet):
            return None
        return verb


#: The features that make a form a present, which is where a participle sits in a table.
_PRESENT = frozenset({"present", "participle"})


def present_wanted(feats: str) -> dict[str, str] | None:
    """The gender and number a present-tense occurrence asks of a form, or None where
    the annotator did not say the occurrence is in the present.

    `feats` is the occurrence's Universal Dependencies grammar. The present is said three
    ways: `Tense=Pres`, `VerbForm=Part`, and a person that is every person at once,
    `Person=1,2,3`, which is how the annotator marks a participle — the present has no
    person of its own. An infinitive or an occurrence with another tense is not it.
    """
    parts = dict(part.split("=", 1) for part in (feats or "").split("|") if "=" in part)
    present = (
        parts.get("Tense") == "Pres"
        or parts.get("VerbForm") == "Part"
        or (
            parts.get("Person") == "1,2,3"
            and "Tense" not in parts
            and parts.get("VerbForm") not in ("Inf", "Fin")
        )
    )
    if not present or parts.get("Tense", "Pres") != "Pres":
        return None
    wanted: dict[str, str] = {}
    gender = {"Masc": "masculine", "Fem": "feminine"}.get(parts.get("Gender", ""))
    if gender:
        wanted["gender"] = gender
    number = {"Sing": "singular", "Plur": "plural"}.get(parts.get("Number", ""))
    if number:
        wanted["number"] = number
    return wanted


def _agrees(form: Form, wanted: dict[str, str]) -> bool:
    """Whether a form of the table is a present of the gender and number asked for. A
    form that does not say one of them does not disagree with it."""
    features = set(form.features)
    if _PRESENT.isdisjoint(features):
        return False
    for feature, among in (
        ("gender", {"masculine", "feminine"}),
        ("number", {"singular", "plural"}),
    ):
        said = features & among
        if feature in wanted and said and wanted[feature] not in said:
            return False
    return True


def _orthographies(letters: str) -> tuple[str, str]:
    """The letters with every ו after the first dropped, and with every י dropped: the
    two keys under which a spelling fuller or thinner than this one is the same word.

    Separately, so `נוטל` and `ניטל` — `נוֹטֵל` and `נִיטָּל`, an o and an i — stay apart.
    """
    head, rest = letters[:1], letters[1:]
    return (
        "\u05d5" + head + rest.replace("\u05d5", ""),
        "\u05d9" + head + rest.replace("\u05d9", ""),
    )


def _spelled_by(letters: str, spellings: set[str]) -> bool:
    """Whether one of `spellings` is `letters`, spelled fuller or thinner."""
    if letters in spellings:
        return True
    mine = set(_orthographies(letters))
    return any(not mine.isdisjoint(_orthographies(other)) for other in spellings)


def shin_of(text: str) -> set[str]:
    """Which side a pointed `ש` is dotted on — shin, sin, or both where there are two."""
    return {mark for mark in unicodedata.normalize("NFD", text or "") if mark in "\u05c1\u05c2"}


def _plural(letters: str, feats: str) -> str:
    """A plural the Mishnah writes with `ין` is the `ים` the table writes: `אוֹמְרִין`."""
    if "Number=Plur" in (feats or "") and len(letters) > 3 and letters.endswith("\u05d9\u05df"):
        return letters[:-2] + "\u05d9\u05dd"
    return letters


def _spellings(verb: Paradigm) -> set[str]:
    """Every way a verb is written, on letters alone, its dictionary form included."""
    return {_letters(form.written) for form in verb.forms} | {_letters(verb.lemma)}


EMPTY = Table(verbs={}, by_form={})


@lru_cache(maxsize=1)
def readings(path: Path | None = None) -> dict[str, tuple[str, str]]:
    """The shipped readings, read once: a written form, and the verb it is read as.

    Empty where the file is absent or unreadable, which is the state before #307: the
    binyan and the pointing still settle what they settled.
    """
    where = path or READINGS
    try:
        loaded = json.loads(where.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(loaded, dict) or not isinstance(loaded.get("forms"), dict):
        return {}
    out: dict[str, tuple[str, str]] = {}
    for form, row in loaded["forms"].items():
        if isinstance(row, list) and len(row) >= 2:
            out[str(form)] = (str(row[0]), str(row[1]))
    return out


@lru_cache(maxsize=1)
def table(path: Path | None = None) -> Table:
    """The shipped table, read once.

    An empty one where the file is absent or unreadable, which is a working state: the
    card draws the root, the binyan and the way out to Pealim exactly as it did before.
    """
    where = path or TABLE
    if not where.is_file():
        return EMPTY
    try:
        with gzip.open(where, "rt", encoding="utf-8") as raw:
            loaded = json.load(raw)
    except (OSError, json.JSONDecodeError, EOFError):
        return EMPTY
    if not isinstance(loaded, dict):
        return EMPTY
    return from_shipped(loaded, readings())


def from_shipped(
    loaded: dict[str, Any], read: dict[str, tuple[str, str]] | None = None, ruled: bool = True
) -> Table:
    """A table out of the shipped file's shape. `ruled=False` leaves out what `conjugate`
    filled in, which is the table that filling is worked out from."""
    names = [str(name) for name in loaded.get("features") or ()]

    def forms_of(rows: list[Any], by_rule: bool = False) -> list[Form]:
        return [
            Form(
                written=str(written),
                features=tuple(names[at] for at in codes if 0 <= at < len(names)),
                ruled=by_rule,
            )
            for written, codes in rows
        ]

    filled = loaded.get("filled") if ruled else None
    filled = filled if isinstance(filled, dict) else {}
    verbs: dict[str, Paradigm] = {}
    by_form = {
        str(form): tuple(str(lid) for lid in ids)
        for form, ids in (loaded.get("by_form") or {}).items()
    }
    for lid, row in (loaded.get("verbs") or {}).items():
        if not isinstance(row, list) or len(row) != 2:
            continue
        lemma, rows = row
        forms = forms_of(rows[:MOST])
        added = filled.get(lid)
        if isinstance(added, list) and added:
            more = forms_of(added, by_rule=True)
            forms = _in_order(forms + more)
            for form in more:
                spelled = bare(form.written)
                if str(lid) not in by_form.get(spelled, ()):
                    by_form[spelled] = (*by_form.get(spelled, ()), str(lid))
        verbs[str(lid)] = Paradigm(lemma=str(lemma), forms=tuple(forms))
    return Table(verbs=verbs, by_form=by_form, readings=read or {})


def _in_order(forms: list[Form]) -> list[Form]:
    """A filled table in the order a grammar lays one out, so a cell the rule added sits
    where the reader looks for it rather than at the end. Anything in no standard cell
    keeps its place after them."""
    from .conjugate import CELLS

    at = {cell: index for index, cell in enumerate(CELLS)}
    return sorted(forms, key=lambda form: at.get(tuple(sorted(form.features)), len(CELLS)))


def fill(attested: Table) -> dict[str, Filled]:
    """What `conjugate` adds to each verb of a table that is the source's alone.

    The patterns are learned from the same table — every complete, unpointed verb whose
    lemma says its binyan and whose root comes out at three letters — and every verb is
    then asked for what it lacks. Most lack nothing.
    """
    from .conjugate import fill as fill_one
    from .conjugate import learn
    from .hebrew import root_of

    def taught() -> Iterable[tuple[str, str, str, list[tuple[str, tuple[str, ...]]]]]:
        for verb in attested.verbs.values():
            binyan = binyan_of(verb.lemma)
            root = root_of(verb.lemma, binyan) if binyan else None
            if binyan and root:
                yield verb.lemma, binyan, root, [(f.written, f.features) for f in verb.forms]

    patterns = learn(taught())
    return {
        lid: fill_one(
            verb.lemma,
            [(form.written, form.features) for form in verb.forms],
            patterns,
            binyan_of(verb.lemma),
        )
        for lid, verb in attested.verbs.items()
    }
