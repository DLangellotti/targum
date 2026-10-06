"""The bell, opened on a build that is getting ready (David, 2026-10-06: "I want to be able
to click on one that is getting ready and see the status live").

`building.js` in a real browser, against stand-in `/jobs` and `/job/<id>` answers that the
test moves along: the row is a button that opens the build's status in place, the status
is followed while it is open and in view and at no other time, a finished build turns back
into the done row with its Open, a failed one says why, and every title in the bell is an
isolate that cannot be broken among the English around it.

Skips itself unless Playwright and its Chromium are installed:

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from targum.render.builder import learn_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

TOKEN = "test-key"
TITLE = "קילימנג'רו יום 4 | היום הכי קשה בטיפוס עד עכשיו"


@pytest.fixture(scope="module")
def browser():
    try:
        driver = playwright_api.sync_playwright().start()
    except Exception as why:  # pragma: no cover - environment, not behaviour
        pytest.skip(f"Playwright will not start: {why}")
    try:
        chromium = driver.chromium.launch()
    except Exception as why:  # pragma: no cover - environment, not behaviour
        driver.stop()
        pytest.skip(f"Chromium is not installed: {why}")
    yield chromium
    chromium.close()
    driver.stop()


class Box:
    """The server's side: jobs the test moves along, and every `/job/<id>` asked."""

    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {
            "run": {
                "id": "run",
                "title": TITLE,
                "language": "he",
                "stage": "working",
                "done": 30,
                "total": 80,
                "message": "",
                "said": "30 of 80 sentences ready, about 2 minutes left.",
                "seconds_left": 100,
                "behind": 0,
                "mail": False,
            },
            "old": {
                "id": "old",
                "title": "שיר השירים",
                "language": "he",
                "stage": "done",
                "reader": "song-he/reader/index.html",
                "said": "It's ready to read.",
                "behind": 0,
                "mail": False,
            },
        }
        self.asked: list[str] = []
        self.html = learn_page(TOKEN)

    def answer(self, route: Any, request: Any) -> None:
        url = request.url
        if request.resource_type == "document":
            route.fulfill(status=200, content_type="text/html", body=self.html)
            return
        path = url.split("learn.test", 1)[1].split("?", 1)[0]
        if path == "/jobs":
            body: Any = {"jobs": list(self.jobs.values())}
        elif path.startswith("/job/"):
            self.asked.append(path)
            body = dict(self.jobs[path[len("/job/") :]])
            body.pop("mail", None)
        elif path == "/chat/list":
            body = {"chats": [{"id": "c1", "title": "שיחה על הטיפוס", "answered": 5, "opened": 1}]}
        elif path == "/account/me":
            body = {"signedIn": True, "email": "d@x.test", "initials": "DJ"}
        else:
            body = {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


def opened_page(browser: Any, box: Box) -> Any:
    context = browser.new_context(viewport={"width": 1100, "height": 800})
    page = context.new_page()
    page.route("http://learn.test/**", box.answer)
    page.goto(f"http://learn.test/learn?k={TOKEN}")
    page.wait_for_selector("#notices-count:not([hidden])")
    page.click("#notices-open")
    page.wait_for_selector("li[data-id='job:run'] .notices-row")
    return page


def asked_in(page: Any, box: Box, seconds: float) -> int:
    before = len(box.asked)
    page.wait_for_timeout(int(seconds * 1000))
    return len(box.asked) - before


def seen(page: Any, state: str) -> None:
    """The tab put out of view, or back, as the browser would say it."""
    page.evaluate(
        """(state) => {
          Object.defineProperty(document, 'visibilityState', {
            configurable: true, get: () => state,
          });
          document.dispatchEvent(new Event('visibilitychange'));
        }""",
        state,
    )


def test_every_title_in_the_bell_is_an_isolate_drawn_whole(browser) -> None:
    """The line broke inside a Hebrew title and read as scrambled (2026-10-06)."""
    box = Box()
    page = opened_page(browser, box)
    page.wait_for_selector("li[data-id^='chat:'] bdi")
    got = page.evaluate(
        """() => [...document.querySelectorAll('#notices-list li')].map((li) => {
          const b = li.querySelector('bdi.notices-title');
          return {
            id: li.getAttribute('data-id'),
            text: b && b.textContent,
            lang: b && b.lang,
            display: b && getComputedStyle(b).display,
            isolates: /[\\u2068\\u2069]/.test(li.textContent),
          };
        })"""
    )
    page.context.close()
    rows = {row["id"]: row for row in got}
    assert rows["job:run"]["text"] == TITLE, "the build that is getting ready"
    assert rows["job:old"]["text"] == "שיר השירים", "the build that is done"
    assert rows["chat:c1:5"]["text"] == "שיחה על הטיפוס", "a reply in a chat"
    for row in got:
        assert row["lang"] == "he" and row["display"] == "inline-block", row
        assert not row["isolates"], "an element, not the characters"


def test_a_build_getting_ready_opens_in_place_and_is_followed_while_open(browser) -> None:
    box = Box()
    page = opened_page(browser, box)
    row = page.locator("li[data-id='job:run'] .notices-row")
    assert row.get_attribute("aria-expanded") == "false"
    assert page.locator("li[data-id='job:old'] .notices-row").count() == 0, "done: no toggle"
    assert asked_in(page, box, 2.5) == 0, "nothing is followed until a build is opened"

    row.click()
    page.wait_for_selector("#notices-status-run .notices-bar")
    got = page.evaluate(
        """() => {
          const box = document.getElementById('notices-status-run');
          const bar = box.querySelector('[role=progressbar]');
          return {
            expanded: document.querySelector("li[data-id='job:run'] .notices-row")
              .getAttribute('aria-expanded'),
            controls: document.querySelector("li[data-id='job:run'] .notices-row")
              .getAttribute('aria-controls'),
            stage: box.querySelector('.notices-stage').textContent,
            now: bar.getAttribute('aria-valuenow'),
            max: bar.getAttribute('aria-valuemax'),
            width: bar.firstChild.style.inlineSize,
            said: box.querySelector('.notices-said').textContent,
          };
        }"""
    )
    assert got == {
        "expanded": "true",
        "controls": "notices-status-run",
        "stage": "Translating",
        "now": "30",
        "max": "80",
        "width": "38%",
        "said": "30 of 80 sentences ready, about 2 minutes left.",
    }
    assert asked_in(page, box, 4.5) >= 2, "followed every two seconds while open"

    # It moves, in place: the same status element, a new width and a new line.
    page.evaluate("() => { window.kept = document.getElementById('notices-status-run'); }")
    box.jobs["run"].update(done=60, said="60 of 80 sentences ready, less than a minute left.")
    page.wait_for_function(
        "() => document.querySelector('#notices-status-run .notices-said').textContent"
        ".startsWith('60 of 80')"
    )
    assert page.evaluate(
        "() => window.kept === document.getElementById('notices-status-run')"
        " && window.kept.querySelector('.notices-bar > span').style.inlineSize === '75%'"
    )

    # Collapsed with the keyboard, followed no more; Space opens it again.
    row.focus()
    page.keyboard.press("Enter")
    assert row.get_attribute("aria-expanded") == "false"
    assert page.locator("#notices-status-run").count() == 0
    page.wait_for_timeout(300)
    assert asked_in(page, box, 2.5) == 0, "collapsed: not followed"
    page.keyboard.press("Space")
    page.wait_for_selector("#notices-status-run")
    assert asked_in(page, box, 2.5) >= 1

    # The panel closed, then the tab out of view: not followed either time.
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert asked_in(page, box, 2.5) == 0, "panel closed: not followed"
    page.click("#notices-open")
    page.wait_for_selector("#notices-status-run")
    assert asked_in(page, box, 2.5) >= 1, "open again: followed again"
    seen(page, "hidden")
    page.wait_for_timeout(300)
    assert asked_in(page, box, 2.5) == 0, "tab hidden: not followed"
    seen(page, "visible")
    assert asked_in(page, box, 2.5) >= 1

    # It finishes: the done row with its Open, the keyboard on that Open, and no more asking.
    page.locator("li[data-id='job:run'] .notices-row").focus()
    box.jobs["run"].update(
        stage="done", done=80, reader="kili-he/reader/index.html", said="It's ready to read."
    )
    box.jobs["run"].pop("seconds_left")
    page.wait_for_selector("li[data-id='job:run'] a")
    done = page.evaluate(
        """() => {
          const li = document.querySelector("li[data-id='job:run']");
          return {
            toggle: !!li.querySelector('.notices-row'),
            status: !!li.querySelector('.notices-status'),
            open: li.querySelector('a').textContent,
            href: li.querySelector('a').getAttribute('href'),
            focused: document.activeElement === li.querySelector('a'),
            line: li.querySelector('span').textContent,
          };
        }"""
    )
    assert done == {
        "toggle": False,
        "status": False,
        "open": "Open",
        "href": "/reader/kili-he/reader/index.html?k=test-key",
        "focused": True,
        "line": f"{TITLE} is ready.",
    }
    page.wait_for_timeout(300)
    assert asked_in(page, box, 2.5) == 0, "done: not followed"
    page.context.close()


def test_a_build_that_fails_while_open_says_why_and_stops(browser) -> None:
    box = Box()
    page = opened_page(browser, box)
    page.click("li[data-id='job:run'] .notices-row")
    page.wait_for_selector("#notices-status-run .notices-bar")
    box.jobs["run"].update(
        stage="failed",
        error="That page has no Hebrew on it. Try another link.",
        said="We couldn't get it ready. That page has no Hebrew on it. Try another link. "
        "Nothing was used.",
    )
    box.jobs["run"].pop("seconds_left")
    page.wait_for_function("() => !document.querySelector('#notices-status-run .notices-bar')")
    got = page.evaluate(
        """() => {
          const li = document.querySelector("li[data-id='job:run']");
          return {
            said: li.querySelector('.notices-status').textContent,
            line: li.querySelector('.notices-row span').textContent,
          };
        }"""
    )
    assert got["said"].startswith("We couldn't get it ready. That page has no Hebrew"), got
    assert got["said"].endswith("Nothing was used."), got
    assert got["line"] == f"{TITLE}: That page has no Hebrew on it. Try another link.", got
    page.wait_for_timeout(300)
    assert asked_in(page, box, 2.5) == 0, "failed: not followed"
    page.context.close()
