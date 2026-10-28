"""The playlists page and its two doors, in a real browser (targum-internal#364).

The sheet a shelf row and a reader's ⋯ menu both open — `/playlists?add=` — and the
playlists under it. The server is answered for by a stand-in `fetch`, the way
`test_pages_browser.py` answers for the shelf, and what the page posts is kept.

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum.render.builder import carried, list_page, playlists_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

TOKEN = "test-key"

KITCHEN = {
    "id": 1,
    "name": "Kitchen",
    "made_by": "reader",
    "made": 1,
    "at": None,
    "covers": [
        {"name": "cheese", "title": "Cheese swirls", "language": "en"},
        {"name": "", "title": "Raiba", "language": ""},
    ],
    "seconds": 600,
    "known": 0.88,
    "ready": 1,
    "waiting": 0,
    "failed": 1,
    "unconfirmed": 0,
    "credits": 0,
    "items": [
        {
            "position": 0,
            "reader": "cheese",
            "job": None,
            "title": "Cheese swirls",
            "failed": False,
            "open": "/reader/cheese/reader/index.html",
            "facts": {
                "name": "cheese",
                "entry": "",
                "language": "en",
                "kind": "story",
                "video": False,
                "seconds": 0,
                "minutes": 10,
                "known": 0.88,
                "words": 900,
            },
        },
        {
            "position": 1,
            "reader": None,
            "job": "j2",
            "title": "Raiba",
            "failed": True,
            "open": None,
            "facts": None,
        },
    ],
}

#: What `/playlists.json` says of KITCHEN: the playlist added up, without its texts.
CARD = {key: value for key, value in KITCHEN.items() if key != "items"} | {"count": 2}

FAKE = """
const said = (x) => Promise.resolve(new Response(JSON.stringify(x)));
window.fetch = (url, opts) => {
  const path = String(url).split('?')[0].replace(/^.*?(\\/playlists)/, '$1');
  // Home's own read, a POST since its body carries what is finished (targum#959): not a
  // playlist press, so it is answered as the reads below are and never recorded.
  if (path.endsWith('/suggest')) return said({});
  if (opts && opts.method === 'POST') {
    const posted = JSON.parse(sessionStorage.getItem('posted') || '[]');
    posted.push([path, JSON.parse(opts.body)]);
    sessionStorage.setItem('posted', JSON.stringify(posted));
    if (path === '/playlists') return said({...KITCHEN, id: 2, name: JSON.parse(opts.body).name});
    return said(KITCHEN);
  }
  const current = window.CURRENT || null;
  if (path === '/playlists.json') return said({ playlists: [CARD], current });
  if (path === '/playlists/1.json') return said(KITCHEN);
  return said({});
};
"""


def fake(kitchen: dict = KITCHEN, card: dict = CARD) -> str:
    return f"const KITCHEN = {json.dumps(kitchen)}; const CARD = {json.dumps(card)};" + FAKE


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


def opened(browser, tmp_path: Path, query: str = "", width: int = 390):
    """The page over FAKE: the tab, or with `?playlist=1` the one playlist."""
    page_file = tmp_path / "playlists.html"
    page_file.write_text(carried(playlists_page(TOKEN)), encoding="utf-8")
    context = browser.new_context(viewport={"width": width, "height": 844})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.add_init_script(fake())
    page.goto(page_file.as_uri() + query)
    page.wait_for_selector("#one .item" if "playlist=" in query else "#playlists .pl-card")
    return context, page, thrown


def posted(page) -> list:
    return page.evaluate("() => JSON.parse(sessionStorage.getItem('posted') || '[]')")


def test_the_sheet_adds_a_text_to_a_playlist_with_one_press(browser, tmp_path: Path) -> None:
    context, page, thrown = opened(browser, tmp_path, "?add=jonah&title=%D7%99%D7%95%D7%A0%D7%94")
    assert page.locator("#adding-head").text_content() == "Add יונה to a playlist"
    focused = page.evaluate("() => document.activeElement.textContent")
    assert focused.startswith("Kitchen"), "the first choice is under the finger"
    page.locator("#choose button").first.click()
    page.wait_for_selector("#adding-said:not([hidden])")
    said = page.locator("#adding-said").text_content()
    sent = posted(page)
    context.close()
    assert not thrown, thrown
    assert said == "Added to Kitchen."
    assert sent == [["/playlists/1", {"do": "add", "reader": "jonah", "title": "יונה"}]]


def test_a_new_playlist_takes_the_text_with_it(browser, tmp_path: Path) -> None:
    context, page, thrown = opened(browser, tmp_path, "?add=jonah&title=Jonah")
    page.fill("#new-name", "Prophets")
    page.press("#new-name", "Enter")
    page.wait_for_selector("#adding-said:not([hidden])")
    sent = posted(page)
    context.close()
    assert not thrown, thrown
    assert sent == [["/playlists", {"name": "Prophets", "reader": "jonah", "title": "Jonah"}]]


def test_a_playlist_lists_its_texts_in_order_with_its_keys(browser, tmp_path: Path) -> None:
    context, page, thrown = opened(browser, tmp_path, "?playlist=1", width=1280)
    got = page.evaluate(
        """() => ({
          tab: document.getElementById('lists').hidden,
          start: document.querySelector('.pl-head .start').getAttribute('href'),
          titles: [...document.querySelectorAll('.item-title')].map(n => n.textContent),
          upFirst: document.querySelector('.item .item-keys .up').disabled,
          downLast: [...document.querySelectorAll('.item')].pop()
            .querySelector('.item-keys .down').disabled,
          failed: document.querySelector('.item.failed .item-state').textContent,
          byline: document.querySelector('.pl-byline').textContent,
        })"""
    )
    page.locator(".item").first.locator(".item-keys .down").click()
    page.wait_for_timeout(100)
    sent = posted(page)
    context.close()
    assert not thrown, thrown
    assert got == {
        "tab": True,
        "start": "/reader/cheese/reader/index.html?list=1&at=0&k=test-key",
        "titles": ["Cheese swirls", "Raiba"],
        "upFirst": True,
        "downLast": True,
        "failed": "We couldn't get this text ready. Remove it, then add it again.",
        "byline": "By you",
    }
    assert sent == [["/playlists/1", {"do": "move", "position": 0, "to": 1}]]


def test_alt_and_an_arrow_move_the_row_with_the_focus(browser, tmp_path: Path) -> None:
    context, page, thrown = opened(browser, tmp_path, "?playlist=1", width=1280)
    page.locator(".item").first.locator(".grip").focus()
    page.keyboard.press("Alt+ArrowDown")
    page.wait_for_timeout(100)
    page.keyboard.press("Alt+ArrowUp")
    page.wait_for_timeout(100)
    sent = posted(page)
    focused = page.evaluate("() => document.activeElement.className")
    context.close()
    assert not thrown, thrown
    assert sent[0] == ["/playlists/1", {"do": "move", "position": 0, "to": 1}]
    assert "grip" in focused, "the focus stays on the text it moved"


def test_a_row_is_dragged_to_its_new_place(browser, tmp_path: Path) -> None:
    context, page, thrown = opened(browser, tmp_path, "?playlist=1", width=1280)
    grip = page.locator(".item").first.locator(".grip").bounding_box()
    last = page.locator(".item").last.bounding_box()
    assert grip and last
    page.mouse.move(grip["x"] + grip["width"] / 2, grip["y"] + grip["height"] / 2)
    page.mouse.down()
    page.mouse.move(grip["x"] + 10, last["y"] + last["height"] - 4, steps=8)
    page.mouse.up()
    page.wait_for_timeout(100)
    sent = posted(page)
    context.close()
    assert not thrown, thrown
    assert sent == [["/playlists/1", {"do": "move", "position": 0, "to": 1}]]


def test_the_tab_draws_a_card_a_playlist(browser, tmp_path: Path) -> None:
    """Board PlaylistsTab: the first four for its cover, whose hand made it, how long,
    how much is known, and the one the reader is in marked."""
    page_file = tmp_path / "playlists.html"
    page_file.write_text(carried(playlists_page(TOKEN)), encoding="utf-8")
    context = browser.new_context(viewport={"width": 1280, "height": 844})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    connector = {
        **CARD,
        "id": 3,
        "name": "News",
        "made_by": "connector",
        "waiting": 2,
        "ready": 1,
        "count": 3,
        "unconfirmed": 2,
        "credits": 12,
    }
    page.add_init_script(
        fake()
        + "window.CURRENT = {id: 1, name: 'Kitchen', at: 1};"
        + f"const OTHER = {json.dumps(connector)};"
        + "const plain = window.fetch; window.fetch = (url, opts) =>"
        " String(url).indexOf('/playlists.json') >= 0"
        " ? Promise.resolve(new Response(JSON.stringify({playlists: [CARD, OTHER],"
        " current: window.CURRENT}))) : plain(url, opts);"
    )
    page.goto(page_file.as_uri())
    page.wait_for_selector("#playlists .pl-card")
    got = page.evaluate(
        """() => [...document.querySelectorAll('.pl-card:not(.pl-new-card)')].map(card => ({
          cells: card.querySelectorAll('.pl-mosaic > *').length,
          here: card.querySelector('.pl-here') && card.querySelector('.pl-here').textContent,
          facts: card.querySelector('.pl-facts').textContent,
          known: card.querySelector('.pl-share') && card.querySelector('.pl-share').textContent,
          foot: card.querySelector('.pl-foot') && card.querySelector('.pl-foot').textContent,
          open: card.querySelector('.pl-card-open').getAttribute('href'),
        }))"""
    )
    new_card = page.locator(".pl-new-card").count()
    context.close()
    assert not thrown, thrown
    assert got == [
        {
            # As many cells as texts, filling the square (P2): no empty quarter.
            "cells": 2,
            "here": "You're in it · 2 of 2",
            "facts": "By you · 2 texts · 10\u00a0min",
            "known": "88% known",
            "foot": None,
            "open": "/playlists/1?k=test-key",
        },
        {
            "cells": 2,
            "here": None,
            "facts": "From your AI · 3 texts · 10\u00a0min",
            "known": "88% known",
            "foot": "Not confirmed yetUses 12 credits · Confirm",
            "open": "/playlists/3?k=test-key",
        },
    ]
    assert new_card == 1


def test_a_shelf_row_opens_the_sheet_for_its_text(browser, tmp_path: Path) -> None:
    page_file = tmp_path / "texts.html"
    page_file.write_text(carried(list_page(TOKEN, "texts")), encoding="utf-8")
    readers = [{"name": "jonah", "document": "jonah", "title": "יונה", "language": "he"}]
    # At a desk, where the row draws its + (a phone keeps it in ⋯, audit Q7).
    context = browser.new_context(viewport={"width": 1280, "height": 844})
    page = context.new_page()
    page.add_init_script(
        f"const readers = {json.dumps(readers)};"
        "window.fetch = (url) => Promise.resolve(new Response(JSON.stringify("
        "String(url).split('?')[0].endsWith('/readers') ? {readers, trash: []} : {})));"
    )
    page.goto(page_file.as_uri())
    page.wait_for_selector(".add-to-list")
    href = page.locator(".add-to-list").first.get_attribute("href")
    context.close()
    assert href == "/playlists?add=jonah&title=%D7%99%D7%95%D7%A0%D7%94&k=test-key"


def shelf_with_fake(browser, tmp_path: Path, extra: str = "", width: int = 1280):
    page_file = tmp_path / "texts.html"
    page_file.write_text(carried(list_page(TOKEN, "texts")), encoding="utf-8")
    readers = [{"name": "jonah", "document": "jonah", "title": "יונה", "language": "he"}]
    context = browser.new_context(viewport={"width": width, "height": 844})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.add_init_script(
        f"const readers = {json.dumps(readers)};" + fake() + "const playlistsFetch = window.fetch;"
        "window.fetch = (url, opts) => String(url).split('?')[0].endsWith('/readers')"
        " ? Promise.resolve(new Response(JSON.stringify({readers, trash: []})))"
        " : playlistsFetch(url, opts);" + extra
    )
    page.goto(page_file.as_uri())
    page.wait_for_selector(".add-to-list", state="attached")
    return context, page, thrown


def test_add_to_playlist_is_a_menu_in_place(browser, tmp_path: Path) -> None:
    """2026-09-24: "why do I need to go to an entire new page to add a targum to a
    playlist, it should be doable in a single dropdown." One press opens the reader's
    playlists under the row, a second adds the text, and the page never changes."""
    context, page, thrown = shelf_with_fake(browser, tmp_path)
    before = page.url
    page.locator(".add-to-list").first.click()
    page.wait_for_selector(".playlist-menu .pm-choice")
    assert page.locator(".add-to-list").first.get_attribute("aria-expanded") == "true"
    page.locator(".playlist-menu .pm-choice").first.click()
    page.wait_for_selector(".playlist-menu .pm-status:not([hidden])")
    said = page.locator(".playlist-menu .pm-status").inner_text()
    sent = posted(page)
    after = page.url
    context.close()
    assert after == before, "it stayed on the shelf"
    assert sent == [["/playlists/1", {"do": "add", "reader": "jonah", "title": "יונה"}]]
    assert said == "Added to Kitchen."
    assert not thrown


def test_on_a_phone_add_to_playlist_is_in_the_rows_menu(browser, tmp_path: Path) -> None:
    """Audit Q7 (2026-10-09): a phone's row keeps ⋯ alone, and Add to playlist inside
    it opens the same sheet the + does, on the shelf."""
    context, page, thrown = shelf_with_fake(browser, tmp_path, width=390)
    before = page.url
    page.locator(".row-more").first.click()
    page.locator(".row-menu a", has_text="Add to playlist").click()
    page.wait_for_selector(".playlist-menu .pm-choice")
    row_menu = page.locator(".row-menu").count()
    after = page.url
    context.close()
    assert after == before
    assert row_menu == 0, "the row's menu gave way to the sheet"
    assert not thrown


def test_the_menu_makes_a_new_playlist_with_the_text_in_it(browser, tmp_path: Path) -> None:
    # The phone's sheet, where the name is a field from the start; reached through ⋯.
    context, page, thrown = shelf_with_fake(browser, tmp_path, width=390)
    page.locator(".row-more").first.click()
    page.locator(".row-menu a", has_text="Add to playlist").click()
    page.wait_for_selector(".playlist-menu .pm-choice")
    page.fill(".playlist-menu .pm-name", "Morning")
    confirm = page.locator(".playlist-menu .pm-confirm").inner_text()
    page.locator(".playlist-menu .pm-confirm").click()
    page.wait_for_selector(".playlist-menu .pm-status:not([hidden])")
    sent = posted(page)
    context.close()
    assert confirm == "Create", "the press makes a playlist, so it says so (David, 2026-10-21)"
    assert sent == [["/playlists", {"name": "Morning", "reader": "jonah", "title": "יונה"}]]
    assert not thrown


def test_escape_closes_the_menu_and_gives_focus_back(browser, tmp_path: Path) -> None:
    context, page, thrown = shelf_with_fake(browser, tmp_path)
    page.locator(".add-to-list").first.click()
    page.wait_for_selector(".playlist-menu .pm-choice")
    page.keyboard.press("Escape")
    gone = page.locator(".playlist-menu").count()
    focused = page.evaluate("() => document.activeElement.className")
    context.close()
    assert gone == 0
    assert "add-to-list" in focused
    assert not thrown


def playing_in(languages: dict) -> str:
    """The shelf's fetch, with `/playlists/current.json` answering `languages`."""
    answer = json.dumps({"current": {"id": 1, "name": "Kitchen", "at": 0}, "languages": languages})
    return (
        "const viaShelf = window.fetch; window.fetch = (url, opts) =>"
        " String(url).indexOf('/playlists/current.json') >= 0"
        f" ? Promise.resolve(new Response(JSON.stringify({answer})))"
        " : viaShelf(url, opts);"
    )


def test_play_next_is_in_a_rows_menu_while_you_are_in_a_playlist(browser, tmp_path: Path) -> None:
    """targum-internal#434: "Play next" in a text's ⋯ puts it straight after the one the
    reader is on, in the playlist they are in."""
    context, page, thrown = shelf_with_fake(
        browser, tmp_path, playing_in({"he": {"id": 1, "name": "Kitchen", "at": 0}})
    )
    page.wait_for_timeout(100)
    page.locator(".row-more").first.click()
    press = page.locator(".row-menu .play-next")
    label = press.text_content()
    press.click()
    page.wait_for_function("() => (sessionStorage.getItem('posted') || '').includes('next')")
    sent = posted(page)
    context.close()
    assert not thrown, thrown
    assert label == "Play next in Kitchen"
    assert sent == [["/playlists/1", {"do": "next", "reader": "jonah", "title": "יונה"}]]


def test_play_next_is_only_offered_in_the_texts_own_language(browser, tmp_path: Path) -> None:
    """A French video was offered "Play next in" a Hebrew playlist (2026-10-12). A Hebrew
    row in a reader who is in a French playlist, and in no Hebrew one, is offered none,
    and its Add to playlist asks only for the playlists it may go into."""
    context, page, thrown = shelf_with_fake(
        browser,
        tmp_path,
        playing_in({"fr": {"id": 1, "name": "Romans", "at": 0}})
        + "const viaMenu = window.fetch; window.asked = [];"
        " window.fetch = (url, opts) => { window.asked.push(String(url));"
        " return viaMenu(url, opts); };",
    )
    page.wait_for_timeout(100)
    page.locator(".row-more").first.click()
    offered = page.locator(".row-menu .play-next").count()
    page.keyboard.press("Escape")
    page.locator(".add-to-list").first.click()
    page.wait_for_selector(".playlist-menu .pm-choice")
    asked = page.evaluate("() => window.asked")
    context.close()
    assert not thrown, thrown
    assert offered == 0
    assert any(url.split("/")[-1].startswith("playlists.json?reader=jonah") for url in asked), asked


# --- review fixes, 2026-09-24 -------------------------------------------------------


def opened_with(browser, tmp_path: Path, extra: str, wait: str = "#playlists .pl-card", query=""):
    """The page over FAKE, with `extra` run after it to change what the server says."""
    page_file = tmp_path / "playlists.html"
    page_file.write_text(carried(playlists_page(TOKEN)), encoding="utf-8")
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.add_init_script(fake() + extra)
    page.goto(page_file.as_uri() + query)
    page.wait_for_selector(wait)
    return context, page, thrown


def test_delete_asks_before_it_takes_a_whole_playlist(browser, tmp_path: Path) -> None:
    # The second press goes back to the tab once the server has said so: held here, so
    # the page stays to be read.
    context, page, thrown = opened_with(
        browser,
        tmp_path,
        """
        const before = window.fetch;
        window.fetch = (url, opts) => {
          const out = before(url, opts);
          return opts && opts.body && opts.body.indexOf('gone') >= 0 ? new Promise(() => {}) : out;
        };
        """,
        wait="#one .item",
        query="?playlist=1",
    )
    page.locator(".pl-more").click()
    away = page.locator(".pl-menu .danger")
    away.click()
    first = posted(page)
    label = away.text_content()
    away.click()
    page.wait_for_function("() => (sessionStorage.getItem('posted') || '').includes('gone')")
    second = posted(page)
    context.close()
    assert not thrown, thrown
    assert first == [], "one press takes nothing away"
    assert label == "Yes, delete"
    assert second == [["/playlists/1", {"do": "gone"}]]


def test_the_account_button_is_told_who_is_here(browser, tmp_path: Path) -> None:
    """Every desk page starts sync, which is what the header's account button asks; this
    one did not, and said Sign in to a reader who was signed in."""
    context, page, thrown = opened_with(
        browser,
        tmp_path,
        """
        const before = window.fetch;
        window.fetch = (url, opts) => {
          if (String(url).indexOf('/account/me') >= 0) sessionStorage.setItem('me', '1');
          return before(url, opts);
        };
        """,
    )
    page.wait_for_function("() => sessionStorage.getItem('me') === '1'")
    context.close()
    assert not thrown, thrown


def test_no_connection_is_not_a_sign_in(browser, tmp_path: Path) -> None:
    context, page, thrown = opened_with(
        browser,
        tmp_path,
        "window.fetch = () => Promise.reject(new TypeError('offline'));",
        wait="#fault:not([hidden])",
    )
    said = page.locator("#fault .fault-panel-said").text_content()
    again = page.locator("#fault .fault-go").text_content()
    stranger = page.locator("#stranger").is_hidden()
    context.close()
    assert not thrown, thrown
    # The press says Try again, so the sentence does not (ling-en's rule).
    assert said == "We can't reach targum."
    assert again == "Try again", "a fault offers something to press (targum-internal#474, B2)"
    assert stranger, "a network that failed is not a reader who is signed out"


def test_a_server_that_fails_is_not_one_that_cannot_be_reached(browser, tmp_path: Path) -> None:
    """targum-internal#474, B2: a 502 with no JSON said "We can't reach targum", which is
    another fault, and offered nothing to press. It says the playlists did not load, and
    Try again asks again."""
    context, page, thrown = opened_with(
        browser,
        tmp_path,
        """
        const before = window.fetch;
        window.fetch = (url, opts) => {
          if (String(url).includes('/playlists.json') && !sessionStorage.getItem('failed')) {
            sessionStorage.setItem('failed', '1');
            return Promise.resolve(new Response('<html>Bad gateway</html>', {status: 502}));
          }
          return before(url, opts);
        };
        """,
        wait="#fault:not([hidden])",
    )
    said = page.locator("#fault .fault-panel-said").text_content()
    page.locator("#fault .fault-go").click()
    page.wait_for_selector("#playlists .pl-card")
    gone = page.locator("#fault").is_hidden()
    context.close()
    assert not thrown, thrown
    assert said == "We couldn't load your playlists."
    assert gone


def test_a_slow_answer_says_so_and_offers_try_again(browser, tmp_path: Path) -> None:
    """targum-internal#474, B1: until the server answered, the page was the tabs and
    nothing else. It says it is getting them at once, and past three seconds that it is
    taking longer, with Try again."""
    context, page, thrown = opened_with(
        browser,
        tmp_path,
        """
        const before = window.fetch;
        window.fetch = (url, opts) => {
          if (String(url).includes('/playlists.json') && !sessionStorage.getItem('held')) {
            sessionStorage.setItem('held', '1');
            // Answered late, and badly, once Try again has drawn the page.
            return new Promise((done) => { window.answerLate = done; });
          }
          return before(url, opts);
        };
        """,
        wait="#wait:not([hidden])",
    )
    first = page.locator("#wait").text_content()
    early = page.locator("#slow").is_hidden()
    page.wait_for_selector("#slow:not([hidden])", timeout=5000)
    slow = page.locator("#slow span").text_content()
    page.locator("#slow-again").click()
    page.wait_for_selector("#playlists .pl-card")
    after = page.evaluate(
        "() => [document.getElementById('wait').hidden, document.getElementById('slow').hidden]"
    )
    # The first ask answering now, with a server fault, draws nothing: only the last does.
    page.evaluate("() => window.answerLate(new Response('<html>502</html>', {status: 502}))")
    page.wait_for_timeout(200)
    late = page.evaluate(
        "() => [document.getElementById('fault').hidden,"
        " document.querySelectorAll('#playlists .pl-card').length > 0]"
    )
    context.close()
    assert not thrown, thrown
    assert first == "We're getting your playlists."
    assert early, "not before three seconds"
    assert slow == "This is taking longer than usual."
    assert after == [True, True]
    assert late == [True, True], "a late first answer does not undo the drawn page"


def test_the_sheet_holds_the_focus_and_gives_it_back(browser, tmp_path: Path) -> None:
    """targum-internal#474, B6: the sheet is a modal dialog, so Tab stays in it, and
    Escape puts it away and gives the focus back to New playlist (the strip's press, at a
    desk; a phone has the last card instead)."""
    context, page, thrown = opened(browser, tmp_path, width=1280)
    page.locator("#new-press").focus()
    page.keyboard.press("Enter")
    page.wait_for_selector("#adding:not([hidden])")
    inside = []
    for _ in range(8):
        page.keyboard.press("Tab")
        inside.append(page.evaluate("() => !!document.activeElement.closest('#adding')"))
    page.keyboard.press("Shift+Tab")
    inside.append(page.evaluate("() => !!document.activeElement.closest('#adding')"))
    page.keyboard.press("Escape")
    back = page.evaluate("() => document.activeElement.id")
    context.close()
    assert not thrown, thrown
    assert all(inside), inside
    assert back == "new-press"


def test_a_title_getting_ready_says_its_language(browser, tmp_path: Path) -> None:
    """targum-internal#474, B8: a text that failed or is still getting ready has no facts,
    so its title took the page's language. The playlist keeps to one, and says which."""
    hebrew = {
        **KITCHEN,
        "language": "he",
        "items": [
            KITCHEN["items"][0],
            {**KITCHEN["items"][1], "title": "רייבה"},
        ],
    }
    context, page, thrown = opened_with(
        browser,
        tmp_path,
        f"Object.assign(KITCHEN, {json.dumps(hebrew)});",
        wait="#one .item",
        query="?playlist=1",
    )
    got = page.evaluate(
        """() => {
          const bdi = document.querySelector('.item.failed .item-title bdi');
          const letter = document.querySelector('.item.failed .pl-thumb [lang]');
          return [bdi.getAttribute('lang'), bdi.getAttribute('dir'),
                  letter && letter.getAttribute('lang')];
        }"""
    )
    note = page.locator(".pl-reorder-note").text_content()
    context.close()
    assert not thrown, thrown
    assert got == ["he", "auto", "he"], "the title and its thumbnail's letter"
    assert note == "Drag to reorder, or Alt+↑/↓.", "B5: what the grip does, on the page"


def test_the_protocols_words_never_reach_the_reader(browser, tmp_path: Path) -> None:
    context, page, thrown = opened_with(
        browser,
        tmp_path,
        """
        const before = window.fetch;
        window.fetch = (url, opts) => {
          const read = String(url).split('?')[0].endsWith('/suggest');
          if (opts && opts.method === 'POST' && !read && !sessionStorage.getItem('refused')) {
            sessionStorage.setItem('refused', '1');
            const refused = JSON.stringify({error: 'bad request'});
            return Promise.resolve(new Response(refused, {status: 400}));
          }
          return before(url, opts);
        };
        """,
        wait="#one .item",
        query="?playlist=1",
    )
    page.locator(".item-keys .out").first.click()
    page.wait_for_selector("#one-said:not([hidden])")
    refused = page.locator("#one-said").text_content()
    page.locator(".item-keys .out").first.click()
    page.wait_for_selector("#one-said", state="hidden")
    context.close()
    assert not thrown, thrown
    assert refused == "We couldn't do that. Try again."


@pytest.mark.parametrize("query", ["?add=jonah&title=Jonah", "?playlist=1"])
def test_a_long_name_wraps_inside_its_press(browser, tmp_path: Path, query: str) -> None:
    """A playlist's name runs to 80 characters; at phone width it wraps in its press and
    in its heading rather than running the page off the side (2026-09-24)."""
    long = "A playlist of kitchen conversations and market mornings, kept for Sundays"
    page_file = tmp_path / "playlists.html"
    page_file.write_text(carried(playlists_page(TOKEN)), encoding="utf-8")
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.add_init_script(fake({**KITCHEN, "name": long}, {**CARD, "name": long}))
    page.goto(page_file.as_uri() + query)
    page.wait_for_selector("#one .item" if "playlist" in query else "#playlists .pl-card")
    over = page.evaluate(
        """() => [...document.querySelectorAll('body *')]
            .filter((el) => el.getBoundingClientRect().right > window.innerWidth + 1)
            .filter((el) => !el.closest('.pl-menu[hidden], [hidden]'))
            .map((el) => el.tagName + '.' + el.className)"""
    )
    width = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
    context.close()
    assert over == [] and width <= 0, over


# --- the finish bar's polish (targum-internal#474) ----------------------------------


def test_the_russian_tabs_fit_a_phone(browser, tmp_path: Path) -> None:
    """Polish 3: at 390 in Russian the fourth tab, «Загрузки», was cut at the edge with
    no sign the row scrolls. All four fit."""
    page_file = tmp_path / "playlists.html"
    page_file.write_text(carried(playlists_page(TOKEN, "ru")), encoding="utf-8")
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.add_init_script(fake())
    page.goto(page_file.as_uri())
    page.wait_for_selector("#playlists .pl-card")
    seen = page.evaluate(
        """() => {
          const row = document.getElementById('yours-tabs');
          const last = row.querySelector('[data-tab="uploads"]').getBoundingClientRect();
          return {over: row.scrollWidth - row.clientWidth, end: last.right,
                  edge: row.getBoundingClientRect().right, said: row.innerText};
        }"""
    )
    context.close()
    assert "Загрузки" in seen["said"], seen
    assert seen["over"] <= 0 and seen["end"] <= seen["edge"] + 0.5, seen


def test_a_deleted_playlist_is_said_on_the_tab(browser, tmp_path: Path) -> None:
    """Polish 4: after the second press the page went to the tab and the playlist was just
    gone. Delete leaves a note in this tab and carries the id, and the tab says what went,
    once."""
    context, page, thrown = opened(browser, tmp_path, "?playlist=1")
    went: list[str] = []
    page.on("request", lambda request: went.append(request.url))
    page.locator(".pl-more").click()
    away = page.locator(".pl-menu .danger")
    away.click()
    away.click()
    page.wait_for_timeout(500)
    context.close()
    assert not thrown, thrown
    assert any("/playlists?deleted=1" in url for url in went), went
    assert not any("deleted=Kitchen" in url for url in went), "the name stays out of the link"

    said, role, left = deleted_tab(browser, tmp_path, {"id": "1", "name": "Kitchen"}, "1")
    assert said == "Deleted \u2068Kitchen\u2069."
    assert role == "status"
    assert "deleted" not in left, "a reload does not say it again"


def deleted_tab(browser, tmp_path: Path, note: dict | None, deleted: str) -> tuple:
    """The tab opened at `?deleted=`, with this tab's note (or none) left by a Delete."""
    context, page, thrown = opened(browser, tmp_path)
    page.evaluate(
        "(note) => note ? sessionStorage.setItem('targum.playlist-deleted', JSON.stringify(note))"
        " : sessionStorage.removeItem('targum.playlist-deleted')",
        note,
    )
    page.goto(page.url.split("?")[0] + "?deleted=" + deleted)
    page.wait_for_selector("#playlists .pl-card")
    page.wait_for_timeout(200)
    said = page.locator("#lists-said").text_content()
    role = page.locator("#lists-said").get_attribute("role")
    left = page.evaluate("() => location.search")
    kept = page.evaluate("() => sessionStorage.getItem('targum.playlist-deleted')")
    marked = page.locator("#lists-said *").count()
    context.close()
    assert not thrown, thrown
    assert kept is None, "the note is read once"
    assert marked == 0, "text only, never markup"
    return said, role, left


@pytest.mark.parametrize(
    ("note", "deleted"),
    [
        # A crafted link and no note: nothing to say.
        (None, "Your account is closed. Call us"),
        (None, "1"),
        # A note for another playlist does not lend its name to this id.
        ({"id": "2", "name": "Kitchen"}, "1"),
        # The link's text is never the line, even with a note in the tab.
        ({"id": "1", "name": "Kitchen"}, "<b>Pay here</b>"),
    ],
)
def test_a_crafted_deleted_link_says_nothing(
    browser, tmp_path: Path, note: dict | None, deleted: str
) -> None:
    """qa-claude on #872: `?deleted=` echoed any text into "Deleted {name}.", so a link
    could make the page say anything. Only this tab's own Delete is said."""
    said, _, left = deleted_tab(browser, tmp_path, note, deleted)
    assert said == ""
    assert "deleted" not in left


def test_a_length_keeps_its_number_with_its_unit(browser, tmp_path: Path) -> None:
    """qa-claude on #872: "25" and "min" broke across two lines on a card at 1440."""
    context, page, thrown = opened(browser, tmp_path, width=1440)
    facts = page.locator(".pl-facts").first.text_content()
    context.close()
    assert not thrown, thrown
    assert "10\u00a0min" in facts and "10 min" not in facts, facts


def test_the_sheet_s_choice_says_its_name_and_count_apart(browser, tmp_path: Path) -> None:
    """Polish 5: a screen reader heard "Kitchen2 texts", the name and count one run."""
    context, page, thrown = opened(browser, tmp_path, "?add=jonah&title=Jonah")
    page.wait_for_selector("#choose .named")
    heard = page.evaluate(
        "() => document.querySelector('#choose .named').textContent.replace(/\\s+/g, ' ')"
    )
    drawn = page.evaluate(
        "() => document.querySelector('#choose .named .unseen').getBoundingClientRect().width"
    )
    context.close()
    assert not thrown, thrown
    assert heard.strip() == "Kitchen · 2 texts", heard
    assert drawn <= 1, "said, not drawn"


def test_from_targum_s_share_stays_on_one_line_at_a_desk(browser, tmp_path: Path) -> None:
    """Polish 7: at 1440 the From targum card wrapped "60% known" onto two lines beside
    Open. The bar takes the column and the share keeps to one line."""
    sets = [
        {
            "id": "s1",
            "name": "מילים ראשונות",
            "nameLanguage": "he",
            "english": "First words",
            "count": 6,
            "seconds": 1500,
            "known": 0.6,
            "covers": [],
        }
    ]
    context, page, thrown = opened_with(
        browser,
        tmp_path,
        f"""
        const SETS = {json.dumps(sets)};
        const before = window.fetch;
        window.fetch = (url, opts) => {{
          const listed = String(url).split('?')[0].endsWith('/playlists.json');
          if (listed && !(opts && opts.method === 'POST')) {{
            return Promise.resolve(new Response(JSON.stringify(
              {{playlists: [CARD], current: null, targum: SETS}})));
          }}
          return before(url, opts);
        }};
        """,
    )
    page.set_viewport_size({"width": 1440, "height": 900})
    page.wait_for_selector("#from-targum:not([hidden]) .pl-share")
    lines = page.evaluate(
        """() => {
          const share = document.querySelector('.pl-targum-card .pl-share');
          const tall = parseFloat(getComputedStyle(share).lineHeight) ||
            parseFloat(getComputedStyle(share).fontSize) * 1.3;
          return share.getBoundingClientRect().height / tall;
        }"""
    )
    context.close()
    assert not thrown, thrown
    assert lines < 1.5, lines


def test_offline_the_tab_says_where_saved_playlists_are_once(browser, tmp_path: Path) -> None:
    """Polish 8: offline with the page open, the tab drew a clay fault under the band that
    already says so. It says one quiet line, with the way to Saved on this device, and
    asks again when the connection is back."""
    context, page, thrown = opened_with(
        browser,
        tmp_path,
        """
        Object.defineProperty(navigator, 'onLine', {get: () => window.ONLINE === true});
        const before = window.fetch;
        window.fetch = (url, opts) => window.ONLINE === true
          ? before(url, opts) : Promise.reject(new TypeError('offline'));
        """,
        wait="#fault:not([hidden])",
    )
    panels = page.locator("#fault .fault-panel").count()
    said = page.locator("#fault .pl-away").text_content()
    href = page.locator("#fault .pl-away a").get_attribute("href")
    # Underlined at rest like a text link, not only on hover (qa-claude on #872).
    lined = page.evaluate(
        "() => getComputedStyle(document.querySelector('#fault .pl-away a')).textDecorationLine"
    )
    page.evaluate("() => { window.ONLINE = true; window.dispatchEvent(new Event('online')); }")
    page.wait_for_selector("#playlists .pl-card")
    gone = page.locator("#fault").is_hidden()
    context.close()
    assert not thrown, thrown
    assert panels == 0, "no second fault under the band"
    assert said == "Playlists you saved for offline are under Saved on this device."
    assert href.startswith("/you/saved")
    assert lined == "underline", lined
    assert gone
