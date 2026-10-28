"""The chat pill and its drawer at the finish bar (design.md §14; targum-internal#472).

The real Library page with the real pill and drawer, and the real conversation page framed
in it, in headless Chromium. Every answer is a route stub, so no model is called and nothing
is spent: the chat is stubbed the way design's pass stubbed it.

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from targum.render.builder import chat_page, library_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

TOKEN = "test-key"
SITE = "http://pill.test"

DOOR = "/reader/ha-yam-he/reader/index.html"

#: A conversation with a corrected recast and its why, a door to a text, and a ready
#: quote with its source: the turn design's `thread-*` shots drew.
THREAD = {
    "chat": {"id": "abc", "language": "he"},
    "turns": [
        {"n": 1, "role": "user", "said": "אני רוצה לקרא", "stage": "done"},
        {
            "n": 2,
            "role": "assistant",
            "said": (
                "> אני רוצה לקרוא\n= I want to read\n~ The verb ends with an alef.\n"
                f"{DOOR}\n"
                "מה תרצה לקרוא?\n= What would you like to read?"
            ),
            "stage": "done",
            "doors": {DOOR: {"title": "הַיָּם", "language": "he"}},
            "quotes": [
                {
                    "id": "j1",
                    "title": "כתבה",
                    "language": "he",
                    "source": "https://www.ynet.co.il/news/1",
                    "stage": "ready",
                    "seconds": 240,
                }
            ],
        },
    ],
    "seconds": 30,
}


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


def answer_with(routes: dict[str, Any], signed_out: bool = False):
    library = library_page(TOKEN)
    framed = chat_page(TOKEN, embed=True)

    def answer(route, request) -> None:
        url = request.url
        path = url[len(SITE) :].split("?")[0]
        if "embed=1" in url:
            if signed_out:
                # The session is gone: the server sends the frame to sign-in.
                route.fulfill(status=302, headers={"Location": f"{SITE}/account/signin"})
                return
            route.fulfill(status=200, content_type="text/html", body=framed)
            return
        if path == "/account/signin":
            route.fulfill(
                status=200,
                content_type="text/html",
                headers={"Content-Security-Policy": "frame-ancestors 'none'"},
                body="<!doctype html><title>Sign in</title><p>Sign in</p>",
            )
            return
        if path == "/library":
            route.fulfill(status=200, content_type="text/html", body=library)
            return
        if path in routes:
            route.fulfill(
                status=200, content_type="application/json", body=json.dumps(routes[path])
            )
            return
        if path == "/readers":
            body: Any = {"readers": [], "shared": [], "trash": [], "covers": False}
        elif path in ("/account/me", "/account/follows"):
            body = {"signedIn": False}
        elif path == "/words/common":
            body = {"words": [], "offset": 0, "next": None}
        else:
            body = {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    return answer


def framed_thread(browser, width: int = 390):
    """The conversation page as the drawer frames it, opened on THREAD, under a thumb."""
    context = browser.new_context(
        viewport={"width": width, "height": 844}, has_touch=True, is_mobile=width < 600
    )
    page = context.new_page()
    page.route(
        f"{SITE}/**",
        answer_with(
            {
                "/chat/list": {"chats": [{"id": "abc", "title": "hi", "seen": 1}], "usable": True},
                "/chat/abc": THREAD,
            }
        ),
    )
    page.goto(f"{SITE}/chat?embed=1&k={TOKEN}#abc")
    page.wait_for_selector(".chat-door")
    return context, page


def contrast(fore: str, back: str) -> float:
    def channels(css: str) -> list[float]:
        inside = css[css.index("(") + 1 : css.index(")")].replace("/", " ").replace(",", " ")
        return [float(part) for part in inside.split()[:3]]

    def luminance(rgb: list[float]) -> float:
        out = []
        for value in rgb:
            c = value / 255
            out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]

    one, two = luminance(channels(fore)), luminance(channels(back))
    return (max(one, two) + 0.05) / (min(one, two) + 0.05)


def test_the_door_is_named_by_its_title_and_reads_on_its_fill(browser) -> None:
    """#472 B1 and B2: "Open …" was the accent's brown on the primary, about 1:1, and named
    the text by its folder ("Open ha yam")."""
    context, page = framed_thread(browser)
    got = page.evaluate(
        """() => {
          const door = document.querySelector('.chat-door');
          const name = door.querySelector('bdi');
          const style = getComputedStyle(door);
          return {
            text: door.textContent,
            lang: name && name.getAttribute('lang'),
            dir: name && name.getAttribute('dir'),
            color: style.color,
            fill: style.backgroundColor,
          };
        }"""
    )
    context.close()
    assert got["text"] == "Open הַיָּם" and got["lang"] == "he" and got["dir"] == "rtl", got
    assert contrast(got["color"], got["fill"]) >= 4.5, got


def test_why_a_recast_was_corrected_is_a_visible_press(browser) -> None:
    """#472 B6 (§14.3, "Nothing is hover-only"): the reason lived only in a `title`."""
    context, page = framed_thread(browser)
    press = page.locator(".chat-why-press")
    before = press.get_attribute("aria-expanded")
    shown_before = page.eval_on_selector(".chat-why", "w => !w.hidden")
    label = press.inner_text()
    visible = press.is_visible()
    press.tap()
    after = press.get_attribute("aria-expanded")
    shown_after = page.eval_on_selector(".chat-why", "w => !w.hidden")
    context.close()
    assert visible and label == "Why?", label
    # A reader with no known words sees the reason open from the start; either way the
    # press says which it is, and a tap turns it the other way.
    assert before == ("true" if shown_before else "false"), (before, shown_before)
    assert after == ("true" if shown_after else "false") and shown_after != shown_before


def test_the_thread_s_small_controls_answer_a_thumb(browser) -> None:
    """#472 B9 and B8: Hear was 30px wide, the quote card's two links 24px tall, and the
    box's placeholder broke onto a second line sliced by the field's edge."""
    context, page = framed_thread(browser)
    page.wait_for_selector(".quote-source")
    got = page.evaluate(
        """() => {
          const box = (el) => el.getBoundingClientRect();
          const reach = (el) => {
            const after = getComputedStyle(el, '::after');
            return {
              w: Math.max(box(el).width, parseFloat(after.width) || 0),
              h: Math.max(box(el).height, parseFloat(after.height) || 0),
            };
          };
          const play = document.querySelector('.chat-play');
          return {
            play: { w: box(play).width, h: box(play).height },
            source: reach(document.querySelector('.quote-source')),
            more: reach(document.querySelector('.quote-more')),
            placeholder: getComputedStyle(document.getElementById('say'), '::placeholder')
              .whiteSpace,
          };
        }"""
    )
    context.close()
    assert got["play"]["w"] >= 44 and got["play"]["h"] >= 44, got
    for link in ("source", "more"):
        assert got[link]["w"] >= 44 and got[link]["h"] >= 44, got
    assert got["placeholder"] == "nowrap", got


def test_continue_s_title_carries_its_own_language(browser) -> None:
    """#472 B10: a Hebrew title on Continue's chip read as the page's language."""
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    chips = [
        {
            "id": "continue",
            "line": "Continue",
            "title": "הַיָּם",
            "language": "he",
            "reader": "ha-yam-he/reader/index.html",
        }
    ]
    page.route(
        f"{SITE}/**",
        answer_with({"/chat/list": {"chats": [], "usable": True, "talk": True, "chips": chips}}),
    )
    page.goto(f"{SITE}/chat?embed=1&k={TOKEN}")
    page.wait_for_selector(".chip-title")
    got = page.eval_on_selector(
        ".chip-title", "t => [t.getAttribute('lang'), t.getAttribute('dir')]"
    )
    context.close()
    assert got == ["he", "rtl"], got


def test_no_connection_in_the_frame_is_one_row_at_its_top(browser) -> None:
    """#472 B5: the connection's band stretched to two thirds of the drawer."""
    context = browser.new_context(viewport={"width": 460, "height": 900})
    page = context.new_page()
    page.route(f"{SITE}/**", answer_with({"/chat/list": {"chats": [], "usable": True}}))
    page.goto(f"{SITE}/chat?embed=1&k={TOKEN}")
    page.wait_for_selector("#say")
    page.evaluate("() => window.TargumFault.unreachable()")
    page.wait_for_selector("#fault-banner:not([hidden])")
    got = page.evaluate(
        """() => ({
          band: document.getElementById('fault-banner').getBoundingClientRect(),
          main: document.querySelector('.chat-main').getBoundingClientRect(),
        })"""
    )
    context.close()
    assert got["band"]["top"] <= 1 and got["band"]["height"] < 120, got
    assert got["main"]["top"] >= got["band"]["bottom"] - 1, got
    assert got["main"]["height"] > 600, got


def test_a_pressed_drawer_keeps_the_keyboard_inside_it(browser) -> None:
    """#472 B3: Tab walked out of the drawer into the dimmed page behind the scrim."""
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.route(f"{SITE}/**", answer_with({"/chat/list": {"chats": [], "usable": True}}))
    page.goto(f"{SITE}/library?k={TOKEN}")
    page.wait_for_selector("#talk-open")
    page.click("#talk-open")
    page.frame_locator("#talk-frame").locator("#say").wait_for()
    page.wait_for_timeout(300)
    opened = page.evaluate(
        """() => ({
          modal: document.getElementById('talk-drawer').getAttribute('aria-modal'),
          inert: document.querySelector('.site-head').closest('[inert]') !== null,
        })"""
    )
    escaped = []
    for _ in range(25):
        page.keyboard.press("Tab")
        escaped.append(
            page.evaluate(
                """() => {
                  const at = document.activeElement;
                  return !!at && at !== document.body
                    && !document.getElementById('talk-drawer').contains(at);
                }"""
            )
        )
    page.click("#talk-close")
    page.wait_for_timeout(300)
    closed = page.evaluate(
        """() => ({
          modal: document.getElementById('talk-drawer').getAttribute('aria-modal'),
          inert: document.querySelectorAll('[inert]').length,
          focus: document.activeElement && document.activeElement.id,
        })"""
    )
    context.close()
    assert opened == {"modal": "true", "inert": True}, opened
    assert not any(escaped), "Tab stays between the drawer's own controls and its frame"
    assert closed == {"modal": None, "inert": 0, "focus": "talk-open"}, closed


def test_signed_out_the_drawer_is_a_door_back_in(browser) -> None:
    """#472 B4: with the session gone, the frame landed on sign-in, which refuses to be
    framed, and the drawer was a blank sheet with nothing to press."""
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.route(f"{SITE}/**", answer_with({}, signed_out=True))
    page.goto(f"{SITE}/library?k={TOKEN}")
    page.wait_for_selector("#talk-open")
    page.click("#talk-open")
    page.wait_for_selector("#talk-out:not([hidden])", timeout=5000)
    got = page.evaluate(
        """() => ({
          said: document.querySelector('#talk-out p').textContent,
          href: document.getElementById('talk-sign-in').getAttribute('href'),
          target: document.getElementById('talk-sign-in').getAttribute('target'),
          frame: getComputedStyle(document.getElementById('talk-frame')).display,
        })"""
    )
    context.close()
    assert got["said"] == "Sign in to talk to targum.", got
    assert got["href"].startswith("/account/signin?next=%2Flibrary"), got
    assert got["target"] == "_top" and got["frame"] == "none", got


def test_offline_the_pill_s_reason_keeps_full_ink_and_is_said_once(browser) -> None:
    """#472 B11 and polish 5: the pill was dimmed by opacity, its reason with it, and the
    reason was said twice once the line under the band was drawn."""
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    page.route(f"{SITE}/**", answer_with({}))
    page.goto(f"{SITE}/library?k={TOKEN}")
    page.wait_for_selector("#talk-open")
    got = page.evaluate(
        """() => {
          const pill = document.getElementById('talk-open');
          pill.classList.add('offline-off');
          pill.setAttribute('data-why', 'Chat needs a connection.');
          const before = getComputedStyle(pill, '::before');
          const out = {
            opacity: getComputedStyle(pill).opacity,
            color: before.color,
            fill: before.backgroundColor,
            label: getComputedStyle(pill).color,
            pillFill: getComputedStyle(pill).backgroundColor,
          };
          document.documentElement.classList.add('offline-said');
          out.after = getComputedStyle(pill, '::before').content;
          return out;
        }"""
    )
    context.close()
    assert got["opacity"] == "1", got
    assert contrast(got["color"], got["fill"]) >= 4.5, got
    assert contrast(got["label"], got["pillFill"]) >= 4.5, got
    assert got["after"] == "none", got


READING = {
    "document": "ha-yam-he",
    "section": "sec-0001",
    "sentence": "הַיָּם הָיָה שָׁקֵט מְאוֹד בַּבֹּקֶר, וְהַדַּיָּגִים יָצְאוּ אֶל הַמַּיִם",
    "language": "he",
    "title": "A chapter",
}


def framed_in_a_reader(browser, width: int):
    """The conversation page as a reader's drawer frames it, told what is being read."""
    context = browser.new_context(
        viewport={"width": width, "height": 844}, has_touch=width < 600, is_mobile=width < 600
    )
    page = context.new_page()
    page.route(f"{SITE}/**", answer_with({"/chat/list": {"chats": [], "usable": True}}))
    page.goto(f"{SITE}/chat?embed=1&k={TOKEN}")
    page.wait_for_selector("#say")
    page.wait_for_timeout(300)
    page.evaluate(
        "(about) => window.postMessage({type: 'targum:reading', about}, location.origin)",
        READING,
    )
    page.wait_for_selector("#chat-reading:not([hidden])")
    page.wait_for_timeout(200)
    return context, page


FITS = """() => {
  const field = document.getElementById('say');
  const style = getComputedStyle(field);
  const ctx = document.createElement('canvas').getContext('2d');
  ctx.font = [style.fontStyle, style.fontWeight, style.fontSize, style.fontFamily].join(' ');
  const room = field.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  const text = document.getElementById('chat-reading-text');
  return {
    line: field.placeholder,
    fits: ctx.measureText(field.placeholder).width <= room,
    lang: text.getAttribute('lang'),
    dir: text.getAttribute('dir'),
  };
}"""


@pytest.mark.parametrize("width", [390, 1440])
def test_in_a_reader_the_box_s_line_is_never_cut(browser, width: int) -> None:
    """#472 re-audit: a textarea's placeholder takes no ellipsis in Chromium, so in a
    reader on a phone "Ask about the text, or write in Hebrew" was cut as "or wri". It
    falls back to the line the box says everywhere else where it does not fit."""
    context, page = framed_in_a_reader(browser, width)
    got = page.evaluate(FITS)
    context.close()
    assert got["fits"], got
    if width == 1440:
        assert got["line"] == "Ask about the text, or write in Hebrew", got
    else:
        assert got["line"] == "Hebrew or English", got


def test_the_sentence_being_read_says_its_language(browser) -> None:
    """#472 re-audit, §14.3: the Reading line above the box carried a Hebrew sentence
    with no `lang`, so it was read out in the page's language."""
    context, page = framed_in_a_reader(browser, 390)
    got = page.evaluate(FITS)
    context.close()
    assert got["lang"] == "he" and got["dir"] == "rtl", got
