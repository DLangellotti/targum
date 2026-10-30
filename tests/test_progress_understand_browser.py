"""How much Hebrew you understand, in a browser at 390 and 1440 (targum-internal#575).

design.md §12, "How much Hebrew you understand is measured on a fixed yardstick"
(2026-10-30). The page the server renders, with the account's answers stubbed: the card
stands where "Words you knew" stood, the picker opens and chooses by mouse and by
keyboard, each choice says its own percentage, nothing scrolls sideways, and a thumb's
height on a phone. With `TARGUM_SHOTS` set, each width is saved as
`understand-<width>.png`.

Skips itself without Playwright.
"""

from __future__ import annotations

import datetime
import os
from typing import Any

import pytest
from test_progress_level_browser import SITE, a_record, open_state

pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

TODAY = datetime.date.today()


def noon(when: datetime.date) -> int:
    return int(datetime.datetime.combine(when, datetime.time(12)).timestamp() * 1000)


def with_yardsticks() -> dict[str, Any]:
    """The reading record, and three yardsticks with a line from two months back."""
    began = (TODAY.replace(day=1) - datetime.timedelta(days=40)).replace(day=1)
    last_month = (TODAY.replace(day=1) - datetime.timedelta(days=1)).replace(day=5)
    answer = a_record()

    def entry(percent: int, base: float, gain: float) -> dict[str, Any]:
        return {
            "percent": percent,
            "base": base,
            "days": [
                {"day": last_month.isoformat(), "gain": gain},
                {"day": TODAY.isoformat(), "gain": round(percent / 100 - base - gain, 6)},
            ],
        }

    answer["understand"] = {
        "he": {
            "began": noon(began),
            "registers": {
                "conversation": entry(93, 0.88, 0.03),
                "news": entry(87, 0.79, 0.04),
                "bible": entry(54, 0.46, 0.04),
            },
        }
    }
    return answer


SEEN = """() => {
  const box = (one) => one.getBoundingClientRect();
  const card = document.getElementById('understand');
  const options = [...document.querySelectorAll('#understand-list [role="option"]')];
  return {
    shown: !card.hidden && box(card).height > 0,
    old: !document.getElementById('reading').hidden,
    chosen: document.getElementById('understand-chosen').textContent,
    expanded: document.getElementById('understand-open').getAttribute('aria-expanded'),
    listShown: !document.getElementById('understand-list').hidden,
    options: options.map((one) => one.innerText.replace(/\\s+/g, ' ').trim()),
    heights: options.map((one) => box(one).height),
    open: box(document.getElementById('understand-open')).height,
    said: document.getElementById('understand-said').innerText,
    read: document.getElementById('understand-read').innerText,
    pressed: [...document.querySelectorAll('#understand-by button')]
      .filter((one) => one.getAttribute('aria-pressed') === 'true').map((one) => one.textContent),
    wide: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
    card: [box(card).x, box(card).y, box(card).width],
    lead: ((one) => [one.x, one.bottom])(box(document.querySelector('.level-lead'))),
  };
}"""


@pytest.mark.parametrize("width", [1440, 390])
def test_the_card_picks_a_yardstick_by_mouse_and_by_keyboard(chromium: Any, width: int) -> None:
    context, page, thrown, _ = open_state(chromium, "months", width, reading=with_yardsticks())
    try:
        page.goto(SITE + "/progress")
        page.locator("#understand").wait_for(state="visible", timeout=10_000)
        page.wait_for_load_state("networkidle")
        seen = page.evaluate(SEEN)
        assert seen["shown"] and not seen["old"], "in the place of Words you knew"
        assert seen["chosen"] == "a news article", "news for everyone"
        assert seen["pressed"] == ["Month"]
        assert seen["said"].startswith(
            "You know 87% of the words in a typical news article, up from 79% in "
        )
        assert seen["read"].startswith("In what you read this month you knew "), seen["read"]
        assert seen["wide"], "nothing sideways"
        floor = 44 if width < 600 else 40
        assert seen["open"] >= floor, seen["open"]
        if width > 1000:
            assert abs(seen["card"][0] - seen["lead"][0]) <= 1 and seen["card"][1] > seen["lead"][1]

        page.locator("#understand-open").click()
        seen = page.evaluate(SEEN)
        assert seen["listShown"] and seen["expanded"] == "true"
        assert seen["options"] == [
            "Everyday conversation 93%",
            "✓ A news article 87%",
            "The Bible 54%",
        ]
        assert all(height >= 44 for height in seen["heights"]), seen["heights"]
        assert seen["wide"], "the open list stays on the screen"
        shots = os.environ.get("TARGUM_SHOTS")
        if shots:
            page.screenshot(path=f"{shots}/understand-open-{width}.png", full_page=True)
        page.locator("#understand-list [data-register='conversation']").click()
        seen = page.evaluate(SEEN)
        assert not seen["listShown"] and seen["chosen"] == "everyday conversation"
        assert seen["said"].startswith("You know 93% of the words in everyday conversation")

        # By keyboard: down opens on the chosen one, down again moves, Enter chooses,
        # and the focus comes back to the button.
        page.locator("#understand-open").focus()
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Enter")
        seen = page.evaluate(SEEN)
        assert seen["chosen"] == "the Bible", seen
        assert page.evaluate("document.activeElement.id") == "understand-open"
        # Escape closes without choosing.
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowUp")
        page.keyboard.press("Escape")
        seen = page.evaluate(SEEN)
        assert not seen["listShown"] and seen["chosen"] == "the Bible"

        page.get_by_role("button", name="Week").last.click()
        assert page.evaluate(SEEN)["pressed"] == ["Week"]
        page.reload()
        page.locator("#understand").wait_for(state="visible", timeout=10_000)
        page.wait_for_load_state("networkidle")
        seen = page.evaluate(SEEN)
        assert seen["chosen"] == "the Bible" and seen["pressed"] == ["Week"], "remembered here"
        if shots:
            page.locator("#understand-by button[data-by='month']").click()
            page.locator("#understand-list").evaluate("(list) => list.hidden = true")
            page.screenshot(path=f"{shots}/understand-{width}.png", full_page=True)
        assert not thrown, thrown
    finally:
        context.close()
