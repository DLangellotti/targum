"""Nothing on a desk page runs past its card or the window, at every width a reader has
(David, 2026-10-24: "design seems to be broken — get it fixed here, and on mobile, and in
all other sizes").

His screenshot was Your Words at a desk: the table ran 41px past its card, and its last
column, ignore, sat under Practise these. targum#919 kept the Talk pill's room on both
edges of the column so the column stays centred, which made the column narrower than the
window by twice the pill's reach (1198px at 1440 in English), and the page still asked
the *window* whether there was room for the card beside the table. Now the page asks the
grid. The shoot that day (360 to 1920, every signed-in desk page, English and Russian)
found one more: Your targums' Subscriptions tab at 768. These tests walk both pages at
the widths a reader has, in both languages, and assert that no element is drawn outside
its card and nothing scrolls sideways.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from targum.render.builder import list_page

pytest.importorskip("playwright.sync_api")

TOKEN = "test-key"

#: Every width a reader has, from a small phone to a wall (design.md §14, line 2).
WIDTHS = [360, 390, 768, 1024, 1280, 1440, 1745, 1920]

#: Every element drawn outside the card it stands in, and whether the window scrolls
#: sideways. A card is a `.card`; a hidden or visually hidden element, and anything fixed
#: (the pill, a sheet), is not drawn in the card and is left out, and so is what a row
#: that scrolls sideways holds; and the card itself must stand inside the window.
OUTSIDE = """(selector) => {
  const outside = [];
  for (const card of document.querySelectorAll(selector)) {
    const box = card.getBoundingClientRect();
    if (!box.width || !box.height) continue;
    for (const el of card.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2) continue;
      const look = getComputedStyle(el);
      if (look.position === 'fixed' || (look.clipPath || '').includes('inset(50%')) continue;
      // A row of tabs that scrolls sideways on a phone holds what it scrolls to.
      let scrolled = false;
      for (let up = el.parentElement; up && up !== card; up = up.parentElement) {
        if (getComputedStyle(up).overflowX !== 'visible') scrolled = true;
      }
      if (scrolled) continue;
      if (r.right > box.right + 1 || r.left < box.left - 1) {
        outside.push({
          el: el.tagName.toLowerCase() + '.' + [...el.classList].join('.'),
          text: (el.textContent || '').trim().slice(0, 30),
          by: Math.round(Math.max(r.right - box.right, box.left - r.left)),
        });
      }
    }
  }
  const width = document.documentElement.clientWidth;
  for (const card of document.querySelectorAll(selector)) {
    const box = card.getBoundingClientRect();
    if (box.width && (box.right > width + 1 || box.left < -1)) {
      const by = Math.round(box.right - width);
      outside.push({el: 'the card itself', text: card.className, by});
    }
  }
  return {
    outside: outside.slice(0, 8),
    sideways: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  };
}"""

#: Thirty words still being learned, half met in another form than the dictionary's, as
#: a reader with a list has them (the screenshot had 5,842).
WORDS = [
    ("ביצוע", "הביצועים", 2, "performance; execution"),
    ("לעומת", "לעומת", 3, "compared to; versus"),
    ("הציג", "הציגה", 1, "to present; to show"),
    ("דרש", "דירשו", 2, "study session on the Torah portion"),
    ("ירא", "יראת", 2, "to fear, be afraid"),
    ("לשכה", "הלשכה", 1, "chamber; office"),
    ("נציג", "נציג", 1, "representative"),
    ("הצהרה", "הצהרה", 1, "declaration, statement"),
    ("מילא", "מילאתי", 3, "filled in"),
    ("התעצמות", "התעצמויות", 2, "intensification, strengthening"),
] * 3

#: A line from a section the reader finished, for the practice card.
LINE = (
    "כעת אנבידיה נכנסת לתמונה עם יתרון משמעותי: עשרות שנות ניסיון בתחום הגרפיקה "
    "והגיימינג, לצד טכנולוגיות כמו CUDA ו-RTX."
)


def _vocab() -> tuple[dict[str, Any], dict[str, Any]]:
    vocab: dict[str, Any] = {}
    meanings: dict[str, Any] = {}
    for n, (lemma, surface, status, meaning) in enumerate(WORDS):
        key = lemma if n < 10 else f"{lemma}{n}"
        vocab[key] = {"surface": surface if n < 10 else f"{surface}{n}", "status": status, "at": n}
        meanings[key] = {"meaning": meaning, "seen": n}
    return vocab, meanings


def _facts(vocab: dict[str, Any]) -> dict[str, Any]:
    lemmas = list(vocab)
    return {
        "signedIn": True,
        "met": {lemma: 5 for lemma in lemmas},
        "often": 2,
        "notes": {},
        "practise": [
            {
                "lemma": lemma,
                "word": vocab[lemma]["surface"],
                "title": "האיום החדש על המקבוק: הצצה למהפכה של אנבידיה",
                "name": "nvidia",
                "line": LINE,
                "start": 36,
                "end": 41,
                "translation": "Now Nvidia enters the picture with a significant advantage.",
            }
            for lemma in lemmas[:10]
        ],
    }


def _words_page(browser: Any, width: int, language: str) -> tuple[Any, Any]:
    html = list_page(TOKEN, "words", language)
    vocab, meanings = _vocab()
    facts = _facts(vocab)

    def answer(route, request):  # type: ignore[no-untyped-def]
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        body = json.dumps(facts) if "/account/words" in request.url else "{}"
        route.fulfill(status=200, content_type="application/json", body=body)

    phone = width < 700
    context = browser.new_context(
        viewport={"width": width, "height": 900}, is_mobile=phone, has_touch=phone
    )
    page = context.new_page()
    into = "ru" if language == "ru" else "en"
    page.add_init_script(
        f"localStorage.setItem('targum:vocab:he', {json.dumps(json.dumps(vocab))});"
        f"localStorage.setItem('targum:meanings:he:{into}', {json.dumps(json.dumps(meanings))});"
        "localStorage.setItem('targum:language', 'he');"
    )
    page.route("http://words.test/**", answer)
    page.goto(f"http://words.test/words?k={TOKEN}")
    page.wait_for_selector("#word-rows tr")
    page.wait_for_selector("#practise:not([hidden])")
    page.wait_for_timeout(300)
    return context, page


@pytest.fixture(scope="module")
def browser(chromium):  # type: ignore[no-untyped-def]
    return chromium.browser()


@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("width", WIDTHS)
def test_your_words_keeps_its_table_inside_its_card(browser, width: int, language: str) -> None:
    """The screenshot's page: the table, its ignore and the practice card, each inside
    its own card at every width, in both interface languages."""
    context, page = _words_page(browser, width, language)
    got = page.evaluate(OUTSIDE, ".words-grid > .card")
    beside = page.evaluate(
        """() => {
          const table = document.querySelector('.words-card').getBoundingClientRect();
          const card = document.getElementById('practise').getBoundingClientRect();
          return card.top < table.bottom && card.bottom > table.top;
        }"""
    )
    context.close()
    assert got["outside"] == [], got
    assert got["sideways"] <= 0, got
    if width >= 1745:
        assert beside, "a wide desk keeps the practice card beside the table (board WordsDesk)"


@pytest.mark.parametrize("width", [1280, 1440])
def test_a_word_s_dictionary_form_stands_under_it(browser, width: int) -> None:
    """The lemma under a Hebrew word drifted to the cell's other edge: a `bdi` takes its
    own direction, so `end` inside it was the left. It ends where the word ends."""
    context, page = _words_page(browser, width, "en")
    got = page.evaluate(
        """() => [...document.querySelectorAll('#word-rows .word-cell')]
          .filter((cell) => cell.querySelector('.form'))
          .slice(0, 5)
          .map((cell) => {
            const term = cell.querySelector('.term:not(.form)').getBoundingClientRect();
            const form = cell.querySelector('.form');
            const range = document.createRange();
            range.selectNodeContents(form);
            const drawn = range.getBoundingClientRect();
            return Math.round(Math.abs(drawn.right - term.right));
          })"""
    )
    context.close()
    assert got and max(got) <= 2, got


@pytest.mark.parametrize("language", ["en", "ru"])
@pytest.mark.parametrize("width", WIDTHS)
def test_the_subscriptions_tab_keeps_its_rows_inside_its_card(
    browser, width: int, language: str
) -> None:
    """Your targums' Subscriptions tab at 768 broke «Недельный» in the middle and ran
    «Каждый понедельник» into the next column: five columns in a card that is the column
    less the AI Assistant's room. The table takes the phone's rows wherever it is narrower
    than its columns need."""
    from test_subscriptions_browser import ROWS, SERIES, SITE, serve

    weekly = dict(
        ROWS[0], kind="series", key="weekly", name="Недельный обзор новостей Weekly News Digest"
    )
    listed = {
        "signedIn": True,
        "subscriptions": [weekly, *ROWS[1:]],
        "series": SERIES,
        "credits": {"left": 354, "back": "November 1"},
    }
    readers = {
        "readers": [
            {
                "name": "own",
                "document": "own",
                "title": "כתבה",
                "language": "he",
                "entry": "",
                "built": 1,
                "minutes": 3,
                "seconds": 0,
                "sections": 1,
                "chapters": [],
            }
        ],
        "shared": [],
        "trash": [],
    }
    phone = width < 700
    context = browser.new_context(
        viewport={"width": width, "height": 900}, is_mobile=phone, has_touch=phone
    )
    page = context.new_page()
    serve(
        page,
        {
            "/": list_page("", "texts", language),
            "/readers": readers,
            "/subscriptions.json": listed,
        },
        [],
    )
    page.goto(f"{SITE}/?show=subscriptions")
    page.wait_for_selector("#subs-rows .sub-row")
    page.wait_for_timeout(300)
    got = page.evaluate(OUTSIDE, ".card")
    broken = page.evaluate(
        """() => [...document.querySelectorAll('#subs-rows .sub-row > *')]
          .filter((cell) => cell.scrollWidth > cell.clientWidth + 1)
          .map((cell) => cell.className)"""
    )
    context.close()
    assert got["outside"] == [], got
    assert got["sideways"] <= 0, got
    assert broken == [], "a cell's words run past it"
