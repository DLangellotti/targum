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


# -- what a signed-out reader is told (beta review RDR-01, RDR-02, 2026-11-03) -----------


def opened_as(browser, reader: Path, me: dict, width: int):  # noqa: F811
    """The reader at `width`, with `/account/me` answering `me`; the caller closes it."""
    context = opened(browser, viewport={"width": width, "height": 900})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))

    def serve(route, request):
        path = request.url.split("?")[0].removeprefix(ORIGIN)
        if path == "/account/me":
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(me))
        if not path.startswith(FOLDER):
            return route.fulfill(status=404, body="not found")
        target = reader / (path.removeprefix(FOLDER) or "index.html")
        if not target.is_file():
            return route.fulfill(status=404, body="not found")
        return route.fulfill(status=200, path=str(target), content_type="text/html")

    page.route(ORIGIN + "/**", serve)
    page.goto(ORIGIN + FOLDER + "sec-0001.html")
    page.wait_for_selector(".pair")
    page.evaluate("() => window.TargumSync.settled()")
    return context, page, thrown


def shot(page, name: str, width: int) -> None:
    import os

    where = os.environ.get("TARGUM_SHOTS", "").strip()
    if where:
        Path(where).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(where) / f"{name}-{width}.png"))


@pytest.mark.parametrize("width", [390, 1440])
def test_signed_out_one_quiet_line_says_how_to_keep_the_marks(
    browser,  # noqa: F811
    reader: Path,
    width: int,
) -> None:
    """Public shelves let a stranger open a reader, and every word they marked stayed in
    this browser with nothing to say so. One line under the bar, its press Sign in, and
    the waitlist beside it while the front door takes an address. Tell us is not offered:
    there is no account to answer."""
    me = {"signedIn": False, "signedOut": True, "join": "/#join"}
    context, page, thrown = opened_as(browser, reader, me, width)
    try:
        page.wait_for_selector("#signed-out:not([hidden])")
        line = page.evaluate(
            """() => {
              const line = document.getElementById('signed-out');
              const box = line.getBoundingClientRect();
              return {
                text: line.textContent,
                links: [...line.querySelectorAll('a')]
                  .map((a) => [a.textContent, a.getAttribute('href')]),
                height: box.height,
                sideways: document.documentElement.scrollWidth > window.innerWidth,
                tell: document.getElementById('more-tell-us').hidden,
              };
            }"""
        )
        shot(page, "reader-signed-out", width)
    finally:
        context.close()
    assert not thrown, thrown
    assert line["text"] == "Sign in to keep the words you mark · New here? Join the waitlist"
    assert line["links"] == [
        [
            "Sign in to keep the words you mark",
            "/account/signin?next=%2Freader%2Fa-chapter%2Freader%2Fsec-0001.html",
        ],
        ["Join the waitlist", "/#join"],
    ], line["links"]
    assert 0 < line["height"] < 60 and not line["sideways"], line
    assert line["tell"], "no Tell us for somebody with no account"


def test_signed_out_with_the_front_door_shut_the_line_is_sign_in_alone(
    browser,  # noqa: F811
    reader: Path,
) -> None:
    context, page, thrown = opened_as(browser, reader, {"signedIn": False, "signedOut": True}, 390)
    try:
        page.wait_for_selector("#signed-out:not([hidden])")
        text = page.inner_text("#signed-out")
    finally:
        context.close()
    assert not thrown, thrown
    assert text == "Sign in to keep the words you mark"


def test_with_nobody_to_sign_into_nothing_is_said(browser, reader: Path) -> None:  # noqa: F811
    """A machine somebody runs themselves, with no account on it, is never signed out."""
    context, page, thrown = opened_as(browser, reader, {"signedIn": False}, 1440)
    try:
        page.wait_for_timeout(300)
        hidden = page.evaluate("() => document.getElementById('signed-out').hidden")
    finally:
        context.close()
    assert not thrown, thrown
    assert hidden


@pytest.mark.parametrize("width", [390, 1440])
def test_tell_us_is_the_last_row_of_the_more_menu_for_a_reader_with_an_account(
    browser,  # noqa: F811
    reader: Path,
    width: int,
) -> None:
    """The reader has no account menu, so on the page the beta reads most Tell us was
    reached only after a fault."""
    me = {"signedIn": True, "email": "reader@example.com"}
    context, page, thrown = opened_as(browser, reader, me, width)
    try:
        page.wait_for_selector("#more-tell-us:not([hidden])", state="attached")
        page.click("button.bar-tool.more")
        page.wait_for_selector("#more-tell-us", state="visible")
        last = page.evaluate(
            "() => [...document.querySelectorAll('#more .m-row')]"
            ".filter((r) => !r.closest('[hidden]'))"
            ".map((r) => r.id || r.getAttribute('data-what')).pop()"
        )
        shot(page, "reader-more-tell-us", width)
        page.click("#more-tell-us")
        page.wait_for_selector("dialog.tell-us[open]")
        title = page.inner_text("#tell-us-title")
        signed_out_shown = page.evaluate("() => !document.getElementById('signed-out').hidden")
    finally:
        context.close()
    assert not thrown, thrown
    assert last == "more-tell-us" and title == "Tell us"
    assert not signed_out_shown
