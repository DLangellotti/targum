"""Home's welcome back, in a real browser (design.md §12, "Home says welcome back after a
week away", 2026-10-09; boards WelcomeBackDesk and WelcomeBackPhone).

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from targum.render.builder import list_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

DAY_MS = 24 * 60 * 60 * 1000


def _text(name: str, title: str, **extra: object) -> dict:
    return {
        "name": name,
        "document": name,
        "title": title,
        "language": "he",
        "entry": "",
        "built": int(time.time()) - 30 * 86400,
        "minutes": 3,
        "seconds": 0,
        "sections": 4,
        "chapters": [],
        "known": 0.72,
        "words": 379,
        **extra,
    }


MINE = [
    _text("talk", "האם החשמונאים המציאו את היהדות?", video=True, seconds=1440),
    _text("ruth", "רות", chapters=[{"number": "1"}, {"number": "2"}, {"number": "3"}]),
]


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


def home(browser, tmp_path: Path, days_away: float, due: int = 18, width: int = 1440):
    page_file = tmp_path / "texts.html"
    page_file.write_text(list_page("test-key", "texts"), encoding="utf-8")
    context = browser.new_context(viewport={"width": width, "height": 1600})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    last = int(time.time() * 1000 - days_away * DAY_MS)
    places = [
        {
            "hash": "talk",
            "section": "2",
            "path": "/reader/talk/reader/2.html",
            "seconds": 372,
            "at": last,
        },
        {
            "hash": "ruth",
            "section": "2",
            "path": "/reader/ruth/reader/2.html",
            "seconds": 0,
            "at": last - DAY_MS,
        },
    ]
    answers = {
        "/readers": {"readers": MINE, "shared": [], "trash": []},
        "/account/places": {"signedIn": True, "places": places},
        "/account/due": {"signedIn": True, "due": due},
        "/account/me": {"signedIn": True, "declared": True, "interest": ["news"]},
    }
    page.add_init_script(
        "localStorage.setItem('targum:welcomed', '1');"
        f"const answers = {json.dumps(answers)};"
        "window.__asked = [];"
        "window.fetch = (url) => { const path = String(url).split('?')[0];"
        "  window.__asked.push(String(url));"
        "  const key = Object.keys(answers).find((k) => path.endsWith(k));"
        "  return Promise.resolve(new Response(JSON.stringify(key ? answers[key] : {}))); };"
    )
    page.goto(page_file.as_uri())
    page.wait_for_selector("#library-list li")
    return context, page, thrown


def test_a_week_away_is_welcomed_back_at_the_text_they_stopped_in(browser, tmp_path) -> None:
    context, page, thrown = home(browser, tmp_path, days_away=15)
    try:
        page.wait_for_selector("#welcome-back:not([hidden])")
        line = page.locator("#welcome-back-line").inner_text()
        assert line.startswith("Welcome back. You stopped at part 2 of ")
        assert "האם החשמונאים" in line
        assert page.locator("#welcome-pick .welcome-title").inner_text().startswith("האם")
        go = page.locator("#welcome-pick .welcome-go")
        assert go.inner_text().strip() == "Pick up where you stopped"
        assert "/reader/talk/reader/2.html" in (go.get_attribute("href") or "")
        assert "Stopped at 6:12" in page.locator("#welcome-pick .welcome-facts").inner_text()
        page.wait_for_selector("#welcome-due:not([hidden])")
        assert (
            page.locator("#welcome-due").inner_text().startswith("18 of your words are due a look")
        )
        # The text in the large card is not repeated in Continue.
        titles = page.locator("#continue-cards .home-card-title").all_inner_texts()
        assert titles == ["רות"]
        # The page says nothing about how long they were gone.
        said = page.locator("#welcome-back").inner_text()
        for counted in ("15", "days", "week", "streak"):
            assert counted not in said
        assert not thrown, thrown
    finally:
        context.close()


def test_an_ordinary_day_is_not_welcomed(browser, tmp_path) -> None:
    context, page, thrown = home(browser, tmp_path, days_away=2)
    try:
        page.wait_for_selector("#continue:not([hidden])")
        assert page.locator("#welcome-back").is_hidden()
        assert page.locator("#continue-cards li").count() == 2
        asked = page.evaluate("window.__asked")
        assert not any("/account/due" in url for url in asked), "nothing asked on a normal day"
        assert not thrown, thrown
    finally:
        context.close()


def test_no_words_due_leaves_the_line_out(browser, tmp_path) -> None:
    context, page, _ = home(browser, tmp_path, days_away=9, due=0, width=390)
    try:
        page.wait_for_selector("#welcome-back:not([hidden])")
        page.wait_for_timeout(200)
        assert page.locator("#welcome-due").is_hidden()
    finally:
        context.close()
