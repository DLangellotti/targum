"""Progress on a new device draws what the account brings without loading again
(targum-internal#484).

With nothing in the browser, Progress waits for the account's answer before saying
"nothing yet", which is right. It then called `location.reload()` whenever the answer
brought anything, so a reader signing in on a new phone loaded the page twice: 2.67 s on
the phone profile against design.md §14's 1.5 s, in qa-claude's audit of 2026-10-22. What
arrives is now drawn in place, as Your Words has done since 2026-10-20.

The page is the one the server renders, with the account's answers as routes. Skips itself
without Playwright.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from targum.render.builder import progress_page

pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://progress.test"

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


def pulled(*lemmas: str) -> list[dict[str, Any]]:
    return [
        {
            "language": "he",
            "lemma": lemma,
            "status": 2,
            "surface": lemma,
            "band": 1,
            "learned": 0,
            "at": 100 + n,
            "seen": 200,
            "gone": 0,
        }
        for n, lemma in enumerate(lemmas)
    ]


def open_progress(chromium, sync: dict[str, Any]):
    html = progress_page("")

    def answer(route: Any, request: Any) -> Any:
        path = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        said = {"/account/me": ME, "/sync": sync}.get(path, {"signedIn": True})
        route.fulfill(status=200, content_type="application/json", body=json.dumps(said))

    context = chromium.browser().new_context(viewport={"width": 390, "height": 844})
    context.add_init_script("localStorage.setItem('targum:welcomed', '1');")
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    loads: list[str] = []
    page.on(
        "framenavigated",
        lambda frame: loads.append(frame.url) if frame == page.main_frame else None,
    )
    page.route(f"{SITE}/**", answer)
    return context, page, thrown, loads


def test_a_new_device_draws_the_accounts_words_without_loading_again(chromium) -> None:
    context, page, thrown, loads = open_progress(
        chromium, {"revision": 3, "words": pulled("ספר", "דרך", "עיר")}
    )
    try:
        page.goto(SITE + "/progress")
        page.wait_for_selector("#page:not([hidden])")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)
        assert len(loads) == 1, loads
        assert page.locator("#nothing").is_hidden()
        assert page.locator("#counts .count-saved b").inner_text() == "3"
        assert not thrown, thrown
    finally:
        context.close()


def test_an_account_with_nothing_in_it_still_says_nothing_yet(chromium) -> None:
    context, page, thrown, loads = open_progress(chromium, {"revision": 1})
    try:
        page.goto(SITE + "/progress")
        page.wait_for_selector("#nothing:not([hidden])")
        assert len(loads) == 1, loads
        assert page.locator("#page").is_hidden()
        assert not thrown, thrown
    finally:
        context.close()
