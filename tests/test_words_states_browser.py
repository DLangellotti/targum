"""Your Words, Your Phrases and the Grammar tab, in a real browser (design.md §14, line 8;
Your Words QA, 2026-10-20, targum-internal#467).

Each state the QA drew at desk and phone width is pinned here, so the next change cannot
quietly undo it: the wait said, and said again past three seconds; a reader with no words
given the page itself, with the line that says what fills it and a way to the Library,
and no stage tabs, column heads or exports over nothing; a refusal and being offline
each said in words rather than as "Nothing here yet"; the tab's count grouped as the
head's is; the Grammar tab titled, its refusal said as one rather than as "Grammar
practice is in Hebrew for now", its first draw leaving the keyboard and the scroll where
they were, a round walked by keyboard alone, every Hebrew answer carrying its lang and
direction, the verdicts said in Russian under the Russian interface, and the presses a
thumb uses reaching 44px.

The pages are the ones the server renders (`list_page`); the account's answers are
routes. Skips itself without Playwright and its Chromium, as the other browser tests do.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from targum.render.builder import list_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://words.test"
EMAIL = "r@x.test"
ME = {
    "signedIn": True,
    "email": EMAIL,
    "initials": "R",
    "readsSaid": True,
    "reads": ["en"],
    "language": "he",
    "learning": ["he"],
    "interest": ["news"],
}

ITEM = {
    "key": "k1",
    "spot": "binyan",
    "example": False,
    "title": "השליח",
    "line": "אֲנִי יוֹדֵעַ.",
    "start": 5,
    "end": 12,
    "translation": "I know.",
    "ask": "Which binyan is this verb in?",
    "options": ["פעל", "פיעל"],
    "answer": 0,
    "said": "פעל",
    "rule": "The binyan is the pattern of letters and vowels around the root.",
    "contrast": {"line": "אֲנִי מְדַבֵּר.", "start": 5, "end": 13, "said": "פיעל"},
}
PRACTICE = {
    "signedIn": True,
    "spots": [
        {
            "key": "binyan",
            "kind": "choice",
            "ready": True,
            "encounters": 12,
            "texts": 3,
            "needs": {"encounters": 6, "texts": 2},
        },
        {
            "key": "stress",
            "kind": "choice",
            "ready": False,
            "encounters": 0,
            "texts": 0,
            "needs": {"encounters": 6, "texts": 2},
        },
    ],
    "round": {
        "spot": "binyan",
        "items": [
            {**ITEM, "key": "k0", "example": True},
            ITEM,
            {**ITEM, "key": "k2"},
        ],
    },
}


@pytest.fixture(scope="module")
def browser():
    try:
        driver = playwright_api.sync_playwright().start()
    except Exception as why:  # pragma: no cover - environment, not behaviour
        pytest.skip(f"Playwright will not start: {why}")
    try:
        running = driver.chromium.launch()
    except Exception as why:  # pragma: no cover - the browser itself is not installed
        driver.stop()
        pytest.skip(f"no Chromium: run `playwright install chromium` ({why})")
    yield running
    running.close()
    driver.stop()


def words(count: int) -> dict[str, Any]:
    """A Hebrew ledger of `count` words, every one still being learned."""
    letters = "אבגדהוזחטיכלמנסעפצקרשת"
    out: dict[str, Any] = {}
    for n in range(count):
        lemma = letters[n % 22] + letters[n // 22 % 22] + letters[n // 484 % 22]
        out[lemma] = {"status": 1 + n % 3, "at": 1_760_000_000_000 - n, "seen": 1}
    return out


def open_page(
    browser,
    which: str,
    answers: dict[str, Any],
    *,
    phone: bool = False,
    offline: bool = False,
    ledger: dict[str, Any] | None = None,
    language: str = "en",
):
    """A list page, with `answers` by path: a dict is JSON, an int a bare status, "abort"
    a dropped connection and "hold" an answer that never comes."""
    html = list_page("", which, language=language)
    held: list = []

    def answer(route, request):
        path = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        said = answers.get(path, ME if path == "/account/me" else {"signedIn": True})
        if said == "abort":
            return route.abort("internetdisconnected")
        if said == "hold":
            return held.append(route)
        if isinstance(said, int):
            return route.fulfill(status=said, content_type="application/json", body="{}")
        route.fulfill(status=200, content_type="application/json", body=json.dumps(said))

    size = {"width": 390, "height": 844} if phone else {"width": 1440, "height": 900}
    extra = {"is_mobile": True, "has_touch": True} if phone else {}
    context = browser.new_context(viewport=size, reduced_motion="reduce", **extra)
    unplugged = "Object.defineProperty(Navigator.prototype, 'onLine', {get: () => false});"
    kept = ""
    if ledger is not None:
        state = {"email": EMAIL, "revision": 1, "pushed": 1}
        kept = (
            f"localStorage.setItem('targum:sync', {json.dumps(json.dumps(state))});"
            f"localStorage.setItem('targum:vocab:he', "
            f"{json.dumps(json.dumps(ledger, ensure_ascii=False))});"
        )
    context.add_init_script(
        "localStorage.setItem('targum:language', 'he');"
        "localStorage.setItem('targum:learning', '[\"he\"]');"
        + kept
        + (unplugged if offline else "")
    )
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    return context, page, thrown, held, f"{SITE}/{which}"


def test_the_wait_for_words_is_said_and_said_again_after_three_seconds(browser) -> None:
    context, page, thrown, held, url = open_page(browser, "words", {"/account/me": "hold"})
    page.clock.install()
    page.goto(url)
    waiting = page.locator("#home-waiting")
    assert waiting.is_visible()
    assert waiting.inner_text() == "Opening your words…"
    page.clock.run_for(3100)
    assert waiting.inner_text() == "We're still opening your words."
    assert page.locator("#nothing").is_hidden()
    assert not thrown
    context.close()


@pytest.mark.parametrize("phone", [False, True], ids=["desk", "phone"])
def test_a_reader_with_no_words_gets_the_page_and_a_way_on(browser, phone: bool) -> None:
    context, page, thrown, _, url = open_page(browser, "words", {}, phone=phone)
    page.goto(url)
    page.wait_for_selector("#page:not([hidden])")
    empty = page.locator("#words-empty")
    empty.wait_for(state="visible")
    assert "Tap a word as you go" in empty.inner_text()
    go = empty.locator("a.empty-go")
    assert go.inner_text() == "Find something to read"
    assert go.get_attribute("href").startswith("/library")
    # Nothing drawn over nothing: no stages, no column heads, no deck of no words.
    assert page.locator("#stage-chips").is_hidden()
    assert page.locator("#word-table").is_hidden()
    assert page.locator("#export-anki").is_hidden()
    assert page.locator("#export-words").is_hidden()
    assert page.locator("#nothing").is_hidden()
    assert page.locator("#home-waiting").is_hidden()
    if phone:
        assert go.bounding_box()["height"] >= 44
    assert page.evaluate("document.scrollingElement.scrollWidth <= innerWidth")
    assert not thrown
    context.close()


@pytest.mark.parametrize("phone", [False, True], ids=["desk", "phone"])
def test_a_refusal_is_said_with_try_again_not_as_nothing_yet(browser, phone: bool) -> None:
    context, page, thrown, _, url = open_page(
        browser, "words", {"/account/me": 500, "/sync": 500}, phone=phone
    )
    page.goto(url)
    nothing = page.locator("#nothing")
    nothing.wait_for(state="visible")
    assert page.locator("#nothing-lede").inner_text() == "We couldn't load your words."
    assert "Nothing here yet" not in nothing.inner_text()
    again = page.locator("#nothing-again")
    assert again.is_visible()
    if phone:
        assert again.bounding_box()["height"] >= 44
    assert page.locator("#home-waiting").is_hidden()
    assert not thrown
    context.close()


def test_offline_is_said_as_offline(browser) -> None:
    context, page, thrown, _, url = open_page(
        browser, "phrases", {"/account/me": "abort", "/sync": "abort"}, offline=True
    )
    page.goto(url)
    page.locator("#nothing").wait_for(state="visible")
    assert page.locator("#nothing-lede").inner_text() == "You're offline."
    assert "back online" in page.locator("#nothing-says").inner_text()
    # The bar's banner carries the one Try again; the page asks again when back online.
    assert page.locator("#nothing-again").is_hidden()
    assert not thrown
    context.close()


def test_words_kept_here_draw_at_once_and_the_tab_count_is_grouped(browser) -> None:
    context, page, thrown, _, url = open_page(
        browser, "words", {"/account/me": "hold"}, ledger=words(1200)
    )
    page.goto(url)
    page.wait_for_selector("#page:not([hidden])")
    assert page.locator("#home-waiting").is_hidden()
    assert page.locator("#count-words").inner_text() == "1,200"
    assert page.locator("#words-summary").inner_text().startswith("1,200 on your list")
    assert page.locator("#word-rows tr").count() == 200
    assert not thrown
    context.close()


def test_a_fresh_browser_draws_the_accounts_words_without_loading_again(browser) -> None:
    """The words the account brings are drawn from this browser once they land: the page
    loaded itself a second time for them, which took a phone's first visit from 1.3 s to
    3.2 s (Your Words QA, 2026-10-20)."""
    pulled = [
        {
            "language": "he",
            "lemma": lemma,
            "status": 2,
            "surface": lemma,
            "band": 1,
            "learned": 0,
            "at": 100 + n,
            "seen": 200,
            "gone": 0,
        }
        for n, lemma in enumerate(["ספר", "דרך", "עיר"])
    ]
    context, page, thrown, _, url = open_page(
        browser, "words", {"/sync": {"revision": 3, "words": pulled}}
    )
    loads: list[str] = []
    page.on(
        "framenavigated",
        lambda frame: loads.append(frame.url) if frame == page.main_frame else None,
    )
    page.goto(url)
    page.wait_for_selector("#word-rows tr")
    page.wait_for_timeout(500)
    assert len(loads) == 1, loads
    assert page.locator("#word-rows tr").count() == 3
    assert page.locator("#home-waiting").is_hidden()
    assert not thrown
    context.close()


def test_the_way_back_and_the_exports_reach_44px_under_a_thumb(browser) -> None:
    context, page, thrown, _, url = open_page(browser, "words", {}, phone=True, ledger=words(3))
    page.goto(url)
    page.wait_for_selector("#export-anki:not([hidden])")
    for selector in (".words-back", "#export-anki", "#export-words", "#search"):
        box = page.locator(selector).bounding_box()
        assert box and box["height"] >= 44, selector
    assert page.locator("#export-words").bounding_box()["width"] >= 44
    assert not thrown
    context.close()


def test_the_grammar_wait_is_said_and_said_again(browser) -> None:
    context, page, thrown, _, url = open_page(browser, "grammar", {"/account/practice": "hold"})
    page.clock.install()
    page.goto(url)
    waiting = page.locator("#home-waiting")
    assert waiting.inner_text() == "Opening your practice…"
    page.clock.run_for(3100)
    assert waiting.inner_text() == "We're still opening your practice."
    assert not thrown
    context.close()


def test_a_grammar_refusal_is_a_refusal(browser) -> None:
    context, page, thrown, _, url = open_page(browser, "grammar", {"/account/practice": 500})
    page.goto(url)
    page.locator("#nothing").wait_for(state="visible")
    assert page.locator("#nothing-lede").inner_text() == "We couldn't load your practice."
    assert page.locator("#nothing-again").is_visible()
    assert "in Hebrew for now" not in page.inner_text("body")
    assert not thrown
    context.close()


@pytest.mark.parametrize("phone", [False, True], ids=["desk", "phone"])
def test_a_round_by_keyboard_with_every_hebrew_answer_marked(browser, phone: bool) -> None:
    context, page, thrown, _, url = open_page(
        browser, "grammar", {"/account/practice": PRACTICE}, phone=phone
    )
    page.goto(url)
    page.wait_for_selector("#grammar-round:not([hidden])")
    assert page.title().startswith("Grammar")
    # The first draw moves nothing: no focus taken, no phone scrolled to the card.
    assert page.evaluate("document.activeElement === document.body")
    assert page.evaluate("scrollY") == 0
    go = page.locator(".grammar-go")
    assert go.get_attribute("aria-label") == "Practise Root and binyan"

    def hebrew_runs_marked() -> None:
        bare = page.evaluate(
            """() => {
              const hebrew = (n) => n.nodeType === 3 && /[\\u0590-\\u05FF]/.test(n.textContent);
              const lang = (e) => (e.closest('[lang]') || { getAttribute: () => '' })
                .getAttribute('lang');
              return [...document.querySelectorAll('#grammar-round *')]
                .filter((e) => [...e.childNodes].some(hebrew))
                .filter((e) => !/^he/.test(lang(e) || '') || !e.closest('[dir]'))
                .map((e) => e.className + ':' + e.textContent.slice(0, 12));
            }"""
        )
        assert not bare, bare

    hebrew_runs_marked()
    start = page.locator(".grammar-next")
    if phone:
        box = start.bounding_box()
        assert box["width"] >= 44 and box["height"] >= 44
    start.focus()
    page.keyboard.press("Enter")
    assert "grammar-option" in page.evaluate("document.activeElement.className")
    page.keyboard.press("Enter")  # the first answer, which is right
    assert "grammar-next" in page.evaluate("document.activeElement.className")
    assert page.locator(".grammar-verdict").inner_text() == "Yes, פעל."
    hebrew_runs_marked()
    page.keyboard.press("Enter")
    page.keyboard.press("Tab")  # the second answer, which is wrong
    page.keyboard.press("Enter")
    assert page.locator(".grammar-verdict").inner_text() == "It's פעל here."
    page.keyboard.press("Enter")
    assert page.locator(".grammar-done").is_visible()
    assert "grammar-again" in page.evaluate("document.activeElement.className")
    assert page.evaluate("document.scrollingElement.scrollWidth <= innerWidth")
    assert not thrown
    context.close()


def test_the_verdicts_are_said_in_russian(browser) -> None:
    context, page, thrown, _, url = open_page(
        browser, "grammar", {"/account/practice": PRACTICE}, language="ru"
    )
    page.goto(url)
    page.wait_for_selector("#grammar-round:not([hidden])")
    assert page.locator(".grammar-verdict").inner_text() == "Здесь — פעל."
    assert page.locator(".grammar-other").inner_text() == "Где — פיעל:"
    assert page.title().startswith("Грамматика")
    assert not thrown
    context.close()
