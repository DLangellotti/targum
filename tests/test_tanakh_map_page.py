"""The Tanakh map's page (targum-internal#144): every chapter a square, linked to where
it is read, and shaded from `/tanakh-map.json` by the share of it the reader knows.

The data behind it is `test_tanakh_map.py`'s. Here: that the page draws the Tanakh in the
Hebrew order and count, that a chapter's address is its book's door with the chapter on
it, that Aramaic and a missing book are never a share, that the server answers a signed-
in reader with their own shares, and — in a browser where there is one — that the squares
take their shade and the card says what a square is.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import test_serve
from test_serve import Postbox, call, sign_in

from targum import catalogue, coverage
from targum.render import builder
from targum.render.builder import tanakh_map, tanakh_map_page
from targum.serve import Handler

KNOWN = 9

served = test_serve.served
postbox = test_serve.postbox


@pytest.fixture
def shelf(monkeypatch: pytest.MonkeyPatch) -> None:
    """A catalogue holding Genesis and Daniel in Hebrew, and Exodus only in Russian."""
    rows = [
        {"id": "genesis", "title": "בראשית", "language": "he", "source": "sefaria:Genesis"},
        {"id": "daniel", "title": "דניאל", "language": "he", "source": "sefaria:Daniel"},
        {"id": "exodus-ru", "title": "Исход", "language": "ru", "source": "sefaria:Exodus"},
    ]
    monkeypatch.setattr(catalogue, "CATALOGUE", [catalogue._entry(row) for row in rows])


def square(page: str, ref: str) -> str:
    found = re.search(rf'<(a|span) class="cell[^"]*"[^>]*data-ref="{ref}"[^>]*>', page)
    assert found, f"no square for {ref}"
    return found.group(0)


# -- the page ------------------------------------------------------------------------


def test_every_chapter_is_a_square_in_the_hebrew_order_and_count(shelf: None) -> None:
    page = tanakh_map_page("k")
    refs = re.findall(r'class="cell[^"]*"[^>]*data-ref="([^"]+)"', page)
    assert len(refs) == 929 and len(set(refs)) == 929
    assert refs[0] == "Genesis 1" and refs[-1] == "II Chronicles 36"
    assert refs.index("Malachi 3") < refs.index("Psalms 1"), "the Prophets before the Writings"

    parts = {part["part"]: [book["name"] for book in part["books"]] for part in tanakh_map()}
    assert list(parts) == ["torah", "prophets", "writings"]
    assert len(parts["torah"]) == 5
    # Samuel and Kings one book each, and the Twelve as twelve.
    assert parts["prophets"][:4] == ["Joshua", "Judges", "Samuel", "Kings"]
    assert len(parts["prophets"]) == 7 + 12
    assert parts["writings"][-2:] == ["Ezra–Nehemiah", "Chronicles"]
    assert len(parts["writings"]) == 11
    samuel = next(
        book for part in tanakh_map() for book in part["books"] if book["name"] == "Samuel"
    )
    assert [half["mark"] for half in samuel["halves"]] == ["I", "II"]
    assert samuel["hebrew"] == "שמואל"


def test_a_square_is_its_chapter_s_address(shelf: None) -> None:
    """The book's door with the chapter's first verse on it: the door opens the reader's
    copy, and its contents page sends `#12:1` on to the file that holds chapter 12."""
    page = tanakh_map_page("k")
    genesis = square(page, "Genesis 12")
    assert genesis.startswith("<a ") and 'href="/open/genesis#12:1"' in genesis
    assert 'aria-label="Genesis 12"' in genesis and 'data-verses="20"' in genesis


def test_a_book_the_library_lacks_is_unavailable_not_unknown(shelf: None) -> None:
    """Exodus is on this shelf only in Russian, which is not a Hebrew chapter to read."""
    page = tanakh_map_page("k")
    exodus = square(page, "Exodus 3")
    assert exodus.startswith("<span ") and "away" in exodus and "href" not in exodus
    assert "Not in the library yet" in page


def test_the_aramaic_chapters_are_marked_and_named(shelf: None) -> None:
    page = tanakh_map_page("k")
    assert "aramaic" in square(page, "Daniel 3") and 'data-language="arc"' in square(
        page, "Daniel 3"
    )
    assert "aramaic" not in square(page, "Daniel 1")
    assert "aramaic" in square(page, "Ezra 5") and "away" in square(page, "Ezra 5")
    assert "Aramaic, not measured yet" in page


def test_the_legend_counts_the_way_the_server_does() -> None:
    page = tanakh_map_page("k")
    assert f'data-steps="{" ".join(map(str, coverage.MAP_STEPS))}"' in page
    for turn in coverage.MAP_STEPS:
        assert f"{turn}%" in page
    assert [coverage.map_step(p) for p in (0, 49, 50, 74, 75, 89, 90, 94, 95, 100)] == [
        0, 0, 1, 1, 2, 2, 3, 3, 4, 4,
    ]  # fmt: skip
    assert coverage.map_percent(0.946) == 94, "rounded down, so a square never overstates"
    assert coverage.map_percent(1.2) == 100


def test_it_stands_under_your_progress_and_fetches_nothing_but_its_own_answer() -> None:
    page = tanakh_map_page("k")
    assert re.findall(r'data-nav="(\w+)"[^>]*aria-current="page"', page) == ["progress"]
    assert "<h1>The Tanakh</h1>" in page
    assert not re.search(r'(src|href)="https?://', page.split("<footer", 1)[0])


def test_it_speaks_russian() -> None:
    page = tanakh_map_page("k", language="ru")
    assert "<h1>Танах</h1>" in page and "Писания" in page
    assert '"tanakh.card.share"' in page, "the card's words ride to the script"


def test_your_progress_opens_the_map() -> None:
    from targum.render.builder import progress_page

    assert 'href="/tanakh-map"' in progress_page("k")


# -- the server ----------------------------------------------------------------------


def test_the_page_is_served_at_its_address(
    served: tuple[int, str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, token, _ = served
    monkeypatch.setattr(Handler, "tanakh", "<html>the map</html>")
    status, body, _ = call(port, "GET", f"/tanakh-map?k={token}")
    assert status == 200 and b"the map" in body


def test_signed_out_there_is_nothing_to_shade(served: tuple[int, str, Path]) -> None:
    port, token, _ = served
    status, said, _ = call(port, "GET", f"/tanakh-map.json?k={token}")
    assert status == 200 and said["signedIn"] is False and said["chapters"] == {}
    assert isinstance(said["portion"], str), 'the year strip\'s ink tick, or "" with no corpus'


def test_a_reader_is_answered_with_their_own_shares(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    port, token, _ = served
    cookie = sign_in(port, postbox)
    commonest = coverage.read_map().words["he"][:300]
    words = [
        {"language": "he", "lemma": lemma, "status": KNOWN, "at": 1, "seen": 1}
        for lemma in commonest
    ]
    status, answer, _ = call(port, "POST", f"/sync?k={token}", {"words": words}, cookie=cookie)
    assert status == 200 and answer["signedIn"], answer

    status, said, _ = call(port, "GET", f"/tanakh-map.json?k={token}", cookie=cookie)
    assert status == 200 and said["signedIn"] is True
    chapters: dict[str, Any] = said["chapters"]
    expected = coverage.chapter_map(set(commonest))
    assert chapters["Genesis 1"] == coverage.map_percent(expected["Genesis 1"] or 0)
    assert 40 < chapters["Genesis 1"] < 100
    assert "Daniel 3" not in chapters, "an Aramaic chapter is not measured, never 0%"
    assert len(chapters) == 929 - 10
    assert said["finished"] == [], "nothing read through yet"


def test_a_second_account_signed_out_is_turned_away(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """Once anybody has an account, signing out means what it means everywhere."""
    port, token, _ = served
    sign_in(port, postbox)
    status, said, _ = call(port, "GET", "/tanakh-map.json")
    assert status == 401 and "signIn" in said


def test_this_week_s_portion_is_its_chapters(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum.parasha import build as corpus

    portion = SimpleNamespace(summary="Genesis 12:1-17:27", books=["Genesis"])
    monkeypatch.setattr(corpus, "current", lambda *a, **k: portion)
    assert Handler._portion_chapters() == [f"Genesis {n}" for n in range(12, 18)]
    # Mid-chapter at both ends takes both chapters whole.
    portion.summary = "Genesis 6:9-11:32"
    assert Handler._portion_chapters()[0] == "Genesis 6"
    monkeypatch.setattr(corpus, "current", lambda *a, **k: None)
    assert Handler._portion_chapters() == []


# -- in a browser ----------------------------------------------------------------------


def _open(browser: Any, html: str, answer: dict[str, Any], **context: Any) -> Any:
    def route(handled: Any, request: Any) -> None:
        if "tanakh-map.json" in request.url:
            handled.fulfill(status=200, content_type="application/json", body=json.dumps(answer))
        elif request.url.endswith("/tanakh-map"):
            handled.fulfill(status=200, content_type="text/html", body=html)
        else:
            handled.fulfill(status=200, content_type="application/json", body="{}")

    opened = browser.new_context(**context)
    page = opened.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route("http://map.test/**", route)
    page.goto("http://map.test/tanakh-map")
    page.wait_for_timeout(300)
    page.thrown = thrown
    return opened, page


@pytest.fixture(scope="module")
def browser() -> Any:
    playwright_api = pytest.importorskip(
        "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
    )
    try:
        driver = playwright_api.sync_playwright().start()
    except Exception as why:  # pragma: no cover - environment, not behaviour
        pytest.skip(f"Playwright will not start: {why}")
    try:
        running = driver.chromium.launch()
    except Exception as why:  # pragma: no cover - the browser itself is not installed
        driver.stop()
        pytest.skip(f"no Chromium: run `playwright install chromium` ({why})")
    yield running
    running.close()
    driver.stop()


ANSWER = {
    "signedIn": True,
    "chapters": {"Genesis 1": 96, "Genesis 2": 91, "Genesis 3": 40, "Genesis 12": 77},
    "week": ["Genesis 12"],
}


def test_the_squares_take_their_shade_and_the_card_says_what_one_is(
    browser: Any, shelf: None
) -> None:
    opened, page = _open(
        browser, tanakh_map_page(""), ANSWER, viewport={"width": 1280, "height": 900}
    )
    step = "(ref) => document.querySelector(`[data-ref='${ref}']`).getAttribute('data-step')"
    assert page.evaluate(step, "Genesis 1") == "4"
    assert page.evaluate(step, "Genesis 2") == "3"
    assert page.evaluate(step, "Genesis 3") == "0"
    assert page.evaluate(step, "Genesis 4") is None, "not in the answer is not measured"
    assert page.evaluate(step, "Daniel 3") is None
    assert "week" in page.get_attribute("[data-ref='Genesis 12']", "class")
    assert page.inner_text("#tanakh-sum").startswith("2 chapters")

    page.hover("[data-ref='Genesis 12']")
    card = page.inner_text("#tanakh-card")
    assert "Genesis 12" in card and "20 verses" in card and "You know 77% of its words." in card
    assert page.get_attribute("#card-read", "href") == "/open/genesis#12:1"

    page.hover("[data-ref='Daniel 3']")
    assert "Aramaic" in page.inner_text("#tanakh-card")
    page.hover("[data-ref='Exodus 3']")
    assert "Not in the library yet." in page.inner_text("#tanakh-card")
    assert page.is_hidden("#card-read")
    assert not page.thrown
    opened.close()


def test_a_chapter_read_through_is_solid_leaf_and_its_card_says_so(
    browser: Any, shelf: None
) -> None:
    """targum-internal#144: finished chapters are solid leaf, whatever share of their
    words is known, and a book the library lacks never is."""
    answer = {**ANSWER, "finished": ["Genesis 3", "Exodus 3"]}
    opened, page = _open(
        browser, tanakh_map_page(""), answer, viewport={"width": 1280, "height": 900}
    )
    classes = "(ref) => document.querySelector(`[data-ref='${ref}']`).className"
    assert "read" in page.evaluate(classes, "Genesis 3").split()
    assert "read" not in page.evaluate(classes, "Genesis 1").split()
    assert "read" not in page.evaluate(classes, "Exodus 3").split(), "not in the library"
    fill = (
        "(ref) => getComputedStyle(document.querySelector(`[data-ref='${ref}']`)).backgroundColor"
    )
    legend = page.evaluate(
        "getComputedStyle(document.querySelector('.tanakh-legend .cell.read')).backgroundColor"
    )
    assert page.evaluate(fill, "Genesis 3") == legend, "the legend's swatch is the square"
    page.hover("[data-ref='Genesis 3']")
    assert "You've read it" in page.inner_text("#tanakh-card")
    assert not page.thrown
    opened.close()


YEAR = [
    {
        "slug": "bereshit",
        "name": "Bereshit",
        "hebrew": "בראשית",
        "chapters": [f"Genesis {n}" for n in range(1, 7)],
        "href": "/library/parasha-bereshit",
    },
    {
        "slug": "noach",
        "name": "Noach",
        "hebrew": "נח",
        "chapters": [f"Genesis {n}" for n in range(6, 12)],
        "href": "/library/parasha-noach",
    },
    {
        "slug": "lech-lecha",
        "name": "Lech-Lecha",
        "hebrew": "לך לך",
        "chapters": [f"Genesis {n}" for n in range(12, 18)],
        "href": "/library/parasha-lech-lecha",
    },
]


def test_chapters_of_a_portion_take_whole_chapters() -> None:
    """Chapter-level, as #144 says: Noach starts at 6:9 and still takes chapter 6."""
    from targum.parasha.build import chapters_of
    from targum.parasha.models import Portion

    noach = Portion(
        slug="noach", name="Noach", hebrew="נח", summary="Genesis 6:9-11:32", books=["Genesis"]
    )
    assert chapters_of(noach) == [f"Genesis {n}" for n in range(6, 12)]
    assert chapters_of(Portion(slug="x", name="X", hebrew="", summary="", books=[])) == []


def test_the_year_strip_is_a_link_a_portion_in_the_order_they_are_read(
    shelf: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(builder, "tanakh_year", lambda: YEAR)
    page = tanakh_map_page("")
    ticks = re.findall(r'<a class="year-tick" href="([^"]+)" data-slug="([^"]+)"', page)
    assert ticks == [(one["href"], one["slug"]) for one in YEAR]
    assert 'aria-label="Noach, Genesis 6–11"' in page
    monkeypatch.setattr(builder, "tanakh_year", lambda: [])
    assert '<a class="year-tick"' not in tanakh_map_page(""), "no corpus, no strip"


def test_the_year_and_the_map_light_each_other(
    browser: Any, shelf: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(builder, "tanakh_year", lambda: YEAR)
    answer = {**ANSWER, "portion": "lech-lecha"}
    opened, page = _open(
        browser, tanakh_map_page(""), answer, viewport={"width": 390, "height": 844}
    )
    widths = page.evaluate(
        "[...document.querySelectorAll('.year-item')].map((li) => li.getBoundingClientRect().width)"
    )
    assert len(widths) == 3 and abs(widths[0] - widths[1]) < 2, widths
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    week = page.evaluate(
        "[...document.querySelectorAll('.year-tick.week')].map((t) => t.dataset.slug)"
    )
    assert week == ["lech-lecha"], "this week's tick is the one the server named"

    lit = "() => [...document.querySelectorAll('.cell.lit')].map((c) => c.dataset.ref)"
    page.hover(".year-tick[data-slug='noach']")
    assert page.evaluate(lit) == [f"Genesis {n}" for n in range(6, 12)]
    assert "Noach" in page.inner_text("#year-said")
    page.focus("[data-ref='Genesis 12']")
    assert page.evaluate("document.querySelector('.year-tick.lit').dataset.slug") == "lech-lecha"
    assert not page.thrown
    opened.close()


def test_the_keyboard_walks_the_map_from_one_stop(browser: Any, shelf: None) -> None:
    opened, page = _open(
        browser, tanakh_map_page(""), ANSWER, viewport={"width": 1280, "height": 900}
    )
    stops = page.evaluate("document.querySelectorAll('#tanakh-map [tabindex=\"0\"]').length")
    assert stops == 1
    page.focus("[data-ref='Genesis 1']")
    page.keyboard.press("ArrowDown")
    assert page.evaluate("document.activeElement.getAttribute('data-ref')") == "Genesis 11"
    page.keyboard.press("ArrowRight")
    assert page.evaluate("document.activeElement.getAttribute('data-ref')") == "Genesis 12"
    assert "Genesis 12" in page.inner_text("#tanakh-card")
    opened.close()


def test_on_a_phone_a_tap_shows_the_card_and_read_is_the_press(browser: Any, shelf: None) -> None:
    opened, page = _open(
        browser,
        tanakh_map_page(""),
        ANSWER,
        viewport={"width": 390, "height": 844},
        has_touch=True,
        is_mobile=True,
    )
    page.tap("[data-ref='Genesis 2']")
    page.wait_for_timeout(100)
    assert page.url == "http://map.test/tanakh-map", "the tap did not leave the map"
    assert "Genesis 2" in page.inner_text("#tanakh-card")
    reach = page.evaluate("document.getElementById('card-read').getBoundingClientRect().height")
    assert reach >= 44
    assert page.evaluate("document.documentElement.scrollWidth") <= 390
    opened.close()
