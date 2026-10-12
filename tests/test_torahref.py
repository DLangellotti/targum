"""Every way into the Torah reads as one place: book, chapter, verse.

A reference is the whole input or nothing, so the None cases matter as much as the hits:
a sentence that starts like a reference must stay a sentence.
"""

from __future__ import annotations

import pytest

from targum import torahref
from targum.parasha.cut import BOOKS
from targum.torahref import TorahRef, hebrew_number, parse


def gen(chapter: int, verse: int = 1, to_verse: int | None = None) -> TorahRef:
    return TorahRef("Genesis", chapter, verse, to_verse)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Each book, in English, abbreviated, transliterated and in Hebrew.
        ("Genesis 12:1", gen(12, 1)),
        ("Gen. 12:1", gen(12, 1)),
        ("gn 12:1", gen(12, 1)),
        ("Bereshit 12:1", gen(12, 1)),
        ("B'reshit 12:1", gen(12, 1)),
        ("בראשית 12:1", gen(12, 1)),
        ("Exodus 20:2", TorahRef("Exodus", 20, 2)),
        ("Ex 20:2", TorahRef("Exodus", 20, 2)),
        ("Shemos 20:2", TorahRef("Exodus", 20, 2)),
        ("Sh'mot 20:2", TorahRef("Exodus", 20, 2)),
        ("שמות כ ב", TorahRef("Exodus", 20, 2)),
        ("Leviticus 19:18", TorahRef("Leviticus", 19, 18)),
        ("Lev 19:18", TorahRef("Leviticus", 19, 18)),
        ("Vayyikra 19:18", TorahRef("Leviticus", 19, 18)),
        ("ויקרא יט יח", TorahRef("Leviticus", 19, 18)),
        ("Numbers 36:13", TorahRef("Numbers", 36, 13)),
        ("Nm 6:24", TorahRef("Numbers", 6, 24)),
        ("BaMidbar 6:24", TorahRef("Numbers", 6, 24)),
        ("במדבר לו יג", TorahRef("Numbers", 36, 13)),
        ("Deuteronomy 6:4", TorahRef("Deuteronomy", 6, 4)),
        ("Deut. 6:4", TorahRef("Deuteronomy", 6, 4)),
        ("D'varim 6:4", TorahRef("Deuteronomy", 6, 4)),
        ("דברים ו ד", TorahRef("Deuteronomy", 6, 4)),
        ("DEUTERONOMY 34:12", TorahRef("Deuteronomy", 34, 12)),
        # A bare book or chapter opens at its first verse.
        ("Genesis", gen(1)),
        ("Gen.", gen(1)),
        ("בְּרֵאשִׁית", gen(1)),
        ("Genesis 12", gen(12)),
        ("בראשית יב", gen(12)),
        # Hebrew numerals, with and without their marks.
        ("בראשית י״ב:א׳", gen(12, 1)),
        ("בראשית י\"ב:א'", gen(12, 1)),
        ("בראשית יב׳ ג׳", gen(12, 3)),
        ("בראשית טו ו", gen(15, 6)),
        ("בראשית טז א", gen(16, 1)),
        ("בראשית ט״ו:ו׳", gen(15, 6)),
        ("בראשית פרק יב פסוק א", gen(12, 1)),
        ("בְּרֵאשִׁית פרק נ פסוק כו", gen(50, 26)),
        # Separators.
        ("Genesis 12.1", gen(12, 1)),
        ("Genesis 12,1", gen(12, 1)),
        ("Genesis 12 1", gen(12, 1)),
        ("Genesis.12.1", gen(12, 1)),
        ("  Genesis 12:1.  ", gen(12, 1)),
        # Ranges: a same-chapter range keeps its end, a cross-chapter one does not.
        ("Genesis 12:1-5", gen(12, 1, 5)),
        ("Genesis 12:1–5", gen(12, 1, 5)),
        ("Genesis 12:1 - 5", gen(12, 1, 5)),
        ("Genesis 12:1-13:4", gen(12, 1)),
        ("Genesis 12:1-12:9", gen(12, 1, 9)),
        ("Genesis 12-13", gen(12)),
        ("בראשית יב:א-ה", gen(12, 1, 5)),
        # Sefaria links.
        ("https://www.sefaria.org/Genesis.12.1", gen(12, 1)),
        ("https://www.sefaria.org/Genesis.12.1-5", gen(12, 1, 5)),
        ("https://www.sefaria.org/Genesis.12", gen(12)),
        ("https://www.sefaria.org/Genesis.12.1-13.4?lang=bi&with=all", gen(12, 1)),
        ("https://www.sefaria.org.il/Numbers.6.24?lang=he", TorahRef("Numbers", 6, 24)),
        ("sefaria.org/Exodus.20.2", TorahRef("Exodus", 20, 2)),
        # Portions, in English and Hebrew, however they are spelled.
        ("Lech Lecha", gen(12)),
        ("lech-lecha", gen(12)),
        ("Lekh Lekha", gen(12)),
        ("LECHLECHA", gen(12)),
        ("לך לך", gen(12)),
        ("לֶךְ־לְךָ", gen(12)),
        ("Parashat Noach", gen(6, 9)),
        ("פרשת נח", gen(6, 9)),
        ("Chayei Sarah", gen(23)),
        ("Toldos", gen(25, 19)),
        ("Beha'alotcha", TorahRef("Numbers", 8, 1)),
        ("Ki Tisa", TorahRef("Exodus", 30, 11)),
        ("Ha'azinu", TorahRef("Deuteronomy", 32, 1)),
        ("V'Zot HaBerachah", TorahRef("Deuteronomy", 33, 1)),
        ("וזאת הברכה", TorahRef("Deuteronomy", 33, 1)),
        ("Shelach", TorahRef("Numbers", 13, 1)),
        # A combined week opens where the first of the two begins.
        ("Vayakhel-Pekudei", TorahRef("Exodus", 35, 1)),
        ("ויקהל-פקודי", TorahRef("Exodus", 35, 1)),
        ("Matot-Masei", TorahRef("Numbers", 30, 2)),
        ("Nitzavim-Vayeilech", TorahRef("Deuteronomy", 29, 9)),
    ],
)
def test_parses(text: str, expected: TorahRef) -> None:
    assert parse(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "בראשית יב ויאמר",
        "Genesis is great",
        "Genesis 51:1",
        "Exodus 41",
        "Leviticus 28:1",
        "Numbers 37:1",
        "Deuteronomy 35:1",
        "Exodus 0:1",
        "Exodus 1:0",
        "Isaiah 1:1",
        "https://www.sefaria.org/Isaiah.1.1",
        "https://www.sefaria.org/Song_of_Songs.1.1",
        "https://example.com/Genesis.12.1",
        "",
        "   ",
        "12:1",
        "Genesis 12:5-1",
        "Genesis 12:1 and more",
        "בראשית יה",
        "בראשית אא",
        "Noach 6:9",
        "Lech Lecha is my portion",
        "Vayakhel-Noach",
        "hello",
    ],
)
def test_refuses(text: str) -> None:
    assert parse(text) is None


def test_books_are_the_corpus_names() -> None:
    assert set(torahref.CHAPTERS) == set(BOOKS)


def test_every_portion_opens_where_it_begins() -> None:
    from targum.parasha.build import fixed_starts

    for book in BOOKS:
        for start in fixed_starts(book):
            at = TorahRef(book, start.chapter, start.verse)
            assert parse(start.name) == at, start.name
            assert parse(start.hebrew) == at, start.hebrew


def _write(number: int) -> str:
    """A reference writer for Hebrew numerals, independent of the one under test."""
    hundreds = letters = ""
    if number >= 100:
        hundreds, number = "ק", number - 100
    tens, units = divmod(number, 10)
    if tens == 1 and units in (5, 6):
        return hundreds + "ט" + "וז"[units - 5]
    letters += " יכלמנסעפצ"[tens].strip() if tens else ""
    letters += " אבגדהוזחט"[units].strip() if units else ""
    return hundreds + letters


@pytest.mark.parametrize("number", range(1, 151))
def test_hebrew_numerals_round_trip(number: int) -> None:
    written = _write(number)
    assert hebrew_number(written) == number
    marked = f"{written[:-1]}״{written[-1]}" if len(written) > 1 else f"{written}׳"
    assert hebrew_number(marked) == number


def test_named_numerals() -> None:
    assert hebrew_number("טו") == 15
    assert hebrew_number("טז") == 16
    assert hebrew_number("קנ") == 150
    assert hebrew_number("י״ב") == 12
    assert hebrew_number("יב׳") == 12
    assert hebrew_number("ויאמר") is None
    assert hebrew_number("ך") is None
