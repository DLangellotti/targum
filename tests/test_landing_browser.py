"""The front door's demos, run in a browser: the Hebrew they draw says it is Hebrew.

`landing.js` writes the word card, the film's lines and caption and the Genesis verses
as it runs, so the runs it draws are not in the page a template renders and
`test_brand.test_every_hebrew_run_on_the_front_door_says_its_language` cannot see them.
Here the page is opened, every word in the film is pressed so every card is drawn, and
the Torah demo is walked through each of its modes, reading the page after each step
(targum-internal#517, design.md §14 line 3).

Skips itself unless Playwright and its Chromium are installed:

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest

from targum.render.builder import front_page

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


#: Reads every text node with a Hebrew letter in it and names the ones whose nearest
#: `lang` is not Hebrew, Aramaic or Yiddish, or says no direction beside it.
WALK = """() => {
  const loose = new Set();
  const HEBREW = /[\\u0590-\\u05FF\\uFB1D-\\uFB4F]/;
  const read = (where) => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (!HEBREW.test(node.data)) continue;
      const holder = node.parentElement;
      if (holder.closest('script, style, template')) continue;
      const told = holder.closest('[lang]');
      const lang = told && told.getAttribute('lang');
      if (!['he', 'arc', 'yi'].includes(lang) || !told.hasAttribute('dir')) {
        loose.add(where + ': <' + holder.tagName.toLowerCase() + ' class="' +
          holder.className + '"> ' + node.data.trim().slice(0, 24));
      }
    }
  };
  read('as drawn');
  const ids = [...document.querySelectorAll('#lines .w')].map((w) => w.dataset.id);
  for (const id of ids) {
    const word = document.querySelector('#lines .w[data-id="' + id + '"]');
    if (word) word.click();
    read('card ' + id);
  }
  for (const mode of ['read', 'verse', 'aliyah']) {
    document.querySelector('[data-mode="' + mode + '"]').click();
    read(mode);
    for (let step = 0; step < 12; step++) {
      const go = document.querySelector('#torahFoot [data-go]');
      if (!go || go.dataset.go === 'restart') break;
      go.click();
      read(mode + ' ' + step);
    }
  }
  return { loose: [...loose], words: ids.length };
}"""


@pytest.mark.parametrize("language", ["en", "ru"])
def test_every_hebrew_run_the_demos_draw_says_its_language(browser, language: str) -> None:
    html = front_page(language, "https://targum.page")

    def answer(route, request):
        if urlparse(request.url).path == "/":
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route("http://door.test/**", answer)
    page.goto("http://door.test/")
    page.wait_for_selector("#lines .w")
    got = page.evaluate(WALK)
    context.close()

    assert not thrown, thrown
    assert got["words"] > 20, "the film drew its words"
    assert not got["loose"], "§14: Hebrew with no lang or no dir:\n" + "\n".join(got["loose"])
