"""Home's Subscriptions tab and one subscription's page, in a real browser (design.md §12,
"A subscription is the account's, and what it brings comes under Continue", 2026-10-09).

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from targum.render.builder import list_page, subscription_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://targum.test"


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


def _row(**fields: Any) -> dict[str, Any]:
    base = {
        "id": 1,
        "kind": "series",
        "key": "parasha",
        "name": "The weekly portion",
        "hebrew": "פרשת השבוע",
        "page": "/subscriptions/1",
        "language": "he",
        "source": "",
        "state": "on",
        "since": 1_000,
        "paused": 0,
        "every": "week",
        "perWeek": 0,
        "builds": False,
        "cap": 0,
        "used": 0,
        "latest": None,
        "new": 0,
    }
    base.update(fields)
    return base


ROWS = [
    _row(
        latest={
            "key": "noach",
            "title": "נח",
            "reader": "/parasha/read/noach/",
            "state": "ready",
            "came": "",
            "seen": False,
            "link": "",
        },
        new=1,
    ),
    _row(
        id=2,
        kind="channel",
        key="UC1",
        name="כאן ארכיון",
        hebrew="",
        page="/subscriptions/2",
        every="feed",
        perWeek=2.1,
        builds=True,
        cap=60,
        used=38,
        latest={
            "key": "v1",
            "title": "פלאפל או מקדונלדס?",
            "reader": "/reader/v1/reader/index.html",
            "state": "ready",
            "came": "",
            "seen": False,
            "link": "https://youtu.be/v1",
        },
        new=1,
    ),
    _row(
        id=3,
        kind="topic",
        key="sport",
        name="",
        hebrew="",
        page="/subscriptions/3",
        every="feed",
        perWeek=14,
    ),
    _row(
        id=4,
        kind="podcast",
        key="https://feed.example/rss",
        name="A podcast",
        hebrew="",
        page="/subscriptions/4",
        every="feed",
        builds=True,
        cap=30,
        used=30,
        state="paused",
    ),
]
SERIES = [
    {
        "id": "weekly",
        "name": "Weekly News Digest",
        "hebrew": "מבט השבוע",
        "what": "",
        "page": "/weekly",
    },
    {"id": "parasha", "name": "The weekly portion", "hebrew": "", "what": "", "page": "/parasha"},
]


def serve(page, routes: dict[str, Any], posted: list[tuple[str, Any]]) -> None:
    """Answer the page's own asks from `routes`, and keep what it posts."""

    def answer(route, request) -> None:
        path = request.url[len(SITE) :].split("?")[0]
        if request.method == "POST":
            body = json.loads(request.post_data or "{}")
            posted.append((path, body))
            found = routes.get(("POST", path), {})
            reply = found(body) if callable(found) else found
            return route.fulfill(
                status=200, content_type="application/json", body=json.dumps(reply)
            )
        if path in routes and isinstance(routes[path], str):
            return route.fulfill(status=200, content_type="text/html", body=routes[path])
        reply = routes.get(path, {})
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(reply))

    page.route(f"{SITE}/**", answer)
    # Home sends a reader who has answered nothing to the arrival; this one has.
    page.add_init_script("localStorage.setItem('targum:arrived', 'everyday');")


def test_the_tab_draws_every_subscription_in_its_chips(browser, tmp_path: Path) -> None:
    context = browser.new_context(viewport={"width": 1280, "height": 2000})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    posted: list[tuple[str, Any]] = []
    listed = {
        "signedIn": True,
        "subscriptions": ROWS,
        "series": SERIES,
        "credits": {"left": 354, "back": "November 1"},
    }
    serve(
        page,
        {
            "/": list_page("", "texts"),
            # Something on the shelf: a reader with nothing yet is shown no tabs at all.
            "/readers": {
                "readers": [
                    {
                        "name": "own",
                        "document": "own",
                        "title": "כתבה",
                        "language": "he",
                        "entry": "",
                        "built": 1,
                        "minutes": 3,
                        "seconds": 0,
                        "sections": 1,
                        "chapters": [],
                    }
                ],
                "shared": [],
                "trash": [],
            },
            "/subscriptions.json": listed,
            ("POST", "/subscriptions/4"): {"subscription": dict(ROWS[3], state="on")},
            ("POST", "/account/follows"): {"signedIn": True, "follows": ["parasha", "weekly"]},
        },
        posted,
    )
    page.goto(f"{SITE}/?show=subscriptions")
    page.wait_for_selector("#subs-rows .sub-row")
    got = page.evaluate(
        """() => ({
          rows: [...document.querySelectorAll('#subs-rows .sub-row')].map((li) => li.dataset.kind),
          chips: [...document.querySelectorAll('#subs-chips .chip')].map((b) => b.textContent),
          credits: document.getElementById('subs-credits').textContent,
          months: [...document.querySelectorAll('#subs-rows .sub-month')].map((m) => m.textContent),
          every: [...document.querySelectorAll('#subs-rows .sub-every')].map((m) => m.textContent),
          news: document.querySelectorAll('#subs-rows .sub-new').length,
          offered: [...document.querySelectorAll('#subs-offer .sub-offer-row')]
            .map((li) => li.textContent),
          shelf: document.getElementById('shelf-panel').hidden,
          // A row of the table, never a card in the tab's card (design.md §9), and its
          // tile the one tile: the letter on its kind's colour, never a Latin "T" on beige.
          cards: [...document.querySelectorAll('#subs-rows .sub-row, #subs-offer .sub-offer-row')]
            .filter((li) => getComputedStyle(li).boxShadow !== 'none').length,
          tiles: [...document.querySelectorAll('#subs-rows .sub-tile')].map((t) =>
            [...t.classList].find((c) => c.startsWith('tone-'))),
        })"""
    )
    assert got["cards"] == 0, got
    assert got["tiles"] == ["tone-set", "tone-spoken", "tone-news", "tone-spoken"], got
    assert got["rows"] == ["series", "channel", "topic", "podcast"], got
    assert got["chips"] == ["All 4", "Series 1", "News 1", "Channels 1", "Podcasts 1"], got
    assert got["credits"] == (
        "68 credits on subscriptions this month · 354 left in all, resets on November 1"
    ), got
    assert got["months"][:3] == ["No credits", "38 of 60 credits", "No credits"], got
    assert got["months"][3].startswith("Paused"), got
    assert got["every"] == ["Every week", "About 2 a week", "About 14 a week", "As it comes out"]
    assert got["news"] == 2 and got["shelf"], got
    # The series not taken are offered only while the tab is empty (design.md §12, "A
    # subscription's page is two columns, and the tab is a table with its filters").
    assert got["offered"] == [], got

    page.click("#subs-chips .chip:has-text('Channels')")
    assert page.eval_on_selector_all("#subs-rows .sub-row", "rows => rows.length") == 1
    page.click("#subs-chips .chip:has-text('All')")
    page.click("#subs-rows .sub-resume")
    page.wait_for_timeout(200)
    context.close()
    assert ("/subscriptions/4", {"action": "resume"}) in posted
    assert not thrown, thrown


def test_one_subscription_lists_what_it_brought_and_pauses(browser) -> None:
    context = browser.new_context(viewport={"width": 1280, "height": 2000})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    posted: list[tuple[str, Any]] = []
    one = dict(
        ROWS[1],
        caps=[30, 60, 120, 240],
        items=[
            {
                "key": "v2",
                "title": "חדש",
                "link": "https://youtu.be/v2",
                "reader": "",
                "state": "building",
                "came": "",
                "seen": False,
                "found": 5_000,
                "published": 5_000,
                "seconds": 240,
                "credits": 0,
                "why": "",
                "building": True,
            },
            {
                "key": "v1",
                "title": "פלאפל או מקדונלדס?",
                "link": "https://youtu.be/v1",
                "reader": "/reader/v1/reader/index.html",
                "state": "ready",
                "came": "",
                "seen": False,
                "found": 4_000,
                "published": 4_000,
                "seconds": 240,
                "credits": 4,
                "why": "",
                "building": False,
            },
            {
                "key": "v0",
                "title": "ישן",
                "link": "https://youtu.be/v0",
                "reader": "",
                "state": "listed",
                "came": "before",
                "seen": False,
                "found": 900,
                "published": 900,
                "seconds": 660,
                "credits": 0,
                "why": "",
                "building": False,
            },
        ],
    )
    answer = {"signedIn": True, "subscription": one, "credits": {"left": 354, "back": "November 1"}}
    serve(
        page,
        {
            "/subscriptions/2": subscription_page(""),
            "/subscriptions/2.json": answer,
            ("POST", "/subscriptions/2"): {**answer, "subscription": dict(one, state="paused")},
        },
        posted,
    )
    page.goto(f"{SITE}/subscriptions/2")
    page.wait_for_selector("#sub-body .sub-item")
    got = page.evaluate(
        """() => ({
          title: document.getElementById('sub-name').textContent,
          heads: [...document.querySelectorAll('.sub-items h2')].map((h) => h.textContent),
          items: [...document.querySelectorAll('.sub-item')].map((li) => li.textContent),
          doors: [...document.querySelectorAll('.sub-item .sub-act')]
            .map((a) => a.getAttribute('href')),
          cap: document.querySelector('#sub-cap .sub-cap-used').textContent,
        })"""
    )
    assert got["title"] == "כאן ארכיון"
    assert got["heads"] == ["Videos", "Out before you subscribed"], got
    assert "Getting ready" in got["items"][0] and "New" in got["items"][1], got
    assert "Get it ready · about 11 credits" in got["items"][2], got
    assert got["doors"] == [
        "/reader/v1/reader/index.html",
        "/add?source=https%3A%2F%2Fyoutu.be%2Fv0",
    ], got
    assert got["cap"].startswith("38 of 60 credits used in "), got
    page.click(".sub-pause")
    page.wait_for_selector(".sub-resume")
    note = page.text_content(".sub-paused-note")
    context.close()
    assert ("/subscriptions/2", {"action": "pause"}) in posted
    assert note and note.startswith("Paused.")
    assert not thrown, thrown


def test_the_cap_is_changed_on_the_subscriptions_own_page(browser) -> None:
    """design.md §12, "A monthly cap is the second press that lasts": the four caps the
    confirm page offers, the one chosen marked, and Save."""
    context = browser.new_context(viewport={"width": 1280, "height": 2000})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    posted: list[tuple[str, Any]] = []
    one = dict(ROWS[1], caps=[30, 60, 120, 240], items=[])
    answer = {"signedIn": True, "subscription": one, "credits": {"left": 354, "back": "November 1"}}
    serve(
        page,
        {
            "/subscriptions/2": subscription_page(""),
            "/subscriptions/2.json": answer,
            ("POST", "/subscriptions/2"): {**answer, "subscription": dict(one, cap=120)},
        },
        posted,
    )
    page.goto(f"{SITE}/subscriptions/2")
    page.wait_for_selector("#sub-cap .cap-choice")
    chosen = page.eval_on_selector("#sub-cap input:checked", "radio => radio.value")
    page.click("#sub-cap .cap-choice:has-text('120')")
    page.click("#sub-cap button[type=submit]")
    page.wait_for_selector("#sub-said:not([hidden])")
    said = page.text_content("#sub-said")
    now = page.eval_on_selector("#sub-cap input:checked", "radio => radio.value")
    context.close()
    assert chosen == "60"
    assert ("/subscriptions/2", {"action": "cap", "cap": 120}) in posted
    assert said == "Saved. The cap is 120 credits a month." and now == "120"
    assert not thrown, thrown


def test_what_a_subscription_brought_leads_continue_marked_new(browser) -> None:
    """design.md §12, "A subscription is the account's, and what it brings comes under
    Continue": New, named by what it came from, and opening it says so to the account."""
    context = browser.new_context(viewport={"width": 1280, "height": 2000})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    posted: list[tuple[str, Any]] = []
    brought = {
        "signedIn": True,
        "items": [
            {
                "subscription": 2,
                "key": "v1",
                "title": "פלאפל או מקדונלדס?",
                "kind": "channel",
                "name": "כאן ארכיון",
                "topic": "",
                "language": "he",
                "door": "/reader/v1/reader/index.html",
                "seconds": 240,
                "published": 1,
                "found": 1,
            },
            {
                "subscription": 3,
                "key": "a1",
                "title": "הפועל חולון אלופה",
                "kind": "topic",
                "name": "",
                "topic": "sport",
                "language": "he",
                "door": "/add?source=https%3A%2F%2Fone%2Fa1",
                "seconds": 0,
                "published": 1,
                "found": 1,
            },
            {
                "subscription": 4,
                "key": "r1",
                "title": "Новости",
                "kind": "outlet",
                "name": "РБК",
                "topic": "",
                "language": "ru",
                "door": "/add?source=x",
                "seconds": 0,
                "published": 1,
                "found": 1,
            },
        ],
    }
    serve(
        page,
        {
            "/": list_page("", "texts"),
            "/readers": {
                "readers": [
                    {
                        "name": "own",
                        "document": "own",
                        "title": "כתבה",
                        "language": "he",
                        "entry": "",
                        "built": 1,
                        "minutes": 3,
                        "seconds": 0,
                        "sections": 1,
                        "chapters": [],
                    }
                ],
                "shared": [],
                "trash": [],
            },
            "/subscriptions/new.json": brought,
            "/reader/v1/reader/index.html": "<!doctype html><title>reader</title>",
            ("POST", "/subscriptions/seen"): {"seen": True},
        },
        posted,
    )
    page.goto(f"{SITE}/")
    page.wait_for_selector("#continue-cards .home-card.is-new")
    got = page.evaluate(
        """() => [...document.querySelectorAll('#continue-cards .home-card')].map((li) => ({
          tag: li.querySelector('.home-tag').textContent,
          go: li.querySelector('.home-card-go').textContent,
          href: li.querySelector('a').getAttribute('href'),
        }))"""
    )
    assert got[0] == {
        "tag": "New · כאן ארכיון",
        "go": "Watch",
        "href": "/reader/v1/reader/index.html",
    }, got
    assert got[1]["tag"] == "New · Sport" and got[1]["href"].startswith("/add?source="), got
    assert all("РБК" not in card["tag"] for card in got), "a Russian outlet is not Hebrew's"
    page.click("#continue-cards .home-card.is-new a")
    page.wait_for_url(f"{SITE}/reader/v1/reader/index.html")
    context.close()
    assert ("/subscriptions/seen", {"subscription": 2, "key": "v1"}) in posted
    assert not thrown, thrown
