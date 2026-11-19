"""The portion page's finish (targum-internal#409, slice 3; design.md §12, 2026-11-19), in a
browser: Subscribe says when it is still saving, when it did not go through and when it
was pressed offline, and the PDF press is named in words at both widths.

The page is the one `parasha_page` draws, its scripts inlined as served, opened at a
made-up origin whose `/account/follows` the test answers. Nothing leaves the machine.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from test_parasha_page import _cycle
from test_reader_browser import browser  # noqa: F401

from targum.parasha import calendar as cal
from targum.render.builder import parasha_page

pytest.importorskip("playwright.sync_api", reason="Playwright is not installed")

ORIGIN = "http://targum.test"
NOTE = ".series-subscribe-note"


@pytest.fixture
def page_html() -> str:
    listed = _cycle()
    return parasha_page(listed[1], schedule=cal.Schedule.diaspora, listed=listed, signed_in=True)


@pytest.fixture
def opened(browser: Any, page_html: str) -> Iterator[tuple[Any, Any, list[Any]]]:  # noqa: F811
    """The page at 1440, signed in and not subscribed, with every POST to follows held
    until the test answers it."""
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    held: list[Any] = []

    def follows(route: Any) -> None:
        if route.request.method == "POST":
            held.append(route)
            return
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"signedIn": True, "follows": []}),
        )

    page.route(f"{ORIGIN}/account/follows*", follows)
    page.route(
        f"{ORIGIN}/parasha/noach",
        lambda route: route.fulfill(status=200, content_type="text/html", body=page_html),
    )
    page.goto(f"{ORIGIN}/parasha/noach")
    page.locator("#series-subscribe:not([hidden]) .series-switch").wait_for()
    try:
        yield context, page, held
    finally:
        context.close()


def test_portion_subscribe_says_it_is_still_saving_past_three_seconds(opened) -> None:  # type: ignore[no-untyped-def]
    context, page, held = opened
    page.clock.install()
    page.locator(".series-switch").click()
    page.wait_for_function("() => document.querySelector('.series-switch').disabled")
    assert page.locator(NOTE).is_hidden()
    page.clock.run_for(3100)
    assert page.locator(NOTE).inner_text() == "Still saving…"
    assert page.locator(NOTE).get_attribute("role") == "status"
    held[0].fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps({"signedIn": True, "follows": ["parasha"]}),
    )
    page.wait_for_function(
        "() => document.querySelector('.series-switch').getAttribute('aria-pressed') === 'true'"
    )
    assert page.locator(NOTE).is_hidden(), "saved: nothing left to say"


def test_portion_subscribe_that_fails_says_so_and_keeps_its_state(opened) -> None:  # type: ignore[no-untyped-def]
    context, page, held = opened
    page.locator(".series-switch").click()
    page.wait_for_function("() => document.querySelector('.series-switch').disabled")
    held[0].fulfill(status=500, content_type="text/plain", body="no")
    page.wait_for_function("() => !document.querySelector('.series-subscribe-note').hidden")
    assert page.locator(NOTE).inner_text() == "We couldn't save that. Try again."
    press = page.locator(".series-switch")
    assert press.get_attribute("aria-pressed") == "false" and not press.is_disabled()


def test_portion_subscribe_pressed_offline_says_so_and_asks_nobody(opened) -> None:  # type: ignore[no-untyped-def]
    context, page, held = opened
    context.set_offline(True)
    page.locator(".series-switch").click()
    assert page.locator(NOTE).inner_text() == "You're offline. Subscribe when you're back."
    assert held == [], "nothing was sent"
    assert page.locator(".series-switch").get_attribute("aria-pressed") == "false"


@pytest.mark.parametrize("width", [1440, 390])
def test_portion_pdf_press_is_labelled_at_every_width(
    browser: Any,  # noqa: F811
    page_html: str,
    width: int,
) -> None:
    """Named in words beside its glyph (design.md §14, "Nothing is hover-only"), and
    reachable by a thumb on a phone."""
    context = browser.new_context(
        viewport={"width": width, "height": 900}, has_touch=width < 600, is_mobile=width < 600
    )
    page = context.new_page()
    try:
        page.route(
            f"{ORIGIN}/parasha/noach",
            lambda route: route.fulfill(status=200, content_type="text/html", body=page_html),
        )
        page.route(
            f"{ORIGIN}/account/follows*",
            lambda route: route.fulfill(
                status=200, content_type="application/json", body='{"signedIn": true}'
            ),
        )
        page.goto(f"{ORIGIN}/parasha/noach")
        label = page.locator("a.series-pdf .series-pdf-label")
        assert label.is_visible() and label.inner_text() == "Download PDF"
        assert page.locator("a.series-pdf").get_attribute("title") is None
        box = page.locator("a.series-pdf").bounding_box()
        assert box is not None and box["height"] >= 36
        if width < 600:
            assert box["width"] >= 44 and box["height"] >= 44
    finally:
        context.close()
