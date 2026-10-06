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


# --- the text card (2026-10-06) ------------------------------------------------------

#: A recording's short-lived address, as `mcp_http.text_card_meta` writes one. Answered
#: by the test's own route, never the network.
HEARD = "https://targum.page/heard?t=abcdefghijklmnopqrstuvwxyz012345"
META = "targum.page/texts"

SONG = {
    "from": "mine",
    "name": "שיר-השירים-he",
    "title": "שיר השירים",
    "language": "he",
    "reader": "https://targum.page/r/abcdefgh",
    "known_share": 0.72,
    "words": 2600,
}
RUTH = {
    "from": "library",
    "id": "ruth",
    "title": "מגילת רות",
    "english": "The Book of Ruth",
    "minutes": 19,
    "known_share": 0.48,
    "on_shelf": True,
    "reader": "https://targum.page/r/ijklmnop",
}
CAFE = {
    "from": "library",
    "id": "cafe-dialogue",
    "title": "בבית הקפה",
    "english": "In a café",
    "minutes": 3,
    "on_shelf": False,
    "reader": "",
}

TEXT_HOST = """
<!doctype html>
<html><head><meta charset="utf-8">
<style>
  html { color-scheme: %(theme)s; }
  html, body { margin: 0; background: %(ground)s; }
  iframe { border: 0; display: block; width: 440px; height: %(height)spx; margin: 24px; }
</style></head>
<body>
<iframe id="f" sandbox="allow-scripts allow-same-origin"></iframe>
<script>
  const RESULT = %(result)s;
  window.calls = [];
  window.opened = "";
  const frame = document.getElementById("f");
  const post = (message) => frame.contentWindow.postMessage({ jsonrpc: "2.0", ...message }, "*");
  window.addEventListener("message", (event) => {
    if (event.source !== frame.contentWindow) return;
    const m = event.data;
    if (m.method === "ui/initialize") {
      post({ id: m.id, result: {
        protocolVersion: "2026-01-26",
        hostCapabilities: { serverTools: {}, openLinks: {} },
        hostInfo: { name: "host", version: "0" },
        hostContext: { theme: "%(theme)s" },
      } });
    } else if (m.method === "ui/notifications/initialized") {
      post({ method: "ui/notifications/tool-result", params: RESULT });
    } else if (m.method === "tools/call") {
      window.calls.push(m.params);
    } else if (m.method === "ui/open-link") {
      window.opened = m.params.url;
      post({ id: m.id, result: {} });
    }
  });
  frame.srcdoc = %(card)s;
</script>
</body></html>
"""


def text_hosted(
    theme: str, rows: dict[str, Any], meta: list[dict[str, Any]], height: int = 220
) -> str:
    from targum.render.builder import build_text_card

    result = {
        "content": [{"type": "text", "text": json.dumps(rows, ensure_ascii=False)}],
        "structuredContent": rows,
        "_meta": {META: meta},
    }
    return TEXT_HOST % {
        "ground": GROUND[theme],
        "theme": theme,
        "height": height,
        "result": json.dumps(result, ensure_ascii=False),
        "card": json.dumps(build_text_card()).replace("</", "<\\/"),
    }


def _later(minutes: int = 20) -> int:
    import time

    return int((time.time() + minutes * 60) * 1000)


def _silence() -> bytes:
    """A tenth of a second of silence as a WAV, for the route to answer the card with."""
    import io
    import wave

    out = io.BytesIO()
    with wave.open(out, "wb") as sound:
        sound.setnchannels(1)
        sound.setsampwidth(2)
        sound.setframerate(8000)
        sound.writeframes(b"\x00\x00" * 800)
    return out.getvalue()


def _cards(page: Any) -> Any:
    page.wait_for_function(
        "document.getElementById('f').contentDocument?.querySelector('.card-text')"
    )
    return page.frame_locator("#f")


def _shot(page: Any, name: str) -> None:
    if SHOTS:
        Path(SHOTS).mkdir(parents=True, exist_ok=True)
        page.locator("#f").screenshot(path=str(Path(SHOTS) / f"{name}.png"))


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_text_card_draws_one_text_in_the_host_s_theme(browser, theme: str) -> None:  # noqa: F811
    context = opened(browser, viewport={"width": 520, "height": 300}, scrolling=False)
    page = context.new_page()
    fetched: list[str] = []
    page.on("request", lambda request: fetched.append(request.url))
    page.set_content(text_hosted(theme, RUTH, [{"door": RUTH["reader"]}], height=180))
    card = _cards(page)

    assert card.locator("html").get_attribute("data-theme") == theme
    title = card.locator(".card-title")
    assert title.text_content() == "מגילת רות"
    assert title.get_attribute("dir") == "rtl" and title.get_attribute("lang") == "he"
    assert card.locator(".card-english").text_content() == "The Book of Ruth"
    assert card.locator(".card-minutes").text_content() == "19 min"
    assert card.locator(".card-known").text_content() == "You know about 5 words in 10 here."
    door = card.locator(".card-door")
    assert door.text_content() == "Open" and door.get_attribute("href") == RUTH["reader"]
    assert card.locator(".card-play").is_hidden(), "no recording, no button"
    ink = card.locator(".card-title").evaluate("el => getComputedStyle(el).color")
    assert ink == ("rgb(230, 225, 216)" if theme == "dark" else "rgb(28, 26, 23)")
    door.click()
    page.wait_for_function("window.opened !== ''")
    assert page.evaluate("window.opened") == RUTH["reader"]
    assert page.evaluate("window.calls") == [], "the card asks for no tool"
    assert fetched == [], f"the card fetched {fetched}"
    _shot(page, f"text-card-{theme}")
    context.close()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_list_is_a_short_stack_with_a_library_door(browser, theme: str) -> None:  # noqa: F811
    context = opened(browser, viewport={"width": 520, "height": 560}, scrolling=False)
    page = context.new_page()
    fetched: list[str] = []
    page.on("request", lambda request: fetched.append(request.url))
    rows = {"count": 3, "texts": [SONG, RUTH, CAFE]}
    meta = [
        {"door": SONG["reader"]},
        {"door": RUTH["reader"]},
        {"door": "https://targum.page/library/cafe-dialogue"},
    ]
    page.set_content(text_hosted(theme, rows, meta, height=500))
    card = _cards(page)
    assert card.locator(".card-text").count() == 3
    assert card.locator("main").get_attribute("class") == "cards stack"
    # A shelf text gives its words, and is counted at the library's own pace.
    first = card.locator(".card-text").nth(0)
    assert first.locator(".card-minutes").text_content() == "20 min"
    assert first.locator(".card-english").is_hidden()
    third = card.locator(".card-text").nth(2)
    assert third.locator(".card-known").text_content() == ""
    door = third.locator(".card-door")
    assert door.text_content() == "Open in the library"
    door.click()
    page.wait_for_function("window.opened !== ''")
    assert page.evaluate("window.opened") == "https://targum.page/library/cafe-dialogue"
    assert fetched == [], f"the card fetched {fetched}"
    _shot(page, f"text-card-list-{theme}")
    context.close()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_a_text_with_a_recording_plays_it_and_fetches_nothing_else(browser, theme: str) -> None:  # noqa: F811
    context = opened(browser, viewport={"width": 520, "height": 300}, scrolling=False)
    asked: list[str] = []

    def answer(route: Any) -> None:
        asked.append(route.request.url)
        route.fulfill(status=200, body=_silence(), headers={"Content-Type": "audio/wav"})

    context.route("https://targum.page/heard**", answer)
    page = context.new_page()
    fetched: list[str] = []
    page.on("request", lambda request: fetched.append(request.url))
    meta = [
        {
            "door": RUTH["reader"],
            "audio": {"src": HEARD, "ends": _later(), "credit": "Shmuel Be'eri"},
        }
    ]
    page.set_content(text_hosted(theme, RUTH, meta, height=200))
    card = _cards(page)
    play = card.locator(".card-play")
    play.wait_for(state="visible")
    assert play.text_content().strip() == "Listen"
    assert card.locator(".card-credit").text_content() == "Read by Shmuel Be'eri"
    page.wait_for_timeout(200)
    assert fetched == [], "nothing is fetched before Listen is pressed"
    _shot(page, f"text-card-audio-{theme}")

    play.click()
    page.wait_for_function("window.calls !== undefined")
    card.locator('.card-play[aria-pressed="true"]').wait_for()
    assert card.locator(".card-play-word").text_content() == "Pause"
    page.wait_for_function(
        "document.getElementById('f').contentDocument.getElementById('ear').currentSrc !== ''"
    )
    for _ in range(50):
        if fetched:
            break
        page.wait_for_timeout(50)
    assert set(fetched) == {HEARD}, f"the card fetched {fetched}"
    assert asked and set(asked) == {HEARD}
    # It finishes on its own and the button goes back to Listen.
    card.locator('.card-play[aria-pressed="false"]').wait_for(timeout=5000)
    assert page.evaluate("window.calls") == []
    context.close()


def test_a_recording_past_its_time_has_no_button(browser) -> None:  # noqa: F811
    context = opened(browser, viewport={"width": 520, "height": 300}, scrolling=False)
    page = context.new_page()
    fetched: list[str] = []
    page.on("request", lambda request: fetched.append(request.url))
    meta = [{"door": RUTH["reader"], "audio": {"src": HEARD, "ends": _later(-1)}}]
    page.set_content(text_hosted("light", RUTH, meta, height=200))
    card = _cards(page)
    assert card.locator(".card-play").is_hidden()
    assert fetched == []
    context.close()


def test_a_recording_that_will_not_play_takes_its_button_away(browser) -> None:  # noqa: F811
    context = opened(browser, viewport={"width": 520, "height": 300}, scrolling=False)
    context.route("https://targum.page/heard**", lambda route: route.fulfill(status=404))
    page = context.new_page()
    meta = [{"door": RUTH["reader"], "audio": {"src": HEARD, "ends": _later()}}]
    page.set_content(text_hosted("light", RUTH, meta, height=200))
    card = _cards(page)
    card.locator(".card-play").click()
    card.locator(".card-play").wait_for(state="hidden", timeout=5000)
    context.close()


# --- what a publisher put out (2026-10-06) -------------------------------------------

#: Two articles and an episode as `search_sources` answers with them: texts not yet on
#: targum, so each door is our add page with the address in the box.
FOUND = {
    "count": 3,
    "items": [
        {
            "title": "הכנסת אישרה את התקציב לשנה הבאה",
            "link": "https://www.ynet.co.il/news/article/abc123",
            "publisher": "Ynet",
            "kind": "news",
            "seconds": 0,
            "known_share": 0.71,
        },
        {
            "title": "מזג האוויר: גשם ראשון בצפון",
            "link": "https://www.kan.org.il/item/1",
            "publisher": "Kan",
            "kind": "news",
            "seconds": 0,
            "known_share": None,
        },
        {
            "title": "הפודקאסט היומי",
            "link": "https://www.kan.org.il/podcast/2",
            "publisher": "Kan",
            "kind": "podcast",
            "seconds": 1260,
            "known_share": 0.5,
        },
    ],
}
ADD = "https://targum.page/add?source="


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_found_articles_open_on_our_add_page(browser, theme: str) -> None:  # noqa: F811
    """A feed item is a text not yet on targum: its publisher, its length where the feed
    knows it, how much the reader would know where that was measured, and one door to
    our add page. Never the publisher's page, never Listen, and nothing fetched."""
    from urllib.parse import quote

    context = opened(browser, viewport={"width": 520, "height": 520}, scrolling=False)
    page = context.new_page()
    fetched: list[str] = []
    page.on("request", lambda request: fetched.append(request.url))
    doors = [ADD + quote(str(item["link"]), safe="") for item in FOUND["items"]]
    # A recording beside a found item is ignored, were one ever sent.
    meta = [{"door": doors[0], "audio": {"src": HEARD, "ends": _later()}}] + [
        {"door": door} for door in doors[1:]
    ]
    page.set_content(text_hosted(theme, FOUND, meta, height=460))
    card = _cards(page)
    assert card.locator(".card-text").count() == 3
    first, second, third = (card.locator(".card-text").nth(n) for n in range(3))

    title = first.locator(".card-title")
    assert title.get_attribute("dir") == "rtl" and title.get_attribute("lang") == "he"
    assert first.locator(".card-from").text_content() == "Ynet"
    assert first.locator(".card-minutes").is_hidden(), "a feed's summary gives no length"
    assert first.locator(".card-known").text_content() == "You know about 7 words in 10 here."
    assert second.locator(".card-known").is_hidden(), "nothing measured, nothing said"
    assert third.locator(".card-minutes").text_content() == "21 min"
    assert third.locator(".card-door").text_content() == "Listen on targum"
    assert card.locator(".card-play:visible").count() == 0, "a found item has no Listen"

    door = first.locator(".card-door")
    assert door.text_content() == "Read on targum"
    assert door.get_attribute("href") == doors[0]
    door.click()
    page.wait_for_function("window.opened !== ''")
    assert page.evaluate("window.opened") == doors[0]
    assert page.evaluate("window.calls") == [], "the card asks for no tool"
    assert fetched == [], f"the card fetched {fetched}"
    _shot(page, f"feed-card-{theme}")
    context.close()


def test_a_found_item_with_no_door_beside_it_has_none(browser) -> None:  # noqa: F811
    """The card never falls back to the item's own link, which is the publisher's."""
    context = opened(browser, viewport={"width": 520, "height": 300}, scrolling=False)
    page = context.new_page()
    one = {"count": 1, "items": [FOUND["items"][0]]}
    page.set_content(text_hosted("light", one, [{}], height=200))
    card = _cards(page)
    assert card.locator(".card-door").is_hidden()
    assert card.locator(".card-door").get_attribute("href") is None
    context.close()
