"""Your Progress's Level section, every state of design.md §14.1 at 390 and 1440
(targum-internal#553; §12, "Your level leads with what you can read", 2026-10-28).

Signed out, loading, error, week one, a few weeks, months, the top rung, Aramaic, Yiddish,
French on the European scale alone, and the Russian interface: each loads the page the
server renders, with the account's answers stubbed, at a desk and as a touch phone. Each
must draw what it promises, print no percentage anywhere in the section, never scroll
sideways, give every row a thumb's height, and throw nothing. With `TARGUM_SHOTS` set to
a folder, each state is saved there as `level-<state>-<width>.png` for the card.

Skips itself without Playwright.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from test_progress_states_browser import SITE, me, record

from targum.render.builder import progress_page

pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)


def rung(kind: str, state: str, readable: int = 0, name: str = "") -> dict[str, Any]:
    return {
        "kind": kind,
        "name": name or kind,
        "share": None,
        "state": state,
        "texts": 9,
        "readable": readable,
    }


LEVELS = ("A1", "A2", "B1", "B2+")


def ladder(easy: int, counts: tuple[int, ...] = ()) -> list[dict[str, Any]]:
    """The four levels with the first `easy` easy, the one after it the next step."""
    out = []
    for at, kind in enumerate(LEVELS):
        state = "easy" if at < easy else "next" if at == easy else "ahead"
        out.append(rung(kind, state, counts[at] if at < len(counts) else 0))
    return out


def story(**fields: Any) -> dict[str, Any]:
    return {
        "signedIn": True,
        "library": True,
        "known": 0,
        "ladder": [],
        "here": None,
        "next": None,
        "level": None,
        "conversations": True,
        "texts": [],
        "words": [],
        **fields,
    }


ULPAN_BET = {
    "scale": "ulpan",
    "letter": "א+",
    "name": "aleph plus",
    "cefr": "A1",
    "next": {"letter": "ב", "name": "bet"},
    "toward": 0.38,
}
ULPAN_GIMEL = {
    "scale": "ulpan",
    "letter": "ג",
    "name": "gimel",
    "cefr": "B1",
    "next": {"letter": "ד", "name": "dalet"},
    "toward": 0.11,
}

#: Each state: what the page is asked with, and what Level must then say.
STATES: dict[str, dict[str, Any]] = {
    "signed-out": {
        "signed": False,
        "says": "Sign in to see which texts you can read on your own.",
    },
    "loading": {"hold": True, "says": "We're working out your level."},
    "error": {"fail": True, "says": "We couldn't load this part.", "press": "Try again"},
    "week-one": {
        "story": story(known=86, ladder=ladder(0), next=0),
        "says": "Start with beginner texts.",
        "press": "Open a conversation",
        "rows": 4,
        "foot": False,
    },
    "few-weeks": {
        "story": story(known=1240, ladder=ladder(1, (38, 4)), here=0, next=1, level=ULPAN_BET),
        "says": "You can read beginner texts on your own.",
        "press": "Show texts at your level",
        "rows": 4,
        "foot": "In ulpan terms you're at aleph plus (א׳+), about A1 on the European scale.",
        "next": "Next: bet ב׳",
    },
    "months": {
        "story": story(
            known=4730, ladder=ladder(3, (118, 143, 52, 11)), here=2, next=3, level=ULPAN_GIMEL
        ),
        "says": "You can read B1 texts on your own.",
        "press": "Show texts at your level",
        "rows": 4,
        "foot": "In ulpan terms you're at gimel (ג׳), about B1 on the European scale.",
        "next": "Next: dalet ד׳",
    },
    "top-rung": {
        "story": story(
            known=12500,
            ladder=ladder(4, (118, 143, 60, 40)),
            here=3,
            level={
                "scale": "ulpan",
                "letter": "ו",
                "name": "vav",
                "cefr": "C2",
                "next": None,
                "toward": None,
            },
        ),
        "says": "That's the hardest level in the Library.",
        "press": "Show texts at your level",
        "rows": 4,
        "foot": "In ulpan terms you're at vav (ו׳), about C2 on the European scale.",
        "bar": False,
    },
    "aramaic": {
        "language": "arc",
        "story": story(
            known=400,
            ladder=[
                rung("onkelos", "easy", 3),
                rung("former-prophets", "next"),
                rung("jonathan-torah", "ahead"),
                rung("latter-prophets", "ahead"),
                rung("writings", "ahead"),
            ],
            here=0,
            next=1,
        ),
        "says": "You can read Onkelos on your own.",
        "rows": 5,
        "foot": False,
    },
    "yiddish": {
        "language": "yi",
        "story": story(known=120, library=False),
        "says": "You know 120 words so far",
        "foot": False,
    },
    "french": {
        "language": "fr",
        "story": story(
            known=2100,
            ladder=ladder(2, (40, 12, 3)),
            here=1,
            next=2,
            level={
                "scale": "cefr",
                "letter": "B1",
                "name": "B1",
                "cefr": "",
                "next": {"letter": "B2", "name": "B2"},
                "toward": 0.25,
            },
        ),
        "says": "You can read A2 texts on your own.",
        "press": "Show texts at your level",
        "rows": 4,
        "foot": "On the European scale you're about B1. It runs from A1, for beginners, to C2.",
        "next": "Next: B2",
    },
    "russian": {
        "page": "ru",
        "story": story(
            known=4730, ladder=ladder(3, (118, 143, 52, 11)), here=2, next=3, level=ULPAN_GIMEL
        ),
        "title": "Уровень",
        "says": "Вы можете сами читать тексты уровня B1.",
        "press": "Показать тексты вашего уровня",
        "rows": 4,
        "foot": "По меркам ульпана у вас уровень гимель (ג׳)",
        "next": "Дальше — уровень далет ד׳",
    },
}

SEEN = """() => {
  const where = document.getElementById('where');
  const box = (one) => one.getBoundingClientRect();
  const shown = (one) => !!one && one.offsetParent !== null;
  const at = (id) => document.getElementById(id);
  const bar = at('level-bar');
  const all = (selector) => [...where.querySelectorAll(selector)];
  return {
    text: where.innerText,
    title: at('where-section').textContent,
    labels: all('[aria-label]').map((one) => one.getAttribute('aria-label')),
    rows: all('#touchstones .touch-row').filter(shown).map((one) => box(one).height),
    foot: shown(at('level-foot')) ? at('level-said').textContent : '',
    bar: shown(bar)
      ? {role: bar.getAttribute('role'), label: bar.getAttribute('aria-label'),
         hidden: bar.getAttribute('aria-hidden'),
         nextHidden: at('level-next').closest('[aria-hidden]') !== null,
         height: box(bar).height, next: at('level-next').textContent}
      : null,
    letters: all('bdi').map((one) => [one.getAttribute('lang'), one.getAttribute('dir')]),
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
  };
}"""


def open_state(chromium: Any, name: str, width: int) -> tuple[Any, Any, list[str]]:
    spec = STATES[name]
    signed = spec.get("signed", True)
    language = spec.get("language", "he")
    html = progress_page("", spec.get("page", "en"))
    synced = record(40, 6, 9)
    for word in synced["words"]:
        word["language"] = language
    for doc in synced["docs"]:
        doc["language"] = language
    answers: dict[str, Any] = {
        "/account/me": dict(me(signed), language=language, learning=[language])
        if signed
        else me(False),
        "/sync": synced,
        "/account/story": spec.get("story", story()),
        "/account/totals": {"signedIn": True, "on": True, "totals": []},
        "/account/reading": {"signedIn": True, "reading": {}},
    }

    def answer(route: Any, request: Any) -> Any:
        path = request.url[len(SITE) :].split("?")[0]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        if path == "/account/story" and spec.get("hold"):
            return None  # Never answered: the loading line stays.
        if path == "/account/story" and spec.get("fail"):
            return route.fulfill(status=500, content_type="text/plain", body="no")
        if not signed and path != "/account/me":
            return route.fulfill(
                status=401, content_type="application/json", body='{"signedIn": false}'
            )
        said = answers.get(path, {"signedIn": signed})
        return route.fulfill(status=200, content_type="application/json", body=json.dumps(said))

    phone = width < 600
    context = chromium.browser().new_context(
        viewport={"width": width, "height": 900}, has_touch=phone, is_mobile=phone
    )
    # Signed out, the words are this browser's own, as a reader's are before an account.
    vocab = {
        f"מלה{n}": {"status": 9, "surface": f"מלה{n}", "at": 1_790_000_000_000 + n}
        for n in range(40)
    }
    stored = json.dumps(json.dumps(vocab))
    context.add_init_script(
        "localStorage.setItem('targum:welcomed', '1');"
        f"localStorage.setItem('targum:language', '{language}');"
        + ("" if signed else f"localStorage.setItem('targum:vocab:{language}', {stored});")
    )
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    return context, page, thrown


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("state", list(STATES))
def test_every_level_state_is_drawn_without_a_percentage(
    chromium: Any, state: str, width: int
) -> None:
    spec = STATES[state]
    context, page, thrown = open_state(chromium, state, width)
    try:
        page.goto(SITE + "/progress")
        page.locator("#where").get_by_text(spec["says"], exact=False).first.wait_for(
            state="visible", timeout=10_000
        )
        if not spec.get("hold"):
            page.wait_for_load_state("networkidle")
        seen = page.evaluate(SEEN)
        shots = os.environ.get("TARGUM_SHOTS")
        if shots:
            page.screenshot(path=f"{shots}/level-{state}-{width}.png", full_page=True)

        assert seen["title"] == spec.get("title", "Level")
        assert "%" not in seen["text"], seen["text"]
        assert not [label for label in seen["labels"] if "%" in label], seen["labels"]
        assert seen["scroll"] <= seen["client"], seen
        if "press" in spec:
            press = (
                page.locator("#where")
                .get_by_role("link", name=spec["press"])
                .or_(page.locator("#where").get_by_role("button", name=spec["press"]))
            )
            assert press.first.is_visible(), spec["press"]
        if "rows" in spec:
            assert len(seen["rows"]) == spec["rows"]
            assert all(height >= 44 for height in seen["rows"]), seen["rows"]
        if spec.get("foot") is False:
            assert seen["foot"] == "" and seen["bar"] is None
        elif "foot" in spec:
            assert seen["foot"].startswith(spec["foot"]), seen["foot"]
            assert ["he", "rtl"] in seen["letters"] or spec.get("language") == "fr"
        if "next" in spec:
            assert seen["bar"] is not None
            assert seen["bar"]["next"] == spec["next"]
            # The bar is hidden from a screen reader and the Next line is not, so the line
            # is heard once and no percentage at all (#554, qa on targum#978).
            assert seen["bar"]["hidden"] == "true" and seen["bar"]["role"] is None, seen["bar"]
            assert not seen["bar"]["nextHidden"], seen["bar"]
            assert page.get_by_role("progressbar").count() == 0
            tree = page.locator("#level-toward").aria_snapshot()
            assert tree.count(spec["next"].split(" ")[-2]) == 1, tree
            assert 3 <= seen["bar"]["height"] <= 5, "a thin line"
        if spec.get("bar") is False:
            assert seen["bar"] is None
        assert not thrown, thrown
    finally:
        context.close()


COLUMNS = """() => [...document.querySelectorAll('#touchstones .touch-row')]
  .filter((row) => row.offsetParent !== null)
  .map((row) => {
    const at = (name) => {
      const one = row.querySelector('.' + name);
      return one ? [one.getBoundingClientRect().left, one.getBoundingClientRect().right] : null;
    };
    return {state: at('touch-state'), count: at('touch-count')};
  })"""


@pytest.mark.parametrize("state", ["months", "russian", "aramaic"])
def test_the_ladder_columns_line_up_row_to_row_at_a_desk(chromium: Any, state: str) -> None:
    """At 1440 the ladder is a board: name, state, count, each column starting where the
    row above's did. In Russian «Вам легко» and «Следующий шаг» stepped from row to row,
    because a longer count pushed its own row's state along; on the Aramaic ladder a row
    with nothing to read yet has no count, and its state slid right (targum-internal#554)."""
    spec = STATES[state]
    context, page, thrown = open_state(chromium, state, 1440)
    try:
        page.goto(SITE + "/progress")
        page.locator("#where").get_by_text(spec["says"], exact=False).first.wait_for(
            state="visible", timeout=10_000
        )
        page.wait_for_load_state("networkidle")
        rows = page.evaluate(COLUMNS)
        assert len(rows) >= 4, rows
        assert all(row["state"] for row in rows), rows
        for column in ("state", "count"):
            edges = {round(row[column][0]) for row in rows if row[column]}
            assert len(edges) <= 1, (column, rows)
        assert not thrown, thrown
    finally:
        context.close()
