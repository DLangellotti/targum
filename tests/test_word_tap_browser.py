"""A word tapped under a docked picture, on a phone.

On a narrow window a docked picture suspends paging (`pagingSuspended`): a page cut to
what is left under a picture leaves most of a pair of empty paper, so the reader scrolls
while the picture is up. A word's card is an occupant of the same band, the band holds
one thing at a time, and so the card put the picture away — which un-suspended paging,
which laid the chapter out in pages and showed the last page anybody had turned to. A
reader who had been scrolling has turned to none, so every tap on a word sent them to
page one: the top of the transcript, with the word they had asked about nowhere on the
screen (David, on his phone, 2026-09-20).

Two things were wrong, and the second would have been found next. A card is a visit and
must not change the mode at all ("A word's card covers the page on a phone; it does not
move it", design.md §12). And when the mode really does change — the reader closes the
picture, or opens it — the line they were on is the place, not a page number kept from
another sitting.

Neither browser fixture could see it: the video one has no words to tap, and the chapter
one has no picture. This is both.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

# The fixtures live in the browser module rather than a conftest, so they are
# imported by name to register them here.
from test_reader_browser import (  # noqa: E402, F401
    address,
    browser,
    coin,
    settled,
)

PHONE = {"width": 390, "height": 844}


def talk(folder: Path, lines: int = 60) -> Path:
    """A video import whose lines have words to tap: what a real one is."""
    from targum.audio import manifest as manifest_module
    from targum.models import (
        Annotation,
        Document,
        Segment,
        SegmentedDocument,
        Token,
        Translation,
    )
    from targum.render import render

    (folder / "audio" / "parts").mkdir(parents=True)
    with wave.open(str(folder / "audio" / "parts" / "part-001.wav"), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"\x00" * 16000)
    (folder / "video" / "parts").mkdir(parents=True)
    (folder / "video" / "parts" / "part-001.webm").write_bytes(
        (Path(__file__).parent / "fixtures" / "tiny.webm").read_bytes()
    )
    segments, tokens, minted = [], {}, 0
    for n in range(1, lines + 1):
        words = [coin(minted + i) for i in range(8)]
        minted += len(words)
        segment = Segment(
            id=f"{n:04d}.000-aaaaaa",
            block_id=f"b{n:04d}",
            block_index=n,
            index=0,
            text=" ".join(words),
        )
        segments.append(segment)
        offset, marks = 0, []
        for word in words:
            marks.append(
                Token(start=offset, end=offset + len(word), surface=word, lemma=word, band=2)
            )
            offset += len(word) + 1
        tokens[segment.id] = marks
    manifest_module.write(
        folder,
        manifest_module.AudioManifest(
            source="source.mp4",
            sha256="x",
            duration=200.0,
            language="he",
            parts=[
                manifest_module.ManifestPart(
                    number=1,
                    start=0.0,
                    end=200.0,
                    audio="audio/parts/part-001.wav",
                    video="video/parts/part-001.webm",
                    spans={s.id: [n * 3.0, n * 3.0 + 2.5] for n, s in enumerate(segments)},
                )
            ],
        ),
    )
    return render(
        Document(source="source.mp4", title="A talk", language="he", blocks=[], content_hash="h"),
        SegmentedDocument(document_hash="h", language="he", segmenter="fake/1", segments=segments),
        [
            Translation(
                name="English",
                document_hash="h",
                source_language="he",
                target_language="en",
                provider="null",
                segments={s.id: "A line of the talk, in English." for s in segments},
            )
        ],
        folder / "reader",
        annotation=Annotation(
            document_hash="h",
            language="he",
            annotator="test/1",
            method="frequency",
            method_note="a test",
            tokens=tokens,
        ),
        folder=folder,
    )[0]


WHERE = """() => {
  const picture = document.getElementById('video');
  const card = document.getElementById('gloss-card');
  const bar = document.querySelector('.bar').getBoundingClientRect().bottom;
  // The first line whose Hebrew starts under the bar: the line a reader is on.
  const pairs = [...document.querySelectorAll('.pair')].filter((p) => !p.hidden);
  const on = pairs.find((p) => p.getBoundingClientRect().bottom > bar + 4);
  return {
    paged: document.body.classList.contains('paged'),
    scrollY: Math.round(window.scrollY),
    picture: !picture.hidden,
    card: !!card && !card.hidden,
    line: on ? on.getAttribute('data-id') : '',
    lines: pairs.map((p) => p.getAttribute('data-id')),
    all: document.querySelectorAll('.pair').length,
  };
}"""

A_WORD_ON_SCREEN = """() => {
  const foot = parseFloat(getComputedStyle(document.body).getPropertyValue('--foot')) || 0;
  const word = [...document.querySelectorAll('span.w')].find((w) => {
    const r = w.getBoundingClientRect();
    return r.width > 0 && r.top > 120 && r.bottom < window.innerHeight - foot - 40;
  });
  const r = word.getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
}"""


def on_a_phone(browser, built: Path):  # noqa: F811
    """Default settings — pages on, which is what a new reader has — and a touch screen."""
    context = browser.new_context(
        viewport=PHONE, is_mobile=True, has_touch=True, reduced_motion="reduce"
    )
    page = context.new_page()
    page.goto(address(built))
    page.wait_for_selector(".pair")
    page.wait_for_selector("#video:not([hidden])")
    settled(page)
    return context, page


def test_tapping_a_word_under_a_docked_picture_leaves_the_page_where_it_was(
    browser,  # noqa: F811
    tmp_path,
) -> None:
    context, page = on_a_phone(browser, talk(tmp_path))
    try:
        page.evaluate("() => window.scrollTo(0, 2500)")
        page.wait_for_timeout(300)
        before = page.evaluate(WHERE)
        assert not before["paged"] and before["picture"], f"scrolling under a picture: {before}"
        assert before["scrollY"] > 2000, before

        at = page.evaluate(A_WORD_ON_SCREEN)
        page.touchscreen.tap(at["x"], at["y"])
        page.wait_for_timeout(500)
        tapped = page.evaluate(WHERE)
        assert tapped["card"], f"the word's card is up: {tapped}"
        assert not tapped["paged"], f"a card is a visit, and does not change the mode: {tapped}"
        assert abs(tapped["scrollY"] - before["scrollY"]) < 4, (
            f"the screen does not move under a tap: {before} then {tapped}"
        )

        # Put the card away, and the band gives back what it took — still in place.
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        after = page.evaluate(WHERE)
        assert after["picture"] and not after["card"], after
        assert not after["paged"] and abs(after["scrollY"] - before["scrollY"]) < 4, after
    finally:
        context.close()


def test_closing_the_picture_turns_to_the_page_the_reader_was_on(
    browser,  # noqa: F811
    tmp_path,
) -> None:
    """Pages come back when the picture goes, as they always did — on the line the
    reader was reading, and not on the last page somebody turned to in another sitting,
    which for a reader who has only ever scrolled is page one."""
    context, page = on_a_phone(browser, talk(tmp_path))
    try:
        page.evaluate("() => window.scrollTo(0, 2500)")
        page.wait_for_timeout(300)
        before = page.evaluate(WHERE)
        page.evaluate("() => document.querySelector('#video .video-close').click()")
        page.wait_for_function("() => document.body.classList.contains('paged')")
        page.wait_for_timeout(300)
        after = page.evaluate(WHERE)
    finally:
        context.close()
    assert len(after["lines"]) < after["all"], f"the chapter is in pages again: {after}"
    assert before["line"] in after["lines"], (
        f"the page shown holds the line they were on, {before['line']}: {after['lines']}"
    )


def test_opening_the_picture_keeps_the_page_that_was_open(
    browser,  # noqa: F811
    tmp_path,
) -> None:
    """The other way. A reader turning pages opens the picture, the pages are put away
    under it, and the scroll they are handed starts where their page did — not at the
    top of a transcript they were a third of the way through."""
    context, page = on_a_phone(browser, talk(tmp_path))
    try:
        page.evaluate("() => document.querySelector('#video .video-close').click()")
        page.wait_for_function("() => document.body.classList.contains('paged')")
        for _ in range(4):
            page.locator("#turn .forward").tap()
            page.wait_for_timeout(120)
        before = page.evaluate(WHERE)
        assert before["lines"] and before["lines"][0] != "0001.000-aaaaaa", before
        page.evaluate("() => document.querySelector('.player-video').click()")
        page.wait_for_function("() => !document.body.classList.contains('paged')")
        page.wait_for_timeout(400)
        after = page.evaluate(WHERE)
    finally:
        context.close()
    assert after["picture"] and len(after["lines"]) == after["all"], after
    assert after["line"] in before["lines"], (
        f"the line under the bar is one of the page that was open: {before['lines']}, {after}"
    )
