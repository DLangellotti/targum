"""Upload's states, held in a real browser (targum-internal#466, design.md §14).

The finish pass walked Upload on a hosted copy at desk and phone widths. What it fixed is
pinned here: the wait for a build on the card it was priced on (the queue, the stage,
the end, a failure, the rails stopping it, a connection lost), a link pasted without its
scheme, a link that is not one, refusals under the box, the priced card's place on a
phone, the slow line, a voice note, no connection, and the paused page.

Every door that prices or builds is answered here; nothing reaches a server.

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from targum.render.builder import add_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

TOKEN = "test-key"
ORIGIN = "http://upload.test"
READER = "a-text-he/reader/index.html"
QUOTE = {
    "id": "j1",
    "stage": "ready",
    "title": "האישה שצעדה אלפי קילומטרים",
    "language": "he",
    "segments": 48,
    "total": 48,
    "estimate": 0.02,
    "source": "https://www.ynet.co.il/news/article/abc",
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


class Doors:
    """The server, as far as Upload asks it: each door's answer, and what was asked."""

    def __init__(self, html: str, **answers: Any) -> None:
        self.html = html
        self.answers = answers
        self.asked: list[str] = []
        #: What `/job/j1` says, in turn; the last is said again.
        self.jobs: list[dict[str, Any]] = []
        #: Doors that are out of reach.
        self.down: set[str] = set()

    def __call__(self, route, request) -> None:
        path = request.url.split("?")[0][len(ORIGIN) :]
        if path == "/add":
            return route.fulfill(status=200, content_type="text/html", body=self.html)
        self.asked.append(path)
        if any(path.startswith(door) for door in self.down):
            return route.abort()
        if path.startswith("/job/") and self.jobs:
            body: Any = self.jobs.pop(0) if len(self.jobs) > 1 else self.jobs[0]
        else:
            body = next(
                (said for door, said in self.answers.items() if path == door.replace("_", "/")),
                {},
            )
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def opened(browser, doors: Doors, width: int = 1280, phone: bool = False, script: str = ""):
    options: dict[str, Any] = {"viewport": {"width": width, "height": 844 if phone else 900}}
    if phone:
        options.update(is_mobile=True, has_touch=True)
    context = browser.new_context(**options)
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    if script:
        page.add_init_script(script)
    page.route(ORIGIN + "/**", doors)
    page.goto(ORIGIN + "/add")
    # The follow asks every two seconds on a real page; here it asks at once.
    page.evaluate("() => { window.TargumBring.POLL = 30; }")
    return context, page, thrown


def priced_and_confirmed(page) -> None:
    page.fill("#given", QUOTE["source"])
    page.click("#go")
    page.wait_for_selector("#status .confirm")
    page.click("#status .confirm")


def test_the_wait_keeps_the_title_says_the_queue_and_opens_the_reader(browser) -> None:
    doors = Doors(add_page(TOKEN), _prepare=QUOTE, _build={"id": "j1", "stage": "queued"})
    doors.jobs = [
        dict(QUOTE, stage="queued", behind=2, said="It's waiting to start, behind 2 other texts."),
        dict(QUOTE, stage="queued", behind=2, said="It's waiting to start, behind 2 other texts."),
        dict(QUOTE, stage="working", done=24, total=48, said="About a minute left."),
        dict(QUOTE, stage="working", done=24, total=48, said="About a minute left."),
        dict(QUOTE, stage="done", done=48, total=48, reader=READER),
    ]
    context, page, thrown = opened(browser, doors)
    page.evaluate("() => { window.TargumBring.POLL = 400; }")
    priced_and_confirmed(page)
    page.wait_for_selector(".wait-stage:has-text('Waiting behind 2 builds')")
    card = page.inner_text("#status")
    assert QUOTE["title"] in card, "the title stays on the card while it is made"
    assert "behind 2 other texts" in card, "the server's own line is said"
    assert "Your targums" in card, "it says where it will be"
    meter = page.locator("#status .meter.is-building[role=progressbar]")
    assert meter.count() == 1 and meter.get_attribute("aria-label")
    page.wait_for_selector(".wait-stage:has-text('50%')")
    page.wait_for_url("**/reader/**", timeout=8000)
    assert "/reader/a-text-he/reader/index.html" in page.url, page.url
    context.close()
    assert not thrown, thrown


def test_a_build_that_fails_says_so_with_try_again(browser) -> None:
    doors = Doors(add_page(TOKEN), _prepare=QUOTE, _build={"id": "j1", "stage": "queued"})
    failed = "We couldn't get it ready. We couldn't open that page. Nothing was used."
    doors.jobs = [dict(QUOTE, stage="failed", error="We couldn't open that page.", said=failed)]
    context, page, thrown = opened(browser, doors)
    priced_and_confirmed(page)
    page.wait_for_selector("#status .fault-marked")
    assert page.inner_text("#status .fault-marked") == failed
    assert QUOTE["title"] in page.inner_text("#status")
    asked = len(doors.asked)
    page.click("#status .wait .btn:has-text('Try again')")
    page.wait_for_selector("#status .confirm")
    assert doors.asked[asked:].count("/prepare") == 1, "Try again prices again"
    assert "/build" not in doors.asked[asked:], "and spends nothing until Confirm"
    context.close()
    assert not thrown, thrown


def test_a_build_the_rails_stop_is_a_panel_and_is_no_longer_asked_after(browser) -> None:
    doors = Doors(add_page(TOKEN), _prepare=QUOTE, _build={"id": "j1", "stage": "queued"})
    doors.jobs = [
        dict(QUOTE, stage="queued", behind=0),
        dict(
            QUOTE,
            stage="blocked",
            blocked="You've used all your credits this month.",
            fact="The library still opens",
            act="top-up",
        ),
    ]
    context, page, thrown = opened(browser, doors)
    priced_and_confirmed(page)
    page.wait_for_selector("#status .fault-panel")
    asked = doors.asked.count("/job/j1")
    page.wait_for_timeout(600)
    assert doors.asked.count("/job/j1") == asked, "it stopped asking (it asked for ever)"
    context.close()
    assert not thrown, thrown


def test_a_wait_that_loses_the_connection_says_where_it_will_be(browser) -> None:
    doors = Doors(add_page(TOKEN), _prepare=QUOTE, _build={"id": "j1", "stage": "queued"})
    doors.jobs = [dict(QUOTE, stage="queued", behind=1)]
    context, page, thrown = opened(browser, doors)
    page.evaluate("() => { window.TargumBring.POLL = 5; }")
    priced_and_confirmed(page)
    page.wait_for_selector(".wait-stage:has-text('Waiting behind 1 build')")
    doors.down.add("/job/")
    page.wait_for_selector(".wait-stage:has-text('still being made')", timeout=8000)
    assert page.locator("#status a.btn:has-text('Your targums')").count() == 1
    context.close()
    assert not thrown, "a dropped connection threw on every ask: " + "; ".join(thrown)


def test_a_link_without_its_scheme_is_priced_as_a_link(browser) -> None:
    doors = Doors(add_page(TOKEN), _prepare=QUOTE)
    context, page, thrown = opened(browser, doors)
    page.fill("#given", "www.ynet.co.il/news/article/abc")
    assert "Thanks for the link" in page.inner_text("#understood")
    page.click("#go")
    page.wait_for_selector("#status .confirm")
    assert "/chat/say" not in doors.asked, "it was looked for as a request, a turn of chat"
    sent = [r for r in doors.asked if r == "/prepare"]
    assert sent
    context.close()
    assert not thrown, thrown


@pytest.mark.parametrize(
    ("typed", "said"),
    [
        ("htps//ynet.co.il/article", "That isn't a whole link."),
        ("", "Paste a link or some Hebrew, or drop a file."),
    ],
)
def test_what_cannot_be_priced_is_refused_under_the_box(browser, typed: str, said: str) -> None:
    doors = Doors(add_page(TOKEN))
    context, page, thrown = opened(browser, doors)
    page.fill("#given", typed)
    page.click("#go")
    page.wait_for_selector(".fault-under")
    assert page.inner_text(".fault-under").startswith(said)
    assert page.is_hidden("#status"), "said under the box, not on the card at the right"
    assert not {"/chat/say", "/prepare"} & set(doors.asked)
    context.close()
    assert not thrown, thrown


def test_a_refusal_puts_the_promise_under_the_box_away(browser) -> None:
    doors = Doors(add_page(TOKEN), _prepare={"error": "We couldn't open that page."})
    context, page, thrown = opened(browser, doors)
    page.fill("#given", QUOTE["source"])
    assert "work out how long" in page.inner_text("#understood")
    page.click("#go")
    page.wait_for_selector(".fault-under")
    assert page.is_hidden("#understood"), "it still said it was working out how long"
    page.fill("#given", QUOTE["source"] + "?again")
    assert page.is_visible("#understood")
    context.close()
    assert not thrown, thrown


def test_on_a_phone_the_priced_card_comes_before_what_works(browser) -> None:
    doors = Doors(add_page(TOKEN), _prepare=QUOTE)
    context, page, thrown = opened(browser, doors, width=390, phone=True)
    page.fill("#given", QUOTE["source"])
    page.click("#go")
    page.wait_for_selector("#status .confirm")
    page.wait_for_timeout(900)
    where = page.evaluate(
        """() => ({
          card: document.getElementById('status').getBoundingClientRect().top,
          box: document.getElementById('bring-box').getBoundingClientRect().bottom,
          works: document.querySelector('.works').getBoundingClientRect().top,
          confirm: document.querySelector('#status .confirm').getBoundingClientRect().bottom,
          from: document.getElementById('from').getBoundingClientRect().height,
          height: innerHeight,
        })"""
    )
    assert where["box"] <= where["card"] < where["works"], where
    assert where["confirm"] <= where["height"], "Confirm is scrolled into view"
    assert where["from"] >= 44, "the language's select answers a thumb"
    context.close()
    assert not thrown, thrown


def test_a_wait_past_three_seconds_says_it_is_still_going(browser) -> None:
    doors = Doors(add_page(TOKEN))

    def held(route, request):
        if request.url.split("?")[0].endswith("/prepare"):
            return  # never answered
        doors(route, request)

    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.route(ORIGIN + "/**", held)
    page.goto(ORIGIN + "/add")
    page.fill("#given", QUOTE["source"])
    page.click("#go")
    page.wait_for_timeout(1200)
    assert "Still working" not in page.inner_text("#status")
    page.wait_for_selector("#status :text('Still working')", timeout=4000)
    context.close()


def test_a_voice_note_is_thanked_as_a_recording(browser) -> None:
    """Chrome records into webm, which is a film's container too."""
    fake = """
      (() => {
        const fake = {
          can: true,
          recording: () => false,
          toggle: (button, done) => {
            setTimeout(() => done(new Blob(['x'], { type: 'audio/webm;codecs=opus' })), 50);
            return true;
          },
        };
        Object.defineProperty(window, 'TargumSpeak', { get: () => fake, set: () => {} });
      })();
    """
    doors = Doors(add_page(TOKEN))
    context, page, thrown = opened(browser, doors, script=fake)
    page.click("#record")
    page.wait_for_selector("#given-files .given-file")
    assert page.inner_text("#understood").startswith("Thanks for the recording.")
    assert "Recorded just now" in page.inner_text("#given-files")
    context.close()
    assert not thrown, thrown


def test_with_no_connection_upload_is_greyed_and_says_why(browser) -> None:
    doors = Doors(add_page(TOKEN))
    context, page, thrown = opened(browser, doors)
    context.set_offline(True)
    page.evaluate("() => window.dispatchEvent(new Event('offline'))")
    page.wait_for_selector("#go.offline-off")
    assert page.get_attribute("#go", "aria-disabled") == "true"
    assert page.inner_text("#understood") == "Uploading needs the connection."
    context.set_offline(False)
    page.evaluate("() => window.dispatchEvent(new Event('online'))")
    page.wait_for_function("() => document.getElementById('understood').innerText === ''")
    context.close()


def test_the_paused_page_says_nothing_new_once(browser) -> None:
    notice = "We can't get anything new ready right now."
    doors = Doors(add_page(TOKEN, no_key=notice))
    context, page, thrown = opened(browser, doors)
    text = page.inner_text("main")
    assert text.count(notice) == 1, "the notice and the line under the box said it twice"
    assert page.inner_text("#understood") == "Everything you have still opens."
    context.close()
    assert not thrown, thrown
