"""The picture at the top of a phone takes its room out of the page.

Since targum-internal#422 a phone has one way for a video to stand: the picture under the
bar, its row of controls under it, and the transcript under those. That is what the
picture docked at the top used to be, and the rules this file was written for are the
same rules, so they are kept; what went is the corner the reader chose (there is one
now) and full screen (the browser's, under ⋯).

Written first for the dock (2026-09-20):

The band at the foot has always been measured and told to the stylesheet, so the page is
padded by it and the strip rides on it. The one resident that can stand at the top
instead — the picture, docked there — was kept out of those sums (`atFoot`), rightly,
and then counted nowhere. Pages are cut under it, but on a narrow window a docked
picture suspends paging, so the reader it meets is the scrolling one, which knew of
nothing at the top but the bar. The picture stood over the bar, over the first lines of
the text with no way to scroll them clear, and over every line the voice brought to the
top. In part one of an import the title is tall enough to be the thing covered; in part
two it is the text (David, on his phone, 2026-09-20).
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")

# The fixtures live in the browser module rather than a conftest, so they are
# imported by name to register them here.
from test_reader_browser import (  # noqa: E402, F401
    address,
    browser,
    settled,
    video_reader,
)

PHONE = {"width": 390, "height": 844}

STANDS = """() => {
  const rect = (el) => {
    const r = el.getBoundingClientRect();
    return { top: r.top, bottom: r.bottom };
  };
  const panel = document.getElementById('video');
  const shown = !panel.hidden;
  // The lines on show: under a picture the title and byline are said under it instead.
  const lines = [...document.querySelectorAll('#reader .pair')]
    .filter((p) => p.getClientRects().length);
  return {
    head: getComputedStyle(document.documentElement).getPropertyValue('--head').trim(),
    picture: shown ? rect(panel) : null,
    bar: rect(document.querySelector('.bar')),
    first: rect(lines[0]),
    twentieth: lines[19] ? rect(lines[19]) : null,
    scrollY: window.scrollY,
  };
}"""


def opened_on_a_phone(browser, built):  # noqa: F811
    context = browser.new_context(
        viewport=PHONE, is_mobile=True, has_touch=True, reduced_motion="reduce"
    )
    page = context.new_page()
    page.goto(address(built))
    page.wait_for_selector(".pair")
    page.wait_for_selector("#video:not([hidden])")
    settled(page)
    page.wait_for_timeout(300)
    return context, page


def test_the_picture_stands_under_the_bar_and_over_none_of_the_text(
    browser,  # noqa: F811
    tmp_path,
) -> None:
    """The bar, then the picture and its controls, then the first line — none over the
    next. The bar is on top now (#422): it was under the picture when the picture was a
    dock the reader could put at the top or the foot."""
    context, page = opened_on_a_phone(browser, video_reader(tmp_path, lines=40))
    try:
        got = page.evaluate(STANDS)
    finally:
        context.close()
    assert got["scrollY"] == 0 and got["bar"]["top"] <= 1, got
    assert got["picture"]["top"] >= got["bar"]["bottom"] - 1, f"the picture is under the bar: {got}"
    assert got["first"]["top"] >= got["picture"]["bottom"] - 1, (
        f"and the first line can be read without scrolling: {got}"
    )


def test_a_line_brought_to_the_top_lands_under_the_picture_not_behind_it(
    browser,  # noqa: F811
    tmp_path,
) -> None:
    """`--ceiling` is every line's `scroll-margin`, and it is how the voice brings the
    line it is saying to the top. It counted the bar and not the picture."""
    context, page = opened_on_a_phone(browser, video_reader(tmp_path, lines=40))
    try:
        page.evaluate(
            "() => [...document.querySelectorAll('#reader .pair')]"
            ".filter((p) => p.getClientRects().length)[19].scrollIntoView({ block: 'start' })"
        )
        page.wait_for_timeout(300)
        got = page.evaluate(STANDS)
    finally:
        context.close()
    assert got["scrollY"] > 0, got
    # The picture stays with the reader as they scroll: it is the transcript that moves.
    assert got["picture"]["top"] >= got["bar"]["bottom"] - 1, f"still under the bar: {got}"
    assert got["twentieth"]["top"] >= got["picture"]["bottom"] - 1, f"clear of the picture: {got}"
    assert got["twentieth"]["top"] < got["picture"]["bottom"] + 60, (
        f"and at the top, not below: {got}"
    )


def test_the_room_at_the_top_goes_when_the_picture_does(browser, tmp_path) -> None:  # noqa: F811
    """Put away under ⋯, the picture leaves no picture's height of empty paper above the
    text, and brought back it takes its room again."""
    context, page = opened_on_a_phone(browser, video_reader(tmp_path, lines=40))
    try:
        assert page.evaluate(STANDS)["head"] != ""
        page.evaluate("() => window.TargumVideo.hide()")
        page.wait_for_timeout(400)
        closed = page.evaluate(STANDS)
        page.evaluate("() => document.querySelector('.m-row[data-video]').click()")
        page.wait_for_timeout(400)
        back = page.evaluate(STANDS)
    finally:
        context.close()
    assert closed["head"] == "" and closed["bar"]["top"] == 0 and closed["picture"] is None, closed
    assert back["head"] != "" and back["picture"] is not None, back
