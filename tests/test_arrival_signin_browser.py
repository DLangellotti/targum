"""The sign-in door's states, in a real browser (design.md §14; arrival QA, 2026-10-18).

What the door says while a link is being sent and once it has gone, and what a page the
mailed link opens keeps for the arrival after it. The server is a route: these are about
what the page draws, and `test_arrival_doors.py` holds what the server answers.

Skips itself without Playwright and its Chromium, as the other browser tests do.
"""

from __future__ import annotations

import json

import pytest

from targum.render.builder import signin_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)


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


def served(browser, html: str, path: str, answer, **context_options):
    context = browser.new_context(viewport={"width": 390, "height": 844}, **context_options)
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))

    def route(route, request):
        if request.url.split("?")[0].endswith(path):
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            answer(route, request)

    page.route("http://door.test/**", route)
    page.goto("http://door.test" + path)
    return context, page, thrown


def sent(route, request) -> None:
    route.fulfill(status=200, content_type="application/json", body=json.dumps({"sent": True}))


def test_once_the_link_has_gone_the_door_says_what_next_and_offers_another_address(
    browser,
) -> None:
    """It said "Thanks. We've sent a link to …" and nothing more: no word on what to do
    with it, and no way back to an address typed wrong but a reload."""
    context, page, thrown = served(browser, signin_page(), "/account/signin", sent)
    page.fill("#email", "rader@example.com")
    page.click("#ask button")
    page.wait_for_selector(".sent-next:not([hidden])")
    said = page.inner_text(".door")
    assert "Thanks. We've sent a link to rader@example.com." in said
    assert "Open it to sign in. It works once, for 20 minutes." in said
    assert page.is_hidden("#ask")

    page.click(".sent-again")
    assert page.is_visible("#ask") and page.is_enabled("#ask button")
    assert page.evaluate("document.activeElement.id") == "email"
    assert page.is_hidden(".sent-next") and page.is_hidden("#sent")
    context.close()
    assert not thrown, thrown


def test_a_link_slow_to_send_is_said_after_three_seconds(browser) -> None:
    """A greyed button and nothing else, for as long as the mail takes, reads as a press
    that did nothing and gets pressed again."""
    held: list = []

    def answer(route, request):
        if "/account/sign-in" in request.url:
            held.append(route)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context, page, thrown = served(browser, signin_page(), "/account/signin", answer)
    page.clock.install()
    page.fill("#email", "reader@example.com")
    page.click("#ask button")
    page.clock.run_for(1000)
    assert page.is_hidden("#sent"), "not before three seconds"
    page.clock.run_for(2500)
    assert page.inner_text("#sent") == "We're still sending your link."
    assert page.is_disabled("#ask button")
    held[0].fulfill(status=200, content_type="application/json", body=json.dumps({"sent": True}))
    page.wait_for_selector(".sent-next:not([hidden])")
    assert "Thanks. We've sent a link to reader@example.com." in page.inner_text("#sent")
    context.close()
    assert not thrown, thrown


def test_the_page_a_russian_link_opens_keeps_russian_for_the_arrival(browser) -> None:
    """Opened on a phone that never saw the form, the page is the only thing that knows
    the link was asked for in Russian; it keeps that where the arrival reads it."""
    html = signin_page(landing="chitatel@example.com", token="t", language="ru", asked="ru")
    context, page, thrown = served(browser, html, "/account/enter", sent)
    assert page.evaluate("localStorage.getItem('targum:into')") == "ru"
    assert page.get_attribute("form.enter", "action") == "/account/enter?lang=ru"
    context.close()
    assert not thrown, thrown


def test_a_choice_this_browser_already_made_is_not_overruled(browser) -> None:
    html = signin_page(landing="reader@example.com", token="t", language="ru", asked="ru")
    context = browser.new_context()
    context.add_init_script("localStorage.setItem('targum:into', 'en')")
    page = context.new_page()
    page.route(
        "http://door.test/**",
        lambda route, request: route.fulfill(status=200, content_type="text/html", body=html),
    )
    page.goto("http://door.test/account/enter")
    assert page.evaluate("localStorage.getItem('targum:into')") == "en"
    context.close()
