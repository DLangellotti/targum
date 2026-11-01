"""Home's one card and More that fit you, in a real browser (targum-internal#615; design.md
§12, "Home's one card finds what fits you", 2026-11-01).

Behind `TARGUM_FIND_BUTTON`. The page is the one the server renders (`list_page`), the
server's answers are routes, and each test runs at 390 and at 1440. Skips itself without
Playwright and its Chromium, as the other browser tests do. Where `TARGUM_SHOTS` names a
folder, each state is also saved there as a picture, for David.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

from targum.finds import button
from targum.render.builder import list_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://home.test"
TOKEN = "k"
WIDTHS = [390, 1440]


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


@pytest.fixture(autouse=True)
def on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(button.FLAG, "1")


SHELF_PICK = {
    "id": "hannah",
    "title": "חנה סנש: יומן",
    "language": "he",
    "kind": "novel",
    "register": "modern",
    "minutes": 14,
    "reason": {"key": "suggest.known", "share": 95},
    "fit": "band",
}

MORE = [
    {"id": f"m{n}", "title": title, "language": "he", "kind": kind, "percent": share,
     "reason": {"key": "suggest.known", "share": share}, "fit": "band"}
    for n, (title, kind, share) in enumerate(
        [("בבנק: פתיחת חשבון", "dialogue", 96), ("הנסיך הקטן", "novel", 94),
         ("תל אביב", "article", 93), ("סיפורי חלם", "story", 91)]
    )
]  # fmt: skip

WEB_PICK = {
    "id": "find-7",
    "find": 7,
    "origin": "find",
    "title": "איך מכינים שקשוקה בבית",
    "language": "he",
    "kind": "article",
    "collection": "find:web",
    "host": "www.he.wikibooks.org",
    "minutes": 6,
    "credits": 0,
    "reason": {"key": "suggest.known", "share": 94},
    "fit": "band",
}

CHIPS = [
    {"topic": "cooking", "label": "Cooking", "suggested": True},
    {"topic": "sport", "label": "Sport", "suggested": False},
    {"topic": "football", "label": "Football", "suggested": False},
]


def _row(name: str) -> dict[str, Any]:
    return {
        "name": name, "document": name, "entry": "", "title": "ספר", "language": "he",
        "register": "modern", "kind": "article", "sections": 1, "chapters": [],
        "readyChapters": 0, "built": 100, "drawn": False, "words": 100,
    }  # fmt: skip


Answer = Callable[[dict[str, Any]], Any]


def home(browser, width: int, find: Answer, suggest: Answer | None = None):
    """Home with one text on the shelf; `/find` and `/suggest` answer by `find` and
    `suggest`, each given the posted body. Every body posted to `/find` is kept."""
    html = list_page(TOKEN, "texts")
    posted: list[dict[str, Any]] = []
    went: list[str] = []

    def default_suggest(body: dict[str, Any]) -> Any:
        if body.get("instead_of"):
            return {"suggestion": None}
        return {"suggestion": SHELF_PICK, "library": True, "more": MORE}

    def answer(route, request):
        path = urlparse(request.url).path
        if path.startswith("/reader/") or path.startswith("/open/"):
            went.append(path)
            return route.fulfill(status=200, content_type="text/html", body="<p>elsewhere</p>")
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        body = json.loads(request.post_data or "{}") if request.method == "POST" else {}
        if path == "/readers":
            said: Any = {"readers": [_row("one")], "shared": [], "trash": []}
        elif path == "/account/places":
            return route.fulfill(status=401, content_type="application/json", body="{}")
        elif path == "/account/me":
            said = {"signedIn": False}
        elif path == "/suggest":
            said = (suggest or default_suggest)(body)
        elif path == "/find":
            posted.append(body)
            said = find(body)
        else:
            said = {}
        route.fulfill(status=200, content_type="application/json", body=json.dumps(said))

    phone = width < 640
    context = browser.new_context(
        viewport={"width": width, "height": 900},
        is_mobile=phone,
        has_touch=phone,
        reduced_motion="reduce",
    )
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.add_init_script(
        "sessionStorage.setItem('targum:arrival-over', '1');"
        "localStorage.setItem('targum:language', 'he');"
    )
    page.route(f"{SITE}/**", answer)
    page.goto(f"{SITE}/?k={TOKEN}")
    return context, page, thrown, posted, went


def shot(page, name: str, width: int) -> None:
    where = os.environ.get("TARGUM_SHOTS", "").strip()
    if not where:
        return
    Path(where).mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(Path(where) / f"{name}-{width}-page.png"), full_page=True)
    page.locator(".home-side").screenshot(path=str(Path(where) / f"{name}-{width}-card.png"))


CARD = """() => {
  const q = (s) => document.querySelector(s);
  const text = (s) => (q(s) || {}).textContent || '';
  const seen = (s) => { const e = q(s); return !!e && !e.closest('[hidden]') && e.getBoundingClientRect().height > 0; };
  return {
    label: text('#rc-label'),
    title: text('#try-next .home-card-title'),
    known: text('#try-next .rc-known'),
    facts: text('#try-next .home-card-facts'),
    credits: seen('#try-next .rc-credits'),
    presses: [...document.querySelectorAll('#try-next .rc-presses .btn')].map((b) => b.textContent.trim()),
    open: (q('#try-next .rc-open') || {}).className || '',
    quiet: text('#try-next .rc-quiet'),
    upload: (q('.read-card .rc-foot .btn') || {}).className || '',
    uploadSlab: !!q('.upload-card'),
    more: [...document.querySelectorAll('#more-rows .more-facts')].map((e) => e.textContent),
    moreShown: seen('#more-fit'),
    says: text('#try-next .rc-says'),
    steps: [...document.querySelectorAll('#try-next .rc-steps li')].map((li) => [li.className, li.textContent]),
    sideways: document.documentElement.scrollWidth > window.innerWidth,
    cardAboveShelf: q('.read-card').getBoundingClientRect().top < q('.home-shelf').getBoundingClientRect().top,
  };
}"""  # noqa: E501


@pytest.mark.parametrize("width", WIDTHS)
def test_one_card_draws_the_pick_and_more_that_fit_under_it(browser, width: int) -> None:
    context, page, thrown, _, went = home(browser, width, lambda body: {"pick": None})
    page.wait_for_selector("#try-next .rc-pick")
    page.wait_for_selector("#more-fit:not([hidden])")
    got = page.evaluate(CARD)
    shot(page, "pick", width)
    page.click("#rc-how-press")
    how = page.inner_text("#rc-how")
    shot(page, "how", width)
    page.click("#try-next .rc-open")
    page.wait_for_timeout(300)
    context.close()
    assert not thrown, thrown
    assert got["label"] == "One to try next" and got["title"] == "חנה סנש: יומן"
    assert got["known"] == "95% known" and got["facts"] == "Book · 14 min", got
    assert not got["credits"], "a free pick says nothing of credits"
    assert got["presses"] == ["Read", "Something else", "Topic"], got
    assert "tonal" in got["open"] and "filled" in got["upload"] and not got["uploadSlab"]
    assert got["more"] == ["96% known · Conversation", "94% known · Book", "93% known · Article",
                           "91% known · Story"], got  # fmt: skip
    assert got["moreShown"] and not got["sideways"], got
    assert got["cardAboveShelf"] == (width < 640), "straight after Continue on a phone"
    assert how.startswith("Comprehensible input.") and "90% of the words" in how, how
    assert went == ["/open/hannah"], went


@pytest.mark.parametrize("width", WIDTHS)
def test_something_else_goes_on_to_the_web_step_by_step(browser, width: int) -> None:
    stages = iter(
        [
            {"search": "s1", "stage": "reading", "pages": 6, "left": 2},
            {"search": "s1", "stage": "checking", "pages": 6, "left": 2},
            {"search": "s1", "stage": "done", "pick": WEB_PICK, "left": 2},
        ]
    )

    def find(body: dict[str, Any]) -> Any:
        if body.get("search"):
            return next(stages)
        return {"search": "s1", "stage": "searching", "pages": 0, "left": 2}

    context, page, thrown, posted, _ = home(browser, width, find)
    page.wait_for_selector("#try-next .rc-pick")
    page.click("#try-next .rc-else")
    page.wait_for_selector("#try-next .rc-steps")
    first = page.evaluate(CARD)
    page.wait_for_selector("#try-next li.now:has-text('Reading 6 pages')")
    reading = page.evaluate(CARD)
    shot(page, "web", width)
    page.wait_for_selector("#try-next .rc-pick")
    found = page.evaluate(CARD)
    shot(page, "web-pick", width)
    context.close()
    assert not thrown, thrown
    assert posted[0] == {"language": "he", "skip": []}, posted[0]
    assert first["says"] == "Looking on the web." and first["steps"][0][0] == "now", first
    assert [cls for cls, _ in reading["steps"]] == ["done", "now", ""], reading
    assert reading["steps"][2][1] == "Counting the words you know"
    assert found["facts"] == "6 min · he.wikibooks.org" and found["known"] == "94% known"
    assert found["presses"][0] == "Read" and not found["credits"], found
    assert found["quiet"] == "2 web searches left today", found
    assert not found["sideways"]


@pytest.mark.parametrize("width", WIDTHS)
def test_stop_puts_the_last_pick_back_and_tells_the_server(browser, width: int) -> None:
    def find(body: dict[str, Any]) -> Any:
        if body.get("stop"):
            return {"search": "s2", "stage": "stopped"}
        if body.get("search"):
            return {"search": "s2", "stage": "reading", "pages": 3, "left": 3}
        return {"search": "s2", "stage": "searching", "pages": 0, "left": 3}

    context, page, thrown, posted, _ = home(browser, width, find)
    page.wait_for_selector("#try-next .rc-pick")
    page.click("#try-next .rc-else")
    page.wait_for_selector("#try-next .rc-stop")
    page.click("#try-next .rc-stop")
    page.wait_for_selector("#try-next .rc-pick")
    got = page.evaluate(CARD)
    page.wait_for_timeout(1800)
    context.close()
    assert not thrown, thrown
    assert {"stop": "s2"} in posted, posted
    assert got["title"] == "חנה סנש: יומן" and got["quiet"] == "", got
    assert not any(body.get("search") == "s2" for body in posted[posted.index({"stop": "s2"}) :])


@pytest.mark.parametrize("width", WIDTHS)
def test_a_topic_picks_again_at_once_and_names_the_press(browser, width: int) -> None:
    def find(body: dict[str, Any]) -> Any:
        if body.get("chips"):
            return {"chips": CHIPS}
        if body.get("topics") == ["football"]:
            return {"pick": {**WEB_PICK, "id": "find-9", "find": 9, "title": "מכבי חיפה",
                             "kind": "video", "credits": 11, "host": "youtube.com"}}  # fmt: skip
        return {"pick": None, "why": "off", "message": "We found nothing at your level today."}

    context, page, thrown, posted, _ = home(browser, width, find)
    page.wait_for_selector("#try-next .rc-pick")
    page.click("#try-next .rc-topic")
    page.wait_for_selector("#rc-topics .tab")
    chips = page.evaluate(
        "() => [...document.querySelectorAll('#rc-topics .tab')]"
        ".map((t) => [t.textContent, t.classList.contains('is-likely')])"
    )
    sideways = page.evaluate("() => document.documentElement.scrollWidth > window.innerWidth")
    shot(page, "topics", width)
    page.click("#rc-topics .tab:has-text('Football')")
    page.wait_for_selector("#try-next .home-card-title:has-text('מכבי חיפה')")
    got = page.evaluate(CARD)
    shot(page, "topic-pick", width)
    context.close()
    assert not thrown, thrown
    assert chips == [["Cooking", True], ["Sport", False], ["Football", False]], chips
    assert not sideways
    assert {"language": "he", "skip": [], "topics": ["football"]} in posted, posted
    assert got["presses"] == ["Watch", "Something else", "Football"], got
    assert got["credits"] and got["facts"] == "Video · 6 min · youtube.com", got


@pytest.mark.parametrize("width", WIDTHS)
def test_nothing_fits_and_the_day_s_limit_each_leave_one_press(browser, width: int) -> None:
    capped = "That's today's 3 web searches. More tomorrow."
    answers = iter([{"pick": None, "why": "reader", "message": capped, "left": 0}])
    context, page, thrown, _, _ = home(browser, width, lambda body: next(answers))
    page.wait_for_selector("#try-next .rc-pick")
    page.click("#try-next .rc-else")
    page.wait_for_selector("#try-next .rc-says:has-text('More tomorrow')")
    got = page.evaluate(CARD)
    shot(page, "cap", width)
    context.close()
    assert not thrown, thrown
    assert got["says"] == "That's today's 3 web searches. More tomorrow."
    assert got["presses"] == ["Topic"], got


def test_the_card_is_the_old_one_while_the_switch_is_off(
    browser, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(button.FLAG)
    html = list_page(TOKEN, "texts")
    assert 'data-find="1"' not in html and 'id="read-card"' not in html
    assert 'class="upload-card"' in html
    monkeypatch.setenv(button.FLAG, "1")
    html = list_page(TOKEN, "texts")
    assert 'data-find="1"' in html and 'id="read-card"' in html and "upload-card" not in html
