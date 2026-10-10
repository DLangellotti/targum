"""The five surfaces a refusal is drawn on, in a real browser (design.md §12, "A refusal
is drawn on one of five surfaces", 2026-10-09).

Under a field, a line, a panel, the connection's banner and a whole page. `fault.js`
draws the first four and the templates the fifth; what is held here is what a reader
sees of each — where it stands, what it says, what can be pressed, and that the clay is
only ever the mark or the outline.

Skips itself without Playwright and its Chromium, as the other browser tests do.
"""

from __future__ import annotations

import json

import pytest

from targum.render.builder import add_page, not_found_page, signin_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

TOKEN = "test-key"
INK = "rgb(28, 26, 23)"
CLAY = "rgb(180, 85, 63)"


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


def served(browser, html: str, path: str, answer, width: int = 1280):
    """`html` at `http://fault.test{path}`, every other request handed to `answer`."""
    context = browser.new_context(viewport={"width": width, "height": 900})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))

    def route(route, request):
        if request.url.split("?")[0].endswith(path):
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            answer(route, request)

    page.route("http://fault.test/**", route)
    page.goto("http://fault.test" + path)
    return context, page, thrown


def json_answer(route, body: dict, status: int = 200) -> None:
    route.fulfill(status=status, content_type="application/json", body=json.dumps(body))


UNDER = """
() => {
  const under = document.querySelector('.fault-under');
  if (!under) return null;
  const field = document.querySelector('.fault-field');
  return {
    said: under.querySelector('.fault-said').textContent,
    ink: getComputedStyle(under).color,
    mark: getComputedStyle(under.querySelector('.fault-icon')).stroke,
    outlined: field ? field.id : null,
    focused: document.activeElement ? document.activeElement.id : null,
    invalid: document.activeElement.getAttribute('aria-invalid'),
    described: (document.activeElement.getAttribute('aria-describedby') || '').split(' '),
    underId: under.id,
  };
}
"""


def test_what_the_box_was_given_is_refused_under_the_box(browser) -> None:
    """Under a field: the well outlined in clay, focus left in the box, one line under
    it. Typing again takes both away."""
    refusal = "We can't read .docx files. Paste the text instead."

    def answer(route, request):
        if "/prepare" in request.url:
            json_answer(route, {"error": refusal})
        else:
            json_answer(route, {})

    context, page, thrown = served(browser, add_page(TOKEN), "/add", answer)
    page.fill("#given", "https://example.com/lesson.docx")
    page.click("#go")
    page.wait_for_selector(".fault-under")
    under = page.evaluate(UNDER)
    card_hidden = page.evaluate("() => document.getElementById('status').hidden")
    page.type("#given", " ")
    mended = page.evaluate(
        "() => [!!document.querySelector('.fault-under'), !!document.querySelector('.fault-field'),"
        " document.getElementById('given').getAttribute('aria-describedby')]"
    )
    context.close()

    assert not thrown, thrown
    assert under["said"] == refusal
    assert under["ink"] == INK and under["mark"] == CLAY
    assert under["outlined"] == "given-well" and under["focused"] == "given"
    assert under["invalid"] == "true" and under["underId"] in under["described"]
    assert "understood" in under["described"], "the box keeps what already described it"
    assert card_hidden, "the card under the box steps aside"
    assert mended == [False, False, "understood"]


def test_targum_out_of_reach_is_one_band_under_the_top_bar(browser) -> None:
    """The connection's banner: in the header, under its row; one Try again and no ×;
    and Try again presses again."""
    asked: list[str] = []

    def answer(route, request):
        if "/prepare" in request.url:
            asked.append(request.url)
            if len(asked) == 1:
                route.abort()
                return
            json_answer(route, {"error": "That isn't a link. Paste one that starts with https."})
        else:
            json_answer(route, {})

    context, page, thrown = served(browser, add_page(TOKEN), "/add", answer)
    page.fill("#given", "https://example.com/a")
    page.click("#go")
    page.wait_for_selector("#fault-banner:not([hidden])")
    band = page.evaluate(
        """() => {
          const band = document.getElementById('fault-banner');
          return {
            said: band.querySelector('.fault-said').textContent,
            buttons: [...band.querySelectorAll('button')].map((b) => b.textContent),
            inHeader: band.parentElement.classList.contains('site-head'),
            role: band.getAttribute('role'),
          };
        }"""
    )
    page.click("#fault-banner .fault-act")
    page.wait_for_selector(".fault-under")
    gone = page.evaluate("() => document.getElementById('fault-banner').hidden")
    context.close()

    assert not thrown, thrown
    assert band == {
        "said": "We can't reach targum. This page stays open.",
        "buttons": ["Try again"],
        "inHeader": True,
        "role": "status",
    }
    assert len(asked) == 2 and gone


@pytest.mark.parametrize("width", [390, 1280])
def test_an_address_with_nothing_at_it_is_a_whole_page(browser, width: int) -> None:
    """A whole page: the desk's top bar stays, then a heading in the reading serif, one
    sentence and one button."""
    context, page, thrown = served(
        browser, not_found_page(), "/nowhere", lambda route, request: json_answer(route, {}), width
    )
    page.wait_for_timeout(200)
    seen = page.evaluate(
        """() => {
          const main = document.querySelector('main.fault-page');
          const go = main.querySelector('.fault-go');
          return {
            bar: !!document.querySelector('header.site-head .site-nav'),
            heading: main.querySelector('h1').textContent,
            serif: getComputedStyle(main.querySelector('h1')).fontFamily.includes('Iowan'),
            said: main.querySelector('p').textContent,
            go: [go.textContent, go.getAttribute('href')],
            presses: main.querySelectorAll('a, button').length,
            sideways: document.documentElement.scrollWidth > window.innerWidth + 1,
          };
        }"""
    )
    context.close()

    assert not thrown, thrown
    assert seen == {
        "bar": True,
        "heading": "We can't find that page",
        "serif": True,
        "said": "There's nothing at this address.",
        "go": ["Go to the library", "/library"],
        "presses": 1,
        "sideways": False,
    }


def test_the_sign_in_doors_are_whole_pages_and_a_refused_address_is_under_its_field(
    browser,
) -> None:
    """The link that has expired and the account being closed are whole pages; an
    address the server would not take is said under the field that holds it."""
    refusal = "We couldn't read that as an email address. Check it and try again."

    def answer(route, request):
        if "/account/sign-in" in request.url:
            json_answer(route, {"error": refusal}, 400)
        else:
            json_answer(route, {})

    context, page, thrown = served(browser, signin_page(), "/account/signin", answer)
    page.fill("#email", "david@targum")
    page.click("#ask button")
    page.wait_for_selector(".fault-under")
    under = page.evaluate(UNDER)
    context.close()
    assert not thrown, thrown
    assert under["said"] == refusal and under["focused"] == "email"
    assert under["outlined"] == "email" and under["invalid"] == "true"

    closing = signin_page(closing=True)
    assert "This account is being closed" in closing
    assert 'class="fault-go" href="mailto:hello@targum.page"' in closing
    assert 'id="ask"' not in closing, "nothing to sign in with: the mail is the way on"
    expired = signin_page(expired=True)
    assert "This link has expired" in expired and 'id="ask"' in expired


def test_a_sign_in_that_took_too_long_is_a_panel_with_sign_in_again() -> None:
    page = signin_page(said="That sign-in took too long.", again="/account/google")
    assert 'class="fault-panel trouble"' in page
    assert '<a class="fault-go" href="/account/google">Sign in again</a>' in page


def test_a_panel_draws_top_up_greyed_until_there_is_somewhere_to_pay(browser) -> None:
    """A panel in place: the sentence, one button and a quiet line. Top up is drawn and
    cannot be pressed, with the reason beside it (§12)."""
    context, page, thrown = served(
        browser, not_found_page(), "/nowhere", lambda route, request: json_answer(route, {})
    )
    page.wait_for_timeout(200)
    drawn = page.evaluate(
        """() => {
          const box = window.TargumFault.panel(
            "You've used this month's credits. Top up, or they reset on 1 November.",
            { topUp: true, fact: "The library still opens" }
          );
          document.querySelector('main').appendChild(box);
          const up = box.querySelector('.fault-go');
          return {
            said: box.querySelector('.fault-panel-said').textContent,
            up: [up.textContent, up.disabled],
            facts: [...box.querySelectorAll('.fault-fact')].map((f) => f.textContent),
            upInk: getComputedStyle(up).color,
          };
        }"""
    )
    context.close()

    assert not thrown, thrown
    assert drawn["up"] == ["Top up", True]
    assert drawn["facts"] == ["Payments open soon", "The library still opens"]
    assert drawn["upInk"] == "rgb(107, 100, 92)", "greyed: ink-soft, not the primary's"


def test_a_refusal_from_a_rail_is_a_panel_in_place_of_the_price(browser) -> None:
    """A panel in place (2026-10-09): what the rail said, its way on and what still
    works, where the price would have been. The server sends the three apart
    (`serve.Refusal`); the sentence no longer recites the quiet line."""

    def answer(route, request):
        if "/prepare" in request.url:
            json_answer(
                route,
                {
                    "id": "j1",
                    "title": "A text",
                    "stage": "blocked",
                    "blocked": "We've hit our limit for today. Try again in 24 hours.",
                    "fact": "Your texts still open",
                    "act": "library",
                },
            )
        else:
            json_answer(route, {})

    context, page, thrown = served(browser, add_page(TOKEN), "/add", answer)
    page.fill("#given", "https://example.com/a")
    page.click("#go")
    page.wait_for_selector("#status .fault-panel")
    drawn = page.evaluate(
        """() => {
          const box = document.querySelector('#status .fault-panel');
          const go = box.querySelector('.fault-go');
          return {
            said: box.querySelector('.fault-panel-said').textContent,
            go: [go.textContent, go.getAttribute('href')],
            fact: box.querySelector('.fault-fact').textContent,
            title: document.querySelector('#status .quote-title').textContent,
          };
        }"""
    )
    context.close()

    assert not thrown, thrown
    assert drawn == {
        "said": "We've hit our limit for today. Try again in 24 hours.",
        "go": ["Open the library", "/library?k=test-key"],
        "fact": "Your texts still open",
        "title": "A text",
    }
