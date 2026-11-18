"""A daily goal on Your Progress, drawn in a browser at 1440 and at 390 (targum-internal#537;
design.md §12, "A daily goal counts days, never a run", 2026-11-14).

The two counts, the three kinds of square in their real colours, the sentence a screen
reader hears, the form set in place, and no page wider than the screen. The arithmetic is
`test_progress_goal.py`. Skips itself without Playwright.

**The day is pinned** (targum-internal#748): the totals are dated from `TODAY`, and the
browser's clock and time zone are pinned to a moment on that day in UTC. They were dated
from `date.today()` when the module was imported, and the page read its own clock, so a
suite that crossed midnight UTC between the two drew "today" a day off and failed.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest

from targum.render.builder import progress_page

pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://progress.test"

ME = {
    "signedIn": True,
    "email": "r@x.test",
    "initials": "R",
    "readsSaid": True,
    "reads": ["en"],
    "language": "he",
    "learning": ["he"],
    "interest": ["news"],
}

SYNC = {
    "revision": 3,
    "words": [
        {
            "language": "he",
            "lemma": f"מלה{n}",
            "status": 9 if n % 2 else 2,
            "surface": f"מלה{n}",
            "band": 1,
            "learned": 0,
            "at": 100 + n,
            "seen": 200,
            "gone": 0,
        }
        for n in range(40)
    ],
    "docs": [],
    "days": [],
}


#: The day the page is drawn on, whatever day the suite runs (targum-internal#748).
TODAY = date(2026, 11, 18)
#: The moment the browser's clock says, on `TODAY` in UTC.
NOON = datetime.combine(TODAY, time(12), UTC)


def _ago(days: int) -> str:
    return (TODAY - timedelta(days=days)).isoformat()


def _row(days: int, words: int) -> dict[str, Any]:
    return {
        "day": _ago(days),
        "language": "he",
        "medium": "read",
        "words": words,
        "listened": 0,
        "watched": 0,
    }


TOTALS = [_row(0, 40), _row(1, 600), _row(2, 300), _row(4, 120), _row(6, 260)]


def open_page(
    chromium: Any,
    width: int,
    language: str = "en",
    goals: dict | None = None,
    at: datetime = NOON,
) -> Any:
    html = progress_page("", language)
    posted: list[Any] = []
    held = {"goals": dict(goals or {})}

    def answer(route: Any, request: Any) -> Any:
        path = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        if path == "/account/goal":
            sent = json.loads(request.post_data or "{}")
            posted.append(sent)
            if sent.get("amount"):
                held["goals"][sent["language"]] = {"unit": sent["unit"], "amount": sent["amount"]}
            else:
                held["goals"].pop(sent["language"], None)
            body: Any = {"signedIn": True, "goals": held["goals"]}
        else:
            body = {
                "/account/me": ME,
                "/sync": SYNC,
                "/account/totals": {
                    "signedIn": True,
                    "on": True,
                    "kept": True,
                    "totals": TOTALS,
                    "goals": held["goals"],
                    "words": None,
                },
                "/account/reading": {"signedIn": True, "reading": {}},
            }.get(path, {"signedIn": True})
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    phone = width < 600
    # UTC, as the totals are dated, and the clock at `at`: the page's "today" is TODAY.
    context = chromium.browser().new_context(
        viewport={"width": width, "height": 900},
        has_touch=phone,
        is_mobile=phone,
        timezone_id="UTC",
    )
    context.add_init_script(
        "localStorage.setItem('targum:welcomed', '1');"
        "localStorage.setItem('targum:language', 'he');"
    )
    page = context.new_page()
    page.clock.set_fixed_time(at)
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    page.goto(SITE + "/progress")
    return context, page, thrown, posted


def _fits(page: Any) -> None:
    measured = page.evaluate(
        "() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]"
    )
    assert measured[0] <= measured[1], measured


@pytest.mark.parametrize("width", [1440, 390])
def test_a_goal_is_two_counts_and_three_kinds_of_square(chromium: Any, width: int) -> None:
    context, page, thrown, _ = open_page(
        chromium, width, goals={"he": {"unit": "words", "amount": 250}}
    )
    try:
        page.locator("#days-grid .day").first.wait_for(state="attached", timeout=10_000)
        assert page.locator("#days-title").inner_text() == "Days active · 5 of 30"
        assert page.locator("#goal-title").inner_text() == "Daily goal · 3 of 30"
        assert page.locator("#goal-said").inner_text() == "250 words read a day"
        assert page.locator("#days-grid").get_attribute("aria-label") == (
            "You were active on 5 of the last 30 days, and reached your goal on 3 of them."
        )
        colours = page.evaluate(
            """() => {
              const root = getComputedStyle(document.documentElement);
              const probe = document.createElement('span');
              document.body.appendChild(probe);
              const as = (name) => {
                probe.style.background = root.getPropertyValue(name).trim();
                return getComputedStyle(probe).backgroundColor;
              };
              const days = [...document.querySelectorAll('#days-grid .day')];
              const out = {
                leaf: as('--step-4'), under: as('--step-2'), rest: as('--divider'),
                squares: days.map((d) => getComputedStyle(d).backgroundColor),
                kinds: days.map((d) => d.className),
              };
              probe.remove();
              return out;
            }"""
        )
        squares, kinds = colours["squares"], colours["kinds"]
        assert kinds[-1] == "day under", "today under the goal is any day under it"
        assert squares[-1] == colours["under"] and squares[-2] == colours["leaf"]
        assert squares[-4] == colours["rest"]
        assert colours["leaf"] != colours["under"] != colours["rest"]
        assert page.locator("#goal-set").is_hidden()
        _fits(page)
        assert not thrown, thrown
    finally:
        context.close()


def test_set_in_place_and_read_again(chromium: Any) -> None:
    context, page, thrown, posted = open_page(chromium, 1440)
    try:
        page.locator("#days-grid .day").first.wait_for(state="attached", timeout=10_000)
        assert page.locator("#goal-head").is_hidden()
        page.get_by_role("button", name="Set a daily goal").click()
        assert page.locator("#goal-form").is_visible()
        assert page.locator("#goal-remove").is_hidden()
        assert page.locator("#goal-amount option").all_inner_texts() == [
            "100",
            "250",
            "500",
            "1,000",
            "2,500",
        ]
        page.get_by_role("button", name="Minutes listening").click()
        assert page.locator("#goal-amount option").all_inner_texts() == [
            "5",
            "10",
            "15",
            "30",
            "60",
        ]
        page.get_by_role("button", name="Words read").click()
        page.locator("#goal-amount").select_option("500")
        page.get_by_role("button", name="Save").click()
        page.locator("#goal-head").wait_for(state="visible")
        assert posted == [{"language": "he", "unit": "words", "amount": 500}]
        assert page.locator("#goal-title").inner_text() == "Daily goal · 1 of 30"
        assert page.locator("#goal-form").is_hidden()
        page.get_by_role("button", name="Change").click()
        page.get_by_role("button", name="Remove goal").click()
        page.locator("#goal-set").wait_for(state="visible")
        assert posted[-1]["amount"] == 0
        assert page.locator("#goal-head").is_hidden()
        assert not thrown, thrown
    finally:
        context.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_russian_fits(chromium: Any, width: int) -> None:
    context, page, thrown, _ = open_page(
        chromium, width, language="ru", goals={"he": {"unit": "minutes", "amount": 15}}
    )
    try:
        page.locator("#days-grid .day").first.wait_for(state="attached", timeout=10_000)
        assert page.locator("#goal-title").inner_text() == "Цель на день · 0 из 30"
        assert page.locator("#goal-said").inner_text() == "15 минут аудио и видео в день"
        page.locator("#goal-change").click()
        assert page.locator("#goal-form").is_visible()
        _fits(page)
        assert not thrown, thrown
    finally:
        context.close()


@pytest.mark.parametrize(
    "at",
    [
        datetime.combine(TODAY, time(0, 0, 1), UTC),
        datetime.combine(TODAY, time(23, 59, 59), UTC),
    ],
    ids=["just-after-midnight", "just-before-midnight"],
)
def test_the_day_is_the_same_at_either_end_of_it(chromium: Any, at: datetime) -> None:
    """targum-internal#748: drawn a second after midnight or a second before the next,
    today is TODAY and is the last square, under the goal, as at noon."""
    context, page, thrown, _ = open_page(
        chromium, 1440, goals={"he": {"unit": "words", "amount": 250}}, at=at
    )
    try:
        page.locator("#days-grid .day").first.wait_for(state="attached", timeout=10_000)
        assert page.locator("#days-title").inner_text() == "Days active · 5 of 30"
        assert page.locator("#goal-title").inner_text() == "Daily goal · 3 of 30"
        kinds = page.evaluate(
            "() => [...document.querySelectorAll('#days-grid .day')].map((d) => d.className)"
        )
        assert kinds[-1] == "day under"
        assert not thrown, thrown
    finally:
        context.close()
