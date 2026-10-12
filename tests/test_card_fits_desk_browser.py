"""The word's card at a desk stands between the bar and the band at the foot (READER-10,
READER-12, QA 2026-10-11).

It stood over the next-page arrow and the words tab, and a verb's card — whose root, forms
and where it was met arrive after it opens — ran past the foot of an 800px window, with
its stages and "ignore" out of reach.
"""

from __future__ import annotations

import pytest
from test_reader_browser import browser  # noqa: F401
from test_reader_qa_browser import DESK, opened, served  # noqa: F401

WHERE = """
() => {
  const box = (el) => {
    if (!el || el.hidden) return null;
    const r = el.getBoundingClientRect();
    return r.height ? [r.top, r.bottom] : null;
  };
  return {
    card: box(document.getElementById('gloss-card')),
    bar: box(document.querySelector('.bar')),
    foot: [document.getElementById('turn'), document.getElementById('list-tab'),
           document.getElementById('player')].map(box).filter(Boolean),
    window: innerHeight,
  };
}
"""

#: Tap the last word drawn on the page, the one with least room under it.
LAST_WORD = """
() => {
  const ws = [...document.querySelectorAll('.pair .w')].filter((w) => {
    const r = w.getBoundingClientRect();
    return w.offsetParent && r.height && r.bottom < innerHeight - 80;
  });
  ws[ws.length - 1].click();
}
"""


@pytest.mark.parametrize("grown", [0, 700], ids=["as-opened", "grown-after"])
def test_the_card_stands_between_the_bar_and_the_foot(browser, served: str, grown: int) -> None:  # noqa: F811
    context, page = opened(browser, served, DESK)
    try:
        page.evaluate(LAST_WORD)
        page.wait_for_selector("#gloss-card:not([hidden])")
        if grown:
            # What a verb's facts do after the card is up: the card grows.
            page.evaluate(
                f"() => {{ const d = document.createElement('div'); d.style.height = '{grown}px';"
                " document.getElementById('gloss-card').appendChild(d); }"
            )
            page.wait_for_timeout(300)
        got = page.evaluate(WHERE)
        assert got["card"], got
        assert got["card"][0] >= got["bar"][1], got
        for foot in got["foot"]:
            if foot[0] > got["bar"][1]:
                assert got["card"][1] <= foot[0], got
        assert got["card"][1] <= got["window"], got
    finally:
        context.close()
