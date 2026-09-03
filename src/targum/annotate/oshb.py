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
from ..paths import ensure, model_dir, write_atomic

SOURCE = "https://raw.githubusercontent.com/openscriptures/morphhb/master/wlc/{book}.xml"
#: Strong's numbers into Hebrew headwords. The morphology says *which* lexeme a word
#: belongs to, as a number; this says what that lexeme is called. Same project, same
#: licence, and the dictionary underneath is public domain.
LEXICON = "https://raw.githubusercontent.com/openscriptures/HebrewLexicon/master/HebrewStrong.xml"
LEXICON_FILE = "strongs.json"

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
        """Which piece is the word itself rather than something stuck to the front.

        The last piece, always: Hebrew builds a word by putting function letters before
        it, so whatever is left at the end is what the word is. Said as a property rather
        than assumed at each call site, because it is a claim about the language and
        deserves somewhere to be written down and tested.
        """
        return len(self.pieces) - 1

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
        except Exception as bad:  # noqa: BLE001 - network, XML and HTTP all land here
            raise TargumError("Could not fetch the Hebrew lexicon.", str(bad)) from bad
        write_atomic(root() / LEXICON_FILE, json.dumps(headwords, ensure_ascii=False))
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
    global _HEADWORDS, _SPELLED
    _loaded.clear()
    _HEADWORDS = None
    _SPELLED = None


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
