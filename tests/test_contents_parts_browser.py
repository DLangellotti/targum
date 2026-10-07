"""A recording's contents page, in a real browser (David, 2026-10-07; design.md §12, "One
press gets the whole video, a part at a time").

The press on the recording's quote covered every part, and opening a part's page is what
starts it — so the contents page has no Transcribe on a waiting row and no Prepare all.
Each waiting row says plainly how its part stands: waiting, or being made, followed live
from the same list of builds the bell follows. A book's contents page keeps its presses.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from test_reader_browser import address, browser, opened  # noqa: E402, F401
from test_video_next_part_browser import WIDE, two_parts  # noqa: E402

#: Where the screenshots go, when a run is asked to keep them.
SHOTS = os.environ.get("TARGUM_SHOTS", "")


def standing(page, name: str, ready: list[bool], jobs: list[list[dict]]) -> list[str]:
    """Stand in for the box: `/readers` says which parts are ready, `/jobs` answers the
    next of `jobs` (the last again once they run out). Every POST is kept."""
    posted: list[str] = []
    left = list(jobs)
    chapters = [{"number": n + 1, "ready": made} for n, made in enumerate(ready)]

    def on_readers(route) -> None:
        body = {"readers": [{"name": name, "chapters": chapters}]}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    def on_jobs(route) -> None:
        payload = left.pop(0) if len(left) > 1 else left[0]
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps({"jobs": payload})
        )

    def on_post(route) -> None:
        posted.append(route.request.url)
        route.fulfill(status=404, content_type="application/json", body="{}")

    page.route("**/readers*", on_readers)
    page.route("**/jobs*", on_jobs)
    page.route("**/chapter*", on_post)
    return posted


def test_a_waiting_part_says_how_it_stands_and_has_no_press(browser, tmp_path) -> None:  # noqa: F811
    """Part one made, part two being made, part three waiting. No button on either row
    and no Prepare all; part two's row says it is being made with the box's own line
    about it, and turns ready when it is; part three's says it is waiting, and its link
    opens its page. The page asks for nothing to be made."""
    reader = two_parts(tmp_path, second_ready=False, count=3)
    making = {
        "id": "j2",
        "stage": "working",
        "folder": tmp_path.name,
        "making": [2],
        "said": "1 of 2 sentences ready.",
    }
    context = opened(browser, WIDE)
    page = context.new_page()
    page.emulate_media(color_scheme="light")
    posted = standing(
        page,
        tmp_path.name,
        [True, False, False],
        [[making], [making], [{**making, "stage": "done"}]],
    )
    try:
        page.goto(address(reader / "index.html"))
        rows = page.locator(".toc [data-chapter]")
        page.wait_for_function(
            "() => document.querySelector('[data-chapter=\"2\"] .get-said')"
            " && document.querySelector('[data-chapter=\"2\"] .get-said').textContent !== ''"
        )
        assert page.locator(".toc .get").count() == 0, "no Transcribe on a part"
        assert page.locator("#prepare").count() == 0, "and no Prepare all"
        two = rows.nth(1).locator(".get-said")
        three = rows.nth(2).locator(".get-said")
        assert two.inner_text() == "Being made. 1 of 2 sentences ready."
        assert three.inner_text() == "Waiting. We make it when you open it."
        assert two.get_attribute("role") == "status"
        # Inside a Hebrew list, an English sentence ends on its full stop, not starts on it.
        assert two.evaluate("e => getComputedStyle(e).direction") == "ltr"
        assert rows.nth(0).locator(".get-said").count() == 0, "a made part says nothing"
        assert rows.nth(2).locator("a").get_attribute("href") == "sec-0003.html"
        if SHOTS:
            Path(SHOTS).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(SHOTS) / "contents-parts-light.png"), full_page=True)
        # The part being made finishes, and the page reloads onto it.
        with page.expect_navigation(timeout=10000):
            pass
        assert posted == [], "nothing on this page asks for anything to be made"
    finally:
        context.close()


def test_a_books_contents_page_keeps_its_presses(browser, tmp_path) -> None:  # noqa: F811
    """A book is unchanged: a waiting chapter's row has Translate and what it spends, and
    Prepare all stands under the list."""
    from test_chapter_ui import book

    from targum.models import Document, SegmentedDocument, Translation, read_artifact
    from targum.render import render

    folder = tmp_path / "book-he"
    book(folder, chapters=2, translated=1)
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    translation = read_artifact(Translation, folder / "translations" / "null.natural.en.json")
    assert segmented is not None and translation is not None
    document = Document(source="m", title="A Book", language="he", blocks=[], content_hash="b")
    render(document, segmented, [translation], folder / "reader")

    context = opened(browser, WIDE)
    page = context.new_page()
    standing(page, folder.name, [True, False], [[]])
    try:
        page.goto(address(folder / "reader" / "index.html"))
        page.wait_for_selector(".toc .get")
        assert page.locator(".toc .get").inner_text() == "Translate"
        assert page.locator(".toc .get-cost").inner_text() == "Uses none of your credits"
        assert page.locator(".toc .get-said").count() == 0
        page.wait_for_selector("#prepare", state="visible")
        assert page.locator("#prepare").inner_text() == "Prepare all"
    finally:
        context.close()
