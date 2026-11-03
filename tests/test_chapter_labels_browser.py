"""A chapter's label in a real browser (David, 2026-11-03; design.md §12, "A chapter says
"פרק א׳", and the work is named once"): the contents list, Next, and the bar on a wide
window say "פרק ב׳", and the bar keeps the work's name beside it."""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")

from test_chapter_labels import WORK, built  # noqa: E402
from test_reader_browser import address, browser, opened  # noqa: E402, F401
from test_video_next_part_browser import WIDE  # noqa: E402


def test_the_contents_next_and_bar_say_the_chapter(browser, tmp_path) -> None:  # noqa: F811
    reader = built(tmp_path)
    context = opened(browser, WIDE)
    page = context.new_page()
    try:
        page.goto(address(reader / "index.html"))
        rows = page.locator(".toc [data-chapter] a")
        assert [rows.nth(n).inner_text().strip("⁨⁩") for n in range(2)] == [
            "פרק א׳",
            "פרק ב׳",
        ]

        page.goto(address(reader / "sec-0001.html"))
        part = page.locator(".bar-title .bar-part")
        assert part.is_visible()
        assert part.inner_text() == "פרק א׳"
        assert page.locator(".bar-title .up").inner_text() == WORK
        assert page.locator("a.next bdi").inner_text() == "פרק ב׳"
        # The heading in the text is the text, and still names the work.
        assert WORK in page.locator(".pair.head .src.plain").first.inner_text()
    finally:
        context.close()


def test_a_narrow_window_leaves_the_bar_to_the_work(browser, tmp_path) -> None:  # noqa: F811
    reader = built(tmp_path)
    context = opened(browser, {"width": 390, "height": 844})
    page = context.new_page()
    try:
        page.goto(address(reader / "sec-0001.html"))
        assert page.locator(".bar-title .bar-part").count() == 1
        assert not page.locator(".bar-title .bar-part").is_visible()
    finally:
        context.close()
