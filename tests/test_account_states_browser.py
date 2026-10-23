"""Your account in the states that are not the account (targum-internal#469, design's
blockers B1–B6): still asking, not reached, offline, signed out, the seven days after
Delete, the export, a refused sign-in and the month nearly or quite used."""

from __future__ import annotations

import json
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api")

from targum.render.builder import you_page  # noqa: E402

TOKEN = "test-key"

ME = {
    "signedIn": True,
    "email": "r@example.org",
    "initials": "R",
    "learning": ["he"],
    "reads": ["en"],
    "hours": {"used": 7.85, "allowed": 8, "ends": "1 November"},
    "connections": [],
}


@pytest.fixture
def browser(chromium):
    return chromium.browser()


def opened(
    browser,
    me: Any = ME,
    status: int = 200,
    hold: bool = False,
    offline: bool = False,
    export: tuple[int, str] = (200, "{}"),
    forget: Any = None,
    width: int = 1280,
    held: str = "",
    language: str = "en",
):
    html = you_page(TOKEN, language)
    asked: list[str] = []

    def answer(route, request):
        url = request.url
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        asked.append(url)
        if "/account/me" in url:
            if hold:
                return  # never answered
            if status >= 500:
                return route.fulfill(status=status, content_type="text/plain", body="gone")
            return route.fulfill(
                status=status, content_type="application/json", body=json.dumps(me)
            )
        if "/account/export" in url:
            return route.fulfill(status=export[0], content_type="application/json", body=export[1])
        if "/account/forget" in url:
            return route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(forget or {"signedIn": False}),
            )
        if "/account/sign-in" in url:
            body = {"error": "We're closing this account. To keep it, email hello@targum.page."}
            return route.fulfill(status=403, content_type="application/json", body=json.dumps(body))
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps({"signedIn": False})
        )

    context = browser.new_context(viewport={"width": width, "height": 900}, accept_downloads=True)
    page = context.new_page()
    if held:
        page.add_init_script(f"localStorage.setItem('targum:initials', '{held}');")
    page.route("http://acct.test/**", answer)
    if offline:
        # Registered last, so it runs first (Playwright matches routes newest first).
        page.add_init_script("Object.defineProperty(navigator, 'onLine', {get: () => false});")
        page.route("http://acct.test/account/**", lambda route: route.abort())
    page.goto(f"http://acct.test/you?k={TOKEN}")
    return context, page, asked


SHOWN = """() => [...document.querySelectorAll('main.account > section')]
  .filter((s) => !s.hidden).map((s) => s.id)"""


def test_a_slow_account_says_it_is_getting_it_and_more_past_three_seconds(browser) -> None:
    context, page, _ = opened(browser, hold=True)
    first = page.evaluate(SHOWN)
    page.wait_for_selector("#you-slow:not([hidden])", timeout=6000)
    context.close()
    assert first == ["you-loading"], first


def test_an_unreachable_account_is_not_told_to_sign_in(browser) -> None:
    context, page, _ = opened(browser, status=502, held="R")
    page.wait_for_selector("#you-unreachable:not([hidden])")
    page.wait_for_timeout(300)
    shown = page.evaluate(SHOWN)
    corner = page.evaluate("document.getElementById('account-open').textContent.trim()")
    context.close()
    assert shown == ["you-unreachable"]
    assert corner == "R", "the corner keeps who this browser last knew, not Sign in"


def test_offline_says_what_still_opens(browser) -> None:
    context, page, _ = opened(browser, offline=True)
    page.wait_for_selector("#you-offline:not([hidden])")
    link = page.locator("#you-offline a").get_attribute("href")
    context.close()
    assert link == "/you/saved"


def test_signed_out_is_the_one_answer_that_asks_to_sign_in(browser) -> None:
    context, page, _ = opened(browser, me={"signedIn": False}, status=401)
    page.wait_for_selector("#stranger:not([hidden])")
    said = page.locator("#stranger").inner_text()
    context.close()
    assert said.strip() == "Sign in to see your account."


@pytest.mark.parametrize(
    ("used", "said"),
    [
        (7.9, "6 credits left. The library and word cards use none."),
        (8.0, "You've used this month's credits. They come back on 1 November."),
    ],
)
def test_nearly_out_and_out_say_what_still_works(browser, used: float, said: str) -> None:
    me = {**ME, "hours": {"used": used, "allowed": 8, "ends": "1 November"}}
    context, page, _ = opened(browser, me=me)
    page.wait_for_selector("#credits-low:not([hidden])")
    line = page.locator("#credits-low").inner_text()
    context.close()
    assert line.startswith(said), line


def test_delete_ends_on_a_card_that_says_what_happened(browser) -> None:
    context, page, _ = opened(browser)
    page.wait_for_selector("#you-forget")
    page.click("#you-forget")
    focused = page.evaluate("document.activeElement.id")
    page.click("#you-forget")
    page.wait_for_selector("#you-closed:not([hidden])")
    got = page.evaluate(
        """() => ({
          shown: [...document.querySelectorAll('main.account > section')]
            .filter((s) => !s.hidden).map((s) => s.id),
          role: document.getElementById('you-closed').getAttribute('role'),
          focused: document.activeElement.id,
          said: document.getElementById('you-closed').innerText,
        })"""
    )
    page.wait_for_timeout(1800)
    stayed = page.url
    context.close()
    assert focused == "you-keep", "the safe choice takes the focus when Delete arms"
    assert (
        got["shown"] == ["you-closed"]
        and got["role"] == "status"
        and got["focused"] == "you-closed"
    )
    assert "7 days" in got["said"] and "hello@targum.page" in got["said"]
    assert stayed.startswith("http://acct.test/you"), "no redirect on a timer"


def test_export_says_when_it_is_done_and_when_the_session_has_gone(browser) -> None:
    context, page, _ = opened(browser)
    page.wait_for_selector("#you-export")
    with page.expect_download() as got:
        page.click("#you-export")
    name = got.value.suggested_filename
    done = page.locator("#you-ending-said").inner_text()
    context.close()
    assert name == "targum.json" and done.strip() == "Downloaded targum.json."

    context, page, _ = opened(browser, export=(401, json.dumps({"signedIn": False})))
    page.wait_for_selector("#you-export")
    page.click("#you-export")
    page.wait_for_selector("#you-ending-said:not([hidden])")
    said = page.locator("#you-ending-said").inner_text()
    context.close()
    assert "signed out" in said


def test_a_refused_sign_in_says_why_under_the_field(browser) -> None:
    context, page, _ = opened(browser, me={"signedIn": False}, status=401)
    page.wait_for_selector("#stranger:not([hidden])")
    page.click("#account-open")
    page.fill("#account-email", "closing@example.org")
    page.press("#account-email", "Enter")
    page.wait_for_timeout(400)
    text = page.evaluate("document.getElementById('account-panel').innerText")
    context.close()
    assert "To keep it, email hello@targum.page." in text


# --- design's polish (targum-internal#469) -----------------------------------------

POLISHED = {
    **ME,
    "hours": {"used": 2, "allowed": 8, "ends": "November 1"},
    "connections": [{"client": "c", "name": "Claude", "scopes": "library", "made": 1, "seen": 0}],
    "prompts": [{"id": 1, "name": "my-verbs", "says": "Drill my verbs in every tense. " * 12}],
}

NOTES = """() => {
  const seen = (el) => el.offsetParent !== null;
  const all = [...document.querySelectorAll('main.account .note, main.account .acct-says')]
    .filter(seen)
    .filter((el) => !el.closest('#you-loading, #you-unreachable, #you-offline, #you-closed'));
  const root = parseFloat(getComputedStyle(document.documentElement).fontSize);
  return {
    sizes: [...new Set(all.map((el) => parseFloat(getComputedStyle(el).fontSize) / root))],
    colours: [...new Set(all.map((el) => getComputedStyle(el).color))],
    soft: getComputedStyle(document.documentElement).getPropertyValue('--ink-soft').trim(),
    count: all.length,
  };
}"""


def test_every_quiet_line_is_one_note_at_meta_size(browser) -> None:
    """Polish 5: the notes under What's connected and Your prompts were 0.9375rem in full
    ink, the credits note and a row's line 0.8125rem. §13's meta is 0.875rem."""
    context, page, _ = opened(browser, me=POLISHED)
    try:
        page.wait_for_selector("#prompt-rows .row")
        got = page.evaluate(NOTES)
        assert got["count"] > 5
        assert got["sizes"] == [0.875], got
        assert len(got["colours"]) == 1, got
    finally:
        context.close()


def test_a_long_prompt_is_held_to_two_lines_on_a_phone(browser) -> None:
    """Polish 6: a long prompt ran six lines at 390. It is a `.row` now, its text clamped."""
    context, page, _ = opened(browser, me=POLISHED, width=390)
    try:
        page.wait_for_selector("#prompt-rows .row")
        lines = page.evaluate(
            """() => {
              const says = document.querySelector('#prompt-rows .acct-says');
              return says.getBoundingClientRect().height
                / parseFloat(getComputedStyle(says).lineHeight);
            }"""
        )
        assert lines <= 2.05, lines
    finally:
        context.close()


def test_a_long_prompt_opens_on_a_press_and_closes_on_another(browser) -> None:
    """qa-claude on #871: clamped to two lines, a long prompt had nowhere to show the rest.
    The text opens on a press or a key and closes again; a short one is plain text."""
    short = {"id": 2, "name": "short", "says": "Drill my verbs."}
    me = {**POLISHED, "prompts": [*POLISHED["prompts"], short]}
    context, page, _ = opened(browser, me=me, width=390)
    try:
        page.wait_for_selector("#prompt-rows .row")
        says = page.locator("#prompt-rows .acct-says")
        lines = """(el) => el.getBoundingClientRect().height
          / parseFloat(getComputedStyle(el).lineHeight)"""
        first = says.nth(0)
        assert first.get_attribute("role") == "button"
        assert first.get_attribute("aria-expanded") == "false"
        assert says.nth(1).get_attribute("role") is None, "a short prompt has nothing to open"
        first.click()
        assert first.get_attribute("aria-expanded") == "true"
        assert first.evaluate(lines) > 3, "the whole prompt shows"
        first.focus()
        page.keyboard.press("Enter")
        assert first.get_attribute("aria-expanded") == "false"
        assert first.evaluate(lines) <= 2.05
    finally:
        context.close()


def test_every_rung_fits_the_your_hebrew_select_in_russian_on_a_phone(browser) -> None:
    """Polish 7: a native select can't wrap, and «Могу поддержать простой разгово…» was
    cut at 390. Every rung's label fits the select's own width in Russian."""
    context, page, _ = opened(browser, language="ru", width=390)
    try:
        page.wait_for_selector("#you-level option", state="attached")
        over = page.evaluate(
            """() => {
              const pick = document.getElementById('you-level');
              const style = getComputedStyle(pick);
              const room = pick.clientWidth - parseFloat(style.paddingInlineStart)
                - parseFloat(style.paddingInlineEnd);
              const pen = document.createElement('canvas').getContext('2d');
              pen.font = style.fontWeight + ' ' + style.fontSize + ' ' + style.fontFamily;
              return [...pick.options]
                .filter((o) => pen.measureText(o.textContent).width > room)
                .map((o) => o.textContent);
            }"""
        )
        assert over == [], over
    finally:
        context.close()
