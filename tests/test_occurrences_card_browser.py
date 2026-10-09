"""The word card on a box that shows where words come round (targum-internal#95, #96).

Off — `TARGUM_OCCURRENCES` unset, which is every box until somebody decides otherwise —
the card must be the card it was, byte for byte, and must ask nothing. On, it asks
`/word/met` once when it opens and says what came back. The route is answered here, so
what is under test is the page's half; the server's is `test_occurrences_card.py`.

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

#: One Chromium, shared with the reader's own browser tests.
browser = test_reader_browser.browser

VERB = "כתב"
NOUN = "ספר"


@pytest.fixture(scope="module")
def verb_page(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One line: a verb with its root and binyan, and a noun with neither."""
    text = f"{VERB} {NOUN}"
    segment = Segment(id="0000.000-aaaaaa", block_id="b0", block_index=0, index=0, text=text)
    tokens = [
        Token(start=0, end=3, surface=VERB, lemma=VERB, band=2, root=VERB, binyan="פעל"),
        Token(start=4, end=7, surface=NOUN, lemma=NOUN, band=2),
    ]
    pages = render(
        Document(
            source="memory",
            title="A chapter",
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
                segments={segment.id: "He wrote a book."},
            )
        ],
        tmp_path_factory.mktemp("verb") / "reader",
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
                entries={VERB: "to write", NOUN: "book"},
            )
        },
    )
    return pages[0]


#: What `/word/met` says about the verb, on a box that shows it.
SAID = {
    "here": 4,
    "tanakh": 241,
    "met": ["Jonah 1:4", "Ruth 2:1", "יונה"],
    "more": 6,
    "family": {"met": 6, "known": 3, "words": [VERB, "מכתב", "כתובה"]},
}


def card_of(chromium: Any, page_file: Path, me: dict[str, Any], lemma: str) -> dict[str, Any]:
    """Open the page as a served, signed-in reader whose account answers `me`, tap the
    word, and hand back the card and what the page asked of `/word/met`."""
    html = page_file.read_text(encoding="utf-8")
    asked: list[str] = []
    context = opened(chromium)
    page = context.new_page()

    def answer(route: Any, request: Any) -> None:
        if "/account/me" in request.url:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(me))
        elif "/word/met" in request.url:
            asked.append(request.url)
            route.fulfill(status=200, content_type="application/json", body=json.dumps(SAID))
        elif "/sync" in request.url or "/gloss" in request.url or "/events" in request.url:
            route.fulfill(status=200, content_type="application/json", body="{}")
        else:
            route.fulfill(status=200, content_type="text/html", body=html)

    page.route("http://reader.test/**", answer)
    page.goto("http://reader.test/reader/a-build/reader/index.html?k=test")
    page.wait_for_selector(".pair")
    if me.get("signedIn"):
        page.wait_for_function("() => window.TargumSync && window.TargumSync.who")
    tap = f"() => [...document.querySelectorAll('.w')].find((w) => w.textContent === '{lemma}')"
    page.evaluate(tap + ".click()")
    page.wait_for_timeout(400)
    got = {"html": page.evaluate("() => document.querySelector('.gloss-card').outerHTML")}
    got["page"], got["context"], got["asked"] = page, context, asked
    return got


ME = {"signedIn": True, "email": "reader@example.com", "revision": 0, "counts": {}}


@pytest.mark.parametrize("lemma", [VERB, NOUN])
def test_off_the_card_is_the_card_it_was(browser: Any, verb_page: Path, lemma: str) -> None:
    """The switch off and the switch absent — an account that says nothing of it, as
    every box said until now — draw the same card, byte for byte, and ask nothing."""
    before = card_of(browser, verb_page, ME, lemma)
    after = card_of(browser, verb_page, {**ME, "occurrences": False}, lemma)
    for got in (before, after):
        got["context"].close()
    assert after["html"] == before["html"]
    assert not before["asked"] and not after["asked"], "nothing is asked of /word/met"
    assert "card-round" not in after["html"] and "root-open" not in after["html"]
    if lemma == VERB:
        assert 'class="root"' in after["html"], "the root is there, as the plain word it was"


def test_on_the_card_says_where_the_word_comes_round(browser: Any, verb_page: Path) -> None:
    got = card_of(browser, verb_page, {**ME, "occurrences": True}, VERB)
    page = got["page"]
    try:
        assert len(got["asked"]) == 1, "asked once, when the card opened"
        url = got["asked"][0]
        assert "document=h" in url and "section=1" in url and "root=" in url
        lines = page.evaluate(
            "() => [...document.querySelectorAll('.gloss-card .card-round')]"
            ".map((line) => line.textContent)"
        )
        assert lines == [
            "6 words from כ־ת־ב met, 3 known",
            # How many texts leads, as the board's label over the stage control says it
            # (audit Q6); the texts themselves are said for a screen reader and a pointer.
            "Met in 9 texts · 4× in this text · 241× in the Tanakh"
            + "met in Jonah 1:4, Ruth 2:1, יונה and 6 more",
        ]
        # A title in Hebrew sits in its own bdi, as the root does.
        assert page.evaluate(
            "() => [...document.querySelectorAll('.gloss-card .card-met bdi')]"
            ".map((b) => b.textContent)"
        ) == ["יונה"]

        # The root is the way in to the words of it the reader met.
        root = ".gloss-card .card-facts .root-open"
        assert page.get_attribute(root, "aria-expanded") == "false"
        assert page.query_selector(".gloss-card .card-root-words") is None
        page.click(root)
        page.wait_for_selector(".gloss-card .card-root-words")
        assert page.get_attribute(root, "aria-expanded") == "true"
        assert page.text_content(".gloss-card .card-root-words") == "כתב · מכתב · כתובה"
        assert page.is_visible(".gloss-card"), "pressing the root keeps the card open"
        assert len(got["asked"]) == 1, "and asks nothing again"
    finally:
        got["context"].close()


def test_on_a_word_with_no_root_has_no_root_line(browser: Any, verb_page: Path) -> None:
    got = card_of(browser, verb_page, {**ME, "occurrences": True}, NOUN)
    try:
        assert "root=&" in got["asked"][0]
        assert "root-open" not in got["html"] and "card-root-met" not in got["html"]
    finally:
        got["context"].close()
