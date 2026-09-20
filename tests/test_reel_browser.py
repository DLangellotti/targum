"""A film at the size the importer keeps, in a real browser.

`tiny.webm` is 64x36 and `tall.webm` is 36x64, and that is the right size for a fixture
right up until the size is the bug. Watching is a grid, and a grid track left `auto` is
sized by what is in it: a reel comes down 480x854 (`video.VIDEO_HEIGHT` is the short
side), and at that size the picture made its own row 2562px tall on a 900px window, with
the line it was saying and the transport both under the fold. A 64px film never could,
so every test of this mode passed over a page nobody could use (design review,
2026-09-20).

`reel.webm` is 480x854 and `film.webm` is 854x480: one second of one colour, under 5KB
each, so they are committed rather than generated.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")

# The fixtures live in the browser module rather than a conftest, so they are
# imported by name to register them here.
from test_reader_browser import (  # noqa: E402, F401
    browser,
    open_reader,
    video_reader,
    watch,
)

WINDOWS = [
    {"width": 320, "height": 568},
    {"width": 390, "height": 844},
    {"width": 844, "height": 390},
    {"width": 768, "height": 1024},
    {"width": 1440, "height": 900},
    {"width": 1440, "height": 700},
]

LAID_OUT = """
() => {
  const box = (s) => {
    const r = document.querySelector(s).getBoundingClientRect();
    return { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
  };
  return {
    window: { right: document.documentElement.clientWidth, bottom: window.innerHeight },
    picture: box('#video .video-el'),
    transport: box('#video .player'),
    keys: box('#video .video-keys'),
  };
}
"""


@pytest.mark.parametrize("film", ["reel.webm", "film.webm"])
def test_watching_keeps_a_real_film_inside_the_window(browser, tmp_path, film) -> None:
    """The picture, the keys and the transport are all on the screen, at every size a
    reader holds — a phone both ways up, a tablet, a laptop, and a laptop window that is
    short, which is where a landscape film overflowed the same way."""
    built = video_reader(tmp_path, film=film)
    for size in WINDOWS:
        context, page = open_reader(browser, built, viewport=size)
        try:
            page.wait_for_function(
                "() => document.getElementById('video').style.cssText.includes('--film')"
            )
            watch(page)
            page.wait_for_timeout(150)
            got = page.evaluate(LAID_OUT)
        finally:
            context.close()
        for name in ("picture", "transport", "keys"):
            seen = got[name]
            assert seen["left"] >= -1 and seen["top"] >= -1, (film, size, name, got)
            assert seen["right"] <= got["window"]["right"] + 1, (film, size, name, got)
            assert seen["bottom"] <= got["window"]["bottom"] + 1, (film, size, name, got)
