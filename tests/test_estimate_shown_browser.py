"""Our estimate on home's card and on Your Progress, in a real browser at 390 and 1440
(design.md §12, "A text's figure is our estimate until your marks settle it" and "Your
level comes from your words check until your marks reach one", both 2026-11-04).

The beta review's B1 reader abroad (2026-11-03): the card said "7% known" under a
promise of 90%, and Progress listed texts at 6–8% under "Texts at your level now" beside
"Start with beginner texts". With `TARGUM_SHOTS` set to a folder, each state is saved
there as `estimate-<surface>-<width>.png`.

Skips itself without Playwright.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from test_home_one_card_browser import CARD, home
from test_progress_level_browser import SITE as PROGRESS_SITE
from test_progress_level_browser import open_state

from targum.finds import button

pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

WIDTHS = [390, 1440]

PICK = {
    "id": "everyday-news",
    "title": "חדשות היום",
    "language": "he",
    "kind": "article",
    "register": "modern",
    "minutes": 6,
    "reason": {"key": "suggest.estimated", "share": 92},
    "estimated": True,
    "fit": "band",
}

MORE = [
    {"id": f"m{n}", "title": title, "language": "he", "kind": kind, "percent": share,
     "reason": {"key": key, "share": share}, "fit": "band", **extra}
    for n, (title, kind, share, key, extra) in enumerate(
        [("תל אביב", "article", 93, "suggest.estimated", {"estimated": True}),
         ("הנסיך הקטן", "novel", 94, "suggest.estimated", {"estimated": True}),
         ("בבנק: פתיחת חשבון", "dialogue", 96, "suggest.known", {})]
    )
]  # fmt: skip


def shot(page: Any, name: str, width: int) -> None:
    where = os.environ.get("TARGUM_SHOTS", "").strip()
    if where:
        Path(where).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(where) / f"estimate-{name}-{width}.png"), full_page=True)


LABEL = """(selector) => {
  const one = document.querySelector(selector);
  if (!one) return null;
  const style = getComputedStyle(one);
  const number = getComputedStyle(one.parentElement);
  return {text: one.textContent, weight: style.fontWeight, colour: style.color,
          numberWeight: number.fontWeight, numberColour: number.color,
          height: one.getBoundingClientRect().height};
}"""


@pytest.fixture
def finds_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(button.FLAG, "1")


@pytest.mark.parametrize("width", WIDTHS)
def test_home_s_card_says_our_estimate_labelled(chromium: Any, finds_on: None, width: int) -> None:
    def suggest(body: dict[str, Any]) -> Any:
        return {"suggestion": PICK, "library": True, "more": MORE}

    context, page, thrown, _, _ = home(
        chromium.browser(), width, lambda body: {"pick": None}, suggest
    )
    try:
        page.wait_for_selector("#try-next .rc-pick")
        page.wait_for_selector("#more-fit:not([hidden])")
        got = page.evaluate(CARD)
        label = page.evaluate(LABEL, "#try-next .rc-known .estimate-ours")
        shot(page, "card", width)
    finally:
        context.close()
    assert not thrown, thrown
    assert got["known"] == "About 92% (our estimate)", got
    assert label is not None and label["text"] == "(our estimate)"
    assert label["weight"] == "400" and label["numberWeight"] == "600", "a quiet label"
    assert label["colour"] != label["numberColour"], "in the soft ink, beside the number"
    assert got["more"] == [
        "About 93% (our estimate) · Article",
        "About 94% (our estimate) · Book",
        "96% known · Conversation",
    ], got
    assert not got["sideways"], "nothing scrolls sideways"


TEXTS = """() => [...document.querySelectorAll('#level-rows .next-row')].map((row) => ({
  title: row.querySelector('.next-term').textContent,
  end: (row.querySelector('.next-end') || {}).textContent || '',
  quiet: !!row.querySelector('.next-end .estimate-ours'),
  height: row.getBoundingClientRect().height,
}))"""


@pytest.mark.parametrize("width", WIDTHS)
def test_progress_says_the_check_s_level_and_our_estimate_labelled(
    chromium: Any, width: int
) -> None:
    context, page, thrown, _ = open_state(chromium, "words-check", width)
    try:
        page.goto(PROGRESS_SITE + "/progress")
        page.locator("#where").get_by_text("From your words check").wait_for(timeout=10_000)
        page.wait_for_load_state("networkidle")
        page.locator("#level-rows .next-row").first.wait_for(timeout=10_000)
        rows = page.evaluate(TEXTS)
        lead = page.inner_text(".level-lead")
        wide = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        shot(page, "progress", width)
    finally:
        context.close()
    assert not thrown, thrown
    assert "From your words check" in lead and "Start with beginner texts" not in lead, lead
    assert "words to" not in lead, "no bar: the marks reach no rung yet"
    assert [(row["title"], row["end"], row["quiet"]) for row in rows] == [
        ("חדשות היום", "About 93% (our estimate)", True),
        ("סיפור קצר", "About 91% (our estimate)", True),
        ("במעלית", "96% known", False),
    ], rows
    assert not wide, "nothing scrolls sideways"
