"""Your Words plays a word's sound from the list (targum-internal#498), in a browser.

A beta reader, 2026-10-21, on the Words list's word column: "And be able to play the
sounds here too." Each row, and the word's card, carries the reader card's Hear: the
voice's clip from `/say-word`, which targum pays for and keeps by the word (design.md
§12, "A word said from its card is on targum", 2026-10-07).
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("playwright.sync_api")

from targum.render.builder import list_page  # noqa: E402

TOKEN = "test-key"

#: A clip the page can be handed: a real, silent WAV, so `Audio.play` has something to
#: play rather than a refusal to swallow.
SILENT = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="


@pytest.fixture
def browser(chromium):
    return chromium.browser()


def words_page(browser, width: int, language: str, said: list[dict], two: bool = False):
    html = list_page(TOKEN, "words")

    def answer(route, request):
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        if "/say-word" in request.url:
            said.append(
                {
                    "body": json.loads(request.post_data or "{}"),
                    "key": request.headers.get("x-targum-key"),
                }
            )
            body = json.dumps({"audio": SILENT})
        else:
            body = "{}"
        route.fulfill(status=200, content_type="application/json", body=body)

    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    words = {
        "he": "'עיר': {surface: 'עִיר', status: 1, at: 3}",
        "arc": "'מלכא': {surface: 'מלכא', status: 1, at: 3}",
    }
    if two:
        words["he"] += ", 'ספר': {surface: 'סֵפֶר', status: 1, at: 4}"
    page.add_init_script(
        f"localStorage.setItem('targum:vocab:{language}', JSON.stringify({{{words[language]}}}));"
        f"localStorage.setItem('targum:language', '{language}')"
    )
    # Every voice the page makes, and whether it was stopped, so a test can tell two
    # Hear presses apart from two words said at once.
    page.add_init_script(
        "window.__voices = []; const Real = window.Audio;"
        "window.Audio = function (src) { const a = new Real(src);"
        " const one = { src: src, paused: false };"
        " window.__voices.push(one);"
        " const pause = a.pause.bind(a); a.pause = () => { one.paused = true; pause(); };"
        " return a; };"
    )
    page.route("http://words.test/**", answer)
    page.goto(f"http://words.test/words?k={TOKEN}")
    page.wait_for_selector("#word-rows tr")
    return context, page


@pytest.mark.parametrize("width", [390, 1280])
def test_every_row_plays_its_word_as_the_card_does(browser, width: int) -> None:
    said: list[dict] = []
    context, page = words_page(browser, width, "he", said)
    hear = page.locator("#word-rows tr .word-cell .hear")
    label = hear.get_attribute("aria-label")
    box = hear.bounding_box()
    hear.click()
    page.wait_for_timeout(200)
    card = page.locator('[role="dialog"]:not([hidden])').count()
    # Pressed again, the clip is the one already made: nothing asked twice.
    hear.click()
    page.wait_for_timeout(100)
    # Reachable from the keyboard: a Tab stop of its own, and Enter plays it, without
    # opening the row's card.
    focusable = page.evaluate(
        "(() => { const b = document.querySelector('#word-rows .hear');"
        " b.focus(); return document.activeElement === b; })()"
    )
    before = page.evaluate("window.__voices.length")
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    entered = page.evaluate("window.__voices.length") - before
    card_after_enter = page.locator('[role="dialog"]:not([hidden])').count()
    # One voice at a time: every voice but the last was stopped by the press after it.
    voices = page.evaluate("window.__voices")
    sideways = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    context.close()

    assert label == "Hear עִיר"
    assert said == [{"body": {"text": "עִיר", "language": "he"}, "key": TOKEN}]
    assert card == 0, "the press is the word's sound, not the row's card"
    assert focusable
    assert entered == 1 and card_after_enter == 0, "Enter says the word, and opens nothing"
    assert len(voices) == 3 and all(one["paused"] for one in voices[:-1]), voices
    assert box and box["width"] > 0
    assert not sideways


def test_the_words_card_plays_it_too(browser) -> None:
    said: list[dict] = []
    context, page = words_page(browser, 1280, "he", said)
    page.locator("#word-rows tr .meaning").click()
    page.wait_for_selector('[role="dialog"]:not([hidden]) .hear')
    page.locator('[role="dialog"]:not([hidden]) .hear').click()
    page.wait_for_timeout(200)
    context.close()
    assert said and said[0]["body"] == {"text": "עִיר", "language": "he"}


def test_a_language_the_voice_does_not_read_has_no_button(browser) -> None:
    said: list[dict] = []
    context, page = words_page(browser, 1280, "he", said)
    got = page.evaluate(
        "[!!TargumVocab.hearButton('מלכא', 'arc'), !!TargumVocab.hearButton('Stadt', 'de'),"
        " !!TargumVocab.hearButton('ville', 'fr')]"
    )
    context.close()
    assert got == [False, False, True]


def test_a_second_word_stops_the_first(browser) -> None:
    """Two Hear presses on two rows never say two words at once (qa on #844)."""
    said: list[dict] = []
    context, page = words_page(browser, 1280, "he", said, two=True)
    presses = page.locator("#word-rows tr .word-cell .hear")
    presses.nth(0).click()
    page.wait_for_timeout(150)
    presses.nth(1).click()
    page.wait_for_timeout(150)
    voices = page.evaluate("window.__voices")
    context.close()
    assert len(said) == 2
    assert len(voices) == 2 and voices[0]["paused"] and not voices[1]["paused"], voices
