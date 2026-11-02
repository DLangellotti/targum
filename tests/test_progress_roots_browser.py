"""The "from N roots" label under "words known" (design.md §12, '"from N roots" is a label on the
known-words count', 2026-11-02; targum-internal#594), drawn in a browser at 390 and 1440.

A second muted label on the known-words count, in the label's own colour and never a
figure of its own; absent where the account sends no count (no lexicon, another
language) or a count of none. The arithmetic is `test_root_card.py`.

`TARGUM_SHOTS=<dir>` saves a screenshot of the ledger at each width there. Skips itself
without Playwright.
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


@pytest.mark.parametrize("width", [1440, 390])
def test_the_roots_are_a_label_under_words_known(chromium: Any, width: int) -> None:
    context, page, thrown = open_page(chromium, dict(BOTH, roots=1412), width)
    try:
        label = page.locator("#counts .count-known .count-roots")
        label.wait_for(timeout=10_000)
        assert label.inner_text() == "from 1,412 roots", "exact, grouped, never rounded"
        measured = page.evaluate(
            """() => {
              const tile = document.querySelector('#counts .count-known');
              const spans = tile.querySelectorAll('span');
              const box = (n) => n.getBoundingClientRect();
              return {
                spans: spans.length,
                figures: tile.querySelectorAll('b').length,
                labelColor: getComputedStyle(spans[0]).color,
                rootsColor: getComputedStyle(spans[1]).color,
                labelSize: getComputedStyle(spans[0]).fontSize,
                rootsSize: getComputedStyle(spans[1]).fontSize,
                under: box(spans[1]).top >= box(spans[0]).bottom - 1,
                tiles: document.querySelectorAll('#counts > div').length,
                scroll: document.documentElement.scrollWidth,
                client: document.documentElement.clientWidth,
              };
            }"""
        )
        assert measured["spans"] == 2 and measured["figures"] == 1, "a label, not a figure"
        assert measured["rootsColor"] == measured["labelColor"], "muted, as the label is"
        assert measured["rootsSize"] == measured["labelSize"]
        assert measured["under"], "under words known"
        assert measured["scroll"] <= measured["client"], measured
        where = os.environ.get("TARGUM_SHOTS")
        if where:
            page.locator("#ledger").screenshot(path=str(Path(where) / f"roots-{width}.png"))
        assert not thrown, thrown
    finally:
        context.close()


@pytest.mark.parametrize("roots", [None, 0])
def test_no_count_no_label(chromium: Any, roots: int | None) -> None:
    context, page, thrown = open_page(chromium, dict(BOTH, roots=roots), 1440)
    try:
        page.locator("#counts .count-known").wait_for(timeout=10_000)
        assert page.locator(".count-roots").count() == 0
        assert not thrown, thrown
    finally:
        context.close()
