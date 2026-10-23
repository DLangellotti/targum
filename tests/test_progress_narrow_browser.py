"""Your Progress at a phone's width never scrolls sideways (targum-internal#522, §14.2).

Polish 6 on #471 kept each time figure on one line, and the three figures stayed in three
columns of 91px at 390: "9 ч 28 мин" needs about 120, so it ran into "2 ч 30 мин" and the
document scrolled sideways, to 461px on Aramaic in Russian. Under 40rem the figures now
wrap. This loads the page the server renders, in Russian, with the longest time values a
month holds, and measures it at 390 and 320.

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


def me(language: str) -> dict[str, Any]:
    return {
        "signedIn": True,
        "email": "r@x.test",
        "initials": "R",
        "readsSaid": True,
        "reads": ["ru"],
        "language": language,
        "learning": [language],
        "interest": ["news"],
    }


def pulled(language: str, *lemmas: str) -> list[dict[str, Any]]:
    return [
        {
            "language": language,
            "lemma": lemma,
            "status": 2 if n % 2 else 3,
            "surface": lemma,
            "band": 1,
            "learned": 0,
            "at": 100 + n,
            "seen": 200,
            "gone": 0,
        }
        for n, lemma in enumerate(lemmas)
    ]


def totals(language: str) -> dict[str, Any]:
    """ "9 ч 28 мин" listened and watched, and a five-figure count of words read."""
    today = datetime.date.today().isoformat()
    row = {"day": today, "language": language, "words": 11_385}
    return {
        "signedIn": True,
        "on": True,
        "totals": [
            dict(row, medium="read", listened=0, watched=0),
            dict(row, medium="listen", words=0, listened=9 * 3600 + 28 * 60, watched=0),
            dict(row, medium="watch", words=0, listened=0, watched=9 * 3600 + 28 * 60),
        ],
    }


def open_progress(chromium: Any, language: str, width: int):
    html = progress_page("", "ru")
    answers = {
        "/account/me": me(language),
        "/sync": {"revision": 3, "words": pulled(language, "ספר", "דרך", "עיר", "בית")},
        "/account/totals": totals(language),
    }

    def answer(route: Any, request: Any) -> Any:
        path = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        said = answers.get(path, {"signedIn": True})
        route.fulfill(status=200, content_type="application/json", body=json.dumps(said))

    context = chromium.browser().new_context(viewport={"width": width, "height": 844})
    context.add_init_script(
        "localStorage.setItem('targum:welcomed', '1');"
        f"localStorage.setItem('targum:language', '{language}');"
    )
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    return context, page, thrown


@pytest.mark.parametrize("width", [390, 320])
@pytest.mark.parametrize("language", ["he", "arc", "yi"])
def test_the_time_figures_never_overlap_or_push_the_page_sideways(
    chromium: Any, language: str, width: int
) -> None:
    context, page, thrown = open_progress(chromium, language, width)
    try:
        page.goto(SITE + "/progress")
        page.wait_for_selector("#spent:not([hidden]) .spent-amount")
        page.wait_for_load_state("networkidle")
        amounts = page.locator("#spent-figures .spent-amount").all_inner_texts()
        assert "9 ч 28 мин" in amounts, amounts
        measured = page.evaluate(
            """() => ({
              scroll: document.documentElement.scrollWidth,
              client: document.documentElement.clientWidth,
              wide: [...document.querySelectorAll('body *')]
                .filter((one) => one.getBoundingClientRect().right
                                 > document.documentElement.clientWidth + 0.5)
                .slice(0, 8)
                .map((one) => one.tagName + '#' + one.id + '.' + one.className),
              boxes: [...document.querySelectorAll('#spent-figures .spent-figure')].map(
                (one) => { const r = one.getBoundingClientRect();
                           return [r.left, r.top, r.right, r.bottom]; }),
              amounts: [...document.querySelectorAll('#spent-figures .spent-amount')].map(
                (one) => { const r = one.getBoundingClientRect();
                           return [r.left, r.top, r.right, r.bottom]; }),
            })"""
        )
        assert measured["scroll"] <= measured["client"], measured
        for kind in ("boxes", "amounts"):
            rects = measured[kind]
            for i, a in enumerate(rects):
                assert a[2] <= measured["client"], (kind, a, measured["client"])
                for b in rects[i + 1 :]:
                    apart = a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]
                    assert apart, (kind, a, b)
        assert not thrown, thrown
    finally:
        context.close()


def test_the_learned_note_sits_inside_the_ledger_on_the_desk(chromium: Any) -> None:
    """At 1440 the "Learned on targum" line sat under the ledger on the desk ground,
    outside any card (targum-internal#522; §9, §13)."""
    context, page, thrown = open_progress(chromium, "he", 1440)
    try:
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto(SITE + "/progress")
        page.wait_for_selector("#page:not([hidden])")
        assert page.locator("#ledger #learned-note").is_visible()
        assert not thrown, thrown
    finally:
        context.close()
