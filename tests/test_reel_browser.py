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


DOCKED = """
() => {
  const rect = (el) => {
    const r = el.getBoundingClientRect();
    return { left: r.left, top: r.top, right: r.right, bottom: r.bottom };
  };
  const panel = document.getElementById('video');
  return {
    window: document.documentElement.clientWidth,
    panel: rect(panel),
    picture: rect(panel.querySelector('.video-el')),
    keys: [...panel.querySelectorAll('.video-keys > *')]
      .filter((el) => getComputedStyle(el).display !== 'none' && el.offsetWidth > 0)
      .map((el) => Object.assign({ name: el.className }, rect(el))),
  };
}
"""


def docked(browser, tmp_path, size):  # noqa: F811
    built = video_reader(tmp_path, film="reel.webm", lines=12)
    context, page = open_reader(browser, built, viewport=size)
    try:
        page.wait_for_function("() => document.getElementById('video').classList.contains('tall')")
        page.wait_for_timeout(150)
        return page.evaluate(DOCKED)
    finally:
        context.close()


@pytest.mark.parametrize("width", [320, 390, 768])
def test_a_docked_reel_is_a_band_on_a_phone(browser, tmp_path, width) -> None:  # noqa: F811
    """Under 60rem the picture is an occupant of the band: the sheet is the window's
    width, so no line of the page shows beside it, and its keys stand clear of a picture
    too narrow to carry a row of them."""
    got = docked(browser, tmp_path, {"width": width, "height": 844})
    assert got["panel"]["left"] <= 1 and got["panel"]["right"] >= got["window"] - 1, got
    picture = got["picture"]
    for key in got["keys"]:
        clear = key["right"] <= picture["left"] + 1 or key["left"] >= picture["right"] - 1
        assert clear, f"{key['name']} is over the picture: {got}"


def test_a_docked_reel_keeps_its_keys_in_the_panel(browser, tmp_path) -> None:  # noqa: F811
    """The bar across the panel was written for the landscape dock's 20rem. On the
    upright one "Full screen" ran off the edge with two keys under it."""
    got = docked(browser, tmp_path, {"width": 1440, "height": 900})
    assert len(got["keys"]) == 4, got
    for key in got["keys"]:
        assert key["left"] >= got["panel"]["left"] - 1, (key, got["panel"])
        assert key["right"] <= got["panel"]["right"] + 1, (key, got["panel"])
    ordered = sorted(got["keys"], key=lambda key: key["left"])
    for before, after in zip(ordered, ordered[1:], strict=False):
        assert before["right"] <= after["left"] + 1, f"two keys overlap: {before} {after}"


@pytest.mark.parametrize("film", ["reel.webm", "film.webm"])
def test_watching_keeps_a_real_film_in_the_window(browser, tmp_path, film) -> None:  # noqa: F811
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
