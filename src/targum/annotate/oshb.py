"""The Hebrew Bible, already analysed by hand, looked up rather than predicted.

A model that reads Hebrew is guessing, and on the biblical register it guesses badly:
measured over Genesis 1, the current annotator returns a lemma that is not a word in any
language once every four words, and the best available replacement still mistakes the
waw-consecutive — glossing "and he saw" as "to fear" seven times in a chapter.

None of that is necessary. **The Tanakh is a fixed corpus and it has already been
morphologically tagged, by people, and released openly.** The Open Scriptures Hebrew Bible
carries, for every word of the Hebrew Bible, where its prefixes divide, which lexeme it
belongs to, and its full morphology. On a closed corpus a lookup does not merely beat a
model — it is the thing the model is scored against.

So the Tanakh is not annotated here. It is read.

**What comes from where.** The consonantal text is the Westminster Leningrad Codex and is
in the public domain. The lemma and morphology are the Open Scriptures Hebrew Bible
Project's own work, under CC BY 4.0, which is why `LICENSING.md` credits them and why this
is a dependency targum can carry into a paid product where the previous annotator was not.

**Why it is fetched rather than vendored.** Forty books is tens of megabytes of somebody
else's data that changes on its own schedule. It goes where the language models go —
`model_dir()`, which survives `cache clear` — and is converted once on arrival into the
shape this module reads, so nothing parses XML while a reader waits.

The Mishnah on the shelf is out of scope: this is the Hebrew Bible, and rabbinic Hebrew is
a different register with different resources.
"""

from __future__ import annotations

import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import NamedTuple

from ..errors import TargumError
from ..models import NUMBER_MARK, numbered
from ..paths import ensure, model_dir, write_atomic

SOURCE = "https://raw.githubusercontent.com/openscriptures/morphhb/master/wlc/{book}.xml"
#: Strong's numbers into Hebrew headwords. The morphology says *which* lexeme a word
#: belongs to, as a number; this says what that lexeme is called. Same project, same
#: licence, and the dictionary underneath is public domain.
LEXICON = "https://raw.githubusercontent.com/openscriptures/HebrewLexicon/master/HebrewStrong.xml"
LEXICON_FILE = "strongs.json"
#: What each of those lexemes means, from the same file and the same download. Kept
#: beside the headwords rather than inside them so a box that fetched before this existed
#: still reads its headwords and simply has no senses.
SENSES_FILE = "senses.json"

#: What a lexeme means in a word or two, from STEP Bible's Translators Brief lexicon of
#: Extended Strongs for Hebrew (targum-internal#510). Strong's own definitions are the
#: King James translators' thickets, typos and all; these are the short glosses Tyndale
#: House scholars wrote against the same numbers, under CC BY 4.0.
#:
#: **Only the Gloss column is read.** The file's Meaning column is the Abridged BDB, ©
#: Online Bible, carved out of STEP Bible's grant, and it is never stored, shown or
#: shipped. Pinned to a commit, because the file's alignment is "not yet completed" and
#: moves, and fetched rather than vendored, because the file asks not to be redistributed.
#: What targum changes is written down in `tbesh_changes.tsv`, as the licence asks.
TBESH = (
    "https://raw.githubusercontent.com/STEPBible/STEPBible-Data/"
    "48b7cfbda441adb6445ea565b4ed23dd98dfdf2e/Lexicons/"
    "TBESH%20-%20Translators%20Brief%20lexicon%20of%20Extended%20Strongs%20for%20Hebrew"
    "%20-%20STEPBible.org%20CC%20BY.txt"
)
TBESH_FILE = "tbesh.json"
TBESH_CREDIT = "STEP Bible"
TBESH_LICENCE = "CC BY 4.0"
#: The change note and the hand fixes, in one file beside this one.
TBESH_CHANGES = Path(__file__).with_name("tbesh_changes.tsv")

#: Named where the licence requires it, and here as well because a file that carries
#: somebody's work should say whose it is at the top of the thing that reads it.
CREDIT = "Open Scriptures Hebrew Bible Project"
LICENCE = "CC BY 4.0"

_OSIS_NS = {"o": "http://www.bibletechnologies.net/2003/OSIS/namespace"}

#: How a reference names a book, against how the morphology file does. Written out rather
#: than derived: "I Samuel" is `1Sam` and "Song of Songs" is `Song`, and a rule that got
#: those from the words would be a rule with two exceptions and no way to check itself.
#:
#: The keys are the book names that actually appear in this shelf's refs, gathered from
#: the built texts rather than from a list of the canon.
BOOKS: dict[str, str] = {
    "Genesis": "Gen",
    "Exodus": "Exod",
    "Leviticus": "Lev",
    "Numbers": "Num",
    "Deuteronomy": "Deut",
    "Joshua": "Josh",
    "Judges": "Judg",
    "I Samuel": "1Sam",
    "II Samuel": "2Sam",
    "I Kings": "1Kgs",
    "II Kings": "2Kgs",
    "Isaiah": "Isa",
    "Jeremiah": "Jer",
    "Ezekiel": "Ezek",
    "Hosea": "Hos",
    "Joel": "Joel",
    "Amos": "Amos",
    "Obadiah": "Obad",
    "Jonah": "Jonah",
    "Micah": "Mic",
    "Nahum": "Nah",
    "Habakkuk": "Hab",
    "Zephaniah": "Zeph",
    "Haggai": "Hag",
    "Zechariah": "Zech",
    "Malachi": "Mal",
    "Psalms": "Ps",
    "Proverbs": "Prov",
    "Job": "Job",
    "Song of Songs": "Song",
    "Ruth": "Ruth",
    "Lamentations": "Lam",
    "Ecclesiastes": "Eccl",
    "Esther": "Esth",
    "Daniel": "Dan",
    "Ezra": "Ezra",
    "Nehemiah": "Neh",
    "I Chronicles": "1Chr",
    "II Chronicles": "2Chr",
}


#: A lexeme identified by number rather than by letter. The tagging writes a Strong's
#: number against a piece that is a word and a single letter — `b`, `l`, `c` — against a
#: piece that is a prefix stuck to one. That is the whole of how `Word.content` tells
#: them apart.
_NUMBERED = re.compile(r"^\d")

#: The morphology's first letter for a pronominal suffix, and for the preposition one
#: hangs on: `ל֥וֹ` is `R` + `Sp3ms`.
_SUFFIX = "S"
_HOST = "R"


class Word(NamedTuple):
    """One orthographic word of the Hebrew Bible, as it was tagged.

    `pieces`, `lexemes` and `morph` are the same length and line up: a word written
    `בְּ/רֵאשִׁ֖ית` is two pieces, the preposition and the noun, and each piece has its own
    lexeme and its own morphology. A word with no prefix is one piece, which is most of
    them.
    """

    #: As written, pointed and cantillated, with the division marks taken out.
    text: str
    #: The word cut where its prefixes divide, which is the division a person made.
    pieces: tuple[str, ...]
    #: Strong's number per piece, or a letter for a prefix — `b` for the bet of `בְּרֵאשִׁית`.
    #: A number identifies a lexeme, so it tells `ספר` the book from `ספר` the scribe,
    #: which no spelling of the word can.
    lexemes: tuple[str, ...]
    #: The morphology code per piece, with the leading language letter removed: `Ncfsa`
    #: is a common feminine singular absolute noun, `Vqp3ms` a qal perfect 3ms verb.
    morph: tuple[str, ...]
    #: Where the Masoretes wrote one word and read another, what was written. Empty for
    #: the overwhelming majority of words, which are read as they are written. `text`
    #: above is always the *read* form, because that is the one the shelf carries and
    #: the one a reader is looking at.
    ketiv: str = ""

    @property
    def content(self) -> int:
        """Which piece is the word itself rather than something stuck to it.

        **The last piece that has a lexeme number of its own.** The tagging numbers a
        piece that is a word and writes a bare letter — `b`, `l`, `c` — against a piece
        that is a prefix, so the numbers say which piece the word is and nothing has to
        be assumed about where in the word it sits.

        It used to say "the last piece", which is true of Hebrew prefixes and wrong at
        both ends of a word (targum-internal#64):

        - **Aramaic suffixes its definite article.** `מַלְכָּא` is `מַלְכָּ` + `א`, so the last
          piece is the article and the king came back a `PART`. 18.8% of the Aramaic in
          Daniel and Ezra.
        - **Hebrew suffixes its pronouns.** `זַרְעוֹ`, "his seed", is `זַרְע` + `וֹ`, so the
          last piece is the suffix and a noun came back a `PRON`. 17.2% of the words in
          Genesis carry one.

        Measured over Genesis, Isaiah, Psalms, Daniel and Ezra: 83.6% of words are
        unchanged by this and every one of the 10,986 that move was a `PRON` — 6,851 of
        them nouns, 2,435 verbs. Nothing becomes a pronoun that was not one.

        Where no piece carries a number, a preposition with a pronoun on the end is the
        preposition (2026-10-12, known issues 1.4). `בּוֹ` is `בְּ` + `וֹ` with no noun between
        them, and this used to say the suffix was the word — so `בּוֹ` and `ל֥וֹ` were filed
        under ו and a reader was told "and", 240 times in Genesis and Exodus alone. The
        preposition is the word to learn and the suffix is the same handful of endings on
        every one of them, which is how `אִתּוֹ` (numbered, so already the preposition) and
        the modern path's `שלו` and `בו` are filed too. Otherwise the last piece stands.
        """
        numbered = [i for i, lexeme in enumerate(self.lexemes) if _NUMBERED.match(lexeme.strip())]
        if numbered:
            return min(numbered[-1], len(self.pieces) - 1)
        last = len(self.pieces) - 1
        if 0 < last < len(self.morph) and self.morph[last].startswith(_SUFFIX):
            hosts = [i for i, code in enumerate(self.morph[:last]) if code.startswith(_HOST)]
            if hosts:
                return hosts[-1]
        return last

    @property
    def lexeme(self) -> str:
        """Which lexeme the content piece belongs to, or "" where none was recorded.

        Clamped rather than indexed straight, because the three lists usually line up and
        occasionally do not: a word read differently from how it is written carries its
        pieces from the text and its lemma from the attribute, and the attribute is
        sometimes one field where the text is two. Indexing past the end there would have
        lost a whole verse to an exception.
        """
        return self.lexemes[min(self.content, len(self.lexemes) - 1)] if self.lexemes else ""

    @property
    def code(self) -> str:
        """The morphology of the content piece, clamped for the reason `lexeme` is."""
        return self.morph[min(self.content, len(self.morph) - 1)] if self.morph else ""


def root() -> Path:
    """Where the tagged text lives. Beside the language models, and for the same reason:
    tens of megabytes that a `cache clear` has no business removing."""
    return model_dir() / "oshb"


def available() -> bool:
    return (root() / LEXICON_FILE).is_file() and any(
        (root() / f"{code}.json").is_file() for code in BOOKS.values()
    )


_HEADWORDS: dict[str, str] | None = None
#: Bare spelling -> every pointed headword written that way. How the lexicon says a
#: spelling is shared: `אלה` has five entries, and which one a word belongs to is a fact
#: the morphology knows and the bare lemma throws away.
_SPELLED: dict[str, set[str]] | None = None


def _lexicon() -> dict[str, str]:
    global _HEADWORDS
    if _HEADWORDS is None:
        path = root() / LEXICON_FILE
        try:
            _HEADWORDS = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _HEADWORDS = {}
    return _HEADWORDS


_MEANINGS: dict[str, str] | None = None


def _senses() -> dict[str, str]:
    global _MEANINGS
    if _MEANINGS is None:
        path = root() / SENSES_FILE
        try:
            _MEANINGS = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # A box that fetched before senses were kept. Nothing is broken by their
            # absence: every word still carries its dictionary form and its morphology.
            _MEANINGS = {}
    return _MEANINGS


def headword(lexeme: str) -> str:
    """The Hebrew word a Strong's number names, pointed, or "" where it names none.

    The number arrives as the morphology writes it — `7225`, or `1254 a` where a lexeme
    was split into senses after Strong numbered it. The letter is a distinction Strong's
    own dictionary does not carry, so it is dropped to find the headword. What tells
    `סֵפֶר` the book from `סֹפֵר` the scribe is the pointing of the headword itself —
    see `contested`.
    """
    number = (lexeme or "").strip().split(" ")[0].lstrip("H")
    if not number.isdigit():
        return ""
    return _lexicon().get(number, "")


def sense(lexeme: str) -> str:
    """What a Strong's number means in English, or "" where nothing was recorded.

    The same number the morphology already writes against every word of the Hebrew Bible,
    which is why this needs no lookup and cannot be wrong about which word it is: the
    tagging says the lexeme and this says what that lexeme means. Free, offline, and
    public domain (targum-internal#64).

    Empty on a box that fetched the lexicon before senses were kept, which is the honest
    answer and the same one a missing entry gives.
    """
    number = (lexeme or "").strip().split(" ")[0].lstrip("H")
    if not number.isdigit():
        return ""
    return _senses().get(number, "")


_BRIEFS: dict[str, str] | None = None
_CHANGES: dict[str, str] | None = None


def _briefs() -> dict[str, str]:
    global _BRIEFS
    if _BRIEFS is None:
        path = root() / TBESH_FILE
        try:
            _BRIEFS = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # A box that has not fetched it yet. Strong's answers, as it did before.
            _BRIEFS = {}
    return _BRIEFS


def _key(estrong: str) -> str:
    """`H6213a` as the tagging writes it, `6213 a`; `H0430` as `430`."""
    found = re.match(r"^H(\d{4})([a-z]?)$", estrong.strip())
    if not found:
        return ""
    number = str(int(found[1]))
    return f"{number} {found[2]}" if found[2] else number


def changes() -> dict[str, str]:
    """targum's hand fixes to the brief glosses, by key, from `tbesh_changes.tsv`.

    Read from the file the licence's change note is, so the note and the fixes cannot
    drift apart: a fix made anywhere else would be a change nobody was told about.
    """
    global _CHANGES
    if _CHANGES is None:
        found: dict[str, str] = {}
        for line in TBESH_CHANGES.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            fields = line.split("\t")
            key = _key(fields[0])
            if key and len(fields) >= 3 and fields[2].strip():
                found[key] = fields[2].strip()
        _CHANGES = found
    return _CHANGES


def brief(lexeme: str) -> str:
    """What a Strong's number means in a word or two, or "" where TBESH has nothing.

    Keyed by the bare number, the way a meaning is filed (`glossed_as` drops the letter):
    `1254 a` create and `1254 b` fatten are one card, so the card says what the number
    means most often across the Tanakh — *to create*. A number written with a letter
    finds the same answer as one written without. targum's fixes go on top.
    """
    number = (lexeme or "").strip().split(" ")[0].lstrip("H")
    if not number.isdigit():
        return ""
    key = str(int(number))
    return changes().get(key) or _briefs().get(key, "")


def bare(text: str) -> str:
    """Letters only, with the space of a two-word headword kept."""
    stripped = "".join(
        ch for ch in unicodedata.normalize("NFC", text or "") if not unicodedata.combining(ch)
    )
    return re.sub(r"\s+", " ", re.sub(r"[^א-ת ]", "", stripped)).strip()


def contested(spelling: str) -> bool:
    """Whether more than one headword in the lexicon is spelled this way bare.

    `אלה` is: אֵלֶּה these, אָלָה a curse, אֵלָה a terebinth, and two more. `בית` is not:
    every entry written that way is בַּיִת. Measured over the whole lexicon, 1,160 of
    6,242 bare spellings are shared, by 2,851 headwords between them — and for each of
    those the bare lemma alone cannot say which word this is, so a meaning filed under
    it alone is filed under the wrong word half the time.
    """
    global _SPELLED
    if _SPELLED is None:
        spelled: dict[str, set[str]] = {}
        for head in _lexicon().values():
            spelled.setdefault(bare(head), set()).add(unicodedata.normalize("NFC", head))
        _SPELLED = spelled
    return len(_SPELLED.get(bare(spelling), ())) > 1


_BY_FORM: dict[str, set[str]] | None = None


def _by_form() -> dict[str, set[str]]:
    """Every way a headword is written, pointed and bare, into the numbers spelled that
    way. Both, because a meaning is filed under the pointed headword where a spelling is
    shared and under the bare lemma everywhere else — `Token.glossed_as`."""
    global _BY_FORM
    if _BY_FORM is None:
        found: dict[str, set[str]] = {}
        for number, head in _lexicon().items():
            pointed = unicodedata.normalize("NFC", head)
            found.setdefault(pointed, set()).add(number)
            found.setdefault(bare(pointed), set()).add(number)
        _BY_FORM = found
    return _BY_FORM


def filed_as(lexeme: str) -> str:
    """The pointed headword a meaning is filed under, with its Strong's number on where
    more than one lexeme is pointed alike; "" where the number names no headword.

    The pointed form tells אֵלֶּה from אָלָה, and nothing written tells `853`, the object
    marker, from `854`, "with": both are אֵת. Filed under אֵת alone, whichever a text met
    first lent its meaning to the other, and אִתְּךָ, "with you", said "[marks the direct
    object]" all through Genesis (known issues 1.4, 2026-10-12). The same is true of 646
    pointed headwords in the lexicon — אֵל "to" and אֵל "God", אַף "also" and אַף "anger" —
    so the rule is the spelling's, not a list of the ones noticed. `NUMBER_MARK` says how
    the number is written, and `models.shown` takes it off again for anything displayed.
    """
    pointed = headword(lexeme)
    if not pointed:
        return ""
    pointed = unicodedata.normalize("NFC", pointed)
    if len(_by_form().get(pointed, ())) < 2:
        return pointed
    number = (lexeme or "").strip().split(" ")[0].lstrip("H")
    return f"{pointed}{NUMBER_MARK.format(number)}"


def sense_for(form: str) -> str:
    """What a written form means, where the lexicon is not of two minds about it.

    `form` is what a meaning is filed under: the pointed headword where two words share
    a spelling, the bare lemma everywhere else.

    One *sense* rather than one number, because the two are not the same question.
    `מֶלֶךְ` is both `4428` and `4430` — the Hebrew king and the Aramaic one — and they
    mean the same thing, so there is nothing ambiguous to a reader about being told "a
    king". Where the candidates disagree this says nothing, which is the honest answer
    and the one `contested` was written for.
    """
    if not form:
        return ""
    if numbered(form):
        return brief(numbered(form)) or sense(numbered(form))
    numbers = _by_form().get(unicodedata.normalize("NFC", form)) or _by_form().get(bare(form))
    if not numbers:
        return ""
    said = {brief(number) or sense(number) for number in numbers}
    said.discard("")
    return said.pop() if len(said) == 1 else ""


def parse_lexicon(xml: str) -> dict[str, str]:
    """Strong's numbers into headwords, from the lexicon file."""
    out: dict[str, str] = {}
    for entry in ET.fromstring(xml).iter():
        if entry.tag.split("}")[-1] != "entry":
            continue
        name = (entry.get("id") or "").lstrip("H")
        word = next((c for c in entry if c.tag.split("}")[-1] == "w"), None)
        written = (word.text or "").strip() if word is not None else ""
        if name.isdigit() and written:
            out[name] = unicodedata.normalize("NFC", written)
    return out


def _prose(element: ET.Element | None) -> str:
    """One field of an entry as running text, with its inline markup dropped."""
    if element is None:
        return ""
    return re.sub(r"\s+", " ", "".join(element.itertext())).strip()


def parse_senses(xml: str) -> dict[str, str]:
    """Strong's numbers into what the word means, from the same file as the headwords.

    Read out of the lexicon already being fetched rather than from a dictionary of its
    own: the entries carry a definition beside the headword and it was being thrown away.
    Public domain, same project, same download.

    `meaning` where there is one and `usage` otherwise. `meaning` is the lexicographer's
    prose — "a king", "to live", "a word, command, discourse, or subject" — and `usage`
    is the list of words the King James translators reached for, which reads as a gloss
    for a content word and as a thicket for a function word. Neither is trimmed here.
    Whether a card should show all of it is a question for the surface that shows it,
    and one this file has no business answering (targum-internal#64).
    """
    out: dict[str, str] = {}
    for entry in ET.fromstring(xml).iter():
        if entry.tag.split("}")[-1] != "entry":
            continue
        name = (entry.get("id") or "").lstrip("H")
        if not name.isdigit():
            continue
        fields = {child.tag.split("}")[-1]: child for child in entry}
        said = _prose(fields.get("meaning")) or _prose(fields.get("usage"))
        if said:
            out[name] = said
    return out


#: A data row of the TBESH file: everything else in it is prose about the data.
_TBESH_ROW = re.compile(r"^H\d{4}[a-z]?$")
#: The columns read, and the only ones: eStrong, dStrong, uStrong, Hebrew,
#: transliteration, morph, Gloss. The eighth, Meaning, is Online Bible's and is cut off
#: at the split, never held, never written.
_TBESH_READ = 7
_GLOSS = 6


class TbeshRow(NamedTuple):
    estrong: str
    dstrong: str
    ustrong: str
    morph: str
    gloss: str


def parse_tbesh(text: str) -> dict[str, list[TbeshRow]]:
    """The TBESH file's data rows by eStrong, with the Gloss column and never Meaning."""
    out: dict[str, list[TbeshRow]] = {}
    for line in text.lstrip("﻿").splitlines():
        # Split no further than the Gloss: the Meaning, if any, stays one unread string
        # in the remainder and is dropped with it.
        fields = line.split("\t", _TBESH_READ)[:_TBESH_READ]
        if len(fields) < _TBESH_READ or not _TBESH_ROW.match(fields[0].strip()):
            continue
        estrong, dstrong, ustrong, _hebrew, _said, morph, gloss = (f.strip() for f in fields)
        out.setdefault(estrong, []).append(TbeshRow(estrong, dstrong, ustrong, morph, gloss))
    return out


def _own(row: TbeshRow) -> bool:
    """Whether a row is an entry of its own: its dStrong is its uStrong with nothing after
    the `=` (`H1697G =`, against `H1697H = a Meaning of`)."""
    left, _, relation = row.dstrong.partition("=")
    return not relation.strip() and left.strip() == row.ustrong.strip()


def is_name(row: TbeshRow) -> bool:
    """Whether a row is a proper or place name rather than the common word.

    TBESH capitalises a name's gloss, and that is the mark this reads. Its morph is no
    help on its own: the many common nouns that also name a place carry the noun's morph
    on the name row (דֶּרֶךְ has "Way" beside "way: road", סוּס "Horse (Gate)" beside
    "horse"), and some common words carry a name's `N:` morph ("stream" beside "Nile",
    "plain" beside "Arabah"). The first letter decides, past any bracket.

    A gentilic is not a name here (the morph's last field ends in `G`, as in `N:N--LG`).
    "Canaanite" is the word a learner meets, and letting it sit out would hand כְּנַעֲנִי
    the gloss of its rare twin, "merchant".
    """
    first = next((ch for ch in row.gloss if ch.isalpha()), "")
    if not first.isupper():
        return False
    return not row.morph.rsplit("-", 1)[-1].endswith("G")


def _head(rows: list[TbeshRow]) -> TbeshRow:
    """The row that is the word itself rather than one of its senses or names.

    In order (targum-internal#510, after ling-he's review):

    1. The entry's own row that its "a Meaning of" rows point to, and that is not a
       name. דֶּרֶךְ's senses all point to H1870K "way: road", not to H1870H "Way".
    2. Else its first own row that is not a name: שָׁבוּעַ is "week", not "Weeks".
    3. Else its first row of any kind that is not a name.
    4. Else, where every row is a name, its first own row: a person is his own name.
    5. Else its first row whose morph is not `N:`, because אֱלֹהִים has no own row and
       no lowercase one, and is "God", not "(LORD)-Elohe".
    6. Else its first row.
    """
    pointed = [
        row.ustrong.split(",")[0].strip()
        for row in rows
        if row.dstrong.partition("=")[2].strip().startswith("a Meaning of")
    ]
    for target in pointed:
        for row in rows:
            if _own(row) and row.ustrong.strip() == target and not is_name(row):
                return row
    for candidates in (
        (row for row in rows if _own(row) and not is_name(row)),
        (row for row in rows if not is_name(row)),
        (row for row in rows if _own(row)),
        (row for row in rows if not row.morph.startswith("N:")),
    ):
        found = next(candidates, None)
        if found is not None:
            return found
    return rows[0]


#: Words that finish a phrasal verb. Where everything after a "/" is one of these, the
#: slash stays: "to cut down/off" is one verb two ways, and "to cut down; off" reads as
#: two meanings, the second of them not a word.
_PARTICLES = frozenset(
    {
        "up",
        "down",
        "off",
        "out",
        "over",
        "away",
        "open",
        "in",
        "on",
        "back",
        "aside",
        "through",
        "together",
        "forth",
        "about",
        "around",
        "apart",
        "under",
        "by",
    }
)


def shorten(gloss: str) -> str:
    """A TBESH Gloss as a card says it. Each rule is a line of `tbesh_changes.tsv`.

    The head before the first `": "` (`to go: walk` is *to go*), `/` as `; `
    (`servant/slave`) except between the particles of one phrasal verb
    (`to cut down/off`), and the backticks and a closing `!` taken off.
    """
    head = gloss.split(": ")[0].replace("`", "").strip()
    parts = [part.strip() for part in head.split("/")]
    if len(parts) > 1 and not all(part.lower() in _PARTICLES for part in parts[1:]):
        head = "; ".join(parts)
    else:
        head = "/".join(parts)
    return head.rstrip("!").strip()


def briefs_from(rows: dict[str, list[TbeshRow]], counts: dict[str, int]) -> dict[str, str]:
    """Every key the tagging can write, into its brief gloss.

    `counts` is how often each lexeme, as the tagging writes it (`6213 a`), occurs across
    the Tanakh. A lettered key (`1254 a`) gets its own variant's gloss. A bare key gets
    the gloss of the variant with the most tokens, because the bare number is what a
    meaning is filed under: עָשָׂה is *to make* (6213 a, 2,624 tokens), never *to press*
    (6213 b, 3). A variant that is a name sits the count out wherever a common-word
    variant exists: צָבָא is *army* (199 tokens), not *Hosts* (287, the name in "LORD of
    Hosts").
    """
    out: dict[str, str] = {}
    # Per number, the best candidate so far: (not a name, tokens, letter rank) and its
    # gloss. A bare row outranks a letter at a tie, and `a` outranks `b`, so a number the
    # tagging never writes falls to TBESH's own bare row or its first letter.
    best: dict[str, tuple[tuple[int, int, int], str]] = {}
    for estrong, found in rows.items():
        key = _key(estrong)
        head = _head(found)
        said = shorten(head.gloss)
        if not key or not said:
            continue
        number, _, letter = key.partition(" ")
        if letter:
            out[key] = said
        score = (
            0 if is_name(head) else 1,
            counts.get(key, 0),
            -ord(letter) if letter else 0,
        )
        if number not in best or score > best[number][0]:
            best[number] = (score, said)
    for number, (_score, said) in best.items():
        out[number] = said
    return out


def _counts() -> dict[str, int]:
    """How often each lexeme occurs across the books on disk, as the tagging writes it."""
    found: dict[str, int] = {}
    for code in sorted(set(BOOKS.values())):
        for _name, held in _book(code).items():
            for word in held:
                lexemes = word[2] if isinstance(word[2], list) else []
                for written in lexemes:
                    lexeme = str(written).strip()
                    if _NUMBERED.match(lexeme):
                        found[lexeme] = found.get(lexeme, 0) + 1
    return found


def _path(code: str) -> Path:
    return root() / f"{code}.json"


def parse(xml: str) -> dict[str, list[list[object]]]:
    """One book of OSIS morphology, as verses of words.

    Public because the fetch converts with it and the tests read a fixture through it,
    and two ways of turning this XML into words is two answers waiting to disagree.
    """
    verses: dict[str, list[list[object]]] = {}
    for verse in ET.fromstring(xml).findall(".//o:verse", _OSIS_NS):
        osis = verse.get("osisID") or ""
        if not osis:
            continue
        held = [_word(*found) for found in _read(verse)]
        if held:
            verses[osis] = [row for row in held if row is not None]
    return {name: rows for name, rows in verses.items() if rows}


def _word(element: ET.Element, ketiv: str) -> list[object] | None:
    # Normalised on the way in, because the join downstream compares these strings
    # against the shelf's own text, and two sources may order a vowel and a cantillation
    # mark differently while rendering identically. Canonical ordering is what makes
    # "the same word" something a comparison can see.
    text = unicodedata.normalize("NFC", element.text or "")
    if not text.strip():
        return None
    pieces = text.split("/")
    lexemes = (element.get("lemma") or "").split("/")
    # The language letter leads every code — H for Hebrew, A for the Aramaic of Daniel
    # and Ezra — and it is a fact about the verse rather than about the word.
    morph = re.sub(r"^[HA]", "", element.get("morph") or "").split("/")
    return [text.replace("/", ""), pieces, lexemes, morph, ketiv]


def _read(verse: ET.Element) -> Iterator[tuple[ET.Element, str]]:
    """The words of one verse in reading order, with the qere preferred.

    Where the Masoretes wrote one word and read another, this file writes the *written*
    form as an ordinary word and hides the *read* form inside a note beside it:

        <w type="x-ketiv" lemma="3318">הוצא</w>
        <note type="variant"><rdg type="x-qere"><w>הַיְצֵ֣א</w></rdg></note>

    Taking the direct children alone therefore yields the ketiv — unpointed, and not what
    is on the page. The shelf carries the qere, so aligning against the ketiv puts the
    whole verse out by a word. That single mistake accounted for 139 of the 143
    misaligned verses across Genesis, Isaiah, Psalms and Ruth.

    So the qere wins and the ketiv is carried beside it, which is the same order of
    preference a printed Tanakh makes.
    """
    pending: str = ""
    for child in verse:
        tag = child.tag.split("}")[-1]
        if tag == "w":
            if child.get("type") == "x-ketiv":
                # Held back: its qere is in the note that follows, and that is the word.
                pending = unicodedata.normalize("NFC", (child.text or "").replace("/", ""))
                continue
            yield child, ""
        elif tag == "note":
            read = child.find(".//o:rdg[@type='x-qere']/o:w", _OSIS_NS)
            if read is not None:
                yield read, pending
            pending = ""


def fetch(books: list[str] | None = None, notify: Callable[[str], None] | None = None) -> int:
    """Download the morphology and convert it once. Returns how many books arrived.

    Loud on failure and idempotent on success: a book already converted is left alone, so
    this is safe to re-run and safe to interrupt.
    """
    import httpx

    say = notify or (lambda _message: None)
    wanted = books or sorted(set(BOOKS.values()))
    ensure(root())
    got = 0
    for code in wanted:
        if _path(code).exists():
            got += 1
            continue
        say(f"Fetching {code}…")
        try:
            answer = httpx.get(SOURCE.format(book=code), timeout=120.0, follow_redirects=True)
            answer.raise_for_status()
            verses = parse(answer.text)
        except Exception as bad:  # noqa: BLE001 - network, XML and HTTP all land here
            raise TargumError(f"Could not fetch the morphology for {code}.", str(bad)) from bad
        write_atomic(_path(code), json.dumps(verses, ensure_ascii=False))
        got += 1

    if not (root() / LEXICON_FILE).exists():
        say("Fetching the lexicon…")
        try:
            answer = httpx.get(LEXICON, timeout=180.0, follow_redirects=True)
            answer.raise_for_status()
            headwords = parse_lexicon(answer.text)
            senses = parse_senses(answer.text)
        except Exception as bad:  # noqa: BLE001 - network, XML and HTTP all land here
            raise TargumError("Could not fetch the Hebrew lexicon.", str(bad)) from bad
        write_atomic(root() / LEXICON_FILE, json.dumps(headwords, ensure_ascii=False))
        # From the same download, parsed a second time rather than fetched again.
        write_atomic(root() / SENSES_FILE, json.dumps(senses, ensure_ascii=False))

    # Gated on its own file, not on the lexicon's: a box that fetched the lexicon before
    # this existed would otherwise never get it (targum-internal#510).
    if not (root() / TBESH_FILE).exists():
        say(f"Fetching the brief glosses from {TBESH_CREDIT}…")
        try:
            answer = httpx.get(TBESH, timeout=180.0, follow_redirects=True)
            answer.raise_for_status()
            rows = parse_tbesh(answer.text)
            if not rows:
                raise ValueError("no rows in the file")
        except Exception as bad:  # noqa: BLE001 - network, HTTP and format all land here
            raise TargumError("Could not fetch the brief Hebrew glosses.", str(bad)) from bad
        # Counted from the books just fetched, so the bare number gets the variant the
        # Tanakh uses most. Only the Gloss column is in `rows`; nothing else is written.
        write_atomic(
            root() / TBESH_FILE,
            json.dumps(briefs_from(rows, _counts()), ensure_ascii=False, sort_keys=True),
        )
        global _BRIEFS
        _BRIEFS = None
    return got


_loaded: dict[str, dict[str, list[list[object]]]] = {}


def _book(code: str) -> dict[str, list[list[object]]]:
    if code not in _loaded:
        path = _path(code)
        if not path.is_file():
            _loaded[code] = {}
        else:
            try:
                _loaded[code] = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                # A half-written book is a book targum does not have. The annotator falls
                # back rather than failing a build over a file it can simply re-fetch.
                _loaded[code] = {}
    return _loaded[code]


def forget() -> None:
    """Drop what is held in memory. For a test that swaps the directory underneath."""
    global _HEADWORDS, _SPELLED, _MEANINGS, _BY_FORM, _BRIEFS, _CHANGES
    _loaded.clear()
    _BRIEFS = None
    _CHANGES = None
    _HEADWORDS = None
    _SPELLED = None
    _MEANINGS = None
    _BY_FORM = None


_REF = re.compile(r"^(?P<book>.+?)\s+(?P<chapter>\d+)[:.](?P<verse>\d+)\s*$")


def osis(ref: str) -> str | None:
    """`Genesis 1:1` as `Gen.1.1`, or None where this is not a book we have tagged.

    None is the ordinary answer for most of the shelf — the Mishnah, a newspaper, a
    novel — and is not a failure.
    """
    found = _REF.match((ref or "").strip())
    if not found:
        return None
    code = BOOKS.get(found["book"])
    if code is None:
        return None
    return f"{code}.{found['chapter']}.{found['verse']}"


def words(ref: str) -> tuple[Word, ...] | None:
    """Every word of one verse as it was tagged, or None where there is no tagging.

    None rather than an empty tuple, so a caller can tell "this verse is not in the
    Hebrew Bible" from "this verse is in it and has no words", which never happens but
    would be a silent wrong answer if it did.
    """
    name = osis(ref)
    if name is None:
        return None
    held = _book(name.split(".")[0]).get(name)
    if held is None:
        return None
    return tuple(
        Word(str(text), tuple(pieces), tuple(lexemes), tuple(morph), str(ketiv))  # type: ignore[arg-type]
        for text, pieces, lexemes, morph, ketiv in held
    )


def verses(code: str) -> Iterator[tuple[str, tuple[Word, ...]]]:
    """Every tagged verse of one book, for a report or a measurement."""
    for name in _book(code):
        got = _book(code)[name]
        yield (
            name,
            tuple(
                Word(str(text), tuple(pieces), tuple(lexemes), tuple(morph), str(ketiv))  # type: ignore[arg-type]
                for text, pieces, lexemes, morph, ketiv in got
            ),
        )
