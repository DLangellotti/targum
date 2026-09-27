"""A picture docked at the top of a phone takes its room out of the page.

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
    watch,
)

PHONE = {"width": 390, "height": 844}

STANDS = """() => {
  const rect = (el) => {
    const r = el.getBoundingClientRect();
    return { top: r.top, bottom: r.bottom };
  };
  const panel = document.getElementById('video');
  const shown = !panel.hidden;
  return {
    corner: panel.className,
    head: getComputedStyle(document.documentElement).getPropertyValue('--head').trim(),
    picture: shown ? rect(panel) : null,
    bar: rect(document.querySelector('.bar')),
    first: rect(document.querySelector('.pair')),
    twentieth: rect(document.querySelectorAll('.pair')[19]),
    scrollY: window.scrollY,
  };
}"""


def opened_with(browser, built, corner: str):  # noqa: F811
    context = browser.new_context(
        viewport=PHONE, is_mobile=True, has_touch=True, reduced_motion="reduce"
    )
    context.add_init_script(
        f"try {{ localStorage.setItem('targum:video-corner', '{corner}'); }} catch (e) {{}}"
    )
    page = context.new_page()
    page.goto(address(built))
    page.wait_for_selector(".pair")
    page.wait_for_selector("#video:not([hidden])")
    settled(page)
    page.wait_for_timeout(300)
    return context, page


@pytest.mark.parametrize("corner", ["top-start", "top-end"])
def test_a_picture_at_the_top_stands_over_neither_the_bar_nor_the_text(
    browser,  # noqa: F811
    tmp_path,
    corner,
) -> None:
    context, page = opened_with(browser, video_reader(tmp_path, lines=40), corner)
    try:
        got = page.evaluate(STANDS)
    finally:
        context.close()
    assert got["scrollY"] == 0 and got["picture"]["top"] <= 1, got
    assert got["bar"]["top"] >= got["picture"]["bottom"] - 1, f"the bar is under it: {got}"
    assert got["first"]["top"] >= got["bar"]["bottom"] - 1, (
        f"and the first line can be read without scrolling, which it could not be: {got}"
    )


def test_a_line_brought_to_the_top_lands_under_the_picture_not_behind_it(
    browser,  # noqa: F811
    tmp_path,
) -> None:
    """`--ceiling` is every line's `scroll-margin`, and it is how the voice brings the
    line it is saying to the top. It counted the bar and not the picture."""
    context, page = opened_with(browser, video_reader(tmp_path, lines=40), "top-start")
    try:
        page.evaluate(
            "() => document.querySelectorAll('.pair')[19].scrollIntoView({ block: 'start' })"
        )
        page.wait_for_timeout(300)
        got = page.evaluate(STANDS)
    finally:
        context.close()
    assert got["scrollY"] > 0, got
    # Against the picture as well as the bar: before this the bar was behind the picture
    # too, so a line that cleared the bar had cleared nothing.
    assert got["twentieth"]["top"] >= got["picture"]["bottom"] - 1, f"clear of the picture: {got}"
    assert got["twentieth"]["top"] >= got["bar"]["bottom"] - 1, f"and of the bar: {got}"
    assert got["twentieth"]["top"] < got["bar"]["bottom"] + 60, f"and at the top, not below: {got}"


def test_a_picture_at_the_foot_leaves_the_top_as_it_was(browser, tmp_path) -> None:  # noqa: F811
    context, page = opened_with(browser, video_reader(tmp_path, lines=40), "bottom-end")
    try:
        got = page.evaluate(STANDS)
    finally:
        context.close()
    assert got["head"] == "" and got["bar"]["top"] == 0, got


def test_the_room_at_the_top_goes_when_the_picture_does(browser, tmp_path) -> None:  # noqa: F811
    """Watching is the whole window and closing is no picture at all: neither leaves a
    picture's height of empty paper above the bar."""
    context, page = opened_with(browser, video_reader(tmp_path, lines=40), "top-start")
    try:
        assert page.evaluate(STANDS)["head"] != ""
        watch(page)
        page.wait_for_timeout(300)
        assert page.evaluate(STANDS)["head"] == "", "nothing is kept clear under a full window"
        page.keyboard.press("v")
        page.wait_for_timeout(300)
        assert page.evaluate(STANDS)["head"] != "", "and it is back with the dock"
        page.evaluate("() => document.querySelector('#video .video-close').click()")
        page.wait_for_timeout(400)
        closed = page.evaluate(STANDS)
    finally:
        context.close()
    assert closed["head"] == "" and closed["bar"]["top"] == 0, closed
