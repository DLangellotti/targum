"""Your targums' tabs, sifting and series, in a real browser (design.md §12, "Your targums
has tabs, says what a targum is, and folds a series", 2026-09-26).

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from targum.render.builder import list_page, playlists_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)


def _text(name: str, title: str, **extra: object) -> dict:
    return {
        "name": name,
        "document": name,
        "title": title,
        "language": "he",
        "entry": "",
        "built": int(time.time()) - 3600,
        "minutes": 3,
        "seconds": 0,
        "sections": 1,
        "chapters": [],
        **extra,
    }


#: Three episodes of one series, a text brought by hand, a Library text built, and a
#: shared one opened: seven rows, enough for the sifting to be drawn.
MINE = [
    _text("e63", "עברית אנפלאגד - פרק 63 | שחושבת"),
    _text("e61", "עברית אנפלאגד - פרק 61 | תינוקות"),
    _text("e60", "עברית אנפלאגד - פרק 60 | לעגל פינות"),
    _text("own", "כתבה שהבאתי", english="An article I brought"),
    _text("own2", "עוד כתבה", english="Another article"),
    _text("lib", "משנה ברכות", english="Mishnah Berakhot", entry="mishnah-berakhot-1"),
]
SHARED = [_text("shared", "במעלית", english="In the elevator", entry="d-elev")]
DOCS = {"e61": {"done": True}, "e60": {"done": True}}
OPENED = {"shared": 1000}


@pytest.fixture(scope="module")
def browser():
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


def shelf(browser, tmp_path: Path, width: int = 1280, html: str | None = None):
    page_file = tmp_path / "texts.html"
    page_file.write_text(html or list_page("test-key", "texts"), encoding="utf-8")
    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.add_init_script(
        f"localStorage.setItem('targum:docs', {json.dumps(json.dumps(DOCS))});"
        f"localStorage.setItem('targum:opened', {json.dumps(json.dumps(OPENED))});"
        f"const said = {json.dumps({'readers': MINE, 'shared': SHARED, 'trash': []})};"
        "window.fetch = (url) => Promise.resolve(new Response(JSON.stringify("
        "  String(url).split('?')[0].endsWith('/readers') ? said : {})));"
    )
    page.goto(page_file.as_uri())
    if html is None:
        page.wait_for_selector("#library-list li")
    return context, page, thrown


def titles(page) -> list[str]:
    return [one.strip() for one in page.locator("#library-list .book-title").all_inner_texts()]


def test_a_series_is_one_row_until_it_is_opened(browser, tmp_path: Path) -> None:
    context, page, thrown = shelf(browser, tmp_path)
    folded = titles(page)
    facts = page.locator("#library-list li.is-series .book-facts").inner_text()
    status = page.locator("#library-list li.is-series .row-status").inner_text()
    page.click("#library-list .series-open")
    opened = titles(page)
    named = page.locator("#series-name").inner_text()
    page.click("#series-back")
    back = titles(page)
    context.close()
    assert folded.count("עברית אנפלאגד") == 1 and len(folded) == 5
    assert "3 episodes" in facts and status.strip() == "2 of 3"
    assert named == "עברית אנפלאגד"
    # In episode order, and without the series' name said again on every row.
    assert opened == ["פרק 60 | לעגל פינות", "פרק 61 | תינוקות", "פרק 63 | שחושבת"]
    assert back == folded
    assert not thrown


def test_your_uploads_is_only_what_you_brought(browser, tmp_path: Path) -> None:
    context, page, thrown = shelf(browser, tmp_path)
    page.click("#yours-tabs [data-tab='uploads']")
    uploads = titles(page)
    current = page.get_attribute("#yours-tabs [aria-current='page']", "data-tab")
    address = page.evaluate("() => location.search")
    context.close()
    assert "משנה ברכות" not in uploads, "a Library text you built is not an upload"
    assert "במעלית" not in uploads, "a shared text you opened is not an upload"
    assert "כתבה שהבאתי" in uploads and "עברית אנפלאגד" in uploads
    assert current == "uploads" and "show=uploads" in address
    assert not thrown


def test_all_targums_holds_the_shared_text_you_opened(browser, tmp_path: Path) -> None:
    context, page, _ = shelf(browser, tmp_path)
    everything = titles(page)
    context.close()
    assert "במעלית" in everything and "משנה ברכות" in everything


def test_a_chip_and_a_search_sift_the_shelf(browser, tmp_path: Path) -> None:
    context, page, thrown = shelf(browser, tmp_path)
    chips = page.locator("#status-chips .chip").all_inner_texts()
    page.locator("#status-chips .chip", has_text="Finished").click()
    finished = titles(page)
    page.locator("#status-chips .chip", has_text="Finished").click()
    page.fill("#shelf-find", "brought")
    found = titles(page)
    page.fill("#shelf-find", "zzz")
    nothing = page.locator("#shelf-note").inner_text()
    context.close()
    assert [" ".join(chip.split()) for chip in chips] == [
        "All 7",
        "New 4",
        "Reading 1",
        "Finished 2",
    ]
    # Two finished episodes of one series are still that series, folded.
    assert finished == ["עברית אנפלאגד"]
    assert found == ["כתבה שהבאתי"], "the English under a title is searched too"
    assert nothing == "Nothing here matches that."
    assert not thrown


def test_a_short_shelf_is_not_handed_controls(browser, tmp_path: Path) -> None:
    context, page, _ = shelf(browser, tmp_path)
    page.click("#yours-tabs [data-tab='uploads']")
    hidden = page.locator("#sift-shelf").is_hidden()
    context.close()
    assert hidden, "five uploads is a shelf that needs no sifting"


def test_the_page_says_what_a_targum_is_by_showing_one(browser, tmp_path: Path) -> None:
    context, page, _ = shelf(browser, tmp_path)
    line = page.locator(".defined-line").inner_text()
    under = page.locator(".defined-under").inner_text()
    context.close()
    assert "הַשֻּׁלְחָן" in line and under == "The book is on the table"


def test_the_desk_draws_cards_and_a_phone_draws_rows(browser, tmp_path: Path) -> None:
    widths = {}
    for width in (1280, 390):
        context, page, _ = shelf(browser, tmp_path, width)
        widths[width] = page.eval_on_selector_all(
            "#library-list > li", "all => all.map(li => li.getBoundingClientRect().width)"
        )
        scroll = page.evaluate("() => document.documentElement.scrollWidth")
        context.close()
        assert scroll <= width, "the page never scrolls sideways"
    assert max(widths[1280]) < 1280 / 2, "at a desk several cards share a line"
    assert min(widths[390]) > 390 * 0.8, "on a phone each text is a row"


def test_playlists_wears_the_same_tabs_and_lights_your_targums(browser, tmp_path: Path) -> None:
    context, page, _ = shelf(browser, tmp_path, html=playlists_page("test-key"))
    tabs = page.eval_on_selector_all("#yours-tabs .tab", "all => all.map(a => a.dataset.tab)")
    current = page.get_attribute("#yours-tabs [aria-current='page']", "data-tab")
    here = page.get_attribute(".site-nav a[aria-current='page']", "data-nav")
    context.close()
    assert tabs == ["all", "uploads", "playlists"]
    assert current == "playlists" and here == "texts"
