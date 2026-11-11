"""The open door in a browser (targum-internal#671; design.md §12, 2026-11-10).

The front page's box answers in a popup whose form was the waitlist's: with the door open
it signs up, posting to `/signup` with the link kept, and the popup turns into the server's
own "Check your email". And the bar's Sign up, «Регистрация» in Russian, is longer than
«Записаться» was: on a narrow phone the bar still fits, and the press keeps one line.

Skips itself unless Playwright and its Chromium are installed.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs

import pytest

from targum.render.builder import front_page, weekly_note

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://door.test"

TRIED = {
    "door": "youtube",
    "title": "A video",
    "site": "",
    "minutes": 3,
    "sentences": 0,
    "subtitles": True,
    "link": "https://www.youtube.com/watch?v=abc",
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


@pytest.fixture
def door_open(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    monkeypatch.setenv("TARGUM_OPEN_SIGNUP", "1")
    monkeypatch.setenv("TARGUM_PLANS", "1")


def test_a_link_tried_signs_up_from_the_popup(browser: Any, door_open: None) -> None:
    landing = front_page("en", "https://targum.page")
    answered = front_page("en", "https://targum.page", tried=TRIED)
    sent = weekly_note(
        "Thanks. We've sent a link to new@example.com.",
        heading="Check your email",
        home="/",
    )
    posted: list[dict[str, list[str]]] = []

    def answer(route: Any, request: Any) -> None:
        if request.method == "POST" and request.url.startswith(SITE + "/try"):
            route.fulfill(status=200, content_type="text/html", body=answered)
        elif request.method == "POST" and request.url.startswith(SITE + "/signup"):
            posted.append(parse_qs(request.post_data or ""))
            route.fulfill(status=200, content_type="text/html", body=sent)
        elif request.resource_type == "document":
            route.fulfill(status=200, content_type="text/html", body=landing)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    try:
        page.goto(SITE + "/")
        page.fill(".try-form input[name=link]", TRIED["link"])
        page.click(".try-form button[type=submit]")
        page.wait_for_selector("#popBody .tried-keep")
        assert page.inner_text("#popBody .tried-keep") == (
            "Sign up and this link will be waiting for you."
        )
        assert page.inner_text("#popBody .join-form button") == "Sign up"
        page.fill("#popBody .join-form input[type=email]", "new@example.com")
        page.click("#popBody .join-form button")
        page.wait_for_selector("#popBody .pop-done")
        assert page.inner_text("#popBody .pop-head") == "Check your email"
        assert "We've sent a link to new@example.com." in page.inner_text("#popBody .pop-said")
        assert len(posted) == 1
        assert posted[0]["email"] == ["new@example.com"]
        assert posted[0]["link"] == [TRIED["link"]]
        assert not thrown, thrown
    finally:
        context.close()


#: Whether the page scrolls sideways, and how many lines the bar's press is set on.
FITS = """() => {
  const press = document.querySelector('.bar .btn.cta');
  return {
    wide: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    lines: press.getClientRects().length,
    tall: press.getBoundingClientRect().height,
    text: press.textContent,
  };
}"""


@pytest.mark.parametrize("width", [320, 360, 390])
def test_sign_up_fits_the_bar_on_a_narrow_phone_in_russian(
    browser: Any, door_open: None, width: int
) -> None:
    landing = front_page("ru", "https://targum.page", "ru")

    def answer(route: Any, request: Any) -> None:
        if request.resource_type == "document":
            route.fulfill(status=200, content_type="text/html", body=landing)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(
        viewport={"width": width, "height": 800}, has_touch=True, is_mobile=True
    )
    page = context.new_page()
    page.route(f"{SITE}/**", answer)
    try:
        page.goto(SITE + "/?lang=ru")
        got = page.evaluate(FITS)
        assert got["text"] == "Регистрация"
        assert got["wide"] <= 0, f"the page scrolls sideways at {width}: {got}"
        assert got["lines"] == 1, f"Sign up breaks at {width}: {got}"
    finally:
        context.close()
