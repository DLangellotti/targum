"""Draw the picture a link to targum shows when it is shared (design.md §12, 2026-10-13).

One card for every public page: the lockup on paper and the line under it. 1200 × 630,
the size Facebook, LinkedIn, X and the messengers all crop the least. Drawn by a headless
Chromium from the brand's own SVG geometry (`render/assets/brand/lockup.svg`) and the
reading face, so the picture is the page's type rather than a drawing of it:

    .venv/bin/python scripts/link_preview.py

The reading face is Iowan Old Style, which macOS carries; on a machine without it the
stack falls to Palatino and Georgia, which is §5's own order. Look at the PNG before
committing it.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

BRAND = Path(__file__).resolve().parent.parent / "src" / "targum" / "render" / "assets" / "brand"
OUT = BRAND / "link-preview.png"
WIDTH, HEIGHT = 1200, 630

# §4: paper, ink, and the mark's two columns. §5: the reading face, the wordmark at 600
# with −0.01em tracking. §2: clear space of half the mark's height on every side, which
# the margins here are well past.
CARD = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><style>
  html, body { margin: 0; }
  body {
    width: %(w)dpx; height: %(h)dpx; background: #fbf9f5; color: #1c1a17;
    font-family: 'Iowan Old Style', 'Palatino Linotype', Palatino, Georgia,
      'Times New Roman', serif;
    display: flex; flex-direction: column; justify-content: center; box-sizing: border-box;
    padding: 0 112px;
  }
  /* The lockup's own proportions: the mark 72 units tall beside an 84-unit wordmark, 12
     units between them (lockup.svg), opened a little at this size so the t clears. */
  .lockup { display: flex; align-items: center; gap: 28px; }
  .lockup svg { width: 75px; height: 96px; display: block; }
  .word {
    font-size: 112px; font-weight: 600; letter-spacing: -0.01em; line-height: 1;
    color: #201e1b;
  }
  .line { margin: 58px 0 0; font-size: 58px; font-weight: 400; line-height: 1.15; }
</style></head><body>
  <div class="lockup">
    <svg viewBox="20 12 56 72" aria-hidden="true">
      <rect x="20" y="12" width="22" height="62" rx="5" fill="#201e1b"/>
      <rect x="54" y="22" width="22" height="62" rx="5" fill="#a5824f"/>
    </svg>
    <span class="word">targum</span>
  </div>
  <p class="line">Learn Hebrew from anything.</p>
</body></html>"""


def main() -> None:
    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        page.set_content(CARD % {"w": WIDTH, "h": HEIGHT})
        page.evaluate("document.fonts.ready")
        page.screenshot(path=str(OUT), clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT})
        browser.close()
    print(OUT)


if __name__ == "__main__":
    main()
