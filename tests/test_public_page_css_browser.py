"""The public text, legal and about pages carry only the CSS they use (targum-internal#550).

They used to inline all of shared.css and reader.css, about 315 kB, for a few dozen rules;
they now load `public-page.css`, which `scripts/public_page_css.py` writes from those two
sheets. Two promises, both held here in Chromium:

- the file is what the script writes today, so a rule changed in shared.css or reader.css
  that a public page draws cannot quietly fall out of step;
- every element on every one of those pages, and its ::before and ::after, computes the
  same style with the file as with the two sheets, at 390 and 1440, light and dark.

Skips itself without Playwright.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

from targum.render.builder import _asset

pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "public_page_css.py"


@pytest.fixture(scope="module")
def script() -> Any:
    spec = importlib.util.spec_from_file_location("public_page_css", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


READ = r"""() => {
  const out = [];
  for (const el of document.querySelectorAll('*')) {
    for (const pseudo of [null, '::before', '::after']) {
      const cs = getComputedStyle(el, pseudo);
      if (pseudo && (cs.content === 'none' || cs.content === 'normal')) {
        out.push(null);
        continue;
      }
      const style = {};
      for (let k = 0; k < cs.length; k++) style[cs[k]] = cs.getPropertyValue(cs[k]);
      out.push([el.tagName.toLowerCase() + '.' + String(el.className) + (pseudo || ''), style]);
    }
  }
  return out;
}"""


def test_public_page_css_is_what_the_script_writes(chromium: Any, script: Any) -> None:
    written = script.TARGET.read_text(encoding="utf-8")
    assert script.generate(chromium.browser()) == written, (
        "public-page.css is out of date: run scripts/public_page_css.py"
    )


def test_the_pages_load_it_in_the_two_sheets_place(script: Any) -> None:
    for name, (html, last) in script.pages().items():
        shipped = "".join(str(_asset(n)) for n in ("tokens.css", "public-page.css", last))
        assert shipped in html, name
        assert str(_asset("reader.css")) not in html, name
        assert str(_asset("shared.css")) not in html, name


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [390, 1440])
def test_every_element_computes_the_same_style(
    chromium: Any, script: Any, width: int, scheme: str
) -> None:
    browser = chromium.browser()
    different: list[str] = []
    for name, (html, _last) in script.pages().items():
        before = html.replace(
            str(_asset("public-page.css")),
            str(_asset("shared.css")) + str(_asset("reader.css")),
            1,
        )
        drawn = []
        for page_html in (before, html):
            context = browser.new_context(
                viewport={"width": width, "height": 900}, color_scheme=scheme
            )
            page = context.new_page()
            page.set_content(page_html)
            drawn.append(page.evaluate(READ))
            context.close()
        for was, now in zip(drawn[0], drawn[1], strict=True):
            if was == now:
                continue
            if was is None or now is None:
                different.append(f"{name}: a pseudo-element came or went")
                continue
            for prop, value in was[1].items():
                if now[1].get(prop) != value:
                    different.append(f"{name} {was[0]}: {prop} {value} -> {now[1].get(prop)}")
    assert not different, "\n".join(different[:20])
