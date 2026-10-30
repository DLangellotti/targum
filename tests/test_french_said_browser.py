"""The French "as said" switch in a browser (targum-internal#266): with it on, the page
draws its ties and greys its silent letters, and every word is where it was — the same
text, the same offsets, the same word saved the same way.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

# The fixtures live in the browser module rather than a conftest, so they are imported by
# name to register them here.
from test_french_said import french_page  # noqa: E402
from test_reader_browser import browser, open_reader  # noqa: E402, F401

#: Every word the reader drew, with the offsets it saves by and the lemma it files under.
WORDS = """() => [...document.querySelectorAll('.pair .src .w')].map((w) => [
  w.textContent, w.getAttribute('data-bare'), w.getAttribute('data-lemma'),
])"""
TEXTS = """() => [...document.querySelectorAll('.pair .src')]
  .filter((c) => c.offsetParent).map((c) => c.textContent)"""
TAP = """(text) => [...document.querySelectorAll('.pair .src .w')]
  .find((w) => w.textContent === text).click()"""
#: The reading on the card, once the page has named its language.
READING = """() => {
  const said = document.querySelector('#gloss-card .said bdi');
  return said && said.getAttribute('lang') === 'fr-fonipa' ? said.textContent : null;
}"""


def reading(page, surface: str) -> str:
    page.evaluate(TAP, surface)
    return page.wait_for_function(READING).json_value()


LEDGER = "() => JSON.parse(localStorage.getItem('targum:vocab:fr') || '{}')"


def saved(page, surface: str) -> dict:
    page.keyboard.press("1")
    page.wait_for_function(
        "(n) => Object.keys(JSON.parse(localStorage.getItem('targum:vocab:fr') || '{}'))"
        ".length >= n",
        arg=1,
    )
    entries = page.evaluate(LEDGER)
    entry = next(value for value in entries.values() if value.get("surface") == surface)
    return {key: value for key, value in entry.items() if key not in {"at", "seen", "changed"}}


def test_the_switch_moves_no_word_and_saves_the_same_word(
    browser,  # noqa: F811
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader = french_page(tmp_path / "reader", monkeypatch, on=True)

    context, page = open_reader(browser, reader)
    off_words, off_texts = page.evaluate(WORDS), page.evaluate(TEXTS)
    assert page.evaluate("() => document.body.classList.contains('said-on')") is False
    assert reading(page, "Les") == "lez‿", "the card says les as it is said here, in French"
    off_saved = saved(page, "Les")
    context.close()

    context, page = open_reader(browser, reader)
    page.keyboard.press("n")
    page.wait_for_function("() => document.body.classList.contains('said-on')")
    assert (
        page.evaluate(
            "() => document.querySelector('[data-said-toggle]').getAttribute('aria-pressed')"
        )
        == "true"
    )
    drawn = page.evaluate(
        """() => ({
          ties: [...document.querySelectorAll('.said-tie')].map((s) => [
            s.textContent, s.getAttribute('data-said'),
            getComputedStyle(s, '::after').content,
          ]),
          elided: [...document.querySelectorAll('.said-elide')].map((s) => s.textContent),
          mute: [...document.querySelectorAll('.said-mute')].map((s) => [
            s.textContent, getComputedStyle(s).color,
          ]),
        })"""
    )
    assert drawn["ties"] == [[" ", "z", '"z"'], [" ", "z", '"z"']], "les‿enfants, quelques‿amis"
    assert drawn["elided"] == ["’"]
    assert [text for text, _ in drawn["mute"]] == ["ts", "t", "s", "st", "t", "t", "s", "ts", "nt"]
    assert drawn["mute"][0][1] == "rgb(107, 100, 92)", "muted ink, §4"

    assert page.evaluate(TEXTS) == off_texts, "not a letter added to the text"
    assert page.evaluate(WORDS) == off_words, "every word where it was, filed where it was"
    assert reading(page, "Les") == "lez‿"
    assert saved(page, "Les") == off_saved, "the same word, saved the same way"

    # And off again, the ties are there to be drawn and drawn as nothing.
    page.keyboard.press("n")
    page.wait_for_function("() => !document.body.classList.contains('said-on')")
    tie = page.evaluate(
        "() => getComputedStyle(document.querySelector('.said-tie'), '::after').content"
    )
    assert tie in ("none", "normal")
    assert json.dumps(page.evaluate(WORDS)) == json.dumps(off_words)
    context.close()
