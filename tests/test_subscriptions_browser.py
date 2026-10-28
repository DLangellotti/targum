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
        # Home's own read is a POST since its body carries what is finished (targum#959):
        # answered as a read, and never kept with what the page posts.
        if path == "/suggest":
            return route.fulfill(status=200, content_type="application/json", body="{}")
        if request.method == "POST":
            body = json.loads(request.post_data or "{}")
            posted.append((path, body))
            found = routes.get(("POST", path), {})
            reply = found(body) if callable(found) else found
            # A refusal: (status, body), as the door answers a 409.
            status, reply = reply if isinstance(reply, tuple) else (200, reply)
            return route.fulfill(
                status=status, content_type="application/json", body=json.dumps(reply)
            )
        if isinstance(routes.get(path), tuple):
            # A fault: (status, body), the body an HTML page as a proxy in front sends.
            status, body = routes[path]
            return route.fulfill(status=status, content_type="text/html", body=body)
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
        "68 credits on subscriptions this month · 354 credits left in all, resets on November 1"
    ), got
    assert got["months"][:3] == ["Uses no credits", "38 of 60 credits", "Uses no credits"], got
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


def test_the_library_s_news_opens_the_tab_on_its_topics(browser) -> None:
    """The Library's News says "Follow a topic" and sends the reader here, `?chip=news`,
    with News chosen (2026-10-20). An address naming no chip is All, as before."""
    context = browser.new_context(viewport={"width": 1280, "height": 2000})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    own = {
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
    serve(
        page,
        {
            "/": list_page("", "texts"),
            "/readers": {"readers": [own], "shared": [], "trash": []},
            "/subscriptions.json": {"signedIn": True, "subscriptions": ROWS, "series": SERIES},
        },
        [],
    )
    for asked, kinds, pressed in (
        ("news", ["topic"], "News 1"),
        ("nonsense", ["series", "channel", "topic", "podcast"], "All 4"),
    ):
        page.goto(f"{SITE}/?show=subscriptions&chip={asked}")
        page.wait_for_selector("#subs-rows .sub-row")
        got = page.evaluate(
            """() => ({
              rows: [...document.querySelectorAll('#subs-rows .sub-row')]
                .map((li) => li.dataset.kind),
              pressed: document.querySelector('#subs-chips .chip[aria-pressed="true"]').textContent,
            })"""
        )
        assert got == {"rows": kinds, "pressed": pressed}, got
    context.close()
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
    # Said under the head, where the press was (#475 polish 4).
    page.wait_for_selector(".sub-head-said")
    said = page.text_content(".sub-head-said")
    now = page.eval_on_selector("#sub-cap input:checked", "radio => radio.value")
    context.close()
    assert chosen == "60"
    assert ("/subscriptions/2", {"action": "cap", "cap": 120}) in posted
    assert said == "Saved. The cap is 120 credits a month." and now == "120"
    assert not thrown, thrown


def test_an_unsubscribed_channel_starts_again_only_on_the_confirm_page(browser) -> None:
    """targum-internal#475 B8: Subscribe again on a channel that was unsubscribed goes to
    the confirm page with its old cap, never straight back on in one press (design.md
    §12, "A monthly cap is the second press that lasts"). Off, the page draws no cap and
    no mail, and says when it was unsubscribed."""
    context = browser.new_context(viewport={"width": 1280, "height": 2000})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    posted: list[tuple[str, Any]] = []
    one = dict(
        ROWS[1],
        state="off",
        ended=1_760_000_000_000,
        again="/subscribe?kind=channel&source=https%3A%2F%2Fwww.youtube.com%2Fchannel%2FUC1&cap=60",
        caps=[30, 60, 120, 240],
        items=[],
    )
    answer = {"signedIn": True, "subscription": one, "credits": {"left": 354, "back": "November 1"}}
    serve(
        page,
        {
            "/subscriptions/2": subscription_page(""),
            "/subscriptions/2.json": answer,
            "/subscribe": "<!doctype html><title>confirm</title><p id=confirm>confirm</p>",
        },
        posted,
    )
    page.goto(f"{SITE}/subscriptions/2")
    page.wait_for_selector("#sub-body .sub-head")
    got = page.evaluate(
        """() => ({
          again: [...document.querySelectorAll('.sub-resume')]
            .map((a) => [a.tagName, a.getAttribute('href')]),
          cap: document.querySelectorAll('#sub-cap').length,
          mail: document.querySelectorAll('.sub-mail').length,
          meta: document.querySelector('.sub-meta').textContent,
          none: document.querySelector('.sub-none').textContent,
        })"""
    )
    page.click(".sub-head .sub-resume")
    page.wait_for_selector("#confirm")
    landed = page.url
    context.close()
    assert got["again"] and all(tag == "A" for tag, _ in got["again"]), got
    assert all(href == one["again"] for _, href in got["again"]), got
    assert got["cap"] == 0 and got["mail"] == 0, got
    assert "You unsubscribed on" in got["meta"] and "subscribed since" not in got["meta"], got
    # Off, nothing more comes, so the page promises nothing (#475, qa-claude after #890).
    assert got["none"] == "You're unsubscribed, so nothing new comes here.", got
    assert landed.startswith(f"{SITE}/subscribe?kind=channel&") and "cap=60" in landed
    assert not posted, "nothing was posted: the confirm page is the press"
    assert not thrown, thrown


CONFIRM_AGAIN = "/subscribe?kind=podcast&source=https%3A%2F%2Ffeed.example%2Frss&cap=30"
REFUSED_AGAIN = (
    409,
    {"error": "Choose the monthly cap again to subscribe.", "confirm": CONFIRM_AGAIN},
)


def test_a_resume_the_door_refuses_goes_to_the_confirm_page(browser) -> None:
    """A paused podcast unsubscribed meanwhile, in another tab: Resume meets the door's
    409, which names the confirm page, and the press goes there rather than saying it
    failed (#475, qa-claude after #883). On its own page and on the tab's row alike."""
    context = browser.new_context(viewport={"width": 1280, "height": 2000})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    posted: list[tuple[str, Any]] = []
    one = dict(ROWS[3], caps=[30, 60, 120, 240], items=[])
    answer = {"signedIn": True, "subscription": one, "credits": {"left": 354, "back": "November 1"}}
    routes = {
        "/subscriptions/4": subscription_page(""),
        "/subscriptions/4.json": answer,
        ("POST", "/subscriptions/4"): REFUSED_AGAIN,
        "/subscribe": "<!doctype html><title>confirm</title><p id=confirm>confirm</p>",
        **_tab_routes({"signedIn": True, "subscriptions": ROWS, "series": SERIES}),
    }
    serve(page, routes, posted)
    page.goto(f"{SITE}/subscriptions/4")
    page.click(".sub-head .sub-resume")
    page.wait_for_selector("#confirm")
    assert page.url == f"{SITE}{CONFIRM_AGAIN}", page.url

    page.goto(f"{SITE}/?show=subscriptions")
    page.click('#subs-rows .sub-row[data-kind="podcast"] .sub-resume')
    page.wait_for_selector("#confirm")
    assert page.url == f"{SITE}{CONFIRM_AGAIN}", page.url
    context.close()
    assert posted == [("/subscriptions/4", {"action": "resume"})] * 2, posted
    assert not thrown, thrown


def test_an_unsubscribed_series_comes_back_on_its_one_press(browser) -> None:
    """A series is free, so Subscribe again keeps its one press (#475 B8)."""
    context = browser.new_context(viewport={"width": 1280, "height": 2000})
    page = context.new_page()
    posted: list[tuple[str, Any]] = []
    one = dict(ROWS[0], state="off", ended=1_760_000_000_000, again="", items=[])
    answer = {"signedIn": True, "subscription": one, "credits": {"left": 354, "back": "November 1"}}
    serve(
        page,
        {
            "/subscriptions/1": subscription_page(""),
            "/subscriptions/1.json": answer,
            ("POST", "/subscriptions/1"): {**answer, "subscription": dict(one, state="on")},
        },
        posted,
    )
    page.goto(f"{SITE}/subscriptions/1")
    page.click(".sub-head .sub-resume")
    page.wait_for_selector(".sub-pause")
    context.close()
    assert ("/subscriptions/1", {"action": "resume"}) in posted


def _tab_routes(listed: Any) -> dict[str, Any]:
    return {
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
        "/subscriptions.json": listed,
    }


def test_a_fault_on_the_tab_is_never_told_as_no_subscriptions(browser) -> None:
    """#475 B1: a 502 with an HTML body says it couldn't load, with Try again that loads
    again; it never says "You haven't subscribed to anything yet."; and a 401 says to
    sign in, with Sign in."""
    context = browser.new_context(viewport={"width": 1280, "height": 2000})
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    routes = _tab_routes((502, "<html><body>Bad gateway</body></html>"))
    serve(page, routes, [])
    page.goto(f"{SITE}/?show=subscriptions")
    page.wait_for_selector("#subs-said:not([hidden])")
    said = page.text_content("#subs-said")
    empty_shown = page.eval_on_selector("#subs-empty", "p => !p.hidden")
    routes["/subscriptions.json"] = {
        "signedIn": True,
        "subscriptions": ROWS,
        "series": SERIES,
        "credits": {"left": 354, "back": "November 1"},
    }
    page.click("#subs-said .sub-again")
    page.wait_for_selector("#subs-rows .sub-row")
    gone = page.eval_on_selector("#subs-said", "p => p.hidden")
    context.close()
    assert said and said.startswith("We couldn't load your subscriptions."), said
    assert "Try again" in said and not empty_shown, (said, empty_shown)
    assert gone, "the fault line goes once the list is drawn"
    assert not thrown, thrown

    context = browser.new_context(viewport={"width": 1280, "height": 2000})
    page = context.new_page()
    serve(page, _tab_routes((401, '{"signedIn": false}')), [])
    page.goto(f"{SITE}/?show=subscriptions")
    page.wait_for_selector("#subs-said:not([hidden])")
    said = page.text_content("#subs-said")
    door = page.get_attribute("#subs-said .sub-sign-in", "href")
    empty_shown = page.eval_on_selector("#subs-empty", "p => !p.hidden")
    context.close()
    assert said and said.startswith("Sign in to see your subscriptions."), said
    assert door and door.startswith("/account/signin?next="), door
    assert not empty_shown


def test_a_fault_on_one_subscription_is_never_told_as_gone(browser) -> None:
    """#475 B1: on one subscription's page a 502 says it couldn't load, with Try again;
    only a 404 says we couldn't find it."""
    context = browser.new_context(viewport={"width": 1280, "height": 2000})
    page = context.new_page()
    routes: dict[str, Any] = {
        "/subscriptions/2": subscription_page(""),
        "/subscriptions/2.json": (502, "<html>Bad gateway</html>"),
    }
    serve(page, routes, [])
    page.goto(f"{SITE}/subscriptions/2")
    page.wait_for_selector("#sub-said:not([hidden])")
    said = page.text_content("#sub-said")
    gone = page.eval_on_selector("#gone", "s => !s.hidden")
    routes["/subscriptions/2.json"] = {
        "signedIn": True,
        "subscription": dict(ROWS[1], caps=[30, 60, 120, 240], items=[]),
        "credits": {"left": 354, "back": "November 1"},
    }
    page.click("#sub-said .sub-again")
    page.wait_for_selector("#sub-body .sub-head")
    context.close()
    assert said and said.startswith("We couldn't load this subscription."), said
    assert not gone

    context = browser.new_context(viewport={"width": 1280, "height": 2000})
    page = context.new_page()
    serve(
        page,
        {
            "/subscriptions/2": subscription_page(""),
            "/subscriptions/2.json": (404, '{"error": "not found"}'),
        },
        [],
    )
    page.goto(f"{SITE}/subscriptions/2")
    page.wait_for_selector("#gone:not([hidden])")
    context.close()


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


# --- the finish (targum-internal#475) ---------------------------------------------------


def _tab_page(browser, listed: Any, width: int = 1280, held: bool = False, aborted: bool = False):
    """Home's Subscriptions tab with `/subscriptions.json` answered by `listed`, held with
    no answer, or aborted as a dropped connection."""
    context = browser.new_context(viewport={"width": width, "height": 2000})
    page = context.new_page()
    shelf = {
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
    }
    serve(page, {"/": list_page("", "texts"), "/readers": shelf}, [])
    if held:
        page.route(f"{SITE}/subscriptions.json*", lambda route, request: None)
    elif aborted:
        page.route(f"{SITE}/subscriptions.json*", lambda route, request: route.abort())
    else:
        page.route(
            f"{SITE}/subscriptions.json*",
            lambda route, request: route.fulfill(
                status=200, content_type="application/json", body=json.dumps(listed)
            ),
        )
    return context, page


def test_the_tab_says_it_is_getting_them_and_then_that_it_is_slow(browser) -> None:
    """#475 B2: until the list answered the tab showed only its foot line."""
    context, page = _tab_page(browser, None, held=True)
    page.goto(f"{SITE}/?show=subscriptions")
    page.wait_for_selector("#subs-loading:not([hidden])")
    first = page.text_content("#subs-loading-said")
    page.wait_for_selector("#subs-loading-said .sub-again", timeout=6000)
    slow = page.text_content("#subs-loading-said")
    context.close()
    assert first == "We're getting your subscriptions.", first
    assert slow and slow.startswith("This is taking longer than usual."), slow


def test_one_subscription_says_it_is_getting_it_and_then_that_it_is_slow(browser) -> None:
    """#475 B2: one subscription's page showed nothing under the bar until it answered."""
    context = browser.new_context(viewport={"width": 1280, "height": 1200})
    page = context.new_page()
    serve(page, {"/subscriptions/2": subscription_page("")}, [])
    page.route(f"{SITE}/subscriptions/2.json*", lambda route, request: None)
    page.goto(f"{SITE}/subscriptions/2")
    first = page.text_content("#sub-loading-said")
    visible = page.is_visible("#sub-loading")
    page.wait_for_selector("#sub-loading-said .sub-again", timeout=6000)
    slow = page.text_content("#sub-loading-said")
    context.close()
    assert visible and first == "We're getting this subscription.", first
    assert slow and slow.startswith("This is taking longer than usual."), slow


def test_no_connection_on_the_tab_is_said_once_by_the_band(browser) -> None:
    """#475 polish 1: the band said "We can't reach targum" and the tab said it again."""
    context, page = _tab_page(browser, None, aborted=True)
    page.goto(f"{SITE}/?show=subscriptions")
    page.wait_for_selector("#fault-banner:not([hidden])")
    line_hidden = page.eval_on_selector("#subs-said", "p => p.hidden")
    context.close()
    assert line_hidden, "the band says it; the tab draws no second line"


def test_news_with_no_topic_says_so_with_the_way_to_the_topics(browser) -> None:
    """#475 B3: the Library's "Follow a topic" landed on News 0 with no line and no press.
    Now it says so, and goes to the topics in the Library's News (David, 2026-10-22)."""
    listed = {
        "signedIn": True,
        "subscriptions": [ROWS[0]],
        "series": SERIES,
        "credits": {"left": 354, "back": "November 1"},
    }
    context, page = _tab_page(browser, listed)
    page.goto(f"{SITE}/?show=subscriptions&chip=news")
    page.wait_for_selector(".sub-empty-chip")
    said = page.text_content(".sub-empty-chip")
    go = page.get_attribute(".sub-follow-topic", "href")
    context.close()
    assert said and said.startswith("You don't follow a news topic yet."), said
    assert go == "/library#see/kind/article", go


def test_names_are_marked_in_the_language_they_are_written_in(browser) -> None:
    """#475 B5 and B11: a topic's name ("Sport") and a Latin channel name ("Ivrit Club")
    were marked Hebrew; the chips' counts were text at about 3:1."""
    rows = [
        dict(ROWS[2]),
        dict(ROWS[1], id=5, name="Ivrit Club", page="/subscriptions/5"),
        dict(ROWS[1]),
    ]
    listed = {
        "signedIn": True,
        "subscriptions": rows,
        "series": SERIES,
        "credits": {"left": 354, "back": "November 1"},
    }
    context, page = _tab_page(browser, listed)
    page.goto(f"{SITE}/?show=subscriptions")
    page.wait_for_selector("#subs-rows .sub-row")
    got = page.evaluate(
        """() => ({
          names: [...document.querySelectorAll('#subs-rows .sub-name bdi')]
            .map((b) => [b.textContent, b.getAttribute('lang')]),
          counts: [...document.querySelectorAll('#subs-chips .tab-count')]
            .map((c) => getComputedStyle(c).opacity),
        })"""
    )
    context.close()
    assert got["names"] == [["Sport", None], ["Ivrit Club", None], ["כאן ארכיון", "he"]], got
    assert set(got["counts"]) == {"1"}, got


def _capped_one(**fields: Any) -> dict[str, Any]:
    return dict(
        ROWS[1],
        cap=30,
        used=30,
        caps=[30, 60, 120, 240],
        items=[
            {
                "key": "v3",
                "title": "איך מזמינים קפה",
                "link": "https://youtu.be/v3",
                "reader": "",
                "state": "waiting",
                "why": "cap",
                "came": "",
                "seen": False,
                "found": 6_000,
                "published": 6_000,
                "seconds": 2520,
                "credits": 0,
                "building": False,
            }
        ],
        **fields,
    )


def test_at_the_cap_a_hebrew_title_is_its_own_run_and_a_small_cap_says_so(browser) -> None:
    """#475 B6 and B7: the waiting title was spliced into the sentence as bare text, and a
    cap of 30 against items of about 42 credits said "about 1 video"."""
    context = browser.new_context(viewport={"width": 390, "height": 1600})
    page = context.new_page()
    answer = {
        "signedIn": True,
        "subscription": _capped_one(),
        "credits": {"left": 354, "back": "November 1"},
    }
    serve(page, {"/subscriptions/2": subscription_page(""), "/subscriptions/2.json": answer}, [])
    page.goto(f"{SITE}/subscriptions/2")
    page.wait_for_selector(".sub-capped")
    got = page.evaluate(
        """() => {
          const says = document.querySelector('.sub-capped p');
          return {
            text: says.textContent,
            runs: [...says.querySelectorAll('bdi')]
              .map((b) => [b.textContent, b.getAttribute('lang')]),
            about: [...document.querySelectorAll('#sub-cap .cap-about')]
              .map((a) => [a.textContent, a.className]),
          };
        }"""
    )
    context.close()
    assert got["text"].startswith("You've used this month's 30 credits for "), got
    assert ["איך מזמינים קפה", "he"] in got["runs"] and ["כאן ארכיון", "he"] in got["runs"], got
    assert got["about"][0] == ["less than one new one", "cap-about is-short"], got
    assert got["about"][1][0] == "about 1 video", got


def test_an_article_with_no_picture_takes_no_tile_on_a_phone(browser) -> None:
    """#475 polish 3: every article had the same grey tile, and its press stood centred
    under its title."""
    context = browser.new_context(viewport={"width": 390, "height": 1600})
    page = context.new_page()
    topic = dict(
        ROWS[2],
        caps=[30, 60, 120, 240],
        items=[
            {
                "key": "a1",
                "title": "Новости дня",
                "link": "https://example.ru/a1",
                "reader": "",
                "state": "listed",
                "came": "",
                "seen": False,
                "found": 5_000,
                "published": 5_000,
                "seconds": 0,
                "credits": 0,
                "building": False,
            }
        ],
    )
    answer = {"signedIn": True, "subscription": topic, "credits": {"left": 354, "back": ""}}
    serve(page, {"/subscriptions/3": subscription_page(""), "/subscriptions/3.json": answer}, [])
    page.goto(f"{SITE}/subscriptions/3")
    page.wait_for_selector(".sub-item")
    got = page.evaluate(
        """() => {
          const row = document.querySelector('.sub-item').getBoundingClientRect();
          const act = document.querySelector('.sub-item .sub-act').getBoundingClientRect();
          return {
            tile: getComputedStyle(document.querySelector('.sub-item-pic')).display,
            endGap: row.right - act.right,
            sameLine: act.top
              < document.querySelector('.sub-item-title').getBoundingClientRect().bottom,
          };
        }"""
    )
    context.close()
    assert got["tile"] == "none", got
    assert got["endGap"] < 2 and got["sameLine"], got


def test_the_confirm_page_s_mosaic_fills_its_tile(browser) -> None:
    """#475 B10: a channel's tile was four flat strips, its rows collapsed to a glyph's
    height."""
    from targum.render.builder import subscribe_page

    channel = {
        "kind": "channel",
        "key": "UC1",
        "name": "Ivrit Club",
        "hebrew": "",
        "what": "",
        "language": "he",
        "source": "https://www.youtube.com/channel/UC1",
        "perWeek": 2.0,
        "seconds": 480.0,
        "creditsEach": 8,
        "builds": True,
        "outlets": 0,
        "before": [],
    }
    context = browser.new_context(viewport={"width": 1280, "height": 1200})
    page = context.new_page()
    serve(page, {"/subscribe": subscribe_page(channel)}, [])
    page.goto(f"{SITE}/subscribe")
    page.wait_for_selector(".sub-confirm-tile.is-mosaic")
    got = page.evaluate(
        """() => {
          const mosaic = document.querySelector('.sub-confirm-tile.is-mosaic');
          const tile = mosaic.getBoundingClientRect();
          const cell = mosaic.querySelector('span').getBoundingClientRect();
          return { tile: tile.height, cell: cell.height };
        }"""
    )
    context.close()
    assert got["cell"] >= got["tile"] / 2 - 2, got
