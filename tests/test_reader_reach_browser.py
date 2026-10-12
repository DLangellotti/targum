"""§8 on a portion's reader under a thumb (READER-04, QA 2026-10-11).

"Play this line", the verse's number and the speed answered a tap over 22×22, 22×15 and
38×26 at 390. Measured the way a thumb lands, by what the browser hits, not by the size
of the drawing: a reach a stylesheet promises can be clipped, or drawn under the text.
"""

from __future__ import annotations

from test_reader_browser import browser  # noqa: F401
from test_reader_qa_browser import PHONE, opened, served  # noqa: F401

#: How far a control answers a tap along the row and the column through its middle: the
#: run of points around the middle that land on it, end to end.
REACH = """
(sel) => {
  const el = [...document.querySelectorAll(sel)].find((e) => {
    const r = e.getBoundingClientRect();
    return r.width && r.height && r.top >= 60 && r.bottom <= innerHeight;
  });
  if (!el) return {missing: true};
  const r = el.getBoundingClientRect();
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  const hits = (px, py) => el.contains(document.elementFromPoint(px, py));
  const run = (dx, dy) => {
    let n = 0;
    while (n < 60 && hits(x + dx * (n + 1), y + dy * (n + 1))) n++;
    return n;
  };
  return {
    middle: hits(x, y),
    across: run(1, 0) + run(-1, 0) + 1,
    up: run(0, 1) + run(0, -1) + 1,
  };
}
"""

#: The words of the verse drawn level with its play, and near it.
UNDER = """
() => {
  const say = document.querySelector('.pair.verse.voiced .say');
  const pair = say.closest('.pair');
  const r = say.getBoundingClientRect();
  const near = (b) => b.right > r.left - 2 && b.left < r.right + 2
    && b.bottom > r.top && b.top < r.bottom;
  return [...pair.querySelectorAll('.src .w')]
    .filter((w) => w.offsetParent && [...w.getClientRects()].some(near))
    .map((w) => w.textContent);
}
"""


def test_a_verse_s_play_its_number_and_the_speed_answer_a_thumb(browser, served: str) -> None:  # noqa: F811
    context, page = opened(browser, served, PHONE, touch=True)
    try:
        for selector in (".pair.verse.voiced .say", ".pair.verse .verse-number"):
            reach = page.evaluate(REACH, selector)
            assert not reach.get("missing"), selector
            assert reach["middle"], f"{selector} is under something else at its middle"
            assert reach["across"] >= 44 and reach["up"] >= 44, (selector, reach)
        assert page.evaluate(UNDER) == [], "the verse runs under its play"

        page.evaluate("() => window.TargumPlayer.show()")
        page.wait_for_selector("#player .player-rate-now")
        speed = page.evaluate(REACH, "#player .player-rate-now")
        assert speed["middle"] and speed["across"] >= 44 and speed["up"] >= 42, speed
    finally:
        context.close()
