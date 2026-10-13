"""The first finish in a language goes home (design.md §12, "The first finish goes home",
2026-10-12).

David: "the user isn't explained what to do after completing their first targum — they
should be logically redirected to their 'your targums' page." So the first Done in a
language leaves for Your targums, which says once what the press did, with its Undo; every
later Done finishes in place, as it did.

Run in a browser from end to end: a built reader, its Done pressed, and the home page the
server renders, with the account's answers stubbed.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from targum.models import Block, BlockKind, Document, Segment, SegmentedDocument, Translation
from targum.render import render
from targum.render.builder import list_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

TOKEN = "test-key"
SITE = "http://home.test"
READER = "/reader/a-text/reader/index.html"
LINES = ["Мальчик читает книгу.", "Сегодня хорошая погода."]

# What the browser holds about finished texts and whether this language has gone home.
STATE = """() => ({
  address: location.pathname,
  docs: JSON.parse(localStorage.getItem('targum:docs') || '{}'),
  went: localStorage.getItem('targum:went-home:ru'),
})"""


def built(out: Path) -> str:
    """A two-line Russian reader with English under it."""
    segments = [
        Segment(id=f"{n:04d}.000-aaaaaa", block_id=f"b{n:04d}", block_index=n, index=n, text=text)
        for n, text in enumerate(LINES)
    ]
    document = Document(
        source="memory",
        title=LINES[0],
        language="ru",
        blocks=[Block(id="b0000", kind=BlockKind.paragraph, text=segments[0].text)],
        content_hash="h",
    )
    segmented = SegmentedDocument(
        document_hash="h", language="ru", segmenter="test/1", segments=segments
    )
    english = Translation(
        name="English",
        document_hash="h",
        source_language="ru",
        target_language="en",
        provider="null",
        segments={s.id: f"Line {s.index}." for s in segments},
    )
    return render(document, segmented, [english], out)[0].read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def browser():
    try:
        driver = playwright_api.sync_playwright().start()
    except Exception as why:  # pragma: no cover - environment, not behaviour
        pytest.skip(f"Playwright will not start: {why}")
    try:
        running = driver.chromium.launch()
    except Exception as why:  # pragma: no cover - the browser itself is not installed
        driver.stop()
        pytest.skip(f"no Chromium: run `playwright install chromium` ({why})")
    yield running
    running.close()
    driver.stop()


def opened(browser, reader: str, seeded: dict[str, str] | None = None, signed_in: bool = True):
    """A page on the reader, served with home behind it, and the browser holding
    `seeded`. Returns the context and the page."""
    html = list_page(TOKEN, "texts")

    def answer(route, request):
        path = request.url[len(SITE) :].split("?")[0]
        if path.startswith("/reader/"):
            return route.fulfill(status=200, content_type="text/html", body=reader)
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        body: dict[str, Any] = {}
        if path == "/account/me":
            body = (
                {
                    "signedIn": True,
                    "email": "d@x.test",
                    "initials": "D",
                    "readsSaid": True,
                    "reads": ["en"],
                    "language": "ru",
                    "learning": ["ru"],
                }  # fmt: skip
                if signed_in
                else {"signedIn": False}
            )
        elif path == "/readers":
            body = {
                "readers": [
                    {
                        "name": "a-text", "document": "a-text", "title": LINES[0],
                        "language": "ru", "register": "modern", "kind": "article",
                        "sections": 1, "chapters": [], "readyChapters": 1, "built": 1,
                        "opened": 1, "drawn": True, "path": READER,
                    }
                ],
                "shared": [], "trash": [], "covers": False,
            }  # fmt: skip
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context = browser.new_context(
        viewport={"width": 1280, "height": 800}, reduced_motion="reduce", color_scheme="light"
    )
    page = context.new_page()
    stored = {"targum:learning": json.dumps(["ru"]), "targum:language": "ru", **(seeded or {})}
    page.add_init_script(
        "if (!sessionStorage.getItem('seeded')) {"
        "  sessionStorage.setItem('seeded', '1');"
        f"  const held = {json.dumps(stored)};"
        "  Object.keys(held).forEach((k) => localStorage.setItem(k, held[k]));"
        "}"
    )
    page.route(f"{SITE}/**", answer)
    page.goto(SITE + READER)
    page.wait_for_selector("#done-go")
    if signed_in:
        page.wait_for_function("() => window.TargumSync && window.TargumSync.who")
    else:
        page.wait_for_timeout(300)
    return context, page


def test_the_first_finish_goes_home_and_says_what_it_did(browser, tmp_path) -> None:
    context, page = opened(browser, built(tmp_path / "one"))
    try:
        page.click("#done-go")
        page.wait_for_url(lambda url: url.split("?")[0] == SITE + "/")
        page.wait_for_selector("#arrived:not([hidden])")
        line = page.inner_text("#arrived")
        assert line.startswith(f"Finished {LINES[0]} · "), line
        assert "known" in line and "looked up" in line and line.endswith("Undo"), line
        # The share names the part it counts, not the whole text home's card counts (§12,
        # "Each share says what it is a share of", 2026-10-13).
        assert re.search(r"\d+% of this (part|text) ·", line), line
        state = page.evaluate(STATE)
        assert any((r.get("sections") or {}) or r.get("done") for r in state["docs"].values())
        assert state["went"], "the language has gone home once"
        # Undo, from home, takes back the finish.
        page.click("#arrived-undo")
        assert page.inner_text("#arrived") == "Taken back."
        state = page.evaluate(STATE)
        assert not any((r.get("sections") or {}) or r.get("done") for r in state["docs"].values())
        # And a reload says nothing: the line is said once.
        page.reload()
        page.wait_for_timeout(300)
        assert page.is_hidden("#arrived")
    finally:
        context.close()


def test_a_language_that_has_gone_home_finishes_in_place(browser, tmp_path) -> None:
    context, page = opened(browser, built(tmp_path / "two"), seeded={"targum:went-home:ru": "1"})
    try:
        page.click("#done-go")
        page.wait_for_selector("#finished:not([hidden])")
        assert page.evaluate(STATE)["address"] == READER
    finally:
        context.close()


def test_a_language_with_a_finish_on_record_finishes_in_place(browser, tmp_path) -> None:
    """A reader who finished texts before the change is not sent anywhere."""
    earlier = {"other": {"done": 1, "language": "ru", "sections": {"1": 1}}}
    context, page = opened(
        browser, built(tmp_path / "three"), seeded={"targum:docs": json.dumps(earlier)}
    )
    try:
        page.click("#done-go")
        page.wait_for_selector("#finished:not([hidden])")
        state = page.evaluate(STATE)
        assert state["address"] == READER and not state["went"]
    finally:
        context.close()


def test_signed_out_finishes_in_place(browser, tmp_path) -> None:
    """Signed out, "/" is the front door and not their home."""
    context, page = opened(browser, built(tmp_path / "four"), signed_in=False)
    try:
        page.click("#done-go")
        page.wait_for_selector("#finished:not([hidden])")
        assert page.evaluate(STATE)["address"] == READER
    finally:
        context.close()
