"""Finish Your targums (targum-internal#716): design's §14 pass of 2026-11-14, in a real
browser.

One test per finding fixed, each failing on the page as it was: one figure for a text
on its shelf row, its Continue card and its playlist row (P1-1); a playlist's rows
offline (P1-2); the tabs with nothing on the shelf or a shelf that failed (P2-3); a
waiting row tagged Building (P2-4); a failed item counted as not done (P2-7); `lang`
after a move (P2-8); Alt+↑/↓ on a phone (P2-14); Save for offline on an empty playlist
(P2-15). The pages are the ones the server renders; the server's answers are routes.
"""

from __future__ import annotations

import copy
import json
from typing import Any
from urllib.parse import urlparse

import pytest

from targum.render.builder import list_page, playlists_page

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
