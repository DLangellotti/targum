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

from targum.render.builder import list_page, playlists_page

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
    page_file.write_text(playlists_page(TOKEN), encoding="utf-8")
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
        "failed": "We couldn't get this text ready.",
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
    page_file.write_text(playlists_page(TOKEN), encoding="utf-8")
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
            "cells": 4,
            "here": "You're in it · 2 of 2",
            "facts": "By you · 2 texts · 10 min",
            "known": "88% known",
            "foot": None,
            "open": "/playlists/1?k=test-key",
        },
        {
            "cells": 4,
            "here": None,
            "facts": "From an assistant · 3 texts · 10 min",
            "known": "88% known",
            "foot": "Not confirmed yetUses 12 credits · Confirm",
            "open": "/playlists/3?k=test-key",
        },
    ]
    assert new_card == 1


def test_a_shelf_row_opens_the_sheet_for_its_text(browser, tmp_path: Path) -> None:
    page_file = tmp_path / "texts.html"
    page_file.write_text(list_page(TOKEN, "texts"), encoding="utf-8")
    readers = [{"name": "jonah", "document": "jonah", "title": "יונה", "language": "he"}]
    context = browser.new_context(viewport={"width": 390, "height": 844})
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


def shelf_with_fake(browser, tmp_path: Path, extra: str = ""):
    page_file = tmp_path / "texts.html"
    page_file.write_text(list_page(TOKEN, "texts"), encoding="utf-8")
    readers = [{"name": "jonah", "document": "jonah", "title": "יונה", "language": "he"}]
    context = browser.new_context(viewport={"width": 390, "height": 844})
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
    page.wait_for_selector(".add-to-list")
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


def test_the_menu_makes_a_new_playlist_with_the_text_in_it(browser, tmp_path: Path) -> None:
    context, page, thrown = shelf_with_fake(browser, tmp_path)
    page.locator(".add-to-list").first.click()
    page.wait_for_selector(".playlist-menu .pm-choice")
    page.fill(".playlist-menu .pm-name", "Morning")
    confirm = page.locator(".playlist-menu .pm-confirm").inner_text()
    page.locator(".playlist-menu .pm-confirm").click()
    page.wait_for_selector(".playlist-menu .pm-status:not([hidden])")
    sent = posted(page)
    context.close()
    assert confirm == "Confirm"
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


def test_play_next_is_in_a_rows_menu_while_you_are_in_a_playlist(browser, tmp_path: Path) -> None:
    """targum-internal#434: "Play next" in a text's ⋯ puts it straight after the one the
    reader is on, in the playlist they are in."""
    context, page, thrown = shelf_with_fake(
        browser,
        tmp_path,
        "const viaShelf = window.fetch; window.fetch = (url, opts) =>"
        " String(url).indexOf('/playlists/current.json') >= 0"
        " ? Promise.resolve(new Response(JSON.stringify("
        "{current: {id: 1, name: 'Kitchen', at: 0}})))"
        " : viaShelf(url, opts);",
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


# --- review fixes, 2026-09-24 -------------------------------------------------------


def opened_with(browser, tmp_path: Path, extra: str, wait: str = "#playlists .pl-card", query=""):
    """The page over FAKE, with `extra` run after it to change what the server says."""
    page_file = tmp_path / "playlists.html"
    page_file.write_text(playlists_page(TOKEN), encoding="utf-8")
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
    assert label == "Confirm delete"
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
        wait="#lists-said:not([hidden])",
    )
    said = page.locator("#lists-said").text_content()
    stranger = page.locator("#stranger").is_hidden()
    context.close()
    assert not thrown, thrown
    assert said == "We couldn't reach targum. Try again in a moment."
    assert stranger, "a network that failed is not a reader who is signed out"


def test_the_protocols_words_never_reach_the_reader(browser, tmp_path: Path) -> None:
    context, page, thrown = opened_with(
        browser,
        tmp_path,
        """
        const before = window.fetch;
        window.fetch = (url, opts) => {
          if (opts && opts.method === 'POST' && !sessionStorage.getItem('refused')) {
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
    page_file.write_text(playlists_page(TOKEN), encoding="utf-8")
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
