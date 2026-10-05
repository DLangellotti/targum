"""A film at the size the importer keeps, in a real browser.

`tiny.webm` is 64x36 and `tall.webm` is 36x64, and that is the right size for a fixture
right up until the size is the bug. Watching is a grid, and a grid track left `auto` is
sized by what is in it: a reel comes down 480x854 (`video.VIDEO_HEIGHT` is the short
side), and at that size the picture made its own row 2562px tall on a 900px window, with
the line it was saying and the transport both under the fold. A 64px film never could,
so every test of this mode passed over a page nobody could use (design review,
2026-09-20). The mode went with targum-internal#422; the sizes did not, and the picture
and its controls are held to the window here whichever way it stands.

`reel.webm` is 480x854 and `film.webm` is 854x480: one second of one colour, under 5KB
each, so they are committed rather than generated.
"""

from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")

# The fixtures live in the browser module rather than a conftest, so they are
# imported by name to register them here.
from test_reader_browser import (  # noqa: E402, F401
    address,
    browser,
    open_reader,
    opened,
    video_reader,
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
    return {
      left: r.left, top: r.top, right: r.right, bottom: r.bottom,
      width: r.width, height: r.height,
    };
  };
  return {
    window: { right: document.documentElement.clientWidth, bottom: window.innerHeight },
    panel: box('#video'),
    picture: box('#video .video-el'),
    controls: box('#video .film-ctl'),
  };
}
"""


@pytest.mark.parametrize("film", ["reel.webm", "film.webm"])
@pytest.mark.parametrize("view", ["beside", "theatre"])
def test_the_picture_and_its_controls_stay_in_the_window(
    browser,  # noqa: F811
    tmp_path,
    film,
    view,
) -> None:
    """The picture and the row under it are on the screen, at every size a reader holds —
    a phone both ways up, a tablet, a laptop, and a laptop window that is short — whichever
    way the picture stands (targum-internal#422). It was the full-screen mode that
    overflowed before: a grid track sized by a film at the importer's size."""
    built = video_reader(tmp_path, film=film)
    for size in WINDOWS:
        context, page = open_reader(browser, built, viewport=size)
        try:
            page.evaluate(f"() => localStorage.setItem('targum:film-view', '{view}')")
            page.reload()
            page.wait_for_selector("#video:not([hidden])")
            page.wait_for_function(
                "() => document.getElementById('video').style.cssText.includes('--film')"
            )
            page.wait_for_timeout(150)
            got = page.evaluate(LAID_OUT)
        finally:
            context.close()
        for name in ("picture", "controls"):
            seen = got[name]
            assert seen["left"] >= -1 and seen["top"] >= -1, (film, view, size, name, got)
            assert seen["right"] <= got["window"]["right"] + 1, (film, view, size, name, got)
            assert seen["bottom"] <= got["window"]["bottom"] + 1, (film, view, size, name, got)
        # The row is as wide as the picture it plays, and stands under it.
        assert got["controls"]["top"] >= got["picture"]["bottom"] - 1, (film, view, size, got)


@pytest.mark.parametrize("width", [320, 390, 768])
def test_an_upright_film_on_a_phone_is_held_under_half_the_window(
    browser,  # noqa: F811
    tmp_path,
    width,
) -> None:
    """On a phone the picture stands above its transcript, the window's width — and a
    reel at the window's width is a column of film taller than the window, so it is held
    to under half of it and stands in the middle, with the transcript under it."""
    built = video_reader(tmp_path, film="reel.webm", lines=12)
    context, page = open_reader(browser, built, viewport={"width": width, "height": 844})
    try:
        page.wait_for_function("() => document.getElementById('video').classList.contains('tall')")
        page.wait_for_timeout(150)
        got = page.evaluate(LAID_OUT)
    finally:
        context.close()
    assert got["panel"]["left"] <= 1 and got["panel"]["right"] >= got["window"]["right"] - 1, got
    assert got["picture"]["height"] <= 844 * 0.46, got
    assert got["picture"]["height"] > got["picture"]["width"], got
    middle = (got["picture"]["left"] + got["picture"]["right"]) / 2
    assert abs(middle - got["window"]["right"] / 2) < 3, f"it stands in the middle: {got}"


BEFORE_IT_LOADS = """
() => {
  const panel = document.getElementById('video');
  const seen = panel.querySelector('.video-el').getBoundingClientRect();
  return {
    loaded: panel.querySelector('.video-el').readyState,
    tall: panel.classList.contains('tall'),
    film: panel.style.getPropertyValue('--film').trim(),
    width: Math.round(seen.width),
    height: Math.round(seen.height),
  };
}
"""


def test_a_reel_is_upright_before_it_loads(browser, tmp_path, monkeypatch) -> None:  # noqa: F811
    """The page learnt a film's shape from the film, so until the metadata landed a reel
    stood in the stylesheet's 16/9 and then jumped upright. The build measures the cut
    and the page carries it. Here the film is never answered at all, so the only thing
    that can have stood the frame upright is what the page was built with."""
    from targum.audio import tools

    # Said rather than probed, so the test does not need an ffprobe to be installed.
    monkeypatch.setattr(tools, "frame", lambda path: [480, 854])
    built = video_reader(tmp_path, film="reel.webm")
    context = opened(browser, {"width": 390, "height": 844})
    try:
        page = context.new_page()
        page.route("**/*.webm*", lambda route: None)
        page.goto(address(built))
        page.wait_for_selector(".pair")
        page.wait_for_selector("#video:not([hidden])")
        got = page.evaluate(BEFORE_IT_LOADS)
    finally:
        context.close()
    assert got["loaded"] == 0, f"the film was not meant to load: {got}"
    assert got["tall"] and got["film"] == "480 / 854", got
    assert got["height"] > got["width"], f"the frame is upright already: {got}"


def test_the_film_has_the_last_word(browser, tmp_path, monkeypatch) -> None:  # noqa: F811
    """A page told the wrong shape is put right when the film arrives: what the build
    measured is a head start, not an authority."""
    from targum.audio import tools

    monkeypatch.setattr(tools, "frame", lambda path: [854, 480])
    built = video_reader(tmp_path, film="reel.webm")
    assert 'data-film="854 / 480"' in built.read_text(encoding="utf-8")
    context, page = open_reader(browser, built, viewport={"width": 390, "height": 844})
    try:
        page.wait_for_function("() => document.getElementById('video').classList.contains('tall')")
        got = page.evaluate(BEFORE_IT_LOADS)
    finally:
        context.close()
    assert got["film"] == "480 / 854", got
