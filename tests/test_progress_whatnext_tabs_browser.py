"""What next is quick to take in (design.md §12, 2026-11-03), drawn in a browser at 390,
1024 and 1440.

Before any tap: the headline, its sentence and the two lists. Under them "Grammar", with
Binyanim | Mishkalim as its `.seg` of real tabs, one grid at a time, the tab of the
headline's gap open on every load. Changing tab shuts an open list of words; arrows move
between the tabs. With one kind only there are no tabs, which
`test_progress_mishkal_browser.py` pins with the grid alone. The grid and the list themselves
are `test_progress_gap_browser.py` and `test_progress_mishkal_browser.py`.

`TARGUM_SHOTS=<dir>` saves a screenshot of each width there. Skips itself without
Playwright.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from test_progress_mishkal_browser import BOTH, open_page

pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

BINYAN = dict(BOTH, lead="binyan")


def shoot(page: Any, name: str) -> None:
    where = os.environ.get("TARGUM_SHOTS")
    if where:
        page.locator("#next").screenshot(path=str(Path(where) / f"{name}.png"))


@pytest.mark.parametrize("width", [390, 1024, 1440])
def test_the_gap_and_the_two_lists_come_before_the_grammar(chromium: Any, width: int) -> None:
    context, page, thrown = open_page(chromium, BINYAN, width)
    try:
        assert page.locator("#next-title").inner_text() == "Your biggest gap: הִתְפַּעֵל verbs"
        said = page.locator("#gap-said")
        # The gloss and two words met stay with the headline they explain (David).
        assert "Hitpa'el verbs are often reflexive or mutual." in said.inner_text()
        binyanim = page.get_by_role("tab", name="Binyanim")
        mishkalim = page.get_by_role("tab", name="Mishkalim")
        assert binyanim.get_attribute("aria-selected") == "true", "the headline's tab"
        assert mishkalim.get_attribute("aria-selected") == "false"
        assert page.locator("#gap-grammar").is_visible()
        assert page.locator("#gap-mishkal").is_hidden(), "one grid at a time"
        assert page.get_by_role("heading", name="Grammar").is_visible(), "the heading stays"
        assert page.get_by_role("tabpanel").count() == 1

        measured = page.evaluate(
            """() => {
              const box = (s) => document.querySelector(s).getBoundingClientRect();
              return {
                scroll: document.documentElement.scrollWidth,
                client: document.documentElement.clientWidth,
                said: box('#gap-said'), lists: box('#next .next-halves'),
                head: box('#grammar-title'), tabs: box('#grammar-tabs'),
                tab: box('#grammar-tab-binyan'), grid: box('#gap-grammar'),
              };
            }"""
        )
        assert measured["scroll"] <= measured["client"], measured
        assert measured["lists"]["top"] >= measured["said"]["bottom"], "the lists follow the gap"
        assert measured["tabs"]["top"] >= measured["lists"]["bottom"], "Grammar sits below"
        assert measured["grid"]["top"] >= measured["tabs"]["bottom"]
        # The heading and its tabs share a line at every width.
        assert measured["tabs"]["top"] < measured["head"]["bottom"]
        if width < 600:
            assert measured["tab"]["height"] >= 44, "a tab answers a thumb over 44px (§8)"
        shoot(page, f"whatnext-{width}")
        assert not thrown, thrown
    finally:
        context.close()


@pytest.mark.parametrize("width", [390, 1024, 1440])
def test_a_mishkal_gap_opens_the_mishkalim_tab(chromium: Any, width: int) -> None:
    context, page, thrown = open_page(chromium, BOTH, width)
    try:
        assert page.get_by_role("tab", name="Mishkalim").get_attribute("aria-selected") == "true"
        assert page.locator("#gap-mishkal").is_visible()
        assert page.locator("#gap-grammar").is_hidden()
        assert page.locator(".mishkal tr.weakest").is_visible()
        shoot(page, f"whatnext-{width}-mishkal")
        assert not thrown, thrown
    finally:
        context.close()


@pytest.mark.parametrize("width", [390, 1024, 1440])
def test_changing_tab_shuts_an_open_list_and_a_load_opens_the_headlines_tab(
    chromium: Any, width: int
) -> None:
    context, page, thrown = open_page(chromium, BINYAN, width)
    try:
        square = page.locator("#grammar tr.weakest .grammar-cell").nth(1)
        square.click()
        assert page.locator("#grammar-words").is_visible()
        shoot(page, f"whatnext-{width}-open")
        page.get_by_role("tab", name="Mishkalim").click()
        assert page.locator("#gap-mishkal").is_visible()
        assert page.locator("#grammar-words").is_hidden()
        assert square.get_attribute("aria-expanded") == "false"
        shoot(page, f"whatnext-{width}-other")
        # Never remembered: the next load opens the headline's tab again.
        page.reload()
        page.locator(".mishkal-row").first.wait_for(state="attached", timeout=10_000)
        assert page.get_by_role("tab", name="Binyanim").get_attribute("aria-selected") == "true"
        assert not thrown, thrown
    finally:
        context.close()


def test_arrows_move_between_the_tabs(chromium: Any) -> None:
    context, page, thrown = open_page(chromium, BINYAN, 1440)
    try:
        binyanim = page.get_by_role("tab", name="Binyanim")
        mishkalim = page.get_by_role("tab", name="Mishkalim")
        assert binyanim.get_attribute("tabindex") == "0"
        assert mishkalim.get_attribute("tabindex") == "-1"
        binyanim.focus()
        page.keyboard.press("ArrowRight")
        assert mishkalim.get_attribute("aria-selected") == "true"
        assert page.evaluate("document.activeElement.id") == "grammar-tab-mishkal"
        assert page.locator("#gap-grammar").is_hidden()
        page.keyboard.press("Home")
        assert binyanim.get_attribute("aria-selected") == "true"
        assert not thrown, thrown
    finally:
        context.close()


@pytest.mark.parametrize("width", [390, 1024, 1440])
def test_the_russian_tabs_say_their_drafts(chromium: Any, width: int) -> None:
    context, page, thrown = open_page(chromium, BINYAN, width, interface="ru")
    try:
        assert page.get_by_role("heading", name="Грамматика").is_visible()
        assert page.get_by_role("tab", name="Биньяны").get_attribute("aria-selected") == "true"
        assert page.get_by_role("tab", name="Мишкали").is_visible()
        scroll = page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
        assert scroll
        shoot(page, f"whatnext-{width}-ru")
        assert not thrown, thrown
    finally:
        context.close()
