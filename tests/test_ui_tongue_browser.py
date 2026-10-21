"""EN · RU in the top bar (design.md §12, "Russian has a switch in the bar", 2026-10-12).

Drawn only for a signed-in reader who may read Russian, and a press says the account's
"Read and translate into" choice and draws the page again.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from targum.render.builder import list_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

TOKEN = "test-key"
SITE = "http://tongue.test"


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


def home(
    browser,
    locale: str,
    reads: list[str],
    signed_in: bool = True,
    width: int = 1280,
    language: str = "en",
    phone: bool = False,
):
    html = list_page(TOKEN, "texts", language=language)
    told: list[dict[str, Any]] = []
    loads: list[str] = []

    def answer(route, request):
        path = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            loads.append(path)
            return route.fulfill(status=200, content_type="text/html", body=html)
        body: dict[str, Any] = {}
        if path == "/account/me":
            body = (
                {
                    "signedIn": True,
                    "email": "d@x.test",
                    "initials": "D",
                    "readsSaid": True,
                    "reads": reads,
                    "language": "he",
                    "learning": ["he"],
                }
                if signed_in
                else {"signedIn": False}
            )
        elif path == "/account/languages":
            told.append(json.loads(request.post_data or "{}"))
            body = {"signedIn": True, "learning": ["he"], "reads": told[-1]["reads"]}
        elif path == "/readers":
            body = {"readers": [], "shared": [], "trash": [], "covers": False}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    extra = {"is_mobile": True, "has_touch": True} if phone else {}
    context = browser.new_context(
        viewport={"width": width, "height": 800},
        locale=locale,
        reduced_motion="reduce",
        color_scheme="light",
        **extra,
    )
    page = context.new_page()
    # Answered the arrival already, so home is home and not `/welcome`.
    page.add_init_script("localStorage.setItem('targum:welcomed', '1')")
    page.route(f"{SITE}/**", answer)
    page.goto(SITE + "/")
    page.wait_for_selector(".lang-open", state="attached")
    page.wait_for_timeout(400)
    return context, page, told, loads


def test_a_browser_in_russian_sees_en_ru_and_a_press_switches(browser) -> None:
    context, page, told, loads = home(browser, "ru-RU", ["en"])
    try:
        assert page.is_visible("#ui-tongue")
        assert page.inner_text("#ui-tongue").split() == ["EN", "·", "RU"]
        assert page.get_attribute(".ui-tongue-key[lang=en]", "aria-pressed") == "true"
        page.click(".ui-tongue-key[lang=ru]")
        page.wait_for_timeout(600)
        assert told == [{"learning": ["he"], "reads": ["ru"]}]
        assert len(loads) == 2, "the page is drawn again in the language chosen"
        assert page.evaluate("() => localStorage.getItem('targum:into')") == "ru"
    finally:
        context.close()


def test_an_account_that_reads_russian_sees_it_whatever_the_browser(browser) -> None:
    context, page, _, _ = home(browser, "en-US", ["ru"])
    try:
        assert page.is_visible("#ui-tongue")
    finally:
        context.close()


def test_nobody_else_sees_it(browser) -> None:
    context, page, _, _ = home(browser, "en-US", ["en"])
    try:
        assert page.is_hidden("#ui-tongue")
        assert page.inner_text("#ui-tongue") == ""
    finally:
        context.close()


def test_signed_out_sees_nothing(browser) -> None:
    context, page, _, _ = home(browser, "ru-RU", ["en"], signed_in=False)
    try:
        assert page.is_hidden("#ui-tongue")
    finally:
        context.close()


@pytest.mark.parametrize("language", ["en", "ru"])
def test_on_a_phone_it_is_a_row_of_the_account_sheet_and_the_bar_fits(browser, language) -> None:
    """design.md §13, 2026-10-18: EN and RU were 28px keys in the phone bar, and widening
    them pushed the Russian bar 32px off the screen. Under 40rem they are a row of the
    account's sheet at 44px, and the bar at 390 fits in English and in Russian."""
    context, page, told, loads = home(
        browser, "ru-RU", ["en"], width=390, language=language, phone=True
    )
    try:
        assert page.is_hidden("#ui-tongue"), "the bar leaves them out on a phone"
        sideways = page.evaluate(
            "() => { const row = document.querySelector('.site-head-row');"
            " return Math.max(row.scrollWidth - row.clientWidth,"
            " row.getBoundingClientRect().right - window.innerWidth,"
            " document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth); }"
        )
        assert sideways <= 0, f"the bar is {sideways}px too wide"
        for child in page.locator(".site-head-row > *:visible").all():
            box = child.bounding_box()
            assert box and box["x"] >= 0 and box["x"] + box["width"] <= 390, child

        page.click("#account-open")
        page.wait_for_selector("#account-panel:not([hidden])")
        assert page.is_visible("#account-tongue")
        assert page.inner_text("#account-tongue-keys").split() == ["EN", "·", "RU"]
        for code in ("en", "ru"):
            key = page.locator(f"#account-tongue-keys .ui-tongue-key[lang={code}]")
            box = key.bounding_box()
            assert box and box["width"] >= 44 and box["height"] >= 44, (code, box)
        other = "ru" if language == "en" else "en"
        page.click(f"#account-tongue-keys .ui-tongue-key[lang={other}]")
        page.wait_for_timeout(600)
        assert told == [{"learning": ["he"], "reads": [other]}]
        assert len(loads) == 2, "the page is drawn again in the language chosen"
    finally:
        context.close()


def test_at_a_desk_the_sheet_has_no_row_and_the_bar_keeps_them(browser) -> None:
    context, page, _, _ = home(browser, "ru-RU", ["en"])
    try:
        assert page.is_visible("#ui-tongue")
        page.click("#account-open")
        page.wait_for_selector("#account-panel:not([hidden])")
        assert page.is_hidden("#account-tongue")
    finally:
        context.close()


def test_on_a_phone_nobody_else_has_the_row(browser) -> None:
    context, page, _, _ = home(browser, "en-US", ["en"], width=390, phone=True)
    try:
        page.click("#account-open")
        page.wait_for_selector("#account-panel:not([hidden])")
        assert page.is_hidden("#account-tongue")
        assert page.inner_text("#account-tongue-keys") == ""
    finally:
        context.close()
