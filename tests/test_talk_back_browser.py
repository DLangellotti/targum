"""On a phone, Back closes Talk before it leaves the page (targum-internal#548).

A beta reader got stuck (2026-10-28): on a phone the Talk sheet covers the page, and the
phone's Back — the button or the swipe — left the page under it instead of putting the
sheet away. David approved one step in the history for the sheet (design.md §12, "On a
phone, Back closes Talk before it leaves the page", 2026-10-28): Back closes it, the next
Back leaves, and closing it any other way takes the step back so none is left that does
nothing. At a desk the drawer adds none, and a conversation opened from the palette adds
none of its own.

The real Library page, its pill and drawer, and the real conversation framed in it, in
headless Chromium, with every answer a route stub, as `test_chat_pill_browser.py` does.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")

from test_chat_pill_browser import SITE, TOKEN, answer_with, browser  # noqa: E402, F401

PHONE = {"width": 390, "height": 844}
DESK = {"width": 1440, "height": 900}

#: Where the tab stands: its address, its history's length, whether the sheet is out, and
#: the frame's own address.
WHERE = """
() => {
  let frame = '';
  try { frame = document.getElementById('talk-frame').contentWindow.location.hash; } catch (e) {}
  return {
    path: location.pathname,
    length: history.length,
    open: document.getElementById('talk-open').getAttribute('aria-expanded') === 'true',
    drawn: !document.getElementById('talk-drawer').hidden,
    frame,
  };
}
"""

ROUTES = {
    "/chat/list": {"chats": [{"id": "abc", "title": "hi", "seen": 1}], "usable": True},
    "/chat/abc": {"chat": {"id": "abc", "language": "he"}, "turns": [], "seconds": 0},
}


def on_the_library(browser, viewport):  # noqa: F811
    """A tab that came to the Library from a page before it, so Back has somewhere to go."""
    context = browser.new_context(viewport=viewport, reduced_motion="reduce")
    page = context.new_page()
    stub = answer_with(ROUTES)

    def answer(route, request):
        if request.url.split("?")[0] == f"{SITE}/before":
            return route.fulfill(
                status=200, content_type="text/html", body="<!doctype html><title>Before</title>"
            )
        return stub(route, request)

    page.route(f"{SITE}/**", answer)
    page.goto(f"{SITE}/before")
    page.goto(f"{SITE}/library?k={TOKEN}")
    page.wait_for_selector("#talk-open:not([hidden])")
    return context, page


def pressed_open(page) -> dict:
    page.click("#talk-open")
    page.wait_for_function("() => !document.getElementById('talk-drawer').hidden")
    return page.evaluate(WHERE)


def shut(page) -> None:
    page.wait_for_function(
        "() => document.getElementById('talk-open').getAttribute('aria-expanded') === 'false'"
    )


def back(page) -> None:
    page.evaluate("() => history.back()")


def test_on_a_phone_back_closes_the_sheet_and_the_next_back_leaves(browser) -> None:  # noqa: F811
    context, page = on_the_library(browser, PHONE)
    try:
        before = page.evaluate(WHERE)
        opened = pressed_open(page)
        assert opened["length"] == before["length"] + 1, "the sheet adds one step"
        assert opened["path"] == "/library", "at the same address"

        back(page)
        shut(page)
        closed = page.evaluate(WHERE)
        assert closed["path"] == "/library" and not closed["open"], "Back closes it, the page stays"

        back(page)
        page.wait_for_url(f"{SITE}/before")
    finally:
        context.close()


@pytest.mark.parametrize("how", ["×", "scrim", "Escape"])
def test_closed_another_way_it_leaves_no_step_behind(browser, how) -> None:  # noqa: F811
    """× (and the dimmed page, and Escape) take the sheet's step back, so the next Back
    leaves the page rather than doing nothing."""
    context, page = on_the_library(browser, PHONE)
    try:
        pressed_open(page)
        if how == "×":
            page.click("#talk-close")
        elif how == "scrim":
            # The dimmed page shows only as a strip over a phone's sheet: pressed as a tap.
            page.evaluate("() => document.getElementById('talk-scrim').click()")
        else:
            page.keyboard.press("Escape")
        shut(page)
        page.wait_for_function("() => !(history.state && history.state.targumTalk)")
        assert page.evaluate(WHERE)["path"] == "/library"

        back(page)
        page.wait_for_url(f"{SITE}/before")
    finally:
        context.close()


def test_at_a_desk_the_drawer_adds_no_step(browser) -> None:  # noqa: F811
    context, page = on_the_library(browser, DESK)
    try:
        before = page.evaluate(WHERE)
        assert pressed_open(page)["length"] == before["length"], "desk is unchanged"
        page.click("#talk-close")
        shut(page)
        back(page)
        page.wait_for_url(f"{SITE}/before")
    finally:
        context.close()


@pytest.mark.parametrize("viewport", [pytest.param(DESK, id="1440"), pytest.param(PHONE, id="390")])
def test_a_conversation_opened_from_the_palette_adds_no_step_of_its_own(
    browser,  # noqa: F811
    viewport,
) -> None:
    """The palette names the conversation in the frame's address. Set, that was a step in
    the holding page's history; replaced, it is none. A phone keeps the sheet's one."""
    context, page = on_the_library(browser, viewport)
    try:
        before = page.evaluate(WHERE)
        page.evaluate("() => window.TargumTalk.open('abc')")
        page.wait_for_function(
            "() => { try { return document.getElementById('talk-frame')"
            ".contentWindow.location.hash === '#abc'; } catch (e) { return false; } }"
        )
        page.wait_for_timeout(200)
        after = page.evaluate(WHERE)
        sheet = 1 if viewport is PHONE else 0
        assert after["length"] == before["length"] + sheet, (before, after)

        if viewport is PHONE:
            back(page)
            shut(page)
            assert page.evaluate(WHERE)["path"] == "/library"
        back(page)
        page.wait_for_url(f"{SITE}/before")
    finally:
        context.close()
