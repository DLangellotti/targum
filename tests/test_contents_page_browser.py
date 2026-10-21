"""The desk's contents page in a real browser (design.md §12, "A contents page is a page of
its own, not a small reader", 2026-10-09): served at the reader's own `index.html`, it
picks up this browser's place for somebody signed out and says it the board's way, keeps
the key on every way in, and still carries a link to a verse on to the file holding it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from test_contents_page import built  # noqa: E402
from test_reader_browser import browser, opened  # noqa: E402, F401
from test_serve import postbox, served  # noqa: E402, F401
from test_video_next_part_browser import WIDE  # noqa: E402

from targum.render.builder import CONTENTS  # noqa: E402


def quiet(page) -> None:
    """Nothing but the page itself is under test: no account, no builds, no saving."""
    page.route("**/account/places*", lambda route: route.fulfill(status=401, body="{}"))
    page.route("**/readers*", lambda route: route.fulfill(status=404, body="{}"))
    page.route("**/jobs*", lambda route: route.fulfill(status=404, body="{}"))
    page.route("**/offline.json*", lambda route: route.fulfill(status=404, body="{}"))


def test_continue_follows_this_browser_and_says_the_chapter(
    browser,  # noqa: F811
    served: tuple[int, str, Path],  # noqa: F811
) -> None:
    port, key, out = served
    built(out / "local" / "book-he")
    context = opened(browser, WIDE, scrolling=False)
    places = {"book": {"section": "3", "segment": "", "seconds": 0, "at": 5}}
    context.add_init_script(
        f"localStorage.setItem('targum:places', JSON.stringify({json.dumps(places)}));"
    )
    page = context.new_page()
    quiet(page)
    try:
        page.goto(f"http://127.0.0.1:{port}/reader/book-he/reader/index.html?k={key}")
        page.wait_for_selector("body.parts")
        start = page.locator("#start")
        page.wait_for_function(
            "() => document.querySelector('#start').textContent.includes('chapter 3')"
        )
        assert start.inner_text().strip() == "Continue: chapter 3"
        assert start.get_attribute("href") == f"sec-0003.html?k={key}"
        assert page.locator('[data-chapter="3"]').evaluate("e => e.classList.contains('here')")
        # Every chapter link carries the key, as the old page's did.
        assert page.locator(".toc .parts-name").first.get_attribute("href") == (
            f"sec-0001.html?k={key}"
        )
    finally:
        context.close()


def test_a_link_to_a_verse_still_goes_on_to_its_file(
    browser,  # noqa: F811
    served: tuple[int, str, Path],  # noqa: F811
) -> None:
    port, key, out = served
    folder = built(out / "local" / "ruth-he")
    # Say chapter 2 is held by the second file, as a Tanakh book's contents would.
    manifest = json.loads((folder / "reader" / CONTENTS).read_text(encoding="utf-8"))
    manifest["sections"][1]["chapters"] = "2"
    (folder / "reader" / CONTENTS).write_text(json.dumps(manifest), encoding="utf-8")
    context = opened(browser, WIDE, scrolling=False)
    page = context.new_page()
    quiet(page)
    try:
        with page.expect_navigation(url="**/sec-0002.html*"):
            page.goto(f"http://127.0.0.1:{port}/reader/ruth-he/reader/index.html?k={key}#2")
    finally:
        context.close()
