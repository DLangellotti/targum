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
    {"kind": "dialogue", "name": "dialogue", "share": 99, "state": "passed", "texts": 9},
    {"kind": "talk", "name": "talk", "share": 96, "state": "passed", "texts": 9},
    {"kind": "article", "name": "article", "share": 93, "state": "here", "texts": 9},
    {"kind": "story", "name": "story", "share": 86, "state": "next", "texts": 9},
    {"kind": "novel", "name": "novel", "share": 70, "state": "ahead", "texts": 9},
    {"kind": "poetry", "name": "poetry", "share": None, "state": "ahead", "texts": 9},
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
            "ladder": [dict(rung, share=None, state="ahead") for rung in LADDER],
            "here": -1,
            "said": "",
            "texts": [],
            "words": [],
        }
    return {
        "signedIn": True,
        "library": True,
        "known": 1700,
        "ladder": LADDER,
        "here": 2,
        "said": "nearly",
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
    html = progress_page("", "en")
    signed = spec["signed"]
    words = spec.get("words", 0)
    answers: dict[str, Any] = {
        "/account/me": me(signed),
        "/sync": record(words, spec.get("texts", 0), spec.get("days", 0)),
        "/account/story": story(bool(words)),
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
