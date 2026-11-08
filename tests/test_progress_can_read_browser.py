"""What you can read in our library, on Your Progress for French, Russian and Italian
(design.md §12, "Progress leads with what you can read", 2026-11-08).

Each loads the page the server renders, with the account's answers stubbed, at a desk and
as a touch phone: the heading, the line saying what the level counts, the three rows with
their exact counts, the ready row opening Read it now, Home's find under them, and How we
measure closed until pressed, with its four papers. The level itself is said once, on the
Reading level card: "About A2", and "310 more dictionary words to B1". Hebrew, sent no
counts, keeps Texts by level and its card. With `TARGUM_SHOTS` set to a folder, before
and after are saved there at 390 and 1440, in English and Russian, light and dark, as
`can-read-<when>-<page>-<width>-<scheme>.png`.

Skips itself without Playwright.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from test_progress_level_browser import ladder, story
from test_progress_states_browser import SITE, me, record

from targum.render.builder import progress_page

pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

A2 = {
    "scale": "cefr",
    "letter": "A2",
    "name": "A2",
    "cefr": "",
    "next": {"letter": "B1", "name": "B1"},
    "toward": 0.4,
    "toGo": 310,
}


def told(coverage: dict[str, int] | None = None, level: Any = A2) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "known": 1400,
        "ladder": ladder(2, (40, 12, 3), reached=2, to_go=(310, 900, 1500, 2500)),
        "here": 1,
        "next": 2,
        "level": level,
    }
    if coverage is not None:
        fields["coverage"] = {**coverage, "among": 5000}
    return story(**fields)


COUNTS = {"ready": 14, "stretch": 37, "notYet": 201}

SEEN = """() => {
  const at = (id) => document.getElementById(id);
  const shown = (one) => !!one && one.offsetParent !== null;
  const card = at('can-read');
  const rows = [...card.querySelectorAll('#can-read-rows .touch-row')];
  const press = at('can-read-how-press');
  const find = at('can-read-find');
  return {
    card: shown(card),
    ladder: shown(at('ladder')),
    head: at('can-read-head').textContent,
    line: shown(at('can-read-line')) ? at('can-read-line').textContent : null,
    rows: rows.map((row) => ({
      name: row.querySelector('.touch-name').textContent,
      state: row.querySelector('.touch-state').textContent,
      link: row.tagName === 'A' ? row.getAttribute('href') : null,
      height: row.getBoundingClientRect().height,
    })),
    find: find && shown(find) ? {text: find.textContent, href: find.getAttribute('href'),
      height: find.getBoundingClientRect().height} : null,
    open: press.getAttribute('aria-expanded'),
    how: shown(at('can-read-how')),
    pressHeight: press.getBoundingClientRect().height,
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  };
}"""


def open_page(
    chromium: Any,
    monkeypatch: pytest.MonkeyPatch,
    language: str,
    said: dict[str, Any],
    width: int,
    page_language: str = "en",
    find: bool = True,
    scheme: str = "light",
) -> tuple[Any, Any, list[str]]:
    if find:
        monkeypatch.setenv("TARGUM_FIND_BUTTON", "1")
    else:
        monkeypatch.delenv("TARGUM_FIND_BUTTON", raising=False)
    html = progress_page("", page_language)
    synced = record(40, 6, 9)
    for word in synced["words"]:
        word["language"] = language
    for doc in synced["docs"]:
        doc["language"] = language
    answers: dict[str, Any] = {
        "/account/me": dict(me(True), language=language, learning=[language]),
        "/sync": synced,
        "/account/story": said,
        "/account/totals": {"signedIn": True, "on": True, "totals": []},
        "/account/reading": {"signedIn": True, "reading": {}},
    }

    def answer(route: Any, request: Any) -> Any:
        path = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        body = answers.get(path, {"signedIn": True})
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    phone = width < 600
    context = chromium.browser().new_context(
        viewport={"width": width, "height": 900},
        has_touch=phone,
        is_mobile=phone,
        color_scheme=scheme,
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
    page.wait_for_load_state("networkidle")
    return context, page, thrown


NAMES = {"fr": "French", "ru": "Russian", "it": "Italian"}


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("language", ["fr", "ru", "it"])
def test_the_three_rows_the_find_and_the_fold(
    chromium: Any, monkeypatch: pytest.MonkeyPatch, language: str, width: int
) -> None:
    context, page, thrown = open_page(chromium, monkeypatch, language, told(COUNTS), width)
    try:
        page.locator("#can-read").wait_for(state="visible", timeout=10_000)
        seen = page.evaluate(SEEN)
        assert seen["card"] and not seen["ladder"], "the card stands in the ladder's place"
        assert seen["head"] == "What you can read in our library"
        assert seen["line"] == (
            f"Counted in dictionary words, among {NAMES[language]}'s 5,000 most common."
        )
        # The level is said once, on the Reading level card.
        assert page.locator("#level-big").text_content() == "About A2"
        assert page.locator("#level-togo").text_content() == "310 more dictionary words to B1"
        assert [(row["name"], row["state"]) for row in seen["rows"]] == [
            ("14 texts", "Ready for you: you know 98% of their words"),
            ("37 texts", "A stretch: 95 to 98%"),
            ("201 texts", "Not yet: under 95%"),
        ]
        links = [row["link"] for row in seen["rows"]]
        assert links == ["/library#see/now", None, None], links
        assert all(row["height"] >= 44 for row in seen["rows"]), seen["rows"]
        assert seen["find"] is not None
        assert seen["find"]["text"] == "Find something to read"
        assert seen["find"]["href"] == "/#read-card"
        assert page.get_by_text(
            "Want something else? We'll look across the web for a video, article or podcast "
            "at your level."
        ).is_visible()
        # Closed at first, and opened by its press.
        assert seen["open"] == "false" and not seen["how"]
        page.locator("#can-read-how-press").click()
        assert page.locator("#can-read-how").is_visible()
        assert page.locator("#can-read-how-press").get_attribute("aria-expanded") == "true"
        how = page.locator("#can-read-how")
        for line in (
            "You learn best from texts you almost fully understand, with a few new words on "
            "each page. This is called comprehensible input, or i+1.",
            "Readers understand a text well when they know about 98% of its words. At 95%, "
            "many still follow it, with more effort. The more words you know, the more you "
            "understand. We count only the most common words because they make up most of "
            "any page.",
            "The level is a rough guide. Learners at one level know quite different numbers "
            "of words, so we say “about”.",
        ):
            assert how.get_by_text(line, exact=True).is_visible(), line
        papers = how.locator("a").evaluate_all(
            "(all) => all.map((one) => [one.textContent, one.getAttribute('href')])"
        )
        assert papers == [
            ["Hu and Nation, 2000", "https://nflrc.hawaii.edu/rfl/item/43"],
            [
                "Laufer and Ravenhorst-Kalovski, 2010",
                "https://scholarspace.manoa.hawaii.edu/bitstream/10125/66648/1/22_1_10125_66648_laufer.pdf",
            ],
            [
                "Schmitt, Jiang and Grabe, 2011",
                "https://www.lextutor.ca/cover/papers/schmitt_etal_2011.pdf",
            ],
            ["Milton, 2010", "https://www.eurosla.org/monographs/EM01/211-232Milton.pdf"],
        ]
        page.locator("#can-read-how-press").click()
        assert not page.locator("#can-read-how").is_visible()
        if width < 600:
            assert seen["pressHeight"] >= 44 and seen["find"]["height"] >= 44
        assert seen["scroll"] <= seen["client"], "nothing sideways"
        assert not thrown, thrown
    finally:
        context.close()


def test_no_ready_text_is_no_link_and_the_line_stands_without_a_level(
    chromium: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    said = told({"ready": 0, "stretch": 1, "notYet": 1}, level=None)
    context, page, thrown = open_page(chromium, monkeypatch, "it", said, 390)
    try:
        page.locator("#can-read").wait_for(state="visible", timeout=10_000)
        seen = page.evaluate(SEEN)
        assert seen["line"] == "Counted in dictionary words, among Italian's 5,000 most common."
        assert [(row["name"], row["link"]) for row in seen["rows"]] == [
            ("0 texts", None),
            ("1 text", None),
            ("1 text", None),
        ]
        assert not thrown, thrown
    finally:
        context.close()


def test_without_the_find_switch_there_is_no_find(
    chromium: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    context, page, thrown = open_page(chromium, monkeypatch, "fr", told(COUNTS), 1440, find=False)
    try:
        page.locator("#can-read").wait_for(state="visible", timeout=10_000)
        seen = page.evaluate(SEEN)
        assert seen["find"] is None
        assert page.locator("#can-read").get_by_text("Want something else?").count() == 0
        assert not thrown, thrown
    finally:
        context.close()


def test_russian_says_it_in_russian(chromium: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    context, page, thrown = open_page(chromium, monkeypatch, "it", told(COUNTS), 390, "ru")
    try:
        page.locator("#can-read").wait_for(state="visible", timeout=10_000)
        seen = page.evaluate(SEEN)
        assert seen["head"] == "Что вы можете читать в нашей библиотеке"
        assert seen["line"] == (
            "Считаем словарные слова среди 5\u00a0000 самых частых слов на итальянском."
        )
        assert page.locator("#level-big").text_content() == "Примерно A2"
        assert page.locator("#level-togo").text_content() == "ещё 310 словарных слов до уровня B1"
        assert [row["name"] for row in seen["rows"]] == ["14 текстов", "37 текстов", "201 текст"]
        assert seen["find"] is not None and seen["find"]["text"] == "Найти, что почитать"
        assert seen["scroll"] <= seen["client"], "nothing sideways"
        assert not thrown, thrown
    finally:
        context.close()


def test_hebrew_keeps_texts_by_level(chromium: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """The server sends Hebrew no counts, and its card is as it was."""
    context, page, thrown = open_page(chromium, monkeypatch, "he", told(), 1440)
    try:
        page.locator("#ladder").wait_for(state="visible", timeout=10_000)
        seen = page.evaluate(SEEN)
        assert seen["ladder"] and not seen["card"]
        assert page.locator("#touchstones .touch-row").count() == 7
        assert page.locator("#level-big").text_content() == "A2"
        assert page.locator("#level-togo").text_content() == "310 words to B1"
        assert not thrown, thrown
    finally:
        context.close()


@pytest.mark.skipif(not os.environ.get("TARGUM_SHOTS"), reason="TARGUM_SHOTS names no folder")
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("page_language", ["en", "ru"])
@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("when", ["before", "after"])
def test_shots(
    chromium: Any,
    monkeypatch: pytest.MonkeyPatch,
    when: str,
    width: int,
    page_language: str,
    scheme: str,
) -> None:
    """Before is the story with no counts, which the page draws as master does: Texts by
    level and its words to go. After is the same reader with the counts."""
    said = told(COUNTS if when == "after" else None)
    context, page, _ = open_page(
        chromium, monkeypatch, "it", said, width, page_language, scheme=scheme
    )
    try:
        page.locator("#can-read" if when == "after" else "#ladder").wait_for(
            state="visible", timeout=10_000
        )
        folder = os.environ["TARGUM_SHOTS"]
        name = f"can-read-{when}-{page_language}-{width}-{scheme}"
        page.screenshot(path=f"{folder}/{name}.png", full_page=True)
        if when == "after":
            page.locator("#can-read-how-press").click()
            page.screenshot(path=f"{folder}/{name}-open.png", full_page=True)
    finally:
        context.close()
