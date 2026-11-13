"""Our own plain forms still post in a real browser (qa-claude on targum#1209).

Every page here sends `Referrer-Policy: no-referrer`, under which a browser's own
same-origin form post says `Origin: null` beside `Sec-Fetch-Site: same-origin`. The
cross-site refusal (#688, #705) has to let that through, or the waitlist and the signup
on the front page and /connect answer every reader 403 with JavaScript off.

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from test_signup_door import OPEN, SHUT, _box, _switched

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


@pytest.mark.parametrize(
    ("page", "switches", "posted"),
    [
        ("/", SHUT, "/waitlist"),
        ("/", OPEN, "/signup"),
        ("/connect", SHUT, "/waitlist"),
        ("/connect", OPEN, "/signup"),
    ],
)
def test_a_join_form_posts_with_javascript_off(
    browser,
    page: str,
    switches: dict[str, str],
    posted: str,
    tmp_path: Path,
    free_port: Callable[[], int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    links: list[tuple[str, str]] = []
    _switched(monkeypatch, switches)
    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "1")
    port, store = _box(tmp_path, free_port, links)
    address = "reader@example.com"
    store.invite(address)
    context = browser.new_context(java_script_enabled=False)
    try:
        tab = context.new_page()
        tab.goto(f"http://127.0.0.1:{port}{page}")
        form = tab.locator(f'form.join-form[action^="{posted}"]').first
        field = form.locator('input[name="email"]')
        field.fill(address)
        with tab.expect_response(lambda response: response.request.method == "POST") as got:
            field.press("Enter")
        response = got.value
        sent = response.request.all_headers()
        assert response.status == 200, (sent, response.status)
        # What makes this the case qa-claude measured, and not a kinder one.
        assert sent.get("origin") == "null", sent
        assert sent.get("sec-fetch-site") == "same-origin", sent
        assert links and links[-1][0] == address
    finally:
        context.close()
