"""What next leads with your biggest grammar gap (design.md §12, 2026-10-30, board 4B;
targum-internal#604), drawn in a browser at 1440 and at 390.

The headline names the gap, the Grammar grid is a real table with its headers scoped and
its percentages as text, a square under the floor says "—", the weakest row is outlined,
a square opens its words, Topics stays hidden, and with no grid the two lists stand alone
under the old title. The arithmetic is `test_gaps.py`.

Skips itself without Playwright.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from targum.render.builder import progress_page

pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://progress.test"
OLD_TITLE = "The words and texts that would help most"

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

KEYS = ("paal", "nifal", "piel", "pual", "hifil", "hufal", "hitpael")
TENSES = ("past", "present", "future", "imperative", "infinitive")


def square(known: int) -> dict[str, Any]:
    return {
        "known": known,
        "tokens": 40,
        "words": [
            {"lemma": "התלבש", "count": 12, "known": False},
            {"lemma": "התקדם", "count": 9, "known": True},
        ],
    }


def grammar(gap: bool = True) -> dict[str, Any]:
    rows = []
    for at, key in enumerate(KEYS):
        cells: dict[str, Any] = {}
        for column, tense in enumerate(TENSES):
            # pu'al and huf'al have no imperative or infinitive worth a figure.
            thin = key in ("pual", "hufal") and column >= 2
            cells[tense] = None if thin else square(max(1, 92 - at * 9 - column * 5))
        rows.append({"binyan": key, "cells": cells, "tokens": 200})
    return {
        "rows": rows,
        "cellFloor": 10,
        "rowFloor": 30,
        "gap": (
            {"binyan": "hitpael", "known": 31, "others": 80, "examples": ["התלבש", "התכתב"]}
            if gap
            else None
        ),
    }


def story(said: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "signedIn": True,
        "library": True,
        "known": 20,
        "ladder": [],
        "here": None,
        "next": None,
        "level": None,
        "texts": [{"id": "jonah", "title": "יונה", "kind": "prose", "known": 91}],
        "words": [{"lemma": "מלה2", "texts": 4}],
        "grammar": said,
    }


def open_page(chromium: Any, said: dict[str, Any] | None, width: int) -> tuple[Any, Any, list]:
    html = progress_page("", "en")

    def answer(route: Any, request: Any) -> Any:
        path = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        found = {
            "/account/me": ME,
            "/sync": SYNC,
            "/account/story": story(said),
            "/account/totals": {"signedIn": True, "on": True, "totals": []},
            "/account/reading": {"signedIn": True, "reading": {}},
        }.get(path, {"signedIn": True})
        route.fulfill(status=200, content_type="application/json", body=json.dumps(found))

    phone = width < 600
    context = chromium.browser().new_context(
        viewport={"width": width, "height": 900}, has_touch=phone, is_mobile=phone
    )
    context.add_init_script(
        "localStorage.setItem('targum:welcomed', '1');"
        "localStorage.setItem('targum:language', 'he');"
    )
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    page.goto(SITE + "/progress")
    return context, page, thrown


@pytest.mark.parametrize("width", [1440, 390])
def test_the_gap_leads_and_the_grid_is_a_table_that_fits(chromium: Any, width: int) -> None:
    context, page, thrown = open_page(chromium, grammar(), width)
    try:
        page.locator("#grammar-rows tr").first.wait_for(state="attached", timeout=10_000)
        title = page.locator("#next-title")
        assert title.inner_text().startswith("Your biggest gap:")
        assert title.locator("bdi[lang=he][dir=rtl]").inner_text() == "הִתְפַּעֵל"
        said = page.locator("#gap-said").inner_text()
        assert "You know 31% of the hitpa'el forms you meet, against 80%" in said
        assert "reflexive or mutual" in said
        assert "You've met" in said and "התלבש" in said and "התכתב" in said

        table = page.get_by_role("table", name="Grammar")
        assert table.is_visible()
        columns = page.locator("#grammar thead th[scope=col]")
        assert columns.count() == 5
        # The long names are what a screen reader hears, at either width.
        assert page.get_by_role("columnheader", name="Imperative").count() == 1
        assert page.locator("#grammar tbody th[scope=row]").count() == 7
        assert page.locator("#grammar tbody th[scope=row] bdi[lang=he]").first.inner_text() == (
            "פָּעַל"
        )
        # pu'al and huf'al: three squares each under the floor.
        assert page.locator("#grammar td.empty").count() == 6
        assert "fewer than 10 forms" in page.locator("#grammar-floor").inner_text()
        weakest = page.locator("#grammar tr.weakest")
        assert weakest.count() == 1 and "hitpa'el" in weakest.inner_text()
        assert page.locator("#gap-topics").is_hidden(), "Topics waits for topic tagging"
        # Both lists still stand under it, as they were.
        assert page.get_by_text("Words you keep meeting and don't know yet").is_visible()
        assert page.get_by_text("Texts at your level now").is_visible()

        measured = page.evaluate(
            """() => ({
              scroll: document.documentElement.scrollWidth,
              client: document.documentElement.clientWidth,
              cell: Math.min(...[...document.querySelectorAll('.grammar-cell')]
                .map((one) => one.getBoundingClientRect().height)),
            })"""
        )
        assert measured["scroll"] <= measured["client"], measured
        if width < 600:
            assert measured["cell"] >= 44, "a square answers a thumb over 44px (§8)"
        assert not thrown, thrown
    finally:
        context.close()


def test_a_square_opens_its_words_and_closes_again(chromium: Any) -> None:
    context, page, thrown = open_page(chromium, grammar(), 1440)
    try:
        page.locator("#grammar-rows tr").first.wait_for(state="attached", timeout=10_000)
        first = page.locator(".grammar-cell").first
        assert first.get_attribute("aria-expanded") == "false"
        first.click()
        box = page.locator("#grammar-words")
        assert box.is_visible() and first.get_attribute("aria-expanded") == "true"
        assert "pa'al, Past" in page.locator("#grammar-words-title").inner_text()
        rows = page.locator("#grammar-word-rows li")
        assert rows.count() == 2
        assert "met 12 times" in rows.nth(0).inner_text()
        assert "known" in rows.nth(1).inner_text()
        first.click()
        assert box.is_hidden() and first.get_attribute("aria-expanded") == "false"
        assert not thrown, thrown
    finally:
        context.close()


def test_one_pattern_with_enough_draws_the_grid_and_no_headline(chromium: Any) -> None:
    context, page, thrown = open_page(chromium, grammar(gap=False), 1440)
    try:
        page.locator("#grammar-rows tr").first.wait_for(state="attached", timeout=10_000)
        assert page.locator("#next-title").inner_text() == OLD_TITLE
        assert page.locator("#gap-said").is_hidden()
        assert page.locator("#grammar tr.weakest").count() == 0
        assert not thrown, thrown
    finally:
        context.close()


def test_with_no_grid_the_two_lists_stand_alone(chromium: Any) -> None:
    context, page, thrown = open_page(chromium, None, 1440)
    try:
        page.get_by_text("Texts at your level now").wait_for(state="visible", timeout=10_000)
        page.locator("#level-rows li").first.wait_for(state="attached", timeout=10_000)
        assert page.locator("#gap").is_hidden()
        assert page.locator("#next-title").inner_text() == OLD_TITLE
        assert not thrown, thrown
    finally:
        context.close()
