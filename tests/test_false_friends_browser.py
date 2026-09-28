"""A false friend on the card, and only for a French text read into English
(targum-internal#267)."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

# The fixtures live in the browser module rather than a conftest, so they are
# imported by name to register them here; the French page is the list's own test's.
from test_false_friends import reader  # noqa: E402
from test_reader_browser import SWITCH, browser, open_reader  # noqa: E402, F401

from targum.annotate.false_friends import ENV, friend_of  # noqa: E402

#: Asked after a turn of the event loop: the line is added by the page's observer of the
#: card, once the card is drawn.
FRIEND = """
async (text) => {
  [...document.querySelectorAll('.w')].find((w) => w.textContent === text).click();
  await new Promise((done) => setTimeout(done));
  const line = document.querySelector('.gloss-card .false-friend');
  return line ? line.textContent : null;
}
"""


def test_the_card_names_a_false_friend_only_for_french_read_into_english(
    browser,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With `TARGUM_FALSE_FRIENDS` on: into English the line is there, into Russian it is
    not, and a text that is not French carries none."""
    monkeypatch.setenv(ENV, "1")
    context, page = open_reader(browser, reader(tmp_path / "fr", "fr"))
    means = friend_of("actuellement")[1]
    assert page.evaluate(FRIEND, "actuellement") == f"false friend: not actually — {means}"
    looks = "() => document.querySelector('.gloss-card .false-friend i').textContent"
    assert page.evaluate(looks) == "actually", "the look-alike is set apart"
    page.keyboard.press("Escape")
    page.evaluate(SWITCH, "t1")
    assert page.evaluate(FRIEND, "actuellement") is None, "read into Russian"
    context.close()
    # The same word on a page that is not French says nothing: the list is English–French.
    context, page = open_reader(browser, reader(tmp_path / "it", "it"))
    assert page.evaluate(FRIEND, "actuellement") is None
    context.close()
