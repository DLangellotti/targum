"""The edition's shape in a real browser, at a phone's width and a desk's (design.md §12,
"A text keeps the shape its edition gives it", 2026-11-04), and the two faults found on
the way: a long row cut through a line at the foot of a page, and a score broken in two.

Skips itself unless Playwright and its Chromium are installed, as the other browser
files do.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from targum.models import BlockKind, Document, Segment, SegmentedDocument, Translation
from targum.render import render

pytest.importorskip("playwright.sync_api", reason="Playwright is not installed")

from test_reader_browser import address  # noqa: E402
from test_reader_browser import browser as browser  # noqa: E402,F401

PHONE = {"width": 390, "height": 844}
DESK = {"width": 1440, "height": 900}
ETNACHTA = "֑"
WORK = "משנה תורה, הלכות יסודי התורה"
#: A sentence of English long enough that a halakha's translation outruns its Hebrew.
LONG = (
    "When man will reflect concerning His works and His great and wonderful creatures, "
    "and will behold through them His wonderful, matchless and infinite wisdom, he will "
    "spontaneously be filled with love, praise and exaltation. "
)


def _verse(n: int, text: str, ref: str) -> Segment:
    return Segment(
        id=f"{n:04d}.000-aaaaaa",
        block_id=f"b{n:04d}",
        block_index=n,
        index=0,
        kind=BlockKind.verse,
        text=text,
        ref=ref,
    )


def _head(n: int, text: str) -> Segment:
    return Segment(
        id=f"{n:04d}.000-hhhhhh",
        block_id=f"b{n:04d}",
        block_index=n,
        index=0,
        kind=BlockKind.heading,
        level=2,
        text=text,
    )


def _reader(out: Path, title: str, segments: list[Segment], english: dict[str, str]) -> Path:
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="fake/1", segments=segments
    )
    document = Document(source="sefaria:Test", title=title, language="he", blocks=[])
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="sefaria",
        segments=english,
    )
    return render(document, segmented, [translation], out)[0]


@pytest.fixture
def halakhot(tmp_path: Path) -> Path:
    """A chapter of halakhot, the second with an English far longer than its Hebrew."""
    segments = [
        _head(0, f"{WORK} ב׳"),
        _verse(1, "הָאֵל הַנִּכְבָּד וְהַנּוֹרָא הַזֶּה מִצְוָה לְאָהֳבוֹ וּלְיִרְאָה אוֹתוֹ", "MT 2:1"),
        _verse(2, " ".join(["וְהֵיאַךְ הִיא הַדֶּרֶךְ לְאַהֲבָתוֹ וְיִרְאָתוֹ"] * 14), "MT 2:2"),
        _verse(3, "כָּל מַה שֶּׁבָּרָא הַקָּדוֹשׁ בָּרוּךְ הוּא", "MT 2:3"),
    ]
    english = {
        segments[0].id: "Mishneh Torah, Foundations of the Torah 2",
        segments[1].id: "It is mandatory to love and fear this God.",
        segments[2].id: LONG * 16,
        segments[3].id: "All that the Holy One created.",
    }
    return _reader(tmp_path / "halakhot", WORK, segments, english)


#: Every line of the open page, each with where it stands and the box it can be seen in:
#: its row's own box, narrowed by the clip its column was given. A line is whole when it
#: is wholly inside that box or wholly outside it.
LINES = """
() => {
  const out = [];
  const range = document.createRange();
  document.querySelectorAll('#reader .pair:not([hidden])').forEach((pair) => {
    const row = pair.getBoundingClientRect();
    Array.from(pair.children).forEach((cell) => {
      if (!cell.matches('.tr, .src')) return;
      const style = getComputedStyle(cell);
      if (style.display === 'none') return;
      const box = cell.getBoundingClientRect();
      let top = Math.max(row.top, box.top);
      let bottom = Math.min(row.bottom, box.bottom);
      const clip = /inset\\(([\\d.]+)px [\\d.]+px ([\\d.]+)px/.exec(style.clipPath || '');
      if (clip) {
        top = Math.max(top, box.top + parseFloat(clip[1]));
        bottom = Math.min(bottom, box.bottom - parseFloat(clip[2]));
      }
      const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT);
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        if (!node.data.trim()) continue;
        range.selectNodeContents(node);
        for (const rect of range.getClientRects()) {
          if (!rect.height) continue;
          out.push({
            column: cell.classList.contains('tr') ? 'tr' : 'src',
            top: rect.top, bottom: rect.bottom, seenTop: top, seenBottom: bottom,
          });
        }
      }
    });
  });
  return out;
}
"""


def _pages(page: Any) -> int:
    said = page.locator("#page-of").inner_text()
    return int(said.split()[-1])


@pytest.mark.parametrize("window", [PHONE, DESK], ids=["390", "1440"])
def test_a_long_row_is_never_cut_through_a_line(browser, halakhot: Path, window) -> None:
    """A halakha whose English runs past the page is cut between lines in each column, and
    every line of it is seen whole on exactly one page (2026-11-04: the English ran under
    the foot of the page with its last line cut in half)."""
    context = browser.new_context(viewport=window)
    try:
        page = context.new_page()
        page.goto(address(halakhot))
        page.wait_for_function("document.querySelector('#page-of')?.textContent.trim()")
        total = _pages(page)
        assert total > 1, "the long halakha needs more than one page"
        seen = 0
        lines_in_all = None
        for n in range(total):
            lines = page.evaluate(LINES)
            for line in lines:
                inside = (
                    line["top"] >= line["seenTop"] - 1 and line["bottom"] <= line["seenBottom"] + 1
                )
                outside = (
                    line["bottom"] <= line["seenTop"] + 1 or line["top"] >= line["seenBottom"] - 1
                )
                assert inside or outside, f"page {n + 1}: a line is cut ({line})"
                if inside and line["column"] == "tr":
                    seen += 1
            if lines_in_all is None:
                lines_in_all = sum(1 for line in lines if line["column"] == "tr")
            if n + 1 < total:
                page.locator("#turn .forward").click()
                page.wait_for_timeout(150)
        # Nothing of the English is lost between the pages.
        assert lines_in_all is not None and seen >= lines_in_all
    finally:
        context.close()


@pytest.mark.parametrize("window", [PHONE, DESK], ids=["390", "1440"])
def test_a_halakha_chapter_wears_its_own_shape(browser, halakhot: Path, window) -> None:
    context = browser.new_context(viewport=window)
    try:
        page = context.new_page()
        page.goto(address(halakhot))
        page.wait_for_function("document.querySelector('#page-of')?.textContent.trim()")
        plate = page.locator(".plate-face")
        assert plate.is_visible()
        assert page.locator(".plate-chapter").inner_text().strip() == "פרק ב׳"
        assert page.locator(".plate-work").inner_text().strip() == WORK
        # The heading's own words are in the page and not drawn.
        assert not page.locator(".pair.plate > .src").first.is_visible()
        number = page.locator('.verse-number[href="#2:1"]')
        assert number.is_visible() and number.inner_text().strip() == "א׳"
    finally:
        context.close()


@pytest.mark.parametrize("window", [PHONE, DESK], ids=["390", "1440"])
def test_a_psalm_and_a_parasha_wear_their_own_shape(browser, tmp_path: Path, window) -> None:
    line = f"מִזְמ֥וֹר לְדָוִ֑{ETNACHTA}ד יְהוָ֥ה רֹ֝עִ֗י לֹ֣א אֶחְסָֽר׃"
    psalm = _reader(
        tmp_path / "psalm",
        "תהילים",
        [_head(0, "תהילים כ״ג"), _verse(1, line, "Psalms 23:1"), _verse(2, line, "Psalms 23:2")],
        {},
    )
    torah = _reader(
        tmp_path / "torah",
        "בראשית",
        [
            _head(0, "בראשית א׳"),
            _verse(1, "וַיְהִי עֶרֶב וַיְהִי בֹקֶר יוֹם אֶחָד׃ (פ)", "Genesis 1:5"),
            _verse(2, "וַיֹּאמֶר אֱלֹהִים יְהִי רָקִיעַ׃", "Genesis 1:6"),
        ],
        {},
    )
    context = browser.new_context(viewport=window)
    try:
        page = context.new_page()
        page.goto(address(psalm))
        shown = page.locator('.pair[id="23:1"] > .src:visible').first
        lines = shown.evaluate(
            """(cell) => {
                const r = document.createRange(); r.selectNodeContents(cell);
                return new Set(Array.from(r.getClientRects()).map((x) => Math.round(x.top))).size;
            }"""
        )
        assert lines >= 2, "the verse stands in its half-lines"
        page.goto(address(torah))
        after = page.locator('.pair[id="1:5"]')
        assert "ends-open" in (after.get_attribute("class") or "")
        gap = page.evaluate(
            """() => {
                const a = document.getElementById('1:5').getBoundingClientRect();
                const b = document.getElementById('1:6').getBoundingClientRect();
                return b.top - a.bottom;
            }"""
        )
        assert gap >= 20, "an open parasha leaves its space"
    finally:
        context.close()


@pytest.mark.parametrize("window", [PHONE, DESK], ids=["390", "1440"])
def test_a_score_is_never_broken_across_lines(browser, tmp_path: Path, window) -> None:
    """However the line falls, "72-73" stands on one line (2026-11-04)."""
    segments = [
        Segment(
            id=f"{n:04d}.000-aaaaaa",
            block_id=f"b{n:04d}",
            block_index=n,
            index=0,
            text=("מכבי " * n) + "הפסידה בתוצאה 72-73 בהיכל.",
        )
        for n in range(1, 30)
    ]
    reader = _reader(tmp_path / "score", "כדורסל", segments, {})
    context = browser.new_context(viewport=window)
    try:
        page = context.new_page()
        page.add_init_script(
            "localStorage.setItem('targum:prefs', JSON.stringify({paged: false, defaults: 4}))"
        )
        page.goto(address(reader))
        broken = page.evaluate(
            """() => Array.from(document.querySelectorAll('bdi.unbroken'))
                .filter((b) => b.offsetParent)
                .filter((b) => {
                  const tops = Array.from(b.getClientRects()).map((r) => Math.round(r.top));
                  return new Set(tops).size > 1;
                })
                .length"""
        )
        counted = page.locator("bdi.unbroken:visible").count()
        assert counted > 0 and broken == 0
    finally:
        context.close()
