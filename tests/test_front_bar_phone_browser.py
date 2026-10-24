"""The public bar keeps its Sign in on a phone (targum-internal#528).

At phone width the front door's bar used to drop Sign in, so a reader coming back with an
account had no way in from the top: on the landing the foot's Sign in was 8,100px down and
on the signed-out Library about 26,000px. Here each page that wears the bar — the landing,
the olim's page, the signed-out Library and a kind page — is opened at 320 and 390 under a
touch screen, in English and Russian, and read for what a template cannot prove: Sign in
is drawn, on screen, 44px across and up, on the bar's one line beside the waitlist, with
nothing scrolling sideways, and it carries a pressed language to the sign-in page.

Skips itself unless Playwright and its Chromium are installed:

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from targum.catalogue import Entry, Kind
from targum.render.builder import aliyah_page, front_page, kind_page, shelf_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

ADDRESS = "https://targum.page"


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


@pytest.fixture
def a_small_shelf(monkeypatch: pytest.MonkeyPatch) -> None:
    """A few Hebrew stories, enough for the Library and its kind page to draw."""
    rows = [
        Entry(
            id=f"he-story-{n}",
            title=f"סיפור {n}",
            author="Somebody Somewhere, 1990",
            language="he",
            source=f"s:he:{n}",
            blurb="A short blurb.",
            words=100,
            english=f"A story, number {n}",
            kind=Kind.story,
        )
        for n in range(8)
    ]
    monkeypatch.setattr("targum.catalogue.CATALOGUE", rows)
    monkeypatch.setattr("targum.catalogue.COLLECTIONS", [])
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")


PAGES: dict[str, Callable[[str], str]] = {
    "landing": lambda language: front_page(language, ADDRESS, asked=language),
    "aliyah": lambda language: aliyah_page(language, ADDRESS, asked=language),
    "library": lambda language: shelf_page(ADDRESS, language, asked=language),
    "kind": lambda language: kind_page("he", "story", ADDRESS, language, asked=language) or "",
}

READ = """() => {
  const box = (el) => {
    if (!el || getComputedStyle(el).display === 'none') return null;
    const r = el.getBoundingClientRect();
    return { left: r.left, right: r.right, top: r.top, bottom: r.bottom,
             width: r.width, height: r.height };
  };
  const bar = document.querySelector('header .col');
  const signin = bar.querySelector('.signin');
  const hit = signin && (() => {
    const r = signin.getBoundingClientRect();
    const at = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return at === signin || signin.contains(at);
  })();
  return {
    overflow: document.documentElement.scrollWidth - window.innerWidth,
    width: window.innerWidth,
    bar: box(bar),
    brand: box(bar.querySelector('.brand')),
    signin: box(signin),
    signinHref: signin && signin.getAttribute('href'),
    signinText: signin && signin.textContent.trim(),
    join: box(bar.querySelector('.cta')),
    hit,
  };
}"""


def _open(browser: Any, html: str, width: int) -> dict[str, Any]:
    context = browser.new_context(
        viewport={"width": width, "height": 800}, has_touch=True, is_mobile=True
    )
    page = context.new_page()
    # Nothing is fetched: the page is whole, and anything it asks for is refused.
    page.route("**/*", lambda route: route.abort())
    page.set_content(html)
    read: dict[str, Any] = page.evaluate(READ)
    context.close()
    return read


@pytest.mark.usefixtures("a_small_shelf")
@pytest.mark.parametrize("width", [320, 390])
@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("name", list(PAGES))
def test_the_phone_bar_keeps_sign_in(browser, name: str, language: str, width: int) -> None:
    html = PAGES[name](language)
    assert html, f"{name} drew nothing"
    read = _open(browser, html, width)

    assert read["overflow"] <= 0, f"{name} {language} scrolls sideways at {width}"
    signin = read["signin"]
    assert signin is not None, f"{name} {language} at {width} has no Sign in in its bar"
    assert read["signinText"] == ("Войти" if language == "ru" else "Sign in")
    # §8: a thumb's 44px, across and up, and the press is the link and nothing over it.
    assert signin["width"] >= 44 and signin["height"] >= 44, (name, language, width, signin)
    assert read["hit"], f"a tap on {name}'s Sign in lands on something else"
    # On screen, inside the bar's one line, and clear of the name and the waitlist.
    assert 0 <= signin["left"] and signin["right"] <= read["width"], signin
    assert read["bar"]["height"] <= 60, f"{name}'s bar folded to two lines at {width}"
    assert signin["left"] >= read["brand"]["right"], "Sign in runs into the name"
    join = read["join"]
    assert join is not None, "the waitlist stays the bar's one call to action"
    assert signin["right"] <= join["left"], "Sign in runs into the waitlist"
    # A language the visitor pressed goes to the sign-in page with them (#925's `asked`).
    assert read["signinHref"] == f"/account/signin?lang={language}"
