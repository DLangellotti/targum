"""The words check in a real browser (design.md §12, "The arrival asks which words you
know", 2026-11-01; targum-internal#613): by keyboard, as a screen reader is told it, and
at a phone's width and a desk's.

`TARGUM_SHOTS=<dir>` keeps a picture of each round at 390 and 1440 for review.

Skips itself without Playwright and its Chromium, as the other browser tests do.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from targum import check
from targum.render.builder import welcome_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

TOKEN = "test-key"
SITE = "http://check.test"


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


def shelf() -> list[dict[str, Any]]:
    return [
        {
            "name": "news-1",
            "title": "חדשות",
            "language": "he",
            "document": "news-1",
            "entry": "",
            "chapters": [],
            "kind": "article",
            "register": "modern",
            "difficulty": 10,
            "tags": ["journalism"],
            "level": {"name": "bet"},
        }
    ]


def arrive(browser, width: int, phone: bool = False):
    html = welcome_page(TOKEN)
    sent: list[dict[str, Any]] = []
    went: list[str] = []

    def answer(route, request):
        path = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            if path != "/welcome":
                went.append(path)
                return route.fulfill(status=200, content_type="text/html", body="<p>away</p>")
            return route.fulfill(status=200, content_type="text/html", body=html)
        body: dict[str, Any] = {}
        if path == "/account/me":
            body = {"signedIn": True, "readsSaid": True, "learning": ["he"], "reads": ["en"]}
        elif path == "/readers":
            body = {"readers": [], "shared": shelf(), "trash": [], "covers": False}
        elif path == "/account/check":
            sent.append(json.loads(request.post_data or "{}"))
            body = {"signedIn": True, "rung": "bet"}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    extra = {"is_mobile": True, "has_touch": True} if phone else {}
    context = browser.new_context(
        viewport={"width": width, "height": 844 if phone else 900},
        reduced_motion="reduce",
        color_scheme="light",
        **extra,
    )
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    page.goto(f"{SITE}/welcome?k={TOKEN}")
    page.wait_for_selector("#arrival:not([hidden])")
    # Hebrew is pressed; one subject; a level.
    page.click("#arrival-done")
    page.click("#arrival-doors .arrival-door >> nth=1")
    page.click("#arrival-done")
    page.click("#arrival-levels .arrival-rung >> nth=1")
    page.click("#arrival-done")
    page.wait_for_selector("#arrival-check:not([hidden])")
    return context, page, sent, went, thrown


def shoot(page, name: str) -> None:
    where = os.environ.get("TARGUM_SHOTS")
    if where:
        Path(where).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(where) / f"{name}.png"), full_page=True)


def pressed(page) -> list[str]:
    return page.eval_on_selector_all(
        "#arrival-words .arrival-word[aria-pressed='true']", "els => els.map(e => e.textContent)"
    )


@pytest.mark.parametrize("width", [390, 1440])
def test_the_check_by_keyboard_and_as_a_screen_reader_hears_it(browser, width: int) -> None:
    """Focus lands on the first word; each word is a toggle a screen reader calls pressed
    or not, in Hebrew, in a list named by the question; Tab walks them, Space and Enter
    press them; Next and Done are reached the same way; the thanks takes the focus."""
    context, page, sent, went, thrown = arrive(browser, width, phone=width < 600)
    shoot(page, f"check-round-1-{width}")
    words = page.locator("#arrival-words .arrival-word")
    assert words.count() == 22
    first = words.nth(0)
    assert page.evaluate("document.activeElement.className") == "arrival-word"
    assert first.get_attribute("aria-pressed") == "false"
    listed = page.locator("#arrival-words")
    assert listed.get_attribute("lang") == "he" and listed.get_attribute("dir") == "rtl"
    assert listed.get_attribute("aria-labelledby") == "arrival-asks-check"
    assert page.evaluate("document.activeElement.tagName") == "BUTTON"

    page.keyboard.press("Space")
    said = page.evaluate("document.activeElement.textContent")
    page.keyboard.press("Tab")
    page.keyboard.press("Enter")
    second = page.evaluate("document.activeElement.textContent")
    assert sorted(pressed(page)) == sorted([said, second])
    if width >= 600:
        assert page.inner_text("#arrival-tapped") == "2 tapped"
    shoot(page, f"check-round-1-tapped-{width}")

    # Nothing sits across the page: no sideways scroll, and on a phone the last word
    # clears the fixed foot once scrolled to.
    assert page.evaluate("document.scrollingElement.scrollWidth") <= width
    last = words.nth(21)
    last.scroll_into_view_if_needed()
    page.evaluate("window.scrollTo(0, document.scrollingElement.scrollHeight)")
    if width < 600:
        foot_top = page.evaluate("document.querySelector('.arrival-foot').getBoundingClientRect().top")
        assert last.bounding_box()["y"] + last.bounding_box()["height"] <= foot_top
    # Every word and both presses reach 44px.
    for selector in ("#arrival-words .arrival-word", "#arrival-skip", "#arrival-done"):
        box = page.locator(selector).first.bounding_box()
        assert box and box["height"] >= 44, selector

    page.focus("#arrival-done")
    assert page.inner_text("#arrival-done") == "Next"
    page.keyboard.press("Enter")
    page.wait_for_function("document.getElementById('arrival-done').textContent === 'Done'")
    assert page.locator("#arrival-words .arrival-word").count() == 19
    assert page.evaluate("document.activeElement.className") == "arrival-word"
    shoot(page, f"check-round-2-{width}")
    page.focus("#arrival-done")
    page.keyboard.press("Enter")
    page.wait_for_selector("#arrival-thanks:not([hidden])")
    assert page.evaluate("document.activeElement.id") == "arrival-asks-thanks"
    assert page.is_hidden("#arrival-skip") and page.is_hidden("#arrival-check")
    shoot(page, f"check-thanks-{width}")
    assert sent and sent[0]["version"] == check.VERSION
    assert sorted(sent[0]["ticked"]) == sorted([said, second])
    page.click("#arrival-done")
    page.wait_for_function("location.pathname.indexOf('/reader/') === 0")
    context.close()
    assert not thrown, thrown


def test_skip_goes_home_and_sends_nothing(browser) -> None:
    context, page, sent, went, thrown = arrive(browser, 390, phone=True)
    page.locator("#arrival-words .arrival-word").nth(0).click()
    page.click("#arrival-skip")
    page.wait_for_function("location.pathname === '/'")
    assert not sent
    context.close()
    assert not thrown, thrown
