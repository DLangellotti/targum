"""A video transcript follows the voice without fighting itself (2026-10-29).

David, on a YouTube interview whose transcript came from its subtitle file: "sometimes
everything is bouncing up and down", and "the cursor isn't following the words".

A subtitle file times cues, not words, and `ingest.subtitles.refined_from` gives every
word of a cue the cue's clock. A cue runs across sentences, so neighbouring lines' spans
overlap (39 of 48 in the interview's first part). Two rules then answered "which line is
being said" — the first span holding the clock, on every `timeupdate`, and the last span
begun, for the line under the picture — and inside an overlap they named different lines,
so the lit line swapped and the transcript was scrolled to each in turn, four times a
second. And the word clocks lit the first word of each cue for the length of the cue.

These drive the film's clock by hand rather than play it: the fixture film is a second
long, and what is under test is what the page does with a clock, not the decoder.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from test_reader_browser import address, browser, opened, video_reader  # noqa: E402, F401

#: Five words a line: offsets [0,3] [4,9] [10,14] [15,19] [20,23].
LINE = "אחד שתיים שלוש ארבע חמש"
OFFSETS = [[0, 3], [4, 9], [10, 14], [15, 19], [20, 23]]
LINES = 12
#: Each cue is two seconds and holds the last two words of line i and the first three of
#: line i + 1, the shape a subtitle file gives a transcript cut into sentences. Cue i runs
#: from FIRST + 2i, and the first three words of line 0 have a cue of their own before it.
FIRST = 10.0


def cue_clocks() -> tuple[list[list[float]], dict[int, list[list[float]]]]:
    words: dict[int, list[list[float]]] = {}
    spans: list[list[float]] = []
    for i in range(LINES):
        opens = FIRST + 2 * (i - 1)
        closes = FIRST + 2 * i
        rows = [[*OFFSETS[k], opens, closes] for k in range(3)]
        rows += [[*OFFSETS[k], closes, closes + 2] for k in range(3, 5)]
        words[i] = rows
        spans.append([opens, closes + 2])
    return spans, words


#: The share of cue i the last two words of line i take: their letters over the cue's.
TAIL = (4 + 3) / (4 + 3 + 3 + 5 + 4)

#: A clock the test holds, on the page's one film element: what the player reads for
#: where the voice is, and a play that only says it started.
FAKE_CLOCK = """
() => {
  const v = document.querySelector('.video-el');
  window.__t = 0;
  Object.defineProperty(v, 'currentTime', {
    configurable: true, get: () => window.__t, set: (x) => { window.__t = x; },
  });
  Object.defineProperty(v, 'paused', { configurable: true, get: () => false });
  v.play = () => { v.dispatchEvent(new Event('play')); return Promise.resolve(); };
  v.pause = () => {};
  window.__lit = [];
  window.__words = [];
  // Every place the page is moved to, as it is moved: reduced motion makes each scroll
  // land at once, so a back-and-forth inside one tick is seen and not averaged away.
  window.__ys = [];
  for (const name of ['scrollTo', 'scrollBy']) {
    const was = window[name].bind(window);
    window[name] = (...args) => { was(...args); window.__ys.push(window.scrollY); };
  }
  new MutationObserver((changes) => {
    for (const change of changes) {
      const el = change.target;
      const had = (change.oldValue || '').split(/\\s+/);
      if (el.matches('#reader .pair') && el.classList.contains('now') && !had.includes('now')) {
        window.__lit.push(el.getAttribute('data-id'));
      }
      if (el.matches('#reader .w') && el.classList.contains('voiced-now')
          && !had.includes('voiced-now')) {
        window.__words.push(el.textContent);
      }
    }
  }).observe(document.getElementById('reader'), {
    subtree: true, attributes: true, attributeFilter: ['class'], attributeOldValue: true,
  });
}
"""

#: The clock moved to `t` and told, as the element tells it four times a second.
TICK = """
(t) => {
  window.__t = t;
  const v = document.querySelector('.video-el');
  for (let i = 0; i < 3; i++) v.dispatchEvent(new Event('timeupdate'));
}
"""

#: Where every line stands in the document, and which is lit.
STANDING = """
() => {
  const now = document.querySelector('#reader .pair.voiced.now');
  return {
    y: window.scrollY,
    lit: now ? now.getAttribute('data-id') : null,
    word: (document.querySelector('#reader .w.voiced-now') || {}).textContent || null,
    lines: [...document.querySelectorAll('#reader .pair.voiced')].map((p) => {
      const r = p.getBoundingClientRect();
      return [Math.round(r.top + window.scrollY), Math.round(r.height)];
    }),
  };
}
"""


def line_id(i: int) -> str:
    return f"{i + 1:04d}.000-aaaaaa"


def playing(browser, built: Path):  # noqa: F811
    context = opened(browser)
    page = context.new_page()
    page.goto(address(built))
    page.wait_for_selector("#video:not([hidden])")
    page.wait_for_function("() => window.TargumPlayer && window.TargumPlayer.length() > 0")
    page.evaluate(FAKE_CLOCK)
    page.click(".bar .listen")
    page.wait_for_timeout(100)
    return context, page


def at(page, t: float) -> dict:
    page.evaluate(TICK, t)
    # Two frames: the word is read off the clock each frame, and a scroll lands in one.
    page.evaluate("() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))")
    return page.evaluate(STANDING)


def test_overlapping_cues_light_one_line_and_scroll_one_way(browser, tmp_path) -> None:  # noqa: F811
    """Through a run of overlapping spans the lit line only goes forward, each line is
    lit once, the page only scrolls down, and lighting a line moves no line: the band is
    a background, not a size."""
    spans, words = cue_clocks()
    built = video_reader(tmp_path, spans=spans, texts=[LINE] * LINES, words=words)
    context, page = playing(browser, built)
    try:
        page.evaluate("() => { window.__lit = []; window.__ys = []; }")
        seen = []
        t = FIRST - 1.9
        while t < FIRST + 2 * (LINES - 2):
            seen.append(at(page, t))
            t += 0.25
        order = [line_id(i) for i in range(LINES)]
        lit = [order.index(s["lit"]) for s in seen]
        assert lit == sorted(lit), f"the lit line went back: {lit}"
        ys = [s["y"] for s in seen]
        assert ys == sorted(ys), f"the transcript was scrolled back up: {ys}"
        assert ys[-1] > ys[0], "and it did follow the voice down"
        moved = page.evaluate("() => window.__ys")
        assert moved == sorted(moved), f"scrolled up and down again: {moved}"
        swaps = page.evaluate("() => window.__lit")
        assert len(swaps) == len(set(swaps)), f"a line was lit twice: {swaps}"
        assert seen[0]["lines"] == seen[-1]["lines"], "lighting a line moved the lines"
        assert all(s["lines"] == seen[0]["lines"] for s in seen)
    finally:
        context.close()


def test_a_cue_shared_by_two_lines_is_split_by_their_letters(browser, tmp_path) -> None:  # noqa: F811
    """Cue 3 holds the end of line 3 and the start of line 4: line 3 is lit for the share
    of it its letters take, then line 4 — not line 4 from the cue's first instant (the
    last span begun) nor line 3 to its last (the first span holding the clock)."""
    spans, words = cue_clocks()
    built = video_reader(tmp_path, spans=spans, texts=[LINE] * LINES, words=words)
    context, page = playing(browser, built)
    try:
        cue = FIRST + 2 * 3
        assert at(page, cue + 0.1)["lit"] == line_id(3)
        assert at(page, cue + 2 * TAIL - 0.05)["lit"] == line_id(3)
        assert at(page, cue + 2 * TAIL + 0.05)["lit"] == line_id(4)
        assert at(page, cue + 1.9)["lit"] == line_id(4)
        # The line under the picture says the same line the transcript lights.
        assert page.evaluate(
            "() => document.querySelector('#reader .pair.film-said').getAttribute('data-id')"
        ) == line_id(4)
    finally:
        context.close()


def test_a_cue_clock_lights_no_word(browser, tmp_path) -> None:  # noqa: F811
    """A clock five words share is not any one word's (design.md §12: the chip is where
    the recording was aligned word by word), so no word is lit, and the step buttons say
    five seconds rather than a word."""
    spans, words = cue_clocks()
    built = video_reader(tmp_path, spans=spans, texts=[LINE] * LINES, words=words)
    context, page = playing(browser, built)
    try:
        t = FIRST - 1.9
        while t < FIRST + 6:
            assert at(page, t)["word"] is None, t
            t += 0.25
        assert page.evaluate("() => window.__words") == []
        assert page.get_attribute(".more-back", "aria-label") == "Back five seconds"
    finally:
        context.close()


def test_a_word_with_its_own_clock_is_lit_as_it_is_said(browser, tmp_path) -> None:  # noqa: F811
    """Where each word has its own clock the chip walks the line with the clock, one
    word at a time, and steps back and on a word."""
    starts = [FIRST + 0.4 * k for k in range(5)]
    words = {0: [[*OFFSETS[k], starts[k], starts[k] + 0.35] for k in range(5)]}
    built = video_reader(tmp_path, spans=[[FIRST, FIRST + 2.0]], texts=[LINE, LINE], words=words)
    context, page = playing(browser, built)
    try:
        said = LINE.split(" ")
        for k in range(5):
            seen = at(page, starts[k] + 0.1)
            assert seen["word"] == said[k], (k, seen["word"])
            assert seen["lit"] == line_id(0)
        assert page.evaluate("() => window.__words") == said
        assert page.get_attribute(".more-back", "aria-label") == "Back a word"
    finally:
        context.close()
