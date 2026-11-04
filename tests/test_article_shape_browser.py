"""An article's picture over its caption in a real browser, at a phone's width and a
desk's (design.md §12, "A text keeps the shape its edition gives it", 2026-11-04)."""

from __future__ import annotations

from pathlib import Path

import pytest

from targum import figures
from targum.models import Block, BlockKind, Document, Picture, Translation
from targum.render import render
from targum.segment import HebrewSegmenter, segment_document

pytest.importorskip("playwright.sync_api", reason="Playwright is not installed")

from test_reader_browser import address  # noqa: E402
from test_reader_browser import browser as browser  # noqa: E402,F401

PHONE = {"width": 390, "height": 844}
DESK = {"width": 1440, "height": 900}


@pytest.fixture
def article(tmp_path: Path) -> Path:
    from PIL import Image

    folder = tmp_path / "targum"
    (folder / "figures").mkdir(parents=True)
    Image.new("RGB", (1000, 500), (90, 120, 160)).save(
        folder / figures.kept_path("b0002"), format="WEBP"
    )
    document = Document(
        source="https://news.example/a",
        title="הפועל חולון היא אלופת המדינה בכדורסל",
        language="he",
        blocks=[
            Block(id="b0000", kind=BlockKind.heading, level=1, text="הפועל חולון היא אלופת המדינה"),
            Block(id="b0001", kind=BlockKind.byline, text="30 במאי 2008"),
            Block(
                id="b0002",
                text="היכל הספורט יד אליהו. חולון ניצחה במגרשה הביתי של יריבתה",
                picture=Picture(src="https://upload.example.org/stadium.jpg"),
            ),
            Block(id="b0003", text="הפועל חולון היא אלופת ישראל בכדורסל."),
        ],
    )
    document.content_hash = document.recompute_hash()
    segmented = segment_document(document, HebrewSegmenter())
    english = Translation(
        name="English",
        document_hash=segmented.document_hash,
        source_language="he",
        target_language="en",
        provider="test",
        segments={s.id: "English line." for s in segmented.segments},
    )
    return render(document, segmented, [english], folder / "reader", folder=folder)[0]


@pytest.mark.parametrize("window", [PHONE, DESK], ids=["390", "1440"])
def test_a_picture_stands_over_its_caption(browser, article: Path, window) -> None:
    context = browser.new_context(viewport=window)
    try:
        page = context.new_page()
        page.goto(address(article))
        figure = page.locator(".pair.caption > .figure img")
        figure.wait_for()
        seen = page.evaluate(
            """() => {
                const img = document.querySelector('.pair.caption > .figure img');
                const row = img.closest('.pair');
                const line = row.querySelector('.src:not([hidden])');
                const a = img.getBoundingClientRect();
                const b = line.getBoundingClientRect();
                return {width: a.width, height: a.height, above: a.bottom <= b.top + 1,
                        fits: a.right <= window.innerWidth && a.left >= 0};
            }"""
        )
        assert seen["width"] > 200 and abs(seen["height"] * 2 - seen["width"]) < 4
        assert seen["above"] and seen["fits"]
    finally:
        context.close()
