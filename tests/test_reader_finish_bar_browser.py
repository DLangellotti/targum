"""The reader's §14 finish bar, in a real browser (targum-internal#703, design's pass of
2026-11-13).

Each test here is one finding of that pass, and fails on the page as it stood before it:
the marking finish drawn as a line press beside Done, a phone's words tab standing over a
video's transcript, Hebrew in the end card and the forms table without its own direction,
controls short of a thumb's 44px, the turning arrows cut by a phone's edges, and a Latin
name in a Hebrew line drawn as a word to learn.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from test_reader_browser import address, browser, built, opened, video_reader  # noqa: E402, F401
from test_reader_reach_browser import REACH  # noqa: E402
from test_video_next_part_browser import two_parts  # noqa: E402

WIDE = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}

#: How the two presses at the foot are drawn.
PRESSES = """
() => Object.fromEntries(['#done-go', '#done-mark'].map((s) => {
  const e = document.querySelector(s);
  const cs = getComputedStyle(e);
  return [s, {
    border: parseFloat(cs.borderTopWidth),
    fill: cs.backgroundColor,
    size: parseFloat(cs.fontSize),
    line: cs.textDecorationLine,
    weight: Number(cs.fontWeight),
  }];
}))
"""


def touch_page(browser, reader: Path, viewport=PHONE):  # noqa: F811
    context = browser.new_context(
        viewport=viewport, reduced_motion="reduce", is_mobile=True, has_touch=True
    )
    page = context.new_page()
    page.goto(address(reader))
    page.wait_for_selector(".pair", state="attached")
    page.wait_for_timeout(300)
    return context, page


def test_marking_the_rest_is_the_quiet_link_beside_done(browser, built: Path) -> None:  # noqa: F811
    """design.md §12, "Done marks nothing; knowing them all is a choice" (2026-10-13): Done
    is the press, and "Done, and mark N words known" is the quiet link beside it. It was
    still the line press of the 2026-10-09 board, an outlined pill (P1-1, P2-17)."""
    context = opened(browser, WIDE)
    page = context.new_page()
    try:
        page.goto(address(built))
        page.wait_for_selector(".pair")
        drawn = page.evaluate(PRESSES)
    finally:
        context.close()
    go, mark = drawn["#done-go"], drawn["#done-mark"]
    assert go["fill"] == "rgb(31, 111, 107)", "Done is filled in teal"
    assert mark["border"] == 0, f"no outline round the marking finish: {mark}"
    assert mark["fill"] in ("rgba(0, 0, 0, 0)", "transparent"), mark
    assert "underline" in mark["line"], mark
    assert mark["weight"] < 600, mark


def test_under_the_picture_done_still_leads_the_marking_finish(browser, built: Path) -> None:  # noqa: F811
    """In Theatre, at the end of a part with a part after it, Next part is the primary
    and Done steps down to a link (2026-10-07). The marking finish was then the biggest
    thing on the card, an outlined pill beside a 13px Done (P1-1). The page is put in
    that state by hand: a part played to its end, with a door to the next."""
    context = opened(browser, WIDE)
    page = context.new_page()
    try:
        page.goto(address(built))
        page.wait_for_selector(".pair")
        page.evaluate(
            """() => {
                 const door = document.createElement('div');
                 door.id = 'film-next';
                 document.body.appendChild(door);
                 document.body.classList.add('film-ended');
               }"""
        )
        drawn = page.evaluate(PRESSES)
    finally:
        context.close()
    go, mark = drawn["#done-go"], drawn["#done-mark"]
    assert go["fill"] in ("rgba(0, 0, 0, 0)", "transparent"), "Next part is the one primary"
    assert mark["border"] == 0, mark
    assert go["size"] >= mark["size"], f"Done is not smaller than the choice beside it: {drawn}"
    assert go["weight"] >= mark["weight"], drawn


#: The band a phone keeps at the foot of a video's transcript, and the tab in it.
BAND = """
() => {
  const tab = document.getElementById('list-tab');
  const r = tab.getBoundingClientRect();
  const band = getComputedStyle(document.body, '::after');
  return {
    tab: !tab.hidden && r.height > 0,
    tabTop: r.top,
    content: band.content,
    bandTop: innerHeight - parseFloat(band.height || '0'),
    fill: band.backgroundColor,
    padded: parseFloat(getComputedStyle(document.body).paddingBottom),
  };
}
"""


def test_a_phone_keeps_a_band_for_the_words_tab_under_a_video(browser, tmp_path) -> None:  # noqa: F811
    """P1-2: under a picture the transcript scrolls, so no page is cut above the words tab
    and the tab stood over whichever line passed under it. The foot now keeps a band of
    paper from the tab's top edge down, as the bar keeps the top, and the body is padded
    by it so the last line scrolls clear (the band `room()` reserves; §14.2)."""
    lines = [f"שורה מספר {n} כאן" for n in range(1, 13)]
    reader = video_reader(tmp_path, texts=lines, lines=len(lines))
    context, page = touch_page(browser, reader)
    try:
        page.wait_for_selector("#video:not([hidden])")
        page.wait_for_function("() => document.body.classList.contains('film')")
        page.wait_for_timeout(300)
        seen = page.evaluate(BAND)
    finally:
        context.close()
    assert seen["tab"], seen
    assert seen["content"] not in ("none", "normal"), f"no band behind the tab: {seen}"
    assert seen["bandTop"] <= seen["tabTop"] + 0.5, seen
    assert seen["fill"] not in ("rgba(0, 0, 0, 0)", "transparent"), seen
    assert seen["padded"] >= 844 - seen["bandTop"] - 0.5, "the last line scrolls clear of it"


def test_hebrew_in_the_end_card_says_its_own_direction(browser, built: Path) -> None:  # noqa: F811
    """P2-6: the chips are laid out from the card's start (`direction: ltr` on the list),
    and each Hebrew word computed ltr inside them (§14.3)."""
    context = opened(browser, WIDE)
    page = context.new_page()
    try:
        page.goto(address(built))
        page.wait_for_selector(".pair")
        page.wait_for_selector("#foot .film-end-he", state="attached")
        chips = page.evaluate(
            """() => [...document.querySelectorAll('#foot .film-end-he')].map((w) => ({
                 dir: getComputedStyle(w).direction, lang: w.closest('[lang]').lang }))"""
        )
    finally:
        context.close()
    assert chips, "the foot shows the words it would mark"
    assert all(one["dir"] == "rtl" and one["lang"] == "he" for one in chips), chips


def test_a_phone_s_short_controls_reach_a_thumb(browser, tmp_path) -> None:  # noqa: F811
    """P2-7, measured by what the browser hits under a coarse pointer: the speed in the
    row under the picture (37px across) and the title in the bar (33px tall)."""
    reader = two_parts(tmp_path)
    context, page = touch_page(browser, reader / "sec-0001.html")
    try:
        page.wait_for_selector("#video:not([hidden])")
        page.wait_for_timeout(300)
        reach = {s: page.evaluate(REACH, s) for s in (".film-ctl .film-rate",)}
        reach[".bar-title .up"] = page.evaluate(
            REACH.replace("r.top >= 60", "r.top >= 0"), ".bar-title .up"
        )
    finally:
        context.close()
    for selector, measured in reach.items():
        assert not measured.get("missing"), selector
        assert measured["middle"], (selector, measured)
        assert measured["across"] >= 44 and measured["up"] >= 44, (selector, measured)


def test_the_strip_s_listening_view_and_a_line_s_play_reach_a_thumb(
    browser,  # noqa: F811
    tmp_path,
    monkeypatch,
) -> None:
    """P2-7: the foot bar's ⌃ for the Listening view answered 36px across, and a scene
    line's own play 32."""
    from test_reader_browser import dialogue

    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(tmp_path / "dialogues"))
    reader = dialogue(tmp_path / "dialogues", tmp_path / "reader")
    context, page = touch_page(browser, reader)
    try:
        page.wait_for_selector("#player:not([hidden])")
        reach = {
            s: page.evaluate(REACH, s) for s in ("#player > .player-listen", ".pair.voiced .say")
        }
    finally:
        context.close()
    for selector, measured in reach.items():
        assert not measured.get("missing"), selector
        assert measured["middle"], (selector, measured)
        assert measured["across"] >= 44 and measured["up"] >= 44, (selector, measured)


def test_the_turning_arrows_stand_inside_a_phone_s_edges(browser, built: Path) -> None:  # noqa: F811
    """P2-9: on a phone both circles stood on the glass's edges, cut at 0 and 390."""
    context = browser.new_context(viewport=PHONE, reduced_motion="reduce")
    page = context.new_page()
    try:
        page.goto(address(built))
        page.wait_for_selector(".turn:not([hidden]) button")
        edges = page.evaluate(
            """() => [...document.querySelectorAll('.turn button')].map((b) => {
                 const r = b.getBoundingClientRect(); return [r.left, r.right]; })"""
        )
    finally:
        context.close()
    assert edges, "the reader is paged"
    for left, right in edges:
        assert left >= 12 and right <= 390 - 12, edges


def test_a_latin_name_in_a_hebrew_line_is_not_a_word_to_learn(browser, tmp_path) -> None:  # noqa: F811
    """P2-14: "Yair" and "Lapid" in an uploaded podcast's Hebrew title were washed and
    tappable as words to learn. A run with no Hebrew letter in a Hebrew text is not one."""
    reader = video_reader(tmp_path, texts=["שלום Yair Lapid לפיד", "עוד שורה כאן"])
    context = opened(browser, WIDE)
    page = context.new_page()
    try:
        page.goto(address(reader))
        page.wait_for_selector(".pair", state="attached")
        page.wait_for_function("() => document.querySelectorAll('#reader .w').length > 0")
        words = page.evaluate(
            "() => [...document.querySelectorAll('#reader .w')].map((w) => w.textContent)"
        )
    finally:
        context.close()
    assert "Yair" not in words and "Lapid" not in words, words
    assert "שלום" in words and "לפיד" in words, words
