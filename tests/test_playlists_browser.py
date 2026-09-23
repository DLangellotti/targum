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
    "items": [
        {
            "position": 0,
            "reader": "cheese",
            "job": None,
            "title": "Cheese swirls",
            "failed": False,
            "open": "/reader/cheese/reader/index.html",
        },
        {
            "position": 1,
            "reader": None,
            "job": "j2",
            "title": "Raiba",
            "failed": True,
            "open": None,
        },
    ],
}

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
  const one = {id: 1, name: 'Kitchen', count: 2, first: 'cheese'};
  if (path === '/playlists.json') return said({ playlists: [one] });
  if (path === '/playlists/1.json') return said(KITCHEN);
  return said({});
};
"""


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


def opened(browser, tmp_path: Path, query: str = ""):
    page_file = tmp_path / "playlists.html"
    page_file.write_text(playlists_page(TOKEN), encoding="utf-8")
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.add_init_script(f"const KITCHEN = {json.dumps(KITCHEN)};" + FAKE)
    page.goto(page_file.as_uri() + query)
    page.wait_for_selector("#playlists .playlist")
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
    context, page, thrown = opened(browser, tmp_path)
    got = page.evaluate(
        """() => ({
          sheet: document.getElementById('adding').hidden,
          start: document.querySelector('.playlist .start').getAttribute('href'),
          titles: [...document.querySelectorAll('.item-title')].map(n => n.textContent),
          upFirst: document.querySelector('.item .item-keys button').disabled,
          downLast: [...document.querySelectorAll('.item')].pop()
            .querySelectorAll('.item-keys button')[1].disabled,
          failed: document.querySelector('.item.failed .item-state').textContent,
        })"""
    )
    page.locator(".item").first.locator("button", has_text="↓").click()
    page.wait_for_timeout(100)
    sent = posted(page)
    context.close()
    assert not thrown, thrown
    assert got == {
        "sheet": True,
        "start": "/reader/cheese/reader/index.html?list=1&at=0&k=test-key",
        "titles": ["Cheese swirls", "Raiba"],
        "upFirst": True,
        "downLast": True,
        "failed": "We couldn't make this one.",
    }
    assert sent == [["/playlists/1", {"do": "move", "position": 0, "by": 1}]]


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
