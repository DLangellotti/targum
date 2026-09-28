"""The chanting marks named, and a verse divided into the phrases they sing.

A Masoretic accent does three jobs at once: it marks the stressed syllable, it names a
fragment of melody, and it says how tightly this word holds to the next one. The third job
is the one a learner needs first. A *disjunctive* accent ends a phrase and a *conjunctive*
one leads into the disjunctive after it, so "mercha tipcha munach etnachta" is two phrases,
not four notes, and the verse's grammar is written into that division.

Nothing here is a model and nothing is spent. The marks are in the text; this reads them.

**Which system.** Twenty-one books are accented one way and three another. The poetic
books — Psalms, Proverbs and Job, "Emet" by their initials — have their own accents
(ole ve-yored, dehi, iluy, tsinnorit) and a different hierarchy over the shared ones, and
reading a psalm by the prose rules would name its marks wrongly with a straight face. So
the poetic system is refused rather than approximated: `read` raises `PoeticAccents` for a
reference in those books and for any verse carrying a mark only they use. Job's prose
frame, 1:1-3:1 and 42:7-17, is accented as prose and is read.

**The hierarchy.** Disjunctives are ranked in four tiers, following Wickes's division of
the prose accents, which is also the one the teaching tradition calls emperors, kings,
dukes and counts:

* emperors: silluq, etnachta
* kings: segol, shalshelet, zakef katan, zakef gadol, tipcha
* dukes: revia, zarka, pashta, yetiv, tevir
* counts: geresh, gershayim, pazer, karnei farah, telisha gedolah, munach legarmeh

Every other accent of the prose system is a conjunctive: munach, mahpach, mercha, mercha
kefulah, darga, kadma, telisha ketanah, yerach ben yomo.

**Four things the codepoints do not say plainly.**

* *Meteg and silluq share U+05BD.* Silluq is the meteg-shaped mark on the stressed syllable
  of a verse's last word, the word before sof pasuq (U+05C3). So the last U+05BD of the
  verse-final word is silluq and every other U+05BD is meteg, which is not an accent and is
  not reported as one.
* *Munach with paseq is a different accent.* A munach followed by the paseq stroke (U+05C0)
  is munach legarmeh, a count. Any other accent followed by paseq keeps its own name; the
  stroke is recorded as a pause. This is the conventional reading and the one a tikkun
  prints; Wickes notes a handful of munach-paseq pairs that are conjunctive, and those are
  named legarmeh here too.
* *Some accents are written twice.* Pashta, segol, zarka and telisha gedolah sit at the
  edge of the word whatever its stress, and editions repeat them on the stressed syllable
  when that is somewhere else. The Leningrad Codex encoding writes pashta's copy as U+05A8
  (the kadma codepoint) and zarka's as U+0598; Sefaria's MAM text writes pashta twice as
  U+0599. Each pair is one accent.
* *Prepositive and postpositive marks look alike in print.* Kadma and pashta, mahpach and
  yetiv, telisha ketanah and gedolah are the same shape in different places. Unicode gives
  each its own codepoint, and this module trusts the codepoint: a text that encoded pashta
  as kadma would be read as kadma.

**Phrases.** Each disjunctive closes a phrase: the words since the last disjunctive, its
conjunctives leading up to it, and itself. A verse's end closes a phrase whatever mark is
there. Words joined by maqaf are one accentual unit and never close a phrase before the
last of them. The phrases nest by rank: a phrase belongs to the first phrase after it
whose closing accent is strictly stronger, which is Wickes's rule that a disjunctive's
domain reaches back to the previous disjunctive of equal or greater power. Etnachta and
silluq have no parent — they are the verse's two halves.

**Sources.** Unicode Standard, Hebrew block (U+0590-U+05FF) and its character names;
W. Wickes, *A Treatise on the Accentuation of the Twenty-One So-Called Prose Books of the
Old Testament* (Oxford, 1887) and *A Treatise on the Accentuation of the Three So-Called
Poetical Books* (Oxford, 1881), both public domain, for the classes, the rule of domains
and Job's prose frame; the table of names and tiers is also the one in Wikipedia's
"Cantillation" article. Nothing here is copied from a copyrighted table: the names are
the tradition's, and the arrangement is this module's.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum
from typing import cast

from ..errors import TargumError

MAQAF = "־"
PASEQ = "׀"
SOF_PASUQ = "׃"
METEG = "ֽ"


class Rank(IntEnum):
    """A disjunctive's strength. Lower is stronger, so `min` finds the ruling one."""

    EMPEROR = 1
    KING = 2
    DUKE = 3
    COUNT = 4


@dataclass(frozen=True, slots=True)
class Accent:
    """One accent of the prose system, or a poetic one named only to be refused.

    `place` is where the mark sits: on the stressed syllable, or at the word's start
    (prepositive) or end (postpositive) whatever the stress. `poetic` marks the ones only
    Psalms, Proverbs and Job use, which have no rank here because this is not their system.
    """

    key: str
    name: str
    hebrew: str
    disjunctive: bool
    rank: Rank | None = None
    place: str = "stress"
    poetic: bool = False

    @property
    def kind(self) -> str:
        return "disjunctive" if self.disjunctive else "conjunctive"

    @property
    def label(self) -> str:
        """The line a word card would carry: "tipcha · disjunctive"."""
        return f"{self.name} · {self.kind}"


def _disjunctive(key: str, name: str, hebrew: str, rank: Rank, place: str = "stress") -> Accent:
    return Accent(key, name, hebrew, True, rank, place)


def _conjunctive(key: str, name: str, hebrew: str, place: str = "stress") -> Accent:
    return Accent(key, name, hebrew, False, None, place)


def _poetic(key: str, name: str, hebrew: str, disjunctive: bool, place: str = "stress") -> Accent:
    return Accent(key, name, hebrew, disjunctive, None, place, poetic=True)


SILLUQ = _disjunctive("silluq", "silluk", "סִלּוּק", Rank.EMPEROR)
ETNACHTA = _disjunctive("etnachta", "etnachta", "אֶתְנַחְתָּא", Rank.EMPEROR)
SEGOL = _disjunctive("segol", "segol", "סֶגּוֹל", Rank.KING, "postpositive")
SHALSHELET = _disjunctive("shalshelet", "shalshelet", "שַׁלְשֶׁלֶת", Rank.KING)
ZAKEF_KATAN = _disjunctive("zakef-katan", "zakef katan", "זָקֵף קָטָן", Rank.KING)
ZAKEF_GADOL = _disjunctive("zakef-gadol", "zakef gadol", "זָקֵף גָּדוֹל", Rank.KING)
TIPCHA = _disjunctive("tipcha", "tipcha", "טִפְחָא", Rank.KING)
REVIA = _disjunctive("revia", "revia", "רְבִיעַ", Rank.DUKE)
ZARKA = _disjunctive("zarka", "zarka", "זַרְקָא", Rank.DUKE, "postpositive")
PASHTA = _disjunctive("pashta", "pashta", "פַּשְׁטָא", Rank.DUKE, "postpositive")
YETIV = _disjunctive("yetiv", "yetiv", "יְתִיב", Rank.DUKE, "prepositive")
TEVIR = _disjunctive("tevir", "tevir", "תְּבִיר", Rank.DUKE)
GERESH = _disjunctive("geresh", "geresh", "גֵּרֵשׁ", Rank.COUNT)
GERSHAYIM = _disjunctive("gershayim", "gershayim", "גֵּרְשַׁיִם", Rank.COUNT)
PAZER = _disjunctive("pazer", "pazer", "פָּזֵר", Rank.COUNT)
KARNEI_FARAH = _disjunctive("karnei-farah", "karnei farah", "קַרְנֵי פָרָה", Rank.COUNT)
TELISHA_GEDOLAH = _disjunctive(
    "telisha-gedolah", "telisha gedolah", "תְּלִישָׁא גְדוֹלָה", Rank.COUNT, "prepositive"
)
LEGARMEH = _disjunctive("munach-legarmeh", "munach legarmeh", "מֻנַּח לְגַרְמֵיהּ", Rank.COUNT)

MUNACH = _conjunctive("munach", "munach", "מֻנַּח")
MAHPACH = _conjunctive("mahpach", "mahpach", "מַהְפַּךְ")
MERCHA = _conjunctive("mercha", "mercha", "מֵרְכָא")
MERCHA_KEFULAH = _conjunctive("mercha-kefulah", "mercha kefulah", "מֵרְכָא כְּפוּלָה")
DARGA = _conjunctive("darga", "darga", "דַּרְגָּא")
KADMA = _conjunctive("kadma", "kadma", "קַדְמָא")
TELISHA_KETANAH = _conjunctive("telisha-ketanah", "telisha ketanah", "תְּלִישָׁא קְטַנָּה", "postpositive")
YERACH = _conjunctive("yerach-ben-yomo", "yerach ben yomo", "יֶרַח בֶּן יוֹמוֹ")

OLE = _poetic("ole", "ole", "עוֹלֶה", True)
ILUY = _poetic("iluy", "iluy", "עִלּוּי", False)
DEHI = _poetic("dehi", "dehi", "דְּחִי", True, "prepositive")
ETNACH_HAFUCH = _poetic("etnach-hafuch", "etnach hafuch", "אֶתְנַח הָפוּךְ", False)

#: Every codepoint U+0591-U+05AE, read by the prose system. U+0598 and U+059D are named
#: for what they are in the twenty-one books — zarka's copy on the stress, and geresh set
#: before the stress — rather than for the poetic accents Unicode also lets them be.
ACCENTS: dict[int, Accent] = {
    0x0591: ETNACHTA,
    0x0592: SEGOL,
    0x0593: SHALSHELET,
    0x0594: ZAKEF_KATAN,
    0x0595: ZAKEF_GADOL,
    0x0596: TIPCHA,
    0x0597: REVIA,
    0x0598: ZARKA,
    0x0599: PASHTA,
    0x059A: YETIV,
    0x059B: TEVIR,
    0x059C: GERESH,
    0x059D: GERESH,
    0x059E: GERSHAYIM,
    0x059F: KARNEI_FARAH,
    0x05A0: TELISHA_GEDOLAH,
    0x05A1: PAZER,
    0x05A2: ETNACH_HAFUCH,
    0x05A3: MUNACH,
    0x05A4: MAHPACH,
    0x05A5: MERCHA,
    0x05A6: MERCHA_KEFULAH,
    0x05A7: DARGA,
    0x05A8: KADMA,
    0x05A9: TELISHA_KETANAH,
    0x05AA: YERACH,
    0x05AB: OLE,
    0x05AC: ILUY,
    0x05AD: DEHI,
    0x05AE: ZARKA,
}

#: Pashta's copy on the stressed syllable, in the Leningrad encoding: the kadma codepoint
#: on a word that also carries pashta is pashta, not a second accent.
_PASHTA_COPY = 0x05A8

#: The books whose accents are not these, by the names both the shelf ("Psalms 23:1") and
#: the morphology ("Ps.23.1") use.
POETIC_BOOKS = frozenset({"Psalms", "Ps", "Proverbs", "Prov", "Job"})

#: Job's opening and closing narrative, accented as prose, as (chapter, verse) bounds.
JOB_PROSE = (((1, 1), (3, 1)), ((42, 7), (42, 17)))

_REF = re.compile(r"^(?P<book>.+?)[\s.](?P<chapter>\d+)[:.](?P<verse>\d+)$")

#: A section mark — פ or ס in brackets anywhere, or bare after a verse — is not a word.
_SECTION = re.compile(r"^[({\[][ספ][)}\]]$")
_BARE_SECTION = re.compile(r"^[ספ]$")


class PoeticAccents(TargumError):
    """A verse from Psalms, Proverbs or Job, whose accents are a different system."""

    def __init__(self, where: str) -> None:
        super().__init__(
            f"{where} is accented in the poetic system of Psalms, Proverbs and Job, "
            "which has its own accents and its own hierarchy; only the prose system of "
            "the other twenty-one books is read."
        )


def system(ref: str) -> str:
    """Which accent system a reference is written in: "prose" or "poetic".

    A reference this cannot parse is assumed to be prose — the twenty-one books are the
    ordinary case — and `read` still refuses a verse whose marks say otherwise.
    """
    found = _REF.match(ref.strip())
    if found is None:
        return "poetic" if ref.strip() in POETIC_BOOKS else "prose"
    book = found["book"]
    if book not in POETIC_BOOKS:
        return "prose"
    if book == "Job":
        place = (int(found["chapter"]), int(found["verse"]))
        if any(first <= place <= last for first, last in JOB_PROSE):
            return "prose"
    return "poetic"


@dataclass(frozen=True, slots=True)
class Word:
    """One written word, and what the accents say about it.

    `text` is the word as written, without the maqaf, paseq or sof pasuq beside it.
    `accents` is every accent it carries, once each, in reading order; `accent` is the
    one that rules it: its strongest disjunctive, otherwise its last conjunctive.
    `joined` is a maqaf after it, which makes it one accentual unit with the next word.
    `token` is which whitespace-separated token of the text it was written in — words
    joined by maqaf share one — so a phrase can be found in anything else counted by
    token, a recording's word clocks among them.
    """

    text: str
    accents: tuple[Accent, ...]
    accent: Accent | None
    joined: bool = False
    paseq: bool = False
    verse_end: bool = False
    token: int = 0


@dataclass(frozen=True, slots=True)
class Phrase:
    """A run of words ending in a disjunctive, or in the verse's end.

    `words` are indices into the verse's words. `closer` is the disjunctive that ends it,
    or None where the verse ends on no disjunctive or the text stops mid-phrase. `parent`
    is the index of the phrase this one subdivides, or None at the top of the verse.
    """

    words: tuple[int, ...]
    closer: Accent | None
    rank: Rank | None
    parent: int | None


@dataclass(frozen=True, slots=True)
class Verse:
    words: tuple[Word, ...]
    phrases: tuple[Phrase, ...]

    def phrase_of(self, word: int) -> int:
        """The index of the phrase that holds word number `word`."""
        for number, phrase in enumerate(self.phrases):
            if word in phrase.words:
                return number
        raise IndexError(word)


def accents_of(word: str, *, verse_end: bool = False, paseq: bool = False) -> tuple[Accent, ...]:
    """Every accent on one written word, once each, in reading order.

    `verse_end` says the word is the last of its verse, which is the only thing that turns
    its U+05BD from meteg into silluq; `paseq` says a paseq follows it, which turns a
    munach into munach legarmeh.
    """
    codes = [ord(char) for char in word if ord(char) in ACCENTS]
    if 0x0599 in codes:
        codes = [code for code in codes if code != _PASHTA_COPY]
    out: list[Accent] = []
    for code in codes:
        accent = ACCENTS[code]
        if accent is MUNACH and paseq:
            accent = LEGARMEH
        if accent not in out:
            out.append(accent)
    if verse_end and METEG in word:
        out.append(SILLUQ)
    return tuple(out)


def ruling(accents: tuple[Accent, ...]) -> Accent | None:
    """The accent that governs a word carrying several: its strongest disjunctive, the
    later one on a tie, and otherwise its last conjunctive."""
    disjunctives = [accent for accent in accents if accent.disjunctive and accent.rank]
    if disjunctives:
        strongest = min(accent.rank for accent in disjunctives if accent.rank)
        return [accent for accent in disjunctives if accent.rank == strongest][-1]
    return accents[-1] if accents else None


def _tokens(text: str) -> list[tuple[str, bool, bool, bool, int]]:
    """(word, joined, paseq, verse_end, token) for each written word, in order."""
    words: list[list[object]] = []
    stopped = SOF_PASUQ in text
    for place, token in enumerate(text.split()):
        if _SECTION.match(token) or (words and words[-1][3] and _BARE_SECTION.match(token)):
            continue
        if not any("א" <= char <= "ת" for char in token):
            if PASEQ in token and words:
                words[-1][2] = True
            if SOF_PASUQ in token and words:
                words[-1][3] = True
            continue
        end = SOF_PASUQ in token
        stroke = PASEQ in token
        token = token.replace(SOF_PASUQ, "").replace(PASEQ, "")
        pieces = token.split(MAQAF)
        for number, piece in enumerate(pieces):
            last = number == len(pieces) - 1
            if not piece:
                continue
            words.append([piece, not last, stroke and last, end and last, place])
    if words and not stopped:
        words[-1][3] = True
    return [(str(w[0]), bool(w[1]), bool(w[2]), bool(w[3]), cast(int, w[4])) for w in words]


def read(text: str, ref: str | None = None) -> Verse:
    """A pointed verse, its words named and grouped into trope phrases.

    `text` is one verse as the edition writes it, with or without its sof pasuq; without
    one, its last word is taken to end the verse. Several verses in one string are read
    in turn, each sof pasuq ending one.

    Raises `PoeticAccents` for a reference in Psalms, Proverbs or Job outside Job's prose
    frame, and for a verse carrying an accent only those books use.
    """
    if ref is not None and system(ref) == "poetic":
        raise PoeticAccents(ref)
    words: list[Word] = []
    for surface, joined, stroke, end, token in _tokens(text):
        accents = accents_of(surface, verse_end=end, paseq=stroke)
        if any(accent.poetic for accent in accents):
            raise PoeticAccents(ref or "This verse")
        words.append(Word(surface, accents, ruling(accents), joined, stroke, end, token))
    return Verse(tuple(words), _phrases(words))


def _phrases(words: list[Word]) -> tuple[Phrase, ...]:
    runs: list[tuple[tuple[int, ...], Accent | None, Rank | None]] = []
    held: list[int] = []
    for number, word in enumerate(words):
        held.append(number)
        closes = word.accent is not None and word.accent.disjunctive and not word.joined
        if closes or word.verse_end:
            closer = word.accent if closes else None
            rank = Rank.EMPEROR if word.verse_end else (closer.rank if closer else None)
            runs.append((tuple(held), closer, rank))
            held = []
    if held:
        runs.append((tuple(held), None, None))
    phrases: list[Phrase] = []
    for number, (members, closer, rank) in enumerate(runs):
        parent = None
        if rank is not None and rank is not Rank.EMPEROR:
            for later in range(number + 1, len(runs)):
                stronger = runs[later][2]
                if stronger is not None and stronger < rank:
                    parent = later
                    break
        phrases.append(Phrase(members, closer, rank, parent))
    return tuple(phrases)
