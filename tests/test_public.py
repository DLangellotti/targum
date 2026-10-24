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
from targum.render.builder import SHELF_ROWS, kind_page, shelf_page, text_page

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


def test_the_catalogue_page_names_itself_and_reaches_every_text() -> None:
    """One catalogue. There were two — a Library and a Beit Midrash — and the split meant
    a reader had to already know which room a text was in to find it. Since #519 a text
    is on the Library or one press away on its kind's page, and every one is a link a
    crawler follows."""
    html = shelf_page(ADDRESS)
    assert f'href="{ADDRESS}/library"' in html, "a canonical URL, or duplicates compete"
    kinds = set(re.findall(r'href="(/library/k/[a-z]+/[a-z]+)"', html))
    pages = [html] + [kind_page(*at.split("/")[3:], ADDRESS) or "" for at in sorted(kinds)]
    for entry in CATALOGUE:
        assert any(f'href="/library/{entry.id}"' in page for page in pages), entry.id


def test_an_empty_catalogue_says_so_rather_than_pretending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tested by emptying it rather than by waiting for it to be empty: it has twenty
    texts now, so the earlier version of this found nothing to check and passed without
    asserting anything at all."""
    monkeypatch.setattr("targum.catalogue.CATALOGUE", [])
    assert "Nothing here yet" in shelf_page(ADDRESS)


def _shelf_of_two(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ruth drafted in Russian, and a text nobody has drafted yet."""
    from targum.catalogue import Entry

    monkeypatch.setattr(
        "targum.catalogue.CATALOGUE",
        [
            Entry(
                id="ruth",
                title="רות",
                author="Ketuvim · Ruth",
                language="he",
                source="sefaria:he:Ruth",
                blurb="Four chapters, the shortest way in.",
                words=100,
                english="Ruth",
                named={"ru": "Рут (Руфь)"},
                blurbs={"ru": "Четыре главы — самый короткий путь внутрь."},
            ),
            Entry(
                id="undrafted",
                title="ספר",
                author="Somebody, 1990",
                language="he",
                source="s",
                blurb="Nobody has said this in Russian yet.",
                words=100,
                english="A Book",
            ),
        ],
    )


def _row(html: str, entry_id: str) -> str:
    start = html.index(f'href="/library/{entry_id}"')
    return html[start : html.index("</li>", start)]


def test_a_russian_shelf_row_is_in_russian_where_the_text_page_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The shelf ignored what the catalogue knew: 1,306 of 1,315 rows drew English under
    a Russian chrome while each text page said the Russian (targum-internal#520)."""
    _shelf_of_two(monkeypatch)
    ruth = _row(shelf_page(ADDRESS, language="ru"), "ruth")
    assert '<span class="english" lang="ru" dir="ltr">Рут (Руфь)</span>' in ruth
    assert '<span class="blurb">Четыре главы — самый короткий путь внутрь.</span>' in ruth
    assert "Ruth" not in ruth and "shortest" not in ruth
    # The place takes the book names David chose on 2026-10-21.
    assert '<span class="byline">Писания · Рут</span>' in ruth


def test_a_row_with_no_russian_falls_back_to_english_and_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never wrong, only foreign — and marked English, so a screen reader reads it as
    English rather than as Russian."""
    _shelf_of_two(monkeypatch)
    row = _row(shelf_page(ADDRESS, language="ru"), "undrafted")
    assert '<span class="english" lang="en" dir="ltr">A Book</span>' in row
    assert '<span class="blurb" lang="en">Nobody has said this in Russian yet.</span>' in row
    assert '<span class="byline">Somebody, 1990</span>' in row


def test_an_english_shelf_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    _shelf_of_two(monkeypatch)
    ruth = _row(shelf_page(ADDRESS), "ruth")
    assert '<span class="english" lang="en" dir="ltr">Ruth</span>' in ruth
    assert '<span class="blurb">Four chapters, the shortest way in.</span>' in ruth
    assert '<span class="byline">Ketuvim · Ruth</span>' in ruth
    assert not re.search("[А-Яа-я]", ruth)


def test_a_text_page_says_its_place_in_the_page_language() -> None:
    """The text page's own place line said "Ketuvim · Ruth" under a Russian chrome while
    the shelf behind it said «Писания · Рут» (targum-internal#523, from #477)."""
    from targum.catalogue import Entry

    ruth = Entry(
        id="ruth",
        title="רות",
        author="Ketuvim · Ruth",
        language="he",
        source="sefaria:he:Ruth",
        blurb="Four chapters, the shortest way in.",
        words=100,
        english="Ruth",
    )
    assert '<p class="byline">Писания · Рут</p>' in text_page(ruth, ADDRESS, language="ru")
    assert '<p class="byline">Ketuvim · Ruth</p>' in text_page(ruth, ADDRESS)


# -- what a text is -----------------------------------------------------------


# -- the Library in sections (targum-internal#519) ------------------------------------


def _entry(n: int, language: str, kind: Kind, author: str = "Somebody, 1990") -> object:
    from targum.catalogue import Entry

    return Entry(
        id=f"{language}-{kind.value}-{n}",
        title=f"ספר {n}" if language == "he" else f"Book {n}",
        author=author,
        language=language,
        source=f"s:{language}:{n}",
        blurb=f"Blurb {n}.",
        words=100,
        english=f"Book {n}",
        kind=kind,
    )


def _a_wide_shelf(monkeypatch: pytest.MonkeyPatch) -> None:
    """Russian with more rows than Hebrew, so Hebrew first is the rule and not the count;
    a kind longer than a kind shows, and a kind shorter."""
    rows = [
        *(_entry(n, "ru", Kind.talk) for n in range(20)),
        *(_entry(n, "he", Kind.story) for n in range(9)),
        *(_entry(n, "he", Kind.poetry) for n in range(2)),
        *(_entry(n, "it", Kind.story) for n in range(3)),
    ]
    monkeypatch.setattr("targum.catalogue.CATALOGUE", rows)
    monkeypatch.setattr("targum.catalogue.COLLECTIONS", [])


def _sections(html: str) -> list[str]:
    return re.findall(r'<section class="lib-lang" id="in-([a-z]+)"', html)


def test_the_library_stands_hebrew_first_then_each_language_by_its_size(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chekhov and Italian picture books stood in Ruth's column, under a line about Hebrew
    (#477, B4). Hebrew leads because Hebrew is what targum teaches, whoever has more."""
    _a_wide_shelf(monkeypatch)
    html = shelf_page(ADDRESS)
    assert _sections(html) == ["he", "ru", "it"]
    assert 'Hebrew <span class="lib-count">· 11 texts</span>' in html
    assert 'Russian <span class="lib-count">· 20 texts</span>' in html
    russian = shelf_page(ADDRESS, language="ru")
    assert 'Иврит <span class="lib-count">· 11 текстов</span>' in russian
    assert 'Итальянский <span class="lib-count">· 3 текста</span>' in russian


def test_the_library_draws_a_few_rows_a_kind_and_a_way_to_all_of_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pin: 1,315 rows on one page was 237,000px at 1440. A kind shows its first rows
    and says how many there are; one that fits shows them all and offers no more."""
    _a_wide_shelf(monkeypatch)
    html = shelf_page(ADDRESS)
    kinds = re.findall(r'<section class="lib-kind"', html)
    rows = html.count('<li class="lib-row">')
    assert rows <= SHELF_ROWS * len(kinds)
    assert rows == SHELF_ROWS + 2 + SHELF_ROWS + 3
    assert '<a class="lib-all" href="/library/k/he/story">All 9 <span' in html
    assert '<a class="lib-all" href="/library/k/ru/talk">All 20 <span' in html
    assert "/library/k/he/poetry" not in html and "/library/k/it/story" not in html
    # In the signed-in Library's order and its words: Stories before Poetry.
    assert html.index(">Stories</h3>") < html.index(">Poetry</h3>")
    assert "Все 9" in shelf_page(ADDRESS, language="ru")


def test_the_library_asks_for_the_waitlist_under_its_lede(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The only ask was Sign in at the top and the waitlist under all 1,315 rows (§6)."""
    _a_wide_shelf(monkeypatch)
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    html = shelf_page(ADDRESS)
    head = html[
        html.index('<header class="lib-head">') : html.index(
            "</header>", html.index('<header class="lib-head">')
        )
    ]
    assert "34 texts and videos to learn from." in head
    assert "Free to read once you’re in." in head
    assert '<a class="btn cta" href="/#join">Join the waitlist</a>' in head
    assert html.index('class="lib-head"') < html.index('class="lib-lang"')


def test_the_library_wears_the_front_door_and_carries_no_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One look across the public front (David, 2026-10-24): the landing's bar, ground
    and face. Script-free, so every text is a link with nothing in front of it."""
    _a_wide_shelf(monkeypatch)
    html = shelf_page(ADDRESS)
    assert '<body class="landing">' in html
    assert '<header class="bar">' in html
    assert "Source Sans 3" in html
    assert "<script" not in html.replace('<script type="application/ld+json">', "")


def test_a_kind_has_a_page_of_its_own_that_is_not_indexed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every text of the kind, and kept out of search until David decides it belongs
    there; its links to the texts are still followed."""
    _a_wide_shelf(monkeypatch)
    page = kind_page("he", "story", ADDRESS)
    assert page is not None
    assert page.count('<li class="lib-row">') == 9
    assert '<meta name="robots" content="noindex">' in page
    assert "<title>Hebrew · Stories — Library — targum</title>" in page
    assert f'<link rel="canonical" href="{ADDRESS}/library/k/he/story">' in page
    assert '<a class="lib-back" href="/library">' in page
    assert '<meta name="robots"' not in shelf_page(ADDRESS)
    russian = kind_page("he", "story", ADDRESS, language="ru") or ""
    assert "<title>Иврит · Рассказы — Библиотека — targum</title>" in russian
    assert kind_page("he", "talk", ADDRESS) is None
    assert kind_page("xx", "story", ADDRESS) is None


#: What the public Library may weigh, with the faces it carries inside it. It was 806 kB
#: (184 kB gzipped) with every row and the reader's stylesheet; a phone on 1.6 Mbps
#: has §14's 1.5 s.
SHELF_BUDGET = {"en": 240_000, "ru": 290_000}


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_library_weighs_the_same_however_long_the_catalogue_grows(
    monkeypatch: pytest.MonkeyPatch, language: str
) -> None:
    """The payload check (#519): 1,320 texts in five languages draw a bounded page, and
    the page carries no stylesheet but the front door's and its own."""
    rows = [
        _entry(n, code, kind)
        for code, kinds in (("he", list(Kind)), ("ru", list(Kind)[:5]), ("it", [Kind.story]))
        for kind in kinds
        for n in range(1320 // 30)
    ]
    monkeypatch.setattr("targum.catalogue.CATALOGUE", rows)
    monkeypatch.setattr("targum.catalogue.COLLECTIONS", [])
    html = shelf_page(ADDRESS, language=language)
    kinds = html.count('<section class="lib-kind"')
    assert html.count('<li class="lib-row">') <= SHELF_ROWS * kinds
    assert len(html.encode("utf-8")) < SHELF_BUDGET[language], len(html.encode("utf-8"))
    assert "body.public" not in html, "the sheet pages' stylesheet, and the reader's with it"


def test_a_pressed_language_goes_on_every_link_the_library_draws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """In an English browser, /library?lang=ru opened its kinds, its texts and the
    waitlist in English (design's review of #925). A language the browser chose is not
    carried: it is chosen again on the next page."""
    _a_wide_shelf(monkeypatch)
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    html = shelf_page(ADDRESS, language="ru", asked="ru")
    assert '<a class="lib-all" href="/library/k/he/story?lang=ru">' in html
    assert 'href="/library/he-story-0?lang=ru"' in html
    assert '<a class="btn cta" href="/?lang=ru#join">' in html
    assert 'href="/account/signin?lang=ru"' in html
    assert 'href="/?lang=ru#own"' in html
    rows = re.findall(r'href="(/library/[^"]*)"', html)
    assert rows and all(row.endswith("?lang=ru") for row in rows), rows
    kind = kind_page("he", "story", ADDRESS, language="ru", asked="ru") or ""
    assert '<a class="lib-back" href="/library?lang=ru">' in kind
    assert "?lang=" not in shelf_page(ADDRESS, language="ru").split("<main")[1].split("</main>")[0]


def test_a_kind_of_videos_counts_videos(monkeypatch: pytest.MonkeyPatch) -> None:
    """ "178 texts" headed Russian · Videos (design's review of #925)."""
    _a_wide_shelf(monkeypatch)
    assert '<p class="lib-lede">20 videos</p>' in (kind_page("ru", "talk", ADDRESS) or "")
    russian = kind_page("ru", "talk", ADDRESS, language="ru") or ""
    assert '<p class="lib-lede">20 видео</p>' in russian
    assert '<p class="lib-lede">9 texts</p>' in (kind_page("he", "story", ADDRESS) or "")


def test_a_hebrew_word_inside_a_latin_byline_says_its_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ "Omid Memarian, תרגם Gallia Hoz, 2014" put a Hebrew word in an English run, read
    with the English voice (#477, polish 10)."""
    row = _entry(1, "he", Kind.essay, author="Omid Memarian, תרגם Gallia Hoz, 2014")
    monkeypatch.setattr("targum.catalogue.CATALOGUE", [row])
    html = _row(shelf_page(ADDRESS), "he-essay-1")
    assert (
        '<span class="byline">Omid Memarian, <bdi lang="he">תרגם</bdi> Gallia Hoz, 2014</span>'
        in html
    )


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
    from targum.render.builder import translation_credit

    for entry in CATALOGUE:
        text = strip(text_page(entry, ADDRESS))
        for rendering in translation_credit(entry).renderings:
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
        ("Numbers 4:21-7:89", "Бемидбар 4:21-7:89"),
        ("Genesis 1:1-6:8", "Берейшит 1:1-6:8"),
        ("Deuteronomy 33:1-34:12", "Дварим 33:1-34:12"),
        ("I Kings 18:46-19:21", "Млахим I 18:46-19:21"),
        ("II Kings 4:1-37", "Млахим II 4:1-37"),
        ("II Samuel 22:1-51", "Шмуэль II 22:1-51"),
        ("Isaiah 54:1-10", "Йешаяу 54:1-10"),
        ("Hosea 14:2-10; Micah 7:18-20", "Ошеа 14:2-10; Миха 7:18-20"),
        ("Song of Songs Seder 1.1", "Шир а-Ширим седер 1.1"),
        ("Ezra and Nehemiah Seder 10", "Эзра и Нехемья седер 10"),
        ("Nehemiah 12:27-13:31", "Нехемья 12:27-13:31"),
        ("Psalms 90-96", "Теилим 90-96"),
        # A tractate has no Russian name in the catalogue, and is left as Hebcal spells it.
        ("Kelim 30:4-Oholot 1:1", "Kelim 30:4-Oholot 1:1"),
    ],
)
def test_a_reading_names_its_book_in_russian(english: str, russian: str) -> None:
    """targum-internal#188: "Numbers 4:21-7:89" on a Russian page is the one English
    phrase the parasha's title kept. The numbers stay; the book is named the way the
    Russian interface names it, «Бемидбар»."""
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
    assert "Бемидбар 4:21-7:89" in seen and "Numbers" not in html
    assert "14 сивана" in seen and "Sivan" not in seen
    assert "Шофтим 13:2-25 · 24 стиха" in seen
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


def test_read_it_signs_in_and_lands_on_the_text() -> None:
    """Known issues 2.13: signed out, "Read it" went to `/account/signin` with nothing
    after it, so the learner signed in and landed home instead of on the text they chose.
    Both doors on the page carry the text, through `/open/`, and a Russian page keeps
    its language at the door."""
    import re

    from targum.catalogue import everything
    from targum.render.builder import text_page

    entry = next(iter(everything()))
    page = text_page(entry, "https://targum.page")
    doors = re.findall(r'<a class="(?:go|enter)" href="([^"]+)"', page)
    assert doors == [f"/account/signin?next=%2Fopen%2F{entry.id}"] * 2
    russian = text_page(entry, "https://targum.page", language="ru")
    assert f'href="/account/signin?next=%2Fopen%2F{entry.id}&amp;lang=ru"' in russian


# -- what a shared link shows -------------------------------------------------


def test_every_public_page_names_the_link_preview() -> None:
    """One picture for every public page, at its full address and its size (design.md
    §12, "A shared link shows the mark", 2026-10-13). Without it a shared link was bare
    and Meta's crawler asked for /null."""
    import struct

    from targum.catalogue import everything
    from targum.render.builder import LINK_PREVIEW, LINK_PREVIEW_SIZE

    entry = next(iter(everything()))
    for page in (shelf_page(ADDRESS), text_page(entry, ADDRESS)):
        assert f'property="og:image" content="{ADDRESS}/link-preview.png"' in page
        assert 'property="og:image:width" content="1200"' in page
        assert 'property="og:image:height" content="630"' in page
        assert 'name="twitter:card" content="summary_large_image"' in page
        assert "null" not in re.findall(r'<meta property="og:image" content="([^"]*)"', page)[0]
    head = LINK_PREVIEW.read_bytes()[:24]
    assert head[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", head[16:24]) == LINK_PREVIEW_SIZE, "the size the tags say"


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_about_page_carries_the_public_head(language: str) -> None:
    """targum-internal#518: /about is in the sitemap and in every public foot, and a shared
    link to it was a bare line, with no description and no picture. It takes the head
    every other public page has, from the same partial."""
    from targum.render.builder import about_page

    page = about_page(language=language, address=ADDRESS)
    for tag in (
        'name="description" content="',
        'property="og:title" content="',
        'property="og:description" content="',
        f'property="og:url" content="{ADDRESS}/about"',
        f'property="og:image" content="{ADDRESS}/link-preview.png"',
        'property="og:image:alt" content="',
        'name="twitter:card" content="summary_large_image"',
        f'<link rel="canonical" href="{ADDRESS}/about">',
    ):
        assert tag in page, tag
    described = re.search(r'<meta name="description" content="([^"]+)"', page)
    assert described and described.group(1).strip()
    if language == "ru":
        assert "Все изменения" in described.group(1), "the Russian page says it in Russian"
    assert page.count("<title>") == 1 and page.count('rel="canonical"') == 1
    assert 'hreflang="' not in page, "one address for every language, so no alternates"


def test_a_page_with_no_address_names_no_preview(monkeypatch: pytest.MonkeyPatch) -> None:
    """A local build knows no origin, and a picture at a relative address is one a crawler
    drops. Nothing is better than a broken one."""
    monkeypatch.delenv("TARGUM_PUBLIC_ADDRESS", raising=False)
    page = shelf_page("")
    assert "og:image" not in page
    assert 'name="twitter:card" content="summary"' in page


# -- the credit names the translation the page shows (targum-internal#521) ----------
#
# A Russian page set Hebrew beside Russian lines and credited, under an English
# "Translation", Metsudah's English: a credit for words it did not show and none for the
# words it did. Built on rows of this file's own, for the reason given above.

ENGLISH = "The Metsudah test Chumash"
RUSSIAN = "Пятикнижие, пер. Герштейна и Гордона"


def a_torah_row(monkeypatch: pytest.MonkeyPatch, drawn: bool):  # type: ignore[no-untyped-def]
    """A Torah book carrying an English and a Russian rendering, and Rashi, with an
    opening whose Russian is copied out of the Russian rendering or (`drawn=False`) is
    ours, translated from the English the way every sample's Russian was."""
    from dataclasses import replace

    from targum import catalogue
    from targum.catalogue import Line, Rendering

    entry = replace(
        CATALOGUE[0],
        id="a-torah-book",
        translations=[
            Rendering(
                name=ENGLISH,
                source="sefaria:en:Genesis",
                publisher="Metsudah Publications",
                licence="CC-BY",
            ),
            Rendering(
                name=RUSSIAN,
                source="published:ru:Genesis",
                publisher="Gerstein & Gordon (Vilna, 1875)",
                licence="Public Domain",
                licence_url="https://rusneb.ru/catalog/000199_000009_009682814/",
            ),
            Rendering(name="Rashi Chumash", source="sefaria:en:Rashi on Genesis", licence="CC-BY"),
        ],
    )
    lines = [
        Line(
            source="בְּרֵאשִׁית בָּרָא אֱלֹהִים",
            target="In the beginning Elohim created",
            said={"ru": "Въ началѣ сотворилъ Богъ"},
            drawn={"ru": "published:ru:Genesis"} if drawn else {},
        )
    ]
    monkeypatch.setattr(catalogue, "sample_for", lambda entry_id: lines)
    return entry


def structured(html: str) -> dict:  # type: ignore[type-arg]
    import json

    found = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert found
    return json.loads(found.group(1))  # type: ignore[no-any-return]


def provenance(html: str) -> str:
    found = re.search(r'<section class="provenance".*?</section>', html, re.S)
    assert found, "the page names no translation"
    return found.group(0)


def test_a_russian_page_credits_the_russian_translation_it_shows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = a_torah_row(monkeypatch, drawn=True)
    html = text_page(entry, ADDRESS, language="ru")
    credit = strip(provenance(html))
    assert RUSSIAN in credit and "Gerstein & Gordon" in credit and "Public Domain" in credit
    assert 'href="https://rusneb.ru/catalog/000199_000009_009682814/"' in provenance(html)
    assert ENGLISH not in credit, "the English is not on this page"
    assert "Rashi" not in credit
    assert '<p class="target" lang="ru"' in html
    works = structured(html)["workTranslation"]
    assert [(work["name"], work["inLanguage"]) for work in works] == [(RUSSIAN, "ru")]


def test_an_english_page_credits_the_english_translation_it_shows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = a_torah_row(monkeypatch, drawn=True)
    html = text_page(entry, ADDRESS, language="en")
    credit = strip(provenance(html))
    assert ENGLISH in credit and "Metsudah Publications" in credit and "CC-BY" in credit
    assert RUSSIAN not in credit, "the Russian is not on this page"
    assert '<p class="target" lang="en"' in html
    works = structured(html)["workTranslation"]
    assert [(work["name"], work["inLanguage"]) for work in works] == [(ENGLISH, "en")]


def test_russian_lines_we_translated_say_so_and_name_the_english_they_came_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every sample's Russian so far: a model's, from the English beside it. The page
    does not call it the published Russian, and names the CC BY English it was made
    from, which a translation of that English still owes."""
    from targum.strings import text

    entry = a_torah_row(monkeypatch, drawn=False)
    credit = strip(provenance(text_page(entry, ADDRESS, language="ru")))
    assert RUSSIAN not in credit, "the published Russian is not what is shown"
    assert ENGLISH in credit and "CC-BY" in credit
    assert text("text.page.we-translated-these-lines-from-the-english", "ru") in credit


def test_a_text_in_the_pages_language_shows_its_english(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Russian story beside a Russian "translation" of itself is no translation."""
    from dataclasses import replace

    from targum import catalogue
    from targum.catalogue import Line, Rendering

    story = replace(
        CATALOGUE[0],
        id="a-russian-story",
        language="ru",
        translations=[Rendering(name="The English original", source="https://x.test/en")],
    )
    lines = [Line(source="Встречайте", target="Meet", said={"ru": "Познакомьтесь"})]
    monkeypatch.setattr(catalogue, "sample_for", lambda entry_id: lines)
    html = text_page(story, ADDRESS, language="ru")
    assert '<p class="target" lang="en" dir="ltr">Meet</p>' in html
    assert "Познакомьтесь" not in html
    assert "The English original" in strip(provenance(html))


def test_the_credit_heading_is_said_in_the_pages_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = a_torah_row(monkeypatch, drawn=True)
    assert "<h2>Перевод</h2>" in provenance(text_page(entry, ADDRESS, language="ru"))
    assert "<h2>Translation</h2>" in provenance(text_page(entry, ADDRESS, language="en"))


@pytest.mark.parametrize(("language", "ours"), [("en", "We translated this text."), ("ru", None)])
def test_a_bought_translation_says_it_is_ours_and_names_targum_as_translator(
    monkeypatch: pytest.MonkeyPatch, language: str, ours: str | None
) -> None:
    """A row whose translation we bought, with no published rendering, says so in words
    and in the JSON-LD rather than crediting nobody."""
    from dataclasses import replace

    from targum import catalogue
    from targum.catalogue import Line
    from targum.strings import text

    bought = replace(CATALOGUE[0], id="a-bought-text", translations=[], model="claude-opus-5")
    lines = [
        Line(source="כיון שנושב רוח חם", target="As soon as a warm wind", said={"ru": "Как только"})
    ]
    monkeypatch.setattr(catalogue, "sample_for", lambda entry_id: lines)
    html = text_page(bought, ADDRESS, language=language)
    said = ours or text("text.page.we-translated-this-text", language)
    assert said in strip(provenance(html))
    assert structured(html)["workTranslation"] == [
        {
            "@type": "Book",
            "inLanguage": language,
            "translator": {"@type": "Organization", "name": "targum"},
        }
    ]


def test_lines_we_translated_name_targum_beside_the_english_in_the_json_ld(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = a_torah_row(monkeypatch, drawn=False)
    works = structured(text_page(entry, ADDRESS, language="ru"))["workTranslation"]
    assert [(work.get("name"), work["inLanguage"]) for work in works] == [
        (ENGLISH, "en"),
        (None, "ru"),
    ]
    assert works[1]["translator"] == {"@type": "Organization", "name": "targum"}
