"""A word's card on a wide window settles without a ResizeObserver loop (beta
triage, 2026-10-21: "ResizeObserver loop completed with undelivered notifications" on
three dialogue scenes, build b6c499af8ab3).

The browser says that when an observer's own callback resizes what it watches before the
frame is painted. `watchGrowth` placed a card again when it grew after opening, and
placing caps a card that has run past its room: it shrank inside the callback that saw
it grow.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")

from test_reader_browser import (  # noqa: E402, F401
    address,
    browser,
    dialogue,
    opened,
)

LOOPS = """
window.__loops = 0;
window.addEventListener("error", function (event) {
  if (/ResizeObserver loop/.test(event.message || "")) window.__loops += 1;
});
"""


@pytest.fixture
def wide(browser, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(tmp_path / "dialogues"))
    built = dialogue(tmp_path / "dialogues", tmp_path / "reader", turns=4, span=1.0, words=True)
    context = opened(browser, viewport={"width": 1280, "height": 560})
    context.add_init_script(LOOPS)
    page = context.new_page()
    page.goto(address(built))
    page.wait_for_function("() => !!document.querySelector('.w')")
    yield page
    context.close()


def test_a_card_that_grows_past_its_room_is_capped_without_a_loop(wide) -> None:
    page = wide
    page.locator(".w").first.click()
    page.wait_for_selector("#gloss-card:not([hidden])")
    # What arrives after the card opens — a verb's root, its forms — and runs it past
    # the room the window has under or over the word.
    page.evaluate(
        """() => {
          const more = document.createElement('div');
          more.style.height = '2000px';
          document.getElementById('gloss-card').appendChild(more);
        }"""
    )
    page.wait_for_timeout(400)
    assert page.evaluate("document.getElementById('gloss-card').style.maxHeight") != ""
    assert page.evaluate("window.__loops") == 0
