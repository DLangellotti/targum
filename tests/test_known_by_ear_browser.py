"""Known by ear on the reader's word card, in a browser (targum-internal#536).

design.md §12, "A word can be known by ear, and only the reader says so" (2026-11-14): a
toggle on its own line under the five stages, a thumb tall, which writes the ear mark
alone and which a second press takes back. The stage and the text's figures stay the
reading marks. Measured the way `test_reader_reach_browser.py` measures.
"""

# ruff: noqa: F811

from __future__ import annotations

from test_reader_browser import browser  # noqa: F401
from test_reader_qa_browser import PHONE, opened, served  # noqa: F401
from test_reader_reach_browser import REACH
from test_reader_reach_rest_browser import tap_a_word

#: The word the card was opened for, as the reader's store keeps it.
STORED = """
() => Object.assign({}, ...Object.keys(localStorage)
  .filter((key) => key.startsWith('targum:vocab:'))
  .map((key) => JSON.parse(localStorage.getItem(key) || '{}')))
"""

#: Where the toggle stands: under the scale and its legend, and before the field.
ORDER = """
() => {
  const box = document.querySelector('#gloss-card .vocab-editor');
  const at = (name) => [...box.children].findIndex((e) => e.classList.contains(name));
  return {scale: at('levels'), legend: at('level-legend'), stage: at('card-stage'),
          ear: at('ear-toggle'), field: at('note-open')};
}
"""


def test_the_card_s_known_by_ear_answers_a_thumb_and_writes_the_mark_alone(
    browser, served: str
) -> None:
    context, page = opened(browser, served, PHONE, touch=True)
    try:
        tap_a_word(page)
        toggle = page.locator("#gloss-card .ear-toggle")
        assert toggle.count() == 1
        assert toggle.inner_text() == "Known by ear"
        assert toggle.get_attribute("aria-pressed") == "false"
        order = page.evaluate(ORDER)
        # On the phone sheet the legend stands in a line of its own with ignore, which the
        # reader builds under the scale (`card-stage`); the toggle comes after either.
        legend = order["legend"] if order["legend"] >= 0 else order["stage"]
        assert order["scale"] < legend < order["ear"] < order["field"], order
        page.evaluate(
            "() => document.querySelector('#gloss-card .ear-toggle')"
            ".scrollIntoView({block: 'center'})"
        )
        reach = page.evaluate(REACH, "#gloss-card .ear-toggle")
        assert reach["middle"] and reach["up"] >= 44, reach

        before = page.evaluate(STORED)
        figure = page.evaluate("() => (document.querySelector('#known-count') || {}).textContent")
        toggle.tap()
        assert toggle.get_attribute("aria-pressed") == "true"
        after = page.evaluate(STORED)
        marked = [lemma for lemma, word in after.items() if word.get("ear") == 1]
        assert len(marked) == 1, after
        word = after[marked[0]]
        assert word["status"] is None, "known by ear is not a stage"
        assert word["at"] == 0, "and the word is not saved by it"
        assert marked[0] not in before or before[marked[0]].get("status") == word["status"]
        assert (
            page.evaluate("() => (document.querySelector('#known-count') || {}).textContent")
            == figure
        ), "the text's known figure is the reading one"

        toggle.tap()
        assert toggle.get_attribute("aria-pressed") == "false"
        assert marked[0] not in page.evaluate(STORED), "a second press takes it back"
    finally:
        context.close()
