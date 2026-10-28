"""Write `public-page.css`: the rules of shared.css and reader.css a public page uses
(targum-internal#550).

    .venv/bin/python scripts/public_page_css.py            # writes the file
    .venv/bin/python scripts/public_page_css.py --check    # exits 1 if it is out of date

A public text page, the four legal pages and /about used to carry all of `shared.css` and
`reader.css`, about 315 kB, for a few dozen rules. This renders each of those pages in
Chromium with the two sheets in place, and keeps every rule whose selector matches an
element there once its states are taken off (`:hover`, `:focus-visible`, `::before` …, so
a hover or a dark-mode rule for an element on the page is kept with it). What is kept is
written in the sheets' own order, inside the `@media` and `@supports` rules it stood in,
with any `@keyframes` a kept rule names. The pages then load `public-page.css` in the two
sheets' place, and `tests/test_public_page_css_browser.py` holds both promises: the file
is what this writes today, and every element on those pages computes the same style with
it as with the two sheets, at 390 and 1440, light and dark.

Run it after changing a rule in shared.css or reader.css that a public page draws; the
test names the case. Needs Playwright's Chromium.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ASSETS = Path(__file__).resolve().parent.parent / "src" / "targum" / "render" / "assets"
TARGET = ASSETS / "public-page.css"
SOURCES = ("shared.css", "reader.css")

HEAD = """/* public-page.css — written by scripts/public_page_css.py; do not edit by hand.

   The rules of shared.css and reader.css that a public text page, the legal pages or
   /about match, in those sheets' own order (targum-internal#550). The pages load this in
   the two sheets' place: about 315 kB became this file. Change the rule in shared.css or
   reader.css and run the script again; tests/test_public_page_css_browser.py says when. */
"""

#: Every state a rule can be written for that the page does not show when it loads.
STATES = (
    r"::?(before|after|placeholder|marker|selection|first-line|first-letter|backdrop|"
    r"-webkit-[\w-]+|-moz-[\w-]+)"
    r"|:(hover|focus|focus-visible|focus-within|active|visited|target|checked|disabled|"
    r"enabled|placeholder-shown|popover-open|open|indeterminate|invalid|valid|"
    r"user-invalid|autofill)(?![\w-])"
)

KEEP = r"""([sources, states]) => {
  const stripped = (selector) => {
    const bare = selector.replace(new RegExp(states, 'g'), '').trim();
    if (bare !== '' && !/[>+~]$/.test(bare)) return bare;
    return bare.replace(/[>+~]\s*$/, '').trim() || '*';
  };
  const matches = (selectorText) => selectorText.split(',').some((part) => {
    try { return !!document.querySelector(stripped(part)); } catch (e) { return false; }
  });
  const kept = {};
  for (const sheet of document.styleSheets) {
    const name = sheet.ownerNode && sheet.ownerNode.dataset.sheet;
    if (!sources.includes(name)) continue;
    const walk = (rules, path) => {
      [...rules].forEach((rule, n) => {
        const here = path.concat(n);
        if (rule instanceof CSSStyleRule) {
          if (matches(rule.selectorText)) kept[name + ':' + here.join('.')] = true;
        } else if (rule.cssRules) {
          walk(rule.cssRules, here);
        }
      });
    };
    walk(sheet.cssRules, []);
  }
  return Object.keys(kept);
}"""

WRITE = r"""([sources, keys]) => {
  const keep = new Set(keys);
  const out = [];
  const names = new Set();
  for (const sheet of document.styleSheets) {
    const name = sheet.ownerNode && sheet.ownerNode.dataset.sheet;
    if (!sources.includes(name)) continue;
    const walk = (rules, path) => {
      const lines = [];
      [...rules].forEach((rule, n) => {
        const here = path.concat(n);
        if (rule instanceof CSSStyleRule) {
          if (keep.has(name + ':' + here.join('.'))) {
            lines.push(rule.cssText);
            const anim = rule.style.getPropertyValue('animation-name')
              || rule.style.getPropertyValue('animation');
            for (const word of (anim || '').split(/[\s,]+/)) if (word) names.add(word);
          }
        } else if (rule.cssRules && !(rule instanceof CSSKeyframesRule)) {
          const inner = walk(rule.cssRules, here);
          if (inner.length) {
            const head = rule.cssText.slice(0, rule.cssText.indexOf('{')).trim();
            lines.push(head + ' {\n' + inner.map((l) => '  ' + l).join('\n') + '\n}');
          }
        }
      });
      return lines;
    };
    out.push(...walk(sheet.cssRules, []));
  }
  for (const sheet of document.styleSheets) {
    const name = sheet.ownerNode && sheet.ownerNode.dataset.sheet;
    if (!sources.includes(name)) continue;
    for (const rule of sheet.cssRules) {
      if (rule instanceof CSSKeyframesRule && names.has(rule.name)) out.push(rule.cssText);
    }
  }
  return out;
}"""


def pages() -> dict[str, tuple[str, str]]:
    """Every public page this is for, each with the sheet that follows the two."""
    from unittest import mock

    from targum.catalogue import CATALOGUE, Entry, Line
    from targum.render.builder import about_page, legal_page, text_page

    address = "https://targum.page"
    # A text page's opening lines come from the catalogue file, which a public checkout
    # may not hold; two lines are given here so the page always draws its sample, the
    # part that carries reader.css's rules (`.pair`), wherever this runs.
    opening = [
        Line(
            source="וַיְהִי בִּימֵי שְׁפֹט הַשֹּׁפְטִים",
            target="In the days when the judges ruled",
            said={},
            drawn={},
        ),
        Line(source="וַיְהִי רָעָב בָּאָרֶץ", target="there was a famine in the land.", said={}, drawn={}),
    ]
    sample = mock.patch.object(Entry, "sample", new=property(lambda _entry: opening))
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
    with sample:
        texts = {
            "ruth-en": (text_page(ruth, address), "public.css"),
            "ruth-ru": (text_page(ruth, address, language="ru"), "public.css"),
        }
    found: dict[str, tuple[str, str]] = {
        **texts,
        "about-en": (about_page("en", address), "about.css"),
        "about-ru": (about_page("ru", address), "about.css"),
    }
    for entry in CATALOGUE:
        if entry.id.startswith("scene-"):
            found["scene"] = (text_page(entry, address), "public.css")
            break
    for which in ("privacy", "terms", "retention", "deletion"):
        found[which] = (legal_page(which, address), "public.css")
    return {name: (inlined(html), last) for name, (html, last) in found.items()}


def inlined(html: str) -> str:
    """The page with any linked stylesheet of ours put back inline, one `<style>` holding
    them all, as a page that inlines draws them: a public page links its sheets once it is
    on the desk's list (targum-internal#549), and this reads the sheets by their text."""
    import re

    from targum.render.builder import _asset, asset_address

    names = {asset_address(name): name for name in _SHEETS}
    links = [href for href in re.findall(r'<link rel="stylesheet" href="([^"]+)">', html)]
    ours = [href for href in links if href in names]
    if not ours:
        return html
    joined = "<style>" + "".join(str(_asset(names[href])) for href in ours) + "</style>"
    first = html.index(f'<link rel="stylesheet" href="{ours[0]}">')
    rest = html[first:]
    for href in ours:
        rest = rest.replace(f'<link rel="stylesheet" href="{href}">', "", 1)
    return html[:first] + joined + rest


#: Every sheet a public page this is for may name.
_SHEETS = ("tokens.css", "shared.css", "reader.css", "public-page.css", "public.css", "about.css")


def with_sources(html: str, last: str) -> str:
    """The page as it was: the two sheets in `public-page.css`'s place, each in a
    `<style data-sheet>` of its own so the page can say which sheet a rule came from."""
    from targum.render.builder import _asset

    for wanted in (("public-page.css",), ("shared.css", "reader.css")):
        joined = "".join(str(_asset(name)) for name in (*wanted, last))
        if joined in html:
            tagged = "".join(
                f'</style><style data-sheet="{name}">{_asset(name)}</style><style>'
                for name in SOURCES
            )
            return html.replace(joined, tagged + str(_asset(last)), 1)
    raise SystemExit(f"neither sheet set is in the page that ends with {last}")


def generate(browser: Any) -> str:
    keys: list[str] = []
    seen: set[str] = set()
    written: list[str] | None = None
    first = ""
    for html, last in pages().values():
        page = browser.new_page()
        page.set_content(with_sources(html, last))
        for key in page.evaluate(KEEP, [list(SOURCES), STATES]):
            if key not in seen:
                seen.add(key)
                keys.append(key)
        if not first:
            first = with_sources(html, last)
        page.close()
    page = browser.new_page()
    page.set_content(first)
    written = page.evaluate(WRITE, [list(SOURCES), keys])
    page.close()
    return HEAD + "\n" + "\n".join(written or []) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if the file is stale")
    args = parser.parse_args(argv)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as driver:
        browser = driver.chromium.launch()
        try:
            text = generate(browser)
        finally:
            browser.close()
    if args.check:
        if TARGET.read_text(encoding="utf-8") != text:
            print("public-page.css is out of date: run scripts/public_page_css.py", file=sys.stderr)
            return 1
        return 0
    TARGET.write_text(text, encoding="utf-8")
    print(f"wrote {TARGET.name}: {len(text.encode('utf-8')):,} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
