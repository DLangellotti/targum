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

#: How long ago each row was built, in seconds, rather than a moment frozen at import.
#: `NOW` was `int(time.time())` read once when this module loaded, and a row built "7
#: hours ago" is 7 h 38 m old by the time a 38-minute suite reaches this file — which the
#: page rounds to 8. So the test passed on a short run and failed on a long one, and did
#: it deterministically rather than at random (2026-09-24). `_readers()` resolves these
#: against the clock at the moment the page is handed them.
AGES = {"vlog": 7 * 3600, "weekly": 86400, "mishna": 2 * 86400}

READERS = [
    {
        "name": "vlog",
        "document": "d1",
        "title": "A day in Tel Aviv",
        "language": "he",
        "entry": "",
        "built": -AGES["vlog"],
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
        "built": -AGES["weekly"],
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
        "built": -AGES["mishna"],
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


def _readers() -> list[dict]:
    """The rows, aged from the clock as it is now and not as it was at import."""
    now = int(time.time())
    return [{**row, "built": now + int(row["built"])} for row in READERS]


def shelf(browser, tmp_path: Path, width: int):
    page_file = tmp_path / "texts.html"
    page_file.write_text(list_page("test-key", "texts"), encoding="utf-8")
    # Tall enough that the shelf under home's Continue is on screen without a scroll: a
    # scroll closes an open ⋯, which is right for a reader and not what these are about.
    context = browser.new_context(viewport={"width": width, "height": 2000})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.add_init_script(
        f"localStorage.setItem('targum:docs', {json.dumps(json.dumps(DOCS))});"
        f"const readers = {json.dumps(_readers())};"
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
    """Board Main's row (P4, 2026-10-09): the title with a quiet line under it — where you
    are with it, its length, its English, its playlists — then its kind as a tag, how
    much of it you know as a meter, and when at the end."""
    context, page, thrown = shelf(browser, tmp_path, 1280)
    first = page.locator("#library-list li").first
    facts = first.locator(".book-facts").inner_text()
    tag = first.locator(".row-tag").inner_text()
    known = first.locator(".row-meter").get_attribute("aria-label")
    end = first.locator(".row-end").inner_text()
    said = first.locator(".row-end").get_attribute("aria-label")
    statuses = page.locator("#library-list .fact-status").all_inner_texts()
    context.close()
    assert "10 min video" in facts
    # No rung and no CEFR code on a row (design.md §12, "A text is named in everyday
    # words", 2026-10-09).
    assert "Bet" not in facts and "A2" not in facts
    assert tag.strip() == "Video"
    assert known == "You know 72%"
    assert end.strip() == "7 hours ago" and said == "Uploaded 7 hours ago"
    assert "In Morning" in facts
    assert [one.strip() for one in statuses] == ["Finished", "3 of 6", "New"]
    assert not thrown


def test_a_library_text_says_when_it_was_opened_not_added(browser, tmp_path: Path) -> None:
    context, page, _ = shelf(browser, tmp_path, 1280)
    row = page.locator("#library-list li").nth(2)
    facts = row.locator(".book-facts").inner_text()
    said = row.locator(".row-end").get_attribute("aria-label") or ""
    context.close()
    assert "3 min read" in facts
    assert "Uploaded" not in said, "a library text came to everybody at once"


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


def test_on_a_phone_the_row_keeps_its_title_and_its_line(browser, tmp_path: Path) -> None:
    """Board HomePhone: the picture, the title and its line; the tag folds away, the
    status stays in the line, and a known share keeps its meter under it (audit Q7,
    2026-10-09). The row keeps ⋯ alone, and Add to playlist is inside it."""
    context, page, thrown = shelf(browser, tmp_path, 390)
    first = page.locator("#library-list li").first
    pill = first.locator(".row-tag").is_visible()
    folded = first.locator(".fact-status").is_visible()
    measured = page.locator("#library-list li .row-meter.meter").first
    meter = measured.count() == 0 or measured.is_visible()
    plus = page.locator("#library-list li .add-to-list").first.is_visible()
    page.locator("#library-list .row-more").first.click()
    page.wait_for_selector(".row-menu")
    added = page.locator(".row-menu a[href*='/playlists?add=']").count()
    wide = page.evaluate("() => document.documentElement.scrollWidth")
    context.close()
    assert not pill and folded and meter
    assert not plus and added == 1
    assert wide <= 390, "the page never scrolls sideways"
    assert not thrown


def test_the_nav_has_the_shelf_first_and_marks_it_here(browser, tmp_path: Path) -> None:
    context, page, _ = shelf(browser, tmp_path, 1280)
    places = page.eval_on_selector_all(
        ".site-nav a[data-nav]", "all => all.map(a => a.dataset.nav)"
    )
    here = page.get_attribute(".site-nav a[aria-current='page']", "data-nav")
    context.close()
    # First since 2026-10-08, when Your targums became home (design.md §12).
    assert places == ["texts", "library", "progress", "add"]
    assert here == "texts"


def test_a_phone_calls_the_shelf_targums(browser, tmp_path: Path) -> None:
    """One name (design.md §12, "Yours and everyone's", 2026-09-25). A phone said Texts
    from 2026-09-24, because "targums" alone read as a typo; a place with two names read
    worse. A phone's foot says "Your targums" whole since 2026-10-09, as board HomePhone
    draws it (design.md §12, "The boards are the desk")."""
    context, page, _ = shelf(browser, tmp_path, 390)
    phone = page.locator(".site-nav a[data-nav='texts']").inner_text()
    context.close()
    context, page, _ = shelf(browser, tmp_path, 1280)
    desk = page.locator(".site-nav a[data-nav='texts']").inner_text()
    context.close()
    assert phone.strip() == "Your targums"
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
    drawn = [{**_readers()[0], "drawn": True}]
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


#: Every + and ⋯ on the shelf, and whether any of them lies under the Talk to targum pill
#: in the window's width. The pill is fixed and the cards scroll only up and down, so a
#: key clear of it across the window is clear of it at every scroll position.
UNDER_THE_PILL = """() => {
  const pill = document.getElementById('talk-open').getBoundingClientRect();
  const keys = [...document.querySelectorAll('#library-list .add-to-list, #library-list .row-more')]
    .map((key) => key.getBoundingClientRect())
    .filter((key) => key.width > 0);
  return {
    pill: [Math.round(pill.left), Math.round(pill.right)],
    keys: keys.length,
    under: keys.filter((key) => key.right > pill.left && key.left < pill.right).length,
    sideways: document.documentElement.scrollWidth > window.innerWidth,
  };
}"""


@pytest.mark.parametrize("width", [1024, 1152, 1280, 1366])
def test_the_talk_pill_never_covers_a_cards_keys(browser, tmp_path: Path, width: int) -> None:
    """targum-internal#379. At a desk between 1024 and 1280px the pill sat over the
    right-hand cards' + and ⋯, and they could not be pressed until scrolled past it. The
    grid keeps its end edge clear of the pill instead (layout over reader controls)."""
    context, page, thrown = shelf(browser, tmp_path, width)
    got = page.evaluate(UNDER_THE_PILL)
    context.close()
    assert got["keys"] and got["under"] == 0, got
    assert not got["sideways"]
    assert not thrown


def test_a_longer_pill_takes_more_room(browser, tmp_path: Path) -> None:
    """The room is the pill's own width, measured, so Russian's longer words are cleared
    too and not only the English the width was first seen in."""
    context, page, _ = shelf(browser, tmp_path, 1024)
    page.evaluate(
        "() => { document.querySelector('#talk-open .talk-short').textContent = 'Поговорить с targum'; }"
    )
    page.wait_for_timeout(100)
    got = page.evaluate(UNDER_THE_PILL)
    context.close()
    assert got["keys"] and got["under"] == 0, got


#: Every link, button and field on a desk page that the pill's column of the window
#: reaches, outside the bar and the pill's own drawer. The pill is fixed and a page
#: scrolls only up and down, so a control clear of it across the window is clear of it at
#: every scroll position.
CLEAR_OF_THE_PILL = """() => {
  const pill = document.getElementById('talk-open');
  const box = pill.getBoundingClientRect();
  const away = '.site-head, #talk-open, .talk-drawer, .palette, .talk-scrim, .palette-scrim';
  const under = [...document.querySelectorAll('a, button, input, select, textarea, summary')]
    .filter((el) => !el.closest(away))
    .filter((el) => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0 && r.right > box.left && r.left < box.right;
    })
    .map((el) => el.outerHTML.slice(0, 80));
  const row = document.querySelector('.site-head-row').getBoundingClientRect();
  return {
    shown: !pill.hidden && box.width > 0,
    pill: [Math.round(box.left), Math.round(box.right)],
    under,
    sideways: document.documentElement.scrollWidth > window.innerWidth,
    bar: [Math.round(row.left), Math.round(row.right)],
  };
}"""


@pytest.mark.parametrize("width", [1024, 1280, 1440])
@pytest.mark.parametrize("which", ["texts", "library", "progress", "add"])
def test_at_a_desk_the_talk_pill_covers_nothing(browser, which: str, width: int) -> None:
    """Audit 2, gap 3: the pill sat on the Library's second "See all →", the Words table
    and the Upload card, because only a phone kept room for it. At a desk the page keeps
    its end edge clear of what the pill reaches; at 1440 the pill says "Talk" and stands
    in the margin outside the column, and the bar keeps the whole width."""
    from targum.render.builder import add_page, library_page, progress_page

    html = {
        "texts": lambda: list_page("test-key", "texts"),
        "library": lambda: library_page("test-key"),
        "progress": lambda: progress_page("test-key"),
        "add": lambda: add_page("test-key"),
    }[which]()

    def answer(route, request):  # type: ignore[no-untyped-def]
        if request.resource_type == "document":
            route.fulfill(status=200, content_type="text/html", body=html)
            return
        path = request.url.split("?")[0]
        said: dict = {"readers": _readers(), "trash": []} if path.endswith("/readers") else {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(said))

    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    page.add_init_script("sessionStorage.setItem('targum:arrival-over', '1');")
    page.route("http://desk.test/**", answer)
    page.goto(f"http://desk.test/{which}?k=test-key")
    page.wait_for_timeout(600)
    got = page.evaluate(CLEAR_OF_THE_PILL)
    context.close()
    assert got["shown"], got
    assert got["under"] == [], got
    assert not got["sideways"], got
    if width == 1440:
        # The pill stands in the margin: nothing moved, and the column is the board's.
        assert got["bar"][1] - got["bar"][0] >= 1248, got
