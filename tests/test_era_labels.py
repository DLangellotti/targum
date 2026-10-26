"""An older Hebrew says which it is (David, 2026-10-25; design.md §12).

Revival, rabbinic and medieval Hebrew stay mixed into the Library and the arrival, and
each says which Hebrew it is wherever it shows: «Revival-era Hebrew, 1890s», with the
decade where the byline gives a year. Modern Hebrew, the Tanakh and every other language
say nothing, so their pages are what they were.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from html import unescape

import pytest

from targum import catalogue
from targum.catalogue import Entry, Register
from targum.chat import tools
from targum.render import builder
from targum.render.builder import build_text_card, contents_page, text_page

ADDRESS = "https://targum.page"


def entry(register: Register, author: str = "", language: str = "he") -> Entry:
    return Entry(
        id=f"era-{register.value or 'none'}",
        title="סיפור",
        author=author,
        language=language,
        source=f"benyehuda:era-{register.value}",
        blurb="A story long enough to describe itself on its own page.",
        words=1300,
        english="A Story",
        register=register,
    )


@pytest.mark.parametrize(
    ("register", "author", "english", "russian"),
    [
        (
            Register.revival,
            "מיכה יוסף ברדיצ'בסקי, 1896",
            "Revival-era Hebrew, 1890s",
            "Иврит эпохи Возрождения, 1890-е",
        ),
        (Register.revival, "יוסף חיים ברנר", "Revival-era Hebrew", "Иврит эпохи Возрождения"),
        (
            Register.rabbinic,
            "משה בן מימון, 1180 · ספר המדע",
            "Rabbinic Hebrew, 1180s",
            "Раввинский иврит, 1180-е",
        ),
        (Register.rabbinic, "", "Rabbinic Hebrew", "Раввинский иврит"),
        (
            Register.medieval,
            "יהודה הלוי, תרגם יהודה אבן תיבון, 1167",
            "Medieval Hebrew, 1160s",
            "Средневековый иврит, 1160-е",
        ),
    ],
)
def test_each_older_hebrew_is_labelled_with_its_decade_where_it_has_one(
    register: Register, author: str, english: str, russian: str
) -> None:
    one = entry(register, author)
    assert catalogue.era_said(one) == english
    assert catalogue.era_said(one, "ru") == russian
    state = one.state()
    assert state["era"] == register.value
    assert state["decade"] == catalogue.decade_of(one)


@pytest.mark.parametrize(
    "one",
    [
        entry(Register.modern, "State of Israel, 1948"),
        entry(Register.biblical),
        entry(Register.none, "Лев Толстой, 1886", language="ru"),
        # A register on a row in another language is not a Hebrew to label.
        entry(Register.revival, "1900", language="yi"),
    ],
    ids=["modern", "biblical", "russian", "yiddish"],
)
def test_modern_hebrew_the_tanakh_and_other_languages_say_nothing(one: Entry) -> None:
    assert catalogue.era_of(one) is None
    assert catalogue.era_said(one) == ""
    assert one.state()["era"] == "" and one.state()["decade"] == 0


def test_every_older_hebrew_in_the_catalogue_is_labelled() -> None:
    for one in catalogue.CATALOGUE:
        if one.language == "he" and one.register in catalogue.ERAS:
            assert catalogue.era_said(one), one.id
        elif one.register in (Register.modern, Register.biblical, Register.none):
            assert not catalogue.era_said(one), one.id


def test_the_text_page_says_the_era_under_the_byline() -> None:
    revival = entry(Register.revival, "יוסף חיים ברנר, 1906")
    html = text_page(revival, ADDRESS)
    assert '<p class="era" lang="en">Revival-era Hebrew, 1900s</p>' in html
    assert "Иврит эпохи Возрождения, 1900-е" in text_page(revival, ADDRESS, language="ru")


def test_a_modern_text_page_is_unchanged() -> None:
    modern = entry(Register.modern, "State of Israel, 1948")
    html = text_page(modern, ADDRESS)
    assert 'class="era"' not in html
    # The same page as a row with no register at all: nothing was added for it.
    assert html == text_page(replace(modern, register=Register.none), ADDRESS)


def test_the_contents_page_and_the_reader_ask_the_catalogue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    revival = entry(Register.revival, "מיכה יוסף ברדיצ'בסקי, 1896")
    modern = entry(Register.modern)
    rows = {revival.source: revival, modern.source: modern}
    monkeypatch.setattr(catalogue, "matching", lambda source: rows.get(source))
    assert builder._era_of_source(revival.source, "en") == "Revival-era Hebrew, 1890s"
    assert builder._era_of_source(revival.source, "ru") == "Иврит эпохи Возрождения, 1890-е"
    assert builder._era_of_source(modern.source, "en") == ""
    assert builder._era_of_source("upload:mine", "en") == ""

    manifest = {
        "version": 1,
        "document": "d",
        "title": revival.title,
        "author": revival.author,
        "source": revival.source,
        "language": "he",
        "medium": "read",
        "layout": "book",
        "sections": [
            {"number": n, "file": f"sec-{n:04d}.html", "title": f"פרק {n}", "words": 9}
            for n in (1, 2)
        ],
    }
    page = contents_page(manifest, {})
    assert '<span class="parts-era">Revival-era Hebrew, 1890s</span>' in page
    plain = contents_page({**manifest, "source": modern.source}, {})
    assert 'class="parts-era"' not in plain


def test_the_connectors_rows_carry_the_label_and_modern_ones_do_not() -> None:
    revival = tools._entry_row(entry(Register.revival, "אחד העם, 1891"), None, {})
    assert revival["era"] == "Revival-era Hebrew, 1890s"
    assert revival["era_of"] == {"register": "revival", "decade": 1890}
    rabbinic = tools._entry_row(entry(Register.rabbinic), None, {})
    assert rabbinic["era"] == "Rabbinic Hebrew"
    assert rabbinic["era_of"] == {"register": "rabbinic", "decade": 0}
    modern = tools._entry_row(entry(Register.modern), None, {})
    assert "era" not in modern and "era_of" not in modern


def eras_on(page: str) -> dict[str, list[str]]:
    found = re.search(r"data-eras='([^']*)'", page)
    assert found
    said: dict[str, list[str]] = json.loads(unescape(found.group(1)))
    return said


def test_the_text_card_says_the_era_in_the_pages_language() -> None:
    assert eras_on(build_text_card())["revival"] == [
        "Revival-era Hebrew",
        "Revival-era Hebrew, {decade}s",
    ]
    assert eras_on(build_text_card("ru"))["revival"][1] == "Иврит эпохи Возрождения, {decade}-е"
