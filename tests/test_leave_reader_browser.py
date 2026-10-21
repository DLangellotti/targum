"""Leaving a text by the mark in its corner lands on the desk in the text's language.

David, 2026-10-07 (design.md §12): a Russian text imported over the connector, read, and
left by the mark at the top left, landed on Learn in Hebrew. The mark now carries the
text's language and Learn takes it as it takes a press of the language menu.

Run in a browser from end to end: a built reader, its mark pressed, and the Learn page
the server renders, with the account's answers stubbed so what is sent can be read.
"""

from __future__ import annotations

import json
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
SITE = "http://learn.test"
READER = "/reader/a-text/reader/index.html"

LINES = {
    "ru": ["Мальчик читает книгу.", "Сегодня хорошая погода."],
    "he": ["הילד קורא ספר.", "היום מזג האוויר טוב."],
    "es": ["El niño lee un libro.", "Hoy hace buen tiempo."],
}


def built(out: Path, language: str) -> str:
    """A two-line reader in `language`, with English under it."""
    segments = [
        Segment(id=f"{n:04d}.000-aaaaaa", block_id=f"b{n:04d}", block_index=n, index=n, text=text)
        for n, text in enumerate(LINES[language])
    ]
    document = Document(
        source="memory",
        title=LINES[language][0],
        language=language,
        blocks=[Block(id="b0000", kind=BlockKind.paragraph, text=segments[0].text)],
        content_hash="h",
    )
    segmented = SegmentedDocument(
        document_hash="h", language=language, segmenter="test/1", segments=segments
    )
    english = Translation(
        name="English",
        document_hash="h",
        source_language=language,
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


def leave(
    browser,
    reader: str,
    language: str,
    learning: list[str],
    chosen: str = "he",
    shot: Path | None = None,
) -> dict[str, Any]:
    """Open `reader`, press its mark, and say where Learn landed and what it told the
    account. The account learns `learning` and was last in `chosen`, and its shelf holds
    the text being left."""
    html = list_page(TOKEN, "texts")
    account = {"language": chosen, "learning": list(learning)}
    told: list[dict[str, Any]] = []

    def answer(route, request):
        url = request.url
        path = url[len(SITE) :].split("?")[0]
        if path.startswith("/reader/"):
            return route.fulfill(status=200, content_type="text/html", body=reader)
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        body: dict[str, Any] = {}
        if path == "/account/me":
            body = {
                "signedIn": True, "email": "d@x.test", "initials": "D", "readsSaid": True,
                "declared": "aleph", "reads": ["en"], **account,
            }  # fmt: skip
        elif path == "/account/language":
            asked = json.loads(request.post_data or "{}")
            told.append(asked)
            # The server's rule: the corner may add a language targum teaches.
            if asked.get("add") and asked["language"] in ("he", "arc", "yi", "fr", "ru", "it"):
                account["learning"] = sorted(set(account["learning"]) | {asked["language"]})
            if asked["language"] in account["learning"]:
                account["language"] = asked["language"]
            body = {"signedIn": True, **account}
        elif path == "/readers":
            body = {
                "readers": [
                    {
                        "name": "a-text", "document": "a-text", "title": LINES[language][0],
                        "language": language, "register": "modern", "kind": "article",
                        "sections": 1, "chapters": [], "readyChapters": 1, "built": 1,
                        "opened": 0, "drawn": True, "path": READER,
                    }
                ],
                "shared": [], "trash": [], "covers": False,
            }  # fmt: skip
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context = browser.new_context(
        viewport={"width": 1280, "height": 800}, reduced_motion="reduce", color_scheme="light"
    )
    page = context.new_page()
    page.add_init_script(
        "if (!sessionStorage.getItem('seeded')) {"
        "  sessionStorage.setItem('seeded', '1');"
        f"  localStorage.setItem('targum:learning', {json.dumps(json.dumps(learning))});"
        f"  localStorage.setItem('targum:language', {json.dumps(chosen)});"
        "}"
    )
    page.route(f"{SITE}/**", answer)
    page.goto(SITE + READER)
    page.wait_for_selector("#home:not([hidden])")
    href = page.get_attribute("#home", "href")
    page.click("#home")
    page.wait_for_url(lambda url: url.split("?")[0] == SITE + "/")
    page.wait_for_selector(".lang-open", state="attached")
    page.wait_for_timeout(400)
    landed = page.evaluate(
        """() => ({
          address: location.pathname + location.search,
          menu: document.querySelector('.lang-name').textContent,
          stored: localStorage.getItem('targum:language'),
          learning: JSON.parse(localStorage.getItem('targum:learning') || 'null'),
        })"""
    )
    if shot is not None:
        page.screenshot(path=str(shot))
    context.close()
    return {"href": href, "told": told, "account": account, **landed}


def test_a_russian_text_left_by_its_mark_lands_on_learn_in_russian(browser, tmp_path) -> None:
    """The case David met: Russian on the shelf, Hebrew on the account's list, Hebrew in
    the menu. Learn opens in Russian, the account is put in Russian with Russian turned
    on, and the address is the plain page."""
    got = leave(browser, built(tmp_path / "ru", "ru"), "ru", learning=["he"])
    assert got["href"] == "/?learning=ru"
    assert got["menu"] == "Russian" and got["stored"] == "ru"
    assert got["address"] == "/", "a reload is the plain page, not a second press"
    assert got["told"] == [{"language": "ru", "add": True}]
    assert got["account"] == {"language": "ru", "learning": ["he", "ru"]}
    assert got["learning"] == ["he", "ru"]


def test_a_hebrew_text_left_by_its_mark_lands_on_learn_in_hebrew(browser, tmp_path) -> None:
    got = leave(browser, built(tmp_path / "he", "he"), "he", learning=["he", "ru"], chosen="ru")
    assert got["href"] == "/?learning=he"
    assert got["menu"] == "Hebrew" and got["stored"] == "he"
    assert got["account"]["language"] == "he"


def test_a_text_in_a_language_with_no_desk_leaves_learn_where_it_was(browser, tmp_path) -> None:
    """Spanish has no Learn of its own: the page stays in Russian, where the reader left
    it, and the account is not asked to change anything."""
    got = leave(browser, built(tmp_path / "es", "es"), "es", learning=["he", "ru"], chosen="ru")
    assert got["href"] == "/?learning=es"
    assert got["menu"] == "Russian" and got["stored"] == "ru"
    assert got["told"] == [] and got["address"] == "/"


def test_a_reader_built_before_goes_home_as_it_did(browser, tmp_path) -> None:
    """A reader written before 2026-10-07 carries its script inside it and says nothing
    on the way out, and the server sends no referrer: Learn opens in the language it
    was in, until the next deploy's rebuild writes the reader again."""
    page = built(tmp_path / "old", "ru")
    old = page.replace('keyed(inItsLanguage("/"))', 'keyed("/")')
    assert old != page, "the line a reader built before this carries"
    got = leave(browser, old, "ru", learning=["he", "ru"], chosen="he")
    assert got["href"] == "/"
    assert got["menu"] == "Hebrew" and got["told"] == []
