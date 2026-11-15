"""The first text's first screen on a phone (targum-internal#723 P2 8, carried to #703).

Page 1 of a Khan Academy reader at 390 was its title and its source, and the source
was said twice ("KhanAcademyHebrew" under both columns, the translation leaving the name
as it was), so the first sentence was a swipe away while the line over the page said
"Tap a word". The byline now says a name once, and belongs to the title the way a plate
does: the page holds on to the first line, cut between its lines where room is short.
Skips itself without Playwright.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from test_reader_browser import browser, opened  # noqa: E402, F401

from targum.models import (  # noqa: E402
    Block,
    BlockKind,
    Document,
    Segment,
    SegmentedDocument,
    Translation,
)
from targum.render import render  # noqa: E402

SOURCE = "KhanAcademyHebrew"
PAGED = """(() => { try {
  localStorage.setItem("targum:prefs", JSON.stringify({ paged: true, defaults: 4 }));
} catch (e) {} })();"""


def built(out: Path) -> Path:
    segments = [
        Segment(id="0000.000-aaaaaa", block_id="b0", block_index=0, index=0,
                kind=BlockKind.heading, level=1, text="הסתברות - הכרות בסיסית"),
        Segment(id="0001.000-bbbbbb", block_id="b1", block_index=1, index=1,
                kind=BlockKind.byline, text=SOURCE),
        Segment(id="0002.000-cccccc", block_id="b2", block_index=2, index=2,
                kind=BlockKind.heading, level=2, text="חלק 1 · 0:00–8:18"),
    ]  # fmt: skip
    long = " ".join(["בשיעור זה אנו רוצים לתת לכם הכרות בסיסית עם הסתברות"] * 6)
    for n in range(3, 9):
        segments.append(
            Segment(id=f"{n:04d}.000-dddddd", block_id=f"b{n}", block_index=n, index=n, text=long)
        )
    translation = {
        s.id: "In this lesson we want to give you a basic introduction. " * 6 for s in segments
    }
    translation["0000.000-aaaaaa"] = "Probability — A Basic Introduction"
    translation["0001.000-bbbbbb"] = SOURCE
    translation["0002.000-cccccc"] = "Part 1 · 0:00–8:18"
    document = Document(
        source="memory",
        title="הסתברות",
        language="he",
        blocks=[Block(id="b0", kind=BlockKind.paragraph, text=long)],
        content_hash="h",
    )
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="test/1", segments=segments
    )
    english = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments=translation,
    )
    return render(document, segmented, [english], out)[0]


def test_the_source_is_said_once_and_the_first_line_is_on_page_one(
    browser,  # noqa: F811
    tmp_path: Path,
) -> None:
    page_file = built(tmp_path / "reader")
    context = opened(browser, viewport={"width": 390, "height": 600}, scrolling=False)
    context.add_init_script(PAGED)
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    try:
        page.goto(page_file.as_uri())
        page.wait_for_selector(".pair")
        page.wait_for_function("() => document.body.classList.contains('first-page')")
        got = page.evaluate(
            """() => {
              const pairs = [...document.querySelectorAll('.pair')];
              const first = pairs.find((pair) => !pair.classList.contains('head')
                && !pair.classList.contains('byline'));
              const box = first.getBoundingClientRect();
              return {
                shown: pairs.filter((pair) => !pair.hidden).map((pair) => pair.className),
                said: [...document.querySelectorAll('.pair.byline > *')]
                  .filter((cell) => cell.getClientRects().length)
                  .map((cell) => cell.textContent.trim()),
                firstShown: !first.hidden,
                top: box.top,
                height: innerHeight,
              };
            }"""
        )
        assert got["said"] == [SOURCE], "a name the translation left alone, once"
        assert got["firstShown"], got
        assert got["top"] < got["height"] - 60, "the first line stands on the first screen"
        assert not thrown, thrown
    finally:
        context.close()
