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
import re
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
        page.wait_for_selector("#list-nav", state="attached")
        assert page.evaluate(PAUSED), "opening an item from its playlist plays nothing"
        assert page.evaluate("() => document.body.classList.contains('watching')"), (
            "inside a playlist a video opens watching"
        )
        page.click("#video .video-list-next")
        page.wait_for_url("**/two/**go=1")
        page.wait_for_selector("#list-nav", state="attached")
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
        page.wait_for_selector("#list-nav", state="attached")
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
        page.wait_for_selector("#list-nav", state="attached")
        page.evaluate(swipe, -200)
        page.wait_for_url("**/two/**go=1")
        page.wait_for_selector("#list-nav", state="attached")
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
        page.wait_for_selector("#list-nav", state="attached")
        page.evaluate("() => window.scrollTo(0, 0)")
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(200)
        assert "/film/" not in page.url, "an arrow mid-text scrolls the text"
        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(200)
        page.keyboard.press("ArrowDown")
        page.wait_for_url("**/film/**go=1")
        page.wait_for_selector("#list-nav", state="attached")
        # And Tab reaches the press, which Enter presses.
        page.focus("#done-mark")
        assert page.evaluate("() => document.activeElement.id === 'done-mark'")
    finally:
        context.close()


def test_nothing_moves_under_reduced_motion(browser, tmp_path) -> None:  # noqa: F811
    """Criterion 2: the next item replaces this one; nothing travels."""
    one, two = two_films(tmp_path)
    context, _ = listed(browser, playlist(one, two))
    page = context.new_page()
    try:
        page.goto(at(one, 0))
        page.wait_for_selector("#list-nav", state="attached")
        moving = page.evaluate(
            """() => [...document.querySelectorAll('#foot, #foot *, .video-list-next')]
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
        page.wait_for_selector("#list-nav", state="attached")
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
        page.wait_for_selector("#list-nav", state="attached")
        assert "1 more is getting ready" in page.inner_text("#foot-next")
        page.click("#video .video-list-next")
        page.wait_for_url("**/two/**at=2**")
        page.wait_for_selector("#list-nav", state="attached")
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
        page.wait_for_selector("#list-nav", state="attached")
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


def test_the_end_card_adds_up_what_each_item_came_to(browser, tmp_path) -> None:  # noqa: F811
    """design.md §12, "The finished box is three figures" (2026-09-25): each press keeps
    what its item came to, and the end card adds them up across the playlist."""
    one = chapter(tmp_path / "one" / "reader")
    two = other_text(tmp_path / "two" / "reader")
    context, _ = listed(browser, playlist(one, two))
    context.route(
        "**/playlists/7/end.json",
        lambda route: route.fulfill(status=200, content_type="application/json", body="{}"),
    )
    page = context.new_page()
    try:
        page.goto(at(one, 0))
        page.wait_for_selector("#list-nav", state="attached")
        page.evaluate("() => document.getElementById('done-mark').click()")
        page.wait_for_url("**/two/**go=1")
        page.wait_for_selector("#list-nav", state="attached")
        page.evaluate("() => document.getElementById('done-mark').click()")
        page.wait_for_selector("#list-end .list-end-tiles")
        tiles = page.inner_text("#list-end .list-end-tiles")
        assert "2\ntexts finished" in tiles, tiles
        assert re.search(r"\+[1-9]\d*\nwords known", tiles), tiles
        assert "100%\nknown here" in tiles, "every word marked, across both"
        assert "0\nwords looked up" in tiles
    finally:
        context.close()


# --- review fixes, 2026-09-24 -------------------------------------------------------

from test_reader_browser import dialogue  # noqa: E402


def test_the_end_names_the_words_and_its_door_is_a_pill(browser, tmp_path) -> None:  # noqa: F811
    one, two = two_films(tmp_path)
    context, _ = listed(browser, playlist(one, two))
    words = [
        {"word": "שלום", "language": "he", "new": True},
        {"word": "בית", "language": "he", "new": False},
    ]
    context.route(
        "**/playlists/7/end.json",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "words": {"met": 2, "new": 1, "list": words},
                    "next": {"id": 9, "name": "More like Reels", "count": 5, "open": "/set/9"},
                }
            ),
        ),
    )
    page = context.new_page()
    try:
        page.goto(at(two, 1))
        page.wait_for_selector("#list-nav", state="attached")
        page.click("#video .video-list-next")
        page.wait_for_selector("#list-end .list-end-next")
        got = page.evaluate(
            """() => {
              const door = getComputedStyle(document.querySelector('#list-end .list-end-next'));
              return {
                words: [...document.querySelectorAll('#list-end .list-end-list bdi')]
                  .map((w) => [w.textContent, w.getAttribute('lang')]),
                decoration: door.textDecorationLine,
                radius: door.borderRadius,
                dir: document.getElementById('list-end').getAttribute('dir'),
              };
            }"""
        )
        assert got["words"] == [["שלום", "he"], ["בית", "he"]]
        assert got["decoration"] == "none" and got["radius"] == "999px"
        assert got["dir"] == "ltr"
        assert "More like Reels, 5 texts" in page.inner_text("#list-end")
    finally:
        context.close()


def test_an_end_with_nothing_to_say_still_says_where_you_are(browser, tmp_path) -> None:  # noqa: F811
    one, two = two_films(tmp_path)
    context, _ = listed(browser, playlist(one, two))
    context.route("**/playlists/7/end.json", lambda route: route.fulfill(status=500, body="{}"))
    page = context.new_page()
    try:
        page.goto(at(two, 1))
        page.wait_for_selector("#list-nav", state="attached")
        page.click("#video .video-list-next")
        page.wait_for_selector("#list-end .list-end-home")
        assert "That's the end of Reels." in page.inner_text("#list-end")
        assert page.get_attribute("#list-end .list-end-home", "href").startswith("/playlists")
    finally:
        context.close()


def test_a_hebrew_title_keeps_its_punctuation_on_its_own_side(browser, tmp_path) -> None:  # noqa: F811
    text = chapter(tmp_path / "text" / "reader")
    one = video_reader(tmp_path / "film")
    answer = playlist(text, one)
    answer["items"][1]["title"] = "מה טבעונים אוכלים?"
    context, _ = listed(browser, answer)
    page = context.new_page()
    try:
        page.goto(at(text, 0))
        page.wait_for_selector("#foot-next .list-up-next bdi")
        got = page.evaluate(
            """() => ({
              dir: document.querySelector('#foot-next .list-ahead').getAttribute('dir'),
              title: document.querySelector('#foot-next .list-up-next bdi').textContent,
              isolated: document.querySelector('#foot-next .list-up-next bdi').getAttribute('dir'),
            })"""
        )
        assert got == {"dir": "ltr", "title": "מה טבעונים אוכלים?", "isolated": "auto"}
    finally:
        context.close()


@pytest.mark.parametrize("viewport", [None, {"width": 390, "height": 844}])
def test_next_stands_clear_of_the_player(browser, tmp_path, monkeypatch, viewport) -> None:  # noqa: F811
    """On an audio scene the strip stood over Next, and a press there hit Hear first."""
    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(tmp_path / "dialogues"))
    one = dialogue(tmp_path / "dialogues", tmp_path / "one" / "x", turns=3, words=True)
    two = dialogue(tmp_path / "dialogues", tmp_path / "two" / "x", turns=3, words=True)
    context, _ = listed(browser, playlist(one, two), viewport=viewport)
    page = context.new_page()
    try:
        page.goto(at(one, 0))
        page.wait_for_selector("#list-nav", state="attached")
        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(200)
        hit = page.evaluate(
            """() => {
              const box = document.getElementById('done-mark').getBoundingClientRect();
              const x = box.left + box.width / 2;
              const on = document.elementFromPoint(x, box.top + box.height / 2);
              const strip = document.getElementById('player').getBoundingClientRect();
              return [on && on.className, box.bottom <= strip.top || box.right <= strip.left];
            }"""
        )
        assert hit == ["foot-go", True]
    finally:
        context.close()


def test_the_arrow_turns_a_paged_scene_and_then_moves_on(browser, tmp_path, monkeypatch) -> None:  # noqa: F811
    """A page that fits the window has nothing to scroll, so the arrow turns it; at the
    foot of the last page it goes on to the next item. Before, it did nothing at all until
    the last page, and the key to Next looked dead."""
    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(tmp_path / "dialogues"))
    one = dialogue(tmp_path / "dialogues", tmp_path / "one" / "x", turns=40, span=0.05)
    two = dialogue(tmp_path / "dialogues", tmp_path / "two" / "x", turns=3)
    context = opened(browser, scrolling=False)
    answer = json.dumps(playlist(one, two))
    context.route(
        "**/playlists/*.json",
        lambda route: route.fulfill(status=200, content_type="application/json", body=answer),
    )
    page = context.new_page()
    try:
        page.goto(at(one, 0))
        page.wait_for_selector("#list-nav", state="attached")
        page.wait_for_function("() => document.body.classList.contains('paged')")
        pages = page.evaluate("() => window.TargumReader.onLastPage() ? 1 : 2")
        assert pages == 2, "the scene is long enough to be cut into pages"
        for _ in range(60):
            if "/two/" in page.url:
                break
            page.keyboard.press("ArrowDown")
            page.wait_for_timeout(60)
        page.wait_for_url("**/two/**go=1")
    finally:
        context.close()


# What a page says about a text: its document, whether a section of it is finished, and
# how many words are on the Hebrew list.
DOCUMENT = "() => JSON.parse(document.getElementById('targum-data').textContent).document"
RECORD = """(doc) => {
  const docs = JSON.parse(localStorage.getItem('targum:docs') || '{}');
  const words = JSON.parse(localStorage.getItem('targum:vocab:he') || '{}');
  return { sections: (docs[doc] || {}).sections || {}, known: Object.keys(words).length };
}"""


def other_text(out: Path) -> Path:
    """A second text. `chapter` builds the same words every time, and two readers of one
    text are one document: a press on the first would be news on nothing."""
    reader = chapter(out)
    page = reader.read_text(encoding="utf-8")
    found = re.search(r'"document": "([^"]+)"', page)
    assert found, "the page names its document"
    reader.write_text(page.replace(found.group(0), '"document": "another"', 1), encoding="utf-8")
    return reader


def test_the_press_finishes_marks_and_is_taken_back_where_it_lands(browser, tmp_path) -> None:  # noqa: F811
    """design.md §12, "The foot is one block" (2026-09-25). In a playlist the press is
    Next and says both halves; it finishes the item, marks the words never marked, and
    the page it leads to says so once, with one Undo that takes back both."""
    one = chapter(tmp_path / "one" / "reader")
    two = other_text(tmp_path / "two" / "reader")
    context, _ = listed(browser, playlist(one, two))
    page = context.new_page()
    try:
        page.goto(at(one, 0))
        page.wait_for_selector("#list-nav", state="attached")
        said = page.inner_text("#done-mark")
        assert said.startswith("Next, and mark ") and said.endswith(" words known")
        assert page.inner_text("#done-plain") == "Next without marking"
        assert page.inner_text("#list-nav") == "Reels, 1 of 2", "no Back on the first"
        document = page.evaluate(DOCUMENT)
        page.evaluate("() => document.getElementById('done-mark').click()")
        page.wait_for_url("**/two/**go=1")
        page.wait_for_selector("#arrived:not([hidden])")
        line = page.inner_text("#arrived")
        assert line.startswith("Finished Item 1 · ")
        # The finished box's three figures, on one line (§12, 2026-09-25).
        assert re.search(r"· \+[1-9]\d* known · \d+% · \d+ looked up", line), line
        state = page.evaluate(RECORD, document)
        assert state["sections"], "the item is finished"
        assert state["known"] > 0, "and its words are marked"
        page.click("#arrived-undo")
        state = page.evaluate(RECORD, document)
        assert state == {"sections": {}, "known": 0}, "one Undo takes back both"
        assert page.inner_text("#arrived") == "Taken back."
        # And a reload says nothing: the line is said once.
        page.reload()
        page.wait_for_selector("#list-nav", state="attached")
        assert page.is_hidden("#arrived")
    finally:
        context.close()


def test_a_swipe_finishes_without_marking(browser, tmp_path) -> None:  # noqa: F811
    """A swipe is a press, and marking words is never done by a gesture."""
    one = chapter(tmp_path / "one" / "reader")
    two = other_text(tmp_path / "two" / "reader")
    context, _ = listed(browser, playlist(one, two))
    page = context.new_page()
    try:
        page.goto(at(one, 0))
        page.wait_for_selector("#list-nav", state="attached")
        document = page.evaluate(DOCUMENT)
        page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
        page.wait_for_timeout(200)
        page.keyboard.press("ArrowDown")
        page.wait_for_url("**/two/**go=1")
        page.wait_for_selector("#arrived:not([hidden])")
        assert page.inner_text("#arrived").startswith("Finished Item 1")
        assert "marked known" not in page.inner_text("#arrived")
        state = page.evaluate(RECORD, document)
        assert state["known"] == 0, "nothing was marked"
        assert state["sections"], "and the item is finished"
    finally:
        context.close()
