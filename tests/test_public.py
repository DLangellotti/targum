"""The pages a stranger can reach.

These are the only surfaces a search engine ever sees, and the whole reason for
compiling a catalogue: somebody looking for a particular text should be able to find it
rather than meet a page saying "Coming soon". Everything else stays shut.
"""

from __future__ import annotations

import re
from html import unescape

import pytest

from targum.catalogue import CATALOGUE, Kind, Tag, beit_midrash
from targum.render.builder import shelf_page, text_page

ADDRESS = "https://targum.page"


def strip(markup: str) -> str:
    """The text a crawler indexes: no style block, no markup, entities resolved.

    Unescaping matters: Jinja turns the apostrophe in "Nevi'im" into `&#39;`, correctly,
    so comparing raw catalogue strings against raw HTML fails on exactly the entries
    whose names carry one.
    """
    markup = re.sub(r"<(style|script)[^>]*>.*?</\1>", " ", markup, flags=re.S)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", markup)).split())


# -- the catalogue ------------------------------------------------------------


def test_the_catalogue_page_names_itself_and_lists_every_text() -> None:
    """One list. There were two — a Library and a Beit Midrash — and the split meant a
    reader had to already know which room a text was in to find it."""
    html = shelf_page(ADDRESS)
    assert f'href="{ADDRESS}/library"' in html, "a canonical URL, or duplicates compete"
    for entry in CATALOGUE:
        assert f'href="/library/{entry.id}"' in html


def test_an_empty_catalogue_says_so_rather_than_pretending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tested by emptying it rather than by waiting for it to be empty: it has twenty
    texts now, so the earlier version of this found nothing to check and passed without
    asserting anything at all."""
    monkeypatch.setattr("targum.catalogue.CATALOGUE", [])
    assert "Nothing here yet" in shelf_page(ADDRESS)


# -- what a text is -----------------------------------------------------------


def test_the_jewish_texts_are_tagged() -> None:
    """The split is gone; what it was for is not. Some readers — ultra-Orthodox ones
    especially — would rather not be shown secular material at all, and a Beit Midrash
    mode needs to know which entries they came for. That is this tag, and nothing else
    can stand in for it: `sefaria:` is where a text was fetched from, not what it is.
    """
    tagged = beit_midrash()
    assert tagged, "the Tanakh entries carry the tag"
    assert all(Tag.tanakh in entry.tags for entry in tagged)
    # And it is a property of the entry, so it survives into the browser.
    assert tagged[0].state()["tags"] == ["tanakh"]

    untagged = [entry for entry in CATALOGUE if not entry.tags]
    assert untagged, "and the secular texts do not"
    assert untagged[0].state()["tags"] == []


# -- one text -----------------------------------------------------------------


@pytest.mark.parametrize("entry", CATALOGUE, ids=lambda e: e.id)
def test_every_text_page_carries_what_a_search_engine_needs(entry: object) -> None:
    html = text_page(entry, ADDRESS)  # type: ignore[arg-type]
    assert "<title>" in html and "</title>" in html
    described = re.search(r'name="description" content="([^"]+)"', html)
    assert described and len(described.group(1)) > 20, "a description worth showing"
    assert 'property="og:title"' in html
    assert f'rel="canonical" href="{ADDRESS}/' in html


@pytest.mark.parametrize("entry", CATALOGUE, ids=lambda e: e.id)
def test_a_text_page_is_about_the_text(entry: object) -> None:
    """Whoever arrives searched for the book, not for a reading tool."""
    text = strip(text_page(entry, ADDRESS))  # type: ignore[arg-type]
    assert entry.title in text  # type: ignore[attr-defined]
    assert entry.author in text  # type: ignore[attr-defined]
    assert entry.blurb in text  # type: ignore[attr-defined]


def test_the_sample_is_real_reading_in_both_languages() -> None:
    """A page of description ranks for nothing and tells a visitor nothing.

    Where an opening has been chosen, both sides of it have to actually be on the page.
    """
    with_sample = [entry for entry in CATALOGUE if entry.sample]
    assert with_sample, "at least one entry should carry an opening"
    for entry in with_sample:
        text = strip(text_page(entry, ADDRESS))
        for line in entry.sample:
            assert line.source[:40] in text, f"{entry.id}: source missing"
            assert line.target[:40] in text, f"{entry.id}: translation missing"


def test_the_source_side_is_marked_with_its_language_and_direction() -> None:
    """Hebrew rendered left-to-right is the failure this catches, and RTL is structural."""
    hebrew = [entry for entry in CATALOGUE if entry.language == "he" and entry.sample]
    assert hebrew
    for entry in hebrew:
        html = text_page(entry, ADDRESS)
        assert 'dir="rtl"' in html
        assert f'lang="{entry.language}"' in html


def test_a_translation_is_named_wherever_a_text_is_shown() -> None:
    """A reader decides whether to trust a translation by who made it.

    That is why it is body text rather than an attribution footnote — and for CC-BY it
    is also the obligation being discharged by the code rather than by memory.
    """
    for entry in CATALOGUE:
        text = strip(text_page(entry, ADDRESS))
        for rendering in entry.translations:
            assert rendering.name in text
            if rendering.publisher:
                assert rendering.publisher in text
            if rendering.licence:
                assert rendering.licence in text


def test_no_page_leaks_a_route_that_needs_an_account() -> None:
    private = ("/progress", "/readers", "/reader/", "/job/", "/glossary/")
    pages = [shelf_page(ADDRESS)]
    pages += [text_page(entry, ADDRESS) for entry in CATALOGUE]
    for html in pages:
        for route in private:
            assert f'href="{route}' not in html, f"{route} is not for strangers"


def test_samples_belong_to_entries_that_exist() -> None:
    """A sample keyed to a deleted entry is invisible until somebody wonders why a page
    is thin, so fail here instead."""

    from targum.catalogue import _samples

    known = {entry.id for entry in CATALOGUE}
    assert set(_samples()) <= known, f"samples for unknown entries: {set(_samples()) - known}"


def test_every_text_is_classified_and_measured() -> None:
    """The library sorts and filters on these three, and a filter is only worth having
    if what is behind it is true. Difficulty in particular is counted off the whole text
    by `scripts/measure_difficulty.py` rather than judged by eye — an entry added with
    the field left at zero is one the library cannot place."""
    from targum.catalogue import CATALOGUE, Kind, Register

    for entry in CATALOGUE:
        assert isinstance(entry.kind, Kind), entry.id
        assert isinstance(entry.register, Register), entry.id
        # A twenty-word scene can hold no uncommon word at all, and then zero is the
        # measurement rather than the absence of one; everywhere else zero means an
        # entry added with the field left blank.
        if entry.kind is Kind.dialogue:
            assert 0 <= entry.difficulty <= 60, entry.id
        else:
            assert entry.difficulty, f"{entry.id} has never been measured"
            # A share of running words, so anything outside these is a bug in the
            # counting rather than an unusually hard book.
            assert 5 <= entry.difficulty <= 60, entry.id
        assert entry.minutes >= 1, entry.id
        if entry.language.startswith("he"):
            assert entry.register is not Register.none, entry.id


def test_hebrew_poetry_reads_harder_than_hebrew_narrative() -> None:
    """A sanity check on the measurement rather than on any one number: whatever the
    scale is doing, Psalms cannot come out easier than Genesis."""
    from targum.catalogue import CATALOGUE, Kind

    def hardest(kind: Kind) -> float:
        found = [
            e.difficulty for e in CATALOGUE if e.kind is kind and e.register.value == "biblical"
        ]
        return sum(found) / len(found)

    assert hardest(Kind.poetry) > hardest(Kind.prose)


def test_a_cover_prompt_says_what_the_brand_never_draws() -> None:
    """An image model asked for a Hebrew book cover returns a scroll, a candelabrum and a
    flag every time, and §10 names all three as things this brand does not do."""
    from targum.catalogue import CATALOGUE, cover_prompt

    prompt = cover_prompt(CATALOGUE[0])
    said = prompt.lower()
    for banned in ("no flags", "no lettering", "no gradients", "ritual objects", "no maps"):
        assert banned in said
    # And it is about this text, not a generic cover.
    assert CATALOGUE[0].title in prompt and CATALOGUE[0].blurb in prompt


@pytest.mark.parametrize("kind", list(Kind))
def test_every_kind_of_text_has_a_cover_prompt(kind: Kind) -> None:
    """`cover_prompt` names each kind in words, from a table — and a kind added to the
    enum without a row in that table raised `KeyError` from the `/cover` route, so the
    library's Draw button answered with an empty body for every scene."""
    from dataclasses import replace

    from targum.catalogue import cover_prompt

    prompt = cover_prompt(replace(CATALOGUE[0], kind=kind))
    assert CATALOGUE[0].title in prompt


# -- what a text page says to a machine ---------------------------------------


def test_a_text_page_says_what_it_is_about() -> None:
    """These are the only pages a search engine sees, and four hundred pages about four
    hundred books looked like four hundred pages."""
    import json
    import re

    from targum.catalogue import by_id, everything
    from targum.render.builder import text_page

    entry = next(iter(everything()))
    page = text_page(entry, "https://targum.page")
    assert 'og:type" content="book"' in page
    found = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.S)
    assert found, "no structured data"
    about = json.loads(found.group(1))
    assert about["@type"] == "Book"
    assert about["name"] == entry.title
    assert about["inLanguage"] == entry.language
    assert by_id(entry.id) is not None


def test_a_byline_that_names_a_place_is_never_written_down_as_a_person() -> None:
    """`author` holds a person for the moderns and something else entirely for the rest —
    `Ketuvim · Ruth`, `משנה · סדר זרעים`. Filling schema.org's Person slot with one of
    those is telling a machine something untrue in order to fill a slot."""
    from targum.catalogue import Entry
    from targum.render.builder import text_schema

    place = Entry(
        id="x",
        title="ת",
        author="Ketuvim · Ruth",
        language="he",
        source="s",
        blurb="b",
        words=100,
    )
    assert "author" not in text_schema(place)

    person = Entry(
        id="y",
        title="ת",
        author="יוסף חיים ברנר, 1920",
        language="he",
        source="s",
        blurb="b",
        words=100,
    )
    assert text_schema(person)["author"]["name"] == "יוסף חיים ברנר, 1920"


def test_a_text_says_which_work_it_belongs_to() -> None:
    """Off the collections, which are real structure rather than a guess at one."""
    from targum.catalogue import collections
    from targum.render.builder import text_schema

    groups = collections()
    if not groups:
        return
    group = groups[0]
    from targum.catalogue import by_id

    entry = by_id(group.members[0])
    assert entry is not None
    assert text_schema(entry)["isPartOf"]["name"] == group.title


# -- the public pages in Russian (targum-internal#188) -------------------------
#
# Built on an entry of this file's own rather than on a catalogue row: the suite reads a
# 22-row fixture with no Russian in it, and the real 920-row catalogue is private data
# that CI's public checkout does not have. What is being tested is the page, not the data.


def a_russian_row():  # type: ignore[no-untyped-def]
    """A catalogue row drafted in Russian, the way all 920 real ones are."""
    from dataclasses import replace

    return replace(
        CATALOGUE[0],
        english="Israeli Declaration of Independence",
        blurb="The founding declaration, in a formal register.",
        named={"ru": "Декларация независимости Израиля"},
        blurbs={"ru": "Учредительная декларация в торжественном регистре."},
    )


def test_a_text_page_says_the_name_and_the_blurb_in_the_language_it_speaks() -> None:
    """These are the only pages a search engine sees, and this one said the book's name
    and description in English to everybody — while the shelf behind the sign-in has
    shown both in Russian since #289. Somebody who found targum by searching in Russian
    met an English description of the book they had searched for.
    """
    entry = a_russian_row()

    said = strip(text_page(entry, ADDRESS, language="ru"))
    assert entry.named["ru"] in said
    assert entry.blurbs["ru"] in said
    assert entry.english not in said, "and not the English beside it, which would be both"

    english = strip(text_page(entry, ADDRESS, language="en"))
    assert entry.english in english and entry.blurb in english, "English is unchanged"
    assert entry.blurbs["ru"] not in english


def test_the_russian_page_marks_its_russian_as_russian() -> None:
    """A Russian sentence inside `lang="en"` is read aloud in an English voice and
    indexed as English, which is the opposite of what this page is for."""
    html = text_page(a_russian_row(), ADDRESS, language="ru")
    assert '<p class="english" lang="ru"' in html
    assert '<p class="lede" lang="ru"' in html


def test_the_description_a_search_engine_shows_is_in_the_pages_language() -> None:
    """The meta description is the line under the title in a result, so it is the half of
    this that a Russian searcher reads before deciding whether to click."""
    entry = a_russian_row()
    html = text_page(entry, ADDRESS, language="ru")
    described = re.search(r'name="description" content="([^"]+)"', html)
    assert described and unescape(described.group(1)) == entry.blurbs["ru"]


def test_a_row_with_no_russian_shows_the_english_rather_than_nothing() -> None:
    """Empty means "not drafted yet", and the English showing is never wrong, only
    foreign — the rule the catalogue's own comment states."""
    bare = CATALOGUE[0]
    assert not bare.named.get("ru") and not bare.blurbs.get("ru"), "the fixture has none"
    assert bare.name_in("ru") == bare.english
    assert bare.blurb_in("ru") == bare.blurb
    said = strip(text_page(bare, ADDRESS, language="ru"))
    assert bare.blurb in said, "a Russian page with nothing Russian to say still says it"


def test_a_regional_tag_is_read_as_its_language() -> None:
    """`ru-RU` is Russian. The desk already normalises this; the public page must too, or
    a browser that asks politely gets English."""
    entry = a_russian_row()
    assert entry.blurb_in("ru-RU") == entry.blurbs["ru"]
    assert entry.name_in("RU") == entry.named["ru"]


def test_each_language_of_a_text_page_has_its_own_address_and_canonicals_to_it() -> None:
    """`hreflang` needs a URL per language: a crawler cannot be told two languages of a
    page exist unless each has one (targum-internal#188).

    And each canonicals to *itself*. Pointing the Russian page's canonical at the English
    would ask for the English to be indexed instead, which is the opposite of the point —
    the Russian would never rank and this card exists to have it rank.
    """
    entry = a_russian_row()
    base = f"{ADDRESS}/library/{entry.id}"

    english = text_page(entry, ADDRESS, language="en")
    assert f'rel="canonical" href="{base}"' in english, "English keeps the address it had"

    russian = text_page(entry, ADDRESS, language="ru")
    assert f'rel="canonical" href="{base}?lang=ru"' in russian


def test_a_text_page_declares_its_other_languages() -> None:
    entry = a_russian_row()
    base = f"{ADDRESS}/library/{entry.id}"
    for html in (
        text_page(entry, ADDRESS, language="en"),
        text_page(entry, ADDRESS, language="ru"),
    ):
        assert f'<link rel="alternate" hreflang="en" href="{base}">' in html
        assert f'<link rel="alternate" hreflang="ru" href="{base}?lang=ru">' in html
        # Where a crawler sends somebody whose language is neither.
        assert f'<link rel="alternate" hreflang="x-default" href="{base}">' in html


def test_a_page_with_no_address_declares_no_alternates() -> None:
    """A page rendered without an address has no URLs to point at, and half an hreflang
    set is worse than none."""
    html = text_page(a_russian_row(), "", language="ru")
    assert "hreflang" not in html


def _head(html: str) -> list[str]:
    """What a search result and a shared link show: the title, the description, and the
    two social tags that repeat them."""
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    assert title, "no title"
    said = [title.group(1)]
    for name in ('name="description"', 'property="og:title"', 'property="og:description"'):
        found = re.search(rf'<meta {name} content="([^"]*)"', html)
        assert found, f"no {name}"
        said.append(found.group(1))
    return [unescape(one) for one in said]


def test_a_russian_public_page_has_no_english_in_its_title_or_description() -> None:
    """targum-internal#188. The Russian pages and their hreflang were live, and the title
    and description a search result shows were still English on the shelf, the text pages,
    the parasha and the daily cycles — «מגילת העצמאות — Library — targum» on a page whose
    body was Russian.

    What may stay Latin is a name: targum's own, and the portion, its verses, the cycle's
    day and the Hebrew date as the calendar spells them. Anything else in Latin letters is
    English that leaked. A portion browsed to by name is titled with nothing but names, so
    it is the one head with no Russian in it to find.
    """
    from datetime import date

    from targum.daily.calendar import Day
    from targum.daily.cycles import CYCLES
    from targum.parasha import calendar as cal
    from targum.parasha.models import Portion
    from targum.render.builder import daily_page, parasha_page

    portion = Portion(
        slug="nasso",
        name="Nasso",
        hebrew="נָשֹׂא",
        numbers=[35],
        summary="Numbers 4:21-7:89",
        opening="וַיְדַבֵּר",
        verses=176,
        aliyot=7,
    )
    day = Day(
        day=date(2026, 9, 1),
        cycle=CYCLES[0].slug,
        title="Kelim 28:2-3",
        hebrew="כלים כח:ב-ג",
        hdate="19 Elul 5786",
        reference="Kelim 28:2-3",
        span=None,
    )
    pages = {
        "shelf": (shelf_page(ADDRESS, language="ru"), ""),
        "text": (text_page(a_russian_row(), ADDRESS, language="ru"), ""),
        "this week": (
            parasha_page(
                portion, schedule=cal.Schedule.diaspora, shabbat=date(2026, 5, 30), language="ru"
            ),
            f"{portion.name} {portion.summary}",
        ),
        "a portion": (
            parasha_page(portion, schedule=cal.Schedule.diaspora, language="ru"),
            f"{portion.name} {portion.summary}",
        ),
        "a portion with no range": (
            parasha_page(
                portion.model_copy(update={"summary": ""}),
                schedule=cal.Schedule.diaspora,
                language="ru",
            ),
            f"{portion.name} {portion.summary}",
        ),
        "daily": (
            daily_page(CYCLES[0], day, language="ru"),
            f"{day.title} {day.hdate}",
        ),
    }
    for page, (html, names) in pages.items():
        for said in _head(html):
            left = said.replace("targum", "")
            for name in names.split():
                left = left.replace(name, "")
            assert not re.search(r"[A-Za-z]{2,}", left), f"{page}: English in {said!r}"
            assert re.search(r"[А-Яа-яЁё]", said) or page == "a portion", (
                f"{page}: nothing Russian in {said!r}"
            )


def test_the_english_public_heads_say_what_they_said() -> None:
    """The move to the catalogue changed where the words live, not what English says."""
    assert "<title>Library — targum</title>" in shelf_page(ADDRESS)
    described = _head(shelf_page(ADDRESS))[1]
    assert described.startswith("Hebrew — Tanakh, novels, essays and speeches")
    assert "— Library — targum</title>" in text_page(a_russian_row(), ADDRESS)


# -- the names a calendar spells, and the daily and parasha pages in Russian (#188) ------


def _nasso():  # type: ignore[no-untyped-def]
    from targum.parasha.models import Portion

    return Portion(
        slug="nasso",
        name="Nasso",
        hebrew="נָשֹׂא",
        numbers=[35],
        summary="Numbers 4:21-7:89",
        opening="וַיְדַבֵּר",
        verses=176,
        aliyot=7,
    )


def _a_day(title: str = "Kelim 28:2-3", hdate: str = "19 Elul 5786"):  # type: ignore[no-untyped-def]
    from datetime import date

    from targum.daily.calendar import Day
    from targum.daily.cycles import CYCLES

    return Day(
        day=date(2026, 9, 1),
        cycle=CYCLES[0].slug,
        title=title,
        hebrew="כלים כח:ב-ג",
        hdate=hdate,
        reference=title,
        span=None,
    )


@pytest.mark.parametrize(
    ("english", "russian"),
    [
        ("Numbers 4:21-7:89", "Числа 4:21-7:89"),
        ("Genesis 1:1-6:8", "Бытие 1:1-6:8"),
        ("Deuteronomy 33:1-34:12", "Второзаконие 33:1-34:12"),
        ("I Kings 18:46-19:21", "I Царей 18:46-19:21"),
        ("II Kings 4:1-37", "II Царей 4:1-37"),
        ("II Samuel 22:1-51", "II Самуила 22:1-51"),
        ("Isaiah 54:1-10", "Исаия 54:1-10"),
        ("Hosea 14:2-10; Micah 7:18-20", "Осия 14:2-10; Михей 7:18-20"),
        ("Song of Songs Seder 1.1", "Песнь песней седер 1.1"),
        ("Ezra and Nehemiah Seder 10", "Ездра и Неемия седер 10"),
        ("Nehemiah 12:27-13:31", "Неемия 12:27-13:31"),
        ("Psalms 90-96", "Псалмы 90-96"),
        # A tractate has no Russian name in the catalogue, and is left as Hebcal spells it.
        ("Kelim 30:4-Oholot 1:1", "Kelim 30:4-Oholot 1:1"),
    ],
)
def test_a_reading_names_its_book_in_russian(english: str, russian: str) -> None:
    """targum-internal#188: "Numbers 4:21-7:89" on a Russian page is the one English
    phrase the parasha's title kept. The numbers stay; the book is named the way the
    Russian shelf already names it, «Числа»."""
    from targum.strings import said_reference

    assert said_reference(english, "ru") == russian
    assert said_reference(english, "en") == english, "English is left as Hebcal wrote it"


@pytest.mark.parametrize(
    ("english", "russian"),
    [
        ("19 Elul 5786", "19 элуля 5786"),
        ("1 Tishrei 5787", "1 тишрея 5787"),
        ("15 Sh'vat 5787", "15 швата 5787"),
        ("14 Adar II 5787", "14 адара II 5787"),
        ("14 Adar I 5787", "14 адара I 5787"),
        ("14 Adar 5786", "14 адара 5786"),
        ("1 Av 5786", "1 ава 5786"),
    ],
)
def test_a_hebrew_date_names_its_month_in_russian(english: str, russian: str) -> None:
    from targum.strings import said_hebrew_date

    assert said_hebrew_date(english, "ru") == russian
    assert said_hebrew_date(english, "en") == english


def test_a_month_is_only_ever_a_whole_word() -> None:
    """ "Av" is a month and the first two letters of "Avot", which is a tractate."""
    from targum.strings import said_hebrew_date, said_reference

    assert said_reference("Avot 1:1", "ru") == "Avot 1:1"
    assert said_hebrew_date("Avot 1:1", "ru") == "Avot 1:1"


def test_the_cycles_say_in_english_what_the_catalogue_says() -> None:
    """The daily page says a cycle's rhythm, credit and the cycles it cannot carry
    through the catalogue now; `daily.cycles` still holds the English, and the two must
    not drift apart."""
    from targum.daily.cycles import ABSENT, CYCLES
    from targum.strings import catalogue

    english = catalogue("en")
    for cycle in CYCLES:
        assert english[f"series.{cycle.slug}.name"] == cycle.name
        assert english[f"series.{cycle.slug}.what"] == cycle.blurb
        assert english[f"series.{cycle.slug}.rhythm"] == cycle.rhythm
        assert english[f"series.{cycle.slug}.credit"] == cycle.credit
    for name, why in ABSENT.items():
        key = "daily.absent." + "-".join(name.lower().split())
        assert english[key] == name
        assert english[f"{key}.why"] == why


def _body(html: str) -> str:
    """The words a reader sees: the body with its tags, scripts and styles taken out."""
    body = html.split("<body", 1)[1]
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", body, flags=re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    return unescape(" ".join(body.split()))


def test_a_russian_daily_page_says_its_headings_in_russian() -> None:
    """The head was Russian since #519 and the page under it was not: the headline, the
    line under it, the day's reading and its date, the other cycles and the credits."""
    from targum.daily.cycles import ABSENT, CYCLES
    from targum.render.builder import daily_page

    cycle = CYCLES[0]
    others = [(one, "תהלים צ") for one in CYCLES[1:]]
    html = daily_page(
        cycle,
        _a_day(),
        others=others,
        absent=list(ABSENT.items()),
        address=ADDRESS,
        language="ru",
    )
    seen = _body(html)
    assert '<h1 class="series-title">Мишна йомит</h1>' in html
    assert "Две мишны в день, через все шестьдесят три трактата" in seen
    assert "19 элуля" in seen and "Elul" not in seen
    for one in CYCLES[1:]:
        assert one.name not in seen, f"{one.name} is said in English"
    assert "Нах йоми" in seen and "Сегодня: תהלים צ" in seen
    assert cycle.credit not in seen and "рукописи Кауфмана A50" in seen
    for name, why in ABSENT.items():
        assert why not in seen, f"why {name} is absent is said in English"
    assert "Даф йоми" in seen

    english = daily_page(cycle, _a_day(), others=others, absent=list(ABSENT.items()))
    assert f'<h1 class="series-title">{cycle.name}</h1>' in english
    assert cycle.blurb in _body(english) and cycle.credit in _body(english)
    assert "19 Elul" in _body(english)


def test_today_s_daily_page_declares_its_languages_and_canonicals_to_its_own() -> None:
    from targum.daily.cycles import CYCLES
    from targum.render.builder import daily_page

    cycle = CYCLES[0]
    base = f"{ADDRESS}/{cycle.slug}"
    english = daily_page(cycle, _a_day(), address=ADDRESS, language="en")
    russian = daily_page(cycle, _a_day(), address=ADDRESS, language="ru")
    assert f'rel="canonical" href="{base}"' in english, "English keeps the address it had"
    assert f'rel="canonical" href="{base}?lang=ru"' in russian
    for html in (english, russian):
        assert f'<link rel="alternate" hreflang="en" href="{base}">' in html
        assert f'<link rel="alternate" hreflang="ru" href="{base}?lang=ru">' in html
        assert f'<link rel="alternate" hreflang="x-default" href="{base}">' in html

    # A dated day falls out of the window in a fortnight: no canonical, no alternates.
    dated = daily_page(cycle, _a_day(), address=ADDRESS, language="ru", is_today=False)
    assert "hreflang" not in dated.split("</head>")[0] and 'rel="canonical"' not in dated


def test_a_russian_parasha_page_names_its_books_and_its_month_in_russian() -> None:
    from datetime import date

    from targum.parasha import calendar as cal
    from targum.parasha.models import Haftarah
    from targum.render.builder import parasha_page

    portion = _nasso()
    haftarah = Haftarah(key="judges-13-2-25", summary="Judges 13:2-25", hebrew="שופטים", verses=24)
    html = parasha_page(
        portion,
        schedule=cal.Schedule.diaspora,
        shabbat=date(2026, 5, 30),
        hdate="14 Sivan 5786",
        haftarah=haftarah,
        listed=[portion],
        address=ADDRESS,
        language="ru",
    )
    seen = _body(html)
    assert "Числа 4:21-7:89" in seen and "Numbers" not in html
    assert "14 сивана" in seen and "Sivan" not in seen
    assert "Судьи 13:2-25 · 24 стиха" in seen
    assert "Metsudah linear" not in seen and "подстрочный перевод Мецуда" in seen

    base = f"{ADDRESS}/parasha/{portion.slug}"
    assert f'rel="canonical" href="{base}?lang=ru"' in html
    assert f'<link rel="alternate" hreflang="ru" href="{base}?lang=ru">' in html
    assert f'<link rel="alternate" hreflang="en" href="{base}">' in html

    english = parasha_page(
        portion,
        schedule=cal.Schedule.diaspora,
        shabbat=date(2026, 5, 30),
        hdate="14 Sivan 5786",
        haftarah=haftarah,
        address=ADDRESS,
    )
    assert f'rel="canonical" href="{base}"' in english
    assert "Numbers 4:21-7:89" in _body(english) and "14 Sivan" in _body(english)
    assert "Judges 13:2-25 · 24 verses" in _body(english)
    assert "the Metsudah linear translation" in _body(english)


def test_a_russian_weekly_page_describes_itself_in_russian() -> None:
    """The weekly's description was the issue's standfirst alone, which is one sentence
    in Hebrew on every language's page. What the series is follows it, in the page's own
    language."""
    from targum.render.builder import weekly_page
    from targum.weekly.models import Edition, Issue, Level, State, entry_id, folder

    week = "2026-w36"
    issue = Issue(
        id=week,
        dated="2026-08-31",
        title="השבוע בעברית",
        blurb="שבוע של חדשות.",
        state=State.published,
        editions=[
            Edition(level=one, entry_id=entry_id(week, one), folder=folder(week, one), ok=True)
            for one in Level
        ],
    )
    russian = _head(weekly_page(issue, Level.bet, address=ADDRESS, language="ru"))[1]
    assert russian == "שבוע של חדשות. Новости на иврите, написанные тремя способами, каждую неделю."
    english = _head(weekly_page(issue, Level.bet, address=ADDRESS))[1]
    assert english == "שבוע של חדשות. Hebrew news, written three ways, every week."
