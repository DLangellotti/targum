"""The Library's states, in a real browser (design.md §14, line 8; Library QA, 2026-10-20,
targum-internal#465).

Each state the QA drew at desk and phone width is pinned here, so the next change cannot
quietly undo it: the wait said, and said again past three seconds; a refusal, a dropped
connection and being offline each said in words, with the press that asks again where it
is ours to give; the shelf's own file failing said as a failure rather than as an empty
language; a band with nothing in it said as a band and not as a search that missed; no
"0% known" before any word is marked; a Hebrew byline carrying its language and its
direction; and See all's presses reaching 44px under a thumb.

The page is the one the server renders (`library_page`), linked to its files as a desk
page is once they are kept; `conftest.py` answers the files. The account's
answers are routes. Skips itself without Playwright and its Chromium, as the other browser
tests do.
"""

from __future__ import annotations

import dataclasses
import json
import re
from typing import Any

import pytest

from targum.catalogue import everything
from targum.render.builder import library_page, read_as_portions

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://library.test"


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


@pytest.fixture(scope="module")
def page_html() -> str:
    return library_page("")


def library(
    browser,
    html: str,
    answers: dict[str, Any],
    *,
    phone: bool = False,
    offline: bool = False,
    hash: str = "",
    lose_shelf: bool = False,
    language: str = "he",
    stored: bool = True,
    learns: tuple[str, ...] = (),
):
    """The Library, with `answers` by path: a dict is JSON, an int a bare status, "abort"
    a dropped connection and "hold" an answer that never comes."""
    held: list = []
    if lose_shelf:
        # An address the server never made, so the conftest's desk files do not answer it
        # and the route below refuses it: the shelf's file failing to arrive.
        nowhere = "/assets/catalogue.0000000000000000.json"
        html = re.sub(r"/assets/catalogue\.[0-9a-f]+\.json", nowhere, html)

    def answer(route, request):
        path = request.url[len(SITE) :].split("?")[0].split("#")[0]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        if path.startswith("/assets/") and path not in answers:
            # Every file the page names is answered by `conftest.py`; this is what is not.
            return route.abort("failed")
        said = answers.get(path, {})
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
    # The languages the account says are learned, as `sync.js` mirrors them.
    learning = json.dumps(sorted({"he", language, *learns}))
    # `stored=False` is a browser that has never been told either.
    kept = (
        f"localStorage.setItem('targum:language', '{language}');"
        f"localStorage.setItem('targum:learning', '{learning}');"
    )
    context.add_init_script((kept if stored else "") + (unplugged if offline else ""))
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    return context, page, thrown, held, f"{SITE}/library{hash}"


def built(known: float, count: int = 400) -> list[dict[str, Any]]:
    """Hebrew catalogue texts on the shared shelf, each known at `known`."""
    entries = [e for e in everything() if e.language == "he" and not read_as_portions(e)]
    return [
        {
            "name": f"shared-{n}-he",
            "document": f"{n:064d}",
            "title": entry.title,
            "language": "he",
            "entry": entry.id,
            "shared": True,
            "known": known,
            "words": 100,
            "sections": 1,
            "chapters": [],
        }
        for n, entry in enumerate(entries[:count])
    ]


def test_the_wait_is_said_and_said_again_after_three_seconds(browser, page_html) -> None:
    context, page, thrown, held, url = library(browser, page_html, {"/readers": "hold"})
    page.clock.install()
    page.goto(url)
    waiting = page.locator("#lib-waiting")
    assert waiting.is_visible()
    assert waiting.inner_text() == "Opening the Library…"
    page.clock.run_for(3100)
    assert waiting.inner_text() == "We're still opening the Library."
    assert page.locator("#lib-fault").is_hidden()
    assert not thrown
    context.close()


@pytest.mark.parametrize("phone", [False, True], ids=["desk", "phone"])
def test_a_refusal_is_said_with_try_again_not_drawn_as_empty_shelves(
    browser, page_html, phone
) -> None:
    context, page, thrown, _, url = library(browser, page_html, {"/readers": 500}, phone=phone)
    page.goto(url)
    fault = page.locator("#lib-fault")
    fault.wait_for(state="visible")
    assert page.locator("#lib-fault-lede").inner_text() == "We couldn't open the Library."
    again = page.locator("#lib-fault-again")
    assert again.is_visible()
    # The panel every surface draws (errors QA, targum-internal#468), with Tell us.
    assert "fault-panel" in (fault.get_attribute("class") or "")
    assert page.locator("#lib-fault-tell").is_visible()
    # Not a first visit's shelves, which is what a 500 with a JSON body used to draw.
    assert page.locator("#shelves").is_hidden()
    assert page.locator("#lib-waiting").is_hidden()
    if phone:
        box = again.bounding_box()
        assert box and box["height"] >= 44
        assert page.evaluate("document.scrollingElement.scrollWidth <= innerWidth")
    assert not thrown
    context.close()


def test_no_answer_is_said_as_unreachable(browser, page_html) -> None:
    context, page, thrown, _, url = library(browser, page_html, {"/readers": "abort"})
    page.goto(url)
    page.locator("#lib-fault").wait_for(state="visible")
    assert page.locator("#lib-fault-lede").inner_text() == "We can't reach targum."
    assert page.locator("#lib-fault-again").is_visible()
    assert not thrown
    context.close()


def test_offline_says_offline_and_leaves_the_press_to_the_banner(browser, page_html) -> None:
    context, page, thrown, _, url = library(browser, page_html, {"/readers": "abort"}, offline=True)
    page.goto(url)
    page.locator("#lib-fault").wait_for(state="visible")
    assert page.locator("#lib-fault-lede").inner_text() == "You're offline."
    assert "back online" in page.locator("#lib-fault-says").inner_text()
    assert page.locator("#lib-fault-again").is_hidden()
    assert not thrown
    context.close()


def test_the_shelf_file_failing_is_a_failure_not_an_empty_language(browser, page_html) -> None:
    context, page, thrown, _, url = library(
        browser, page_html, {"/readers": {"readers": [], "shared": []}}, lose_shelf=True
    )
    page.goto(url)
    page.locator("#lib-fault").wait_for(state="visible")
    assert page.locator("#lib-fault-lede").inner_text() == "We couldn't open the Library."
    assert "No Hebrew texts" not in page.locator("main").inner_text()
    assert page.locator("#lib-doors").is_hidden()
    assert not thrown
    context.close()


def test_an_empty_band_is_said_as_a_band_with_a_way_to_every_text(browser, page_html) -> None:
    # Every built text known at a half: nothing is Read it now.
    answers = {"/readers": {"readers": [], "shared": built(0.5), "signedIn": True}}
    context, page, thrown, _, url = library(browser, page_html, answers, hash="#see/now")
    page.goto(url)
    empty = page.locator("#picked-empty")
    empty.wait_for(state="visible")
    said = empty.inner_text()
    assert said.startswith("Nothing you can read now yet.")
    assert "Try another search" not in said
    page.locator("#picked-empty .lib-empty-go").click()
    page.locator("#catalogue > li").first.wait_for()
    assert page.locator("#picked-empty").is_hidden()
    assert not thrown
    context.close()


def test_no_nought_is_a_share_before_any_word_is_marked(browser, page_html) -> None:
    answers = {"/readers": {"readers": [], "shared": built(0.0), "signedIn": True}}
    context, page, thrown, _, url = library(browser, page_html, answers)
    page.goto(url)
    page.locator("#shelves .band-known").first.wait_for()
    shares = page.locator("#shelves .band-known").all_inner_texts()
    assert shares and not [one for one in shares if one.startswith("0%")]
    page.goto(f"{SITE}/library#see")
    page.locator("#catalogue .see-known").first.wait_for()
    rows = page.locator("#catalogue .see-known").all_inner_texts()
    assert not [one for one in rows if one.startswith("0%")]
    assert not thrown
    context.close()


def test_a_hebrew_byline_carries_its_language_and_direction(browser, page_html) -> None:
    answers = {"/readers": {"readers": [], "shared": [], "signedIn": True}}
    context, page, thrown, _, url = library(browser, page_html, answers, hash="#see/kind/books")
    page.goto(url)
    page.locator("#catalogue .row-by").first.wait_for()
    wrong = page.evaluate(
        """() => [...document.querySelectorAll('#catalogue .row-by, #catalogue .row-blurb')]
          .filter((e) => /^[^A-Za-z\\u0590-\\u05ff]*[\\u0590-\\u05ff]/.test(e.textContent))
          .filter((e) => e.getAttribute('lang') !== 'he' || e.getAttribute('dir') !== 'auto')
          .map((e) => e.textContent)"""
    )
    assert not wrong, wrong[:5]
    assert not thrown
    context.close()


def test_tab_passes_the_search_box_to_the_shelves(browser, page_html) -> None:
    """The box opened the search on focus, and the search kept the keyboard inside it, so
    the doors and the shelves under it could not be reached by Tab at all."""
    answers = {"/readers": {"readers": [], "shared": built(0.5), "signedIn": True}}
    context, page, thrown, _, url = library(browser, page_html, answers)
    page.goto(url)
    page.locator("#shelves .band-card").first.wait_for()
    page.focus("#find")
    page.keyboard.press("Tab")
    assert page.locator("#palette").is_hidden()
    assert page.evaluate("document.activeElement.className") == "lib-door"
    # A letter typed still opens the one search.
    page.focus("#find")
    page.keyboard.type("t")
    page.locator("#palette").wait_for(state="visible")
    assert not thrown
    context.close()


def test_see_all_presses_reach_44px_under_a_thumb(browser, page_html) -> None:
    answers = {"/readers": {"readers": [], "shared": built(0.8), "signedIn": True}}
    context, page, thrown, _, url = library(browser, page_html, answers, phone=True)
    page.goto(url)
    page.locator("#shelves .band-all").first.wait_for()
    short = page.evaluate(
        """() => [...document.querySelectorAll('#shelves .band-all, .lib-door')]
          .map((e) => e.getBoundingClientRect()).filter((r) => r.height < 44).length"""
    )
    assert short == 0
    page.goto(f"{SITE}/library#see/stretch")
    page.locator("#catalogue > li").first.wait_for()
    heights = page.evaluate(
        """() => [...document.querySelectorAll('#see-back-link, #rows-head button')]
          .filter((e) => e.offsetParent).map((e) => e.getBoundingClientRect().height)"""
    )
    assert heights and min(heights) >= 44, heights
    assert page.evaluate("document.scrollingElement.scrollWidth <= innerWidth")
    assert not thrown
    context.close()


def test_a_refused_press_on_a_shelf_card_is_read_whole_on_a_phone(browser, page_html) -> None:
    """A card that is not built asks first; when it is refused, the sentence was cut to
    one line on a phone ("We can't open this one ri…")."""
    refused = "We can't open this one right now. Try another text."
    answers = {
        "/readers": {"readers": [], "shared": [], "signedIn": True},
        "/prepare": {"error": refused},
    }
    context, page, thrown, _, url = library(browser, page_html, answers, phone=True)
    page.goto(url)
    card = page.locator("#shelves button.band-card").first
    card.click()
    state = card.locator(".row-state")
    page.wait_for_function(
        "(said) => [...document.querySelectorAll('#shelves .row-state')]"
        ".some((e) => e.textContent === said)",
        arg=refused,
    )
    assert state.inner_text() == refused
    assert state.evaluate("(e) => e.scrollWidth <= e.clientWidth + 1")
    # And a redraw of the shelves keeps it: it vanished a second after it was said, when
    # the account's sync landed and the shelves were drawn again.
    page.evaluate("() => { location.hash = '#see'; }")
    page.locator("#catalogue > li").first.wait_for()
    page.evaluate("() => { history.back(); }")
    page.locator("#shelves .band-card").first.wait_for()
    page.wait_for_function(
        "(said) => [...document.querySelectorAll('#shelves .row-state')]"
        ".some((e) => e.textContent === said)",
        arg=refused,
    )
    assert not thrown
    context.close()


def test_words_in_one_language_do_not_measure_another_shelf(browser, page_html) -> None:
    """A reader with Hebrew words who opened another language's shelf met every text in
    it on A stretch, "You know 75–90% of their words", each one "Not measured yet"."""
    assert [e for e in everything() if e.language == "arc"], "the fixture has Aramaic texts"
    mine = {
        "name": "mine-arc",
        "document": "f" * 64,
        "title": "טקסט",
        "language": "arc",
        "entry": "",
        "known": 0,
        "words": 10,
        "sections": 1,
        "chapters": [],
    }
    answers = {"/readers": {"readers": [mine], "shared": built(0.95), "signedIn": True}}
    context, page, thrown, _, url = library(browser, page_html, answers, language="arc")
    page.goto(url)
    page.locator("#shelves .band-card").first.wait_for()
    shelves = page.locator("#shelves").inner_text()
    assert "Until you mark words you know" in shelves
    assert "You know 75" not in shelves
    assert not thrown
    context.close()
    # And the Hebrew shelf is still measured by the Hebrew words.
    context, page, thrown, _, url = library(browser, page_html, answers, language="he")
    page.goto(url)
    page.locator("#shelves .band-card").first.wait_for()
    assert "Until you mark words you know" not in page.locator("#shelves").inner_text()
    assert not thrown
    context.close()


def test_a_language_with_no_shelf_is_one_card_with_upload(browser, page_html) -> None:
    """targum-internal#476, B3: the Yiddish shelf drew a search over nothing, an empty card
    in three bands and "Not here? Upload your own", which answers a search nobody made. A
    language with no shelf is one card: there is none yet, Upload, and what works."""
    assert not [e for e in everything() if e.language == "yi"], "the fixture has no Yiddish"
    answers = {"/readers": {"readers": [], "shared": built(0.5, 20), "signedIn": True}}
    context, page, thrown, _, url = library(browser, page_html, answers, language="yi")
    page.goto(url)
    page.locator("#no-shelf").wait_for()
    got = page.evaluate(
        """() => ({
          said: document.getElementById('no-shelf-said').textContent,
          go: document.querySelector('#no-shelf .no-shelf-go').getAttribute('href'),
          find: document.getElementById('lib-find').hidden,
          list: document.getElementById('picked').hidden,
          elsewhere: document.getElementById('elsewhere').hidden,
        })"""
    )
    assert got == {
        "said": "There's no Yiddish shelf yet.",
        "go": "/add",
        "find": True,
        "list": True,
        "elsewhere": True,
    }
    assert not thrown
    context.close()
    # The Hebrew shelf keeps its search and has no such card.
    context, page, thrown, _, url = library(browser, page_html, answers, language="he")
    page.goto(url)
    page.locator("#shelves .band-card").first.wait_for()
    assert page.locator("#no-shelf").is_hidden() and page.locator("#lib-find").is_visible()
    assert not thrown
    context.close()


@pytest.fixture(scope="module")
def two_shelves_html() -> str:
    """The fixture shelf with one Russian row added, so there are two languages' files."""
    from targum import catalogue as catalogue_module

    real = catalogue_module.everything
    hebrew = [entry for entry in real() if entry.language == "he"][0]
    russian = dataclasses.replace(hebrew, id="ru-one", title="Один рассказ", language="ru")
    rows = [*real(), russian]
    catalogue_module.everything = lambda: rows  # type: ignore[assignment]
    try:
        return library_page("")
    finally:
        catalogue_module.everything = real  # type: ignore[assignment]


def shelf_asked(page: Any) -> list[str]:
    return [
        re.sub(r"\.[0-9a-f]{16}\.json$", "", url.split("/assets/")[1])
        for url in page.evaluate("performance.getEntriesByType('resource').map(e => e.name)")
        if "/assets/catalogue" in url
    ]


@pytest.mark.parametrize("language", ["he", "ru"])
def test_the_library_asks_for_its_own_languages_shelf_only(
    browser, two_shelves_html, language
) -> None:
    """targum-internal#484: the whole shelf was 270 kB gzipped and Hebrew's half of it.
    The page asks for what every shelf needs and the language it opens on, never the
    others, and draws that language's rows from them."""
    reader = {
        "name": "mine-ru",
        "document": "1" * 64,
        "title": "Мой текст",
        "language": "ru",
        "sections": 1,
        "chapters": [],
    }
    answers = {"/readers": {"readers": [reader], "shared": [], "signedIn": True}}
    context, page, thrown, _, url = library(
        browser, two_shelves_html, answers, hash="#see", language=language
    )
    page.goto(url)
    page.locator("#catalogue > li").first.wait_for()
    asked = shelf_asked(page)
    assert sorted(asked) == sorted(["catalogue", f"catalogue-{language}"]), asked
    drawn = page.locator("#catalogue").inner_text()
    assert ("Один рассказ" in drawn) == (language == "ru")
    assert not thrown
    context.close()


RUSSIAN_READER = {
    "name": "mine-ru",
    "document": "1" * 64,
    "title": "Мой текст",
    "language": "ru",
    "sections": 1,
    "chapters": [],
}


def test_a_fresh_browser_asks_for_the_account_s_language_first(browser, two_shelves_html) -> None:
    """qa-claude on #891: a cold browser guessed Hebrew whatever the account said, so a
    Russian or Italian reader paid for Hebrew's 126 kB, never shown, before their own.
    The server names the account's language in the page; nothing else is asked for."""
    from targum.serve import ACCOUNT_SLOT, with_account

    assert ACCOUNT_SLOT in two_shelves_html
    html = with_account(two_shelves_html, "ru", {"he", "ru"})
    answers = {"/readers": {"readers": [RUSSIAN_READER], "shared": [], "signedIn": True}}
    context, page, thrown, _, url = library(browser, html, answers, hash="#see", stored=False)
    page.goto(url)
    page.locator("#catalogue > li").first.wait_for()
    assert sorted(shelf_asked(page)) == ["catalogue", "catalogue-ru"]
    assert "Один рассказ" in page.locator("#catalogue").inner_text()
    assert page.evaluate("localStorage.getItem('targum:language')") == "ru"
    assert page.evaluate("localStorage.getItem('targum:learning')") == '["he","ru"]'
    assert not thrown
    context.close()


def test_moving_offline_to_a_language_not_fetched_keeps_the_shelf_and_the_language(
    browser, two_shelves_html
) -> None:
    """qa-claude on #891: offline, a move to a language whose shelf had not been fetched
    put the could-not-open card over the last language's cards, and the saved language
    had already moved. Now the shelf on the page stays, the language stays, and one quiet
    line says the other opens when the connection is back, which it then does."""
    from targum.render.builder import asset_files

    # Russian's file at an address of the test's own, so it can be lost and then found:
    # a routed answer arrives whatever the browser's connection says.
    real = re.search(r"/assets/catalogue-ru\.[0-9a-f]{16}\.json", two_shelves_html)
    assert real
    elsewhere = "/assets/catalogue-ru.0000000000000000.json"
    html = two_shelves_html.replace(real.group(0), elsewhere)
    answers: dict[str, Any] = {
        "/readers": {"readers": [RUSSIAN_READER], "shared": [], "signedIn": True},
        elsewhere: "abort",
    }
    context, page, thrown, _, url = library(browser, html, answers, hash="#see", learns=("ru",))
    page.goto(url)
    page.locator("#catalogue > li").first.wait_for()
    before = page.locator("#catalogue").inner_text()
    assert sorted(shelf_asked(page)) == ["catalogue", "catalogue-he"]

    context.set_offline(True)
    page.locator("#langs .lang-open").click()
    page.locator('#langs [role="menuitemradio"][data-code="ru"]').click()
    held = page.locator("#lib-held")
    held.wait_for(state="visible")
    named = page.evaluate("window.TARGUM_LANGUAGES.ru")
    assert held.inner_text() == f"{named} opens when you're back online."
    assert page.locator("#lib-fault").is_hidden(), "not the could-not-open card"
    assert page.locator("#catalogue").inner_text() == before, "what was drawn stays"
    assert page.evaluate("localStorage.getItem('targum:language')") == "he"

    answers[elsewhere] = json.loads(asset_files()[real.group(0)][0])
    context.set_offline(False)
    page.wait_for_function("localStorage.getItem('targum:language') === 'ru'")
    page.wait_for_function(
        "document.getElementById('catalogue').innerText.indexOf('Один рассказ') >= 0"
    )
    assert held.is_hidden()
    assert not thrown
    context.close()
