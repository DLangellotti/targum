"""Your Progress's level part, every state of design.md §14.1 at 390 and 1440
(targum-internal#561; §12, "Your level, v3", 2026-10-29).

Signed out, loading, error, week one, a few weeks, months, the top rung, Aramaic, Yiddish,
French on the European scale alone, and the Russian interface: each loads the page the
server renders, with the account's answers stubbed, at a desk and as a touch phone. Each
must draw what it promises, print no percentage on the card or the ladder, never scroll
sideways, give every row a thumb's height, and throw nothing. Then Words you knew: Day,
Week and Month, the choice remembered, the line one tab stop with its points said by the
arrows, and the empty and failed states. With `TARGUM_SHOTS` set to a folder, each state
is saved there as `level-<state>-<width>.png` for the card.

Skips itself without Playwright.
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Any

import pytest
from test_progress_states_browser import SITE, me, record

from targum.render.builder import progress_page

pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)


def rung(
    kind: str,
    state: str,
    readable: int = 0,
    name: str = "",
    texts: int = 9,
    covered: bool | None = None,
    to_go: int | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "kind": kind,
        "name": name or kind,
        "state": state,
        "texts": texts,
        "readable": readable,
    }
    if covered is not None:
        row["covered"] = covered
        row["toGo"] = to_go
    return row


LEVELS = ("A1", "A2", "B1", "B2", "C1", "C2", "past-C2")


def ladder(
    easy: int, counts: tuple[int, ...] = (), reached: int = 0, to_go: tuple[int, ...] = ()
) -> list[dict[str, Any]]:
    """The seven levels with the first `easy` easy and the one after it the next step by
    texts; the first `reached` covered by the reader's words, and the rest the words to go
    in `to_go`, Past C2 with none. C2 and Past C2 have no texts."""
    out = []
    above = iter(to_go)
    for at, kind in enumerate(LEVELS):
        state = "easy" if at < easy else "next" if at == easy else "ahead"
        covered = at < reached
        left = None if covered or kind == "past-C2" else next(above, None)
        out.append(
            rung(
                kind,
                state,
                counts[at] if at < len(counts) else 0,
                texts=0 if kind in ("C2", "past-C2") else 9,
                covered=covered,
                to_go=left,
            )
        )
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
        "first": None,
        "conversations": True,
        "texts": [],
        "words": [],
        **fields,
    }


ULPAN_ALEPH_PLUS = {
    "scale": "ulpan",
    "letter": "א+",
    "name": "aleph plus",
    "cefr": "A1",
    "next": {"letter": "ב", "name": "bet"},
    "toward": 0.38,
    "toGo": 412,
}
ULPAN_DALET = {
    "scale": "ulpan",
    "letter": "ד",
    "name": "dalet",
    "cefr": "B2",
    "next": {"letter": "ה", "name": "hey"},
    "toward": 0.52,
    "toGo": 637,
}
MONTHS = ladder(3, (118, 143, 52, 11), reached=4, to_go=(637, 2041))

#: Each state: what the page is asked with, and what the part must then say.
STATES: dict[str, dict[str, Any]] = {
    "signed-out": {
        "signed": False,
        "says": "Sign in to see which texts you can read on your own.",
        "mark": None,
    },
    "loading": {"hold": True, "says": "We're working out your level."},
    "error": {"fail": True, "says": "We couldn't load this part.", "press": "Try again"},
    "week-one": {
        "story": story(
            known=86,
            ladder=ladder(0, to_go=(148, 1712, 3688, 4874, 6530, 8046)),
            next=0,
            first={"scale": "ulpan", "letter": "א", "name": "aleph", "toward": 0.4, "toGo": 148},
        ),
        "says": "Start with beginner texts.",
        "press": "Start learning",
        "rows": 7,
        "mark": None,
        "togo": "148 words to א׳",
    },
    "few-weeks": {
        "story": story(
            known=1240,
            ladder=ladder(1, (38, 4), reached=1, to_go=(1300, 3100, 5000, 7400, 10200)),
            here=0,
            next=1,
            level=ULPAN_ALEPH_PLUS,
        ),
        "says": "412 words to ב׳",
        "press": "Show texts you can read now",
        "rows": 7,
        "mark": ("א׳+", "About A1"),
        "togo": "412 words to ב׳",
    },
    "months": {
        "story": story(known=4730, ladder=MONTHS, here=2, next=3, level=ULPAN_DALET),
        "says": "637 words to ה׳",
        "press": "Show texts you can read now",
        "rows": 7,
        "mark": ("ד׳", "About B2"),
        "togo": "637 words to ה׳",
        "c1": "637 words to go",
    },
    "top-rung": {
        "story": story(
            known=12500,
            ladder=ladder(4, (118, 143, 60, 40), reached=7),
            here=3,
            level={
                "scale": "ulpan",
                "letter": "ו",
                "name": "vav",
                "cefr": "C2",
                "next": None,
                "toward": None,
                "toGo": None,
            },
        ),
        "says": "About C2",
        "press": "Show texts you can read now",
        "rows": 7,
        "mark": ("ו׳", "About C2"),
        "togo": None,
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
        "mark": None,
        "togo": None,
    },
    "yiddish": {
        "language": "yi",
        "story": story(known=120, library=False),
        "says": "You know 120 words so far",
        "mark": None,
        "togo": None,
    },
    "french": {
        "language": "fr",
        "story": story(
            known=2100,
            ladder=ladder(2, (40, 12, 3), reached=3, to_go=(237, 587, 1137)),
            here=1,
            next=2,
            level={
                "scale": "cefr",
                "letter": "B1",
                "name": "B1",
                "cefr": "",
                "next": {"letter": "B2", "name": "B2"},
                "toward": 0.25,
                "toGo": 237,
            },
        ),
        "says": "237 words to B2",
        "press": "Show texts you can read now",
        "rows": 7,
        "mark": ("B1", ""),
        "togo": "237 words to B2",
    },
    "russian": {
        "page": "ru",
        "story": story(known=4730, ladder=MONTHS, here=2, next=3, level=ULPAN_DALET),
        "title": "Ваш уровень",
        "says": "Ещё 637 слов до уровня ה׳",
        "press": "Показать тексты, которые можно читать уже сейчас",
        "rows": 7,
        "mark": ("ד׳", "Примерно B2"),
        "togo": "Ещё 637 слов до уровня ה׳",
        "c1": "Ещё 637 слов",
    },
}

SEEN = """() => {
  const where = document.getElementById('where');
  const box = (one) => one.getBoundingClientRect();
  const shown = (one) => !!one && one.offsetParent !== null;
  const at = (id) => document.getElementById(id);
  const bar = at('level-bar');
  const all = (selector) => [...where.querySelectorAll(selector)];
  const big = at('level-big');
  const lead = document.querySelector('.level-lead');
  const ladder = at('ladder');
  return {
    text: where.innerText,
    counted: [lead, ladder].filter(shown).map((one) => one.innerText).join('\\n'),
    title: at('where-section').textContent,
    titleBox: [box(at('where-section')).width, box(at('where-section')).height],
    labels: all('[aria-label]').map((one) => one.getAttribute('aria-label')),
    rows: all('#touchstones .touch-row').filter(shown).map((one) => box(one).height),
    states: all('#touchstones .touch-state').map((one) => one.textContent),
    mark: shown(at('level-mark'))
      ? {big: big.textContent, cefr: at('level-cefr').textContent,
         spoken: at('level-spoken').textContent, lang: big.getAttribute('lang'),
         hidden: big.getAttribute('aria-hidden'),
         weight: getComputedStyle(big).fontWeight, size: parseFloat(getComputedStyle(big).fontSize),
         family: getComputedStyle(big).fontFamily}
      : null,
    bar: shown(bar)
      ? {role: bar.getAttribute('role'), hidden: bar.getAttribute('aria-hidden'),
         height: box(bar).height, togo: at('level-togo').textContent}
      : null,
    titleSize: document.querySelector('.page-title')
      ? parseFloat(getComputedStyle(document.querySelector('.page-title')).fontSize) : 0,
    letters: all('bdi').filter(shown)
      .map((one) => [one.getAttribute('lang'), one.getAttribute('dir')]),
    semibold: [...document.fonts].some((face) =>
      face.family.replace(/"/g, '') === 'Noto Sans Hebrew'
      && String(face.weight) === '600' && face.status === 'loaded'),
    scroll: document.documentElement.scrollWidth,
    client: document.documentElement.clientWidth,
    wide: [...document.querySelectorAll('body *')]
      .filter((one) => box(one).right > document.documentElement.clientWidth + 0.5)
      .map((one) => one.id || one.className || one.tagName).slice(0, 8),
  };
}"""


def reading_days(*days: tuple[datetime.date, int, int]) -> dict[str, Any]:
    return {
        "signedIn": True,
        "measurable": 20,
        "reading": {
            "he": {
                "line": [],
                "months": 0,
                "sections": len(days),
                "days": [
                    {"day": when.isoformat(), "tokens": tokens, "known": known, "sections": 1}
                    for when, known, tokens in days
                ],
            }
        },
    }


def open_state(
    chromium: Any,
    name: str,
    width: int,
    reading: dict[str, Any] | None = None,
    reading_fails: bool = False,
) -> tuple[Any, Any, list[str], list[str]]:
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
        "/account/reading": reading or {"signedIn": True, "reading": {}},
    }
    asked: list[str] = []

    def answer(route: Any, request: Any) -> Any:
        path = request.url[len(SITE) :].split("?")[0]
        asked.append(request.url[len(SITE) :])
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        if path == "/account/story" and spec.get("hold"):
            return None  # Never answered: the loading line stays.
        if path == "/account/story" and spec.get("fail"):
            return route.fulfill(status=500, content_type="text/plain", body="no")
        if path == "/account/reading" and reading_fails:
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
    return context, page, thrown, asked


@pytest.mark.parametrize("width", [1440, 390])
@pytest.mark.parametrize("state", list(STATES))
def test_every_level_state_is_drawn_without_a_percentage(
    chromium: Any, state: str, width: int
) -> None:
    spec = STATES[state]
    context, page, thrown, _ = open_state(chromium, state, width)
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

        # No visible heading: the h2 is there for a screen reader and nobody else.
        assert seen["title"] == spec.get("title", "Your level")
        assert seen["titleBox"][0] <= 1 and seen["titleBox"][1] <= 1, seen["titleBox"]
        assert "%" not in seen["counted"], seen["counted"]
        assert not [label for label in seen["labels"] if "%" in label], seen["labels"]
        assert seen["scroll"] <= seen["client"], seen["wide"]
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
        if "mark" in spec and spec["mark"] is None:
            assert seen["mark"] is None, seen["mark"]
        elif "mark" in spec:
            big, cefr = spec["mark"]
            mark = seen["mark"]
            assert mark is not None
            assert (mark["big"], mark["cefr"]) == (big, cefr)
            # At the page title's step and in 600.
            assert mark["weight"] == "600"
            assert 30 <= mark["size"] <= 34, mark
            if spec.get("language", "he") == "he":
                assert mark["lang"] == "he" and mark["hidden"] == "true" and mark["spoken"]
                assert "Noto Sans Hebrew" in mark["family"], mark["family"]
                assert seen["semibold"], "the 600 cut is carried and loaded, never faked"
        if "togo" in spec and spec["togo"] is None:
            assert seen["bar"] is None
        elif "togo" in spec:
            assert seen["bar"] is not None
            assert seen["bar"]["togo"] == spec["togo"]
            # The bar is not spoken; the words line is, once, as text.
            assert seen["bar"]["hidden"] == "true" and seen["bar"]["role"] is None
            assert 3 <= seen["bar"]["height"] <= 5, "a thin line"
            if spec.get("language", "he") == "he":
                assert ["he", "rtl"] in seen["letters"]
        if "c1" in spec:
            assert seen["states"][4] == spec["c1"], "C1's number is the card's"
        assert not thrown, thrown
    finally:
        context.close()


LAYOUT = """() => {
  const box = (one) => one.getBoundingClientRect();
  const lead = box(document.querySelector('.level-lead'));
  const ladder = box(document.getElementById('ladder'));
  const reading = box(document.getElementById('reading'));
  return {lead: [lead.x, lead.y, lead.width, lead.bottom],
          ladder: [ladder.x, ladder.y, ladder.width, ladder.bottom],
          reading: [reading.x, reading.y, reading.width, reading.bottom]};
}"""

TODAY = datetime.date.today()


def a_record() -> dict[str, Any]:
    """Two months back and three days lately: every view has two points."""
    first = (TODAY.replace(day=1) - datetime.timedelta(days=70)).replace(day=10)
    second = (TODAY.replace(day=1) - datetime.timedelta(days=35)).replace(day=10)
    return reading_days(
        (first, 80, 100),
        (second, 90, 100),
        (TODAY - datetime.timedelta(days=9), 60, 100),
        (TODAY - datetime.timedelta(days=2), 70, 100),
        (TODAY, 91, 100),
    )


@pytest.mark.parametrize("width", [1440, 1024, 390])
def test_two_even_columns_at_a_desk_and_one_on_a_phone(chromium: Any, width: int) -> None:
    """At a desk the card with the chart under it on the left and the ladder on the right,
    even, ending at about the same height; on a phone, card, ladder, chart."""
    context, page, thrown, _ = open_state(chromium, "months", width, reading=a_record())
    try:
        page.goto(SITE + "/progress")
        page.locator("#reading").wait_for(state="visible", timeout=10_000)
        page.wait_for_load_state("networkidle")
        seen = page.evaluate(LAYOUT)
        shots = os.environ.get("TARGUM_SHOTS")
        if shots:
            page.screenshot(path=f"{shots}/level-layout-{width}.png", full_page=True)
        lead, ladder, reading = seen["lead"], seen["ladder"], seen["reading"]
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        ), "nothing sideways"
        if width > 1000:
            assert lead[0] < ladder[0] and abs(lead[1] - ladder[1]) <= 1, seen
            assert abs(lead[2] - ladder[2]) <= 2, "two even columns"
            assert abs(reading[0] - lead[0]) <= 1 and reading[1] > lead[3], seen
            assert abs(reading[3] - ladder[3]) <= 200, "they end at about the same height"
        else:
            assert lead[3] <= ladder[1] and ladder[3] <= reading[1], seen
        assert not thrown, thrown
    finally:
        context.close()


SWITCH = """() => {
  const buttons = [...document.querySelectorAll('#reading-by button')];
  const box = (one) => one.getBoundingClientRect();
  return {
    pressed: buttons.filter((one) => one.getAttribute('aria-pressed') === 'true')
      .map((one) => one.textContent),
    heights: buttons.map((one) => box(one).height),
    group: document.getElementById('reading-by').getAttribute('role'),
    label: document.getElementById('reading-by').getAttribute('aria-label'),
    said: document.getElementById('reading-said').innerText,
    live: document.getElementById('reading-live').textContent,
    empty: (document.querySelector('#reading .reading-empty') || {}).textContent || '',
    chart: (document.querySelector('#reading .chart') || {offsetHeight: 0}).offsetHeight,
  };
}"""


@pytest.mark.parametrize("width", [1440, 390])
def test_words_you_knew_switches_day_week_month_and_remembers(chromium: Any, width: int) -> None:
    context, page, thrown, asked = open_state(chromium, "months", width, reading=a_record())
    try:
        page.goto(SITE + "/progress")
        page.locator("#reading").wait_for(state="visible", timeout=10_000)
        page.wait_for_load_state("networkidle")
        seen = page.evaluate(SWITCH)
        assert seen["group"] == "group" and seen["label"] == "Show by"
        assert seen["pressed"] == ["Month"], "the coarsest view with two points"
        assert "of the words you read." in seen["said"] and "%" in seen["said"]
        assert "We count only" not in page.locator("#reading").inner_text()
        floor = 44 if width < 600 else 40
        assert all(height >= floor for height in seen["heights"]), seen["heights"]
        # The time zone is the page's own, sent with the ask.
        assert any(one.startswith("/account/reading?tz=") for one in asked), asked

        page.get_by_role("button", name="Day").click()
        seen = page.evaluate(SWITCH)
        assert seen["pressed"] == ["Day"]
        assert seen["said"].startswith("Today you knew 91% of the words you read."), seen["said"]
        assert "fell" not in seen["said"]

        page.get_by_role("button", name="Week").click()
        assert page.evaluate(SWITCH)["pressed"] == ["Week"]
        page.reload()
        page.locator("#reading").wait_for(state="visible", timeout=10_000)
        page.wait_for_load_state("networkidle")
        assert page.evaluate(SWITCH)["pressed"] == ["Week"], "remembered in this browser"

        # One tab stop for the line, and the arrows say each point.
        page.get_by_role("button", name="Day").click()
        page.locator("#reading .chart svg").focus()
        first = page.evaluate(SWITCH)["live"]
        assert first.endswith("1 section") and "91%" in first, first
        page.keyboard.press("ArrowLeft")
        before = page.evaluate(SWITCH)["live"]
        assert "70%" in before and before != first, before
        assert page.locator("#reading .reading-point").evaluate_all(
            "(dots) => dots.every((dot) => !dot.hasAttribute('tabindex'))"
        ), "the dots are not tab stops of their own"
        assert not thrown, thrown
    finally:
        context.close()


def test_an_empty_view_keeps_its_height_and_says_what_would_draw_it(chromium: Any) -> None:
    old = reading_days((datetime.date(2025, 6, 10), 80, 100), (datetime.date(2025, 7, 10), 90, 100))
    context, page, thrown, _ = open_state(chromium, "months", 390, reading=old)
    try:
        page.goto(SITE + "/progress")
        page.locator("#reading").wait_for(state="visible", timeout=10_000)
        page.wait_for_load_state("networkidle")
        page.get_by_role("button", name="Day").click()
        seen = page.evaluate(SWITCH)
        assert seen["empty"] == (
            "We'll draw this once you've finished sections on two different days."
        )
        assert seen["chart"] >= 118, "the chart's 120px stays"
        assert not thrown, thrown
    finally:
        context.close()


def test_a_reading_that_fails_says_so_with_try_again(chromium: Any) -> None:
    context, page, thrown, _ = open_state(chromium, "months", 1440, reading_fails=True)
    try:
        page.goto(SITE + "/progress")
        page.locator("#reading-failed").wait_for(state="visible", timeout=10_000)
        assert page.locator("#reading-again").is_visible()
        assert not thrown, thrown
    finally:
        context.close()
