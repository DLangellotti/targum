"""Finish Your targums (targum-internal#716): design's §14 pass of 2026-11-14, in a real
browser.

One test per finding fixed, each failing on the page as it was: one figure for a text
on its shelf row, its Continue card and its playlist row (P1-1); a playlist's rows
offline (P1-2); the tabs with nothing on the shelf or a shelf that failed (P2-3); a
waiting row tagged Building (P2-4); a failed item counted as not done (P2-7); `lang`
after a move (P2-8); Alt+↑/↓ on a phone (P2-14); Save for offline on an empty playlist
(P2-15). The second pass: presses greyed offline (P2-9); one fault block (P2-10); no
chip at nought (P2-11); no New on what was cancelled (P2-13); Find by author (P2-16);
a recording tagged Audio (P2-17); a title given the row's slack at a desk (P2-18). The
pages are the ones the server renders; the server's answers are routes.
"""

from __future__ import annotations

import copy
import json
from typing import Any
from urllib.parse import urlparse

import pytest

from targum.render.builder import list_page, playlists_page, subscription_page

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

SITE = "http://yours.test"
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


#: The design pass's text: 70% marked, 97% our estimate. Its marks do not settle it.
FIGURE = {"known": 0.7, "estimated": 0.97, "words": 66_040}


def reader(name: str, **fields: Any) -> dict[str, Any]:
    return {
        "name": name,
        "document": name,
        "entry": "",
        "title": "שכול וכשלון",
        "language": "he",
        "register": "modern",
        "kind": "novel",
        "sections": 1,
        "chapters": [],
        "readyChapters": 0,
        "built": 1_794_000_000,
        "drawn": False,
        **FIGURE,
        **fields,
    }


def item(position: int, **fields: Any) -> dict[str, Any]:
    name = f"t{position}"
    return {
        "position": position,
        "reader": name,
        "job": None,
        "title": "שכול וכשלון",
        "failed": False,
        "open": f"/reader/{name}/reader/index.html",
        "facts": {
            "name": name,
            "entry": "",
            "language": "he",
            "kind": "novel",
            "video": False,
            "seconds": 0,
            "minutes": 30,
            **FIGURE,
        },
        **fields,
    }


def playlist(**fields: Any) -> dict[str, Any]:
    return {
        "id": 1,
        "name": "Morning commute",
        "made_by": "reader",
        "made": 1,
        "at": None,
        "covers": [],
        "seconds": 3600,
        "known": 0.7,
        "estimated": 0.97,
        "ready": 2,
        "waiting": 0,
        "failed": 0,
        "unconfirmed": 0,
        "credits": 0,
        "language": "he",
        "items": [item(0), item(1)],
        **fields,
    }


def open_page(
    browser,
    html: str,
    path: str,
    answers: dict[str, Any],
    *,
    width: int = 1440,
    coarse: bool = False,
    post: Any = None,
):
    """`path` on SITE, its document `html`, every ask answered from `answers` (a value, or
    (status, value)); a POST answered with `post`."""

    def answer(route, request):
        where = urlparse(request.url).path
        if request.resource_type == "document":
            return route.fulfill(status=200, content_type="text/html", body=html)
        if where.startswith("/thumb/"):
            return route.fulfill(status=404, body="")
        if request.method == "POST" and post is not None and where.startswith("/playlists/"):
            return route.fulfill(status=200, content_type="application/json", body=json.dumps(post))
        said = answers.get(where, {})
        status, said = said if isinstance(said, tuple) else (200, said)
        if where == "/account/places" and where not in answers:
            status = 401
        route.fulfill(status=status, content_type="application/json", body=json.dumps(said))

    context = browser.new_context(
        viewport={"width": width, "height": 900},
        is_mobile=coarse,
        has_touch=coarse,
        reduced_motion="reduce",
    )
    context.add_init_script(
        "sessionStorage.setItem('targum:arrival-over', '1');"
        "localStorage.setItem('targum:welcomed', '1');"
        "localStorage.setItem('targum:arrived', 'everyday');"
        "localStorage.setItem('targum:language', 'he');"
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
                    {"name": "any-pointer", "value": "coarse"},
                    {"name": "hover", "value": "none"},
                ]
            },
        )
    page.goto(f"{SITE}{path}?k={TOKEN}")
    return context, page, thrown


def one_playlist(browser, one: dict[str, Any], **options: Any):
    context, page, thrown = open_page(
        browser,
        playlists_page(TOKEN),
        "/playlists/1",
        {"/playlists/1.json": one, "/account/me": {"signedIn": True}},
        **options,
    )
    page.wait_for_selector("#one .item, #one .note")
    return context, page, thrown


def home(browser, answers: dict[str, Any], width: int = 1440):
    return open_page(
        browser,
        list_page(TOKEN, "texts", "en"),
        "/",
        {"/account/me": {"signedIn": False}, "/suggest": {}, **answers},
        width=width,
    )


# -- P1-1: one figure ----------------------------------------------------------------------


def test_a_text_s_row_and_its_continue_card_say_one_figure(browser) -> None:
    """Continue said "about 97% (our estimate)" and the row's meter under it the marked
    70%: the meter now says the text's one figure, as ours."""
    context, page, thrown = home(
        browser, {"/readers": {"readers": [reader("t0")], "shared": [], "trash": []}}
    )
    page.wait_for_selector("#library-list .row-meter.meter")
    page.wait_for_selector("#continue-cards li")
    meter = page.locator("#library-list .row-meter.meter").first.get_attribute("aria-label")
    card = page.locator("#continue-cards").inner_text()
    context.close()
    assert not thrown, thrown
    assert meter == "You know about 97% of the whole text (our estimate)"
    assert "You know about 97% of the whole text (our estimate)" in card


def test_a_playlist_says_the_same_figure_as_ours(browser) -> None:
    """The playlist's Known column and its head said the marked 70%."""
    context, page, thrown = one_playlist(browser, playlist())
    rows = page.eval_on_selector_all(".pl-items .pl-share", "all => all.map((s) => s.textContent)")
    head = page.locator(".pl-head .pl-share").text_content()
    context.close()
    assert not thrown, thrown
    assert rows == ["About 97% (our estimate)"] * 2
    assert head == "About 97% (our estimate)"


# -- P1-2: offline -------------------------------------------------------------------------


def test_offline_a_playlist_s_row_keeps_its_height(browser) -> None:
    """Offline, "Not on this device" stood in the number column one word a line, every
    row four lines tall. It is a line of the title's column now."""
    context, page, thrown = one_playlist(browser, playlist())
    page.wait_for_selector(".pl-items .item-title")
    context.set_offline(True)
    page.wait_for_selector(".pl-items .item[data-offline] .offline-tag")
    got = page.evaluate(
        """() => [...document.querySelectorAll('.pl-items .item[data-offline]')].map((li) => {
          const tag = li.querySelector('.offline-tag');
          return {
            inTitle: !!tag.closest('.item-what'),
            height: li.getBoundingClientRect().height,
            tagHeight: tag.getBoundingClientRect().height,
          };
        })"""
    )
    context.close()
    assert not thrown, thrown
    assert got
    for row in got:
        assert row["inTitle"] and row["height"] < 110 and row["tagHeight"] < 30, row


# -- P2-3: the tabs --------------------------------------------------------------------------


def test_the_tabs_stay_when_the_shelf_could_not_be_loaded(browser) -> None:
    context, page, thrown = home(browser, {"/readers": (500, {"error": "no"})})
    page.wait_for_selector("#nothing:not([hidden])")
    tabs = page.locator("#yours-tabs").is_visible()
    links = page.eval_on_selector_all("#yours-tabs .tab", "all => all.map((a) => a.dataset.tab)")
    context.close()
    assert tabs, "a reader with playlists still reaches them"
    assert links == ["recent", "playlists", "subscriptions", "uploads"]


# -- P2-4: a waiting row ---------------------------------------------------------------------


def test_a_row_waiting_in_line_says_waiting_with_no_meter(browser) -> None:
    waiting = {
        "id": "j1",
        "source": "https://example.com/a",
        "title": "כתבה",
        "language": "he",
        "stage": "queued",
        "behind": 1,
        "done": 0,
        "total": 0,
        "made": 1_794_211_200,
    }
    context, page, thrown = home(
        browser,
        {
            "/readers": {"readers": [reader("t0")], "shared": [], "trash": []},
            "/jobs": {"jobs": [waiting]},
        },
    )
    page.wait_for_selector("#library-list .row-status.is-waiting")
    got = page.evaluate(
        """() => {
          const row = document.querySelector('#library-list .row-status.is-waiting').closest('li');
          return {
            tag: row.querySelector('.row-status').textContent,
            meter: !!row.querySelector('.meter'),
          };
        }"""
    )
    context.close()
    assert not thrown, thrown
    assert got == {"tag": "Waiting", "meter": False}


# -- P2-7, P2-8, P2-14, P2-15: the playlist's page -----------------------------------------


def test_a_failed_item_is_counted_apart_and_named_by_its_medium(browser) -> None:
    failed = {
        "position": 2,
        "reader": None,
        "job": "j9",
        "title": "פודקאסט",
        "failed": True,
        "open": None,
        "facts": None,
        "medium": "listen",
    }
    making = dict(failed, position=3, job="j10", failed=False, medium=None)
    one = playlist(items=[item(0), item(1), failed, making], waiting=1, failed=1)
    context, page, thrown = one_playlist(browser, one)
    line = page.locator(".pl-head .pl-getting-ready").text_content()
    row = page.locator(".item.failed .item-kind").text_content()
    context.close()
    assert not thrown, thrown
    assert line == "Getting ready · 2 of 3 done · 1 failed"
    assert row == "We couldn't get this recording ready. Remove it, then add it again."


def test_a_move_keeps_the_titles_language(browser) -> None:
    """The move's answer carried no language, so the titles still getting ready became
    `lang=en` (P2-8); the page keeps the one it had."""
    making = {
        "position": 2,
        "reader": None,
        "job": "j10",
        "title": "כתבה",
        "failed": False,
        "open": None,
        "facts": None,
    }
    one = playlist(items=[item(0), item(1), making], waiting=1)
    moved = copy.deepcopy(one)
    del moved["language"]
    context, page, thrown = open_page(
        browser,
        playlists_page(TOKEN),
        "/playlists/1",
        {"/playlists/1.json": one, "/account/me": {"signedIn": True}},
        post=moved,
    )
    page.wait_for_selector("#one .item")
    page.locator(".item[data-position='1'] .grip").focus()
    page.keyboard.press("Alt+ArrowUp")
    page.wait_for_timeout(300)
    langs = page.eval_on_selector_all(
        ".pl-items .item-title bdi", "all => all.map((b) => b.getAttribute('lang'))"
    )
    context.close()
    assert not thrown, thrown
    assert langs == ["he", "he", "he"]


def test_a_phone_is_told_what_its_finger_does(browser) -> None:
    context, page, thrown = one_playlist(browser, playlist(), width=390, coarse=True)
    note = page.locator(".pl-reorder-note").text_content()
    context.close()
    assert note == "Drag ≡ to reorder."


def test_an_empty_playlist_offers_nothing_to_save(browser) -> None:
    context, page, thrown = one_playlist(
        browser, playlist(items=[], ready=0, known=None, estimated=None)
    )
    page.wait_for_selector("#one .note")
    saving = page.locator("#one .pl-offline").count()
    context.close()
    assert not thrown, thrown
    assert saving == 0


# -- the second pass ---------------------------------------------------------------------


def a_subscription(**fields: Any) -> dict[str, Any]:
    """A channel that builds, on, with one item ready to get ready and its cap."""
    from test_subscriptions_browser import _row

    one = _row(
        id=2,
        kind="channel",
        key="UC1",
        name="כאן ארכיון",
        hebrew="",
        page="/subscriptions/2",
        every="feed",
        perWeek=2.1,
        builds=True,
        cap=60,
        used=12,
        caps=[30, 60, 120, 240],
        items=[
            {
                "key": "v1",
                "title": "איך מזמינים קפה",
                "link": "https://youtu.be/v1",
                "reader": "",
                "state": "listed",
                "why": "",
                "came": "",
                "seen": False,
                "found": 6_000,
                "published": 6_000,
                "seconds": 600,
                "credits": 0,
                "building": False,
            }
        ],
    )
    one.update(fields)
    return {"signedIn": True, "subscription": one, "credits": {"left": 354, "back": "December 1"}}


def one_subscription(browser, answer: Any, **options: Any):
    context, page, thrown = open_page(
        browser,
        subscription_page(TOKEN),
        "/subscriptions/2",
        {"/subscriptions/2.json": answer, "/account/me": {"signedIn": True}},
        **options,
    )
    return context, page, thrown


# P2-9


def test_offline_the_presses_that_need_us_are_greyed(browser) -> None:
    """Pause, Get it ready and the cap's Save stood live offline and failed when pressed."""
    context, page, thrown = one_subscription(browser, a_subscription())
    page.wait_for_selector(".sub-pause")
    page.wait_for_selector(".sub-cap-save")
    context.set_offline(True)
    page.wait_for_selector(".sub-pause[aria-disabled='true']")
    got = page.evaluate(
        """() => ['.sub-pause', '.sub-act.is-quiet', '.sub-cap-save'].map((at) => {
          const press = document.querySelector(at);
          return [at, press && press.getAttribute('aria-disabled'), press && press.dataset.why];
        })"""
    )
    page.click(".sub-pause", force=True)
    context.set_offline(False)
    page.wait_for_selector(".sub-pause:not([aria-disabled])")
    context.close()
    assert not thrown, thrown
    # Get it ready goes to Upload, so it says what Upload's presses say.
    assert got == [
        [".sub-pause", "true", "This needs a connection."],
        [".sub-act.is-quiet", "true", "Uploading needs a connection."],
        [".sub-cap-save", "true", "This needs a connection."],
    ]


def test_offline_new_playlist_is_greyed(browser) -> None:
    context, page, thrown = open_page(
        browser,
        playlists_page(TOKEN),
        "/playlists",
        {"/playlists.json": {"playlists": [playlist()]}, "/account/me": {"signedIn": True}},
    )
    page.wait_for_selector("#new-press:not([hidden]), .pl-new-card")
    context.set_offline(True)
    page.wait_for_selector("#new-press[aria-disabled='true'], .pl-new-card[aria-disabled='true']")
    live = page.eval_on_selector_all(
        "#new-press:not([hidden]), .pl-new-card",
        "all => all.filter((b) => b.getAttribute('aria-disabled') !== 'true').length",
    )
    context.close()
    assert not thrown, thrown
    assert live == 0


# P2-10


def test_recent_playlists_and_subscriptions_draw_one_fault_block(browser) -> None:
    """Three blocks for one fault: Subscriptions had a small tonal Try again and no Tell
    us, Playlists no line of what is still here."""

    def block(page, at: str) -> dict[str, Any]:
        page.wait_for_selector(f"{at} .fault-panel-row")
        return page.eval_on_selector(
            f"{at} .fault-panel-row",
            """(row) => ({
              presses: [...row.children].map((c) => c.className),
              fact: row.querySelector('.fault-fact').textContent,
            })""",
        )

    context, page, _ = home(browser, {"/readers": (500, {"error": "no"})})
    recent = block(page, "#nothing")
    context.close()
    context, page, _ = open_page(
        browser,
        playlists_page(TOKEN),
        "/playlists",
        {"/playlists.json": (500, {"error": "no"}), "/account/me": {"signedIn": True}},
    )
    lists = block(page, "#fault")
    context.close()
    context, page, _ = one_subscription(browser, (502, {"error": "no"}))
    subs = block(page, ".sub-fault")
    context.close()
    assert recent == {
        "presses": ["fault-go", "fault-fact", "fault-act"],
        "fact": "Everything you've read is still here.",
    }
    assert lists == recent and subs == recent, (lists, subs)


# P2-11


def test_a_subscription_chip_is_absent_at_nought(browser) -> None:
    from test_subscriptions_browser import ROWS

    context, page, thrown = open_page(
        browser,
        list_page(TOKEN, "texts", "en"),
        "/",
        {
            "/account/me": {"signedIn": True},
            "/suggest": {},
            "/readers": {"readers": [reader("t0")], "shared": [], "trash": []},
            "/subscriptions.json": {
                "signedIn": True,
                "subscriptions": ROWS[:2],
                "series": [],
                "credits": {"left": 354, "back": "December 1"},
            },
        },
    )
    page.wait_for_selector("#yours-tabs [data-tab='subscriptions']")
    page.click("#yours-tabs [data-tab='subscriptions']")
    page.wait_for_selector("#subs-chips .chip")
    chips = page.eval_on_selector_all("#subs-chips .chip", "all => all.map((c) => c.textContent)")
    context.close()
    assert not thrown, thrown
    assert chips == ["All 2", "Series 1", "Channels 1"]


# P2-13


def test_what_the_reader_cancelled_is_not_new(browser) -> None:
    answer = a_subscription()
    answer["subscription"]["items"][0].update(why="cancelled")
    context, page, thrown = one_subscription(browser, answer)
    page.wait_for_selector(".sub-item")
    got = page.evaluate(
        """() => ({
          fresh: document.querySelectorAll('.sub-item .sub-new, .sub-item.is-new').length,
          said: document.querySelector('.sub-item .sub-item-state').textContent,
        })"""
    )
    context.close()
    assert not thrown, thrown
    assert got == {"fresh": 0, "said": "You cancelled this"}


# P2-16, P2-17, P2-18: Recent's rows


def shelf_of(*rows: dict[str, Any]) -> dict[str, Any]:
    return {"readers": list(rows), "shared": [], "trash": []}


def test_find_matches_who_wrote_it(browser) -> None:
    rows = [reader(f"t{n}", title=f"סיפור {n}", built=1_794_000_000 - n) for n in range(6)]
    rows[3]["author"] = "Yosef Haim Brenner"
    context, page, thrown = home(browser, {"/readers": shelf_of(*rows)})
    page.wait_for_selector("#shelf-find:not([hidden])")
    page.fill("#shelf-find", "brenner")
    page.wait_for_function("document.querySelectorAll('#library-list .book-title').length === 1")
    title = page.locator("#library-list .book-title").inner_text()
    context.close()
    assert not thrown, thrown
    assert title == "סיפור 3"


def test_a_recording_is_tagged_audio(browser) -> None:
    """ "[115] Yair Lapid…" was tagged Text over "40 min audio"."""
    recording = reader("t0", title="ראיון", kind="article", heard=True, seconds=2400)
    context, page, thrown = home(browser, {"/readers": shelf_of(recording)})
    page.wait_for_selector("#library-list .row-tag")
    got = page.evaluate(
        """() => ({
          tag: document.querySelector('#library-list .row-tag').textContent,
          line: document.querySelector('#library-list .book-facts').textContent,
        })"""
    )
    context.close()
    assert not thrown, thrown
    assert got["tag"] == "Audio" and "40 min audio" in got["line"], got


def test_at_a_desk_a_title_takes_the_row_s_slack(browser) -> None:
    """Titles were cut at about 190px beside about 120px of empty row."""
    long = reader("t0", title="אויב שקט ומסוכן: בעקבות המלחמה הארוכה ביותר", kind="article")
    book = reader("t1", built=1_793_000_000)
    context, page, thrown = home(browser, {"/readers": shelf_of(long, book)})
    page.wait_for_selector("#library-list .row-tag")
    got = page.evaluate(
        """() => {
          const rows = [...document.querySelectorAll('#library-list.shelf-rows > li')];
          const left = (li, at) => Math.round(li.querySelector(at).getBoundingClientRect().left);
          return {
            title: rows[0].querySelector('.book-title').getBoundingClientRect().width,
            tags: rows.map((li) => left(li, '.row-tag')),
            meters: rows.map((li) => left(li, '.row-meter')),
          };
        }"""
    )
    context.close()
    assert not thrown, thrown
    assert got["title"] > 260, got
    # The columns still stand in line.
    assert len(set(got["meters"])) == 1, got
