"""What the chat draws of a search, a set and a door, read live (targum-internal#735).

David asked the chat for today's news on 2026-11-15 and got nothing to read: the search
ran and found six articles, the panel drew none of them, the addresses the model wrote
were dropped, the set it made was a lone link, and the door's pill broke "Open" inside
the word. The page here is served with its real policy, as `test_chat_finish_browser`
serves it, and every answer is a route stub: no model is called and nothing is spent.

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from test_chat_finish_browser import QUOTE, SITE, TOKEN, Served, browser  # noqa: F401

pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

#: An EventSource the test feeds by hand, as `test_chat_finish_browser` does.
STREAM = """window.__sources = [];
window.EventSource = class {
  constructor(url) {
    this.url = url; this.readyState = 1; this.on = {}; window.__sources.push(this);
  }
  addEventListener(type, fn) { (this.on[type] = this.on[type] || []).push(fn); }
  close() { this.readyState = 2; }
  fire(type, data) { (this.on[type] || []).forEach((fn) => fn({ data })); }
};"""

FOUND = [
    {
        "title": "הממשלה אישרה את התקציב",
        "link": "https://www.ynet.co.il/news/article/1",
        "publisher": "ynet",
        "kind": "news",
        "language": "he",
        "known_share": 0.92,
        "known_estimated": False,
    },
    {
        "title": "גשם בצפון",
        "link": "https://www.ynet.co.il/news/article/2",
        "publisher": "ynet",
        "kind": "news",
        "language": "he",
        "known_share": 0.84,
        "known_estimated": True,
    },
    {
        "title": "דעה",
        "link": "https://www.israelhayom.co.il/opinions/3",
        "publisher": "Israel Hayom",
        "kind": "news",
        "language": "he",
        "known_share": 0.7,
        "known_estimated": False,
    },
]

SET = {
    "id": 16,
    "name": "חדשות היום",
    "items": [
        {"title": "הממשלה אישרה את התקציב", "credits": 0, "language": "he"},
        {"title": "פרק בפודקאסט", "credits": 4, "language": "he"},
    ],
    "credits": 4,
    "open": "/set/16",
}


def streaming(browser, routes: dict[str, Any], width: int = 1440):  # noqa: F811
    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    page.add_init_script(STREAM)
    base = {"/chat/list": {"chats": [], "usable": True}, "/chat/say": {"chat": "abc", "turn": 1}}
    served = Served({**base, **routes})
    page.route(f"{SITE}/**", served)
    page.goto(f"{SITE}/chat?k={TOKEN}")
    page.wait_for_selector("#say")
    page.fill("#say", "מה החדשות היום?")
    page.click("#chat-send")
    page.wait_for_function("() => window.__sources.length > 0")
    return context, page, served


def fire(page, kind: str, data: Any) -> None:
    page.evaluate(
        "([kind, data]) => window.__sources[0].fire(kind, data)",
        [kind, data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)],
    )


def test_what_a_search_found_is_drawn_as_cards_and_open_only_prices_it(browser) -> None:  # noqa: F811
    context, page, served = streaming(browser, {"/prepare": QUOTE})
    fire(page, "found", {"items": FOUND})
    fire(page, "done", {"text": "מָצָאתִי שָׁלוֹשׁ כְּתָבוֹת.\n= I found three articles."})
    page.wait_for_selector(".found-card")
    cards = page.eval_on_selector_all(
        ".found-card",
        """all => all.map((card) => ({
          title: card.querySelector('.quote-title').textContent,
          lang: card.querySelector('.quote-title bdi').getAttribute('lang'),
          meta: card.querySelector('.quote-meta').textContent,
          press: card.querySelector('.quote-go').textContent,
        }))""",
    )
    assert [card["title"] for card in cards] == [row["title"] for row in FOUND]
    assert cards[0] == {
        "title": FOUND[0]["title"],
        "lang": "he",
        "meta": "ynet · Read it now · You know 92% of the words",
        "press": "Open",
    }
    assert "A stretch" in cards[1]["meta"] and "(our estimate)" in cards[1]["meta"]
    assert "Hard for now" in cards[2]["meta"]
    page.click(".found-card .quote-go")
    page.wait_for_selector('.quote-card[data-job="j1"] .quote-go')
    left = page.eval_on_selector_all(".found-card", "all => all.length")
    context.close()
    assert left == 2, "the card Open priced stands in its place"
    assert "/prepare" in served.posted and "/build" not in served.posted, served.posted


def test_an_address_the_model_writes_is_a_link_and_never_dropped(browser) -> None:  # noqa: F811
    context, page, _ = streaming(browser, {})
    fire(
        page,
        "done",
        {
            "text": "הִנֵּה כְּתָבָה.\n= Here is an article.\n"
            "https://www.ynet.co.il/news/article/1\n"
            "רוֹצֶה עוֹד?\n= Want more?"
        },
    )
    page.wait_for_selector("a.chat-out")
    link = page.eval_on_selector(
        "a.chat-out",
        "a => ({href: a.getAttribute('href'), text: a.textContent, target: a.target, rel: a.rel})",
    )
    pairs = page.eval_on_selector_all(".chat-pair", "all => all.length")
    context.close()
    assert link == {
        "href": "https://www.ynet.co.il/news/article/1",
        "text": "ynet.co.il/news/article/1",
        "target": "_blank",
        "rel": "noopener noreferrer",
    }
    assert pairs == 2


def test_a_set_is_a_card_with_its_texts_and_credits(browser) -> None:  # noqa: F811
    context, page, _ = streaming(browser, {})
    fire(page, "set", SET)
    fire(page, "done", {"text": "אַסְפְתִּי אוֹתָן.\n= I gathered them.\n/set/16"})
    page.wait_for_selector(".set-card")
    got = page.evaluate(
        """() => {
          const card = document.querySelector('.set-card');
          return {
            name: card.querySelector('.quote-title').textContent,
            items: [...card.querySelectorAll('.set-items li')].map((li) => li.textContent),
            uses: card.querySelector('.quote-uses').textContent,
            see: card.querySelector('a.quote-go').getAttribute('href'),
            doors: [...document.querySelectorAll('.chat-door')]
              .filter((a) => !a.hidden && a.offsetParent).length,
          };
        }"""
    )
    context.close()
    assert got["name"] == "חדשות היום"
    assert got["items"] == ["הממשלה אישרה את התקציב", "פרק בפודקאסטUses 4 credits"]
    assert got["uses"] == "Uses 4 credits"
    assert got["see"].startswith("/set/16")
    assert got["doors"] == 0, "the set's own path is not drawn a second time as a door"


LONG = "הַמַּסָּע הַגָּדוֹל אֶל אֶרֶץ הַחֲלוֹמוֹת הָרְחוֹקָה"

THREAD = {
    "chat": {"id": "abc", "language": "he"},
    "turns": [
        {"n": 1, "role": "user", "said": "מה לקרוא?", "stage": "done"},
        {
            "n": 2,
            "role": "assistant",
            "said": "נַסֶּה אֶת זֶה.\n= Try this one.\n/reader/long-he/reader/index.html",
            "stage": "done",
            "doors": {"/reader/long-he/reader/index.html": {"title": LONG, "language": "he"}},
        },
    ],
    "seconds": 30,
}

#: Every word of the door, and of "Open", is on one line: a range over it has one box.
WHOLE_WORDS = """() => {
  const door = document.querySelector('.chat-door');
  const broken = [];
  const walk = (node) => {
    if (node.nodeType === 3) {
      const text = node.textContent;
      const words = /\\S+/g;
      let found;
      while ((found = words.exec(text))) {
        const range = document.createRange();
        range.setStart(node, found.index);
        range.setEnd(node, found.index + found[0].length);
        const lines = new Set([...range.getClientRects()].map((r) => Math.round(r.top)));
        if (lines.size > 1) broken.push(found[0]);
      }
    }
    node.childNodes.forEach(walk);
  };
  walk(door);
  const room = door.parentNode.getBoundingClientRect().width;
  return { broken, width: door.getBoundingClientRect().width, room };
}"""


@pytest.mark.parametrize("embed", [False, True])
def test_a_long_title_on_a_door_wraps_between_words_at_360(browser, embed) -> None:  # noqa: F811
    """ "Ope/n": the drawer's pill was a flex box over a line that may break anywhere."""
    context = browser.new_context(viewport={"width": 360, "height": 800})
    page = context.new_page()
    served = Served(
        {
            "/chat/list": {"chats": [{"id": "abc", "title": "hi", "seen": 1}], "usable": True},
            "/chat/abc": THREAD,
        },
        embed=embed,
    )
    page.route(f"{SITE}/**", served)
    page.goto(f"{SITE}/chat?k={TOKEN}#abc")
    page.wait_for_selector(".chat-door")
    got = page.evaluate(WHOLE_WORDS)
    context.close()
    assert got["broken"] == [], got
    assert got["width"] <= got["room"] + 1, "the pill stays inside its line"


def test_listen_stands_beside_the_answer_not_on_a_line_of_its_own(browser) -> None:  # noqa: F811
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    served = Served(
        {
            "/chat/list": {"chats": [{"id": "abc", "title": "hi", "seen": 1}], "usable": True},
            "/chat/abc": THREAD,
        },
    )
    page.route(f"{SITE}/**", served)
    page.goto(f"{SITE}/chat?k={TOKEN}#abc")
    page.wait_for_selector(".chat-turn.them .chat-play")
    got = page.evaluate(
        """() => {
          const turn = document.querySelector('.chat-turn.them');
          const line = turn.querySelector('.chat-line').getBoundingClientRect();
          const play = turn.querySelector('.chat-play').getBoundingClientRect();
          return {
            lineBottom: line.bottom, lineRight: line.right, playTop: play.top, playLeft: play.left,
          };
        }"""
    )
    context.close()
    assert got["playTop"] < got["lineBottom"], got
    assert got["playLeft"] >= got["lineRight"] - 1, got
