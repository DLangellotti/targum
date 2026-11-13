"""Finish Home (targum-internal#695): design's §14 pass of 2026-11-13, in a real browser.

One test per finding fixed, each failing on the page as it was: offline rows and Upload,
a build waiting in line, the Hebrew names the pick and the waiting card draw from data,
More that fit you against the card above it, Continue's nouns, a cancelled build's line,
the building tiles, Building said twice, the card's text presses, the Russian row and
card, a thumb's reach, the first scene's card and a title's site name.

The page is the one the server renders (`list_page`), with the one card on; the server's
answers are routes. Skips itself without Playwright and its Chromium, as the other
browser tests do.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import pytest

from targum.finds import button
from targum.render.builder import list_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://home.test"
TOKEN = "k"


@pytest.fixture(scope="module")
def browser():
    try:
        driver = playwright_api.sync_playwright().start()
    except Exception as why:  # pragma: no cover - environment, not behaviour
        pytest.skip(f"Playwright will not start: {why}")
    try:
        running = driver.chromium.launch()
    except Exception as why:  # pragma: no cover - the browser itself is not installed
        driver.stop()
        pytest.skip(f"no Chromium: run `playwright install chromium` ({why})")
    yield running
    running.close()
    driver.stop()


@pytest.fixture(autouse=True)
def on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(button.FLAG, "1")


def reader(name: str, **fields: Any) -> dict[str, Any]:
    """A text of the reader's own on the shelf: an upload, so Continue holds it."""
    return {
        "name": name,
        "document": name,
        "entry": "",
        "title": "ספר",
        "language": "he",
        "register": "modern",
        "kind": "article",
        "sections": 1,
        "chapters": [],
        "readyChapters": 0,
        "built": 1_794_000_000,
        "drawn": False,
        "words": 100,
        **fields,
    }


def chapters(n: int) -> list[dict[str, Any]]:
    return [
        {"number": c, "title": f"פרק {c}", "file": f"sec-{c:04d}.html", "ready": True}
        for c in range(1, n + 1)
    ]


def job(**fields: Any) -> dict[str, Any]:
    return {
        "id": fields.pop("id", "j1"),
        "source": "https://traffic.omny.fm/d/clips/a/b/audio.mp3",
        "language": "he",
        "stage": "working",
        "done": 0,
        "total": 0,
        "made": 1_794_211_200,
        **fields,
    }


PICK = {
    "id": "hannah",
    "title": "חנה סנש: יומן",
    "language": "he",
    "kind": "novel",
    "register": "modern",
    "minutes": 14,
    "reason": {"key": "suggest.known", "share": 95},
    "fit": "band",
}


def more_row(n: int, kind: str = "article", **fields: Any) -> dict[str, Any]:
    return {
        "id": f"m{n}",
        "title": f"טקסט {n}",
        "language": "he",
        "kind": kind,
        "percent": 94,
        "reason": {"key": "suggest.known", "share": 94},
        "fit": "band",
        **fields,
    }


VIDEOS = [more_row(n, "talk", video=True) for n in range(6)]
TEXTS = [more_row(10 + n) for n in range(4)]

Answer = Callable[[dict[str, Any]], Any]


def home(
    browser,
    width: int,
    *,
    readers: list[dict[str, Any]] | None = None,
    jobs: Callable[[], list[dict[str, Any]]] | list[dict[str, Any]] | None = None,
    suggest: Answer | None = None,
    find: Answer | None = None,
    places: dict[str, Any] | None = None,
    language: str = "en",
    offline: bool = False,
    coarse: bool = False,
):
    html = list_page(TOKEN, "texts", language)
    posted: list[dict[str, Any]] = []

    def default_suggest(body: dict[str, Any]) -> Any:
        if body.get("instead_of"):
            return {"suggestion": None}
        return {"suggestion": PICK, "library": True, "more": VIDEOS}

    def answer(route, request):
        path = urlparse(request.url).path
        if path.startswith("/reader/") or path.startswith("/open/"):
            return route.fulfill(status=200, content_type="text/html", body="<p>elsewhere</p>")
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        if path.startswith("/thumb/"):
            return route.fulfill(status=404, body="")
        body = json.loads(request.post_data or "{}") if request.method == "POST" else {}
        said: Any = {}
        if path == "/readers":
            said = {"readers": readers or [reader("one")], "shared": [], "trash": []}
        elif path == "/jobs":
            said = {"jobs": (jobs() if callable(jobs) else jobs) or []}
        elif path == "/jobs/cancel":
            said = {"cancelled": True}
        elif path == "/account/places":
            return route.fulfill(status=401, content_type="application/json", body="{}")
        elif path == "/account/me":
            said = {"signedIn": False}
        elif path == "/suggest":
            said = (suggest or default_suggest)(body)
        elif path == "/find":
            posted.append(body)
            said = (find or (lambda _: {"pick": None}))(body)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(said))

    phone = width < 640
    context = browser.new_context(
        viewport={"width": width, "height": 900},
        is_mobile=phone,
        has_touch=phone,
        reduced_motion="reduce",
    )
    unplugged = "Object.defineProperty(Navigator.prototype, 'onLine', {get: () => false});"
    context.add_init_script(
        "sessionStorage.setItem('targum:arrival-over', '1');"
        "localStorage.setItem('targum:welcomed', '1');"
        "localStorage.setItem('targum:language', 'he');"
        + (
            f"localStorage.setItem('targum:places', {json.dumps(json.dumps(places))});"
            if places
            else ""
        )
        + (unplugged if offline else "")
    )
    page = context.new_page()
    thrown: list[str] = []
    page.on("pageerror", lambda error: thrown.append(str(error)))
    page.route(f"{SITE}/**", answer)
    if coarse:
        session = context.new_cdp_session(page)
        session.send(
            "Emulation.setEmulatedMedia",
            {
                "features": [
                    {"name": "pointer", "value": "coarse"},
                    {"name": "hover", "value": "none"},
                    {"name": "any-pointer", "value": "coarse"},
                ]
            },
        )
    page.goto(f"{SITE}/?k={TOKEN}")
    return context, page, thrown, posted


# -- P1 1 and 2: offline ------------------------------------------------------------------


def test_offline_a_row_says_not_on_this_device_under_its_title_and_keeps_its_height(
    browser,
) -> None:
    """Offline, "Not on this device" took a grid column of its own, 44px wide, and stood
    one word a line, each row three times its height (design, #695 P1 1). It is a line of
    the title's column now."""
    rows = [reader(f"t{n}", title=f"ספר {n}", minutes=9) for n in range(3)]
    context, page, thrown, _ = home(browser, 1440, readers=rows)
    page.wait_for_selector("#library-list .book-open")
    context.set_offline(True)
    page.wait_for_selector("#library-list li[data-offline='away'] .offline-tag")
    got = page.evaluate(
        """() => [...document.querySelectorAll('#library-list > li[data-offline]')].map((li) => {
          const tag = li.querySelector('.offline-tag');
          return {
            inMain: !!tag.closest('.row-main'),
            height: li.getBoundingClientRect().height,
            tagHeight: tag.getBoundingClientRect().height,
          };
        })"""
    )
    context.close()
    assert not thrown, thrown
    assert got, "no row was marked"
    for row in got:
        assert row["inMain"], row
        assert row["height"] < 100, row
        assert row["tagHeight"] < 30, row


def test_offline_upload_your_own_is_greyed_with_its_own_reason(browser) -> None:
    """Offline, the one card dimmed Watch and Upload and put "Not on this device" under
    both, as if Upload were a text (design, #695 P1 2). Upload is greyed with "Uploading
    needs a connection." under it, and the pick's own note stays with the pick."""
    context, page, thrown, _ = home(
        browser,
        1440,
        suggest=lambda body: {"suggestion": {**PICK, "reader": "/reader/hannah/reader/index.html"}},
    )
    page.wait_for_selector("#try-next .rc-open")
    context.set_offline(True)
    page.wait_for_selector(".rc-foot .offline-reason")
    page.wait_for_selector("#try-next .offline-tag")
    got = page.evaluate(
        """() => {
          const up = document.querySelector('.rc-foot a');
          return {
            off: up.classList.contains('offline-off'),
            dimmedWith: !!up.closest('.offline-away'),
            said: document.querySelector('.rc-foot .offline-reason').textContent,
            notHereInFoot: [...document.querySelectorAll('.rc-foot .offline-tag')]
              .map((e) => e.textContent),
            cardMarked: document.getElementById('read-card').hasAttribute('data-offline'),
            pickMarked: document.getElementById('try-next').getAttribute('data-offline'),
          };
        }"""
    )
    context.close()
    assert not thrown, thrown
    assert got["off"] and not got["dimmedWith"], got
    assert got["said"] == "Uploading needs a connection.", got
    assert got["notHereInFoot"] == ["Uploading needs a connection."], got
    assert not got["cardMarked"] and got["pickMarked"] == "away", got


# -- P1 3: a build waiting in line ---------------------------------------------------------

WHERE = """() => [...document.querySelectorAll('.home-card.is-building')].map((card) => ({
  title: (card.querySelector('.home-card-title') || {}).textContent || '',
  where: (card.querySelector('.home-card-where') || {}).textContent || '',
  bar: !!card.querySelector('.home-bar'),
  tile: (card.querySelector('.thumb') || {}).className || '',
  link: !!card.querySelector('.home-link-glyph'),
  from: [...card.querySelectorAll('.home-card-from bdi')].map((b) => b.getAttribute('lang')),
}))"""


@pytest.mark.parametrize("language", ["en", "ru"])
def test_a_waiting_build_says_how_many_are_ahead_and_a_running_one_says_where_it_is(
    browser, language: str
) -> None:
    """A queued card drew the running card's sliver and the same words, so a build
    waiting in line looked like one running (design, #695 P1 3; David on #694). Waiting,
    it says how many builds are ahead and draws no bar; running, the server's line."""
    jobs = [
        job(id="q", title="תור", stage="queued", behind=2),
        job(
            id="w", title="רץ", stage="working", done=12, total=40, said="12 of 40 sentences ready."
        ),
    ]
    context, page, thrown, _ = home(browser, 1440, jobs=jobs, language=language)
    page.wait_for_function("document.querySelectorAll('.home-card.is-building').length === 2")
    got = {card["title"]: card for card in page.evaluate(WHERE)}
    context.close()
    assert not thrown, thrown
    waiting = {"en": "Waiting behind 2 builds", "ru": "В очереди перед ним 2 текста"}[language]
    assert got["תור"]["where"] == waiting and not got["תור"]["bar"], got
    assert got["רץ"]["where"] == "12 of 40 sentences ready." and got["רץ"]["bar"], got


# -- P1 4: Hebrew names from data -----------------------------------------------------------


def test_hebrew_names_from_data_say_their_language(browser) -> None:
    """The show, who presents it and who makes it (#1197, #1202) carried no lang, on the
    pick and on the waiting card (design, #695 P1 4)."""
    episode = {
        **PICK,
        "id": "find-44",
        "find": 44,
        "origin": "find",
        "title": "פרק 12",
        "kind": "podcast",
        "credits": 48,
        "source_line": {
            "name": "השעה הבינלאומית",
            "url": "https://www.kan.org.il/p/1/",
            "presenter": "ערן סיקורל",
            "by": "כאן",
        },
    }
    jobs = [job(id="a", title="פרק 12", show="השעה הבינלאומית", presenter="ערן סיקורל", by="כאן")]
    context, page, thrown, _ = home(
        browser, 1440, jobs=jobs, suggest=lambda body: {"suggestion": episode, "more": []}
    )
    page.wait_for_selector("#try-next .rc-source")
    page.wait_for_selector(".home-card.is-building .home-card-from")
    pick = page.evaluate(
        "() => [...document.querySelectorAll('#try-next .rc-source bdi')]"
        ".map((b) => [b.getAttribute('lang'), b.getAttribute('dir')])"
    )
    card = page.evaluate(WHERE)[0]
    context.close()
    assert not thrown, thrown
    assert pick == [["he", "auto"]] * 3, pick
    assert card["from"] == ["he"] * 3, card


# -- P1 5: More that fit you ------------------------------------------------------------------

MORE = (
    "() => [...document.querySelectorAll('#more-fit:not([hidden]) #more-rows li .more-title')]"
    ".map((e) => e.textContent)"
)


def test_more_takes_the_card_s_filter_and_never_repeats_the_pick(browser) -> None:
    """More that fit you ignored the card: six videos under Texts, and the pick Harder
    had just drawn as its first row (design, #695 P1 5). It asks again with the card's
    filter, and leaves out what the card shows."""

    def find(body: dict[str, Any]) -> Any:
        if body.get("chips"):
            return {"chips": [], "listen": False}
        if body.get("more_fit"):
            return {"more": TEXTS if body.get("medium") == "read" else VIDEOS}
        if body.get("step") == "harder":
            return {"pick": VIDEOS[0]}
        if body.get("medium") == "read":
            return {"pick": {**PICK, "id": "t-pick", "title": "מאמר"}}
        return {"pick": None}

    context, page, thrown, posted = home(browser, 1440, find=find)
    page.wait_for_selector("#more-fit:not([hidden])")
    first = page.evaluate(MORE)
    page.click("#try-next .rc-step-harder")
    page.wait_for_selector("#try-next .home-card-title:has-text('טקסט 0')")
    after_harder = page.evaluate(MORE)
    page.click("#try-next .rc-topic")
    page.wait_for_selector("#rc-topics .rc-media .tab")
    page.click("#rc-topics .rc-media .tab:has-text('Texts')")
    page.wait_for_selector("#try-next .home-card-title:has-text('מאמר')")
    page.wait_for_function(
        "() => [...document.querySelectorAll('#more-rows .more-title')]"
        ".some((e) => e.textContent === 'טקסט 10')"
    )
    texts = page.evaluate(MORE)
    context.close()
    assert not thrown, thrown
    assert first == [f"טקסט {n}" for n in range(6)], first
    assert "טקסט 0" not in after_harder and len(after_harder) == 5, after_harder
    assert texts == [f"טקסט {10 + n}" for n in range(4)], texts
    assert any(body.get("more_fit") and body.get("medium") == "read" for body in posted), posted


def test_more_is_not_drawn_where_the_card_says_nothing_fits(browser) -> None:
    """ "No new text is 90% known for you yet." stood over six texts at 93–95% (design,
    #695 P1 5)."""
    context, page, thrown, _ = home(
        browser, 1440, suggest=lambda body: {"suggestion": None, "library": True, "more": VIDEOS}
    )
    page.wait_for_selector("#try-next .rc-says")
    page.wait_for_timeout(300)
    hidden = page.evaluate("() => document.getElementById('more-fit').hidden")
    context.close()
    assert not thrown, thrown
    assert hidden


# -- P2 6, 7, 18: Continue's nouns and titles -------------------------------------------------

CONTINUE = """() => [...document.querySelectorAll('#continue-cards .home-card')].map((card) => ({
  tag: (card.querySelector('.home-tag') || {}).textContent || '',
  title: (card.querySelector('.home-card-title') || {}).textContent || '',
  facts: (card.querySelector('.home-card-facts') || {}).textContent || '',
  go: (card.querySelector('.home-card-go') || {}).textContent || '',
}))"""


def test_continue_says_one_noun_per_text_and_a_video_is_a_video(browser) -> None:
    """An article read "Article · part 1 of 4" over "Pick up at chapter 1", Ruth "Tanakh
    · part 2 of 4" over "Pick up at chapter 2"; a video's card said "of the whole text"
    and its row "9 min read"; and Continue kept Wikinews' name on a headline (design,
    #695 P2 6, 7, 18)."""
    rows = [
        reader(
            "news",
            title="הפועל חולון היא אלופת המדינה – ויקיחדשות",
            kind="article",
            sections=4,
            chapters=chapters(4),
        ),
        reader("ruth", title="רות", kind="tanakh", sections=4, chapters=chapters(4)),
        reader("heart", title="הכירו את הלב", kind="talk", video=True, minutes=9, estimated=0.89),
    ]
    now = int(time.time() * 1000)
    places = {
        "news": {"section": "2", "path": "/reader/news/reader/sec-0002.html", "at": now - 1_000},
        "ruth": {"section": "2", "path": "/reader/ruth/reader/sec-0002.html", "at": now - 2_000},
    }
    context, page, thrown, _ = home(browser, 1440, readers=rows, places=places)
    page.wait_for_function("document.querySelectorAll('#continue-cards .home-card').length === 3")
    got = {card["title"]: card for card in page.evaluate(CONTINUE)}
    lengths = page.evaluate(
        "() => [...document.querySelectorAll('#library-list .book-facts')]"
        ".map((e) => e.textContent)"
    )
    context.close()
    assert not thrown, thrown
    news = got["הפועל חולון היא אלופת המדינה"]
    assert news["tag"] == "Article · part 2 of 4" and news["go"] == "Pick up at part 2", news
    ruth = got["רות"]
    assert ruth["tag"] == "Tanakh · chapter 2 of 4" and ruth["go"] == "Pick up at chapter 2", ruth
    heart = got["הכירו את הלב"]
    assert "of the whole video" in heart["facts"] and "text" not in heart["facts"], heart
    assert any("9 min video" in line for line in lengths), lengths
    assert not any("min read" in line for line in lengths if "9 min" in line), lengths


# -- P2 8: a cancelled build says so before it goes ------------------------------------------


def test_a_cancelled_waiting_build_says_so_on_home_before_it_goes(browser) -> None:
    """Cancel on a waiting card: the card went at the next `/jobs`, three seconds on, so
    "Cancelled. Nothing was used." was never read (design, #695 P2 8)."""
    gone = {"yes": False}

    def jobs() -> list[dict[str, Any]]:
        if gone["yes"]:
            return []
        return [job(id="q", title="תור", stage="queued", behind=1, cancellable=True)]

    context, page, thrown, _ = home(browser, 1440, jobs=jobs)
    page.wait_for_selector(".home-card.is-building .home-card-cancel button")
    gone["yes"] = True
    page.click(".home-card.is-building .home-card-cancel button")
    page.wait_for_timeout(3_400)
    during = page.evaluate(
        "() => [...document.querySelectorAll('.home-card.is-building')].map((c) => c.textContent)"
    )
    page.wait_for_timeout(2_000)
    after = page.evaluate("() => document.querySelectorAll('.home-card.is-building').length")
    context.close()
    assert not thrown, thrown
    assert len(during) == 1 and "Cancelled. Nothing was used." in during[0], during
    assert after == 0


# -- P2 9 and 10: the building tiles, and Building once ---------------------------------------


def test_a_bare_link_s_tile_is_a_link_and_an_episode_keeps_its_colour(browser) -> None:
    """A bare upload's tile was an empty grey block, and an episode was clay on the pick
    and grey once building (design, #695 P2 9)."""
    jobs = [
        job(id="b", title="https://traffic.omny.fm/d/clips/a/b/audio.mp3"),
        job(id="e", title="פרק 12", show="השעה הבינלאומית", kind="podcast"),
    ]
    context, page, thrown, _ = home(browser, 1440, jobs=jobs)
    page.wait_for_function("document.querySelectorAll('.home-card.is-building').length === 2")
    got = {card["title"]: card for card in page.evaluate(WHERE)}
    context.close()
    assert not thrown, thrown
    assert got["traffic.omny.fm"]["link"], got
    assert "tone-spoken" in got["פרק 12"]["tile"], got


def test_a_building_row_says_building_once_at_a_desk(browser) -> None:
    """ "27% done · Building" beside a Building tag (design, #695 P2 10)."""
    jobs = [job(id="w", title="רץ", done=27, total=100)]
    context, page, thrown, _ = home(browser, 1440, jobs=jobs)
    page.wait_for_selector("#library-list li.is-building")
    seen = page.evaluate(
        """() => [...document.querySelectorAll('#library-list li.is-building *')]
          .filter((e) => e.children.length === 0 && e.textContent.trim() === 'Building')
          .filter((e) => e.getBoundingClientRect().width > 0).length"""
    )
    context.close()
    assert not thrown, thrown
    assert seen == 1


# -- P2 11 and 12: the card's presses ----------------------------------------------------------

PRESSES = """() => {
  const q = (s) => document.querySelector(s);
  const teal = getComputedStyle(document.documentElement).getPropertyValue('--teal').trim();
  const probe = document.createElement('span');
  probe.style.color = teal; document.body.appendChild(probe);
  const tealRgb = getComputedStyle(probe).color; probe.remove();
  return {
    tealRgb,
    else: getComputedStyle(q('#try-next .rc-else')).color,
    filter: getComputedStyle(q('#try-next .rc-topic')).color,
    tops: ['.rc-open', '.rc-else', '.rc-topic']
      .map((s) => Math.round(q('#try-next ' + s).getBoundingClientRect().top)),
  };
}"""


@pytest.mark.parametrize("language", ["en", "ru"])
def test_something_else_and_filter_are_presses_in_the_primary_on_one_line(
    browser, language: str
) -> None:
    """Something else and Filter were muted grey text, the only presses on the desk in
    muted, and in Russian Фильтр fell to a line of its own at 1440 (design, #695 P2 11,
    12)."""
    video = {**VIDEOS[0], "id": "v-pick", "minutes": 11}
    context, page, thrown, _ = home(
        browser, 1440, language=language, suggest=lambda body: {"suggestion": video, "more": []}
    )
    page.wait_for_selector("#try-next .rc-topic")
    got = page.evaluate(PRESSES)
    context.close()
    assert not thrown, thrown
    assert got["else"] == got["tealRgb"] and got["filter"] == got["tealRgb"], got
    assert len(set(got["tops"])) == 1, got


# -- P2 13 and 14: Russian ---------------------------------------------------------------------


def test_a_russian_row_keeps_its_length_and_the_card_speaks_to_you(browser) -> None:
    """«Начато» alone where English says "Started · 9 min read", and «Знаю 91%» in the
    first person (design, #695 P2 13, 14)."""
    rows = [reader(f"t{n}", title="כוח משיכה - מבוא (הקדמה)", minutes=9) for n in range(2)]
    pick = {**PICK, "reason": {"key": "suggest.known", "share": 91}}
    context, page, thrown, _ = home(
        browser,
        1440,
        readers=rows,
        language="ru",
        suggest=lambda body: {"suggestion": pick, "more": []},
    )
    page.wait_for_selector("#library-list .book-facts")
    page.wait_for_selector("#try-next .rc-known")
    got = page.evaluate(
        """() => ({
          shown: [...document.querySelectorAll('#library-list .book-facts')].map((line) => {
            const box = line.getBoundingClientRect();
            return [...line.querySelectorAll('.fact')]
              .filter((f) => {
                const r = f.getBoundingClientRect();
                return r.width > 0 && r.top < box.bottom - 1;
              })
              .map((f) => f.textContent);
          }),
          known: document.querySelector('#try-next .rc-known').textContent,
          room: [...document.querySelectorAll('#library-list .book-facts')].map((line) =>
            [line.getBoundingClientRect().width, line.scrollWidth, line.textContent]),
        })"""
    )
    context.close()
    assert not thrown, thrown
    for facts in got["shown"]:
        assert "9 мин чтения" in facts, got
    assert got["known"].startswith("Вы знаете"), got


# -- P2 15: a thumb's reach ---------------------------------------------------------------------

REACH = """(selector) => [...document.querySelectorAll(selector)].map((el) => {
  const r = el.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const hit = (x, y) => {
    const e = document.elementFromPoint(x, y);
    return !!e && (e === el || el.contains(e));
  };
  let up = 0; for (let d = 1; d <= 30; d++) { if (hit(cx, cy - d)) up = d; else break; }
  let dn = 0; for (let d = 1; d <= 30; d++) { if (hit(cx, cy + d)) dn = d; else break; }
  return up + dn + 1;
})"""


def test_a_row_s_more_and_more_that_fit_you_reach_44_under_a_thumb(browser) -> None:
    """Under a coarse pointer a row's ⋯ answered over 30px and More's rows over 41–42
    (design, #695 P2 15; §8)."""
    sourced = [
        {
            **row,
            "source_line": {"name": "Khan Academy Hebrew", "url": "https://he.khanacademy.org/"},
        }
        for row in VIDEOS
    ]
    context, page, thrown, _ = home(
        browser,
        390,
        coarse=True,
        readers=[reader("one", minutes=9)],
        suggest=lambda body: {"suggestion": PICK, "more": sourced},
    )
    page.wait_for_selector("#more-fit:not([hidden]) #more-rows li a")
    page.wait_for_selector("#library-list .row-more")
    reach: list[int] = []
    for selector in ("#library-list .row-more", "#more-rows li > a"):
        for at in range(page.locator(selector).count()):
            # In the middle of the glass: the phone's bar is fixed over its foot.
            page.evaluate(
                "([s, n]) => document.querySelectorAll(s)[n].scrollIntoView({block: 'center'})",
                [selector, at],
            )
            reach.append(page.evaluate(REACH, selector)[at])
    context.close()
    assert not thrown, thrown
    assert reach and min(reach) >= 44, reach


# -- P2 16: Start here -----------------------------------------------------------------------------


def test_the_first_scene_says_what_it_is_how_long_and_its_share(browser) -> None:
    """The Hebrew beginner's "Start here" drew its title alone (design, #695 P2 16)."""
    scene = {
        "id": "scene-01",
        "title": "בבית קפה",
        "language": "he",
        "kind": "dialogue",
        "minutes": 3,
        "reason": {"key": "suggest.estimated", "share": 72},
        "scene": {"first": True},
    }
    context, page, thrown, _ = home(
        browser, 1440, suggest=lambda body: {"suggestion": scene, "more": []}
    )
    page.wait_for_selector("#try-next .rc-pick")
    got = page.evaluate(
        """() => ({
          label: document.getElementById('rc-label').textContent,
          facts: (document.querySelector('#try-next .home-card-facts') || {}).textContent || '',
          known: (document.querySelector('#try-next .rc-known') || {}).textContent || '',
        })"""
    )
    context.close()
    assert not thrown, thrown
    assert got["label"] == "Start here", got
    assert got["facts"] == "Conversation · 3 min", got
    assert got["known"].startswith("About 72%"), got
