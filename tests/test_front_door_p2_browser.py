"""Design's §14 finish bar on the front door, 2026-11-12: the P2s a browser has to see
(targum-internal#477). The markup half is `test_front_door_p2.py`.

P2-5: offline, Try it and Join fell back to the plain post, and the browser drew its own
error page (`chrome-error://`). The popup stays, and says `door.offline`; only a server
that answered with nothing to read still falls back to the plain post.

P2-9: under a coarse pointer, /connect's bar (the mark 21 tall, EN/RU 17 × 20, "Connect
targum" 32, the email field 35), the text page's credit links (18–22), the landing demo's
Position slider (31), the legal pages' mark (42) and /credits' rows (22) fell short of 44px.

P2-12: the try box's "Looking at the link…" tile was empty, and read as a picture that
failed to load. It draws a link, and holds still under reduced motion.

Skips itself unless Playwright and its Chromium are installed.
"""

from __future__ import annotations

from typing import Any

import pytest

from targum.render.builder import connect_page, credits_page, front_page, legal_page, text_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://door.test"
ADDRESS = "https://targum.page"

#: What a plain post lands on, so a test can tell it happened.
POSTED = "<html><body><p id='posted'>posted</p></body></html>"

#: The try box's answer, as `/try` returns it: the link, and the waitlist under it.
TRIED = (
    "<html><body><main><div class='tried' role='status'><div class='tried-card'>"
    "<div class='tried-body'><p class='tried-title'>A page</p></div></div>"
    "<form class='join-form' method='post' action='/waitlist'><label class='field'>"
    "<input type='email' name='email' required><button class='btn cta' type='submit'>Join"
    "</button></label></form></div></main></body></html>"
)


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


def opened(
    browser: Any,
    html: str,
    width: int = 1440,
    phone: bool = False,
    posted: Any = None,
    motion: str = "no-preference",
) -> tuple[Any, Any, list[str]]:
    """`html` as every page; `posted(route)` answers a script's POST, and a plain post
    (a document POST) lands on `POSTED`."""

    def answer(route: Any, request: Any) -> None:
        if request.method == "POST" and request.resource_type == "document":
            route.fulfill(status=200, content_type="text/html", body=POSTED)
        elif request.method == "POST" and posted:
            posted(route)
        elif request.resource_type == "document":
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(
        viewport={"width": width, "height": 900},
        has_touch=phone,
        is_mobile=phone,
        reduced_motion=motion,
    )
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    return context, page, thrown


def offline_line(language: str) -> str:
    from targum.strings import text

    return text("door.offline", language)


# -- P2-5 ---------------------------------------------------------------------------------


@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("how", ["offline", "refused"])
def test_a_try_with_no_connection_keeps_the_popup(browser: Any, language: str, how: str) -> None:
    """`offline`: the browser knows it is (`navigator.onLine`). `refused`: it thinks it is
    online, and the request never reaches anything."""
    context, page, thrown = opened(
        browser, front_page(language, ADDRESS), posted=lambda route: route.abort()
    )
    try:
        page.goto(SITE + "/")
        if how == "offline":
            context.set_offline(True)
        page.fill(".try-form input[name=link]", "https://he.wikipedia.org/wiki/x")
        page.click(".try-form button[type=submit]")
        page.wait_for_selector("#pop[open] .pop-head[role=alert]")
        assert page.locator("#pop .pop-head").text_content() == offline_line(language)
        assert page.url.startswith(SITE), page.url
        assert page.locator("#posted").count() == 0
        assert not thrown, thrown
    finally:
        context.close()


@pytest.mark.parametrize("language", ["en", "ru"])
def test_joining_with_no_connection_is_said_in_the_popup(browser: Any, language: str) -> None:
    context, page, thrown = opened(
        browser, front_page(language, ADDRESS), posted=lambda route: route.abort()
    )
    try:
        page.goto(SITE + "/")
        page.fill("#join .join-form input[type=email]", "reader@example.com")
        page.click("#join .join-form button[type=submit]")
        page.wait_for_selector("#pop[open] .pop-head[role=alert]")
        assert page.locator("#pop .pop-head").text_content() == offline_line(language)
        assert page.locator("#posted").count() == 0
        assert not page.locator("#join .join-form button[type=submit]").is_disabled()
        assert not thrown, thrown
    finally:
        context.close()


def test_joining_from_the_tried_link_offline_says_it_where_they_typed(browser: Any) -> None:
    answers = iter(["tried"])

    def posted(route: Any) -> None:
        if next(answers, "gone") == "tried":
            route.fulfill(status=200, content_type="text/html", body=TRIED)
        else:
            route.abort()

    context, page, thrown = opened(browser, front_page("en", ADDRESS), posted=posted)
    try:
        page.goto(SITE + "/")
        page.fill(".try-form input[name=link]", "https://he.wikipedia.org/wiki/x")
        page.click(".try-form button[type=submit]")
        page.wait_for_selector("#pop[open] .tried .join-form")
        page.fill("#pop .join-form input[type=email]", "reader@example.com")
        page.click("#pop .join-form button[type=submit]")
        page.wait_for_selector("#pop .pop-wrong")
        assert page.locator("#pop .pop-wrong").text_content() == offline_line("en")
        assert page.locator("#pop .join-form input[type=email]").input_value() == (
            "reader@example.com"
        ), "the address waits to be sent again"
        assert page.locator("#posted").count() == 0
        assert not thrown, thrown
    finally:
        context.close()


def test_a_server_that_answers_nothing_still_falls_back_to_the_plain_post(
    browser: Any,
) -> None:
    def broken(route: Any) -> None:
        route.fulfill(status=500, content_type="text/html", body="<html>oops</html>")

    context, page, thrown = opened(browser, front_page("en", ADDRESS), posted=broken)
    try:
        page.goto(SITE + "/")
        page.fill(".try-form input[name=link]", "https://he.wikipedia.org/wiki/x")
        page.click(".try-form button[type=submit]")
        page.wait_for_selector("#posted")
        assert not thrown, thrown
    finally:
        context.close()


# -- P2-12 --------------------------------------------------------------------------------


@pytest.mark.parametrize("motion", ["no-preference", "reduce"])
def test_looking_at_the_link_draws_a_link(browser: Any, motion: str) -> None:
    held: list[Any] = []
    context, page, thrown = opened(
        browser, front_page("en", ADDRESS), posted=held.append, motion=motion
    )
    try:
        page.goto(SITE + "/")
        page.fill(".try-form input[name=link]", "https://he.wikipedia.org/wiki/x")
        page.click(".try-form button[type=submit]")
        page.wait_for_selector("#pop[open] .pop-reading")
        got = page.evaluate(
            """() => {
              const mark = document.querySelector('#pop .pop-reading .tried-mark');
              const glyph = mark.querySelector('svg path');
              return {glyph: !!glyph, hidden: mark.getAttribute('aria-hidden'),
                      moving: getComputedStyle(mark).animationName};
            }"""
        )
        assert got["glyph"] and got["hidden"] == "true", got
        if motion == "reduce":
            assert got["moving"] == "none", got
        else:
            assert got["moving"] != "none", got
        assert not thrown, thrown
    finally:
        for route in held:
            route.abort()
        context.close()


# -- P2-9 ---------------------------------------------------------------------------------

#: Does a tap `dy` px above and below the middle of the element land on it?
TAPPED = """([selector, dy]) => {
  return [...document.querySelectorAll(selector)].map((one) => {
    one.scrollIntoView({block: 'center', behavior: 'instant'});
    const r = one.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    const hit = (py) => {
      const at = document.elementFromPoint(x, py);
      return !!at && (at === one || one.contains(at));
    };
    return {text: one.textContent.trim(), up: hit(y - dy), down: hit(y + dy),
            w: r.width, h: r.height};
  });
}"""

#: Each matching element's drawn size.
SIZES = """(selector) => [...document.querySelectorAll(selector)]
  .filter((one) => one.getClientRects().length)
  .map((one) => { const r = one.getBoundingClientRect();
                  return {text: one.textContent.trim(), w: r.width, h: r.height}; })"""


def tapped_everywhere(page: Any, selector: str) -> None:
    taps = page.evaluate(TAPPED, [selector, 20])
    assert taps, f"nothing matches {selector}"
    for tap in taps:
        assert tap["up"] and tap["down"], tap


def thumb(browser: Any, html: str) -> tuple[Any, Any, list[str]]:
    context, page, thrown = opened(browser, html, 390, True)
    return context, page, thrown


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_landing_s_position_slider_answers_a_thumb(browser: Any, language: str) -> None:
    context, page, thrown = thumb(browser, front_page(language, ADDRESS))
    try:
        page.goto(SITE + "/")
        page.wait_for_selector("#lines .w")
        assert page.evaluate("() => matchMedia('(pointer: coarse)').matches")
        tapped_everywhere(page, "#track")
        assert not thrown, thrown
    finally:
        context.close()


@pytest.mark.parametrize("language", ["en", "ru"])
def test_connect_s_bar_and_field_answer_a_thumb(browser: Any, language: str) -> None:
    context, page, thrown = thumb(browser, connect_page(language, ADDRESS))
    try:
        page.goto(SITE + "/connect")
        for selector in (".bar .brand", ".bar .btn", ".bar .tongue a", ".join-form input"):
            sizes = page.evaluate(SIZES, selector)
            assert sizes, f"nothing drawn for {selector}"
            for one in sizes:
                assert one["h"] >= 44, (selector, one)
        for one in page.evaluate(SIZES, ".bar .tongue a"):
            assert one["w"] >= 44, one
        assert not thrown, thrown
    finally:
        context.close()


def test_a_text_page_s_credit_links_answer_a_thumb(browser: Any) -> None:
    from targum.catalogue import Entry, Rendering

    ruth = Entry(
        id="ruth",
        title="רות",
        author="Ketuvim · Ruth",
        language="he",
        source="sefaria:he:Ruth",
        blurb="Four chapters, the shortest way in.",
        words=100,
        english="Ruth",
        translations=[
            Rendering(
                name="The Metsudah test Tanakh",
                source="sefaria:en:Ruth",
                publisher="Metsudah Publications",
                licence="CC-BY",
            )
        ],
    )
    context, page, thrown = thumb(browser, text_page(ruth, ADDRESS))
    try:
        page.goto(SITE + "/library/ruth")
        tapped_everywhere(page, ".provenance a")
        assert not thrown, thrown
    finally:
        context.close()


def test_a_legal_page_s_mark_answers_a_thumb(browser: Any) -> None:
    context, page, thrown = thumb(browser, legal_page("privacy", ADDRESS))
    try:
        page.goto(SITE + "/privacy")
        sizes = page.evaluate(SIZES, ".masthead .brand")
        assert sizes and all(one["h"] >= 44 for one in sizes), sizes
        assert not thrown, thrown
    finally:
        context.close()


def test_the_credits_rows_answer_a_thumb(browser: Any, monkeypatch: Any) -> None:
    from types import SimpleNamespace

    from targum import voices

    word = SimpleNamespace(
        page="https://commons.wikimedia.org/wiki/File:1", attribution="x", word="אֶחָד"
    )
    speaker = SimpleNamespace(
        name="YaronSh",
        licence="CC0",
        licence_url="https://creativecommons.org/publicdomain/zero/1.0/",
        recordings=[word],
    )
    monkeypatch.setattr(voices, "credits", lambda language: [speaker, speaker])
    html = credits_page("en", ADDRESS)
    assert "<summary" in html
    context, page, thrown = thumb(browser, html)
    try:
        page.goto(SITE + "/credits")
        sizes = page.evaluate(SIZES, ".speaker summary")
        assert sizes and all(one["h"] >= 44 for one in sizes), sizes[:3]
        assert not thrown, thrown
    finally:
        context.close()


# -- Connect's finish bar (targum-internal#721) -------------------------------------------


@pytest.mark.parametrize(
    ("language", "heading", "grant"),
    [
        ("en", "your own app", "Connect this app to targum"),
        ("ru", "своём приложении", None),
    ],
)
def test_another_app_does_not_keep_the_last_app_s_name(
    browser: Any, language: str, heading: str, grant: str | None
) -> None:
    """P2 6: after Codex, "Another app" left the heading on "Learn Hebrew in Codex"."""
    from targum.strings import catalogue

    context, page, thrown = opened(browser, connect_page(language, ADDRESS))
    try:
        page.goto(SITE + "/connect")
        page.wait_for_selector("#plats:not([hidden])")
        page.click("#tab-codex")
        assert page.text_content("#cn-app") == "Codex"
        page.click("#tab-other")
        assert page.text_content("#cn-app") == heading
        words = catalogue(language)
        said = grant or words["connect.page.connect-to-targum"].replace(
            "{client}", words["connect.page.this-app"]
        )
        assert page.text_content("#cn-grant-title") == said
        page.click("#tab-claude")
        assert page.text_content("#cn-app") == "Claude", "and an app named again is named"
        assert not thrown, thrown
    finally:
        context.close()


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_refused_copy_says_which_keys_copy_it(browser: Any, language: str) -> None:
    """P2 5: with the clipboard refused, the address was selected and nothing was said."""
    context, page, thrown = opened(browser, connect_page(language, ADDRESS))
    try:
        # The browser refuses the write, as a page on a phone without permission meets it.
        page.add_init_script(
            "Object.defineProperty(navigator, 'clipboard', {value: "
            "{writeText: () => Promise.reject(new Error('refused'))}});"
        )
        page.goto(SITE + "/connect")
        page.click(".cn-address .cn-copy")
        label = page.locator(".cn-address .cn-copy span")
        press = "Press " if language == "en" else "Нажмите "
        page.wait_for_function(
            "(press) => document.querySelector('#cn-said').textContent.startsWith(press)",
            arg=press,
        )
        said = label.text_content() or ""
        assert said.startswith(press) and ("Ctrl+C" in said or "⌘C" in said), said
        selected = page.evaluate("() => String(window.getSelection())")
        assert selected == page.text_content(".cn-address code"), "and the text is selected"
        assert not thrown, thrown
    finally:
        context.close()
