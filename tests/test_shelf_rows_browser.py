"""The shelf row in a real browser (design.md §12, 2026-09-24).

What a text is at a glance: its length, level, known share, when it came, its playlists
and its status, with Add to playlist and a ⋯ holding the rest.

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from targum.render.builder import list_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

NOW = int(time.time())

READERS = [
    {
        "name": "vlog",
        "document": "d1",
        "title": "A day in Tel Aviv",
        "language": "he",
        "entry": "",
        "built": NOW - 7 * 3600,
        "minutes": 9,
        "seconds": 612,
        "video": True,
        "level": {"rung": "ב", "name": "bet", "cefr": "A2"},
        "known": 0.72,
        "words": 410,
        "sections": 1,
        "chapters": [],
        "playlists": ["Morning"],
    },
    {
        "name": "weekly",
        "document": "d4",
        "title": "מבט שבועי",
        "language": "he",
        "entry": "",
        "built": NOW - 86400,
        "minutes": 22,
        "seconds": 0,
        "sections": 6,
        "chapters": [
            {"number": n, "title": f"פרק {n}", "file": f"sec-{n}.html", "ready": True}
            for n in range(1, 7)
        ],
        "readyChapters": 6,
    },
    {
        "name": "news",
        "document": "d5",
        "title": "חדשות",
        "english": "News",
        "language": "he",
        "entry": "news-1",
        "built": NOW - 2 * 86400,
        "minutes": 3,
        "seconds": 0,
        "sections": 1,
        "chapters": [],
    },
]
DOCS = {"d1": {"sections": {"1": True}}, "d4": {"sections": {"1": True, "2": True, "3": True}}}


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


def shelf(browser, tmp_path: Path, width: int):
    page_file = tmp_path / "texts.html"
    page_file.write_text(list_page("test-key", "texts"), encoding="utf-8")
    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.add_init_script(
        f"localStorage.setItem('targum:docs', {json.dumps(json.dumps(DOCS))});"
        f"const readers = {json.dumps(READERS)};"
        "window.fetch = (url, opts) => {"
        "  const path = String(url).split('?')[0];"
        "  if (opts && opts.method === 'POST') {"
        "    const posted = JSON.parse(sessionStorage.getItem('posted') || '[]');"
        "    posted.push([path.replace(/^.*?(\\/[a-z]+)$/, '$1'), JSON.parse(opts.body || '{}')]);"
        "    sessionStorage.setItem('posted', JSON.stringify(posted));"
        "  }"
        "  const said = path.endsWith('/readers') ? {readers, trash: []} : {};"
        "  return Promise.resolve(new Response(JSON.stringify(said)));"
        "};"
    )
    page.goto(page_file.as_uri())
    page.wait_for_selector("#library-list li")
    return context, page, thrown


def test_a_row_says_what_the_text_is_at_a_glance(browser, tmp_path: Path) -> None:
    context, page, thrown = shelf(browser, tmp_path, 1280)
    facts = page.locator("#library-list li").first.locator(".book-facts").inner_text()
    statuses = page.locator("#library-list .row-status").all_inner_texts()
    context.close()
    assert "10 min video" in facts
    assert "Bet · A2" in facts
    assert "You know 72%" in facts
    assert "Added 7 hours ago" in facts
    assert "In Morning" in facts
    assert [one.strip() for one in statuses] == ["Finished", "3 of 6", "New"]
    assert not thrown


def test_a_library_text_says_when_it_was_opened_not_added(browser, tmp_path: Path) -> None:
    context, page, _ = shelf(browser, tmp_path, 1280)
    facts = page.locator("#library-list li").nth(2).locator(".book-facts").inner_text()
    context.close()
    assert "3 min read" in facts
    assert "Added" not in facts, "a library text came to everybody at once"


def test_add_to_playlist_never_wraps(browser, tmp_path: Path) -> None:
    """David's screenshot: "Add to / playlist" on two lines, beside a bordered circle."""
    context, page, _ = shelf(browser, tmp_path, 1280)
    heights = page.eval_on_selector_all(
        "#library-list .add-to-list", "all => all.map(a => a.getBoundingClientRect().height)"
    )
    context.close()
    assert heights and all(height <= 46 for height in heights)


def test_the_more_menu_holds_chapters_and_delete(browser, tmp_path: Path) -> None:
    context, page, thrown = shelf(browser, tmp_path, 1280)
    page.locator("#library-list li").nth(1).locator(".row-more").click()
    page.wait_for_selector(".row-menu")
    items = page.locator(".row-menu button").all_inner_texts()
    page.locator(".row-menu button.bin").click()
    page.wait_for_selector("#library-list li.binned")
    posted = page.evaluate("() => JSON.parse(sessionStorage.getItem('posted') || '[]')")
    menus = page.locator(".row-menu").count()
    context.close()
    assert items == ["Chapters", "Delete"]
    assert posted == [["/trash", {"name": "weekly"}]]
    assert menus == 0, "the menu closes once Delete is pressed"
    assert not thrown


def test_escape_closes_the_more_menu(browser, tmp_path: Path) -> None:
    context, page, _ = shelf(browser, tmp_path, 1280)
    page.locator("#library-list .row-more").first.click()
    page.wait_for_selector(".row-menu")
    page.keyboard.press("Escape")
    gone = page.locator(".row-menu").count()
    context.close()
    assert gone == 0


def test_on_a_phone_the_status_folds_into_the_facts(browser, tmp_path: Path) -> None:
    context, page, thrown = shelf(browser, tmp_path, 390)
    first = page.locator("#library-list li").first
    pill = first.locator(".row-status").is_visible()
    folded = first.locator(".fact-status").is_visible()
    wide = page.evaluate("() => document.documentElement.scrollWidth")
    context.close()
    assert not pill and folded
    assert wide <= 390, "the page never scrolls sideways"
    assert not thrown


def test_the_nav_has_the_shelf_second_and_marks_it_here(browser, tmp_path: Path) -> None:
    context, page, _ = shelf(browser, tmp_path, 1280)
    places = page.eval_on_selector_all(
        ".site-nav a[data-nav]", "all => all.map(a => a.dataset.nav)"
    )
    here = page.get_attribute(".site-nav a[aria-current='page']", "data-nav")
    context.close()
    assert places == ["learn", "texts", "library", "progress", "add"]
    assert here == "texts"


def test_a_phone_calls_the_shelf_texts(browser, tmp_path: Path) -> None:
    """The name is lowercase always, and "targums" alone beside Learn and Library read as
    a typo; a phone says Texts, the desk Your targums (2026-09-24)."""
    context, page, _ = shelf(browser, tmp_path, 390)
    phone = page.locator(".site-nav a[data-nav='texts']").inner_text()
    context.close()
    context, page, _ = shelf(browser, tmp_path, 1280)
    desk = page.locator(".site-nav a[data-nav='texts']").inner_text()
    context.close()
    assert phone.strip() == "Texts"
    assert desk.strip() == "Your targums"


def test_a_video_with_a_poster_shows_its_picture(browser, tmp_path: Path) -> None:
    import base64

    jpeg = base64.b64decode(
        "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4n"
        "ICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACP/E"
        "ABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AVN//2Q=="
    )
    page_file = tmp_path / "texts.html"
    page_file.write_text(list_page("test-key", "texts"), encoding="utf-8")
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    drawn = [{**READERS[0], "drawn": True}]
    page.add_init_script(
        f"const readers = {json.dumps(drawn)};"
        "window.fetch = () => Promise.resolve(new Response(JSON.stringify({readers, trash: []})));"
    )
    page.route("**/thumb/**", lambda route: route.fulfill(body=jpeg, content_type="image/jpeg"))
    page.goto(page_file.as_uri())
    page.wait_for_function(
        "() => { const i = document.querySelector('#library-list .thumb img');"
        " return i && i.complete && i.naturalWidth > 0; }"
    )
    source = page.get_attribute("#library-list .thumb img", "src")
    context.close()
    assert source and "/thumb/vlog" in source
