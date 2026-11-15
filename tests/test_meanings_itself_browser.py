"""The word card with meanings in the language itself (targum-internal#538, design.md §12,
2026-11-14), the page's half; the server's is `test_meanings_itself.py`.

On, the card asks `/gloss` in Hebrew, leads with the Hebrew meaning and keeps the
English one quieter under it. Off, which is every account that has not chosen it, the
card and everything it asks are what they were. `/gloss` is answered here, so nothing is
bought.

Skips itself unless Playwright and its Chromium are installed, as
`test_reader_browser.py` does, whose browser this borrows.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import test_reader_browser
from test_reader_browser import opened

from targum.models import (
    Annotation,
    Block,
    BlockKind,
    Document,
    Glossary,
    Segment,
    SegmentedDocument,
    Token,
    Translation,
)
from targum.render import render

browser = test_reader_browser.browser

NOUN = "ספר"
HEBREW = "דפים כתובים בין שתי כריכות"


@pytest.fixture(scope="module")
def page_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    text = f"קראתי {NOUN}"
    segment = Segment(id="0000.000-aaaaaa", block_id="b0", block_index=0, index=0, text=text)
    tokens = [
        Token(start=0, end=5, surface="קראתי", lemma="קרא", band=2),
        Token(start=6, end=9, surface=NOUN, lemma=NOUN, band=2),
    ]
    pages = render(
        Document(
            source="memory",
            title="A line",
            language="he",
            blocks=[Block(id="b0", kind=BlockKind.paragraph, text=text)],
            content_hash="h",
        ),
        SegmentedDocument(document_hash="h", language="he", segmenter="t/1", segments=[segment]),
        [
            Translation(
                name="English",
                document_hash="h",
                source_language="he",
                target_language="en",
                provider="null",
                segments={segment.id: "I read a book."},
            )
        ],
        tmp_path_factory.mktemp("itself") / "reader",
        annotation=Annotation(
            document_hash="h",
            language="he",
            annotator="t/1",
            method="frequency",
            method_note="a test",
            tokens={segment.id: tokens},
        ),
        glossaries={
            "en": Glossary(
                source_language="he",
                target_language="en",
                provider="test",
                entries={"קרא": "to read", NOUN: "book"},
            )
        },
    )
    return pages[0]


ME = {"signedIn": True, "email": "reader@example.com", "revision": 0, "counts": {}}


def card_of(
    chromium: Any, page_file: Path, me: dict[str, Any], *, wait: str = ""
) -> dict[str, Any]:
    html = page_file.read_text(encoding="utf-8")
    glossed: list[dict[str, Any]] = []
    context = opened(chromium)
    page = context.new_page()

    def answer(route: Any, request: Any) -> None:
        if "/account/me" in request.url:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(me))
        elif "/gloss" in request.url:
            body = json.loads(request.post_data or "{}")
            glossed.append(body)
            said: dict[str, Any] = {}
            if body.get("target") == "he" and not body.get("free"):
                said = {"lemma": body.get("lemma"), "meaning": HEBREW, "grounded": True}
            elif body.get("target") == "he":
                said = {"lemma": body.get("lemma"), "meaning": None, "cached": False}
            route.fulfill(status=200, content_type="application/json", body=json.dumps(said))
        elif "/sync" in request.url or "/events" in request.url:
            route.fulfill(status=200, content_type="application/json", body="{}")
        else:
            route.fulfill(status=200, content_type="text/html", body=html)

    page.route("http://reader.test/**", answer)
    page.goto("http://reader.test/reader/a-build/reader/index.html?k=test")
    page.wait_for_selector(".pair")
    page.wait_for_function("() => window.TargumSync && window.TargumSync.who")
    tap = f"() => [...document.querySelectorAll('.w')].find((w) => w.textContent === '{NOUN}')"
    page.evaluate(tap + ".click()")
    if wait:
        page.wait_for_selector(wait, timeout=5000)
    else:
        page.wait_for_timeout(600)
    got = {"html": page.evaluate("() => document.querySelector('.gloss-card').outerHTML")}
    got["page"], got["context"], got["glossed"] = page, context, glossed
    return got


def test_off_the_card_asks_nothing_in_hebrew(browser: Any, page_file: Path) -> None:
    before = card_of(browser, page_file, ME)
    after = card_of(browser, page_file, {**ME, "meaningsInItself": []})
    for got in (before, after):
        got["context"].close()
    assert after["html"] == before["html"]
    for got in (before, after):
        assert all(body.get("target") != "he" for body in got["glossed"]), got["glossed"]
        assert "itself" not in got["html"] and "card-also" not in got["html"]
        assert "book" in got["html"]


def test_on_the_hebrew_meaning_leads_and_the_english_is_under_it(
    browser: Any, page_file: Path
) -> None:
    got = card_of(
        browser, page_file, {**ME, "meaningsInItself": ["he"]}, wait=".gloss-card .meaning.itself"
    )
    page = got["page"]
    try:
        hebrew = [body for body in got["glossed"] if body.get("target") == "he"]
        assert hebrew[0]["free"] is True, "the cache first"
        assert hebrew[1]["source"] == "he" and not hebrew[1].get("free")
        assert hebrew[1]["sentence"], "bought with its sentence"
        assert len(hebrew) == 2
        meaning = page.query_selector(".gloss-card .meaning.itself")
        assert meaning is not None
        assert meaning.get_attribute("lang") == "he" and meaning.get_attribute("dir") == "rtl"
        assert HEBREW in (meaning.text_content() or "")
        also = page.text_content(".gloss-card .card-also")
        assert also == "In English: book"
        # The order: the Hebrew meaning, then the English under it.
        order = page.evaluate(
            "() => [...document.querySelector('.gloss-card').children]"
            ".map((n) => n.className).filter((c) => /meaning|card-also/.test(c))"
        )
        assert order[0].startswith("meaning") and "card-also" in order[1]
        # Kept where every meaning is kept, under its own pair.
        kept = page.evaluate("() => localStorage.getItem('targum:meanings:he:he')")
        assert HEBREW in kept
    finally:
        got["context"].close()
