"""The build card in a real browser, in a frame, with a host in miniature around it.

design.md §12, "A card in someone else's chat" (2026-10-06): the card takes the host's
theme, draws the rows a tool result hands it, follows the build by asking the host for
`check_job` and for nothing else, and opens its door through the host. The host here is
a page of a few lines that speaks the MCP Apps bridge the way Claude and ChatGPT do.

    uv sync --extra browser && uv run playwright install chromium

Set `TARGUM_CARD_SHOTS` to a folder to keep a picture of the card in each theme.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api")

from test_reader_browser import browser, opened  # noqa: E402, F401

from targum.render.builder import build_card  # noqa: E402

SHOTS = os.environ.get("TARGUM_CARD_SHOTS", "")

#: The host's own ground behind the frame, light and dark, so a picture shows the card
#: as it sits in a conversation. The host's colours, not ours.
GROUND = {"light": "#faf9f5", "dark": "#262624"}

WORKING = {
    "id": "j1",
    "title": "שיר השירים",
    "english": "The Song of Songs",
    "language": "he",
    "stage": "working",
    "done": 12,
    "total": 40,
    "unit": "sentences",
    "seconds_left": 190,
    "said": "12 of 40 sentences ready, about 3 minutes left.",
}
NEARLY = {**WORKING, "done": 30, "said": "30 of 40 sentences ready, about a minute left."}
DONE = {
    **WORKING,
    "stage": "done",
    "done": 40,
    "said": "It's ready to read.",
    "open": "https://targum.page/r/abcdefgh",
}

HOST = """
<!doctype html>
<html><head><meta charset="utf-8">
<style>
  html { color-scheme: %(theme)s; }
  html, body { margin: 0; background: %(ground)s; }
  iframe { border: 0; display: block; width: 440px; height: 260px; margin: 24px; }
</style></head>
<body>
<iframe id="f" sandbox="allow-scripts allow-same-origin"></iframe>
<script>
  const RESULTS = %(results)s;
  const ANSWER = %(answer)s;
  window.calls = [];
  window.opened = "";
  const frame = document.getElementById("f");
  let step = 0;
  const post = (message) => frame.contentWindow.postMessage({ jsonrpc: "2.0", ...message }, "*");
  const reply = (id, result) => post({ id, result });
  window.addEventListener("message", (event) => {
    if (event.source !== frame.contentWindow) return;
    const m = event.data;
    if (m.method === "ui/initialize") {
      reply(m.id, {
        protocolVersion: "2026-01-26",
        hostCapabilities: { serverTools: {}, openLinks: {} },
        hostInfo: { name: "host", version: "0" },
        hostContext: { theme: "%(theme)s" },
      });
    } else if (m.method === "ui/notifications/initialized") {
      post({ method: "ui/notifications/tool-input", params: { arguments: { id: "j1" } } });
      post({
        method: "ui/notifications/tool-result",
        params: { content: [{ type: "text", text: JSON.stringify(RESULTS[0]) }],
                  structuredContent: RESULTS[0] },
      });
    } else if (m.method === "tools/call") {
      window.calls.push(m.params);
      if (!ANSWER) return;
      step += 1;
      const rows = RESULTS[Math.min(step, RESULTS.length - 1)];
      setTimeout(() => reply(m.id, { content: [{ type: "text", text: JSON.stringify(rows) }],
                                     structuredContent: rows }), 30);
    } else if (m.method === "ui/open-link") {
      window.opened = m.params.url;
      reply(m.id, {});
    }
  });
  frame.srcdoc = %(card)s;
</script>
</body></html>
"""


def hosted(theme: str, results: list[dict[str, Any]], answer: bool = True) -> str:
    return HOST % {
        "ground": GROUND[theme],
        "theme": theme,
        "results": json.dumps(results, ensure_ascii=False),
        "answer": "true" if answer else "false",
        # Inside a <script>, so the card's own closing tags must not close it.
        "card": json.dumps(build_card()).replace("</", "<\\/"),
    }


def _frame(page: Any) -> Any:
    page.wait_for_function("document.getElementById('f').contentDocument?.getElementById('card')")
    frame = page.frame_locator("#f")
    return frame


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_card_takes_the_host_s_theme_and_draws_the_rows(browser, theme: str) -> None:  # noqa: F811
    context = opened(browser, viewport={"width": 520, "height": 340}, scrolling=False)
    page = context.new_page()
    fetched: list[str] = []
    page.on("request", lambda request: fetched.append(request.url))
    page.set_content(hosted(theme, [WORKING], answer=False))
    card = _frame(page)
    card.locator("#said").filter(has_text="12 of 40").wait_for()

    assert card.locator("html").get_attribute("data-theme") == theme
    title = card.locator("#title")
    assert title.text_content() == "שיר השירים"
    assert title.get_attribute("dir") == "rtl" and title.get_attribute("lang") == "he"
    assert card.locator("#english").text_content() == "The Song of Songs"
    assert card.locator("#bar").is_visible()
    assert card.locator("#bar").get_attribute("aria-valuenow") == "30"
    assert card.locator("#door").is_hidden(), "no door until the text is ready"
    # The card asked to follow at once, for check_job, holding the tool's longest wait.
    page.wait_for_function("window.calls.length === 1")
    assert page.evaluate("window.calls") == [
        {"name": "check_job", "arguments": {"id": "j1", "wait_seconds": 25}}
    ]
    ink = card.locator("#said").evaluate("el => getComputedStyle(el).color")
    assert ink == ("rgb(230, 225, 216)" if theme == "dark" else "rgb(28, 26, 23)")
    assert fetched == [], f"the card fetched {fetched}"

    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.locator("#f").screenshot(path=str(Path(SHOTS) / f"build-card-{theme}.png"))
    context.close()


def test_the_card_follows_until_done_and_opens_its_door_through_the_host(browser) -> None:  # noqa: F811
    context = opened(browser, viewport={"width": 520, "height": 340}, scrolling=False)
    page = context.new_page()
    page.set_content(hosted("light", [WORKING, NEARLY, DONE]))
    card = _frame(page)
    card.locator("#door").wait_for(state="visible")

    assert card.locator("#said").text_content() == "It's ready to read."
    assert card.locator("#bar").get_attribute("aria-valuenow") == "100"
    door = card.locator("#door")
    assert door.get_attribute("href") == "https://targum.page/r/abcdefgh"
    # Two asks, both for check_job, and none once the build was done.
    page.wait_for_timeout(300)
    calls = page.evaluate("window.calls")
    assert [call["name"] for call in calls] == ["check_job", "check_job"]

    door.click()
    page.wait_for_function("window.opened !== ''")
    assert page.evaluate("window.opened") == "https://targum.page/r/abcdefgh"
    if SHOTS:
        page.locator("#f").screenshot(path=str(Path(SHOTS) / "build-card-done.png"))
    context.close()


def test_a_host_that_turns_dark_is_followed(browser) -> None:  # noqa: F811
    context = opened(browser, viewport={"width": 520, "height": 340}, scrolling=False)
    page = context.new_page()
    page.set_content(hosted("light", [WORKING], answer=False))
    card = _frame(page)
    card.locator("#said").filter(has_text="12 of 40").wait_for()
    page.evaluate(
        """() => document.getElementById('f').contentWindow.postMessage(
          { jsonrpc: '2.0', method: 'ui/notifications/host-context-changed',
            params: { theme: 'dark' } }, '*')"""
    )
    page.wait_for_function(
        "document.getElementById('f').contentDocument.documentElement.dataset.theme === 'dark'"
    )
    context.close()
