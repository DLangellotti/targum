"""The reader in a real browser, on the one question a stub cannot answer: when the
layout changes under a reader, are they still looking at the same sentence?

`tests/js/dom.js` says why this file exists. That stub lays nothing out — its
`getBoundingClientRect` hands back whatever a test put there — so it can tell you which
word the arrows choose and not whether the page moved. Every mode sets the same chapter
at a different height, and until this was fixed the scroll offset survived the change
while the sentence under it did not: on a long chapter, switching to source threw a
reader eighty verses down the page.

**Chrome's own scroll anchoring hides most of it, so these tests turn it off.** Left on,
the browser quietly compensates for content growing above the viewport and the reader
looks nearly fixed — until the redraw replaces the anchor node, or until the reader is
on Safari, which has no scroll anchoring at all. A test that leaves it on is a test that
passes on the one browser where the bug is mildest. What is asserted here is the page's
own work.

Skips itself unless Playwright and its Chromium are installed, the way the node tests
skip without node:

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

from pathlib import Path

import pytest

from targum.models import (
    Annotation,
    Block,
    BlockKind,
    Document,
    Segment,
    SegmentedDocument,
    Token,
    Translation,
    Vocalization,
)
from targum.render import render

playwright_api = pytest.importorskip(
    "playwright.sync_api", reason="Playwright is not installed: uv sync --extra browser"
)

#: Wide enough that the word list takes a column of the page rather than covering it —
#: below 60rem it is an overlay and moves nothing, which would test nothing.
WINDOW = {"width": 1280, "height": 800}

#: How far off the anchored sentence may land. Sub-pixel layout and the rounding in
#: `keep` put it within a pixel; anything larger is the page having moved under someone.
SLACK = 2

#: Long enough that the middle of the chapter is still several screenfuls from the end
#: in source mode, which is the shortest the same text ever gets. A chapter that fits on
#: a screen once the translation is hidden cannot hold a place near its end, and the
#: browser clamping at the bottom would read here as the page having lost one.
VERSES = 120

#: The anchored sentence: far enough in that losing it is unmissable, far enough from
#: the end that every mode can put it back.
ANCHOR = 30

ALEPHBET = "אבגדהוזחטיכלמנסעפצקרשת"
#: A vowel under a letter. The pointed cell is a second cell rather than the same one
#: restyled, so the toggle is a change of layout and not only of paint.
QAMATS = "\u05b8"


def coin(n: int) -> str:
    """A distinct Hebrew word for every word in the chapter.

    The first fixture here repeated one sentence sixty times, and every test that walked
    the arrows failed in the same puzzling way: the queue holds one entry per dictionary
    word, so a chapter of one repeated sentence has its whole queue in verse one, and
    pressing an arrow in the middle of the page threw the reader back to the top. That
    was the fixture, not the reader — but a fixture that cannot be walked cannot test
    walking, and a real chapter has a vocabulary.
    """
    return "".join(ALEPHBET[(n // 22**power) % 22] for power in range(5))


def chapter(out: Path) -> Path:
    """A built reader with everything the bar can change: words, vowels, translation."""
    segments, pointed, tokens, minted = [], {}, {}, 0
    for n in range(VERSES):
        # Alternating lengths, because a chapter of identical pairs would move by the
        # same amount everywhere and hide an anchor that is off by a whole sentence.
        words = [coin(minted + i) for i in range(14 if n % 3 else 42)]
        minted += len(words)
        text = " ".join(words)
        segment = Segment(
            id=f"{n:04d}.000-aaaaaa", block_id=f"b{n:04d}", block_index=n, index=n, text=text
        )
        segments.append(segment)
        pointed[segment.id] = " ".join(QAMATS.join(word) + QAMATS for word in words)
        # One token per word, so the arrows have a queue to walk and the list a count.
        offset, marks = 0, []
        for word in words:
            marks.append(
                Token(
                    start=offset,
                    end=offset + len(word),
                    surface=word,
                    lemma=word,
                    band=1 + (offset % 5),
                )
            )
            offset += len(word) + 1
        tokens[segment.id] = marks

    document = Document(
        source="memory",
        title="A chapter",
        language="he",
        blocks=[Block(id="b0000", kind=BlockKind.paragraph, text=segments[0].text)],
        content_hash="h",
    )
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="test/1", segments=segments
    )
    translation = Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
        # Long enough that the translation is a line of its own in every mode, which is
        # what makes interlinear taller than source rather than the same height.
        segments={
            s.id: f"In the land of Israel the Jewish people arose ({s.id})." for s in segments
        },
    )
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator="test/1",
        method="frequency",
        method_note="a test",
        tokens=tokens,
    )
    vocalization = Vocalization(
        document_hash="h", language="he", vocalizer="test/1", segments=pointed, machine=[]
    )
    pages = render(
        document,
        segmented,
        [translation],
        out,
        annotation=annotation,
        vocalization=vocalization,
    )
    return pages[0]


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return chapter(tmp_path_factory.mktemp("reader") / "reader")


@pytest.fixture(scope="module")
def browser():
    """One Chromium for the file. Launching one a test is most of the run."""
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


@pytest.fixture
def page(browser, built: Path):
    """A reader open in Chromium, with one sentence put at the top of the window.

    `file://` rather than a server on purpose: a reader fetches nothing, and
    `test_render.py` pins that. If this ever needs a server, that is the news.
    """
    # Reduced motion so every scroll the page makes is instant and a measurement taken
    # straight after a keypress is the finished answer rather than a frame of animation.
    # It hides nothing: `keep` never animates in either setting — §8 is why — and what
    # is asserted here is where the page ended up.
    context = browser.new_context(viewport=WINDOW, reduced_motion="reduce")
    open_page = context.new_page()
    open_page.goto(built.as_uri())
    open_page.wait_for_selector(".pair")
    # See the note at the top: the browser's own anchoring would answer for the page.
    open_page.add_style_tag(content="* { overflow-anchor: none !important; }")
    open_page.evaluate(SCROLL_TO_ANCHOR, ANCHOR)
    yield open_page
    context.close()


#: Put one sentence at the top of the reading area. A fraction of the document height
#: would land somewhere different in every mode, which is the thing under test.
SCROLL_TO_ANCHOR = """
(n) => {
  const bar = document.querySelector('.bar');
  const top = (bar ? bar.getBoundingClientRect().height : 0) + 16;
  const pair = document.querySelectorAll('.pair')[n];
  window.scrollTo(0, window.scrollY + pair.getBoundingClientRect().top - top);
}
"""

#: The sentence at the top of the reading area, and how far down the window it sits.
#: The bar is sticky, so the top of the window is not the top of the text — the same
#: sum `ceiling()` does in reader.js, asked here independently of it.
WHERE = """
() => {
  const bar = document.querySelector('.bar');
  const top = (bar ? bar.getBoundingClientRect().height : 0) + 16;
  const pairs = [...document.querySelectorAll('.pair')];
  for (let n = 0; n < pairs.length; n++) {
    const box = pairs[n].getBoundingClientRect();
    if (box.bottom > top) return { n, id: pairs[n].dataset.id, top: Math.round(box.top) };
  }
  return null;
}
"""


@pytest.mark.parametrize(
    ("what", "selector"),
    [
        ("interlinear", '[data-mode="inter"]'),
        ("source only", '[data-mode="source"]'),
        ("larger type", '[data-type="larger"]'),
        ("smaller type", '[data-type="smaller"]'),
        ("line spacing", '[data-type="looser"]'),
        # The one case that passed before the fix as well: a vowel is a combining mark
        # and adds no width, so the pointed cell wraps almost exactly as the bare one
        # does and there is little to lose. It is here because they are two cells rather
        # than one restyled — the day they differ by a line, this says so.
        ("vowel points", "[data-nikkud-toggle]"),
        ("the word list", '.list-close[data-toggle="list"]'),
    ],
)
def test_a_change_of_layout_keeps_the_sentence(page, what: str, selector: str) -> None:
    before = page.evaluate(WHERE)
    assert before is not None and before["n"] == ANCHOR, "not where the fixture left it"

    page.eval_on_selector(selector, "button => button.click()")

    after = page.evaluate(WHERE)
    assert after["id"] == before["id"], (
        f"{what} moved the reader from sentence {before['n']} to {after['n']}"
    )
    assert abs(after["top"] - before["top"]) <= SLACK, f"{what} shifted the sentence on screen"


def test_the_whole_round_trip_comes_back_to_the_same_sentence(page) -> None:
    """Every mode in turn. Each is measured against the one before, so an anchor that
    is a little wrong each time still fails rather than cancelling itself out."""
    start = page.evaluate(WHERE)
    for mode in ("inter", "source", "parallel", "source", "inter", "parallel"):
        before = page.evaluate(WHERE)
        page.eval_on_selector(f'[data-mode="{mode}"]', "button => button.click()")
        after = page.evaluate(WHERE)
        assert after["id"] == before["id"], f"{mode} lost the sentence"
    assert page.evaluate(WHERE)["id"] == start["id"]


#: The word the arrows are standing on: its text, where it is, and whether it still
#: carries the ring, the tab stop and the focus that say the queue is live.
RING = """
() => {
  const w = document.querySelector('.w.queued');
  if (!w) return null;
  return {
    text: w.textContent,
    top: Math.round(w.getBoundingClientRect().top),
    focused: document.activeElement === w,
    tabbable: w.getAttribute('tabindex') === '-1',
  };
}
"""


def test_switching_mode_mid_walk_keeps_the_word_you_are_on(page) -> None:
    """Entering or leaving interlinear rebuilds every span on the page, which used to
    detach the word the arrows were standing on: the ring went out, focus fell back to
    the body, and the reader was walking nothing."""
    for _ in range(6):
        page.keyboard.press("ArrowLeft")  # forward, on a page that reads right to left
    was = page.evaluate(RING)
    assert was is not None, "the arrows did not enter the queue"

    for mode in ("inter", "source", "parallel"):
        page.eval_on_selector(f'[data-mode="{mode}"]', "button => button.click()")
        now = page.evaluate(RING)
        assert now is not None, f"{mode} dropped the word the arrows were on"
        assert now["text"] == was["text"], f"{mode} moved the reader to a different word"
        assert now["focused"] and now["tabbable"], f"{mode} took the keyboard off the word"
        assert abs(now["top"] - was["top"]) <= SLACK, f"{mode} moved the word on screen"

    # And the queue is still walkable from where it was left.
    page.keyboard.press("ArrowLeft")
    assert page.evaluate(RING)["text"] != was["text"]
