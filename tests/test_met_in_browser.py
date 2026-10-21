"""Your Words' "Met in" opens the text at the word (targum-internal#497), in a browser.

A beta reader, 2026-10-21, on the column's "2 texts": "link the full text here so when
looking at the word, I can find it immediately in the conversation/dialogue etc." The
press lists the texts; each opens its reader at the sentence, with the word marked.
"""

# The fixtures are imported by name from the browser module, which ruff reads as
# redefinitions wherever a test takes one as an argument.
# ruff: noqa: F811

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from test_reader_browser import (  # noqa: E402, F401
    VERSES,
    address,
    browser,
    built,
    coin,
    opened,
)

from targum.render.builder import list_page  # noqa: E402

TOKEN = "test-key"

#: The sentence the link lands on, far enough down that landing there is a move.
AT = 40


def lemma_in(n: int, i: int) -> str:
    """The `i`th word of sentence `n` in `test_reader_browser.chapter`, as it mints them."""
    minted = sum(14 if k % 3 else 42 for k in range(n))
    return coin(minted + i)


def test_the_reader_opens_at_the_sentence_with_the_word_marked(browser, built: Path) -> None:
    assert AT < VERSES
    word = lemma_in(AT, 2)
    segment = f"{AT:04d}.000-aaaaaa"
    context = opened(browser)
    page = context.new_page()
    page.goto(address(built) + "?met=" + word + "#" + segment)
    page.wait_for_selector(".w.met-here")
    got = page.evaluate(
        """() => {
          const marked = [...document.querySelectorAll('.w.met-here')];
          const box = marked[0].getBoundingClientRect();
          const look = getComputedStyle(marked[0]);
          return {
            count: marked.length,
            pair: marked[0].closest('.pair').getAttribute('data-id'),
            index: Number(marked[0].getAttribute('data-lemma')),
            seen: box.top >= 0 && box.bottom <= window.innerHeight,
            ring: look.boxShadow,
          };
        }"""
    )
    lemmas = page.evaluate("JSON.parse(document.getElementById('targum-data').textContent).lemmas")
    context.close()
    assert got["count"] == 1, "the word's first time round in that sentence, once"
    assert got["pair"] == segment
    assert lemmas[got["index"]] == word
    assert got["seen"], "the page opens where the word is"
    assert "inset" in got["ring"], "a ring as well as a wash: never colour alone"


def test_without_a_word_named_nothing_is_marked(browser, built: Path) -> None:
    context = opened(browser)
    page = context.new_page()
    page.goto(address(built) + f"#{AT:04d}.000-aaaaaa")
    page.wait_for_selector(".pair .w")
    count = page.evaluate("document.querySelectorAll('.w.met-here').length")
    context.close()
    assert count == 0


@pytest.mark.parametrize("width", [390, 1280])
def test_met_in_lists_the_texts_and_each_opens_at_the_word(browser, width: int) -> None:
    html = list_page(TOKEN, "words")
    facts = {"signedIn": True, "met": {"עיר": 2}, "often": 2, "notes": {}, "practise": []}
    met = {
        "signedIn": True,
        "texts": [
            {
                "title": "רות",
                "chapter": 2,
                "name": "ruth",
                "href": "/reader/ruth/reader/sec-0002.html?met=%D7%A2%D7%99%D7%A8#2:1",
            },
            {
                "title": "A Talk",
                "chapter": 0,
                "name": "talk",
                "href": "/reader/talk/reader/index.html?met=x#s1",
            },
        ],
        "more": 3,
    }
    asked: list[str] = []

    def answer(route, request):
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        if "/account/met" in request.url:
            asked.append(request.url)
            body = json.dumps(met)
        elif "/account/words" in request.url:
            body = json.dumps(facts)
        else:
            body = "{}"
        route.fulfill(status=200, content_type="application/json", body=body)

    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    page.add_init_script(
        "localStorage.setItem('targum:vocab:he', JSON.stringify({"
        "'עיר': {surface: 'עיר', status: 1, at: 3}}));"
        "localStorage.setItem('targum:language', 'he')"
    )
    page.route("http://words.test/**", answer)
    page.goto(f"http://words.test/words?k={TOKEN}")
    page.wait_for_selector("#word-rows .met-open:visible")
    press = page.locator("#word-rows .met-open:visible")
    label = press.text_content()
    press.click()
    page.wait_for_selector(".met-texts a")
    got = page.evaluate(
        """() => ({
          links: [...document.querySelectorAll('.met-texts a')].map((a) => [
            a.textContent, a.getAttribute('href'),
          ]),
          more: document.querySelector('.met-row .met-note').textContent,
          expanded: document.querySelector('#word-rows .met-open[aria-expanded="true"]') !== null,
          focused: document.activeElement.classList.contains('met-open'),
          card: !!document.querySelector('[role="dialog"]:not([hidden])'),
          sideways: document.documentElement.scrollWidth > window.innerWidth,
        })"""
    )
    shots = os.environ.get("TARGUM_SHOTS")
    if shots:
        page.screenshot(path=f"{shots}/met-in-{width}.png", full_page=True)
    # A second press folds it, and asks nothing more.
    page.locator("#word-rows .met-open:visible").click()
    page.wait_for_timeout(100)
    folded = page.locator(".met-row").count()
    context.close()

    assert label == ("met in 2 texts" if width <= 640 else "2 texts")
    assert len(asked) == 1 and "lemma=%D7%A2%D7%99%D7%A8" in asked[0]
    assert got["links"] == [
        [
            "רות · chapter 2",
            f"/reader/ruth/reader/sec-0002.html?met=%D7%A2%D7%99%D7%A8&k={TOKEN}#2:1",
        ],
        ["A Talk", f"/reader/talk/reader/index.html?met=x&k={TOKEN}#s1"],
    ], "the pass key goes before the sentence, not after it"
    assert got["more"] == "And 3 more texts."
    assert got["expanded"] and got["focused"], got
    assert not got["card"], "the press is the list's, not the row's card"
    assert not got["sideways"]
    assert folded == 0
