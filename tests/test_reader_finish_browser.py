"""The reader's finish pass (targum-internal#464, design.md §14, 2026-10-19).

Each test pins a state the QA pass on a hosted copy found below the bar:

- a word's look-up past three seconds says it is still looking (§14, slow);
- the connection's band reads left to right on a Hebrew page;
- a play the page interrupted itself is not said as a recording that would not play;
- on a phone the strip's clock leaves the play button alone;
- a chapter that cannot be started says why on a line, and the press says Try again.

    uv sync --extra browser && uv run playwright install chromium
"""

# The fixtures are imported by name from the browser module, which ruff reads as
# redefinitions wherever a test takes one as an argument.
# ruff: noqa: F811

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from test_chapter_ui import _render_book  # noqa: E402
from test_reader_browser import (  # noqa: E402, F401
    PHONE,
    TAP_ANY,
    address,
    browser,
    built,
    dialogue,
    opened,
    scene,
    strip_up,
)

ORIGIN = "http://reader.test"


def served_page(browser, html: str, gloss=None, chapter=None, viewport=None):
    """A reader served with a key, so the card can ask and the waiting note can press."""
    context = opened(browser, viewport=viewport)
    page = context.new_page()

    def answer(route, request):
        if "/gloss" in request.url:
            if request.post_data_json.get("free") or gloss is None:
                route.fulfill(status=200, content_type="application/json", body='{"meaning": null}')
            else:
                gloss(route)
        elif "/chapter" in request.url and chapter is not None:
            chapter(route)
        elif request.url.split("?")[0].endswith(".html"):
            route.fulfill(status=200, content_type="text/html", body=html)
        else:
            route.fulfill(status=200, content_type="application/json", body="{}")

    page.route(ORIGIN + "/**", answer)
    return context, page


def test_a_look_up_past_three_seconds_says_it_is_still_looking(browser, built: Path) -> None:
    """design.md §14, line 1: past 3 s a wait says so. The card said "looking…" for as
    long as the model took, the same at four seconds as at forty."""
    held: list = []
    context, page = served_page(browser, built.read_text(encoding="utf-8"), gloss=held.append)
    try:
        page.goto(ORIGIN + "/reader/a-build/reader/index.html?k=test")
        page.wait_for_selector(".pair")
        page.evaluate(TAP_ANY)
        page.wait_for_selector("#gloss-card .look-up")
        page.eval_on_selector("#gloss-card .look-up", "button => button.click()")
        page.wait_for_timeout(500)
        soon = page.inner_text("#gloss-card .look-up")
        page.wait_for_timeout(3000)
        later = page.inner_text("#gloss-card .look-up")
    finally:
        context.close()

    assert held, "the look-up went out and was held"
    assert soon == "looking…"
    assert later == "still looking…"


def test_the_connection_band_reads_left_to_right_on_a_hebrew_page(browser, built: Path) -> None:
    """Its words are the interface's. Made empty with `dir="auto"`, Chrome settled it on
    the Hebrew page's right to left before the sentence went in, and the band read
    ".We can't reach targum" with Try again at the far end."""
    context, page = served_page(browser, built.read_text(encoding="utf-8"))
    try:
        page.goto(ORIGIN + "/reader/a-build/reader/index.html?k=test")
        page.wait_for_selector(".pair")
        page.evaluate("() => window.TargumFault.unreachable()")
        band = page.evaluate(
            """() => {
              const band = document.getElementById('fault-banner');
              const said = band.querySelector('.fault-said').getBoundingClientRect();
              const again = band.querySelector('.fault-act').getBoundingClientRect();
              return {
                page: getComputedStyle(document.querySelector('#reader .src')).direction,
                band: getComputedStyle(band).direction,
                sentenceFirst: said.left < again.left,
              };
            }"""
        )
    finally:
        context.close()

    assert band["page"] == "rtl", "the text is right to left, which is what made this happen"
    assert band["band"] == "ltr" and band["sentenceFirst"]


def test_an_interrupted_play_is_not_a_recording_that_would_not_play(scene) -> None:
    """A pause, or a film loaded again after an error, cuts the play promise off with an
    AbortError while what follows plays on. Read as a failure, "We couldn't play this
    recording" stood under a film that was playing."""
    scene.evaluate(
        """() => {
          HTMLMediaElement.prototype.play = function () {
            return Promise.reject(new DOMException('interrupted', 'AbortError'));
          };
        }"""
    )
    scene.click(".player-play")
    scene.wait_for_timeout(400)
    seen = scene.evaluate(
        """() => ({
          refused: document.getElementById('player').classList.contains('refused'),
          said: document.querySelector('.player-said').textContent,
        })"""
    )
    assert not seen["refused"], seen
    assert "couldn't" not in seen["said"], seen


def test_a_refused_play_is_still_said(scene) -> None:
    """The other half: a play the browser refused for want of a source is still said."""
    scene.evaluate(
        """() => {
          HTMLMediaElement.prototype.play = function () {
            return Promise.reject(new DOMException('no source', 'NotSupportedError'));
          };
        }"""
    )
    scene.click(".player-play")
    scene.wait_for_selector("#player.refused")
    assert scene.inner_text(".player-said") == "We couldn't play this recording."


def test_on_a_phone_the_clock_leaves_the_play_button_alone(browser, tmp_path, monkeypatch) -> None:
    """At 390px "0:09 / 10:58" was twice the room the strip had beside its play button,
    and ran under it. A phone says where it is; the track says of how long."""
    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(tmp_path / "dialogues"))
    reader = dialogue(tmp_path / "dialogues", tmp_path / "reader")
    context = opened(browser, viewport=PHONE)
    page = context.new_page()
    try:
        page.goto(address(reader))
        strip_up(page)
        page.click(".player-play")
        page.wait_for_function("() => !!document.querySelector('.player-clock .clock-now')")
        seen = page.evaluate(
            """() => {
              const clock = document.querySelector('.player-clock');
              const play = document.querySelector('.player-play').getBoundingClientRect();
              const shown = [...clock.children].filter(
                (piece) => piece.getBoundingClientRect().width
              );
              return {
                text: clock.textContent,
                shown: shown.map((piece) => piece.className),
                right: Math.max(...shown.map((piece) => piece.getBoundingClientRect().right)),
                play: play.left,
              };
            }"""
        )
    finally:
        context.close()

    assert " / " in seen["text"], "the whole clock is still there for a wider strip"
    assert seen["shown"] == ["clock-now"]
    assert seen["right"] <= seen["play"], seen


def test_a_chapter_that_cannot_be_started_says_why_on_a_line(browser, tmp_path: Path) -> None:
    """The book's waiting note put the server's sentence on its button, so the reason
    became the label of a press that only asked again. The reason is a line now, and the
    press says Try again."""
    html = _render_book(tmp_path, translated=1)[2]
    refusal = "You've used this month's credits."

    def chapter(route) -> None:
        route.fulfill(
            status=200, content_type="application/json", body=json.dumps({"blocked": refusal})
        )

    context, page = served_page(browser, html, chapter=chapter)
    try:
        page.goto(ORIGIN + "/reader/book-he/reader/sec-0002.html?k=test")
        page.wait_for_selector("#translate-chapter:not([hidden])")
        assert page.inner_text("#waiting-note p") == "We haven't translated this chapter yet."
        page.click("#translate-chapter")
        page.wait_for_function("() => document.getElementById('waiting-said').textContent !== ''")
        seen = page.evaluate(
            """() => ({
              said: document.getElementById('waiting-said').textContent,
              marked: document.getElementById('waiting-said').classList.contains('fault-marked'),
              press: document.getElementById('translate-chapter').textContent,
              pressable: !document.getElementById('translate-chapter').disabled,
            })"""
        )
    finally:
        context.close()

    assert seen == {"said": refusal, "marked": True, "press": "Try again", "pressable": True}
