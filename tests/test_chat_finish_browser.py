"""The conversation page at the finish bar (targum-internal#733), served with its real policy.

Design's §14 pass found the pictures sent with the `+` drawn as broken images on every
served page: `test_chat_js` checked them in a harness with no policy, and the policy is a
browser's rule. So this page is served the way `serve.Handler` serves it — the same body
with the same `Content-Security-Policy` — and read in headless Chromium.

Every answer is a route stub, the way `test_chat_pill_browser.py` stubs them: no model is
called, no build starts, nothing is spent.

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import json
import struct
import zlib
from typing import Any

import pytest

from targum.render.builder import chat_page
from targum.serve import Handler

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

TOKEN = "test-key"
SITE = "http://finish.test"


def png(width: int = 24, height: int = 16, clear: bool = False) -> bytes:
    """A real picture, small: a grey PNG the browser can decode, or a wholly transparent
    one with `clear`."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    pixel, kind = (b"\x00\x00\x00\x00", 6) if clear else (b"\x80\x80\x80", 2)
    rows = b"".join(b"\x00" + pixel * width for _ in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, kind, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


#: A quote ready to press, of a text that arrived as two pages of 42 sentences.
QUOTE = {
    "id": "j1",
    "title": "מכתב",
    "language": "he",
    "stage": "ready",
    "pages": 2,
    "segments": 42,
    "estimate": 0.01,
    "doubtful": 3,
    "voice_later": True,
}

#: A conversation whose answer quoted QUOTE.
THREAD = {
    "chat": {"id": "abc", "language": "he"},
    "turns": [
        {"n": 1, "role": "user", "said": "מה זה?", "stage": "done"},
        {"n": 2, "role": "assistant", "said": "Here it is.", "stage": "done", "quotes": [QUOTE]},
    ],
    "seconds": 30,
}

LIST = {"chats": [{"id": "abc", "title": "hi", "seen": 1}], "usable": True}


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


class Served:
    """The chat page under its real policy, every other path a stub, and what was asked."""

    def __init__(self, routes: dict[str, Any], language: str = "en", embed: bool = False) -> None:
        self.routes = routes
        self.body = chat_page(TOKEN, embed=embed, language=language).encode("utf-8")
        self.policy = Handler._policy(self.body)
        self.posted: list[str] = []

    def __call__(self, route, request) -> None:
        path = request.url[len(SITE) :].split("?")[0]
        if request.method == "POST":
            self.posted.append(path)
        if path == "/chat":
            route.fulfill(
                status=200,
                content_type="text/html",
                headers={"Content-Security-Policy": self.policy},
                body=self.body,
            )
            return
        answer = self.routes.get(path)
        if callable(answer):
            answer(route)
            return
        if answer is not None:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(answer))
            return
        if path == "/words/common":
            body: Any = {"words": [], "offset": 0, "next": None}
        elif path in ("/account/me", "/account/follows"):
            body = {"signedIn": False}
        else:
            body = {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def opened(
    browser, routes: dict[str, Any], *, language: str = "en", width: int = 1440, hash_: str = ""
):
    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    refused: list[str] = []
    page.on(
        "console",
        lambda message: (
            refused.append(message.text) if "Content Security Policy" in message.text else None
        ),
    )
    served = Served(routes, language)
    page.route(f"{SITE}/**", served)
    page.goto(f"{SITE}/chat?k={TOKEN}{hash_}")
    return context, page, served, refused


def picture_routes(prepare: Any) -> dict[str, Any]:
    return {
        "/chat/list": {"chats": [], "usable": True},
        "/upload/begin": {"upload": "u1", "chunk": 1_000_000},
        "/upload/u1/0": {},
        "/upload/u1/end": {"upload": "u1", "picture": True},
        "/prepare": prepare,
        "/build": dict(QUOTE, stage="working"),
        "/job/j1": dict(QUOTE, stage="working"),
    }


def choose_pictures(page, count: int = 2) -> None:
    page.set_input_files(
        "#chat-file",
        files=[
            {"name": f"page{n}.png", "mimeType": "image/png", "buffer": png(24 + n, 16)}
            for n in range(count)
        ],
    )


def test_pictures_sent_with_the_plus_are_seen_under_the_served_policy(browser) -> None:
    """P1 1: `blob:` addresses, refused by `img-src 'self' data:`, drew two broken images."""
    context, page, served, refused = opened(browser, picture_routes(QUOTE))
    page.wait_for_selector("#chat-bring")
    choose_pictures(page)
    page.click("#chat-send")
    page.wait_for_function(
        """() => {
          const shown = [...document.querySelectorAll('.chat-sent img')];
          return shown.length === 2 && shown.every((img) => img.complete && img.naturalWidth > 0);
        }""",
        timeout=5000,
    )
    sources = page.eval_on_selector_all(".chat-sent img", "all => all.map((i) => i.src)")
    context.close()
    assert all(src.startswith("data:image/") for src in sources), sources
    assert not refused, refused
    assert "blob:" not in served.policy, "the policy readers are held to did not widen"


def test_a_refused_picture_is_a_refusal_keeps_its_files_and_says_nothing_after(browser) -> None:
    """P2 6: a plain sentence with no mark, the files dropped, and the line still sent as
    a turn about a picture that was never read."""
    context, page, served, _ = opened(
        browser, picture_routes({"error": "We couldn't read these pictures."})
    )
    page.wait_for_selector("#chat-bring")
    choose_pictures(page, 1)
    page.fill("#say", "What does this say?")
    page.click("#chat-send")
    page.wait_for_selector(".chat-turn.bad .fault-line .fault-icon", timeout=5000)
    held = page.eval_on_selector_all("#chat-held .chat-chip", "all => all.length")
    field = page.input_value("#say")
    said = page.inner_text(".chat-turn.bad .fault-line")
    context.close()
    assert "We couldn't read these pictures." in said
    assert held == 1, "the file is back in the box"
    assert field == "What does this say?", "and the line with it"
    assert "/chat/say" not in served.posted, served.posted


def test_a_russian_quote_card_is_russian_throughout(browser) -> None:
    """P1 2: "42 sentences · Будет готово через мгновение." — the card's keys were in
    ru.json but not in the page's bundle."""
    context, page, _, _ = opened(
        browser,
        {"/chat/list": LIST, "/chat/abc": THREAD},
        language="ru",
        hash_="#abc",
    )
    page.wait_for_selector(".quote-card .quote-meta")
    card = page.inner_text(".quote-card")
    context.close()
    for english in ("sentence", "page", "couldn't read", "add audio later"):
        assert english not in card, (english, card)
    assert "предложени" in card and "страниц" in card, card


def test_a_streaming_hebrew_tail_has_its_own_direction_and_language(browser) -> None:
    """P2 3 (§14.3): the tail sat at the left edge and jumped right when its line ended."""
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.add_init_script(
        """window.__sources = [];
        window.EventSource = class {
          constructor(url) {
            this.url = url; this.readyState = 1; this.on = {}; window.__sources.push(this);
          }
          addEventListener(type, fn) { (this.on[type] = this.on[type] || []).push(fn); }
          close() { this.readyState = 2; }
          fire(type, data) { (this.on[type] || []).forEach((fn) => fn({ data })); }
        };"""
    )
    served = Served(
        {"/chat/list": {"chats": [], "usable": True}, "/chat/say": {"chat": "abc", "turn": 1}}
    )
    page.route(f"{SITE}/**", served)
    page.goto(f"{SITE}/chat?k={TOKEN}")
    page.wait_for_selector("#say")
    page.fill("#say", "שלום")
    page.click("#chat-send")
    page.wait_for_function("() => window.__sources.length > 0")
    page.evaluate("() => window.__sources[0].fire('text', 'שלום, מה')")
    tail = page.eval_on_selector(
        ".chat-partial", "p => ({dir: p.getAttribute('dir'), lang: p.getAttribute('lang')})"
    )
    context.close()
    assert tail == {"dir": "auto", "lang": "he"}, tail


def test_a_server_fault_on_the_list_is_said_once_and_not_as_the_connection(browser) -> None:
    """P2 4: a 500 was "We can't reach targum", by the banner and again under the box."""

    def fault(route) -> None:
        route.fulfill(status=500, content_type="text/html", body="<h1>Internal Server Error</h1>")

    context, page, _, _ = opened(browser, {"/chat/list": fault})
    page.wait_for_selector("#chat-said:not([hidden])")
    said = page.inner_text("#chat-said")
    banner = page.evaluate(
        "() => { const b = document.getElementById('fault-banner'); return !!b && !b.hidden; }"
    )
    context.close()
    assert "We can't answer right now" in said and "reach" not in said, said
    assert not banner, "a server that answered is not a lost connection"


def test_a_line_that_never_left_says_so_with_a_try_again_of_its_own(browser) -> None:
    """P2 5: the line stood in the thread in the teal wash, looking sent."""
    reach = {"up": False}

    def say(route) -> None:
        if not reach["up"]:
            route.abort()
            return
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps({"error": "Stop here."})
        )

    context, page, served, _ = opened(
        browser, {"/chat/list": {"chats": [], "usable": True}, "/chat/say": say}
    )
    page.wait_for_selector("#say")
    page.fill("#say", "שלום")
    page.click("#chat-send")
    page.wait_for_selector(".chat-turn.me.unsent .fault-line")
    note = page.inner_text(".chat-turn.me.unsent .fault-line")
    reach["up"] = True
    page.click(".chat-turn.me.unsent .fault-act")
    page.wait_for_selector(".chat-turn.them.bad")
    unsent_after = page.eval_on_selector_all(".chat-turn.unsent", "all => all.length")
    mine = page.eval_on_selector_all(".chat-turn.me", "all => all.length")
    context.close()
    assert "Not sent" in note and "Try again" in note, note
    assert unsent_after == 0 and mine == 1, (unsent_after, mine)
    assert served.posted.count("/chat/say") == 2


def test_unusable_looks_unusable_at_the_edges_too(browser) -> None:
    """P2 7: the `+` and Speak were disabled but drawn at full ink, over an empty thread."""
    context, page, _, _ = opened(browser, {"/chat/list": {"chats": [], "usable": False}})
    page.wait_for_selector(".chat-main.cannot")
    got = page.evaluate(
        """() => ({
          bring: getComputedStyle(document.getElementById('chat-bring')).opacity,
          mic: getComputedStyle(document.getElementById('chat-mic')).opacity,
          thread: getComputedStyle(document.getElementById('chat-thread')).visibility,
        })"""
    )
    context.close()
    assert float(got["bring"]) < 1 and float(got["mic"]) < 1, got
    assert got["thread"] == "hidden", got


def test_tab_meets_the_plus_before_the_field(browser) -> None:
    """P2 8: the `+` is drawn first, and Tab went to the field first."""
    context, page, _, _ = opened(browser, {"/chat/list": {"chats": [], "usable": True}})
    page.wait_for_selector("#chat-bring")
    page.focus("#chat-bring")
    page.keyboard.press("Tab")
    after = page.evaluate("() => document.activeElement.id")
    context.close()
    assert after == "say", after


def test_the_open_conversation_is_current_and_drawn_as_a_row(browser) -> None:
    """P2 9: marked only by weight, which the Hebrew face barely shows."""
    routes = {
        "/chat/list": {
            "chats": [{"id": "abc", "title": "שלום", "seen": 1}, {"id": "xyz", "title": "b"}],
            "usable": True,
        },
        "/chat/abc": THREAD,
    }
    context, page, _, _ = opened(browser, routes, hash_="#abc")
    page.wait_for_selector('.chat-list button[data-chat="abc"].on')
    got = page.evaluate(
        """() => {
          const on = document.querySelector('.chat-list button[data-chat="abc"]');
          const off = document.querySelector('.chat-list button[data-chat="xyz"]');
          return {
            current: on.getAttribute('aria-current'),
            other: off.getAttribute('aria-current'),
            fill: getComputedStyle(on).backgroundColor,
          };
        }"""
    )
    context.close()
    assert got["current"] == "true" and got["other"] is None, got
    assert got["fill"] not in ("rgba(0, 0, 0, 0)", "transparent"), got


def test_offline_the_chips_dim_with_the_box(browser) -> None:
    """P2 12: offline, the chips stayed live teal while Send could not go."""
    routes = {
        "/chat/list": {
            "chats": [],
            "usable": True,
            "chips": [{"id": "know", "line": "Show me what I know"}],
        }
    }
    context, page, _, _ = opened(browser, routes)
    page.wait_for_selector(".chat-ask")
    live = page.eval_on_selector(".chat-ask", "b => b.disabled")
    context.set_offline(True)
    page.wait_for_function("() => document.querySelector('.chat-ask').disabled")
    dim = page.eval_on_selector(".chat-ask", "b => getComputedStyle(b).opacity")
    context.set_offline(False)
    page.wait_for_function("() => !document.querySelector('.chat-ask').disabled")
    pill = page.eval_on_selector("#chat-open-list", "b => getComputedStyle(b).display")
    context.close()
    assert live is False and float(dim) < 1
    assert pill == "none", "Chats opens nothing while there are none"


def test_in_the_drawer_chats_is_not_drawn_while_there_are_none(browser) -> None:
    """qa-claude on #1256: framed, `body.embed .chat-open-list` beat `[hidden]`, and a
    test that read the property stayed green while the pill was drawn."""
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    served = Served({"/chat/list": {"chats": [], "usable": True}}, embed=True)
    page.route(f"{SITE}/**", served)
    page.goto(f"{SITE}/chat?k={TOKEN}")
    page.wait_for_function("() => document.getElementById('chat-open-list').hidden")
    shown = page.eval_on_selector("#chat-open-list", "b => getComputedStyle(b).display")
    context.close()
    assert shown == "none", shown


#: Counts the full decodes alive at once, and every one that was never closed.
DECODES = """(() => {
  const made = window.createImageBitmap.bind(window);
  window.__decodes = { alive: 0, most: 0, made: 0 };
  window.createImageBitmap = (file) =>
    made(file).then((bitmap) => {
      const seen = window.__decodes;
      seen.made += 1;
      seen.alive += 1;
      seen.most = Math.max(seen.most, seen.alive);
      const close = bitmap.close.bind(bitmap);
      bitmap.close = () => { seen.alive -= 1; close(); };
      return bitmap;
    });
})();"""


def test_a_batch_of_pictures_is_drawn_one_decode_at_a_time(browser) -> None:
    """qa-claude on #1256 (P2): every picture was decoded at once, thirty phone photos
    over a gigabyte of bitmaps; a picture the browser cannot decode was read whole for
    nothing; and a transparent screenshot came out black."""
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.add_init_script(DECODES)
    served = Served(picture_routes(QUOTE))
    page.route(f"{SITE}/**", served)
    page.goto(f"{SITE}/chat?k={TOKEN}")
    page.wait_for_selector("#chat-bring")
    files = [
        {"name": f"page{n}.png", "mimeType": "image/png", "buffer": png(30 + n, 20)}
        for n in range(6)
    ]
    files.append({"name": "clear.png", "mimeType": "image/png", "buffer": png(20, 20, clear=True)})
    files.append({"name": "phone.heic", "mimeType": "image/heic", "buffer": b"not a picture" * 64})
    page.set_input_files("#chat-file", files=files)
    page.click("#chat-send")
    page.wait_for_function(
        """() => {
          const shown = [...document.querySelectorAll('.chat-sent img')].slice(0, 7);
          return shown.length === 7 && shown.every((img) => img.complete && img.naturalWidth > 0);
        }""",
        timeout=8000,
    )
    page.wait_for_function("() => window.__decodes.alive === 0")
    got = page.evaluate(
        """() => {
          const all = [...document.querySelectorAll('.chat-sent img')];
          const clear = all[6];
          const canvas = document.createElement('canvas');
          canvas.width = clear.naturalWidth;
          canvas.height = clear.naturalHeight;
          const pen = canvas.getContext('2d');
          pen.drawImage(clear, 0, 0);
          return {
            decodes: window.__decodes,
            corner: [...pen.getImageData(0, 0, 1, 1).data],
            heic: all[7].getAttribute('src'),
            alt: all[7].alt,
          };
        }"""
    )
    context.close()
    assert got["decodes"]["most"] == 1 and got["decodes"]["made"] == 7, got["decodes"]
    assert min(got["corner"][:3]) > 240, f"a transparent picture is drawn on white: {got}"
    assert got["heic"] is None and got["alt"] == "phone.heic", "nothing read whole for nothing"


def test_a_refused_quote_card_has_no_panel_inside_it(browser) -> None:
    """P2 11: a raised panel in a raised card, padded twice at 390."""
    blocked = dict(
        QUOTE,
        stage="blocked",
        blocked="That's all for today.",
        fact="Your texts still open",
        act="library",
    )
    thread = dict(THREAD, turns=[THREAD["turns"][0], dict(THREAD["turns"][1], quotes=[blocked])])
    context, page, _, _ = opened(
        browser, {"/chat/list": LIST, "/chat/abc": thread}, width=390, hash_="#abc"
    )
    page.wait_for_selector(".quote-card.refused")
    got = page.evaluate(
        """() => {
          const card = document.querySelector('.quote-card.refused');
          const way = card.querySelector('.quote-way');
          return {
            panels: card.querySelectorAll('.fault-panel').length,
            note: card.querySelector('.quote-note').textContent,
            marked: card.querySelector('.quote-note').classList.contains('fault-marked'),
            act: way && way.querySelector('a.fault-act')?.textContent,
            fact: way && way.querySelector('.quote-fact')?.textContent,
            last: card.lastElementChild === way,
          };
        }"""
    )
    context.close()
    assert got["panels"] == 0, got
    assert got["marked"] and got["note"] == "That's all for today.", got
    assert got["act"] == "Open the library" and got["fact"] == "Your texts still open", got
    assert got["last"], "the way on stands under the sentence it follows"
