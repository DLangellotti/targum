"""A long address in "We've sent a link to …" wraps on a 320px phone (targum-internal#687).

The line is one run as long as the address, and with nothing to break it a 60-character
address widened the account menu's page to 653px: sideways scroll (design.md §14). Both
places the line is said are held to it, the account menu on every page and the sign-in
door, in English and in Russian.

On a phone the menu is a fixed sheet the width of the screen, so there the page does not
widen: the sheet scrolls sideways instead. So the line and the sheet are measured as well
as the page.

Skips itself without Playwright and its Chromium, as the other browser tests do.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("playwright.sync_api")

from targum.render.builder import signin_page, you_page  # noqa: E402

ADDRESS = "a.very.long.address.for.a.narrow.phone.page@example-mail.org"
assert len(ADDRESS) == 60

SIDEWAYS = "document.documentElement.scrollWidth - document.documentElement.clientWidth"


def overflow(selector: str) -> str:
    """How far the element at `selector` runs past its own box, sideways."""
    return f"(el => el.scrollWidth - el.clientWidth)(document.querySelector({selector!r}))"


@pytest.fixture
def browser(chromium):
    return chromium.browser()


def phone(browser, html: str, path: str):
    context = browser.new_context(viewport={"width": 320, "height": 640})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))

    def answer(route, request):
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        if "/account/sign-in" in request.url:
            return route.fulfill(
                status=200, content_type="application/json", body=json.dumps({"sent": True})
            )
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps({"signedIn": False})
        )

    page.route("http://long.test/**", answer)
    page.goto("http://long.test" + path)
    return context, page, thrown


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_account_menu_wraps_a_long_address(browser, language: str) -> None:
    context, page, thrown = phone(browser, you_page("k", language), "/you?k=k")
    page.click("#account-open")
    page.fill("#account-email", ADDRESS)
    page.press("#account-email", "Enter")
    page.wait_for_function(
        f"document.getElementById('account-said').textContent.includes({ADDRESS!r})"
    )
    assert page.evaluate(SIDEWAYS) <= 0
    assert page.evaluate(overflow("#account-said")) <= 0
    assert page.evaluate(overflow("#account-panel")) <= 0
    context.close()
    assert not thrown, thrown


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_sign_in_door_wraps_a_long_address(browser, language: str) -> None:
    context, page, thrown = phone(browser, signin_page(language=language), "/account/signin")
    page.fill("#email", ADDRESS)
    page.click("#ask button")
    page.wait_for_function(f"document.getElementById('sent').textContent.includes({ADDRESS!r})")
    assert page.evaluate(SIDEWAYS) <= 0
    assert page.evaluate(overflow("#sent")) <= 0
    context.close()
    assert not thrown, thrown
