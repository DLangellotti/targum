"""/after-duolingo-hebrew in a browser: the front page's `landing.js`, run without its film
(targum-internal#676; David, 2026-11-12: "tapping any word in the Shoelace Seller reader
opens it in the word card; the vowel card's switch really toggles; לבית־הספר splits when
tapped").

The front page's own behaviour is `test_landing_browser.py`'s, unchanged. Skips itself
unless Playwright and its Chromium are installed:

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any
from urllib.parse import urlparse

import pytest

from targum.render.builder import after_duolingo_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)


@pytest.fixture(scope="module")
def browser() -> Iterator[Any]:
    """One Chromium for the file."""
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


def opened(browser: Any, motion: str = "reduce") -> tuple[Any, Any, list[str]]:
    html = after_duolingo_page("https://targum.page")

    def answer(route: Any, request: Any) -> None:
        if urlparse(request.url).path == "/after-duolingo-hebrew":
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion=motion)
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route("http://door.test/**", answer)
    page.goto("http://door.test/after-duolingo-hebrew")
    page.wait_for_selector("#story.live")
    return context, page, thrown


def test_every_word_tapped_opens_in_the_card(browser: Any) -> None:
    context, page, thrown = opened(browser)
    held = json.loads(page.eval_on_selector("#landingWords", "(e) => e.textContent"))["words"]
    ids = page.eval_on_selector_all("#storyLines .w", "(ws) => ws.map((w) => w.dataset.id)")
    assert len(ids) == 22
    for word_id in ids:
        page.click(f'#storyLines .w[data-id="{word_id}"]')
        head = page.eval_on_selector("#card .card-word", "(e) => e.textContent")
        assert head == held[word_id]["head"], word_id
        assert page.eval_on_selector_all(".w.open", "(ws) => ws.map((w) => w.dataset.id)") == [
            word_id
        ]
    # The card keeps no list here, so it offers nothing to press.
    assert page.locator("#card button").count() == 0
    # And every Hebrew run the card drew says it is Hebrew (§14).
    loose = page.evaluate(
        """() => [...document.querySelectorAll('#card *')].filter((e) =>
          /[\\u0590-\\u05FF]/.test([...e.childNodes].filter((n) => n.nodeType === 3)
            .map((n) => n.data).join('')) && !e.closest('[lang=he][dir=rtl]'))
          .map((e) => e.outerHTML)"""
    )
    context.close()
    assert not loose, loose
    assert not thrown, thrown


def test_the_keyboard_reaches_every_word(browser: Any) -> None:
    context, page, thrown = opened(browser)
    page.focus('#storyLines .w[data-id="l3w4"]')
    page.keyboard.press("ArrowLeft")
    page.keyboard.press("Enter")
    head = page.eval_on_selector("#card .card-word", "(e) => e.textContent")
    context.close()
    assert head == "הַסֵּפֶר"
    assert not thrown, thrown


def test_the_vowel_switch_switches(browser: Any) -> None:
    context, page, thrown = opened(browser)
    switch = page.locator("#swVowels")
    assert switch.is_visible()
    label = page.locator(".vowels-vis .vs-as .label")
    assert switch.get_attribute("aria-checked") == "false"
    assert "bare-only" in (page.get_attribute("#vsRecipe", "class") or "")
    assert label.text_content() == "As written"
    switch.click()
    assert switch.get_attribute("aria-checked") == "true"
    assert "bare-only" not in (page.get_attribute("#vsRecipe", "class") or "")
    assert label.text_content() == "With vowels"
    # One line now, and its letters are the line's own, spaces and question mark kept.
    assert page.locator(".vowels-vis .vs-with").is_hidden()
    pointed = page.eval_on_selector(
        "#vsRecipe",
        "(e) => [...e.childNodes].map((n) => n.nodeType === 3 ? n.data : "
        "n.querySelector('.pointed').textContent).join('')",
    )
    switch.click()
    context.close()
    assert pointed == "מַדּוּעַ אֵינְךָ הוֹלֵךְ לְבֵית־הַסֵּפֶר?"
    assert not thrown, thrown


def test_the_glued_word_comes_apart_on_a_tap(browser: Any) -> None:
    context, page, thrown = opened(browser)
    glued = page.locator(".glued-vis")
    # With reduced motion it starts apart, as the still picture is drawn.
    assert glued.get_attribute("role") == "button"
    assert glued.get_attribute("aria-pressed") == "true"
    glued.click()
    assert glued.get_attribute("aria-pressed") == "false"
    glued.focus()
    page.keyboard.press("Enter")
    assert glued.get_attribute("aria-pressed") == "true"
    context.close()
    assert not thrown, thrown


def test_with_motion_the_glued_word_opens_once_it_is_seen(browser: Any) -> None:
    context, page, thrown = opened(browser, motion="no-preference")
    glued = page.locator(".glued-vis")
    assert glued.get_attribute("aria-pressed") == "false"
    glued.scroll_into_view_if_needed()
    page.wait_for_function(
        "() => document.querySelector('.glued-vis').getAttribute('aria-pressed') === 'true'",
        timeout=5000,
    )
    context.close()
    assert not thrown, thrown


def test_nothing_the_front_page_s_film_needs_is_asked_for(browser: Any) -> None:
    """The film's parts wait for a film: no fault on a page without one."""
    context, page, thrown = opened(browser, motion="no-preference")
    page.mouse.wheel(0, 3000)
    page.wait_for_timeout(300)
    has_top_live = page.evaluate("() => document.querySelector('.top').classList.contains('live')")
    context.close()
    assert not has_top_live
    assert not thrown, thrown
    assert not [line for line in thrown if re.search("null", line)]


def test_the_clip_has_one_key_and_no_browser_controls(browser: Any) -> None:
    """With the script, the clip's one key stands in for the browser's controls; under
    reduced motion nothing plays by itself (Playwright's Chromium cannot decode H.264, so
    playing is the real browsers' to show, and the key's label is what is checked)."""
    context, page, thrown = opened(browser)
    assert page.eval_on_selector("#clipFilm", "(v) => v.hasAttribute('controls')") is False
    key = page.locator(".clip-play")
    assert key.is_visible()
    assert key.get_attribute("aria-label") == "Play"
    assert page.eval_on_selector("#clipFilm", "(v) => v.paused") is True
    # The first line is the one being said before anything plays, as drawn.
    assert page.locator(".clip-lines .pair.now").count() == 1
    context.close()
    assert not thrown, thrown
