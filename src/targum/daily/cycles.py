"""The daily learning cycles, and how each one names a place on the shelf.

Hebcal publishes thirteen of these and hands them all over in one answer, told apart by
a `category`. What differs between them is not the fetching, which is one call, but two
things only: which shelf a reference points at, and how the reference is written. So the
cycles are data and the walking is not — a new one is a row here, not a module.

**A cycle is only on this shelf if its text is.** Daf Yomi and the Yerushalmi are the
ones people ask for and neither is here: the Talmud's only free Hebrew on Sefaria is
CC-BY-SA, which this shelf refuses, and it is Aramaic besides. Daily Rambam walks all
eighty-eight sections of the Mishneh Torah and thirteen of them are on the shelf, so a
page for it would stop dead in its third month. They are named in `ABSENT` rather than
left out, because "we do not carry that" is an answer and silence is not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


#: Hebcal's flag for each cycle, and the category the items come back under. Both are
#: theirs, not ours, so they are written down exactly rather than derived.
@dataclass(frozen=True, slots=True)
class Cycle:
    """One daily learning cycle."""

    #: The route: `/mishna-yomi`.
    slug: str
    #: Hebcal's query flag, and the `category` its items carry back.
    flag: str
    category: str
    #: What it is called, in both.
    name: str
    hebrew: str
    #: One sentence, in the voice §6 asks for: what it is, not why it is good.
    blurb: str
    #: How much of it there is, said plainly, for the page's dateline.
    rhythm: str
    #: The hero's picture, in `assets/manuscripts/`, and who to credit for it. A
    #: manuscript of the text this cycle reads — see that folder's README for why it is a
    #: page of the book rather than a portrait of whoever stands behind it.
    picture: str
    credit: str


#: The four this shelf can serve, in the order the page offers them.
CYCLES: tuple[Cycle, ...] = (
    Cycle(
        slug="mishna-yomi",
        flag="myomi",
        category="mishnayomi",
        name="Mishna Yomi",
        hebrew="משנה יומית",
        blurb="Two mishnayot a day, through all sixty-three tractates in about six years.",
        rhythm="two mishnayot a day",
        picture="mishnah.jpg",
        credit=(
            "a page of MS Kaufmann A50, the oldest complete Mishnah, from the "
            "Hungarian Academy of Sciences"
        ),
    ),
    Cycle(
        slug="nach-yomi",
        flag="nyomi",
        category="nachyomi",
        name="Nach Yomi",
        hebrew="נ״ך יומי",
        blurb=("A chapter a day of the Prophets and the Writings, the whole of them in two years."),
        rhythm="a chapter a day",
        picture="aleppo.jpg",
        credit="the Aleppo Codex, written by Shlomo ben Buya'a about the year 930",
    ),
    Cycle(
        slug="tanakh-yomi",
        flag="dty",
        category="tanakhYomi",
        name="Tanakh Yomi",
        hebrew="תנ״ך יומי",
        blurb=(
            "The Prophets and the Writings on weekdays, by the sedarim the Masoretes "
            "divided them into."
        ),
        rhythm="one seder a weekday",
        picture="leningrad.jpg",
        credit="the Leningrad Codex, written by Shmuel ben Ya'akov in 1008",
    ),
    Cycle(
        slug="tehillim",
        flag="dps",
        category="dailyPsalms",
        name="Daily Tehillim",
        hebrew="תהלים יומי",
        blurb=(
            "The whole book of Psalms every month, a few chapters a day, by the day of the month."
        ),
        rhythm="a few psalms a day",
        picture="psalms.jpg",
        credit=(
            "the Great Psalms Scroll from Qumran, photographed by the Israel Antiquities Authority"
        ),
    ),
)

#: What Hebcal publishes and this shelf cannot read, with the reason. Shown on the page
#: rather than hidden, because somebody looking for Daf Yomi is owed an answer.
ABSENT: dict[str, str] = {
    "Daf Yomi": "The Talmud is not on this shelf: its only free Hebrew is ShareAlike, "
    "which a build cannot carry onto what it makes.",
    "Yerushalmi Yomi": "The Jerusalem Talmud, for the same reason.",
    "Daily Rambam": "Thirteen of the Mishneh Torah's eighty-eight sections are here, "
    "and a daily cycle walks all of them.",
}

BY_SLUG = {cycle.slug: cycle for cycle in CYCLES}
BY_CATEGORY = {cycle.category: cycle for cycle in CYCLES}


#: A reference as Hebcal writes it, in the three shapes the four cycles use:
#:
#:     Kelim 28:2-3            two mishnayot in one chapter
#:     Kelim 30:4-Oholot 1:1   two mishnayot either side of a tractate
#:     Isaiah 55               a whole chapter
#:     Psalms 90-96            a run of whole chapters
#:
#: Tanakh Yomi is the odd one: its title names a seder ("Ezra and Nehemiah Seder 10")
#: and the verses are in `memo`, so it is read from there — see `Reading.reference`.
_ONE = re.compile(r"^(?P<book>.+?)\s+(?P<chapter>\d+)(?::(?P<verse>\d+))?$")
_RANGE = re.compile(
    r"^(?P<book>.+?)\s+(?P<chapter>\d+)(?::(?P<verse>\d+))?"
    r"\s*-\s*"
    r"(?:(?P<book2>[A-Za-z][^\d]*?)\s+)?(?P<chapter2>\d+)(?::(?P<verse2>\d+))?$"
)


@dataclass(frozen=True, slots=True)
class Span:
    """A reference resolved into where it begins and ends.

    Verses are None where the reference names whole chapters, which is what Nach Yomi and
    Daily Tehillim do. A day that crosses from one book into the next has two book names,
    and it is the one shape that cannot be served out of a single built text.
    """

    book: str
    chapter: int
    verse: int | None
    book2: str
    chapter2: int
    verse2: int | None

    @property
    def crosses(self) -> bool:
        return self.book2 != self.book


def parse_reference(text: str) -> Span | None:
    """`Kelim 28:2-3` and the rest of them, or None where the shape is not one of these.

    None rather than a guess: a reference this does not recognise is a cycle whose shape
    changed or a book whose name has a numeral in it, and inventing a range from either
    would put the wrong text on the page under today's date.
    """
    said = " ".join(text.split())
    found = _RANGE.match(said)
    if found:
        book = found.group("book").strip()
        chapter = int(found.group("chapter"))
        verse = int(found.group("verse")) if found.group("verse") else None
        book2 = (found.group("book2") or book).strip()
        chapter2 = int(found.group("chapter2"))
        verse2 = int(found.group("verse2")) if found.group("verse2") else None
        # `Kelim 28:2-3` ends at verse three of chapter twenty-eight, not at chapter
        # three: where the left side names a verse and the right side is a bare number
        # in the same book, that number is the verse. `Psalms 90-96`, whose left side
        # names no verse, is the other reading of the same shape and is chapters.
        if verse is not None and verse2 is None and book2 == book:
            chapter2, verse2 = chapter, chapter2
        return Span(book, chapter, verse, book2, chapter2, verse2)
    found = _ONE.match(said)
    if not found:
        return None
    book = found.group("book").strip()
    chapter = int(found.group("chapter"))
    verse = int(found.group("verse")) if found.group("verse") else None
    return Span(book, chapter, verse, book, chapter, verse)


def reference_of(item: dict[str, str]) -> str:
    """What a day actually points at.

    `memo` where there is one, and the title otherwise. Tanakh Yomi is why: its title is
    the seder's name — `Ezra and Nehemiah Seder 10` — and the verses it stands for are in
    the memo. Reading the title there would look up a book called "Ezra and Nehemiah
    Seder" and find nothing.
    """
    return (item.get("memo") or item.get("title") or "").strip()
