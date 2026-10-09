"""Subscribing offered from a conversation and confirmed on targum's page, the offer card,
and Subscribe on a series' own page (design.md §12, "A third card, the offer" and "A
subscription is the account's", 2026-10-09)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from targum import mcp_http
from targum import subscriptions as subs
from targum.accounts import Store
from targum.chat import tools as tools_module
from targum.render.builder import ASSETS, build_offer_card
from targum.serve import Library

CHANNEL = {
    "kind": "channel",
    "key": "UCkan",
    "name": "כאן ארכיון",
    "hebrew": "",
    "what": "",
    "language": "he",
    "source": "https://www.youtube.com/channel/UCkan",
    "perWeek": 2.1,
    "seconds": 480.0,
    "creditsEach": 8,
    "builds": True,
    "outlets": 0,
    "before": [],
}


def a_ctx(tmp_path: Path, press_at: str = "https://targum.page") -> tools_module.Ctx:
    from targum import connector

    store = Store(tmp_path / "targum.db")
    signed = store.finish_sign_in(store.start_sign_in("one@example.com"))
    assert signed is not None
    library = Library(tmp_path / "out", store=store)
    return connector.context(library, store, signed[0], press_at=press_at)


# --- the tool -----------------------------------------------------------------------


def test_a_subscription_is_offered_as_a_link_and_nothing_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[tuple[str, str]] = []

    def describe(kind: str, given: str, **_: Any) -> dict[str, Any]:
        asked.append((kind, given))
        return dict(CHANNEL)

    monkeypatch.setattr(subs, "describe", describe)
    ctx = a_ctx(tmp_path)
    got = tools_module.quote_subscription(
        ctx, {"kind": "channel", "source": "https://youtube.com/@kan"}
    )
    assert asked == [("channel", "https://youtube.com/@kan")]
    assert got["subscription"] == {
        "kind": "channel",
        "name": "כאן ארכיון",
        "language": "he",
        "per_week": 2.1,
        "credits_each": 8,
        "builds": True,
        "free": False,
    }
    link = urlparse(got["open"])
    assert link.netloc == "targum.page" and link.path == "/subscribe"
    assert parse_qs(link.query) == {
        "kind": ["channel"],
        "source": ["https://www.youtube.com/channel/UCkan"],
        "via": ["connector"],
    }
    assert "cannot" in got["note"] and "never say money" in got["note"]
    assert ctx.store is not None and ctx.store.subscriptions(ctx.person_id) == [], (
        "a quote writes nothing"
    )

    # Already theirs: the link is where they change it.
    assert ctx.person is not None
    held = ctx.store.add_subscription(ctx.person.id, "channel", "UCkan", cap=60)
    again = tools_module.quote_subscription(ctx, {"kind": "channel", "source": "x"})
    assert again["subscribed"] and again["open"].endswith(f"/subscriptions/{held['id']}")


def test_a_refusal_comes_back_in_one_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum.errors import TargumError

    ctx = a_ctx(tmp_path)
    assert "error" in tools_module.quote_subscription(ctx, {"kind": "nope", "key": "x"})
    assert "error" in tools_module.quote_subscription(ctx, {"kind": "channel"})

    def refuse(kind: str, given: str, **_: Any) -> dict[str, Any]:
        raise TargumError("We couldn't find that channel on YouTube.", key="subscribe.no-channel")

    monkeypatch.setattr(subs, "describe", refuse)
    got = tools_module.quote_subscription(ctx, {"kind": "channel", "source": "x"})
    assert got == {"error": "We couldn't find that channel on YouTube."}
    monkeypatch.setattr(subs, "describe", lambda kind, given, **_: dict(CHANNEL))
    monkeypatch.setenv("TARGUM_PLANS", "1")
    got = tools_module.quote_subscription(ctx, {"kind": "channel", "source": "x"})
    assert "come with a plan" in got["error"]


def test_news_is_offered_free_in_targums_own_chat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    topic = dict(
        CHANNEL, kind="topic", key="sport", name="", builds=False, creditsEach=0, outlets=3
    )
    monkeypatch.setattr(subs, "describe", lambda kind, given, **_: dict(topic))
    got = tools_module.quote_subscription(
        a_ctx(tmp_path, press_at=""), {"kind": "topic", "key": "sport"}
    )
    assert got["open"].startswith("/subscribe?") and "via=chat" in got["open"]
    assert "language=he" in got["open"] and got["subscription"]["free"]
    assert "It is free." in got["note"]


def test_the_tool_is_the_chat_scopes_and_draws_the_offer_card() -> None:
    tool = tools_module.BY_NAME["quote_subscription"]
    assert tool.scope == "chat" and tool.needs_account and not tool.writes and not tool.spends
    assert tool.card == tools_module.OFFER_CARD
    assert tools_module.BY_NAME["quote_set"].card == tools_module.OFFER_CARD
    assert set(mcp_http.CARDS) == {
        tools_module.BUILD_CARD,
        tools_module.TEXT_CARD,
        tools_module.OFFER_CARD,
    }, "design.md §12 allows three"
    shapes = mcp_http.card_shapes([tool])
    assert [shape["uri"] for shape in shapes] == [tools_module.OFFER_CARD]
    assert shapes[0]["_meta"]["ui"]["csp"] == {"connectDomains": [], "resourceDomains": []}
    read = mcp_http.card_read(tools_module.OFFER_CARD, [tool], "ru")
    assert read["contents"][0]["text"] == build_offer_card("ru")
    assert mcp_http.tool_shapes([tool])[0]["_meta"]["ui"]["resourceUri"] == tools_module.OFFER_CARD


# --- the card -----------------------------------------------------------------------


def _offer_script() -> str:
    return re.sub(
        r"^\s*//.*$", "", (ASSETS / "card-offer.js").read_text(encoding="utf-8"), flags=re.M
    )


def test_the_offer_card_fetches_nothing_and_presses_nothing() -> None:
    page = build_offer_card()
    assert not re.search(r"https?://", page)
    without_script = re.sub(r"<script>.*?</script>", " ", page, flags=re.S)
    assert not re.search(r"\b(?:src|srcset|action|poster|href)\s*=", without_script)
    for stray in ("url(", "@import", "<link", "<img", "<iframe", "<audio", "<video", "<form"):
        assert stray not in page, stray
    for stray in ("fetch(", "XMLHttpRequest", "WebSocket", "EventSource", "sendBeacon"):
        assert stray not in page, stray
    script = _offer_script()
    assert "tools/call" not in script and "callTool" not in script and ".request(" not in script
    for tool in tools_module.REGISTRY:
        assert tool.name not in script, f"the card names {tool.name}"
    for door in ("ui/message", "ui/update-model-context", "sendFollowUpMessage"):
        assert door not in script, door
    assert "createElement" not in script and "innerHTML" not in script
    assert page.count("ui/initialize") == 1 and "var TargumCard" in page


def test_the_offer_card_keeps_the_voice_and_both_palettes() -> None:
    for language in ("en", "ru"):
        page = build_offer_card(language)
        visible = re.sub(r"<(script|style)>.*?</\1>", " ", page, flags=re.S)
        visible = re.sub(r"<[^>]+>", " ", visible)
        assert "!" not in visible and "Targum" not in visible
        assert ':root[data-theme="dark"]' in page
        assert '<meta name="color-scheme" content="light dark">' in page
    russian = build_offer_card("ru")
    assert "Подтвердить в targum" in russian and '"few":' in russian, "every form Russian has"


# --- in a browser -------------------------------------------------------------------

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

HOST = """
<!doctype html>
<html><head><meta charset="utf-8"></head>
<body>
<iframe id="f" sandbox="allow-scripts allow-same-origin" style="width:440px;height:300px"></iframe>
<script>
  const RESULT = %(result)s;
  window.opened = "";
  window.calls = [];
  const frame = document.getElementById("f");
  const post = (message) => frame.contentWindow.postMessage({ jsonrpc: "2.0", ...message }, "*");
  window.addEventListener("message", (event) => {
    if (event.source !== frame.contentWindow) return;
    const m = event.data;
    if (m.method === "ui/initialize") {
      post({ id: m.id, result: { protocolVersion: "2026-01-26", hostContext: { theme: "dark" } } });
    } else if (m.method === "ui/notifications/initialized") {
      post({ method: "ui/notifications/tool-result",
             params: { content: [{ type: "text", text: JSON.stringify(RESULT) }],
                       structuredContent: RESULT } });
    } else if (m.method === "ui/open-link") {
      window.opened = m.params.url;
      post({ id: m.id, result: {} });
    } else if (m.method === "tools/call") {
      window.calls.push(m.params);
    }
  });
  frame.srcdoc = %(card)s;
</script>
</body></html>
"""


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


def hosted(result: dict[str, Any], language: str = "en") -> str:
    return HOST % {
        "result": json.dumps(result, ensure_ascii=False),
        "card": json.dumps(build_offer_card(language)).replace("</", "<\\/"),
    }


def test_the_offer_card_draws_a_subscription_and_opens_targums_page(browser) -> None:
    page = browser.new_page()
    page.set_content(
        hosted(
            {
                "subscription": {
                    "kind": "channel",
                    "name": "כאן ארכיון",
                    "language": "he",
                    "per_week": 2.1,
                    "credits_each": 8,
                    "builds": True,
                    "free": False,
                },
                "open": "https://targum.page/subscribe?kind=channel&source=x&via=connector",
            },
            "ru",
        )
    )
    card = page.frame_locator("#f")
    card.locator(".card-door:not([hidden])").wait_for()
    direction = card.locator(".card-title").get_attribute("dir")
    facts = card.locator(".card-facts").text_content()
    label = card.locator(".card-label").text_content()
    theme = card.locator("html").get_attribute("data-theme")
    card.locator(".card-door").click()
    page.wait_for_function("window.opened !== ''")
    opened = page.evaluate("window.opened")
    calls = page.evaluate("window.calls")
    page.close()
    assert direction == "rtl", "a Hebrew name is drawn right to left"
    assert label == "Канал на YouTube" and theme == "dark"
    assert (
        facts
        == "Около 2 в неделю · Около 8 кредитов на новое · Месячный лимит вы выберете в targum"
    )
    assert opened.endswith("via=connector") and calls == [], "it opens a page and presses nothing"


def test_the_offer_card_draws_a_set_with_what_each_text_uses(browser) -> None:
    page = browser.new_page()
    page.set_content(
        hosted(
            {
                "set": {
                    "id": 3,
                    "name": "Reels",
                    "items": [
                        {"title": "במעלית", "credits": 1, "seconds": 50, "audio": True},
                        {"title": "A text", "credits": 0, "seconds": 0, "audio": False},
                    ],
                    "credits": 1,
                    "refused": [],
                },
                "open": "https://targum.page/set/3",
            }
        )
    )
    card = page.frame_locator("#f")
    card.locator(".card-door:not([hidden])").wait_for()
    got = {
        "name": card.locator(".card-title").text_content(),
        "items": card.locator(".card-item").all_text_contents(),
        "sum": card.locator(".card-sum").text_content(),
        "door": card.locator(".card-door").text_content(),
        "hebrew": card.locator(".card-item-title").first.get_attribute("lang"),
    }
    page.close()
    assert got["name"] == "Reels" and got["door"] == "Confirm on targum"
    assert got["items"] == ["במעלית1 min · 1 credit", "A text"], got
    assert got["sum"] == "Uses 1 credit in all" and got["hebrew"] == "he"


# --- Subscribe on a series' page ------------------------------------------------------


def test_a_series_page_carries_subscribe_for_somebody_signed_in() -> None:
    """One page for every series (design.md §12, "A series is one page of the desk, for
    everyone", 2026-10-09): the switch for somebody signed in, drawn in the state the
    account is in, and the sign-in prompt for a stranger."""
    text = (ASSETS.parent / "templates" / "series.html.j2").read_text(encoding="utf-8")
    assert "{%- if signed_in %}" in text and 'id="series-subscribe"' in text
    assert "subscribe.js" in text and "series-sign-in" in text


SITE = "http://targum.test"


def test_the_series_switch_and_the_library_hook(browser) -> None:
    page = browser.new_page()
    posted: list[Any] = []
    follows = {"signedIn": True, "follows": []}

    def answer(route, request) -> None:
        path = request.url[len(SITE) :].split("?")[0]
        if path == "/" and request.method == "GET":
            body = (
                "<!doctype html><html lang='en'><body>"
                "<div class='series-subscribe' id='series-subscribe' data-series='tehillim'"
                " data-subscribe='Subscribe' data-subscribed='Subscribed' hidden>"
                "<button type='button' aria-pressed='false'>Subscribe</button></div>"
                f"<script>{(ASSETS / 'subscribe.js').read_text(encoding='utf-8')}</script>"
                "</body></html>"
            )
            return route.fulfill(status=200, content_type="text/html", body=body)
        if request.method == "POST":
            asked = json.loads(request.post_data or "{}")
            posted.append(asked)
            follows["follows"] = [asked["series"]] if asked.get("on") else []
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(follows))

    page.route(f"{SITE}/**", answer)
    page.goto(f"{SITE}/")
    page.wait_for_selector("#series-subscribe:not([hidden])")
    page.click("#series-subscribe button")
    page.wait_for_selector("#series-subscribe button[aria-pressed='true']")
    said = page.text_content("#series-subscribe button")
    hook = page.evaluate(
        """() => {
          const a = TargumSubscribe.button('channel', 'https://youtube.com/@kan',
            { subscribe: 'Subscribe', subscribed: 'Subscribed' });
          return [a.tagName, a.getAttribute('href'), a.textContent];
        }"""
    )
    page.close()
    assert posted == [{"series": "tehillim", "on": True}] and said == "Subscribed"
    assert hook == [
        "A",
        "/subscribe?kind=channel&source=https%3A%2F%2Fyoutube.com%2F%40kan&via=library",
        "Subscribe",
    ]
