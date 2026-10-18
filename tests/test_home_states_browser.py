"""Home's states, in a real browser (design.md §14, line 8; home QA, 2026-10-18,
targum-internal#463).

Each state the QA drew at desk and phone width is pinned here, so the next change cannot
quietly undo it: the wait said again past three seconds, a refusal and a dropped
connection each said in words with the press that asks again, offline said as offline,
a text read on another device shown as started, a subscription's Hebrew name isolated in
its tag, a long shelf kept short and nothing scrolling sideways at 390.

The page is the one the server renders (`list_page`); the account's answers are routes.
Skips itself without Playwright and its Chromium, as the other browser tests do.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest

from targum.render.builder import list_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://home.test"
HASH = "a" * 64


def reader_row(n: int = 0, chapters: int = 3, document: str = "") -> dict[str, Any]:
    return {
        "name": f"text-{n}-he",
        "document": document or f"{n:064d}",
        "title": f"ספר {n}",
        "language": "he",
        "register": "modern",
        "kind": "book",
        "sections": chapters,
        "chapters": [
            {"number": c, "title": f"פרק {c}", "file": f"sec-{c:04d}.html", "ready": True}
            for c in range(1, chapters + 1)
        ],
        "readyChapters": chapters,
        "built": 1_700_000_000 + n,
        "drawn": False,
        "words": 100,
        "known": 0,
        "entry": "",
    }


ME = {
    "signedIn": True,
    "email": "r@x.test",
    "initials": "R",
    "readsSaid": True,
    "reads": ["en"],
    "language": "he",
    "learning": ["he"],
    "interest": ["news"],
}


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


def home(browser, answers: dict[str, Any], *, phone: bool = False, offline: bool = False):
    """Home, with `answers` by path: a dict or list is JSON, an int a bare status, the
    string "abort" a dropped connection and "hold" an answer that never comes."""
    html = list_page("", "texts")
    held: list = []
    documents: list[str] = []

    def answer(route, request):
        path = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            documents.append(path)
            return route.fulfill(status=200, content_type="text/html", body=html)
        said = answers.get(path, {"signedIn": True} if path != "/account/me" else ME)
        if said == "abort":
            return route.abort("internetdisconnected")
        if said == "hold":
            return held.append(route)
        if isinstance(said, int):
            return route.fulfill(status=said, content_type="application/json", body="{}")
        route.fulfill(status=200, content_type="application/json", body=json.dumps(said))

    size = {"width": 390, "height": 844} if phone else {"width": 1440, "height": 900}
    extra = {"is_mobile": True, "has_touch": True} if phone else {}
    context = browser.new_context(viewport=size, reduced_motion="reduce", **extra)
    unplugged = "Object.defineProperty(Navigator.prototype, 'onLine', {get: () => false});"
    context.add_init_script(
        "localStorage.setItem('targum:welcomed', '1');"
        "localStorage.setItem('targum:language', 'he');" + (unplugged if offline else "")
    )
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    return context, page, thrown, held, documents


def test_a_slow_shelf_is_said_again_after_three_seconds(browser) -> None:
    context, page, thrown, held, _ = home(browser, {"/readers": "hold"})
    page.clock.install()
    page.goto(SITE + "/")
    page.clock.run_for(1000)
    assert page.inner_text("#home-waiting") == "Opening your texts…"
    page.clock.run_for(2500)
    assert page.inner_text("#home-waiting") == "We're still opening your texts."
    context.close()
    assert not thrown, thrown


def test_a_refusal_is_not_an_empty_shelf(browser) -> None:
    """A 500 whose body was JSON drew "Nothing here yet" over a reader's six texts."""
    context, page, thrown, _, documents = home(browser, {"/readers": 500})
    page.goto(SITE + "/")
    page.wait_for_selector("#nothing:not([hidden])")
    assert page.inner_text("#nothing-lede") == "We couldn't load your texts."
    assert "Everything you've read is still here." in page.inner_text("#nothing-says")
    assert page.is_hidden("#first-home") and page.is_hidden("#page")
    assert page.is_visible("#nothing-again")
    page.click("#nothing-again")
    page.wait_for_function("() => true")
    page.wait_for_timeout(300)
    assert len(documents) == 2, "Try again asks for the page again"
    context.close()


def test_no_answer_at_all_is_ours_to_own(browser) -> None:
    context, page, thrown, _, _ = home(browser, {"/readers": "abort"})
    page.goto(SITE + "/")
    page.wait_for_selector("#nothing:not([hidden])")
    assert page.inner_text("#nothing-lede") == "We can't reach targum right now."
    assert page.is_visible("#nothing-again")
    context.close()


def test_offline_says_offline_and_leaves_the_press_to_the_banner(browser) -> None:
    context, page, thrown, _, _ = home(
        browser, {"/readers": "abort", "/jobs": "abort", "/account/places": "abort"}, offline=True
    )
    page.goto(SITE + "/")
    page.wait_for_selector("#nothing:not([hidden])")
    assert page.inner_text("#nothing-lede") == "You're offline."
    assert "when you're back online" in page.inner_text("#nothing-says")
    assert page.is_hidden("#nothing-again"), "the bar's banner carries the one Try again"
    context.close()


def test_a_text_read_on_another_device_is_started_here(browser) -> None:
    """Continue said "Pick up at chapter 2" from the account's place while the row under
    it said New: "opened" was only ever this browser's record."""
    book = reader_row(1, chapters=3, document=HASH)
    place = {
        "hash": HASH,
        "section": "2",
        "path": "/reader/text-1-he/reader/sec-0002.html",
        "segment": "",
        "seconds": 0,
        # An hour ago: a week away would take it out of Continue for welcome back.
        "at": int(time.time() * 1000) - 3_600_000,
    }
    answers = {
        "/readers": {"readers": [book, reader_row(2)], "shared": [], "trash": []},
        "/account/places": {"signedIn": True, "places": [place]},
    }
    context, page, thrown, _, _ = home(browser, answers)
    page.goto(SITE + "/")
    page.wait_for_selector("#continue:not([hidden]) .home-card")
    assert "Pick up at chapter 2" in page.inner_text("#continue")
    rows = page.locator("#library-list > li")
    page.wait_for_function("() => document.querySelectorAll('#library-list > li').length === 2")
    first = rows.nth(0).inner_text()
    assert "ספר 1" in first and "Started" in first and "New" not in first
    assert "New" in rows.nth(1).inner_text(), "a text read nowhere is still New"
    context.close()
    assert not thrown, thrown


def test_a_subscriptions_hebrew_name_stands_in_its_own_isolate(browser) -> None:
    item = {
        "subscription": 3,
        "key": "v1",
        "title": "הכותל המערבי",
        "kind": "channel",
        "name": "כאן ארכיון",
        "topic": "",
        "language": "he",
        "door": "/add?source=x",
        "seconds": 412,
        "published": 1,
        "found": 1,
    }
    answers = {
        "/readers": {"readers": [reader_row(1)], "shared": [], "trash": []},
        "/subscriptions/new.json": {"signedIn": True, "items": [item]},
    }
    context, page, thrown, _, _ = home(browser, answers)
    page.goto(SITE + "/")
    page.wait_for_selector(".home-card.is-new")
    tag = page.locator(".home-card.is-new .home-tag")
    # A flex pill: its parts are items, so the text comes back on two lines.
    assert " ".join(tag.inner_text().split()) == "New · כאן ארכיון"
    assert tag.locator("bdi[dir=auto][lang=he]").inner_text() == "כאן ארכיון"
    assert page.locator(".home-card.is-new .glyph").first.get_attribute("dir") == "auto"
    assert "Watch" in page.inner_text(".home-card.is-new")
    context.close()
    assert not thrown, thrown


def test_a_reader_with_five_hundred_texts_sees_a_short_shelf_on_a_phone(browser) -> None:
    many = [reader_row(n, chapters=1) for n in range(500)]
    answers = {"/readers": {"readers": many, "shared": [], "trash": []}}
    context, page, thrown, _, _ = home(browser, answers, phone=True)
    page.goto(SITE + "/")
    page.wait_for_selector("#page:not([hidden])", timeout=30000)
    page.wait_for_selector("#shelf-more-rows:not([hidden])")
    assert page.locator("#library-list > li").count() == 8
    assert page.is_visible("#shelf-find")
    sideways = page.evaluate(
        "document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth"
    )
    assert sideways == 0
    page.click("#shelf-more-rows")
    assert page.locator("#library-list > li").count() == 500
    context.close()
    assert not thrown, thrown


def test_nothing_yet_says_what_will_appear(browser) -> None:
    answers = {"/readers": {"readers": [], "shared": [], "trash": []}}
    context, page, thrown, _, _ = home(browser, answers, phone=True)
    page.goto(SITE + "/")
    page.wait_for_selector("#first-home:not([hidden])")
    assert page.inner_text("#first-home") == (
        "Nothing here yet. What you open or upload appears here."
    )
    assert page.is_hidden("#shelf-panel") and page.is_visible(".upload-card")
    context.close()
    assert not thrown, thrown


def test_a_first_sync_draws_home_again_in_place_rather_than_reloading(browser) -> None:
    """On a browser that had never synced, home reloaded the whole page once `/sync`
    came back, and with a big shelf a first visit took about five seconds (2026-10-18).
    The answer is drawn in place: a shared text opened on another device joins the shelf
    as Started, Continue picks it up, and the page is loaded once."""
    shared = reader_row(1, chapters=3, document=HASH)
    now = int(time.time() * 1000)
    answers = {
        "/readers": {"readers": [reader_row(2)], "shared": [shared], "trash": []},
        "/sync": "hold",
    }
    context, page, thrown, held, documents = home(browser, answers)
    page.goto(SITE + "/")
    page.wait_for_function("() => document.querySelectorAll('#library-list > li').length === 1")
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(100)
    assert held, "home asks the account for its record"
    page.evaluate("() => { window.__drawn = document.getElementById('page'); }")
    record = {
        "signedIn": True,
        "revision": 1,
        "docs": [{"hash": HASH, "title": "ספר 1", "language": "he", "updated": 1, "opened": now}],
        "places": [
            {
                "hash": HASH,
                "section": "2",
                "path": "/reader/text-1-he/reader/sec-0002.html",
                "segment": "",
                "seconds": 0,
                "at": now - 3_600_000,
            }
        ],
    }
    held[0].fulfill(status=200, content_type="application/json", body=json.dumps(record))
    page.wait_for_function("() => document.querySelectorAll('#library-list > li').length === 2")
    page.wait_for_selector("#continue:not([hidden]) .home-card")
    assert "Pick up at chapter 2" in page.inner_text("#continue")
    first = page.locator("#library-list > li").nth(0).inner_text()
    assert "ספר 1" in first and "Started" in first
    page.wait_for_timeout(300)
    assert documents == ["/"], "the page is loaded once"
    assert page.evaluate("() => window.__drawn === document.getElementById('page')"), (
        "the same page, drawn again"
    )
    context.close()
    assert not thrown, thrown
