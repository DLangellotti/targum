"""Your Progress draws every state of design.md §14.1 at both widths (targum-internal#471).

Signed out, empty, a reader with a lot (5,000 words, 500 texts, 200 days), the story
failing, and offline: each loads the page the server renders, with the account's answers
stubbed, at 1440 and at 390 as a touch phone. Each must say what to do next, never scroll
sideways, and throw nothing. The loading line and the failed story's Try again are pinned
in `test_progress_js.py`, and the longest time figures at 390 and 320 in
`test_progress_narrow_browser.py`; this is the rest of §14.8 for this surface.

Skips itself without Playwright.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

import pytest

from targum.render.builder import progress_page

pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://progress.test"
NOW = 1_792_000_000_000
DAY = 86_400_000
TODAY = datetime.date(2026, 10, 28)

LADDER = [
    {"kind": "A1", "name": "A1", "state": "easy", "texts": 120, "readable": 118},
    {"kind": "A2", "name": "A2", "state": "easy", "texts": 150, "readable": 143},
    {"kind": "B1", "name": "B1", "state": "next", "texts": 90, "readable": 12},
    {"kind": "B2+", "name": "B2+", "state": "ahead", "texts": 45, "readable": 0},
]


def me(signed: bool) -> dict[str, Any]:
    if not signed:
        return {"signedIn": False}
    return {
        "signedIn": True,
        "email": "r@x.test",
        "initials": "R",
        "readsSaid": True,
        "reads": ["en"],
        "language": "he",
        "learning": ["he"],
        "interest": ["news"],
    }


def record(words: int, texts: int, days: int) -> dict[str, Any]:
    """What /sync hands back: a word list, the texts opened and the days read."""
    return {
        "revision": 3,
        "words": [
            {
                "language": "he",
                "lemma": f"מלה{n}",
                "status": 2 + n % 3,
                "surface": f"מלה{n}",
                "band": 1,
                "learned": 0,
                "at": NOW - (n % 120) * DAY,
                "seen": NOW,
                "gone": 0,
            }
            for n in range(words)
        ],
        "docs": [
            {
                "hash": f"h{n}",
                "title": f"Text {n}",
                "language": "he",
                "opened": NOW - (n % 90) * DAY,
                "done": NOW - (n % 90) * DAY if n % 2 else 0,
                "seen": NOW,
                "gone": 0,
            }
            for n in range(texts)
        ],
        "days": [
            {"day": (TODAY - datetime.timedelta(days=n)).isoformat(), "count": 1}
            for n in range(days)
        ],
    }


def story(full: bool) -> dict[str, Any]:
    if not full:
        return {
            "signedIn": True,
            "library": True,
            "known": 0,
            "ladder": [
                dict(rung, share=None, state="next" if at == 0 else "ahead", readable=0)
                for at, rung in enumerate(LADDER)
            ],
            "here": None,
            "next": 0,
            "level": None,
            "texts": [],
            "words": [],
        }
    return {
        "signedIn": True,
        "library": True,
        "known": 1700,
        "ladder": LADDER,
        "here": 1,
        "next": 2,
        "level": {
            "scale": "ulpan",
            "letter": "ב",
            "name": "bet",
            "cefr": "A2",
            "next": {"letter": "ב+", "name": "bet plus"},
            "toward": 0.4,
        },
        "texts": [
            {
                "id": "jonah",
                "title": "יונה",
                "english": "Jonah",
                "author": "",
                "kind": "prose",
                "known": 91,
            },
        ],
        "words": [{"lemma": "מלה1", "texts": 4}, {"lemma": "מלה4", "texts": 2}],
    }


#: What each state must say: the line that tells the reader what to do next. Signed out
#: and empty are the same card: a signed-out reader's words live in the browser, so
#: Progress works without an account, and the bar's Sign in is beside it.
FIRST_WORD = "Your progress starts with the first word you mark in a text."
STATES: dict[str, dict[str, Any]] = {
    "signed-out": {"signed": False, "says": FIRST_WORD, "press": "Open the Library"},
    "empty": {"signed": True, "says": FIRST_WORD, "press": "Open the Library"},
    "lot": {"signed": True, "words": 5000, "texts": 500, "days": 200, "says": "5,000"},
    "failed": {
        "signed": True,
        "words": 40,
        "texts": 6,
        "days": 9,
        "fail": True,
        "says": "We couldn't load this part.",
        "press": "Try again",
    },
    "offline": {"signed": True, "offline": True, "says": "You're offline."},
}


def open_state(chromium: Any, spec: dict[str, Any], width: int) -> tuple[Any, Any, list[str]]:
    interface = spec.get("interface", "en")
    html = progress_page("", interface)
    signed = spec["signed"]
    words = spec.get("words", 0)
    answers: dict[str, Any] = {
        "/account/me": dict(me(signed), reads=[interface]) if signed else me(signed),
        "/sync": record(words, spec.get("texts", 0), spec.get("days", 0)),
        "/account/story": spec.get("story") or story(bool(words)),
        "/account/totals": {"signedIn": True, "on": True, "totals": []},
        "/account/reading": {"signedIn": True, "reading": {}},
    }

    def answer(route: Any, request: Any) -> Any:
        path = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        if spec.get("offline"):
            return route.abort("internetdisconnected")
        if spec.get("fail") and path == "/account/story":
            return route.fulfill(status=500, content_type="text/plain", body="no")
        if not signed and path != "/account/me":
            return route.fulfill(
                status=401, content_type="application/json", body='{"signedIn": false}'
            )
        said = answers.get(path, {"signedIn": signed})
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(said))

    phone = width < 600
    context = chromium.browser().new_context(
        viewport={"width": width, "height": 900}, has_touch=phone, is_mobile=phone
    )
    script = (
        "localStorage.setItem('targum:welcomed', '1');"
        "localStorage.setItem('targum:language', 'he');"
    )
    if spec.get("offline"):
        script += "Object.defineProperty(navigator, 'onLine', {get: () => false});"
    context.add_init_script(script)
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    return context, page, thrown


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("state", list(STATES))
def test_every_state_says_what_next_and_fits(chromium: Any, state: str, width: int) -> None:
    spec = STATES[state]
    context, page, thrown = open_state(chromium, spec, width)
    try:
        page.goto(SITE + "/progress")
        page.get_by_text(spec["says"], exact=False).first.wait_for(state="visible", timeout=10_000)
        page.wait_for_load_state("networkidle")
        measured = page.evaluate(
            """() => ({
              scroll: document.documentElement.scrollWidth,
              client: document.documentElement.clientWidth,
              wide: [...document.querySelectorAll('body *')]
                .filter((one) => one.getBoundingClientRect().right
                                 > document.documentElement.clientWidth + 0.5)
                .slice(0, 6).map((one) => one.tagName + '#' + one.id + '.' + one.className),
            })"""
        )
        assert measured["scroll"] <= measured["client"], measured
        if "press" in spec:
            press = page.get_by_role("link", name=spec["press"]).or_(
                page.get_by_role("button", name=spec["press"])
            )
            assert press.first.is_visible(), spec["press"]
        assert not thrown, thrown
    finally:
        context.close()


# -- What next's Topics (targum-internal#608) ---------------------------------------------

#: The six topics the live lexicon shows, as `topics.progress` sends them: a row a topic,
#: the exact share known, the weakest named, and the words to learn next.
TOPIC_ROWS = [
    ("family", 62),
    ("food", 48),
    ("money", 35),
    ("school", 71),
    ("law", 19),
    ("security", 8),
]


def with_topics(topics: dict[str, Any] | None) -> dict[str, Any]:
    return dict(story(True), grammar=None, mishkal=None, lead=None, topics=topics)


def topics_said(rows: bool = True) -> dict[str, Any]:
    if not rows:
        return {"floor": 100, "rows": [], "weakest": None}
    return {
        "floor": 100,
        "rows": [
            {
                "topic": topic,
                "known": known,
                "words": [
                    {"lemma": "מילואים", "meaning": "reserve duty"},
                    {"lemma": "חייל", "meaning": ""},
                ],
            }
            for topic, known in TOPIC_ROWS
        ],
        "weakest": "security",
    }


TOPIC_WORDS = {
    "en": {"food": "Food & drink", "security": "Security & the army", "title": "Topics"},
    "ru": {"food": "Еда и напитки", "security": "Безопасность и армия", "title": "Темы"},
}


@pytest.mark.parametrize("interface", ["en", "ru"])
@pytest.mark.parametrize("width", [1440, 390])
def test_topics_draw_a_bar_a_topic_that_opens_its_words(
    chromium: Any, width: int, interface: str
) -> None:
    said = TOPIC_WORDS[interface]
    spec = {
        "signed": True,
        "words": 40,
        "interface": interface,
        "story": with_topics(topics_said()),
    }
    context, page, thrown = open_state(chromium, spec, width)
    try:
        page.goto(SITE + "/progress")
        bars = page.locator("#topic-rows .topic-bar")
        bars.first.wait_for(state="visible", timeout=10_000)
        assert page.locator("#gap-topics").is_visible()
        assert page.locator("#topics-title").inner_text() == said["title"]
        assert bars.count() == len(TOPIC_ROWS)
        # No grid here, so no "Grammar" over nothing.
        assert page.locator("#grammar-head").is_hidden()
        food = page.get_by_role("button", name=said["food"])
        assert food.inner_text().replace("\n", " ").endswith("48%")
        fill = page.locator("#topic-rows .topic-fill").nth(1)
        track = page.locator("#topic-rows .topic-track").nth(1)
        ratio = fill.bounding_box()["width"] / track.bounding_box()["width"]  # type: ignore[index]
        assert abs(ratio - 0.48) < 0.02, ratio
        weakest = page.locator("#topic-rows .topic-row.weakest")
        assert weakest.count() == 1 and said["security"] in weakest.inner_text()

        security = page.get_by_role("button", name=said["security"])
        assert security.get_attribute("aria-expanded") == "false"
        security.click()
        assert page.locator("#topics-words").is_visible()
        assert security.get_attribute("aria-expanded") == "true"
        assert said["security"] in page.locator("#topics-words-title").inner_text()
        listed = page.locator("#topics-word-rows").inner_text()
        assert "מילואים" in listed and "reserve duty" in listed
        assert "met" not in listed and "раз" not in listed, "never met: no count"
        security.click()
        assert page.locator("#topics-words").is_hidden()

        measured = page.evaluate(
            """() => ({
              scroll: document.documentElement.scrollWidth,
              client: document.documentElement.clientWidth,
              bar: Math.min(...[...document.querySelectorAll('.topic-bar')]
                .map((one) => one.getBoundingClientRect().height)),
            })"""
        )
        assert measured["scroll"] <= measured["client"], measured
        if width < 600:
            assert measured["bar"] >= 44, "a bar answers a thumb over 44px (§8)"
        assert not thrown, thrown
    finally:
        context.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_under_the_reader_floor_topics_says_what_to_do_not_bars_at_nought(
    chromium: Any, width: int
) -> None:
    spec = {"signed": True, "words": 40, "story": with_topics(topics_said(rows=False))}
    context, page, thrown = open_state(chromium, spec, width)
    try:
        page.goto(SITE + "/progress")
        note = page.locator("#topics-note")
        note.wait_for(state="visible", timeout=10_000)
        assert note.inner_text().startswith("Once you know 100 words")
        assert page.locator("#topic-rows .topic-bar").count() == 0
        assert page.locator("#topic-rows").is_hidden()
        assert not thrown, thrown
    finally:
        context.close()


def test_no_lexicon_on_the_machine_draws_no_topics(chromium: Any) -> None:
    spec = {"signed": True, "words": 40, "story": with_topics(None)}
    context, page, thrown = open_state(chromium, spec, 1440)
    try:
        page.goto(SITE + "/progress")
        page.get_by_text("Texts at your level now").wait_for(state="visible", timeout=10_000)
        page.wait_for_load_state("networkidle")
        assert page.locator("#gap-topics").is_hidden()
        assert page.locator("#gap").is_hidden(), "nothing at all under the two lists"
        assert not thrown, thrown
    finally:
        context.close()


def test_one_topic_bar_has_nothing_to_be_weakest_against(chromium: Any) -> None:
    """As the grid: with one bar there is nothing to set it against, so no outline."""
    one = topics_said()
    one["rows"], one["weakest"] = one["rows"][-1:], "security"
    spec = {"signed": True, "words": 40, "story": with_topics(one)}
    context, page, thrown = open_state(chromium, spec, 1440)
    try:
        page.goto(SITE + "/progress")
        page.locator("#topic-rows .topic-bar").first.wait_for(state="visible", timeout=10_000)
        assert page.locator("#topic-rows .topic-bar").count() == 1
        assert page.locator("#topic-rows .weakest").count() == 0
        assert not thrown, thrown
    finally:
        context.close()
