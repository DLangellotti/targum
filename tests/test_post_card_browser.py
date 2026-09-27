"""The post card in a real browser, at a phone and at a desk (targum-internal#159).

design.md §12, "A post keeps its shape": the head at the top, the pictures at the shape
they were posted in and never cropped, no page wider than the window, the one link home,
and nothing fetched by the page.

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

import pytest

pytest.importorskip("playwright.sync_api")
pytest.importorskip("PIL.Image", reason="Pillow is in the covers extra")

from test_post_card import HOME, a_post, rendered  # noqa: E402

# The fixtures live in the browser module rather than a conftest, so they are imported by
# name to register them here.
from test_reader_browser import address, browser, opened  # noqa: E402, F401

WINDOWS = {"phone": {"width": 390, "height": 844}, "desk": {"width": 1280, "height": 900}}

#: Where a screenshot of each window goes, when somebody wants to look.
SHOTS = os.environ.get("TARGUM_POST_SHOTS", "")

LAID_OUT = """
() => {
  const box = (el) => {
    const r = el.getBoundingClientRect();
    return { left: r.left, top: r.top, right: r.right, bottom: r.bottom,
             width: r.width, height: r.height };
  };
  const row = document.querySelector('.post-pictures');
  const firstRow = document.querySelector('#reader .pair');
  return {
    window: document.documentElement.clientWidth,
    page: document.documentElement.scrollWidth,
    head: box(document.querySelector('.post-head')),
    face: box(document.querySelector('.post-face')),
    row: box(row),
    rowScrolls: row.scrollWidth > row.clientWidth,
    firstRow: box(firstRow),
    pictures: [...row.querySelectorAll('img')].map((img) => ({
      box: box(img),
      natural: [img.naturalWidth, img.naturalHeight],
      said: [Number(img.getAttribute('width')), Number(img.getAttribute('height'))],
      fit: getComputedStyle(img).objectFit,
    })),
    home: document.querySelector('.post-home')?.getAttribute('href') || '',
    homeSays: document.querySelector('.post-home')?.textContent.trim() || '',
  };
}
"""


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    folder = a_post(tmp_path_factory.mktemp("post") / "post")
    rendered(folder)
    return folder / "reader" / "index.html"


@pytest.mark.parametrize("window", list(WINDOWS))
def test_the_post_reads_as_a_post(browser, built: Path, window: str) -> None:  # noqa: F811
    context = opened(browser, viewport=WINDOWS[window])
    page = context.new_page()
    asked: list[str] = []
    page.on("request", lambda request: asked.append(request.url))
    try:
        page.goto(address(built))
        page.wait_for_selector(".post-head")
        page.wait_for_function(
            "() => [...document.querySelectorAll('.post-picture img')].every((i) => i.complete)"
        )
        seen = page.evaluate(LAID_OUT)
        if SHOTS:
            Path(SHOTS).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(SHOTS) / f"post-{window}.png"), full_page=True)
    finally:
        context.close()

    assert seen["page"] <= seen["window"], "no page wider than the window"
    # The head is the top of the reader, and the caption comes after the pictures.
    assert seen["head"]["top"] < seen["row"]["top"] < seen["firstRow"]["top"]
    assert seen["head"]["top"] < 200, "the head stands where the title would"
    assert round(seen["face"]["width"]) == round(seen["face"]["height"]) == 48
    # Every picture at the shape it was posted in, and none cropped to fit.
    assert len(seen["pictures"]) == 3
    for picture in seen["pictures"]:
        width, height = picture["said"]
        drawn = picture["box"]["height"] / picture["box"]["width"]
        assert abs(drawn - height / width) < 0.01, picture
        assert picture["natural"] == picture["said"]
        assert picture["fit"] != "cover"
    assert seen["row"]["right"] <= seen["window"] + 0.5 and seen["row"]["left"] >= -0.5
    assert seen["rowScrolls"], "three pictures are a row the reader swipes"
    # On a phone one picture fills the row, with the next showing at its edge.
    if window == "phone":
        first = seen["pictures"][0]["box"]
        assert first["width"] > 0.8 * seen["row"]["width"]
    assert seen["home"] == HOME and seen["homeSays"] == "On Instagram"
    # Nothing leaves the page's own origin, and no picture is asked for at all: every one
    # was in the page. (A served reader asks its own server who is reading, which is
    # the reader's and not the card's.)
    # Parsed, not split at "/private": that is where a temporary folder starts on a Mac
    # and nowhere else, so on Linux the "origin" was the whole address.
    served = urlparse(address(built))
    origin = f"{served.scheme}://{served.netloc}"
    fetched = [url for url in asked if not url.startswith("data:")]
    assert fetched[0] == address(built)
    assert all(url.startswith(origin + "/") for url in fetched), fetched
    assert not [url for url in fetched if url.endswith((".webp", ".jpg", ".png"))], fetched
