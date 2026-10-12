"""A reader opened signed out asks the account for nothing (QA 2026-10-11, known issues §3).

Signed out, every reader logged a refusal or two in the console: `/offline.json` to keep
the text for offline, `/voice` to ask whether its audio was on its way, `/chapter` to
fetch the next chapter ahead, and `/account/me` itself with a 403. The server now says
"nobody, and an account is needed here" (`signedOut`), and the page asks none of the
account's routes on its own after that. A machine with nobody to sign into is never
signed out, and still fetches ahead as it did.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_reader_browser import browser, chapter, opened  # noqa: F401

ORIGIN = "http://targum.test"
FOLDER = "/reader/a-chapter/reader/"
ACCOUNT_ONLY = ("/offline.json", "/voice", "/chapter", "/jobs", "/chat/list")


@pytest.fixture(scope="module")
def reader(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Two chapters, so the first has a next one to fetch ahead — one still waiting, as a
    book bought a chapter at a time has it: a next chapter already translated says
    `data-ready` and is never asked for (known issues 2026-10-12, m6)."""
    folder = chapter(tmp_path_factory.mktemp("signed-out") / "reader", parts=2).parent
    first = folder / "sec-0001.html"
    first.write_text(first.read_text(encoding="utf-8").replace(" data-ready", ""), encoding="utf-8")
    return folder


def read_to_the_end(browser, reader: Path, me: dict) -> list[str]:  # noqa: F811
    context = opened(browser)
    page = context.new_page()
    asked: list[str] = []

    def serve(route, request):
        path = request.url.split("?")[0].removeprefix(ORIGIN)
        asked.append(path)
        if path == "/account/me":
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(me))
        if path.startswith(ACCOUNT_ONLY):
            return route.fulfill(status=401, content_type="application/json", body="{}")
        if not path.startswith(FOLDER):
            return route.fulfill(status=404, body="not found")
        target = reader / (path.removeprefix(FOLDER) or "index.html")
        if not target.is_file():
            return route.fulfill(status=404, body="not found")
        return route.fulfill(status=200, path=str(target), content_type="text/html")

    page.route(ORIGIN + "/**", serve)
    try:
        page.goto(ORIGIN + FOLDER + "sec-0001.html")
        page.wait_for_selector(".pair")
        page.wait_for_function("() => window.TargumSync && window.TargumSync.who === null")
        page.evaluate("() => window.TargumSync.settled()")
        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(2500)
        return asked
    finally:
        context.close()


def test_signed_out_the_reader_asks_no_route_of_the_account(browser, reader: Path) -> None:  # noqa: F811
    asked = read_to_the_end(browser, reader, {"signedIn": False, "signedOut": True})
    assert "/account/me" in asked
    assert [path for path in asked if path.startswith(ACCOUNT_ONLY)] == []


def test_with_nobody_to_sign_into_the_next_chapter_is_still_fetched_ahead(
    browser,  # noqa: F811
    reader: Path,
) -> None:
    """The control: a fresh install answers "nobody" without `signedOut`, and the page
    goes on doing what it did, so the test above is the gate and not a dead fetch."""
    asked = read_to_the_end(browser, reader, {"signedIn": False})
    assert "/chapter" in asked
