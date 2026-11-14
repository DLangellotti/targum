"""Your Progress keeps a failed sync apart from an empty account (targum-internal#726).

`/account/me` answers and `/sync` fails: the page treated the answered account as an
empty one and drew "Your progress starts with the first word you mark", the same fault
#725 fixed on Your Words. Now, with nothing on this device, the page's fault panel says it
could not load, with Try again; with words on this device, the page is drawn from them
under a line saying so, with Try again; offline the line says offline. Any answered sync
later takes the line or the panel away. A failed pull writes nothing.

The page is the one the server renders; the account's answers are routes. Skips itself
without Playwright and its Chromium.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from test_progress_states_browser import story

from targum.render.builder import progress_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://progress.test"
EMAIL = "r@x.test"
ME = {
    "signedIn": True,
    "email": EMAIL,
    "initials": "R",
    "readsSaid": True,
    "reads": ["en"],
    "language": "he",
    "learning": ["he"],
    "interest": ["news"],
}
MARK = {"email": EMAIL, "revision": 1, "pushed": 1}


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


def ledger(count: int) -> dict[str, Any]:
    """A Hebrew ledger of `count` words, as this browser keeps it."""
    letters = "אבגדהוזחטיכלמנסעפצקרשת"
    return {
        letters[n % 22] + letters[n // 22 % 22]: {
            "status": 1 + n % 3,
            "at": 1_760_000_000_000 - n,
            "seen": 1,
        }
        for n in range(count)
    }


def open_page(browser, answers: dict[str, Any], *, kept: dict | None = None, offline=False):
    """Progress, with `answers` by path: a dict is JSON, an int a bare status and "abort"
    a dropped connection."""
    html = progress_page("", "en")
    defaults: dict[str, Any] = {
        "/account/me": ME,
        "/account/story": story(bool(kept)),
        "/account/totals": {"signedIn": True, "on": True, "totals": []},
        "/account/reading": {"signedIn": True, "reading": {}},
    }

    def answer(route, request):
        path = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        said = answers.get(path, defaults.get(path, {"signedIn": True}))
        if said == "abort":
            return route.abort("internetdisconnected")
        if isinstance(said, int):
            return route.fulfill(status=said, content_type="application/json", body="{}")
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps(said, ensure_ascii=False)
        )

    context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    script = (
        "localStorage.setItem('targum:welcomed', '1');"
        "localStorage.setItem('targum:language', 'he');"
        "localStorage.setItem('targum:learning', '[\"he\"]');"
    )
    if kept is not None:
        script += (
            f"localStorage.setItem('targum:sync', {json.dumps(json.dumps(MARK))});"
            f"localStorage.setItem('targum:vocab:he', "
            f"{json.dumps(json.dumps(kept, ensure_ascii=False))});"
        )
    if offline:
        script += "Object.defineProperty(Navigator.prototype, 'onLine', {get: () => false});"
    context.add_init_script(script)
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    return context, page, thrown


# -- nothing on this device -----------------------------------------------------------


def test_a_failed_sync_with_nothing_here_says_it_could_not_load(browser) -> None:
    context, page, thrown = open_page(browser, {"/sync": 500})
    try:
        page.goto(SITE + "/progress")
        fault = page.locator("#progress-fault")
        fault.wait_for(state="visible", timeout=10_000)
        assert page.locator("#progress-fault-lede").inner_text() == (
            "We couldn't load your progress."
        )
        assert page.locator("#progress-fault-again").is_visible()
        page.wait_for_load_state("networkidle")
        assert page.locator("#nothing").is_hidden()
        assert "first word you mark" not in page.inner_text("body")
        assert page.evaluate("window.TargumSync.pulled") is False
        assert page.evaluate("localStorage.getItem('targum:vocab:he')") is None
        assert not thrown, thrown
    finally:
        context.close()


def test_a_later_answered_sync_takes_the_panel_away(browser) -> None:
    answers: dict[str, Any] = {"/sync": 500}
    context, page, thrown = open_page(browser, answers)
    try:
        page.goto(SITE + "/progress")
        fault = page.locator("#progress-fault")
        fault.wait_for(state="visible", timeout=10_000)
        answers["/sync"] = {"revision": 2, "words": []}
        page.evaluate("window.TargumSync.flush()")
        fault.wait_for(state="hidden")
        # Answered and empty: now it is known to be, and said as that.
        page.get_by_text("first word you mark", exact=False).wait_for(state="visible")
        assert not thrown, thrown
    finally:
        context.close()


# -- words on this device -------------------------------------------------------------


@pytest.mark.parametrize(
    ("answers", "offline"),
    [({"/sync": 500}, False), ({"/sync": "abort"}, False), ({"/account/me": "abort"}, True)],
    ids=["refused", "dropped", "offline"],
)
def test_a_failed_sync_draws_the_progress_saved_here(browser, answers, offline) -> None:
    kept = ledger(5)
    context, page, thrown = open_page(browser, dict(answers), kept=kept, offline=offline)
    try:
        page.goto(SITE + "/progress")
        stale = page.locator("#progress-stale")
        stale.wait_for(state="visible", timeout=10_000)
        said = stale.inner_text()
        assert ("You're offline." in said) if offline else ("couldn't load your latest" in said)
        assert "saved on this device" in said
        assert stale.locator("button.fault-act").inner_text() == "Try again"
        assert page.locator("#page").is_visible()
        assert page.locator("#counts .count-saved b").inner_text() == "5"
        assert page.locator("#nothing").is_hidden()
        assert page.locator("#progress-fault").is_hidden()
        # Nothing of the reader's was touched by the failure.
        assert json.loads(page.evaluate("localStorage.getItem('targum:vocab:he')")) == kept
        assert json.loads(page.evaluate("localStorage.getItem('targum:sync')")) == MARK
        assert not thrown, thrown
    finally:
        context.close()


def test_try_again_asks_in_place_and_takes_the_line_away(browser) -> None:
    answers: dict[str, Any] = {"/sync": 500}
    context, page, thrown = open_page(browser, answers, kept=ledger(3))
    try:
        page.goto(SITE + "/progress")
        stale = page.locator("#progress-stale")
        stale.wait_for(state="visible", timeout=10_000)
        answers["/sync"] = {"revision": 2, "words": []}
        stale.locator("button.fault-act").click()
        stale.wait_for(state="hidden")
        assert page.locator("#counts .count-saved b").inner_text() == "3"
        assert not thrown, thrown
    finally:
        context.close()


def test_any_answered_sync_later_takes_the_line_away(browser) -> None:
    answers: dict[str, Any] = {"/sync": 500}
    context, page, thrown = open_page(browser, answers, kept=ledger(3))
    try:
        page.goto(SITE + "/progress")
        stale = page.locator("#progress-stale")
        stale.wait_for(state="visible", timeout=10_000)
        answers["/sync"] = {"revision": 2, "words": []}
        page.evaluate("window.TargumSync.flush()")
        stale.wait_for(state="hidden")
        assert page.evaluate("window.TargumSync.pulled") is True
        assert not thrown, thrown
    finally:
        context.close()


def test_a_sync_that_answers_draws_no_line(browser) -> None:
    context, page, thrown = open_page(
        browser, {"/sync": {"revision": 2, "words": []}}, kept=ledger(3)
    )
    try:
        page.goto(SITE + "/progress")
        page.locator("#page").wait_for(state="visible", timeout=10_000)
        page.wait_for_load_state("networkidle")
        assert page.locator("#progress-stale").is_hidden()
        assert not thrown, thrown
    finally:
        context.close()
