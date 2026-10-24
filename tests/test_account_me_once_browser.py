"""`/account/me` is asked once a page (targum-internal#484).

qa-claude's page-speed audit (2026-10-22) found every desk page asking who is signed in
three to five times on a cold load: the inbox, the language keys, the account's corner and
the page's own script each sent the question for itself, and some of them waited on each
other. At 150 ms a round trip on a phone that was most of what kept Your targums over
design.md §14's 1.5 s. `keep.js` now asks once and hands each script a copy.

Each page here is the one the server renders, with the account's answers as routes; what is
counted is how many times the question went out. Skips itself without Playwright.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from targum.render.builder import add_page, library_page, list_page, progress_page, you_page

pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://me.test"

ME = {
    "signedIn": True,
    "email": "r@x.test",
    "initials": "R",
    "readsSaid": True,
    "reads": ["en"],
    "language": "he",
    "learning": ["he"],
    "interest": ["news"],
    "hours": {"allowed": 8, "used": 7},
}

PAGES: dict[str, tuple[str, Callable[[], str]]] = {
    "Your targums": ("/", lambda: list_page("", "texts")),
    "subscriptions": ("/?show=subscriptions", lambda: list_page("", "texts")),
    "Library": ("/library", lambda: library_page("")),
    "Progress": ("/progress", lambda: progress_page("")),
    "account": ("/you", lambda: you_page("")),
    "Add": ("/add", lambda: add_page("")),
}


@pytest.mark.parametrize("name", list(PAGES))
def test_a_desk_page_asks_who_is_signed_in_once(chromium, name: str) -> None:
    path, render = PAGES[name]
    html = render()
    asked: list[str] = []

    def answer(route: Any, request: Any) -> Any:
        where = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        if where == "/account/me":
            asked.append(request.url)
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(ME))
        route.fulfill(status=200, content_type="application/json", body="{}")

    context = chromium.browser().new_context(viewport={"width": 390, "height": 844})
    context.add_init_script(
        "localStorage.setItem('targum:welcomed', '1');"
        "localStorage.setItem('targum:language', 'he');"
    )
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    try:
        page.goto(SITE + path)
        page.wait_for_load_state("networkidle")
        # Whatever asks late (a script waiting on the shelf or on sync) has had its turn.
        page.wait_for_timeout(600)
    finally:
        context.close()
    assert len(asked) == 1, f"{name} asked /account/me {len(asked)} times"
    assert not thrown, thrown


def open_account(chromium, answers: list[Any]):
    """Your account, with `/account/me` answered from `answers` in turn (an int is a bare
    status), the last one again once they run out. Returns what was asked.

    The first answer is held until the page has loaded (targum-internal#526). The page's
    scripts ask at different moments of the load: `building.js` as it runs, mid-body, and
    `sync.js` only at DOMContentLoaded. They share one question only while it is still out,
    and a refusal is forgotten as soon as it is back, by design. So on a slow runner a 502
    answered before the rest of the page had run was asked again by the scripts after it:
    correct behaviour, and a failure here on about a quarter of CI's browser jobs. Held
    until `load`, every script that asks on the way in has asked while it is still out."""
    html = you_page("")
    asked: list[str] = []
    held: list[Callable[[], Any]] = []

    def answer(route: Any, request: Any) -> Any:
        where = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        if where == "/account/me":
            said = answers[min(len(asked), len(answers) - 1)]
            asked.append(request.url)
            status, body = (said, "{}") if isinstance(said, int) else (200, json.dumps(said))

            def reply() -> Any:
                return route.fulfill(status=status, content_type="application/json", body=body)

            if len(asked) == 1:
                held.append(reply)
                return None
            return reply()
        route.fulfill(status=200, content_type="application/json", body="{}")

    context = chromium.browser().new_context(viewport={"width": 390, "height": 844})
    context.add_init_script("localStorage.setItem('targum:welcomed', '1');")
    page = context.new_page()
    page.route(f"{SITE}/**", answer)
    page.goto(SITE + "/you")  # returns at `load`: every script on the page has run
    for reply in held:
        reply()
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(300)
    return context, page, asked


def test_a_refused_answer_is_not_kept_for_the_page(chromium) -> None:
    """After a 502 every script on the page has the refusal, and the next to ask (the
    connection coming back, `flush`) reaches the account rather than the kept 502."""
    context, page, asked = open_account(chromium, [502, ME])
    try:
        assert len(asked) == 1, "the 502 was shared, not asked again by each script"
        assert page.evaluate("window.TargumSync.who") is None
        page.evaluate("window.TargumSync.flush()")
        page.wait_for_function("() => window.TargumSync.who && window.TargumSync.who.signedIn")
        assert len(asked) == 2
    finally:
        context.close()


def test_a_fresh_start_asks_again_and_a_plain_one_does_not(chromium) -> None:
    """A change of languages makes the shared answer stale: `start(true)` asks again."""
    context, page, asked = open_account(chromium, [ME])
    try:
        assert len(asked) == 1
        page.evaluate("window.TargumSync.start()")
        page.wait_for_timeout(300)
        assert len(asked) == 1, "a plain start reads the page's answer"
        page.evaluate("window.TargumSync.start(true)")
        page.wait_for_timeout(300)
        assert len(asked) == 2, "a fresh start asks again"
    finally:
        context.close()
