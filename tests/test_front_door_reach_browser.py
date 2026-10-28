"""The front door's last polish from design's §14 pass (targum-internal#477).

Polish 4: the word card's Here row ran its meaning on after the form, and at 1440 the last
word wrapped alone ("crack" / «разбивают» under "Here"). The meaning now has a line of its
own under the form.

Polish 8: under a coarse pointer, four presses answered under 44px: the landing bar's mark
(21 tall), the why-fold (39 wide), the chat demo's "Save as a text" (73 × 20) and a text
page's way back to the Library (38 × 18). A tap 20px above or below the middle of a link
must still land on it.

Skips itself unless Playwright and its Chromium are installed.
"""

from __future__ import annotations

from typing import Any

import pytest

from targum.render.builder import front_page, text_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://door.test"


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


def opened(browser: Any, html: str, width: int, phone: bool) -> tuple[Any, Any, list[str]]:
    def answer(route: Any, request: Any) -> None:
        if request.resource_type == "document":
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(
        viewport={"width": width, "height": 900}, has_touch=phone, is_mobile=phone
    )
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    return context, page, thrown


#: Does a tap `dy` px above and below the middle of the element land on it?
TAPPED = """([selector, dy]) => {
  const one = document.querySelector(selector);
  one.scrollIntoView({block: 'center', behavior: 'instant'});
  const r = one.getBoundingClientRect();
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  const hit = (py) => {
    const at = document.elementFromPoint(x, py);
    return !!at && (at === one || one.contains(at));
  };
  return {up: hit(y - dy), down: hit(y + dy), w: r.width, h: r.height};
}"""


@pytest.mark.parametrize(("language", "gloss"), [("en", "crack"), ("ru", "разбивают")])
def test_the_here_row_puts_its_meaning_on_a_line_of_its_own(
    browser: Any, language: str, gloss: str
) -> None:
    context, page, thrown = opened(
        browser, front_page(language, "https://targum.page"), 1440, False
    )
    try:
        page.goto(SITE + "/")
        page.wait_for_selector("#card .facts-list dd")
        got = page.evaluate(
            """() => {
              const dd = document.querySelector('#card .facts-list dd');
              const gloss = dd.querySelector('.here-gloss');
              const form = dd.querySelector('.he');
              return gloss && {
                text: gloss.textContent, display: getComputedStyle(gloss).display,
                under: gloss.getBoundingClientRect().top >= form.getBoundingClientRect().bottom - 2,
              };
            }"""
        )
        assert got, "the Here row has no meaning of its own"
        assert got["text"] == gloss
        assert got["display"] == "block" and got["under"], got
        assert not thrown, thrown
    finally:
        context.close()


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_landing_s_small_presses_answer_a_thumb(browser: Any, language: str) -> None:
    html = front_page(language, "https://targum.page")
    context, page, thrown = opened(browser, html, 390, True)
    try:
        page.goto(SITE + "/")
        page.wait_for_selector("#lines .w")
        assert page.evaluate("() => matchMedia('(pointer: coarse)').matches")
        brand = page.locator(".bar .brand").bounding_box()
        assert brand and brand["height"] >= 44, brand
        fold = page.locator("#whyFold").bounding_box()
        assert fold and fold["width"] >= 44 and fold["height"] >= 44, fold
        save = page.evaluate(TAPPED, [".ct-sum a", 20])
        assert save["up"] and save["down"], save
        assert not thrown, thrown
    finally:
        context.close()


def test_a_text_page_s_way_back_answers_a_thumb(browser: Any) -> None:
    from targum.catalogue import Entry

    ruth = Entry(
        id="ruth",
        title="רות",
        author="Ketuvim · Ruth",
        language="he",
        source="sefaria:he:Ruth",
        blurb="Four chapters, the shortest way in.",
        words=100,
        english="Ruth",
    )
    context, page, thrown = opened(browser, text_page(ruth, "https://targum.page"), 390, True)
    try:
        page.goto(SITE + "/library/ruth")
        page.wait_for_selector(".where a")
        back = page.evaluate(TAPPED, [".where a", 20])
        assert back["h"] < 44, "the word itself stays small; the reach is what grows"
        assert back["up"] and back["down"], back
        assert not thrown, thrown
    finally:
        context.close()
