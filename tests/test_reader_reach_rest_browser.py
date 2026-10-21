"""§8 under a thumb, the rest of READER-04 (known issues §3, 2026-10-12).

targum#766 gave a verse's play, its number and the speed their 44px. The QA log named
four more that a thumb still missed at 390: the strip's scrubber, the video's play, the
word card's × and "Add your meaning". Measured the way `test_reader_reach_browser.py`
measures, by what the browser hits around the control's middle, and with the rule's
other half: the reach may cross a margin, never the words.
"""

# ruff: noqa: F811

from __future__ import annotations

from test_reader_browser import address, browser, video_reader  # noqa: F401
from test_reader_qa_browser import PHONE, opened, served  # noqa: F401
from test_reader_reach_browser import REACH

#: The controls under `sel` that a tap at their middle does not reach: a reach grown over
#: a neighbour takes the taps meant for it.
COVERED = """
(sel) => [...document.querySelectorAll(sel)]
  .filter((e) => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden')
  .filter((e) => {
    const r = e.getBoundingClientRect();
    if (r.bottom < 0 || r.top > innerHeight) return false;
    return !e.contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2));
  })
  .map((e) => e.className || e.textContent)
"""

#: The words of the card's text that a tap lands on something else for: its head, the
#: scale's legend and the line at its foot are read, never pressed through.
UNDER_CARD = """
() => [...document.querySelectorAll('#gloss-card .lemma, #gloss-card .level-legend, #gloss-card p')]
  .filter((e) => e.getClientRects().length)
  .filter((e) => {
    const r = e.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + 4, r.top + r.height / 2);
    return hit && hit.closest('.note-open, .card-x');
  })
  .map((e) => e.textContent.slice(0, 30))
"""


def tap_a_word(page) -> None:
    """Open the word card on the first word of the first verse, as a thumb does."""
    page.tap(".pair.verse .src .w")
    page.wait_for_selector("#gloss-card:not([hidden]) .card-x")
    page.wait_for_timeout(200)


def test_the_scrubber_answers_a_thumb(browser, served: str) -> None:
    context, page = opened(browser, served, PHONE, touch=True)
    try:
        page.evaluate("() => window.TargumPlayer.show()")
        page.wait_for_selector("#player .player-track", state="visible")
        reach = page.evaluate(REACH, "#player .player-track")
        assert not reach.get("missing")
        assert reach["middle"] and reach["up"] >= 44, reach
        assert page.evaluate(COVERED, "#player button") == []
    finally:
        context.close()


def test_the_word_card_s_close_and_add_your_meaning_answer_a_thumb(browser, served: str) -> None:
    context, page = opened(browser, served, PHONE, touch=True)
    try:
        tap_a_word(page)
        shut = page.evaluate(REACH, "#gloss-card .card-x")
        assert shut["middle"] and shut["across"] >= 44 and shut["up"] >= 44, shut
        add = page.evaluate(REACH, "#gloss-card .note-open")
        assert not add.get("missing"), "the card offers Add your meaning"
        assert add["middle"] and add["up"] >= 44, add
        assert page.evaluate(COVERED, "#gloss-card button") == []
        assert page.evaluate(UNDER_CARD) == [], "a reach crosses the card's text"
    finally:
        context.close()


def test_the_video_s_play_answers_a_thumb(browser, tmp_path) -> None:
    built = video_reader(tmp_path, lines=8)
    context = browser.new_context(
        viewport=PHONE, reduced_motion="reduce", has_touch=True, is_mobile=True
    )
    try:
        page = context.new_page()
        page.goto(address(built))
        page.wait_for_selector("#video:not([hidden])")
        page.wait_for_function("() => window.TargumPlayer && window.TargumPlayer.length() > 0")
        page.wait_for_timeout(200)
        reach = page.evaluate(REACH, ".film-ctl .film-play")
        assert not reach.get("missing")
        assert reach["middle"] and reach["across"] >= 44 and reach["up"] >= 44, reach
        assert page.evaluate(COVERED, ".film-ctl button") == []
    finally:
        context.close()
