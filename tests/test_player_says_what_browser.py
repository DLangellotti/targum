"""The desk player says what each press does (known issues §3, 2026-10-12).

At a desk the strip was a row of glyphs — ×, ↓, ^, +, 1×, −, two steps and a square —
and "Hear first", and only some of them had a name. Every press on it now has a name a
screen reader says and a title the pointer shows, in the page's language.
"""

from __future__ import annotations

from test_reader_browser import browser  # noqa: F401
from test_reader_qa_browser import DESK, opened, served  # noqa: F401

NAMES = """
() => [...document.querySelectorAll('#player button, #player a')]
  .filter((el) => el.getBoundingClientRect().width > 0)
  .map((el) => ({
    cls: el.className,
    name: (el.getAttribute('aria-label') || el.textContent || '').trim(),
    title: (el.getAttribute('title') || '').trim(),
  }))
"""


def test_every_press_on_the_desk_player_is_named_and_titled(browser, served: str) -> None:  # noqa: F811
    context, page = opened(browser, served, DESK)
    try:
        page.evaluate("() => window.TargumPlayer.show()")
        page.wait_for_selector("#player .player-play")
        presses = page.evaluate(NAMES)
        group = page.get_attribute("#player", "aria-label")
    finally:
        context.close()
    assert len(presses) >= 6, presses
    unnamed = [p for p in presses if not p["name"] or not p["title"]]
    assert unnamed == [], unnamed
    play = next(p for p in presses if "player-play" in p["cls"])
    assert play["name"] == play["title"] == group and play["name"].startswith("Play ")
