"""Your targums asks what does not wait on the shelf as the page opens (targum-internal#484).

qa-claude's audit (2026-10-22) found Your targums and its Subscriptions tab over design.md
§14's 1.5 s on a phone because of a chain: `/readers`, then the account's places and the
subscriptions' new items, then `/suggest`, each its own round trip, and the Subscriptions
tab's own list only once the shelf was in. None of those needs the shelf, so each is asked
as the page opens. The account's places were asked twice besides, by home and by the
shelf, with two limits: they are asked once now.

The page is the one the server renders, with `/readers` held so nothing it would have
started can start; what is counted is what went out meanwhile. Skips without Playwright.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from targum.render.builder import list_page

pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://yours.test"

ME = {
    "signedIn": True,
    "email": "r@x.test",
    "initials": "R",
    "readsSaid": True,
    "reads": ["en"],
    "language": "he",
    "learning": ["he"],
    "interest": ["news"],
}


def open_held(chromium, path: str):
    html = list_page("", "texts")
    asked: list[str] = []
    held: list[Any] = []

    def answer(route: Any, request: Any) -> Any:
        where = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        asked.append(request.url[len(SITE) :])
        if where == "/readers":
            return held.append(route)
        said = ME if where == "/account/me" else {"signedIn": True}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(said))

    context = chromium.browser().new_context(viewport={"width": 390, "height": 844})
    context.add_init_script(
        "localStorage.setItem('targum:welcomed', '1');"
        "localStorage.setItem('targum:language', 'he');"
    )
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    page.goto(SITE + path)
    page.wait_for_function("() => document.readyState === 'complete'")
    page.wait_for_timeout(600)
    return context, page, asked, held, thrown


def test_home_asks_the_places_and_the_new_items_beside_the_shelf(chromium) -> None:
    context, page, asked, held, thrown = open_held(chromium, "/")
    try:
        assert held, "the shelf was asked for and is held"
        assert any(one.startswith("/subscriptions/new.json") for one in asked), asked
        places = [one for one in asked if one.startswith("/account/places")]
        assert len(places) == 1, places
        held[0].fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"readers": [], "shared": [], "signedIn": True}),
        )
        page.wait_for_timeout(600)
        places = [one for one in asked if one.startswith("/account/places")]
        assert len(places) == 1, f"home and the shelf share one answer: {places}"
        assert not thrown, thrown
    finally:
        context.close()


def test_the_subscriptions_tab_asks_for_its_list_as_the_page_opens(chromium) -> None:
    context, page, asked, held, thrown = open_held(chromium, "/?show=subscriptions")
    try:
        assert held, "the shelf was asked for and is held"
        assert "/subscriptions.json" in [one.split("?")[0] for one in asked], asked
        held[0].fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"readers": [], "shared": [], "signedIn": True}),
        )
        page.wait_for_timeout(600)
        lists = [one for one in asked if one.split("?")[0] == "/subscriptions.json"]
        assert len(lists) == 1, f"the tab's draw reads the answer already asked: {lists}"
        assert not thrown, thrown
    finally:
        context.close()
