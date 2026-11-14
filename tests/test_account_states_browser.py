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
    routes: dict[str, Any] | None = None,
):
    html = you_page(TOKEN, language)
    asked: list[str] = []

    def answer(route, request):
        url = request.url
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        asked.append(url)
        # A stub per path: "abort" is a dropped connection, a pair is (status, answer).
        for where, stub in (routes or {}).items():
            if where in url:
                if stub == "abort":
                    return route.abort()
                return route.fulfill(
                    status=stub[0], content_type="application/json", body=json.dumps(stub[1])
                )
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
    done = page.locator("#export-said").inner_text()
    context.close()
    assert name == "targum.json" and done.strip() == "Downloaded targum.json."

    context, page, _ = opened(browser, export=(401, json.dumps({"signedIn": False})))
    page.wait_for_selector("#you-export")
    page.click("#you-export")
    page.wait_for_selector("#export-said:not([hidden])")
    said = page.locator("#export-said").inner_text()
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


# --- design's finish bar (targum-internal#719) ---------------------------------------


def test_a_slow_account_is_not_offered_sign_in_in_the_bar(browser) -> None:
    """P1 1: the nav's button said "Sign in" until `/account/me` answered, so a slow page
    told a signed-in reader to sign in. It is a quiet empty circle that opens nothing until
    the account answers."""
    context, page, _ = opened(browser, hold=True)
    try:
        page.wait_for_selector("#you-slow:not([hidden])", timeout=6000)
        corner = page.evaluate(
            """() => { const b = document.getElementById('account-open');
              return {text: b.textContent.trim(), waiting: b.classList.contains('waiting'),
                      disabled: b.getAttribute('aria-disabled'), name: b.getAttribute('aria-label'),
                      shown: !b.hidden}; }"""
        )
        page.click("#account-open", force=True)
        opened_panel = page.evaluate("!document.getElementById('account-panel').hidden")
    finally:
        context.close()
    assert "Sign in" not in corner["text"], corner
    assert corner["text"] == "" and corner["waiting"] and corner["disabled"] == "true", corner
    assert corner["name"] and corner["shown"], "still a named place in the bar, not a gap"
    assert not opened_panel, "the sign-in form is not offered before the account answers"


def test_the_bar_says_sign_in_once_the_account_says_nobody(browser) -> None:
    """The one answer that draws Sign in, on a page that never starts sync itself."""
    context, page, _ = opened(browser, me={"signedIn": False}, status=401)
    try:
        page.wait_for_selector("#stranger:not([hidden])")
        page.wait_for_function(
            "document.getElementById('account-open').textContent.trim() === 'Sign in'"
        )
        waiting = page.evaluate(
            "document.getElementById('account-open').classList.contains('waiting')"
        )
    finally:
        context.close()
    assert not waiting


def test_a_signed_in_bar_draws_the_initials_without_any_held(browser) -> None:
    context, page, _ = opened(browser)
    try:
        page.wait_for_function("document.getElementById('account-open').textContent.trim() === 'R'")
    finally:
        context.close()


FAULT = "#you-languages-said .fault-line"


def test_a_language_that_does_not_reach_the_account_says_so_and_is_drawn_back(browser) -> None:
    """P1 2: no `.catch`, so a dropped connection left the select showing a language the
    account never kept, and said nothing."""
    context, page, asked = opened(browser, routes={"/account/languages": "abort"})
    try:
        page.wait_for_selector("#you-start option[value='fr']", state="attached")
        page.select_option("#you-start", "fr")
        page.wait_for_selector(FAULT)
        said = page.locator("#you-languages-said").inner_text()
        rows = page.evaluate(
            "[...document.querySelectorAll('#you-learning [data-code]')].map((r) => r.dataset.code)"
        )
        again = page.locator(FAULT + " button").inner_text()
        tries = len([u for u in asked if "/account/languages" in u])
        page.click(FAULT + " button")
        page.wait_for_timeout(700)
        retried = len([u for u in asked if "/account/languages" in u])
    finally:
        context.close()
    assert "We couldn't save that." in said and "Saved" not in said
    assert rows == ["he"], "drawn back to what the account kept"
    assert again == "Try again" and retried == tries + 1


def test_a_refused_language_is_a_clay_line_not_a_quiet_one(browser) -> None:
    refusal = {"error": "That language isn't open yet.", "learning": ["he"], "reads": ["en"]}
    context, page, _ = opened(browser, routes={"/account/languages": (400, refusal)})
    try:
        page.wait_for_selector("#you-start option[value='fr']", state="attached")
        page.select_option("#you-start", "fr")
        page.wait_for_selector(FAULT)
        line = page.evaluate(
            """() => { const n = document.getElementById('you-languages-said');
              return {bad: n.classList.contains('bad'), text: n.innerText}; }"""
        )
    finally:
        context.close()
    assert line["bad"] and "That language isn't open yet." in line["text"]


def test_a_rung_that_does_not_reach_the_account_says_so(browser) -> None:
    context, page, _ = opened(browser, routes={"/account/level": "abort"})
    try:
        page.wait_for_selector("#you-level option[value='bet']", state="attached")
        page.select_option("#you-level", "bet")
        page.wait_for_selector(FAULT)
        value = page.evaluate("document.getElementById('you-level').value")
    finally:
        context.close()
    assert value == "", "drawn back to the rung the account kept"


RECORDING = {**ME, "events": {"kept": True, "on": True}, "counting": {"kept": True, "on": True}}


@pytest.mark.parametrize("press", ["#record-switch", "#counting-switch"])
def test_a_switch_that_does_not_reach_the_account_stays_and_says_so(browser, press: str) -> None:
    routes = {"/account/events": "abort", "/account/counting": "abort"}
    context, page, _ = opened(browser, me=RECORDING, routes=routes)
    try:
        page.wait_for_selector(press)
        page.click(press)
        where = "#record-said" if press == "#record-switch" else "#counting-said"
        page.wait_for_selector(where + " .fault-line")
        said = page.locator(where).inner_text()
        pressed = page.get_attribute(press, "aria-pressed")
    finally:
        context.close()
    assert "We couldn't save that." in said and "Stopped" not in said
    assert pressed == "true", "still on, as the account has it"


def test_a_refused_switch_is_not_told_stopped(browser) -> None:
    routes = {"/account/events": (401, {"signedIn": False})}
    context, page, _ = opened(browser, me=RECORDING, routes=routes)
    try:
        page.wait_for_selector("#record-switch")
        page.click("#record-switch")
        page.wait_for_selector("#record-said .fault-line")
        said = page.locator("#record-said").inner_text()
    finally:
        context.close()
    assert "signed out" in said and "Stopped" not in said


def test_erase_that_does_not_reach_the_account_is_not_erased(browser) -> None:
    context, page, _ = opened(browser, me=RECORDING, routes={"/account/events": "abort"})
    try:
        page.wait_for_selector("#record-erase")
        page.click("#record-erase")
        page.click("#record-erase")
        page.wait_for_selector("#record-said .fault-line")
        said = page.locator("#record-said").inner_text()
    finally:
        context.close()
    assert "We couldn't save that." in said and "Erased" not in said


def test_erase_has_a_way_back_with_the_focus(browser) -> None:
    """P2 5: "Erase it for good" had no Keep beside it, as Delete has."""
    context, page, asked = opened(browser, me=RECORDING)
    try:
        page.wait_for_selector("#record-erase")
        page.click("#record-erase")
        armed = page.evaluate(
            """() => ({keep: !document.getElementById('record-keep').hidden,
                       focused: document.activeElement.id,
                       erase: document.getElementById('record-erase').textContent.trim()})"""
        )
        page.click("#record-keep")
        after = page.evaluate(
            """() => ({keep: !document.getElementById('record-keep').hidden,
                       erase: document.getElementById('record-erase').textContent.trim()})"""
        )
    finally:
        context.close()
    assert armed == {"keep": True, "focused": "record-keep", "erase": "Erase it for good"}
    assert after == {"keep": False, "erase": "Erase what's recorded"}
    assert not [u for u in asked if "/account/events" in u], "Keep it erases nothing"


def test_accept_that_does_not_reach_the_account_comes_back(browser) -> None:
    context, page, _ = opened(browser, routes={"/account/grant": "abort"})
    try:
        page.wait_for_selector("#grant-go")
        page.click("#grant-go")
        page.wait_for_selector("#grant-said .fault-line")
        disabled = page.evaluate("document.getElementById('grant-go').disabled")
    finally:
        context.close()
    assert not disabled


def test_exports_answer_is_under_export_and_goes_when_delete_is_asked(browser) -> None:
    """P1 3: "Downloaded targum.json." was the card's last line, under Delete, where it
    then read as Delete's answer."""
    context, page, _ = opened(browser, width=390)
    try:
        page.wait_for_selector("#you-export")
        with page.expect_download():
            page.click("#you-export")
        place = page.evaluate(
            """() => ({row: document.getElementById('export-said').closest('li')
                         === document.getElementById('you-export').closest('li'),
                       ending: document.getElementById('you-ending-said').hidden})"""
        )
        page.click("#you-forget")
        gone = page.evaluate("document.getElementById('export-said').hidden")
    finally:
        context.close()
    assert place == {"row": True, "ending": True}
    assert gone, "nothing of Export's stands beside Yes, delete my account"


def test_a_failed_export_says_so_under_its_press(browser) -> None:
    context, page, _ = opened(browser, export=(500, "{}"))
    try:
        page.wait_for_selector("#you-export")
        page.click("#you-export")
        page.wait_for_selector("#export-said .fault-line")
        said = page.locator("#export-said").inner_text()
    finally:
        context.close()
    assert "We couldn't make the file." in said


def test_the_clay_mark_stays_on_its_sentences_line_on_a_phone(browser) -> None:
    """P2 7: the mark wrapped above "We couldn't reach targum, so nothing was deleted."."""
    context, page, _ = opened(browser, width=390, routes={"/account/forget": "abort"})
    try:
        page.wait_for_selector("#you-forget")
        page.click("#you-forget")
        page.click("#you-forget")
        page.wait_for_selector("#you-ending-said .fault-line")
        tops = page.evaluate(
            """() => { const line = document.querySelector('#you-ending-said .fault-line');
              return [line.querySelector('.fault-icon').getBoundingClientRect().top,
                      line.querySelector('.fault-said').getBoundingClientRect().top]; }"""
        )
    finally:
        context.close()
    assert abs(tops[0] - tops[1]) < 8, tops


def test_slows_try_again_is_errors_press(browser) -> None:
    """P2 8: one look for Try again in slow and in not reached."""
    context, page, _ = opened(browser, hold=True)
    try:
        page.wait_for_selector("#you-slow:not([hidden])", timeout=6000)
        kind = page.evaluate(
            """() => [document.getElementById('you-slow-again').className,
                      document.getElementById('you-reach-again').className,
                      document.getElementById('you-slow-again').parentElement.className]"""
        )
    finally:
        context.close()
    assert kind[0] == kind[1] == "btn tonal" and kind[2] == "ending-row", kind


def test_the_form_of_address_is_one_tab_stop_with_arrows(browser) -> None:
    """P2 10: both radios were Tab stops and the arrows did nothing."""
    me = {**ME, "address": "m"}
    context, page, asked = opened(
        browser, me=me, routes={"/account/address": (200, {"address": "f"})}
    )
    try:
        page.wait_for_selector("#you-address-row:not([hidden])")
        stops = page.evaluate(
            "['m', 'f'].map((f) => document.getElementById('address-' + f).tabIndex)"
        )
        page.focus("#address-m")
        page.keyboard.press("ArrowRight")
        page.wait_for_function(
            "document.getElementById('address-f').getAttribute('aria-checked') === 'true'"
        )
        after = page.evaluate(
            """[document.activeElement.id,
                ...['m', 'f'].map((f) => document.getElementById('address-' + f).tabIndex)]"""
        )
    finally:
        context.close()
    assert stops == [0, -1]
    assert after == ["address-f", -1, 0]
    assert [u for u in asked if "/account/address" in u]


def kept_now(page, me: Any) -> None:
    """From here on `/account/me` answers `me`: what the account holds after a press whose
    own answer was lost. Registered last, so it runs first."""
    page.route(
        "http://acct.test/account/me**",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(me)
        ),
    )


@pytest.mark.parametrize(
    ("press", "where", "field", "said"),
    [
        ("#record-switch", "#record-said", "events", "Stopped. What's already recorded"),
        ("#counting-switch", "#counting-said", "counting", "Stopped. Your texts leave"),
    ],
)
def test_a_switch_whose_answer_was_lost_shows_what_the_account_holds(
    browser, press: str, where: str, field: str, said: str
) -> None:
    """qa N2 on #1227: the server stopped recording but its answer never came. Drawn
    back to what it was, the switch said "on" for a consent the account no longer held."""
    routes = {"/account/events": "abort", "/account/counting": "abort"}
    context, page, _ = opened(browser, me=RECORDING, routes=routes)
    try:
        page.wait_for_selector(press)
        kept_now(page, {**RECORDING, field: {"kept": True, "on": False}})
        page.click(press)
        page.wait_for_function(
            f"document.querySelector({press!r}).getAttribute('aria-pressed') === 'false'"
        )
        line = page.locator(where).inner_text()
        faulted = page.locator(where + " .fault-line").count()
    finally:
        context.close()
    assert said in line and not faulted


def test_a_switch_falls_back_to_what_it_was_when_the_account_cannot_be_read(browser) -> None:
    context, page, _ = opened(browser, me=RECORDING, routes={"/account/events": "abort"})
    try:
        page.wait_for_selector("#record-switch")
        page.route("http://acct.test/account/me**", lambda route: route.abort())
        page.click("#record-switch")
        page.wait_for_selector("#record-said .fault-line")
        pressed = page.get_attribute("#record-switch", "aria-pressed")
    finally:
        context.close()
    assert pressed == "true"


def test_a_grant_whose_answer_was_lost_is_accepted(browser) -> None:
    context, page, _ = opened(browser, routes={"/account/grant": "abort"})
    try:
        page.wait_for_selector("#grant-go")
        kept_now(page, {**ME, "granted": True})
        page.click("#grant-go")
        page.wait_for_selector("#grant-go", state="hidden")
        said = page.locator("#grant-said").inner_text()
    finally:
        context.close()
    assert "now offers a correction" in said
