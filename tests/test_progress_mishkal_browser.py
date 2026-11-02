"""The Mishkal list beside the Grammar grid (design.md §12, 2026-11-02), drawn in a
browser at 390, 1024 and 1440.

A row a reviewed pattern, one square a row, a real table with scoped headers; "—" under
the floor; the weakest row outlined; a square opens its words; What next names the
mishkal gap when the account says it leads; and at a desk the list stands as two columns
of rows, so it is not one long column beside the seven-row grid. The arithmetic is
`test_gaps.py`.

`TARGUM_SHOTS=<dir>` saves a screenshot of each width there. Skips itself without
Playwright.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from test_progress_gap_browser import ME, SITE, SYNC, grammar

from targum.annotate.mishkal import KEYS, template
from targum.render.builder import progress_page

pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

#: Fourteen patterns met, as a reader a few months in might have: the list's own order,
#: two under the floor, miktal the weakest.
MET = {
    "qattal": 9,
    "miqtal": 96,
    "miqtala": 41,
    "maqtela": 23,
    "qtila": 412,
    "qittul": 268,
    "haqtala": 133,
    "hitqattlut": 47,
    "qatul": 156,
    "qatil": 61,
    "qotel": 88,
    "taqtil": 6,
    "qatlut": 190,
    "suffix-i": 341,
}
SHARE = {
    "miqtal": 34,
    "miqtala": 63,
    "maqtela": 48,
    "qtila": 74,
    "qittul": 66,
    "haqtala": 61,
    "hitqattlut": 45,
    "qatul": 69,
    "qatil": 52,
    "qotel": 77,
    "qatlut": 58,
    "suffix-i": 81,
}


def mishkal(gap: bool = True) -> dict[str, Any]:
    rows = []
    for key in KEYS:
        if key not in MET:
            continue
        known = SHARE.get(key)
        rows.append(
            {
                "pattern": key,
                "template": template(key),
                "tokens": MET[key],
                "known": known,
                "words": (
                    [
                        {"lemma": "מספר", "count": 21, "known": True},
                        {"lemma": "מפעל", "count": 5, "known": False},
                    ]
                    if known is not None
                    else []
                ),
            }
        )
    return {
        "rows": rows,
        "cellFloor": 10,
        "rowFloor": 30,
        "gap": (
            {
                "pattern": "miqtal",
                "template": "מִקְטָל",
                "known": 34,
                "others": 68,
                "examples": ["מספר", "מפעל"],
            }
            if gap
            else None
        ),
    }


def open_page(
    chromium: Any,
    said: dict[str, Any],
    width: int,
    interface: str = "en",
) -> tuple[Any, Any, list[str]]:
    html = progress_page("", interface)
    story = {
        "signedIn": True,
        "library": True,
        "known": 20,
        "ladder": [],
        "here": None,
        "next": None,
        "level": None,
        "texts": [{"id": "jonah", "title": "יונה", "kind": "prose", "known": 91}],
        "words": [{"lemma": "מלה2", "texts": 4}],
        **said,
    }
    me = dict(ME, reads=[interface])

    def answer(route: Any, request: Any) -> Any:
        path = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        found = {
            "/account/me": me,
            "/sync": SYNC,
            "/account/story": story,
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
    page.locator(".mishkal-row").first.wait_for(state="attached", timeout=10_000)
    return context, page, thrown


def shoot(page: Any, name: str) -> None:
    where = os.environ.get("TARGUM_SHOTS")
    if where:
        page.locator("#next").screenshot(path=str(Path(where) / f"{name}.png"))


BOTH = {"grammar": grammar(), "mishkal": mishkal(), "lead": "mishkal"}


@pytest.mark.parametrize("width", [1440, 1024, 390])
def test_the_list_is_a_table_under_the_grid_and_fits(chromium: Any, width: int) -> None:
    context, page, thrown = open_page(chromium, BOTH, width)
    try:
        assert page.get_by_role("heading", name="Grammar").is_visible(), "the heading stays"
        assert page.get_by_role("heading", name="Mishkal").is_visible()
        rows = page.locator(".mishkal tbody tr")
        assert rows.count() == len(MET), "only the patterns met, every one of them"
        heads = page.locator(".mishkal tbody th[scope=row] bdi[lang=he]")
        assert heads.first.inner_text() == "קַטָּל", "the list's own order, in ק־ט־ל"
        assert [heads.nth(n).inner_text() for n in range(heads.count())][-2:] == ["־ות", "־י"]
        assert page.get_by_role("columnheader", name="Known").count() >= 1
        assert page.locator(".mishkal td.empty").count() == 2
        assert "fewer than 10 times" in page.locator("#mishkal-floor").inner_text()
        weakest = page.locator(".mishkal tr.weakest")
        assert weakest.count() == 1 and "miktal" in weakest.inner_text()
        assert "often a place or a thing done" in weakest.inner_text()
        # Each list outlines its own weakest; the headline names one.
        assert page.locator("#grammar tr.weakest").count() == 1

        measured = page.evaluate(
            """() => {
              const box = (s) => document.querySelector(s).getBoundingClientRect();
              const tables = [...document.querySelectorAll('.mishkal')]
                .map((t) => t.getBoundingClientRect());
              return {
                scroll: document.documentElement.scrollWidth,
                client: document.documentElement.clientWidth,
                grammar: box('.gap-grammar'), mishkal: box('.gap-mishkal'),
                tables: tables.map((t) => ({left: t.left, top: t.top, height: t.height})),
                rows: [...document.querySelectorAll('.mishkal tbody tr')]
                  .map((tr) => tr.getBoundingClientRect().height),
                rem: parseFloat(getComputedStyle(document.documentElement).fontSize),
                cell: Math.min(...[...document.querySelectorAll('.mishkal .grammar-cell')]
                  .map((one) => one.getBoundingClientRect().height)),
              };
            }"""
        )
        assert measured["scroll"] <= measured["client"], measured
        grammar_box, mishkal_box, tables = (
            measured["grammar"],
            measured["mishkal"],
            measured["tables"],
        )
        # Under the grid at every width (David, 2026-11-02), and the grid keeps its 36rem.
        assert mishkal_box["top"] >= grammar_box["bottom"], "under the grid"
        if width >= 600:
            # Two columns of rows side by side, so no band is left empty beside them.
            assert len(tables) == 2 and tables[0]["top"] == tables[1]["top"]
            assert tables[1]["left"] > tables[0]["left"]
            # Each row on one line: no row is taller than two lines of the pattern.
            assert max(measured["rows"]) < 3.2 * measured["rem"], measured["rows"]
        else:
            assert tables[1]["top"] > tables[0]["top"], "one list on a phone"
            assert measured["cell"] >= 44, "a square answers a thumb over 44px (§8)"
        shoot(page, f"mishkal-{width}")
        assert not thrown, thrown
    finally:
        context.close()


def test_what_next_names_the_mishkal_when_it_leads(chromium: Any) -> None:
    context, page, thrown = open_page(chromium, BOTH, 1440)
    try:
        title = page.locator("#next-title")
        assert title.inner_text() == "Your biggest gap: מִקְטָל words"
        assert title.locator("bdi[lang=he][dir=rtl]").inner_text() == "מִקְטָל"
        said = page.locator("#gap-said").inner_text()
        assert "You know 34% of the miktal words you meet, against 68%" in said
        assert "Miktal words are often a place or a thing done." in said
        assert "You've met" in said and "מספר" in said
        assert not thrown, thrown
    finally:
        context.close()


def test_the_binyan_leads_when_the_account_says_so(chromium: Any) -> None:
    context, page, thrown = open_page(chromium, dict(BOTH, lead="binyan"), 1440)
    try:
        assert page.locator("#next-title").inner_text() == "Your biggest gap: הִתְפַּעֵל verbs"
        assert page.locator(".mishkal tr.weakest").count() == 1
        assert not thrown, thrown
    finally:
        context.close()


def test_a_square_opens_its_words_and_one_list_is_open_at_a_time(chromium: Any) -> None:
    context, page, thrown = open_page(chromium, BOTH, 1440)
    try:
        square = page.locator(".mishkal tr.weakest .grammar-cell")
        square.click()
        box = page.locator("#mishkal-words")
        assert box.is_visible() and square.get_attribute("aria-expanded") == "true"
        assert page.locator("#mishkal-words-title").inner_text() == "miktal: the words you met"
        assert page.locator("#mishkal-word-rows li").count() == 2
        shoot(page, "mishkal-1440-open")
        page.locator("#grammar .grammar-cell").first.click()
        assert box.is_hidden() and square.get_attribute("aria-expanded") == "false"
        assert page.locator("#grammar-words").is_visible()
        assert not thrown, thrown
    finally:
        context.close()


def test_with_no_list_the_grid_stands_as_it_shipped(chromium: Any) -> None:
    """A machine without roots-he.json sends no list: the Mishkal block stays hidden and
    the grid keeps its 36rem."""
    html = progress_page("", "en")
    context = chromium.browser().new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    try:
        story = {"signedIn": True, "library": True, "texts": [], "words": []}
        story.update(grammar=grammar(), mishkal=None, lead="binyan")

        def answer(route: Any, request: Any) -> Any:
            path = request.url[len(SITE) :].split("?")[0]
            if request.resource_type == "document":
                return route.fulfill(status=200, content_type="text/html", body=html)
            found = {"/account/me": ME, "/sync": SYNC, "/account/story": story}.get(
                path, {"signedIn": True}
            )
            route.fulfill(status=200, content_type="application/json", body=json.dumps(found))

        page.add_init_script("localStorage.setItem('targum:language', 'he');")
        page.route(f"{SITE}/**", answer)
        page.goto(SITE + "/progress")
        page.locator("#grammar-rows tr").first.wait_for(state="attached", timeout=10_000)
        assert page.locator("#gap-mishkal").is_hidden()
        assert page.locator("#next-title").inner_text() == "Your biggest gap: הִתְפַּעֵל verbs"
        width = page.evaluate(
            "document.querySelector('.gap-grammar').getBoundingClientRect().width"
        )
        rem = page.evaluate("parseFloat(getComputedStyle(document.documentElement).fontSize)")
        assert width <= 36 * rem + 1
    finally:
        context.close()


@pytest.mark.parametrize("width", [1440, 390])
def test_the_russian_list_says_its_drafts(chromium: Any, width: int) -> None:
    context, page, thrown = open_page(chromium, BOTH, width, interface="ru")
    try:
        assert page.get_by_role("heading", name="Мишкаль").is_visible()
        assert "миктал" in page.locator(".mishkal tr.weakest").inner_text()
        said = page.locator("#gap-said").inner_text()
        assert "Слова миктал часто называют место или то, что сделано." in said
        shoot(page, f"mishkal-{width}-ru")
        assert not thrown, thrown
    finally:
        context.close()
