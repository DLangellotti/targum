"""A video text, in a real browser (targum-internal#422, David, 2026-10-05; design.md §12).

A text that carries a video opens with its picture up, standing one of two ways the reader
chooses in the bar and keeps: Beside — the picture at the left with one thin row of
controls under it and the transcript beside it — or Theatre — the picture large, the line
being said under it with its words tappable, and the transcript a panel one press away.
While it plays everything but the picture, the hairline of where the voice is and the line
steps back. On a phone it is the picture, its controls and the transcript under them.

It replaced the picture in a corner (picked up, moved and sized), its full-screen mode and
the floating strip under it. The tests that were about those went with them; the ones
about what a reader still has — the picture put away and brought back, the strip once it
is put away, the shape of the film — were carried here or left where they were.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

# The fixtures live in the browser module rather than a conftest, so they are
# imported by name to register them here.
from test_reader_browser import (  # noqa: E402, F401
    address,
    browser,
    open_reader,
    opened,
    press_in_more,
    settled,
    video_reader,
)
from test_word_tap_browser import talk  # noqa: E402

PHONE = {"width": 390, "height": 844}

#: How the page stands, what the line under the picture says, and which line is lit.
FILM = r"""
() => {
  const b = document.body.classList;
  const text = (s) => {
    const el = document.querySelector(s);
    return el ? el.textContent.replace(/[⁦-⁩]/g, '').trim() : '';
  };
  const now = document.querySelector('#reader .pair.voiced.now');
  return {
    film: b.contains('film'),
    beside: b.contains('film-beside'),
    theatre: b.contains('film-theatre'),
    panel: b.contains('film-panel'),
    quiet: b.contains('film-quiet'),
    card: b.contains('film-card'),
    pressed: [...document.querySelectorAll('[data-film-view]')]
      .filter((k) => k.getAttribute('aria-pressed') === 'true')
      .map((k) => k.getAttribute('data-film-view')),
    stored: localStorage.getItem('targum:film-view'),
    now: text('#film-sub .film-now'),
    tr: text('#film-sub .film-tr'),
    before: text('#film-sub .film-before'),
    after: text('#film-sub .film-after'),
    lit: now ? now.getAttribute('data-id') : null,
    transcript: document.getElementById('reader').getClientRects().length > 0,
    paused: document.querySelector('.video-el').paused,
  };
}
"""

#: Where things stand, in the window.
BOXES = """
(names) => {
  const out = {};
  for (const [name, sel] of Object.entries(names)) {
    const el = document.querySelector(sel);
    if (!el || !el.getClientRects().length) { out[name] = null; continue; }
    const r = el.getBoundingClientRect();
    out[name] = { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width };
  }
  return out;
}
"""

FIRST_LINE = "#reader .pair.voiced"


def film_open(browser, built: Path, viewport=None, view: str | None = None):  # noqa: F811
    """A reader with its picture up, standing `view` way if one is given."""
    context = opened(browser, viewport)
    if view:
        context.add_init_script(
            f"try {{ localStorage.setItem('targum:film-view', '{view}'); }} catch (e) {{}}"
        )
    page = context.new_page()
    page.goto(address(built))
    # Attached, not visible: in Theatre the transcript waits behind its press.
    page.wait_for_selector(".pair", state="attached")
    page.wait_for_selector("#video:not([hidden])")
    page.wait_for_function("() => window.TargumPlayer && window.TargumPlayer.length() > 0")
    return context, page


def seek(page, seconds: float) -> None:
    page.wait_for_function("() => window.TargumPlayer.seekable()")
    page.evaluate(f"() => window.TargumPlayer.seek({seconds})")
    page.wait_for_timeout(120)


def test_a_video_text_opens_beside_its_transcript(browser, tmp_path) -> None:  # noqa: F811
    """Beside is where a reader starts: the picture at the left, one thin row under it,
    what it is under that, and the transcript to its right. Listen is not in the bar —
    the row under the picture plays it — and nothing floats at the foot. Nothing plays
    until pressed, which is the rule that has held since the picture first came on."""
    built = video_reader(tmp_path, spans=[[0.05, 0.45], [0.5, 0.95]], lines=8)
    context, page = film_open(browser, built)
    try:
        seen = page.evaluate(FILM)
        assert seen["film"] and seen["beside"] and not seen["theatre"], seen
        assert seen["pressed"] == ["beside"], seen
        assert seen["paused"], "nothing plays until pressed"
        assert not page.locator(".bar .listen").is_visible(), "Listen stands down for the row"
        assert not page.locator("#player").is_visible(), "and no strip floats at the foot"
        at = page.evaluate(
            BOXES,
            {
                "picture": ".film-frame",
                "row": ".film-ctl",
                "about": ".film-about",
                "line": FIRST_LINE,
            },
        )
        assert at["row"]["top"] >= at["picture"]["bottom"] - 1, at
        assert abs(at["row"]["width"] - at["picture"]["width"]) < 2, (
            "the row is the picture's width"
        )
        assert at["about"]["top"] >= at["row"]["bottom"] - 1, at
        assert at["line"]["left"] >= at["picture"]["right"], f"the transcript is beside it: {at}"
        assert not page.locator("#film-sub").is_visible(), "the large line is Theatre's"
    finally:
        context.close()


def test_the_switch_is_kept_for_the_reader_not_for_the_text(browser, tmp_path) -> None:  # noqa: F811
    """Beside | Theatre in the bar, remembered per reader: how somebody likes to watch is
    a fact about them, like the speed. So a second text opens the way the first was
    left, and `v` turns between the two."""
    one = video_reader(tmp_path / "one")
    two = video_reader(tmp_path / "two")
    context, page = film_open(browser, one)
    try:
        page.click("[data-film-view='theatre']")
        seen = page.evaluate(FILM)
        assert seen["theatre"] and seen["pressed"] == ["theatre"], seen
        assert seen["stored"] == "theatre", seen
        assert not seen["transcript"], "the transcript waits behind its press"
        assert page.locator("#film-sub").is_visible(), "the line is under the picture"

        page.reload()
        page.wait_for_selector("#video:not([hidden])")
        page.wait_for_timeout(100)
        assert page.evaluate(FILM)["theatre"], "kept across the door"

        page.goto(address(two))
        page.wait_for_selector("#video:not([hidden])")
        page.wait_for_timeout(100)
        assert page.evaluate(FILM)["theatre"], "and on the next text"

        page.keyboard.press("v")
        seen = page.evaluate(FILM)
        assert seen["beside"] and seen["stored"] == "beside", seen
    finally:
        context.close()


def test_the_transcript_opens_beside_a_smaller_picture(browser, tmp_path) -> None:  # noqa: F811
    """In Theatre a press on Transcript opens it as a panel and the picture makes room;
    the panel's × and the same press shut it."""
    built = video_reader(tmp_path, lines=8)
    context, page = film_open(browser, built, view="theatre")
    try:
        wide = page.evaluate(BOXES, {"picture": ".film-frame"})["picture"]
        page.click(".film-transcript")
        seen = page.evaluate(FILM)
        assert seen["panel"] and seen["transcript"], seen
        assert page.get_attribute(".film-transcript", "aria-pressed") == "true"
        at = page.evaluate(BOXES, {"picture": ".film-frame", "line": FIRST_LINE})
        assert at["picture"]["width"] < wide["width"], "the picture grew smaller for it"
        assert at["line"]["left"] >= at["picture"]["right"], at
        page.click(".film-panel-close")
        seen = page.evaluate(FILM)
        assert not seen["panel"] and not seen["transcript"], seen
        assert page.evaluate("() => document.activeElement.classList.contains('film-transcript')")
    finally:
        context.close()


def test_the_line_under_the_picture_follows_the_voice(browser, tmp_path) -> None:  # noqa: F811
    """The line being said, set large, with its English under it and the lines either
    side faded — copied from the transcript as the clock reaches it, and lit there too.
    Between two lines it holds the one just said: it is a line of the transcript, not a
    caption over a film, so it does not blink out over a breath. (The full-screen
    subtitle it replaced did, and a test said so; that rule went with the mode.)"""
    built = video_reader(tmp_path, spans=[[0.05, 0.45], [0.5, 0.95]], lines=3)
    context, page = film_open(browser, built, view="theatre")
    try:
        seek(page, 0.2)
        seen = page.evaluate(FILM)
        assert seen["now"] == "שורה 1" and seen["tr"] == "A line.", seen
        assert seen["after"] == "שורה 2" and seen["before"] == "", seen
        assert seen["lit"] == "0001.000-aaaaaa", "the transcript lights the same line"

        seek(page, 0.6)
        seen = page.evaluate(FILM)
        assert seen["now"] == "שורה 2" and seen["before"] == "שורה 1", seen
        assert seen["lit"] == "0002.000-aaaaaa", seen

        seek(page, 0.47)
        assert page.evaluate(FILM)["now"] == "שורה 1", "between lines, the one just said"

        # Playing, it moves with the clock without anyone seeking.
        seek(page, 0.3)
        page.keyboard.press("Space")
        page.wait_for_function(
            "() => document.querySelector('#film-sub .film-now').textContent.includes('2')",
            timeout=4000,
        )
    finally:
        context.close()


def test_it_steps_back_while_playing_and_comes_back(browser, tmp_path) -> None:  # noqa: F811
    """C. Playing, the bar and the row fade until only the picture, the hairline and the
    line are left; the pointer brings them back, and a pause brings them back for good.
    Nothing steps back while a panel is out."""
    built = video_reader(tmp_path, spans=[[0.05, 0.45], [0.5, 0.95]], lines=3)
    context, page = film_open(browser, built, view="theatre")
    try:
        # The fixture film is a second long; held looping so it is still playing when
        # the row has waited its two and a half seconds.
        page.evaluate("() => { document.querySelector('.video-el').loop = true; }")
        page.mouse.move(5, 795)
        page.keyboard.press("Space")
        page.wait_for_function("() => document.body.classList.contains('film-quiet')", timeout=6000)
        shown = page.evaluate(
            """() => ({
              bar: getComputedStyle(document.querySelector('.bar')).opacity,
              play: getComputedStyle(document.querySelector('.film-play')).opacity,
              track: getComputedStyle(document.querySelector('.film-track')).opacity,
              line: getComputedStyle(document.querySelector('#film-sub')).opacity,
            })"""
        )
        assert shown == {"bar": "0", "play": "0", "track": "1", "line": "1"}, shown

        page.mouse.move(400, 400)
        assert not page.evaluate(FILM)["quiet"], "the pointer brings it back"
        page.wait_for_function("() => document.body.classList.contains('film-quiet')", timeout=6000)

        page.keyboard.press("Space")
        assert not page.evaluate(FILM)["quiet"], "a pause brings it back"
        page.wait_for_timeout(3000)
        assert not page.evaluate(FILM)["quiet"], "and it stays while paused"

        # A panel out holds it, however long it plays.
        page.click(".film-rate")
        page.wait_for_selector("#rates.open")
        page.evaluate("() => document.querySelector('.video-el').play()")
        page.wait_for_timeout(3200)
        assert not page.evaluate(FILM)["quiet"], "nothing steps back under an open panel"
    finally:
        context.close()


def test_a_word_is_tapped_beside_and_in_theatre(browser, tmp_path) -> None:  # noqa: F811
    """Words in the transcript Beside and in the line under the picture in Theatre open the
    reader's own card, with the reader's own levels on them. A word tapped while the voice
    runs stops it, so the card opens over a paused frame; in the line the word stays
    marked while its card is up, and the frame steps down under it."""
    built = talk(tmp_path, lines=12)
    context, page = film_open(browser, built)
    try:
        settled(page)
        page.wait_for_selector("#reader .pair.voiced .w")
        word = page.locator("#reader .pair.voiced .w").nth(2)
        said = word.inner_text()
        word.click()
        page.wait_for_selector("#gloss-card:not([hidden])")
        assert page.locator("#gloss-card .lemma").inner_text() == said

        page.keyboard.press("Escape")
        page.click("[data-film-view='theatre']")
        page.wait_for_selector("#film-sub .film-now .w")
        assert page.evaluate(
            "() => [...document.querySelectorAll('#film-sub .film-now .w')]"
            ".every((w) => w.hasAttribute('data-lemma'))"
        ), "the line's words are the transcript's, levels and all"
        page.evaluate("() => { document.querySelector('.video-el').loop = true; }")
        page.keyboard.press("Space")
        page.wait_for_function("() => !document.querySelector('.video-el').paused")

        word = page.locator("#film-sub .film-now .w").nth(3)
        said = word.inner_text()
        word.click()
        page.wait_for_selector("#gloss-card:not([hidden])")
        seen = page.evaluate(FILM)
        assert seen["paused"], "the tap stopped the voice"
        assert seen["card"], "the frame steps down under the card"
        assert page.locator("#gloss-card .lemma").inner_text() == said
        assert page.locator("#film-sub .w.looked-up").count() == 1, "the word stays marked"
    finally:
        context.close()


def test_the_arrow_keys_step_a_line_at_a_time(browser, tmp_path) -> None:  # noqa: F811
    """↑ and ↓ the line before and after, from wherever the voice is; in Theatre with
    the transcript put away ← and → as well, the way the page reads (a Hebrew text's
    next line is ←)."""
    built = video_reader(tmp_path, spans=[[0.05, 0.45], [0.5, 0.95]], lines=3)
    context, page = film_open(browser, built, view="theatre")
    try:
        seek(page, 0.2)
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(150)
        assert page.evaluate(FILM)["now"] == "שורה 2"
        assert page.evaluate("() => window.TargumPlayer.at()") >= 0.5
        page.keyboard.press("ArrowUp")
        page.wait_for_timeout(150)
        assert page.evaluate(FILM)["now"] == "שורה 1"
        page.keyboard.press("ArrowLeft")
        page.wait_for_timeout(150)
        assert page.evaluate(FILM)["now"] == "שורה 2", "← is on, in a text that reads leftward"
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(150)
        assert page.evaluate(FILM)["now"] == "שורה 1"
    finally:
        context.close()


def test_loop_this_line_holds_the_voice_on_it(browser, tmp_path) -> None:  # noqa: F811
    built = video_reader(tmp_path, spans=[[0.05, 0.45], [0.5, 0.95]], lines=3)
    context, page = film_open(browser, built)
    try:
        seek(page, 0.1)
        page.click(".film-loop")
        assert page.get_attribute(".film-loop", "aria-pressed") == "true"
        page.keyboard.press("Space")
        page.wait_for_timeout(1300)
        seen = page.evaluate(
            "() => ({ at: window.TargumPlayer.at(),"
            " paused: document.querySelector('.video-el').paused })"
        )
        assert not seen["paused"] and seen["at"] < 0.5, f"still on the first line: {seen}"
        page.click(".film-loop")
        assert page.get_attribute(".film-loop", "aria-pressed") == "false"
    finally:
        context.close()


def test_the_speed_is_a_panel_under_its_press(browser, tmp_path) -> None:  # noqa: F811
    """ "1× ▾" opens the six speeds as one of the bar's panels: focus goes in from the
    keyboard and back on Escape, and a pick sets the speed and shuts it."""
    built = video_reader(tmp_path)
    context, page = film_open(browser, built)
    try:
        page.focus(".film-rate")
        page.keyboard.press("Enter")
        page.wait_for_selector("#rates.open")
        assert page.get_attribute(".film-rate", "aria-expanded") == "true"
        assert page.evaluate(
            "() => document.getElementById('rates').contains(document.activeElement)"
        )
        under = page.evaluate(BOXES, {"press": ".film-rate", "panel": "#rates"})
        assert under["panel"]["top"] >= under["press"]["bottom"] - 1, under
        page.keyboard.press("Escape")
        page.wait_for_selector("#rates.open", state="detached")
        assert page.evaluate("() => document.activeElement.classList.contains('film-rate')")

        page.click(".film-rate")
        page.click("#rates [data-rate='1.5']")
        assert page.evaluate("() => document.querySelector('.video-el').playbackRate") == 1.5
        assert page.inner_text(".film-rate-now") == "1.5×"
        assert not page.locator("#rates").is_visible()
    finally:
        context.close()


def test_on_a_phone_the_picture_stands_over_its_controls_and_its_transcript(
    browser,  # noqa: F811
    tmp_path,
) -> None:
    """A, stacked: the picture the window's width, its row under it, and the transcript
    under that. No switch — a phone has the one way of standing — and no line under the
    picture, which is the transcript's job here."""
    built = video_reader(tmp_path, lines=8)
    context, page = film_open(browser, built, viewport=PHONE, view="theatre")
    try:
        assert not page.locator(".film-views").is_visible()
        assert not page.locator("#film-sub").is_visible()
        at = page.evaluate(
            BOXES, {"bar": ".bar", "picture": ".film-frame", "row": ".film-ctl", "line": FIRST_LINE}
        )
        assert at["picture"]["top"] >= at["bar"]["bottom"] - 1, at
        assert at["picture"]["left"] <= 1 and at["picture"]["right"] >= PHONE["width"] - 1, at
        assert at["row"]["top"] >= at["picture"]["bottom"] - 1, at
        assert at["line"]["top"] >= at["row"]["bottom"] - 1, at
        assert page.evaluate(FILM)["beside"], "it is Beside, whatever the wide window keeps"
    finally:
        context.close()


def test_every_thing_the_picture_had_is_still_under_more(browser, tmp_path) -> None:  # noqa: F811
    """The picture on and off, Hear first, the step either side, the file and full
    screen: what the corner window and the strip carried is in ⋯ while the picture is
    up. Hear first is one switch with the strip's."""
    built = video_reader(tmp_path)
    context, page = film_open(browser, built)
    try:
        page.click(".bar-tools [data-more]")
        for row in (".group [data-video]", ".more-first", ".more-back", ".more-on", ".more-get"):
            assert page.locator(row).is_visible(), f"{row} is under ⋯"
        assert page.locator("#fullscreen-group [data-fullscreen]").count() == 1
        page.click(".more-first")
        assert page.get_attribute(".player-first", "aria-pressed") == "true"
        assert page.get_attribute(".more-back", "aria-label") in (
            "Back a word",
            "Back five seconds",
        )
    finally:
        context.close()


def test_a_picture_put_away_is_an_audio_reader_and_comes_back(browser, tmp_path) -> None:  # noqa: F811
    """Put away, the page is what an audio text is (#421): Listen in the bar, the strip
    once it is pressed, and the strip's picture toggle to bring the picture back — kept
    per text, as it was. Back, the strip goes and the row under the picture plays."""
    built = video_reader(tmp_path)
    context, page = film_open(browser, built)
    try:
        press_in_more(page, ".group [data-video]")
        page.wait_for_selector("#video[hidden]", state="attached")
        seen = page.evaluate(FILM)
        assert not seen["film"], seen
        assert page.locator(".bar .listen").is_visible(), "Listen is back in the bar"

        page.reload()
        page.wait_for_selector(".pair")
        assert page.get_attribute("#video", "hidden") is not None, "it stayed away"

        page.click(".bar .listen-play")
        page.wait_for_selector("#player:not([hidden])")
        page.click(".player-video")
        page.wait_for_selector("#video:not([hidden])")
        assert page.evaluate(FILM)["film"]
        assert not page.locator("#player").is_visible(), "the row is the transport again"
    finally:
        context.close()
