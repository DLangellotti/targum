"""Add's "Bring a post" form in a real browser, at a phone's width and a desk's
(targum-internal#158).

The node harness (`tests/js/add_post.js`) says what the form asks; this says that it
fits, that it takes the box's place, and that a real file chosen in a real input goes up
the chunked door and is quoted — the half a stub document cannot lay out.

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from targum.render.builder import add_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

TOKEN = "test-key"
QUOTE = {
    "id": "j1",
    "title": "הופעות הקיץ",
    "language": "he",
    "stage": "ready",
    "pictures_offered": 2,
}
#: Where a run leaves its pictures of the form, when somebody asks for them.
SHOTS = os.environ.get("TARGUM_SHOTS", "")


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


def a_jpeg() -> bytes:
    import io

    from PIL import Image

    out = io.BytesIO()
    Image.new("RGB", (40, 50), "white").save(out, format="JPEG")
    return out.getvalue()


@pytest.mark.parametrize("width", [375, 1280])
def test_the_form_fits_takes_the_boxs_place_and_quotes_what_was_brought(
    browser, width: int
) -> None:
    html = add_page(TOKEN)
    asked: list[tuple[str, object]] = []

    def answer(route, request):
        url = request.url.split("?")[0]
        if url.endswith("/upload/begin"):
            asked.append(("begin", request.post_data_json))
            body = {"upload": "0123456789abcdef", "chunk": 1048576}
        elif "/upload/" in url and url.endswith("/end"):
            asked.append(("end", None))
            body = {"upload": "0123456789abcdef", "picture": True}
        elif "/upload/" in url:
            body = {"got": 0}
        elif url.endswith("/prepare"):
            asked.append(("prepare", request.post_data_json))
            body = QUOTE
        elif url.endswith("/add"):
            return route.fulfill(status=200, content_type="text/html", body=html)
        else:
            body = {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route("http://add.test/**", answer)
    page.goto("http://add.test/add")
    assert page.is_hidden("#post-form")
    page.click("#post-open")
    assert page.is_visible("#post-form") and page.is_hidden("#bring-box")
    assert page.get_attribute("#post-open", "aria-expanded") == "true"
    assert page.evaluate("() => document.activeElement.id") == "post-handle"

    page.fill("#post-handle", "@aviv.bahar")
    page.fill("#post-name", "אביב בהר")
    page.fill("#post-words", "הופעות הקיץ\nשורה שנייה")
    page.set_input_files(
        "#post-file", files=[{"name": "slide.jpg", "mimeType": "image/jpeg", "buffer": a_jpeg()}]
    )
    assert page.locator("#post-files .given-file").count() == 1
    page.fill("#post-link", "https://www.tiktok.com/@aviv/video/7412345678901234567")
    pressed = page.get_attribute('#post-where [data-platform="tiktok"]', "aria-pressed")
    assert pressed == "true", "the link moved the switch"

    # Nothing on the page runs past its edge, and the form's controls are all on it.
    wide = page.evaluate(
        """() => ({
          scroll: document.documentElement.scrollWidth,
          width: window.innerWidth,
          out: [...document.querySelectorAll('#post-form *')]
            .filter((el) => el.getClientRects().length)
            .filter((el) => el.getBoundingClientRect().right > window.innerWidth + 0.5)
            .map((el) => el.id || el.className),
        })"""
    )
    assert wide["scroll"] <= wide["width"] and not wide["out"], wide
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(SHOTS) / f"bring-a-post-{width}.png"), full_page=True)

    page.click("#post-go")
    page.wait_for_selector("#status .filled")
    if SHOTS:
        page.screenshot(path=str(Path(SHOTS) / f"bring-a-post-quoted-{width}.png"), full_page=True)
    context.close()

    assert not thrown, thrown
    kinds = [kind for kind, _ in asked]
    assert kinds == ["begin", "end", "prepare"], kinds
    sent = asked[-1][1]
    assert isinstance(sent, dict)
    assert sent["brought"]["handle"] == "aviv.bahar"
    assert sent["brought"]["platform"] == "tiktok"
    assert sent["uploads"] == ["0123456789abcdef"]
    assert "pictures" not in sent


def test_back_puts_the_box_back(browser) -> None:
    html = add_page(TOKEN)
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.route(
        "http://add.test/**",
        lambda route, request: route.fulfill(
            status=200,
            content_type="text/html" if request.url.endswith("/add") else "application/json",
            body=html if request.url.endswith("/add") else "{}",
        ),
    )
    page.goto("http://add.test/add")
    page.click("#post-open")
    page.click("#post-back")
    assert page.is_visible("#bring-box") and page.is_hidden("#post-form")
    assert page.get_attribute("#post-open", "aria-expanded") == "false"
    context.close()
