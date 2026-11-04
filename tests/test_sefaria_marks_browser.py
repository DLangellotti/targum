"""An edition's citations and a translator's notes in a real browser, at a phone's width
and a desk's (design.md §12, "A text keeps the shape its edition gives it", 2026-11-04).

A citation is drawn small and soft and never takes the page's wash — and its words are
still words: they carry the marks every word carries and answer a tap (David).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from targum.models import (
    Annotation,
    Block,
    BlockKind,
    Document,
    Mark,
    Note,
    Token,
    Translation,
)
from targum.render import render
from targum.segment import HebrewSegmenter, segment_document

pytest.importorskip("playwright.sync_api", reason="Playwright is not installed")

from test_reader_browser import address  # noqa: E402
from test_reader_browser import browser as browser  # noqa: E402,F401

PHONE = {"width": 390, "height": 844}
DESK = {"width": 1440, "height": 900}
TEXT = "האל הנכבד והנורא הזה מצוה לאהבו שנאמר (דברים ו ה) ואהבת את ה' אלהיך"
CITE = "(דברים ו ה)"


@pytest.fixture
def reader(tmp_path: Path) -> Path:
    at = TEXT.index(CITE)
    document = Document(
        source="sefaria:Mishneh Torah, Foundations of the Torah",
        title="משנה תורה, הלכות יסודי התורה",
        language="he",
        blocks=[
            Block(
                id="b0000", kind=BlockKind.heading, level=2, text="משנה תורה, הלכות יסודי התורה ב׳"
            ),
            Block(
                id="b0001",
                kind=BlockKind.verse,
                text=TEXT,
                ref="Mishneh Torah, Foundations of the Torah 2:1",
                marks=[Mark(start=at, end=at + len(CITE), kind="cite")],
            ),
        ],
        ingester="sefaria/6",
    )
    document.content_hash = document.recompute_hash()
    segmented = segment_document(document, HebrewSegmenter())
    verse = next(s for s in segmented.segments if s.kind is BlockKind.verse)
    tokens = {
        verse.id: [
            Token(start=m.start(), end=m.end(), surface=m.group(), lemma=m.group(), band=3)
            for m in re.finditer(r"[א-ת']+", verse.text)
        ]
    }
    english = Translation(
        name="Glazer",
        document_hash=segmented.document_hash,
        source_language="he",
        target_language="en",
        provider="aligned",
        kind="aligned",
        segments={verse.id: 'It is mandatory to love Him, for it is said: "Love" (Deut. 6,5).'},
        notes={
            verse.id: [Note(at=len("It is mandatory to love Him,"), mark="1", text="Sifre. G.")]
        },
    )
    annotation = Annotation(
        document_hash=segmented.document_hash,
        language="he",
        annotator="test/1",
        method="frequency",
        method_note="a test",
        tokens=tokens,
    )
    return render(document, segmented, [english], tmp_path / "reader", annotation=annotation)[0]


@pytest.mark.parametrize("window", [PHONE, DESK], ids=["390", "1440"])
def test_a_citation_is_quiet_and_its_words_are_still_words(browser, reader: Path, window) -> None:
    context = browser.new_context(viewport=window)
    try:
        page = context.new_page()
        page.goto(address(reader))
        page.wait_for_selector(".src .cite .w")
        seen = page.evaluate(
            """() => {
                const cite = document.querySelector('.src .cite');
                const inside = cite.querySelector('.w');
                const outside = Array.from(document.querySelectorAll('.src .w'))
                    .find((w) => !w.closest('.cite'));
                const size = (el) => parseFloat(getComputedStyle(el).fontSize);
                return {
                    words: cite.querySelectorAll('.w').length,
                    smaller: size(cite) < size(cite.closest('.src')),
                    washInside: getComputedStyle(inside).backgroundColor,
                    washOutside: getComputedStyle(outside).backgroundColor,
                };
            }"""
        )
        assert seen["words"] == 3, "דברים, ו and ה are words inside the citation"
        assert seen["smaller"]
        assert seen["washInside"] in ("rgba(0, 0, 0, 0)", "transparent")
        assert seen["washOutside"] not in ("rgba(0, 0, 0, 0)", "transparent")
        # A tap on a cited word opens its card, as a tap on any word does.
        page.locator(".src .cite .w").first.click()
        page.wait_for_function(
            "() => { const c = document.querySelector('.gloss-card');"
            " return !!c && !c.hidden && c.getBoundingClientRect().height > 0; }"
        )
        # The translation's reference is quiet, and its note is under it.
        assert page.locator(".tr .cite").first.inner_text() == "(Deut. 6,5)"
        assert page.locator(".tr .note-mark").first.is_visible()
        assert "Sifre. G." in page.locator(".tr .tr-notes").first.inner_text()
    finally:
        context.close()
