"""A place in the Torah, read off whatever a person typed or pasted.

People come at the five books in more ways than one: "Genesis 12:1", "Gen. 12.1",
"בראשית י״ב:א׳", "בראשית פרק יב פסוק א", a Sefaria link copied out of the address bar,
or just the name of the week's portion — "Lech Lecha", "לך לך". Every one of them is a
way into the same reading, and this module turns each into one `TorahRef`: a book, a
chapter and a verse to open at, with the end of the range where the range stays in one
chapter.

**The whole input or nothing.** `parse` answers only when everything typed is one
reference. "בראשית יב ויאמר" names a verse and then keeps going, and "Genesis is great"
names a book and then says something about it; both are sentences, and opening the
portion on a sentence would answer a question nobody asked. So they are None, and the
caller treats the text as the text it is.

**A name alone is a way in.** A bare book opens at its first verse, and a portion's name
opens where the portion begins. A combined week ("Vayakhel-Pekudei") opens where the
first of its two begins, because that is where the reading starts.

**Where the portions come from.** The 54 starts are the table shipped beside the parasha
package (`parasha/starts.json`, read through `parasha.build.fixed_starts`), so the names
here are exactly the names the shelf uses. A handful of common other spellings sit on top
of them in `_ALIASES`. The parasha package is imported only when a portion name is first
looked up, and the table is read once.

Verse counts per chapter are not checked here: the chapter count is, because it costs one
small table, and whoever opens the reading finds out whether the verse is there.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

#: How many chapters each book has, under the English name the parasha corpus uses for
#: it (`parasha.cut.BOOKS`). A chapter past the end is not a reference.
CHAPTERS = {
    "Genesis": 50,
    "Exodus": 40,
    "Leviticus": 27,
    "Numbers": 36,
    "Deuteronomy": 34,
}

#: Every name a book answers to, already in `_key` form: lowercase, no apostrophes, no
#: nikkud. The English names, the usual abbreviations, the transliterations of the Hebrew
#: titles in the spellings people actually use, and the Hebrew titles themselves.
_BOOK_NAMES: dict[str, tuple[str, ...]] = {
    "Genesis": (
        "genesis",
        "gen",
        "gn",
        "ge",
        "bereshit",
        "bereishit",
        "breishit",
        "bereshis",
        "bereishis",
        "breshit",
        "בראשית",
    ),
    "Exodus": ("exodus", "exod", "ex", "shemot", "shemos", "shmot", "שמות"),
    "Leviticus": ("leviticus", "lev", "lv", "vayikra", "vayyikra", "ויקרא"),
    "Numbers": ("numbers", "num", "nm", "nu", "bamidbar", "bemidbar", "במדבר"),
    "Deuteronomy": ("deuteronomy", "deut", "dt", "deu", "devarim", "dvarim", "דברים"),
}

_BOOKS = {name: book for book, names in _BOOK_NAMES.items() for name in names}

#: Other spellings of the portions' names, by the slug `starts.json` files each under,
#: in `_key` form. The table's own name, Hebrew and slug are always recognised; these are
#: the spellings a reader brings from a different siddur, a different country or Sefaria.
_ALIASES: dict[str, tuple[str, ...]] = {
    "bereshit": ("bereishit", "breishit", "bereshis", "bereishis", "breshit"),
    "noach": ("noah",),
    "lech-lecha": ("lekhlekha", "lechleha"),
    "vayera": ("vayeira",),
    "chayei-sara": ("chayeisarah", "chayesarah", "chayesara"),
    "toldot": ("toldos", "toledot"),
    "vayetzei": ("vayetze", "vayeitzei", "vayeitze"),
    "vayeshev": ("vayeishev",),
    "miketz": ("mikeitz", "mikketz"),
    "vayechi": ("vayehi",),
    "shemot": ("shemos", "shmot"),
    "vaera": ("vaeira",),
    "beshalach": ("beshallach",),
    "yitro": ("yisro",),
    "terumah": ("teruma",),
    "tetzaveh": ("tetzave", "tetsaveh", "תצווה"),
    "ki-tisa": ("kitissa",),
    "pekudei": ("pekude",),
    "vayikra": ("vayyikra",),
    "tzav": ("tsav",),
    "shmini": ("shemini",),
    "metzora": ("metsora", "מצורע"),
    "achrei-mot": ("achareimot", "acharemot"),
    "kedoshim": ("קדושים",),
    "bechukotai": ("bechukosai", "bechukotay", "בחוקותי"),
    "bamidbar": ("bemidbar",),
    "nasso": ("naso",),
    "behaalotcha": ("behaalotecha", "behaalotekha", "behaaloscha", "בהעלותך"),
    "shlach": ("shelach", "shelachlecha", "shlachlecha", "שלח"),
    "korach": ("korah", "קורח"),
    "chukat": ("chukas", "hukkat", "חוקת"),
    "pinchas": ("pinhas", "pinchos", "פנחס"),
    "matot": ("mattot", "matos"),
    "masei": ("massei", "maasei"),
    "devarim": ("dvarim",),
    "vaetchanan": ("vaeschanan",),
    "eikev": ("ekev",),
    "shoftim": ("shofetim",),
    "ki-teitzei": ("kitetzei", "kiteitze", "kitetze", "kiseitzei"),
    "ki-tavo": ("kisavo",),
    "nitzavim": ("nitsavim",),
    "vayeilech": ("vayelech",),
    "vzot-haberachah": (
        "vezothaberachah",
        "vezothaberacha",
        "vzothaberacha",
        "vezothaberakhah",
        "vezothaberakha",
    ),
}

#: Words a portion's name is often introduced with. Dropped before the name is looked up,
#: so "Parashat Noach" and "פרשת נח" are Noach.
_PORTION_WORDS = ("parashat", "parshat", "parashah", "parasha", "parsha", "פרשת")

#: Cantillation and vowel points, U+0591–U+05C7, less the three that are punctuation
#: rather than marks on a letter: the maqaf (U+05BE), which joins words and becomes a
#: hyphen, and the paseq and sof pasuq (U+05C0, U+05C3), which become spaces.
_POINTS = re.compile(r"[֑-ֽֿׁׂׄ-ׇ]")

#: What may sit around a reference without being part of it: whitespace, a full stop at
#: the end of a sentence, brackets. Not ' or ", which in Hebrew are a numeral's marks.
_AROUND = " \t\r\n.,;:!?()[]{}<>"

#: One number as written: arabic digits, or Hebrew letters with the geresh and
#: gershayim marks (and their ASCII stand-ins) wherever they fall. `_number` decides
#: whether the letters are actually a numeral.
_NUM = r"(?:\d+|[א-ת'\"׳״]+)"

#: Between chapter and verse: a colon, a full stop, a comma or plain space. Hebrew may
#: name them — "פרק יב פסוק א" — and the words are tolerated where they belong.
_PLACE = re.compile(
    rf"""^
    (?:פרק\s*)?(?P<chapter>{_NUM})
    (?:(?:\s*[:.,]\s*|\s+)(?:פסוק\s*)?(?P<verse>{_NUM}))?
    (?:\s*[-–—]\s*(?P<end>{_NUM})(?:\s*[:.,]\s*(?P<end_verse>{_NUM}))?)?
    $""",
    re.VERBOSE,
)

#: A book's name at the head of the input: letters, with an apostrophe inside for
#: "B'reshit" and "D'varim". What follows is the place, after an optional full stop for
#: the abbreviations ("Gen. 12:1") and Sefaria's dotted form ("Genesis.12.1").
_HEAD = re.compile(r"^(?P<book>[^\W\d_]+(?:['’׳][^\W\d_]+)?)\.?(?:\s*(?P<rest>.*))?$", re.S)

#: What a portion's name may be made of: letters, and the spaces, hyphens, maqaf and
#: apostrophes its words are joined with.
_NAME = re.compile(r"(?:[^\W\d_]|[\s'’׳\-])+")

#: The hosts a pasted link may come from. Sefaria's Israeli address serves the same
#: refs as the international one.
_SEFARIA = {"sefaria.org", "www.sefaria.org", "sefaria.org.il", "www.sefaria.org.il"}

#: The value of each letter as a numeral. Final forms have no place in a chapter or verse
#: number and are left out, so a word ending in one is never read as a number.
_LETTERS = {
    letter: value
    for letters, step in (("אבגדהוזחט", 1), ("יכלמנסעפצ", 10), ("קרשת", 100))
    for value, letter in zip(range(step, step * 10, step), letters, strict=False)
}


@dataclass(frozen=True)
class TorahRef:
    """Where in the five books to open."""

    #: The English name the parasha corpus files the book under: "Genesis".
    book: str
    chapter: int
    #: 1 when the input named only a chapter, a book or a portion.
    verse: int
    #: The last verse of a range that stays inside `chapter`. A range that runs into
    #: the next chapter keeps None: it opens at its start like any other.
    to_verse: int | None = None


def parse(text: str) -> TorahRef | None:
    """The one Torah reference `text` is, or None where it is anything else.

    Accepts a book and place ("Genesis 12:1", "Gen. 12.1-5", "בראשית י״ב:א׳"), a bare
    book, a Sefaria link to one of the five, or a portion's name. See the module's
    docstring for why a reference with anything after it is None.
    """
    said = _clean(text)
    if not said:
        return None
    if "sefaria.org" in said.lower():
        return _from_link(said)
    return _from_reference(said) or _from_portion(said)


def hebrew_number(token: str) -> int | None:
    """A Hebrew numeral's value — "יב" is 12, "ט״ו" is 15 — or None.

    The marks (geresh, gershayim, or ASCII ' and ") are ignored wherever they fall. The
    letters must be written the standard way: largest first, at most one tens letter and
    one units letter, and fifteen and sixteen as טו and טז, never יה and יו. Anything else
    is a word that happens to be made of letters, which is the point of being strict:
    "ויאמר" is not a verse number.
    """
    letters = re.sub(r"['\"׳״]", "", token)
    if not letters or any(letter not in _LETTERS for letter in letters):
        return None
    if letters.endswith(("יה", "יו")):
        return None
    # Fifteen and sixteen are the one place two units letters stand together.
    teen = 0
    if letters.endswith(("טו", "טז")):
        teen, letters = _LETTERS[letters[-2]] + _LETTERS[letters[-1]], letters[:-2]
        if any(_LETTERS[letter] < 100 for letter in letters):
            return None
    values = [_LETTERS[letter] for letter in letters]
    if values != sorted(values, reverse=True):
        return None
    if sum(1 for value in values if value < 10) > 1:
        return None
    if sum(1 for value in values if 10 <= value < 100) > 1:
        return None
    return sum(values) + teen


def _clean(text: str) -> str:
    """The input with its points gone, its words joined by single spaces and nothing
    that only surrounds it."""
    said = _POINTS.sub("", text).replace("־", "-")
    said = re.sub(r"[׀׃]", " ", said)
    return " ".join(said.split()).strip(_AROUND)


def _key(name: str) -> str:
    """A name reduced to what spelling choices do not change: lowercase, and nothing but
    letters — no spaces, hyphens, maqaf or apostrophes."""
    return "".join(char for char in _POINTS.sub("", name).lower() if char.isalpha())


def _number(token: str | None) -> int | None:
    if token is None:
        return None
    if token.isdigit():
        return int(token)
    return hebrew_number(token)


def _from_reference(said: str) -> TorahRef | None:
    head = _HEAD.match(said)
    if not head:
        return None
    book = _BOOKS.get(_key(head["book"]))
    if book is None:
        return None
    rest = (head["rest"] or "").strip()
    if not rest:
        return TorahRef(book, 1, 1)
    return _place(book, rest)


def _place(book: str, rest: str) -> TorahRef | None:
    found = _PLACE.match(rest)
    if not found:
        return None
    chapter = _number(found["chapter"])
    verse = _number(found["verse"]) if found["verse"] else 1
    if chapter is None or verse is None or not 1 <= chapter <= CHAPTERS[book] or verse < 1:
        return None
    if not found["end"]:
        return TorahRef(book, chapter, verse)
    end = _number(found["end"])
    end_verse = _number(found["end_verse"]) if found["end_verse"] else None
    if end is None or (found["end_verse"] and end_verse is None):
        return None
    if end_verse is not None:
        # "12:1-13:4": the end names its own chapter. Inside one chapter it is a range
        # of verses; across chapters the reading just opens at its start.
        if (end, end_verse) < (chapter, verse) or end > CHAPTERS[book]:
            return None
        return TorahRef(book, chapter, verse, end_verse if end == chapter else None)
    if found["verse"]:
        # "12:1-5": a bare number after a verse is the verse the range ends on.
        if end < verse:
            return None
        return TorahRef(book, chapter, verse, end)
    # "12-13", with no verse on the left, is a range of chapters.
    if end < chapter or end > CHAPTERS[book]:
        return None
    return TorahRef(book, chapter, 1)


def _from_link(said: str) -> TorahRef | None:
    """A Sefaria address: `https://www.sefaria.org/Genesis.12.1-5?lang=bi`. Only the path
    says where; the query is how the page was being shown and is ignored."""
    address = said if "://" in said else f"https://{said}"
    try:
        parts = urlsplit(address)
    except ValueError:
        return None
    if (parts.hostname or "").lower() not in _SEFARIA:
        return None
    path = unquote(parts.path).strip("/")
    if not path or "/" in path:
        return None
    # Sefaria writes a space in a title as an underscore. None of the five has one, but
    # a link to "Song_of_Songs" should fail as an unknown book rather than as noise.
    return _from_reference(path.replace("_", " "))


def _from_portion(said: str) -> TorahRef | None:
    words = said.split(" ", 1)
    if len(words) == 2 and words[0].lower() in _PORTION_WORDS:
        said = words[1]
    # Letters and the marks that join a name's words, and nothing else: "Noach 6:9" is a
    # portion with a place after it, which is not something this knows how to open.
    if not _NAME.fullmatch(said):
        return None
    key = _key(said)
    portions = _portions()
    known = portions.get(key)
    if known is not None:
        return known[1]
    # A combined week, "Vayakhel-Pekudei": two names read one after the other. It
    # opens where the first begins.
    for cut in range(1, len(key)):
        first, second = portions.get(key[:cut]), portions.get(key[cut:])
        if first and second and second[0] == first[0] + 1:
            return first[1]
    return None


@functools.cache
def _portions() -> dict[str, tuple[int, TorahRef]]:
    """Every name a portion goes by, in `_key` form, to its place in the year's order
    and where it begins.

    Imported here rather than at the top: `parasha.build` brings the render and
    annotation modules with it, and a caller that only parses chapter and verse should
    not pay for them.
    """
    from .parasha.build import fixed_starts

    names: dict[str, tuple[int, TorahRef]] = {}
    order = 0
    for book in CHAPTERS:
        for start in fixed_starts(book):
            at = (order, TorahRef(book, start.chapter, start.verse))
            order += 1
            for name in (start.name, start.hebrew, start.slug, *_ALIASES.get(start.slug, ())):
                names.setdefault(_key(name), at)
    return names
