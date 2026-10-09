"""One search, everywhere, in a browser (design.md §12, "One search, everywhere",
2026-10-09; boards FindDesk and FindPhone).

The page is the real Library page; the server is a route that answers `/search.json` and
`/search/word.json` the way `serve._search` and `_search_word` do (`test_search.py`
holds the server to those shapes). What is asserted is what a reader meets: ⌘K and "/",
the empty overlay's recent searches, the groups with their counts, the filters, a word's
sentences, nothing found, the Library's box, and a phone.
"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from targum.render.builder import library_page

pytest.importorskip("playwright.sync_api", reason="Playwright is not installed")

TOKEN = "test-key"


@pytest.fixture
def browser(chromium):
    return chromium.browser()


def _text(title: str, **more: Any) -> dict[str, Any]:
    row = {
        "kind": "text",
        "name": title + "-he",
        "entry": "",
        "title": title,
        "english": "",
        "author": "",
        "language": "he",
        "type": "article",
        "register": "",
        "what": "News",
        "words": 674,
        "href": "/reader/" + title + "-he/reader/index.html",
    }
    row.update(more)
    return row


FOUND = {
    "q": "ירושלם",
    "learning": [{"code": "he", "name": "Hebrew"}, {"code": "ru", "name": "Russian"}],
    "language": "he",
    "name": "Hebrew",
    "languages": [
        {"code": "he", "name": "Hebrew", "count": 8},
        {"code": "ru", "name": "Russian", "count": 2},
    ],
    "groups": [
        {
            "id": "yours",
            "count": 1,
            "rows": [
                _text(
                    "מה טבעונים אוכלים בירושלים?",
                    english="What do vegans eat in Jerusalem?",
                    tag="recent",
                    what="Video",
                    known=0.91,
                    band="now",
                    bandWord="Read it now",
                )
            ],
        },
        {"id": "playlists", "count": 0, "rows": []},
        {"id": "subscriptions", "count": 0, "rows": []},
        {
            "id": "library",
            "count": 6,
            "rows": [
                _text(
                    "ירושלם החדשה",
                    entry=f"lib-{n}",
                    english="New Jerusalem",
                    known=0.81,
                    band="stretch",
                    bandWord="A stretch",
                    href=f"/open/lib-{n}",
                )
                for n in range(6)
            ],
        },
        {
            "id": "words",
            "count": 1,
            "rows": [
                {
                    "kind": "word",
                    "lemma": "ירושלים",
                    "language": "he",
                    "meaning": "Jerusalem",
                    "stage": 9,
                    "sentences": 21,
                    "texts": 14,
                }
            ],
        },
    ],
    "elsewhere": {
        "language": "ru",
        "name": "Russian",
        "count": 2,
        "rows": [_text("Иерусалим", language="ru")],
    },
}

NOTHING = {
    "q": "עגנון",
    "learning": [{"code": "he", "name": "Hebrew"}],
    "language": "he",
    "name": "Hebrew",
    "languages": [],
    "groups": [
        {"id": g, "count": 0, "rows": []}
        for g in ("yours", "playlists", "subscriptions", "library", "words")
    ],
    "elsewhere": {},
}

WORD = {
    "lemma": "ירושלים",
    "language": "he",
    "meaning": "Jerusalem",
    "stage": 9,
    "forms": ["ירושלים", "בירושלים", "לירושלים"],
    "sentences": 3,
    "texts": 2,
    "yours": {
        "count": 2,
        "texts": 1,
        "sentences": [
            {
                "sentence": "הלכתי לראות מה אוכלים טבעוני בירושלים לקראת יום ירושלים.",
                "forms": ["בירושלים", "ירושלים"],
                "title": "מה טבעונים אוכלים בירושלים?",
                "name": "vegan-he",
                "entry": "",
                "language": "he",
                "type": "talk",
                "what": "Video",
                "author": "Vegan Friendly",
                "href": "/sentence/vegan-he?at=s1",
                "known": 0.91,
                "band": "now",
            }
        ],
    },
    "library": {"count": 1, "texts": 1, "sentences": []},
}


def _open(
    browser, width: int = 1440, height: int = 900, recent: list[str] | None = None, **answers: Any
):
    """The Library page with the search's answers routed; returns the page and the
    addresses it asked for."""
    asked: list[str] = []
    html = library_page(TOKEN)

    def answer(route, request):
        url = request.url
        parsed = urlparse(url)
        if parsed.path == "/search.json":
            asked.append(url)
            line = parse_qs(parsed.query).get("q", [""])[0]
            if not line:
                body: Any = {
                    "q": "",
                    "learning": FOUND["learning"],
                    "opened": [_text("בראשית", what="Tanakh")],
                }
            elif line in answers.get("nothing", ()):
                body = dict(NOTHING, q=line)
            else:
                body = dict(FOUND, q=line)
        elif parsed.path == "/search/word.json":
            asked.append(url)
            body = WORD
        elif parsed.path == "/library":
            route.fulfill(status=200, content_type="text/html", body=html)
            return
        elif parsed.path.startswith(("/reader/", "/add", "/open/")):
            route.fulfill(
                status=200, content_type="text/html", body="<html><body>there</body></html>"
            )
            return
        elif parsed.path == "/readers":
            body = {"readers": [], "shared": [], "trash": [], "covers": False}
        elif parsed.path.startswith("/thumb/"):
            route.fulfill(status=404, body="")
            return
        else:
            body = {}
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps(body, ensure_ascii=False)
        )

    phone = width < 500
    context = browser.new_context(
        viewport={"width": width, "height": height}, is_mobile=phone, has_touch=phone
    )
    if recent is not None:
        context.add_init_script(
            "localStorage.setItem('targum:searches', " + json.dumps(json.dumps(recent)) + ");"
        )
    page = context.new_page()
    page.route("http://find.test/**", answer)
    page.goto(f"http://find.test/library?k={TOKEN}")
    page.wait_for_selector("#palette", state="attached")
    return context, page, asked


def _up(page) -> bool:
    return not page.evaluate("() => document.getElementById('palette').hidden")


def test_command_k_and_slash_open_it_and_it_starts_with_what_you_searched(browser) -> None:
    context, page, asked = _open(browser, recent=["Chekhov", "ירושלים"])
    page.click("body", position={"x": 5, "y": 400})
    page.keyboard.press("Meta+k")
    page.wait_for_function("() => !document.getElementById('palette').hidden")
    page.wait_for_selector(".palette-lately .palette-title")
    recent = page.eval_on_selector_all(".palette-recent bdi", "els => els.map(e => e.textContent)")
    assert recent == ["Chekhov", "ירושלים"]
    lately = page.eval_on_selector_all(
        ".palette-lately .palette-title", "els => els.map(e => e.textContent)"
    )
    assert lately == ["בראשית"], "opened lately, from the server"
    assert "lang=he" in asked[0]
    page.keyboard.press("Escape")
    assert not _up(page), "Escape closes it"
    page.keyboard.press("/")
    assert _up(page), "and / opens it"
    # ✕ forgets one search, on this device.
    page.click(".palette-recent-row .palette-drop")
    assert page.evaluate("() => JSON.parse(localStorage.getItem('targum:searches'))") == ["ירושלים"]
    context.close()


def test_what_it_finds_is_grouped_counted_and_filtered(browser) -> None:
    context, page, asked = _open(browser)
    page.click("#palette-open")
    page.fill("#palette-find", "ירושלם")
    page.wait_for_selector(".palette-group[data-group='library']")
    assert "q=%D7%99%D7%A8%D7%95%D7%A9%D7%9C%D7%9D" in asked[-1] and "lang=he" in asked[-1]
    tabs = page.eval_on_selector_all(
        "#palette-filters .tab",
        "els => els.map(e => [e.dataset.filter, e.textContent, e.disabled])",
    )
    assert tabs[0] == ["all", "All8", False]
    assert ["playlists", "Playlists0", True] in tabs, "a group with nothing is not a filter"
    groups = page.eval_on_selector_all(".palette-group", "els => els.map(e => e.dataset.group)")
    assert groups == ["yours", "library", "words"]
    # Four of the Library's six in All, and See all is its filter.
    assert page.locator(".palette-group[data-group='library'] .palette-row").count() == 4
    page.click(".palette-group[data-group='library'] .palette-see-all")
    assert page.locator(".palette-group[data-group='library'] .palette-row").count() == 6
    assert (
        page.get_attribute("#palette-filters .tab[data-filter='library']", "aria-selected")
        == "true"
    )
    # A row: its band in the Library's words and how much is known, over its meter.
    page.click("#palette-filters .tab[data-filter='all']")
    first = page.locator(".palette-group[data-group='yours'] .palette-hit").first
    assert "Read it now" in first.inner_text() and "91% known" in first.inner_text()
    assert first.locator(".meter").count() == 1
    assert first.locator(".row-thumb").count() == 1, "every row has its picture"
    # The level narrows to one band.
    page.select_option(".palette-level-pick", "now")
    assert page.eval_on_selector_all(".palette-group", "els => els.map(e => e.dataset.group)") == [
        "yours",
        "words",
    ]
    # Searched in Hebrew, with all languages one press away.
    assert "Searched in Hebrew." in page.inner_text(".palette-foot")
    # Enter opens the first, and the search is kept on the device.
    page.select_option(".palette-level-pick", "")
    page.focus("#palette-find")
    page.keyboard.press("Enter")
    page.wait_for_url("**/reader/**", timeout=5000)
    assert page.evaluate("() => JSON.parse(localStorage.getItem('targum:searches'))") == ["ירושלם"]
    context.close()


def test_search_all_languages_asks_again_in_every_one(browser) -> None:
    context, page, asked = _open(browser)
    page.click("#palette-open")
    page.fill("#palette-find", "ירושלם")
    page.wait_for_selector(".palette-foot-all")
    page.click(".palette-foot-all")
    page.wait_for_function(
        "() => document.getElementById('palette-lang').textContent.includes('All languages')"
    )
    page.wait_for_timeout(400)
    assert "lang=all" in asked[-1]
    # And the scope's own menu names each language with its count.
    page.click("#palette-lang")
    rows = page.eval_on_selector_all(".palette-lang-row", "els => els.map(e => e.textContent)")
    assert any(row.startswith("Hebrew") and row.endswith("8") for row in rows), rows
    assert rows[-1] == "All languages"
    context.close()


def test_texts_with_this_word(browser) -> None:
    context, page, asked = _open(browser)
    page.click("#palette-open")
    page.fill("#palette-find", "ירושלם")
    page.wait_for_selector(".palette-group[data-group='words'] .palette-hit")
    page.click(".palette-group[data-group='words'] .palette-hit")
    page.wait_for_selector(".palette-sentence-row")
    assert "/search/word.json" in asked[-1] and "lemma=" in asked[-1]
    forms = page.eval_on_selector_all(".palette-form", "els => els.map(e => e.textContent)")
    assert forms == ["ירושלים", "בירושלים", "לירושלים"]
    marks = page.eval_on_selector_all(
        ".palette-sentence mark", "els => els.map(e => e.textContent)"
    )
    assert marks == ["בירושלים", "ירושלים"], "the word is marked where it stands"
    assert page.inner_text(".palette-word-tally") == "3 sentences · 2 texts"
    opener = page.locator(".palette-sentence-row a.btn").first
    assert opener.inner_text() == "Open at this sentence"
    assert "/sentence/vegan-he?at=s1" in (opener.get_attribute("href") or "")
    # Escape steps back to what was found before it closes.
    page.keyboard.press("Escape")
    assert _up(page) and page.locator(".palette-group[data-group='library']").count() == 1
    context.close()


def test_nothing_found_offers_a_link_or_an_upload(browser) -> None:
    context, page, _ = _open(browser, nothing=["עגנון"])
    page.click("#palette-open")
    page.fill("#palette-find", "עגנון")
    page.wait_for_selector(".palette-nothing")
    said = page.inner_text(".palette-nothing-head")
    assert said == "Nothing on targum matches עגנון."
    assert page.get_attribute(".palette-upload", "href").startswith("/add")
    page.fill(".palette-bring input", "https://example.com/story")
    page.click(".palette-bring button[type=submit]")
    page.wait_for_url("**/add?source=https%3A%2F%2Fexample.com%2Fstory**", timeout=5000)
    context.close()


def test_the_librarys_box_is_the_search_held_to_the_library(browser) -> None:
    context, page, asked = _open(browser)
    page.wait_for_selector("#find")
    page.click("#find")
    page.wait_for_function("() => !document.getElementById('palette').hidden")
    assert (
        page.get_attribute("#palette-filters .tab[data-filter='library']", "aria-selected")
        == "true"
    )
    page.keyboard.type("ירושלם")
    page.wait_for_selector(".palette-group[data-group='library']")
    assert page.eval_on_selector_all(".palette-group", "els => els.map(e => e.dataset.group)") == [
        "library"
    ]
    assert page.evaluate("() => document.getElementById('find').value") == ""
    context.close()


def test_on_a_phone_it_is_the_whole_screen(browser) -> None:
    context, page, _ = _open(browser, width=390, height=844)
    page.evaluate("() => window.TargumPalette.show(true)")
    page.fill("#palette-find", "ירושלם")
    page.wait_for_selector(".palette-group[data-group='library']")
    page.wait_for_timeout(400)
    box = page.evaluate(
        """() => {
          const r = document.getElementById('palette').getBoundingClientRect();
          return {left: r.left, top: r.top, width: r.width, height: r.height,
                  back: getComputedStyle(document.getElementById('palette-back')).display,
                  esc: getComputedStyle(document.querySelector('.palette-esc')).display,
                  scroll: document.querySelector('.palette-body').scrollWidth
                    - document.querySelector('.palette-body').clientWidth};
        }"""
    )
    assert box["left"] == 0 and box["top"] == 0 and box["width"] == 390 and box["height"] == 844
    assert box["back"] != "none" and box["esc"] == "none"
    assert box["scroll"] <= 0, "nothing scrolls sideways"
    page.click("#palette-back")
    assert not _up(page), "the way back closes it"
    context.close()
