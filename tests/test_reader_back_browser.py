"""A named back beside the mark, to wherever the text was opened from (targum-internal#546).

A beta reader got stuck inside a reader (2026-10-28): the one way out was the mark, and it
went to Your targums whatever page they had come from. David approved a named back beside
the mark — "← Library", "← <playlist>", "← Your targums" — out of sight while reading and
there when reached for (design.md §12, "A named back beside the mark, in the reader and
Theatre", 2026-10-28). The mark stays exactly as it was and still goes home.

Run end to end in a browser: the desk pages the server renders, a built reader, and the
tab's own store between them, at a phone's 390 and a desk's 1440 (§14.2). Theatre's half
is in `test_video_viewer_browser.py`, where a picture plays.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from targum.models import Block, BlockKind, Document, Segment, SegmentedDocument, Translation
from targum.render import render
from targum.render.builder import library_page, list_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

TOKEN = "test-key"
SITE = "http://back.test"
READER = "/reader/a-text/reader/index.html"
#: Another page of the same text: a section's neighbour.
NEIGHBOUR = "/reader/a-text/reader/sec-0002.html"

PHONE = {"width": 390, "height": 844}
DESK = {"width": 1440, "height": 900}
WIDTHS = [pytest.param(PHONE, id="390"), pytest.param(DESK, id="1440")]

#: The bar as it stands: the back, the mark and the tools, and whether it has stepped back.
BAR = """
() => {
  const box = (s) => {
    const el = document.querySelector(s);
    if (!el || !el.getClientRects().length) return null;
    const r = el.getBoundingClientRect();
    return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, height: r.height,
             opacity: getComputedStyle(el).opacity };
  };
  const back = document.getElementById('bar-back');
  return {
    said: back.textContent.replace(/[\\u2066-\\u2069]/g, '').trim(),
    href: back.getAttribute('href'),
    aria: back.getAttribute('aria-label'),
    hidden: back.hidden,
    home: document.getElementById('home').getAttribute('href'),
    back: box('#bar-back'),
    mark: box('#home'),
    tools: box('.bar > .controls'),
    bar: box('.bar'),
    quiet: document.querySelector('.bar').classList.contains('quiet'),
    focused: document.activeElement && document.activeElement.id,
    wide: document.documentElement.scrollWidth,
    window: window.innerWidth,
  };
}
"""


def built(out: Path) -> str:
    """A Hebrew text long enough to read down, with English under it."""
    lines = [f"שורה מספר {n} בטקסט הזה." for n in range(60)]
    segments = [
        Segment(id=f"{n:04d}.000-aaaaaa", block_id=f"b{n:04d}", block_index=n, index=n, text=text)
        for n, text in enumerate(lines)
    ]
    document = Document(
        source="memory",
        title="טקסט לקריאה",
        language="he",
        blocks=[
            Block(id=f"b{n:04d}", kind=BlockKind.paragraph, text=s.text)
            for n, s in enumerate(segments)
        ],
        content_hash="h",
    )
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="test/1", segments=segments
    )
    english = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        segments={s.id: f"Line {s.index}." for s in segments},
    )
    return render(document, segmented, [english], out)[0].read_text(encoding="utf-8")


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
def reader(tmp_path_factory: pytest.TempPathFactory) -> str:
    return built(tmp_path_factory.mktemp("back"))


@pytest.fixture(scope="module")
def desk() -> dict[str, str]:
    return {"/": list_page(TOKEN, "texts"), "/library": library_page(TOKEN)}


def tab(browser, reader: str, desk: dict[str, str], viewport: dict[str, int]):
    """A fresh tab on a site that serves the reader and the desk pages, and answers
    everything else with an empty account, as a box with nobody signed in would."""
    context = browser.new_context(viewport=viewport, reduced_motion="reduce", color_scheme="light")
    # One scroll rather than pages, so reading down is a scroll; and an arrival already
    # answered, so home stays home rather than asking its questions on `/welcome`.
    context.add_init_script(
        "try {"
        "  localStorage.setItem('targum:prefs', JSON.stringify({ paged: false, defaults: 4 }));"
        "  localStorage.setItem('targum:welcomed', '1');"
        "} catch (e) {}"
    )
    page = context.new_page()

    def answer(route, request):
        path = request.url[len(SITE) :].split("?")[0]
        if path.startswith("/reader/"):
            return route.fulfill(status=200, content_type="text/html", body=reader)
        if path in desk and request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=desk[path])
        body: dict[str, Any] = {"signedIn": False} if path == "/account/me" else {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    page.route(f"{SITE}/**", answer)
    return context, page


def into_reader(page, address: str = READER) -> dict[str, Any]:
    page.goto(SITE + address)
    page.wait_for_selector("#bar-back:not([hidden])")
    # The mark's link is shown once the reader has started, which waits for its store.
    page.wait_for_selector("#home:not([hidden])")
    return page.evaluate(BAR)


def desk_page(page, path: str) -> None:
    page.goto(SITE + path)
    page.wait_for_load_state("load")


@pytest.mark.parametrize("viewport", WIDTHS)
def test_opened_from_the_library_the_back_says_library_and_goes_there(
    browser, reader, desk, viewport
) -> None:
    """The first acceptance: opened from the Library, "← Library" returns there. The mark
    beside it is the mark it always was, and still goes home."""
    context, page = tab(browser, reader, desk, viewport)
    try:
        desk_page(page, "/library")
        bar = into_reader(page)
        assert bar["said"] == "Library" and bar["href"] == "/library", bar
        assert bar["aria"] == "Back to Library"
        assert bar["home"] == "/?learning=he", "the mark still goes to Your targums"

        # §14.2: the back is a thumb's reach, beside the mark and clear of the tools, and
        # nothing runs off the side of a phone.
        back, mark, tools = bar["back"], bar["mark"], bar["tools"]
        assert back["height"] >= 44, back
        assert mark["right"] <= back["left"], "the mark keeps the corner, the back beside it"
        assert back["right"] <= tools["left"], "the back stays clear of the tools"
        assert back["top"] >= bar["bar"]["top"] and back["bottom"] <= bar["bar"]["bottom"]
        assert bar["wide"] <= bar["window"], "nothing scrolls sideways"

        page.click("#bar-back")
        page.wait_for_url(SITE + "/library")
    finally:
        context.close()


@pytest.mark.parametrize("viewport", WIDTHS)
def test_from_home_and_from_a_shared_link_it_says_your_targums(
    browser, reader, desk, viewport
) -> None:
    """Opened from home it says Your targums; opened from a link somebody shared — a tab
    that has been nowhere — it says the same, and goes where the mark goes."""
    context, page = tab(browser, reader, desk, viewport)
    try:
        desk_page(page, "/")
        bar = into_reader(page)
        assert (bar["said"], bar["href"]) == ("Your targums", "/"), bar
    finally:
        context.close()

    context, page = tab(browser, reader, desk, viewport)
    try:
        bar = into_reader(page)
        assert bar["said"] == "Your targums" and bar["href"] == bar["home"], bar
    finally:
        context.close()


def test_a_page_that_names_itself_is_named(browser, reader, desk) -> None:
    """A page whose name its script draws — one playlist — says it on its body, and the
    reader opened from it names it: "← Morning reads". Nothing of it is in the address."""
    context, page = tab(browser, reader, desk, DESK)
    try:
        desk_page(page, "/library")
        page.evaluate("() => document.body.setAttribute('data-came-label', 'Morning reads')")
        bar = into_reader(page)
        assert bar["said"] == "Morning reads" and bar["href"] == "/library", bar
        assert page.evaluate("() => location.search") == "", "no name rides in the address"
    finally:
        context.close()


def test_the_next_page_and_a_reload_keep_where_it_came_from(browser, reader, desk) -> None:
    """The next section, a playlist's next item or the next scene inherit where the text
    was opened from, and so do a reload and the browser's own Back."""
    context, page = tab(browser, reader, desk, DESK)
    try:
        desk_page(page, "/library")
        assert into_reader(page)["said"] == "Library"
        assert into_reader(page, NEIGHBOUR)["said"] == "Library", "the next page keeps it"
        page.reload()
        page.wait_for_selector("#bar-back:not([hidden])")
        assert page.evaluate(BAR)["said"] == "Library", "a reload keeps it"
        page.go_back()
        page.wait_for_selector("#bar-back:not([hidden])")
        assert page.evaluate(BAR)["said"] == "Library", "Back keeps it"
    finally:
        context.close()


@pytest.mark.parametrize("viewport", WIDTHS)
def test_it_steps_back_with_the_bar_and_tab_brings_it_out_first(
    browser, reader, desk, viewport
) -> None:
    """Reading down, the back fades with the rest of the bar and the bar keeps its height;
    the first Tab brings the bar out and lands on the back (§14.3)."""
    context, page = tab(browser, reader, desk, viewport)
    try:
        desk_page(page, "/library")
        out = into_reader(page)
        assert out["back"]["opacity"] == "1"

        page.evaluate("() => window.scrollTo(0, 600)")
        page.wait_for_function("() => document.querySelector('.bar').classList.contains('quiet')")
        quiet = page.evaluate(BAR)
        assert quiet["back"]["opacity"] == "0", "it steps back with the bar"
        assert quiet["mark"]["opacity"] == "0.55", "the mark stays faint, as before"
        assert quiet["bar"]["height"] == out["bar"]["height"], "the bar's height never changes"

        page.keyboard.press("Tab")
        page.wait_for_function("() => !document.querySelector('.bar').classList.contains('quiet')")
        shown = page.evaluate(BAR)
        assert shown["focused"] == "bar-back", "the first Tab lands on the back"
        assert shown["back"]["opacity"] == "1"
        page.keyboard.press("Tab")
        assert page.evaluate("() => document.activeElement.id") == "home", "then the mark"
    finally:
        context.close()


def test_the_installed_app_keeps_the_bar_out_of_the_notch(reader) -> None:
    """Opened from a phone's home screen there is no browser Back: the page is laid out to
    the screen's edges and the bar's row starts under the status bar."""
    assert "viewport-fit=cover" in reader
    assert ".bar { padding-block-start: env(safe-area-inset-top, 0px); }" in reader
