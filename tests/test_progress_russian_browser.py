"""Russian grammar on Your Progress (design.md §12, "Russian grammar on Your Progress",
2026-11-09; targum-internal#639), drawn in a browser at 390 and 1440, in the English and
the Russian interface.

Aspect | Cases under "Grammar", the headline's gap above them and its tab open; the
aspect grid with the perfective present hatched as no such form, aspect pairs under it;
the case grid with its animate accusative row, where and where to under it, never the
gap; More shut on load, holding verbs of motion, nouns in -ь and participles and gerunds.
Every square with a figure opens the forms met, each with its dictionary form, meaning
and "known" or how often it was met, and one list is open at a time across all of it.
Hebrew's own page is `test_progress_whatnext_tabs_browser.py` and its neighbours; here
it is checked that a Hebrew page draws none of this. The arithmetic is `test_gaps_ru.py`.

`TARGUM_SHOTS=<dir>` saves a screenshot of each state there. Skips itself without
Playwright.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from test_progress_gap_browser import ME, SITE, SYNC
from test_progress_mishkal_browser import BOTH

from targum.render.builder import progress_page

pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

#: A Russian list in the browser's store, so the page has a Russian to draw; and Hebrew's,
#: for the page that checks Hebrew is left as it was.
RU_SYNC = dict(
    SYNC,
    words=[
        *SYNC["words"],
        *(
            {
                "language": "ru",
                "lemma": f"слово{n}",
                "status": 9 if n % 2 else 2,
                "surface": f"слово{n}",
                "band": 1,
                "learned": 0,
                "at": 100 + n,
                "seen": 200,
                "gone": 0,
            }
            for n in range(40)
        ),
    ],
)

TENSES = ("past", "present", "future", "imperative", "infinitive")


def square(known: int, words: list[tuple[str, str, str, int, bool]]) -> dict[str, Any]:
    return {
        "known": known,
        "tokens": 40,
        "words": [
            {"form": form, "lemma": lemma, "meaning": meaning, "count": n, "known": k}
            for form, lemma, meaning, n, k in words
        ],
    }


SAID = [("сказал", "сказать", "say", 31, True), ("спросил", "спросить", "ask", 12, False)]
CASE = [("рукой", "рука", "hand", 9, True), ("улыбкой", "улыбка", "smile", 5, False)]


def russian(lead: str = "aspect") -> dict[str, Any]:
    aspect_rows = [
        {
            "row": "imperfective",
            "tokens": 300,
            "cells": {tense: square(80 - n, SAID) for n, tense in enumerate(TENSES)},
        },
        {
            "row": "perfective",
            "tokens": 200,
            "cells": {
                "past": square(61, SAID),
                "present": None,
                "future": square(49, SAID),
                "imperative": None,
                "infinitive": square(55, SAID),
            },
        },
    ]
    cases = ("nom", "gen", "dat", "acc", "acca", "ins", "loc")
    case_rows = [
        {
            "row": key,
            "tokens": 100,
            "cells": {
                "sing": square(60 + n, CASE),
                "plur": None if key == "acca" else square(50 + n, CASE),
            },
        }
        for n, key in enumerate(cases)
    ]
    place_rows = [
        {
            "row": key,
            "tokens": 60,
            "cells": {
                "where": square(40, [("в доме", "дом", "house", 9, True)]),
                "whereto": square(30, [("в город", "город", "town", 6, False)]),
            },
        }
        for key in ("v", "na", "za", "pod")
    ]
    return {
        "aspect": {
            "rows": aspect_rows,
            "gap": {
                "row": "perfective",
                "known": 58,
                "others": 79,
                "examples": [
                    {"lemma": "спросить", "form": "спросил", "meaning": "ask"},
                    {"lemma": "вернуться", "form": "вернулась", "meaning": "come back"},
                ],
            },
        },
        "pairs": {
            "met": 71,
            "both": 38,
            "rows": [
                {
                    "imperfective": "спрашивать",
                    "perfective": "спросить",
                    "known": "imperfective",
                    "count": 9,
                    "meaning": "ask",
                },
                {
                    "imperfective": "отвечать",
                    "perfective": "ответить",
                    "known": "neither",
                    "count": 5,
                    "meaning": "answer",
                },
                {
                    "imperfective": "говорить",
                    "perfective": "сказать",
                    "known": "both",
                    "count": 40,
                    "meaning": "say",
                },
            ],
        },
        "cases": {
            "rows": case_rows,
            "gap": {
                "row": "acca",
                "known": 41,
                "others": 70,
                "examples": [{"lemma": "брат", "form": "брата", "meaning": "brother"}],
            },
        },
        "place": {"rows": place_rows, "gap": None},
        "motion": {
            "tokens": 60,
            "cells": {
                "one": square(79, [("шёл", "идти", "go", 14, True)]),
                "back": square(60, [("ходил", "ходить", "go", 8, False)]),
            },
            "pairs": [
                {"one": "идти", "back": "ходить", "known": "both", "meaning": "go on foot"},
                {"one": "ехать", "back": "ездить", "known": "one", "meaning": "go by transport"},
                {"one": "нести", "back": "носить", "known": "neither", "meaning": "carry"},
            ],
        },
        "soft": {
            "rows": [
                {
                    "row": "fem",
                    "tokens": 40,
                    "cells": {"all": square(64, [("ночь", "ночь", "night", 9, True)])},
                    "examples": ["ночь", "жизнь", "дверь"],
                },
                {
                    "row": "masc",
                    "tokens": 30,
                    "cells": {"all": square(51, [("дня", "день", "day", 12, False)])},
                    "examples": ["день", "гость"],
                },
            ]
        },
        "forms": {
            "rows": [
                {
                    "row": key,
                    "tokens": 40,
                    "cells": {"imperfective": square(41, SAID), "perfective": None},
                }
                for key in ("partact", "partpass", "short", "gerund")
            ],
            "gap": None,
        },
        "lead": lead,
        "cellFloor": 10,
        "rowFloor": 30,
    }


def open_page(
    chromium: Any, said: dict[str, Any], width: int, interface: str = "en", language: str = "ru"
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
        "texts": [{"id": "chekhov", "title": "Капитанский мундир", "kind": "prose", "known": 91}],
        "words": [{"lemma": "мундир", "texts": 4}],
        "grammar": None,
        "mishkal": None,
        "lead": None,
        **said,
    }
    me = dict(ME, reads=[interface], language=language, learning=[language])

    def answer(route: Any, request: Any) -> Any:
        path = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        found = {
            "/account/me": me,
            "/sync": RU_SYNC,
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
        f"localStorage.setItem('targum:language', '{language}');"
    )
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    page.goto(SITE + "/progress")
    return context, page, thrown


def shoot(page: Any, name: str) -> None:
    where = os.environ.get("TARGUM_SHOTS")
    if where:
        page.locator("#next").screenshot(path=str(Path(where) / f"{name}.png"))


def fits(page: Any) -> bool:
    return bool(
        page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
    )


NAMES = {
    "en": {
        "aspect": "Aspect",
        "cases": "Cases",
        "title": "Your biggest gap: perfective verbs",
        "cases-title": "Your biggest gap: the animate accusative",
        "known": "known",
        "more": "More",
    },
    "ru": {
        "aspect": "Вид",
        "cases": "Падежи",
        "title": "Ваш главный пробел: глаголы совершенного вида",
        "cases-title": "Ваш главный пробел: винительный падеж, одушевлённые",
        "known": "знаю",
        "more": "Ещё",
    },
}


@pytest.mark.parametrize("interface", ["en", "ru"])
@pytest.mark.parametrize("width", [390, 1440])
def test_the_tabs_the_gap_and_the_aspect_grid(chromium: Any, width: int, interface: str) -> None:
    names = NAMES[interface]
    context, page, thrown = open_page(chromium, {"russian": russian()}, width, interface)
    try:
        page.locator("#ru-aspect-grid").wait_for(timeout=10_000)
        assert page.locator("#next-title").inner_text() == names["title"]
        assert page.locator("#gap-said").is_visible()
        aspect = page.get_by_role("tab", name=names["aspect"])
        cases = page.get_by_role("tab", name=names["cases"])
        assert aspect.get_attribute("aria-selected") == "true", "the headline's tab"
        assert cases.get_attribute("aria-selected") == "false"
        assert page.locator("#ru-aspect").is_visible() and page.locator("#ru-cases").is_hidden()
        assert page.locator("#gap").is_hidden(), "Hebrew's grids stay out of a Russian page"
        # The perfective present: hatched as no such form, spoken so, never a dash.
        none = page.locator("#ru-aspect-grid td.none")
        assert none.count() == 1
        assert none.locator(".sr").inner_text() in ("No such form", "Такой формы нет")
        assert page.locator("#ru-aspect-grid tr.weakest").count() == 1
        # Aspect pairs under the grid; More shut on load.
        assert page.locator("#ru-part-pairs .next-row").count() == 3
        more = page.locator("#ru-more")
        assert more.is_visible() and more.get_attribute("open") is None
        assert page.locator("#ru-part-motion").is_hidden()
        # The headline's gap sits above the tabs.
        measured = page.evaluate(
            """() => {
              const box = (s) => document.querySelector(s).getBoundingClientRect();
              return {said: box('#gap-said'), tabs: box('#ru-tabs')};
            }"""
        )
        assert measured["tabs"]["top"] > measured["said"]["bottom"]
        if width < 600:
            tab = page.locator("#ru-tab-aspect").bounding_box()
            assert tab and tab["height"] >= 44
        assert fits(page)
        shoot(page, f"ru-progress-{interface}-{width}-aspect")
        assert not thrown, thrown
    finally:
        context.close()


@pytest.mark.parametrize("interface", ["en", "ru"])
@pytest.mark.parametrize("width", [390, 1440])
def test_a_square_opens_its_forms_one_list_at_a_time(
    chromium: Any, width: int, interface: str
) -> None:
    names = NAMES[interface]
    context, page, thrown = open_page(chromium, {"russian": russian()}, width, interface)
    try:
        page.locator("#ru-aspect-grid").wait_for(timeout=10_000)
        first = page.locator("#ru-aspect-grid tr.weakest .grammar-cell").first
        first.click()
        box = page.locator("#ru-aspect-grid-words")
        assert box.is_visible() and first.get_attribute("aria-expanded") == "true"
        rows = box.locator(".next-row")
        assert rows.count() == 2
        top = rows.first.inner_text()
        assert "сказал" in top and "сказать" in top and "say" in top
        assert names["known"] in top
        assert "12" in rows.nth(1).inner_text(), "met 12 times"
        shoot(page, f"ru-progress-{interface}-{width}-list")
        # Another square shuts the first.
        second = page.locator("#ru-aspect-grid tr.weakest .grammar-cell").nth(1)
        second.click()
        assert first.get_attribute("aria-expanded") == "false"
        assert page.locator(".grammar-words:not([hidden])").count() == 1
        # The same square again shuts it.
        second.click()
        assert box.is_hidden()
        # Changing tab shuts an open list; the Cases tab holds its own two.
        second.click()
        page.get_by_role("tab", name=names["cases"]).click()
        assert box.is_hidden()
        assert page.locator("#ru-cases").is_visible() and page.locator("#ru-aspect").is_hidden()
        assert page.locator("#ru-cases-grid tbody tr").count() == 7, "the animate row too"
        assert page.locator("#ru-place-grid tbody tr").count() == 4
        assert page.locator("#ru-place-grid tr.weakest").count() == 0, "never the gap"
        page.locator("#ru-place-grid .grammar-cell").first.click()
        assert "в доме" in page.locator("#ru-place-grid-words").inner_text()
        assert fits(page)
        shoot(page, f"ru-progress-{interface}-{width}-cases")

        # More opens with no script and holds its three, in a course's order.
        page.locator("#ru-more > summary").click()
        assert page.locator("#ru-more").get_attribute("open") is not None
        parts = page.locator("#ru-more-parts > .gap-part")
        assert [parts.nth(n).get_attribute("id") for n in range(parts.count())] == [
            "ru-part-motion",
            "ru-part-soft",
            "ru-part-forms",
        ]
        assert page.locator("#ru-motion-grid .grammar-cell").count() == 2, "two pooled squares"
        assert page.locator("#ru-part-motion .motion-pairs .next-row").count() == 3
        assert page.locator("#ru-soft-grid tbody tr").count() == 2
        assert "B1" in page.locator("#ru-part-forms").inner_text()
        page.locator("#ru-soft-grid .grammar-cell").first.click()
        assert page.locator("#ru-soft-grid-words").is_visible()
        assert page.locator("#ru-place-grid-words").is_hidden(), "one list across all of it"
        assert fits(page)
        shoot(page, f"ru-progress-{interface}-{width}-more")
        # Shutting More shuts the list open in it.
        page.locator("#ru-more > summary").click()
        page.wait_for_function("!document.querySelector('#ru-more').open")
        assert page.locator("#ru-soft-grid-words").is_hidden()
        assert not thrown, thrown
    finally:
        context.close()


@pytest.mark.parametrize("interface", ["en", "ru"])
def test_a_case_gap_opens_the_cases_tab(chromium: Any, interface: str) -> None:
    names = NAMES[interface]
    context, page, thrown = open_page(chromium, {"russian": russian("cases")}, 1440, interface)
    try:
        page.locator("#ru-cases-grid").wait_for(timeout=10_000)
        assert page.locator("#next-title").inner_text() == names["cases-title"]
        assert page.get_by_role("tab", name=names["cases"]).get_attribute("aria-selected") == "true"
        assert page.locator("#ru-cases-grid tr.weakest").count() == 1
        assert "брата" in page.locator("#gap-said").inner_text()
        # Never remembered: the tab follows the headline, and arrows move between them.
        page.get_by_role("tab", name=names["cases"]).focus()
        page.keyboard.press("ArrowLeft")
        assert (
            page.get_by_role("tab", name=names["aspect"]).get_attribute("aria-selected") == "true"
        )
        assert not thrown, thrown
    finally:
        context.close()


def test_with_one_grid_there_are_no_tabs(chromium: Any) -> None:
    said = russian()
    said.update(aspect=None, pairs=None, motion=None, soft=None, forms=None, lead="cases")
    context, page, thrown = open_page(chromium, {"russian": said}, 390)
    try:
        page.locator("#ru-cases-grid").wait_for(timeout=10_000)
        assert page.locator("#ru-tabs").is_hidden()
        assert page.locator("#ru-cases").is_visible()
        assert page.locator("#ru-more").is_hidden(), "nothing in More, no More"
        assert not thrown, thrown
    finally:
        context.close()


def test_a_hebrew_page_draws_none_of_it(chromium: Any) -> None:
    context, page, thrown = open_page(
        chromium, dict(BOTH, lead="binyan", russian=russian()), 1440, language="he"
    )
    try:
        page.locator(".mishkal-row").first.wait_for(state="attached", timeout=10_000)
        assert page.locator("#gap-ru").is_hidden()
        assert page.locator("#gap").is_visible()
        assert page.locator("#next-title").inner_text() == "Your biggest gap: הִתְפַּעֵל verbs"
        assert page.get_by_role("tab", name="Binyanim").get_attribute("aria-selected") == "true"
        assert not thrown, thrown
    finally:
        context.close()
