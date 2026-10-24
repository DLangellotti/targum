"""The public Library in a browser, at a phone's width and a desk's (targum-internal#519).

It was one list of 1,315 texts, 237,000px tall at 1440, with the waitlist under all of
them. Here the grouped page is opened at 390 and 1440, in English and Russian, and read
for what a template cannot prove: the ask is on the first screen, Hebrew's section comes
first, nothing scrolls sideways, the rows stand three across on a desk and one on a
phone, each row answers a thumb over its whole card, the page is the front door's ground
and face, and it fetches nothing.

Skips itself unless Playwright and its Chromium are installed:

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

from typing import Any

import pytest

from targum.catalogue import Entry, Kind
from targum.render.builder import kind_page, shelf_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)


@pytest.fixture(scope="module")
def browser():
    """One Chromium for the file."""
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


def _row(n: int, language: str, kind: Kind) -> Entry:
    hebrew = language in ("he", "arc")
    return Entry(
        id=f"{language}-{kind.value}-{n}",
        title=f"סיפור ארוך מאוד מספר {n}" if hebrew else f"Очень длинное название {n}",
        author="Omid Memarian, תרגם Gallia Hoz, 2014" if n == 1 else "Somebody Somewhere, 1990",
        language=language,
        source=f"s:{language}:{n}",
        blurb="A blurb long enough to run to a second line on a phone, and to a third. " * 2,
        words=100,
        english=f"A rather long English title, number {n}",
        named={"ru": f"Довольно длинное русское название, номер {n}"},
        blurbs={"ru": "Описание, достаточно длинное, чтобы занять вторую строку. " * 2},
        kind=kind,
    )


@pytest.fixture
def a_big_shelf(monkeypatch: pytest.MonkeyPatch) -> None:
    """Five languages, Russian the longest, about 1,300 rows: the live shelf's shape."""
    shape = {
        "ru": [Kind.talk, Kind.dialogue, Kind.story, Kind.article],
        "he": [Kind.dialogue, Kind.story, Kind.article, Kind.talk, Kind.prose, Kind.poetry],
        "it": [Kind.talk, Kind.story],
        "arc": [Kind.prose],
        "fr": [Kind.story],
    }
    rows = [
        _row(n, code, kind)
        for code, kinds in shape.items()
        for kind in kinds
        for n in range({"ru": 110, "he": 120, "it": 50, "arc": 40, "fr": 14}[code])
    ]
    monkeypatch.setattr("targum.catalogue.CATALOGUE", rows)
    monkeypatch.setattr("targum.catalogue.COLLECTIONS", [])
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")


READ = """() => {
  const ask = document.querySelector('.lib-ask .btn');
  const askTop = ask.getBoundingClientRect().top;
  const rows = [...document.querySelectorAll('.lib-row')];
  const first = rows.slice(0, 3).map((row) => Math.round(row.getBoundingClientRect().top));
  const reach = Math.min(...rows.slice(0, 12).map((row) => {
    const link = row.querySelector('a');
    // On screen first, at once (the front door scrolls smoothly): elementFromPoint
    // answers only inside the viewport.
    row.scrollIntoView({ block: 'center', behavior: 'instant' });
    const box = row.getBoundingClientRect();
    // What a tap on the blurb, low in the card, lands on: the row's own link, through
    // its ::after. Not the very corner, which the card's radius rounds away.
    const hit = document.elementFromPoint(box.left + box.width / 2, box.bottom - 10);
    return hit && (hit === link || link.contains(hit)) ? box.height : 0;
  }));
  window.scrollTo({ top: 0, behavior: 'instant' });
  const hebrew = /[\\u0590-\\u05FF]/;
  const loose = [];
  const walker = document.createTreeWalker(document.querySelector('main'), NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (!hebrew.test(node.data)) continue;
    const told = node.parentElement.closest('[lang]');
    if (!told || !['he', 'arc'].includes(told.getAttribute('lang'))) loose.push(node.data.trim());
  }
  return {
    overflow: document.documentElement.scrollWidth - window.innerWidth,
    height: document.documentElement.scrollHeight,
    askTop,
    askHref: ask.getAttribute('href'),
    sections: [...document.querySelectorAll('.lib-lang')].map((s) => s.id),
    rows: rows.length,
    first,
    reach,
    loose,
    ground: getComputedStyle(document.body).backgroundColor,
    face: getComputedStyle(document.body).fontFamily,
    carried: document.fonts.check('600 16px "Source Sans 3"'),
  };
}"""


def _open(browser: Any, html: str, width: int) -> tuple[dict[str, Any], list[str]]:
    fetched: list[str] = []

    def answer(route: Any, request: Any) -> None:
        if request.url == "http://door.test/library":
            route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
        else:
            fetched.append(request.url)
            route.abort()

    context = browser.new_context(
        viewport={"width": width, "height": 844 if width < 600 else 900},
        has_touch=width < 600,
    )
    page = context.new_page()
    page.route("**/*", answer)
    page.goto("http://door.test/library")
    got = page.evaluate(READ)
    context.close()
    return got, fetched


@pytest.mark.parametrize("width", [390, 1440])
@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_grouped_library_reads_on_a_phone_and_a_desk(
    browser: Any, a_big_shelf: None, language: str, width: int
) -> None:
    got, fetched = _open(browser, shelf_page("https://targum.page", language=language), width)

    assert not fetched, f"a reader fetches nothing: {fetched}"
    assert got["overflow"] <= 0, f"scrolls sideways by {got['overflow']}px"
    assert got["sections"][0] == "in-he", got["sections"]
    assert got["askHref"] == "/#join"
    assert got["askTop"] < (844 if width < 600 else 900), "the waitlist is on the first screen"
    # The pin: about 1,300 texts and fourteen kinds draw a few rows each.
    assert got["rows"] <= 6 * 14
    assert got["height"] < (32_000 if width < 600 else 12_000), got["height"]
    if width == 1440:
        assert len(set(got["first"])) == 1, f"three across on a desk: {got['first']}"
    else:
        assert len(set(got["first"])) == 3, f"one column on a phone: {got['first']}"
    assert got["reach"] >= 44, "every row answers a thumb over its whole card"
    assert not got["loose"], f"Hebrew with no lang: {got['loose']}"
    assert got["ground"] == "rgb(236, 231, 222)", "the desk's ground, as the front door"
    assert got["face"].startswith('"Source Sans 3"') and got["carried"], got["face"]


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_kind_page_reads_on_a_phone(browser: Any, a_big_shelf: None, language: str) -> None:
    html = kind_page("he", "story", "https://targum.page", language=language) or ""
    got, fetched = _open(browser, html, 390)
    assert not fetched and got["overflow"] <= 0
    assert got["rows"] == 120
    assert not got["loose"], got["loose"]
