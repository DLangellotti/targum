"""A reader opened from a playlist, in a real browser (targum-internal#366).

design.md §12, "A playlist is swiped, and one press takes the set" (2026-09-23): a swipe
is a press and the next item plays; arriving plays nothing; inside a playlist a video
opens watching, without touching the text's own stores; an article is left from its end;
and after the last item there is an end, which #367 fills.

The readers are served the way the rest of the browser suite serves them. The list itself
is `GET /playlists/<id>.json`, answered here by a route with the shape `serve` answers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from test_reader_browser import (  # noqa: E402, F401
    address,
    browser,
    chapter,
    opened,
    video_reader,
)

PAUSED = "() => Array.from(document.querySelectorAll('video, audio')).every((m) => m.paused)"


def playlist(*readers: Path | None, failed: tuple[int, ...] = ()) -> dict:
    items = []
    for n, reader in enumerate(readers):
        gone = n in failed
        items.append(
            {
                "position": n,
                "reader": None if reader is None or gone else reader.parent.parent.name,
                "job": None,
                "title": f"Item {n + 1}",
                "failed": gone,
                "open": None if reader is None or gone else str(reader),
            }
        )
    return {"id": 7, "name": "Reels", "made_by": "reader", "made": 0, "items": items}


def listed(browser, answer: dict, *, touch: bool = False, viewport=None):  # noqa: F811
    context = opened(browser, viewport)
    if touch:
        context.close()
        context = browser.new_context(
            viewport=viewport or {"width": 390, "height": 844},
            reduced_motion="reduce",
            has_touch=True,
        )
    asked: list[str] = []

    def answer_list(route) -> None:  # type: ignore[no-untyped-def]
        asked.append(route.request.url)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(answer))

    context.route("**/playlists/*.json", answer_list)
    return context, asked


def at(reader: Path, n: int, go: bool = False) -> str:
    return address(reader) + f"?list=7&at={n}" + ("&go=1" if go else "")


def two_films(tmp_path: Path) -> tuple[Path, Path]:
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    return (
        video_reader(first, spans=[[0.0, 0.5], [0.5, 0.9]]),
        video_reader(second, spans=[[0.0, 0.5], [0.5, 0.9]]),
    )


def test_arriving_plays_nothing_and_next_plays_the_next(browser, tmp_path) -> None:  # noqa: F811
    """Criterion 1: the swipe is the press, and only the swipe."""
    one, two = two_films(tmp_path)
    context, _ = listed(browser, playlist(one, two))
    page = context.new_page()
    try:
        page.goto(at(one, 0))
        page.wait_for_selector("#list-nav .list-next")
        assert page.evaluate(PAUSED), "opening an item from its playlist plays nothing"
        assert page.evaluate("() => document.body.classList.contains('watching')"), (
            "inside a playlist a video opens watching"
        )
        page.click("#video .video-list-next")
        page.wait_for_url("**/two/**go=1")
        page.wait_for_selector("#list-nav")
        page.wait_for_function(
            "() => Array.from(document.querySelectorAll('video, audio')).some((m) => !m.paused)",
            timeout=5000,
        )
    finally:
        context.close()


def test_back_plays_nothing_new(browser, tmp_path) -> None:  # noqa: F811
    one, two = two_films(tmp_path)
    context, _ = listed(browser, playlist(one, two))
    page = context.new_page()
    try:
        page.goto(at(two, 1))
        page.wait_for_selector("#video .video-list-back")
        page.click("#video .video-list-back")
        page.wait_for_url("**/one/**at=0")
        assert "go=1" not in page.url
        page.wait_for_selector("#list-nav")
        assert page.evaluate(PAUSED)
    finally:
        context.close()


def test_a_swipe_up_moves_on_and_a_swipe_down_goes_back(browser, tmp_path) -> None:  # noqa: F811
    one, two = two_films(tmp_path)
    context, _ = listed(browser, playlist(one, two), touch=True)
    page = context.new_page()
    swipe = """
    (dy) => {
      const at = (y) =>
        new Touch({ identifier: 1, target: document.body, clientX: 200, clientY: y });
      const fire = (kind, touches, changed) =>
        document.body.dispatchEvent(
          new TouchEvent(kind, { touches, changedTouches: changed, bubbles: true })
        );
      fire('touchstart', [at(500)], [at(500)]);
      fire('touchend', [], [at(500 + dy)]);
    }
    """
    try:
        page.goto(at(one, 0))
        page.wait_for_selector("#list-nav")
        page.evaluate(swipe, -200)
        page.wait_for_url("**/two/**go=1")
        page.wait_for_selector("#list-nav")
        page.evaluate(swipe, 200)
        page.wait_for_url("**/one/**at=0")
    finally:
        context.close()


def test_an_article_is_read_before_it_is_left(browser, tmp_path) -> None:  # noqa: F811
    """A text is scrolled by the arrows until it runs out; only then do they move on.
    And the keys work with no pointer at all (criterion 3)."""
    text = chapter(tmp_path / "text" / "reader")
    one = video_reader(tmp_path / "film")
    context, _ = listed(browser, playlist(text, one))
    page = context.new_page()
    try:
        page.goto(at(text, 0))
        page.wait_for_selector("#list-nav")
        page.evaluate("() => window.scrollTo(0, 0)")
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(200)
        assert "/film/" not in page.url, "an arrow mid-text scrolls the text"
        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(200)
        page.keyboard.press("ArrowDown")
        page.wait_for_url("**/film/**go=1")
        page.wait_for_selector("#list-nav")
        # And Tab reaches Next, which Enter presses.
        page.focus("#list-nav .list-next")
        assert page.evaluate("() => document.activeElement.classList.contains('list-next')")
    finally:
        context.close()


def test_nothing_moves_under_reduced_motion(browser, tmp_path) -> None:  # noqa: F811
    """Criterion 2: the next item replaces this one; nothing travels."""
    one, two = two_films(tmp_path)
    context, _ = listed(browser, playlist(one, two))
    page = context.new_page()
    try:
        page.goto(at(one, 0))
        page.wait_for_selector("#list-nav")
        moving = page.evaluate(
            """() => [...document.querySelectorAll('#list-nav, #list-nav *, .video-list-next')]
                .map((el) => getComputedStyle(el))
                .filter((s) => parseFloat(s.transitionDuration) > 0 || s.animationName !== 'none')
                .length"""
        )
        assert moving == 0
    finally:
        context.close()


def test_the_text_alone_still_opens_as_its_transcript(browser, tmp_path) -> None:  # noqa: F811
    """Criterion 4: watching inside the playlist wrote nothing the text keeps."""
    one, two = two_films(tmp_path)
    context, _ = listed(browser, playlist(one, two))
    page = context.new_page()
    try:
        page.goto(at(one, 0))
        page.wait_for_selector("#list-nav")
        page.goto(address(one))
        page.wait_for_selector("#video:not([hidden])")
        page.wait_for_timeout(200)
        assert not page.evaluate("() => document.body.classList.contains('watching')")
        stored = page.evaluate(
            "() => Object.keys(localStorage).filter((k) => k.startsWith('targum:video-watch:'))"
        )
        assert stored == []
    finally:
        context.close()


def test_a_reader_opened_on_its_own_asks_for_no_list(browser, tmp_path) -> None:  # noqa: F811
    """Criterion 5's half that a browser can see: nothing is asked without `?list=`."""
    one, two = two_films(tmp_path)
    context, asked = listed(browser, playlist(one, two))
    page = context.new_page()
    try:
        page.goto(address(one))
        page.wait_for_selector("#video:not([hidden])")
        page.wait_for_timeout(300)
        assert asked == []
        assert page.query_selector("#list-nav") is None
    finally:
        context.close()


def test_the_ones_not_ready_are_passed_and_the_last_leads_to_the_end(
    browser,  # noqa: F811
    tmp_path,
) -> None:
    one, two = two_films(tmp_path)
    context, _ = listed(browser, playlist(one, None, two, one, failed=(3,)))
    page = context.new_page()
    try:
        page.goto(at(one, 0))
        page.wait_for_selector("#list-nav")
        assert "1 more is getting ready" in page.inner_text("#list-nav")
        page.click("#video .video-list-next")
        page.wait_for_url("**/two/**at=2**")
        page.wait_for_selector("#list-nav")
        assert page.get_attribute("#list-end", "hidden") is not None
        page.click("#video .video-list-next")
        # Empty until #367 fills it, so waited on as a state rather than as something seen.
        page.wait_for_function("() => document.getElementById('list-end').hidden === false")
        assert not page.evaluate("() => document.body.classList.contains('watching')")
        assert "/two/" in page.url, "the end is shown here, and nothing is loaded after it"
    finally:
        context.close()


def test_the_end_says_what_the_set_held_and_offers_one_next_set(
    browser,  # noqa: F811
    tmp_path,
) -> None:
    """#367: the end card is filled once from end.json, and its one door is a press page."""
    one, two = two_films(tmp_path)
    context, _ = listed(browser, playlist(one, two))
    ended: list[str] = []

    def answer_end(route) -> None:  # type: ignore[no-untyped-def]
        ended.append(route.request.url)
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "words": {"met": 84, "new": 12},
                    "next": {"id": 9, "name": "After Reels", "count": 5, "open": "/set/9"},
                }
            ),
        )

    context.route("**/playlists/7/end.json", answer_end)
    page = context.new_page()
    try:
        page.goto(at(two, 1))
        page.wait_for_selector("#list-nav")
        page.click("#video .video-list-next")
        page.wait_for_selector("#list-end .list-end-next")
        said = page.inner_text("#list-end")
        assert "You met 84 words, 12 of them new." in said
        assert "After Reels, 5 texts" in said
        assert page.get_attribute("#list-end .list-end-next", "href").startswith("/set/9")
        # Another press at the end loads nothing more and asks for nothing more.
        page.evaluate(
            "() => document.dispatchEvent(new KeyboardEvent('keydown', {key: 'ArrowDown'}))"
        )
        page.wait_for_timeout(300)
        assert len(ended) == 1, "the end offers more once, and never refills itself"
        assert "/two/" in page.url
    finally:
        context.close()
