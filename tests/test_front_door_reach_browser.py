"""The front door's last polish from design's §14 pass (targum-internal#477).

Polish 4: the word card's Here row ran its meaning on after the form, and at 1440 the last
word wrapped alone ("crack" / «разбивают» under "Here"). The meaning now has a line of its
own under the form.

Polish 8: under a coarse pointer, four presses answered under 44px: the landing bar's mark
(21 tall), the why-fold (39 wide), the chat demo's "Save as a text" (73 × 20) and a text
page's way back to the Library (38 × 18). A tap 20px above or below the middle of a link
must still land on it.

And the door itself (targum-internal#672): signed out, sign-in carries no `chrome.css`, so
its links inside a line drew the browser's blue; under a thumb "Join the waitlist" was
99 × 21 and a text page's "Sign in to read it" 88 × 18; and a 502 from the proxy was told
as the connection ("We can't reach targum") when targum had been reached.

Skips itself unless Playwright and its Chromium are installed.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from targum.render.builder import front_page, signin_page, text_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://door.test"


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
    browser: Any, html: str, width: int, phone: bool, sign_in: Any = None
) -> tuple[Any, Any, list[str]]:
    """`html` as every page, and `sign_in(route)` as what POST /account/sign-in answers."""

    def answer(route: Any, request: Any) -> None:
        if request.resource_type == "document":
            route.fulfill(status=200, content_type="text/html", body=html)
        elif sign_in and request.url.endswith("/account/sign-in"):
            sign_in(route)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    context = browser.new_context(
        viewport={"width": width, "height": 900}, has_touch=phone, is_mobile=phone
    )
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    return context, page, thrown


#: Does a tap `dy` px above and below the middle of the element land on it?
TAPPED = """([selector, dy]) => {
  const one = document.querySelector(selector);
  one.scrollIntoView({block: 'center', behavior: 'instant'});
  const r = one.getBoundingClientRect();
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  const hit = (py) => {
    const at = document.elementFromPoint(x, py);
    return !!at && (at === one || one.contains(at));
  };
  return {up: hit(y - dy), down: hit(y + dy), w: r.width, h: r.height};
}"""


@pytest.mark.parametrize(("language", "gloss"), [("en", "crack"), ("ru", "разбивают")])
def test_the_here_row_puts_its_meaning_on_a_line_of_its_own(
    browser: Any, language: str, gloss: str
) -> None:
    context, page, thrown = opened(
        browser, front_page(language, "https://targum.page"), 1440, False
    )
    try:
        page.goto(SITE + "/")
        page.wait_for_selector("#card .facts-list dd")
        got = page.evaluate(
            """() => {
              const dd = document.querySelector('#card .facts-list dd');
              const gloss = dd.querySelector('.here-gloss');
              const form = dd.querySelector('.he');
              return gloss && {
                text: gloss.textContent, display: getComputedStyle(gloss).display,
                under: gloss.getBoundingClientRect().top >= form.getBoundingClientRect().bottom - 2,
              };
            }"""
        )
        assert got, "the Here row has no meaning of its own"
        assert got["text"] == gloss
        assert got["display"] == "block" and got["under"], got
        assert not thrown, thrown
    finally:
        context.close()


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_landing_s_small_presses_answer_a_thumb(browser: Any, language: str) -> None:
    html = front_page(language, "https://targum.page")
    context, page, thrown = opened(browser, html, 390, True)
    try:
        page.goto(SITE + "/")
        page.wait_for_selector("#lines .w")
        assert page.evaluate("() => matchMedia('(pointer: coarse)').matches")
        brand = page.locator(".bar .brand").bounding_box()
        assert brand and brand["height"] >= 44, brand
        fold = page.locator("#whyFold").bounding_box()
        assert fold and fold["width"] >= 44 and fold["height"] >= 44, fold
        save = page.evaluate(TAPPED, [".ct-sum a", 20])
        assert save["up"] and save["down"], save
        assert not thrown, thrown
    finally:
        context.close()


def test_a_text_page_s_way_back_answers_a_thumb(browser: Any) -> None:
    from targum.catalogue import Entry

    ruth = Entry(
        id="ruth",
        title="רות",
        author="Ketuvim · Ruth",
        language="he",
        source="sefaria:he:Ruth",
        blurb="Four chapters, the shortest way in.",
        words=100,
        english="Ruth",
    )
    context, page, thrown = opened(browser, text_page(ruth, "https://targum.page"), 390, True)
    try:
        page.goto(SITE + "/library/ruth")
        page.wait_for_selector(".where a")
        back = page.evaluate(TAPPED, [".where a", 20])
        assert back["h"] < 44, "the word itself stays small; the reach is what grows"
        assert back["up"] and back["down"], back
        assert not thrown, thrown
    finally:
        context.close()


TEAL = "rgb(31, 111, 107)"

#: The refusal an address not on the guest list gets while the front door takes one, as
#: `serve.py` sends it: the sentence, the words it wraps as a link, and where they go.
REFUSED = (
    '{"error": "Thanks for asking. targum isn\'t open yet. Join the waitlist and we\'ll'
    " email you when it's your turn.\","
    ' "join": "/#join", "join_link": "Join the waitlist"}'
)


def refused(route: Any) -> None:
    route.fulfill(status=403, content_type="application/json", body=REFUSED)


def refused_in(language: str) -> Any:
    """The same refusal in `language`, from the catalogue `serve.py` says it from: on the
    Russian page the link is «Встаньте в список ожидания», the longest of them (#681)."""
    from targum.strings import text

    body = json.dumps(
        {
            "error": text("serve.not-open.waitlist", language),
            "join": "/#join",
            "join_link": text("serve.not-open.join-link", language),
        },
        ensure_ascii=False,
    )

    def answer(route: Any) -> None:
        route.fulfill(status=403, content_type="application/json", body=body)

    return answer


#: Each link's colour and weight, and whether anything is still the browser's blue.
LINKS = """() => [...document.querySelectorAll('.gate .said a, .gate .join-link')].map(a => {
  const style = getComputedStyle(a);
  return {text: a.textContent, color: style.color, weight: style.fontWeight};
})"""


def test_the_door_s_links_are_the_primary(browser: Any) -> None:
    """§4, §13: a link on the desk is teal at the desk's link weight, never `#0000EE`."""
    context, page, thrown = opened(
        browser, signin_page(join="/#join"), 1440, False, sign_in=refused
    )
    try:
        page.goto(SITE + "/account/signin")
        page.fill("#email", "stranger@example.com")
        page.click("#ask button")
        page.wait_for_selector(".gate .join-link")
        links = page.evaluate(LINKS)
        assert [one["text"] for one in links] == ["Join the waitlist", "Join the waitlist"]
        for one in links:
            assert one["color"] == TEAL and one["weight"] == "600", one
        assert not thrown, thrown
    finally:
        context.close()


#: The top of a link's reach, and the bottom of what stands over it.
OVER = """([selector, over]) => {
  const one = document.querySelector(selector);
  const r = one.getBoundingClientRect();
  const reach = getComputedStyle(one, '::after');
  return {
    top: r.top + parseFloat(reach.top),
    above: document.querySelector(over).getBoundingClientRect().bottom,
  };
}"""


@pytest.mark.parametrize("language", ["en", "ru"])
def test_the_door_s_links_answer_a_thumb(browser: Any, language: str) -> None:
    """§8: 44px under a coarse pointer, by a centred reach that crosses only a margin."""
    context, page, thrown = opened(
        browser, signin_page(join="/#join", language=language), 390, True, sign_in=refused
    )
    try:
        page.goto(SITE + "/account/signin")
        assert page.evaluate("() => matchMedia('(pointer: coarse)').matches")
        join = page.evaluate(TAPPED, [".gate .new-here a", 20])
        assert join["h"] < 44, "the words stay their size; the reach is what grows"
        assert join["up"] and join["down"], join
        over = page.evaluate(OVER, [".gate .new-here a", ".gate h1"])
        assert over["top"] >= over["above"], f"the reach crosses the heading: {over}"
        page.fill("#email", "stranger@example.com")
        page.click("#ask button")
        page.wait_for_selector(".gate .join-link")
        refusal = page.evaluate(TAPPED, [".gate .join-link", 20])
        assert refusal["up"] and refusal["down"], refusal
        assert not thrown, thrown
    finally:
        context.close()


def test_a_text_page_s_way_in_answers_a_thumb(browser: Any, monkeypatch: Any) -> None:
    from targum.catalogue import Entry

    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    ruth = Entry(
        id="ruth",
        title="רות",
        author="Ketuvim · Ruth",
        language="he",
        source="sefaria:he:Ruth",
        blurb="Four chapters, the shortest way in.",
        words=100,
        english="Ruth",
    )
    html = text_page(ruth, "https://targum.page")
    assert 'class="door-in"' in html, "the way in is drawn only while the door takes an address"
    context, page, thrown = opened(browser, html, 390, True)
    try:
        page.goto(SITE + "/library/ruth")
        page.wait_for_selector(".door-in a")
        way_in = page.evaluate(TAPPED, [".door-in a", 20])
        assert way_in["h"] < 44, "the words stay their size; the reach is what grows"
        assert way_in["up"] and way_in["down"], way_in
        over = page.evaluate(OVER, [".door-in a", ".door .go"])
        # Not merely clear: without the line's own margin the reach cleared the press by
        # about 1px, a hair a thumb does not respect (#677). With it, about 5.
        assert over["top"] - over["above"] >= 4, f"the reach crowds the waitlist's press: {over}"
        assert not thrown, thrown
    finally:
        context.close()


#: How many lines the link is set on, and whether a tap 20px off its middle lands.
ONE_LINE = """(selector) => {
  const one = document.querySelector(selector);
  return {lines: one.getClientRects().length, text: one.textContent};
}"""


def ruth_behind_the_door(monkeypatch: Any) -> str:
    from targum.catalogue import Entry

    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    ruth = Entry(
        id="ruth",
        title="רות",
        author="Ketuvim · Ruth",
        language="he",
        source="sefaria:he:Ruth",
        blurb="Four chapters, the shortest way in.",
        words=100,
        english="Ruth",
    )
    return text_page(ruth, "https://targum.page", language="ru")


@pytest.mark.parametrize("width", [320, 360])
def test_the_ways_in_keep_one_line_on_a_narrow_phone_in_russian(
    browser: Any, monkeypatch: Any, width: int
) -> None:
    """A link broken over two lines is two fragments, and the reach centred on both stood
    between them, over neither: each way in stays one box at 320 and 360 (#672, #677)."""
    context, page, thrown = opened(
        browser, signin_page(join="/#join", language="ru"), width, True, sign_in=refused_in("ru")
    )
    try:
        page.goto(SITE + "/account/signin")
        page.fill("#email", "stranger@example.com")
        page.click("#ask button")
        page.wait_for_selector(".gate .join-link")
        said = page.locator(".gate .join-link").text_content()
        assert said == "Встаньте в список ожидания", said
        for selector in (".gate .new-here a", ".gate .join-link"):
            got = page.evaluate(ONE_LINE, selector)
            assert got["lines"] == 1, f"{selector} breaks at {width}: {got}"
            tap = page.evaluate(TAPPED, [selector, 20])
            assert tap["up"] and tap["down"], (selector, tap)
        assert not thrown, thrown
    finally:
        context.close()
    context, page, thrown = opened(browser, ruth_behind_the_door(monkeypatch), width, True)
    try:
        page.goto(SITE + "/library/ruth")
        page.wait_for_selector(".door-in a")
        got = page.evaluate(ONE_LINE, ".door-in a")
        assert got["lines"] == 1, f"the text page's way in breaks at {width}: {got}"
        tap = page.evaluate(TAPPED, [".door-in a", 20])
        assert tap["up"] and tap["down"], tap
        assert not thrown, thrown
    finally:
        context.close()


#: What a server's fault looks like on the wire: the proxy's page of HTML while targum
#: restarts, targum's own JSON 5xx that carries no `error` to say (#677), and the one 5xx
#: targum sends on purpose, the mailer's 502, which does (#681). `None` is that sentence,
#: said in the page's language as `serve.py` says it.
FAULTS: dict[str, tuple[int, str, str | None]] = {
    "proxy": (502, "text/html", "<html>502 Bad Gateway</html>"),
    "json": (500, "application/json", '{"ok": false}'),
    "mailer": (502, "application/json", None),
}

#: What the form says after a press, and where the keyboard and the clay mark are.
AFTER = """() => ({
  said: document.querySelector('#sent').textContent,
  shown: !document.querySelector('#sent').hidden,
  marked: document.querySelector('#sent').classList.contains('fault-marked'),
  under: [...document.querySelectorAll('.fault-under')].map((p) => p.textContent),
  invalid: document.querySelector('#email').getAttribute('aria-invalid'),
  outlined: !!document.querySelector('.fault-field'),
  focus: document.activeElement && document.activeElement.matches('#email') ? 'field'
    : document.activeElement && document.activeElement.matches('#ask button') ? 'button'
    : document.activeElement && document.activeElement.tagName,
  banner: !!document.querySelector('#fault-banner:not([hidden])'),
  again: !document.querySelector('#ask button').disabled,
  form: !document.querySelector('#ask').hidden,
})"""


@pytest.mark.parametrize("fault", sorted(FAULTS))
@pytest.mark.parametrize(
    ("language", "line"),
    [
        ("en", "We couldn't send a link just now. Try again."),
        ("ru", "Сейчас не получилось отправить ссылку. Попробуйте ещё раз."),
    ],
)
def test_a_sign_in_the_server_could_not_send_is_not_told_as_the_connection(
    browser: Any, language: str, line: str, fault: str
) -> None:
    """targum was reached, and could not send: neither the connection nor the address. So
    the form's own line says it, with the clay mark, the field is left unmarked, and the
    keyboard is back on the press that tries again (#677, #681)."""
    from targum.strings import text

    status, kind, body = FAULTS[fault]
    if body is None:
        line = text("serve.we-couldn-t-send-the-link", language)
        body = json.dumps({"error": line}, ensure_ascii=False)

    def bad_gateway(route: Any) -> None:
        route.fulfill(status=status, content_type=kind, body=body)

    context, page, thrown = opened(
        browser, signin_page(language=language), 1440, False, sign_in=bad_gateway
    )
    try:
        page.goto(SITE + "/account/signin")
        page.fill("#email", "reader@example.com")
        page.click("#ask button")
        # Every answer gives the press back, so wait on that, not on the line it should say.
        page.wait_for_function("() => !document.querySelector('#ask button').disabled")
        got = page.evaluate(AFTER)
        assert got == {
            "said": line,
            "shown": True,
            "marked": True,
            "under": [],
            "invalid": None,
            "outlined": False,
            "focus": "button",
            "banner": False,
            "again": True,
            "form": True,
        }
        assert not thrown, thrown
    finally:
        context.close()


def test_a_sign_in_the_address_was_refused_for_stays_under_the_field(browser: Any) -> None:
    """A 4xx is about the address that was typed, so it keeps its place under the field,
    with the outline and the keyboard there (design.md §12, 2026-10-09)."""
    from targum.strings import text

    line = text("serve.we-ve-sent-a-few-links", "en")

    def too_often(route: Any) -> None:
        route.fulfill(status=429, content_type="application/json", body=json.dumps({"error": line}))

    context, page, thrown = opened(browser, signin_page(), 1440, False, sign_in=too_often)
    try:
        page.goto(SITE + "/account/signin")
        page.fill("#email", "reader@example.com")
        page.click("#ask button")
        page.wait_for_function("() => !document.querySelector('#ask button').disabled")
        got = page.evaluate(AFTER)
        assert got["under"] == [line], got
        assert got["invalid"] == "true" and got["outlined"], got
        assert got["focus"] == "field" and not got["shown"] and not got["marked"], got
        assert got["again"] and got["form"] and not got["banner"], got
        assert not thrown, thrown
    finally:
        context.close()
