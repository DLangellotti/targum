"""The listening view, in a real browser (design.md §12, "Listening is a view of its own",
2026-10-10; boards ListenPhone, ListenWordPhone and ListenLock).

One player: the view drives the reader's own recording, so every check here reads the
reader's `TargumPlayer` rather than anything the view keeps.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("playwright.sync_api")

from test_reader_browser import (  # noqa: E402, F401
    PHONE,
    address,
    browser,
    dialogue,
    opened,
)

#: Six one-second turns of silence: room to step, hold a line and play on.
SPAN = 1.0
TURNS = 6


@pytest.fixture
def scene(browser, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(tmp_path / "dialogues"))
    built = dialogue(
        tmp_path / "dialogues", tmp_path / "reader", turns=TURNS, span=SPAN, words=True
    )
    context = opened(browser, viewport=PHONE)
    page = context.new_page()
    page.goto(address(built))
    page.wait_for_function("() => !!(window.TargumPlayer && window.TargumPlayer.lines)")
    page.wait_for_function("() => window.TargumPlayer.length() > 0")
    yield page
    context.close()


def open_view(page) -> None:
    page.click("#player .player-listen")
    page.wait_for_selector("#listen-view:not([hidden])")


def test_the_strip_opens_the_view_and_the_view_shows_the_line_being_said(scene) -> None:
    open_view(scene)
    shown = scene.evaluate(
        """() => ({
          now: document.querySelector('.lv-now .film-pair').getAttribute('data-id'),
          first: TargumPlayer.lines()[0].id,
          after: document.querySelector('.lv-after').textContent.length > 0,
          translation: document.querySelector('.lv-tr').textContent,
          expanded: document.querySelector('#player .player-listen').getAttribute('aria-expanded'),
          stored: sessionStorage.getItem('targum:listen-view'),
          playing: !TargumPlayer.paused(),
        })"""
    )
    assert shown["now"] == shown["first"]
    assert shown["after"], "the line after stands faint under it"
    assert shown["translation"] == "Line 0."
    assert shown["expanded"] == "true"
    assert shown["stored"] == "1", "open from one part to the next, for the tab"
    assert shown["playing"] is False, "opening the view plays nothing"
    scene.click(".lv-down")
    assert scene.evaluate("() => document.getElementById('listen-view').hidden")
    assert scene.evaluate("() => sessionStorage.getItem('targum:listen-view')") is None


def test_the_view_plays_and_pauses_the_one_player(scene) -> None:
    open_view(scene)
    scene.click(".lv-play")
    scene.wait_for_function("() => !TargumPlayer.paused() && TargumPlayer.at() > 0.2")
    scene.wait_for_function(
        "() => document.querySelector('.lv-play').getAttribute('aria-pressed') === 'true'"
    )
    assert scene.evaluate("() => document.body.classList.contains('voicing')"), (
        "the reader's own state says the voice is going"
    )
    scene.click(".lv-play")
    scene.wait_for_function("() => TargumPlayer.paused()")
    scene.wait_for_function(
        "() => document.querySelector('.lv-play').getAttribute('aria-label') === 'Play'"
    )


def test_the_steps_are_lines(scene) -> None:
    open_view(scene)
    scene.click(".lv-on")
    scene.wait_for_function("() => Math.abs(TargumPlayer.at() - 1.01) < 0.05")
    assert scene.get_attribute(".lv-on", "aria-label") == "Forward one line"
    scene.click(".lv-on")
    scene.wait_for_function("() => Math.abs(TargumPlayer.at() - 2.01) < 0.05")
    assert scene.evaluate(
        "() => document.querySelector('.lv-now .film-pair').getAttribute('data-id')"
    ) == scene.evaluate("() => TargumPlayer.lines()[2].id")
    scene.click(".lv-back")
    scene.wait_for_function("() => Math.abs(TargumPlayer.at() - 1.01) < 0.05")


def test_a_held_line_plays_again_until_it_is_let_go(scene) -> None:
    open_view(scene)
    scene.click(".lv-on")
    scene.wait_for_function("() => Math.abs(TargumPlayer.at() - 1.01) < 0.05")
    scene.click(".lv-loop")
    assert scene.get_attribute(".lv-loop", "aria-pressed") == "true"
    scene.click(".lv-play")
    scene.wait_for_timeout(1600)
    at = scene.evaluate("() => TargumPlayer.at()")
    assert 1.0 <= at < 2.05, f"the voice stays on the line it holds, not {at}"
    scene.click(".lv-loop")
    assert scene.get_attribute(".lv-loop", "aria-pressed") == "false"


def test_a_word_tapped_pauses_and_keep_listening_plays_on_from_there(scene) -> None:
    open_view(scene)
    scene.click(".lv-play")
    scene.wait_for_function("() => !TargumPlayer.paused() && TargumPlayer.at() > 0.3")
    scene.click(".lv-now .w >> nth=0")
    scene.wait_for_selector("#gloss-card:not([hidden]) .card-keep")
    stopped = scene.evaluate("() => TargumPlayer.at()")
    assert scene.evaluate("() => TargumPlayer.paused()")
    assert scene.evaluate("() => document.body.classList.contains('listen-carded')")
    assert not scene.evaluate("() => document.querySelector('.lv-paused').hidden"), "it says paused"
    assert scene.get_attribute("#gloss-card .card-x", "aria-label") == "Close and keep listening"
    scene.click("#gloss-card .card-keep")
    scene.wait_for_function("() => document.getElementById('gloss-card').hidden")
    scene.wait_for_function("() => !TargumPlayer.paused()")
    assert scene.evaluate("() => TargumPlayer.at()") >= stopped - 0.05
    assert not scene.evaluate("() => document.body.classList.contains('listen-carded')")


def test_escape_puts_the_view_away(scene) -> None:
    open_view(scene)
    scene.keyboard.press("Escape")
    scene.wait_for_function("() => document.getElementById('listen-view').hidden")


def test_the_lock_screen_says_the_text_and_the_line_and_steps_a_line(scene) -> None:
    """Board ListenLock: outside a playlist the Media Session names the text and carries
    the line being said; its back and forward are a line."""
    scene.click("#player .player-play")
    scene.wait_for_function("() => !!(navigator.mediaSession && navigator.mediaSession.metadata)")
    said = scene.evaluate(
        "() => { const m = navigator.mediaSession.metadata; return [m.title, m.artist, m.album]; }"
    )
    assert said[0].startswith("A scene")
    assert said[1], "the line being said is on the lock screen"
    assert said[2] == "targum"


def test_with_nothing_after_it_up_next_says_so(scene) -> None:
    open_view(scene)
    assert scene.evaluate("() => document.querySelector('.lv-next').hidden")
    scene.click(".lv-queue-open")
    scene.wait_for_selector("#listen-queue:not([hidden])")
    assert scene.is_visible(".lv-qempty")
    scene.click(".lv-qdone")
    assert scene.evaluate("() => document.getElementById('listen-queue').hidden")


def test_inside_a_playlist_up_next_is_the_playlist_and_play_in_order_is_play_on(
    browser,  # noqa: F811
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(tmp_path / "dialogues"))
    one = dialogue(tmp_path / "dialogues", tmp_path / "one", turns=3)
    two = dialogue(tmp_path / "dialogues", tmp_path / "two", turns=3)
    answer = {
        "id": 7,
        "name": "On the bus",
        "made_by": "reader",
        "made": 0,
        "items": [
            {
                "position": n,
                "reader": r.parent.parent.name,
                "title": f"Item {n + 1}",
                "failed": False,
                "open": str(r),
                "facts": {"kind": "dialogue", "minutes": 3},
            }
            for n, r in enumerate((one, two))
        ],
    }
    context = opened(browser, viewport=PHONE)
    context.route(
        "**/playlists/*.json",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(answer)
        ),
    )
    page = context.new_page()
    try:
        page.goto(address(one) + "?list=7&at=0")
        page.wait_for_selector("#list-nav", state="attached")
        open_view(page)
        page.wait_for_selector(".lv-next:not([hidden])")
        assert page.inner_text(".lv-next-name") == "Item 2"
        page.click(".lv-next")
        page.wait_for_selector("#listen-queue:not([hidden])")
        rows = page.evaluate(
            """() => [...document.querySelectorAll('.lv-qlist a.lv-qrow')].map((a) => [
              a.querySelector('.lv-qname').textContent, a.getAttribute('href'),
            ])"""
        )
        assert len(rows) == 1 and rows[0][0] == "Item 2"
        assert "list=7&at=1" in rows[0][1] and "listen=1" in rows[0][1]
        assert "On the bus" in page.text_content(".lv-qlist .lv-grp")
        page.click(".lv-order")
        assert page.evaluate("() => localStorage.getItem('targum:play-on')") == "1"
        assert page.evaluate(
            """() => [...document.querySelectorAll('.list-play-on')]
              .every((b) => b.getAttribute('aria-checked') === 'true')"""
        ), "one switch, said in both places"
    finally:
        context.close()


def test_arriving_to_listen_from_a_press_opens_the_view_and_plays(
    browser,  # noqa: F811
    tmp_path,
    monkeypatch,
) -> None:
    """What an Up next row and Play in order open: the view, left open for the tab, and the
    voice. The way a reader gets there is a press on this site, which is what lets the
    browser start a sound on the page it lands on, so the test arrives the same way."""
    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(tmp_path / "dialogues"))
    built = dialogue(tmp_path / "dialogues", tmp_path / "reader", turns=3)
    context = opened(browser, viewport=PHONE)
    page = context.new_page()
    try:
        page.goto(address(built))
        open_view(page)
        page.evaluate(
            """(to) => {
              const row = document.createElement('a');
              row.className = 'lv-qrow probe';
              row.href = to;
              row.textContent = 'next';
              document.querySelector('.lv-qbody').appendChild(row);
            }""",
            address(built) + "?listen=1",
        )
        page.click(".lv-queue-open")
        page.click("a.probe")
        page.wait_for_url("**?listen=1")
        page.wait_for_selector("#listen-view:not([hidden])")
        page.wait_for_function("() => window.TargumPlayer && TargumPlayer.at() > 0.1")
    finally:
        context.close()


def test_arriving_cold_to_listen_waits_for_the_press_and_says_nothing_wrong(
    browser,  # noqa: F811
    tmp_path,
    monkeypatch,
) -> None:
    """Opened with `?listen=1` and no press on the site, the browser refuses the sound
    (NotAllowedError). That is not a muted tab, so nothing says it is: the view stands
    open with its play waiting, and one press plays."""
    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(tmp_path / "dialogues"))
    built = dialogue(tmp_path / "dialogues", tmp_path / "reader", turns=3)
    context = opened(browser, viewport=PHONE)
    context.add_init_script("sessionStorage.setItem('targum:listen-view', '1')")
    # The browser's answer to the arrival's own start, kept where the test can wait on it.
    context.add_init_script(
        """(() => {
          const play = HTMLMediaElement.prototype.play;
          HTMLMediaElement.prototype.play = function () {
            const asked = play.call(this);
            if (!window.__answered && asked && asked.then) {
              asked.then(
                () => { window.__answered = 'played'; },
                (why) => { window.__answered = why.name; }
              );
            }
            return asked;
          };
        })()"""
    )
    page = context.new_page()
    try:
        page.goto(address(built) + "?listen=1")
        page.wait_for_selector("#listen-view:not([hidden])")
        page.wait_for_function("() => !!window.__answered")
        # Whether a browser lets a page nobody pressed on start a sound is its own call;
        # refused, the play waits for the press.
        if page.evaluate("() => window.__answered") == "NotAllowedError":
            page.wait_for_function(
                "() => document.querySelector('.lv-play').getAttribute('aria-label') === 'Play'"
            )
        assert not page.evaluate(
            "() => document.getElementById('player').classList.contains('refused')"
        ), "a refusal to start by itself is not a fault to show"
        assert (
            page.evaluate("() => document.querySelector('.player-said').textContent").find("muted")
            < 0
        )
        if page.evaluate("() => TargumPlayer.paused()"):
            page.click(".lv-play")
        page.wait_for_function("() => !TargumPlayer.paused() && TargumPlayer.at() > 0.1")
    finally:
        context.close()
