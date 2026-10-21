"""A free word list's cap, at the card (design.md §12, "Free and Plan, behind a switch",
2026-10-09), in a real browser, with the switch off and on.

Off, `/account/me` says `{"on": false}` and the 301st word is kept as every word always
was. On, for a free reader with 300 words being learned, the press is refused in the card
as a panel in place, with Start a plan greyed and See plans, and nothing is kept.

Skips itself unless Playwright and its Chromium are installed, as
`test_reader_browser.py` does, whose browser this borrows.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import test_occurrences_card_browser
import test_reader_browser
from test_occurrences_card_browser import NOUN
from test_reader_browser import opened

browser = test_reader_browser.browser
verb_page = test_occurrences_card_browser.verb_page

#: 300 words at stage 1, already in this browser's Hebrew list.
FULL = {f"x{n}": {"status": 1, "surface": f"x{n}", "band": "", "at": n + 1} for n in range(300)}
ME = {"signedIn": True, "email": "reader@example.com", "revision": 0, "counts": {}}


def press_just_met(chromium: Any, page_file: Path, plan: dict[str, Any]) -> dict[str, Any]:
    html = page_file.read_text(encoding="utf-8")
    context = opened(chromium)
    context.add_init_script(
        f"try {{ localStorage.setItem('targum:vocab:he', {json.dumps(json.dumps(FULL))}); }}"
        " catch (e) {}"
    )
    page = context.new_page()
    me = {**ME, "plan": plan}

    def answer(route: Any, request: Any) -> None:
        if "/account/me" in request.url:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(me))
        elif any(p in request.url for p in ("/sync", "/gloss", "/events", "/word/met")):
            route.fulfill(status=200, content_type="application/json", body="{}")
        else:
            route.fulfill(status=200, content_type="text/html", body=html)

    page.route("http://reader.test/**", answer)
    page.goto("http://reader.test/reader/a-build/reader/index.html?k=test")
    page.wait_for_selector(".pair")
    page.wait_for_function("() => window.TargumSync && window.TargumSync.who")
    tap = f"() => [...document.querySelectorAll('.w')].find((w) => w.textContent === '{NOUN}')"
    page.evaluate(tap + ".click()")
    page.wait_for_timeout(400)
    page.click(".gloss-card .levels .level-1")
    page.wait_for_timeout(300)
    got = page.evaluate(
        """(noun) => {
          const panel = document.querySelector('.gloss-card .list-full');
          const kept = JSON.parse(localStorage.getItem('targum:vocab:he') || '{}');
          return {
            panel: panel ? panel.textContent : null,
            start: panel ? panel.querySelector('.fault-go').disabled : null,
            see: panel ? panel.querySelector('.fault-see').getAttribute('href') : null,
            kept: Object.prototype.hasOwnProperty.call(kept, noun),
            card: !!document.querySelector('.gloss-card:not([hidden])'),
          };
        }""",
        NOUN,
    )
    context.close()
    return got


def test_off_the_three_hundred_and_first_word_is_kept(browser: Any, verb_page: Path) -> None:
    got = press_just_met(browser, verb_page, {"on": False})
    assert got["panel"] is None
    assert got["kept"] is True


def test_on_a_full_free_list_refuses_in_the_card(browser: Any, verb_page: Path) -> None:
    plan = {"on": True, "plan": "free", "credits": 60, "planCredits": 480, "words": 300}
    got = press_just_met(browser, verb_page, {**plan, "listed": 300, "topUps": []})
    assert got["kept"] is False
    assert got["panel"] and "holds 300 words on Free" in got["panel"]
    assert "Payments open soon" in got["panel"] and got["start"] is True
    assert got["see"].startswith("/plans")
    assert got["card"], "the card stays where the press was"


def test_on_the_plan_has_no_cap(browser: Any, verb_page: Path) -> None:
    plan = {"on": True, "plan": "plan", "credits": 480, "planCredits": 480, "words": None}
    got = press_just_met(browser, verb_page, {**plan, "listed": 300, "topUps": [60]})
    assert got["panel"] is None and got["kept"] is True
