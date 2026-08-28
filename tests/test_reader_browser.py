"""The reader in a real browser, on the one question a stub cannot answer: is the reader
still looking at what they were looking at — when the layout changes under them, and when
they close the tab and come back to it?

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

import json
from pathlib import Path

import pytest

from targum.models import (
    Annotation,
    Block,
    BlockKind,
    Document,
    Glossary,
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


def bilingual(out: Path) -> Path:
    """The same chapter with two translations and a glossary for each.

    Short, because nothing here is about layout: what it is for is the one question a
    single-language reader cannot ask — when a text can be read in two languages, does
    the page ever hand a reader a meaning written in the other one?
    """
    segments, tokens = [], {}
    for n in range(VERSES // 20):
        words = [coin(n * 3 + i) for i in range(3)]
        segment = Segment(
            id=f"{n:04d}.000-aaaaaa",
            block_id=f"b{n:04d}",
            block_index=n,
            index=n,
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

    def translation(name: str, code: str, saying: str) -> Translation:
        return Translation(
            name=name,
            document_hash="h",
            source_language="he",
            target_language=code,
            provider="null",
            segments={s.id: f"{saying} ({s.index})" for s in segments},
        )

    lemmas = [token.lemma for marks in tokens.values() for token in marks]
    pages = render(
        document,
        segmented,
        [
            translation("English", "en", "In the land of Israel"),
            translation("Russian", "ru", "На земле Израиля"),
        ],
        out,
        annotation=Annotation(
            document_hash="h",
            language="he",
            annotator="test/1",
            method="frequency",
            method_note="a test",
            tokens=tokens,
        ),
        glossaries={
            "en": Glossary(
                source_language="he",
                target_language="en",
                provider="test",
                entries={lemma: f"the English of {lemma}" for lemma in lemmas},
            ),
            # Deliberately thinner than the English one: the last word has a meaning in
            # one language and none in the other, which is the case where a page that
            # reaches for "the" meaning of a word gives itself away.
            "ru": Glossary(
                source_language="he",
                target_language="ru",
                provider="test",
                entries={lemma: f"по-русски {lemma}" for lemma in lemmas[:-1]},
            ),
        },
    )
    return pages[0]


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return chapter(tmp_path_factory.mktemp("reader") / "reader")


@pytest.fixture(scope="module")
def two_languages(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return bilingual(tmp_path_factory.mktemp("bilingual") / "reader")


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


#: These tests are about the scrolling reader, and pages are the default now — every
#: browser with a preference from before there were pages is handed them once. The
#: scrolling reader still exists behind `b`, and what is asserted here is its work, so
#: every context opens with the preference already made. The pages have tests of their
#: own at the foot of the file, in contexts that make no such choice.
SCROLLING = """
(() => {
  try {
    localStorage.setItem("targum:prefs", JSON.stringify({ paged: false, defaults: 3 }));
  } catch (e) {}
})();
"""


def opened(browser, viewport=None, scrolling: bool = True):
    """A context the way every test here wants one: reduced motion, and — unless a test
    is about the pages — the scrolling reader."""
    context = browser.new_context(viewport=viewport or WINDOW, reduced_motion="reduce")
    if scrolling:
        context.add_init_script(SCROLLING)
    return context


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
    context = opened(browser)
    open_page = context.new_page()
    open_page.goto(built.as_uri())
    open_page.wait_for_selector(".pair")
    # See the note at the top: the browser's own anchoring would answer for the page.
    open_page.add_style_tag(content="* { overflow-anchor: none !important; }")
    open_page.evaluate(SCROLL_TO_ANCHOR, ANCHOR)
    # The marks follow a scroll by a frame — `catchUp` in reader.js draws the spans for
    # whatever the scroll brought into view. A test that asks which words are on the
    # screen before that frame has run is asking a question the page has not answered yet.
    open_page.wait_for_function(MARKED, arg=ANCHOR)
    yield open_page
    context.close()


def reopen(page, built: Path):
    """Leave the reader and come back to it, in the same browser.

    The same page rather than a new context on purpose: what the reader wrote on its way
    out is in this browser's store, and a fresh context is a fresh browser, which is a
    reader who has never opened the text at all.
    """
    page.goto(built.as_uri())
    page.wait_for_selector(".pair")
    page.add_style_tag(content="* { overflow-anchor: none !important; }")
    return page


#: Put one sentence in the middle of the reading area, which is where the reader holds a
#: place from. A fraction of the document height would land somewhere different in every
#: mode, which is the thing under test.
SCROLL_TO_ANCHOR = """
(n) => {
  const bar = document.querySelector('.bar');
  const top = (bar ? bar.getBoundingClientRect().height : 0) + 16;
  const eye = top + (window.innerHeight - top) / 2;
  const box = document.querySelectorAll('.pair')[n].getBoundingClientRect();
  window.scrollTo(0, window.scrollY + box.top + box.height / 2 - eye);
}
"""

#: Whether a sentence has had its words drawn on it yet.
MARKED = """
(n) => !!document.querySelectorAll('.pair')[n].querySelector('.w')
"""

#: The sentence in the middle of the reading area, and how far down the window it sits.
#: The bar is sticky, so the top of the window is not the top of the text — the same sum
#: `ceiling()` and `middle()` do in reader.js, asked here independently of them.
WHERE = """
() => {
  const bar = document.querySelector('.bar');
  const top = (bar ? bar.getBoundingClientRect().height : 0) + 16;
  const eye = top + (window.innerHeight - top) / 2;
  const pairs = [...document.querySelectorAll('.pair')];
  for (let n = 0; n < pairs.length; n++) {
    const box = pairs[n].getBoundingClientRect();
    if (box.bottom >= eye) {
      return { n, id: pairs[n].dataset.id, top: Math.round(box.top) };
    }
  }
  return null;
}
"""

#: One named sentence, and where on the screen it sits.
AT = """
(id) => {
  const pair = document.querySelector(`.pair[data-id="${id}"]`);
  return pair ? { top: Math.round(pair.getBoundingClientRect().top) } : null;
}
"""

#: Tap the first word on the screen above the middle of it, and say where it sits. Above
#: the middle so that the word and the sentence in the middle are different answers — a
#: word below it would be carried by holding either, and the test would pass on a page
#: that had never heard of the word. On the screen because a word scrolled past is a place
#: the reader has left and the page is right to drop it: a click sent through the DOM,
#: unlike a pointer, will land happily on a word nobody can see.
TAP_ABOVE = """
() => {
  const bar = document.querySelector('.bar');
  const top = (bar ? bar.getBoundingClientRect().height : 0) + 16;
  const eye = top + (window.innerHeight - top) / 2;
  const word = [...document.querySelectorAll('.w')].find((w) => {
    const box = w.getBoundingClientRect();
    return box.top >= top && box.bottom <= eye;
  });
  if (!word) return null;
  word.click();
  return {
    id: word.closest('.pair').dataset.id,
    text: word.textContent,
    top: Math.round(word.getBoundingClientRect().top),
  };
}
"""

#: The same word after the page has been rebuilt around it, found by what it says: the
#: span the tap landed on is gone, and the text is what the reader still sees.
FIND = """
([id, text]) => {
  const pair = document.querySelector(`.pair[data-id="${id}"]`);
  const word = [...pair.querySelectorAll('.w')].find((w) => w.textContent === text);
  if (!word) return null;
  const box = word.getBoundingClientRect();
  const bar = document.querySelector('.bar');
  const top = (bar ? bar.getBoundingClientRect().height : 0) + 16;
  return { top: Math.round(box.top), onScreen: box.top >= top && box.bottom <= innerHeight };
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
def test_a_change_of_layout_leaves_the_sentence_where_it_was(
    page, what: str, selector: str
) -> None:
    """Every control on the bar, and the same answer from each: the line the reader is on
    stays on the line of the window it was on. Not the middle of the window — the eye is
    already somewhere — and four presses of A+ used to walk a sentence off the top of it.
    """
    before = page.evaluate(WHERE)
    assert before is not None and before["n"] == ANCHOR, "not where the fixture left it"

    page.eval_on_selector(selector, "button => button.click()")

    # That sentence, asked for by name. Not "whatever is in the middle now": a sentence
    # that has just lost a line is shorter, so the middle of the window can fall past its
    # end onto the next one — with the sentence itself exactly where it was, which is the
    # thing under test.
    after = page.evaluate(AT, before["id"])
    assert after is not None, f"{what} lost sentence {before['n']} altogether"
    assert abs(after["top"] - before["top"]) <= SLACK, f"{what} shifted the sentence on screen"


def test_the_whole_round_trip_comes_back_to_the_same_sentence(page) -> None:
    """Every mode in turn. Each is measured against the one before, so an anchor that
    is a little wrong each time still fails rather than cancelling itself out — and the
    whole run against where it started, which is what a reader pressing the same two
    buttons back and forth would see."""
    start = page.evaluate(WHERE)
    for mode in ("inter", "source", "parallel", "source", "inter", "parallel"):
        before = page.evaluate(AT, start["id"])
        page.eval_on_selector(f'[data-mode="{mode}"]', "button => button.click()")
        after = page.evaluate(AT, start["id"])
        assert abs(after["top"] - before["top"]) <= SLACK, f"{mode} lost the sentence"
    assert abs(page.evaluate(AT, start["id"])["top"] - start["top"]) <= SLACK


def test_a_word_you_tapped_is_the_place_a_change_of_view_keeps(page) -> None:
    """A word the pointer opened is a place, the same as a word the arrows are on.

    Tapped well above the middle of the window, so the two answers disagree: hold the
    sentence in the middle instead and this word moves by every line the pairs between
    them gained or lost, which in source mode is most of a screen.
    """
    was = page.evaluate(TAP_ABOVE)
    assert was is not None, "no word on the screen above the middle to tap"

    for mode in ("source", "inter", "parallel"):
        page.eval_on_selector(f'[data-mode="{mode}"]', "button => button.click()")
        now = page.evaluate(FIND, [was["id"], was["text"]])
        assert now is not None, f"{mode} lost the word that was tapped"
        assert abs(now["top"] - was["top"]) <= SLACK, f"{mode} moved the word on screen"


#: What is wearing the place mark: a word, a sentence, or nothing.
HERE = """
() => {
  const word = document.querySelector('.w.here');
  if (word) return { what: 'word', text: word.textContent, id: word.closest('.pair').dataset.id };
  const pair = document.querySelector('.pair.here');
  return pair ? { what: 'sentence', id: pair.dataset.id } : null;
}
"""


@pytest.mark.parametrize("mode", ["inter", "source"])
def test_the_sentence_it_kept_says_so(page, mode: str) -> None:
    """Being put back where you were is no use if you cannot see where that is — and the
    less the page moves, the more the mark is the only way to tell that it held on."""
    before = page.evaluate(WHERE)

    page.eval_on_selector(f'[data-mode="{mode}"]', "button => button.click()")

    mark = page.evaluate(HERE)
    assert mark == {"what": "sentence", "id": before["id"]}, f"{mode} marked {mark}"


def test_the_word_you_tapped_is_still_marked_after_a_change_of_mode(page) -> None:
    """The card a tap opened is put away by the change of layout. The place it stands for
    is not: the word carries the mark instead, through the redraw that interlinear does to
    every span on the page."""
    was = page.evaluate(TAP_ABOVE)

    for mode in ("source", "inter", "parallel"):
        page.eval_on_selector(f'[data-mode="{mode}"]', "button => button.click()")
        mark = page.evaluate(HERE)
        assert mark is not None, f"{mode} left nothing marked"
        assert mark["what"] == "word", f"{mode} marked the sentence, not the word in it"
        assert mark["text"] == was["text"], f"{mode} marked a different word"


def test_the_mark_goes_when_the_reader_does(page) -> None:
    """A band left on a sentence nobody is reading is furniture."""
    page.eval_on_selector('[data-mode="source"]', "button => button.click()")
    assert page.evaluate(HERE) is not None, "nothing was marked to begin with"

    page.evaluate("() => window.scrollBy(0, 200)")
    page.wait_for_timeout(100)
    assert page.evaluate(HERE) is None, "the mark stayed behind after a scroll"


def test_leaving_and_coming_back_marks_the_place_too(page, built: Path) -> None:
    """Opening a text you left half-read is the case the mark was asked for."""
    before = page.evaluate(WHERE)

    reopen(page, built)

    assert page.evaluate(HERE) == {"what": "sentence", "id": before["id"]}


def test_leaving_and_coming_back_lands_on_the_same_sentence(page, built: Path) -> None:
    """The same sentence on the same line of the window, across a closed tab."""
    before = page.evaluate(WHERE)

    after = reopen(page, built).evaluate(AT, before["id"])

    assert after is not None, "the sentence is not on the page the reader came back to"
    assert abs(after["top"] - before["top"]) <= SLACK, "it came back on a different line"


def test_leaving_and_coming_back_lands_on_the_word_you_tapped(page, built: Path) -> None:
    """And the word beats the sentence here too: a reader who tapped a word above the
    middle of the window and then closed the tab left off at that word, which is a
    different line of the window from the sentence the geometry would have picked."""
    middle = page.evaluate(WHERE)
    was = page.evaluate(TAP_ABOVE)
    assert was["id"] != middle["id"], "the tapped word is in the sentence the fixture centred"

    after = reopen(page, built).evaluate(FIND, [was["id"], was["text"]])

    assert after is not None, "the word is not on the page the reader came back to"
    assert abs(after["top"] - was["top"]) <= SLACK, "the word came back on a different line"


def test_a_reading_that_went_nowhere_keeps_no_place(browser, built: Path) -> None:
    """Nothing kept, nothing to put back — twice over. A browser that has never had the
    text open starts where the text does, and so does one that had it open and left it
    exactly where it opened: a reader who scrolled nothing has no place to be given
    back, and a page that scrolls itself for them is a page that has moved for no reason.
    """
    context = opened(browser)
    fresh = context.new_page()
    fresh.goto(built.as_uri())
    fresh.wait_for_selector(".pair")
    assert fresh.evaluate("() => window.scrollY") == 0, "a first opening did not start at the top"

    reopen(fresh, built)
    assert fresh.evaluate("() => window.scrollY") == 0, "coming back moved a reader who had not"
    context.close()


#: The gloss card against the word it was opened for: whether it is on the screen, and
#: whether any part of it is over the word. The card is what the reader reads the answer
#: from and the word is what they are deciding about — the two cannot occupy one line.
COVERING = """
([id, text]) => {
  const card = document.getElementById('gloss-card');
  if (!card || card.hidden) return { open: false };
  const pair = document.querySelector(`.pair[data-id="${id}"]`);
  const word = [...pair.querySelectorAll('.w')].find((w) => w.textContent === text);
  if (!word) return { open: true, word: false };
  const c = card.getBoundingClientRect();
  const w = word.getBoundingClientRect();
  const bar = document.querySelector('.bar');
  const top = (bar ? bar.getBoundingClientRect().height : 0) + 16;
  return {
    open: true,
    word: true,
    over: c.top < w.bottom && c.bottom > w.top && c.left < w.right && c.right > w.left,
    // How far the card sits from the word on the side it chose. `placeNear` leaves 8px.
    beside: Math.min(Math.abs(c.top - w.bottom - 8), Math.abs(w.top - c.bottom - 8)),
    onScreen: w.top >= top && w.bottom <= window.innerHeight,
    cardOnScreen:
      c.height > 0 && c.top >= 0 && c.bottom <= window.innerHeight &&
      c.left >= 0 && c.right <= window.innerWidth,
  };
}
"""

#: A window a third narrower and shorter than the one the fixture reads in. Narrower so
#: every line rewraps and the sentence the reader was on is somewhere else down the page;
#: shorter so a line near the bottom of the old window is off the new one.
CRAMPED = {"width": 860, "height": 560}


def test_a_resize_hands_back_the_word_you_are_on(page) -> None:
    """The one change of layout the page cannot measure first: the browser reflows and
    then says so. The word has to survive it, and be somewhere the reader can see."""
    was = page.evaluate(TAP_ABOVE)
    assert was is not None, "no word on the screen above the middle to tap"

    page.set_viewport_size(CRAMPED)
    page.wait_for_timeout(200)

    now = page.evaluate(FIND, [was["id"], was["text"]])
    assert now is not None, "the resize lost the word"
    assert now["onScreen"], "the word came back somewhere the reader cannot see it"
    mark = page.evaluate(HERE)
    assert mark == {"what": "word", "text": was["text"], "id": was["id"]}, f"marked {mark}"


def test_a_resize_keeps_the_sentence_in_front_of_the_reader(page) -> None:
    """And with no word tapped, the sentence — which is the harder half: after the reflow
    the page has no way of working out which one it was."""
    before = page.evaluate(WHERE)

    page.set_viewport_size(CRAMPED)
    page.wait_for_timeout(200)

    after = page.evaluate(AT, before["id"])
    assert after is not None, "the sentence is not on the page any more"
    assert page.evaluate(HERE) == {"what": "sentence", "id": before["id"]}
    top = after["top"]
    assert 0 < top < CRAMPED["height"], f"the sentence came back off the window at {top}"


def test_the_card_never_ends_up_over_its_own_word(page) -> None:
    """A card is positioned in document coordinates against a word that a resize moves out
    from under it. Left alone it stays where the word used to be — which on a narrower
    window is half off the side of it — so it has to be placed again, and placed by the
    same rule as the first time: beside the word, and never over it. That word is the one
    thing the reader is looking at while they decide what to say about it."""
    was = page.evaluate(TAP_ABOVE)
    before = page.evaluate(COVERING, [was["id"], was["text"]])
    assert before["open"] and not before["over"], "the card started out over the word"

    for size in (CRAMPED, {"width": 1100, "height": 700}, WINDOW):
        page.set_viewport_size(size)
        page.wait_for_timeout(200)
        now = page.evaluate(COVERING, [was["id"], was["text"]])
        assert now["open"] and now["word"], f"the card or its word went missing at {size}"
        assert not now["over"], f"the card sat over its own word at {size}"
        assert now["beside"] <= SLACK, f"the card came away from its word at {size}"
        assert now["onScreen"], f"the word was not on the screen at {size}"
        assert now["cardOnScreen"], f"the card was not on the screen at {size}"


#: A word looked up: what the card says it means, and whether it is still offering to
#: find out. A reader who has already asked should meet the answer, not the button.
CARD = """
() => {
  const card = document.getElementById('gloss-card');
  if (!card || card.hidden) return null;
  const meaning = card.querySelector('.meaning');
  return {
    meaning: meaning ? meaning.textContent : "",
    asking: !!card.querySelector('.look-up'),
  };
}
"""

#: Tap a word with room under it for the card, and say which one it was.
TAP_ANY = """
() => {
  const bar = document.querySelector('.bar');
  const top = (bar ? bar.getBoundingClientRect().height : 0) + 16;
  const word = [...document.querySelectorAll('.w')].find((w) => {
    const box = w.getBoundingClientRect();
    return box.top >= top && box.bottom <= window.innerHeight - 240;
  });
  word.click();
  return word.textContent;
}
"""

#: The same word again, by what it says: the span the first tap landed on is long gone.
TAP_AGAIN = """
(text) => [...document.querySelectorAll('.w')].find((w) => w.textContent === text).click()
"""

#: What a meaning the reader paid for looks like coming back from the server.
MEANING = "a made-up meaning"


def test_a_word_looked_up_stays_looked_up(browser, built: Path) -> None:
    """Looking a word up costs a call to a model, and the answer used to live in the page
    and no further: a reload put the "look it up" button back on a word the reader had
    already asked about. It came back instantly, which was the server's cache doing the
    remembering — this reader should not have to ask twice to be told what it was told
    yesterday.

    Served rather than opened off the disk, because `served` and the pass key are what
    put the button on the card at all. The model is not called: the one request this
    would make is answered here.
    """
    html = built.read_text(encoding="utf-8")
    calls = []
    bought = []
    context = opened(browser)
    page = context.new_page()

    def answer(route, request):
        if "/gloss" in request.url:
            # The server, in miniature: a free ask is answered from what was bought,
            # and a card opening asks that first. Only a real lookup counts as a call.
            if request.post_data_json.get("free"):
                meaning = MEANING if bought else None
                body = {"meaning": meaning, "cached": bool(meaning)}
            else:
                calls.append(request.url)
                bought.append(request.url)
                body = {"meaning": MEANING}
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
        else:
            route.fulfill(status=200, content_type="text/html", body=html)

    page.route("http://reader.test/**", answer)
    page.goto("http://reader.test/reader/a-build/reader/index.html?k=test")
    page.wait_for_selector(".pair")

    word = page.evaluate(TAP_ANY)
    page.wait_for_timeout(300)
    assert page.evaluate(CARD)["asking"], "the card was not offering to look the word up"
    page.eval_on_selector(".look-up", "button => button.click()")
    page.wait_for_timeout(300)
    assert page.evaluate(CARD) == {"meaning": MEANING, "asking": False}

    page.reload()
    page.wait_for_selector(".pair")
    page.evaluate(TAP_AGAIN, word)

    assert page.evaluate(CARD) == {"meaning": MEANING, "asking": False}, (
        "the reader was asked to look up a word they had already looked up"
    )
    assert len(calls) == 1, f"the meaning was bought {len(calls)} times"
    context.close()


#: Every translation cell's language and direction, and what the first one says. The
#: template stamps these from the first translation, so a page that switches without
#: restamping them leaves Russian sentences claiming to be English.
CELLS = """
() => {
  const cells = [...document.querySelectorAll('.pair .tr')];
  const langs = new Set(cells.map((c) => c.getAttribute('lang')));
  const dirs = new Set(cells.map((c) => c.getAttribute('dir')));
  return { langs: [...langs], dirs: [...dirs], first: cells[0].textContent };
}
"""

#: Tap the first word on the page and say what the card gives as its meaning, and whether
#: it is still offering to go and find one.
TAP_FIRST = """
() => {
  const word = document.querySelector('.w');
  word.click();
  const card = document.getElementById('gloss-card');
  const meaning = card.querySelector('.meaning');
  return {
    text: word.textContent,
    meaning: meaning ? meaning.textContent : "",
    lang: meaning ? meaning.getAttribute('lang') : "",
    asking: !!card.querySelector('.look-up'),
  };
}
"""

SWITCH = """
(id) => {
  const picker = document.getElementById('translation');
  picker.value = id;
  picker.dispatchEvent(new Event('change'));
}
"""


def open_reader(browser, page_path: Path, viewport=None):
    context = opened(browser, viewport)
    page = context.new_page()
    page.goto(page_path.as_uri())
    page.wait_for_selector(".pair")
    return context, page


def test_switching_translation_switches_the_language(browser, two_languages: Path) -> None:
    """A reader can hold a translation into English and one into Russian. Everything that
    is about a pair of languages rather than about a word has to follow the picker — and
    the cells have to stop claiming to be written in the first translation's language."""
    context, page = open_reader(browser, two_languages)

    english = page.evaluate(CELLS)
    assert english["langs"] == ["en"] and english["dirs"] == ["ltr"]
    assert "In the land of Israel" in english["first"]

    page.evaluate(SWITCH, "t1")

    russian = page.evaluate(CELLS)
    assert russian["langs"] == ["ru"], "the cells still claimed the first language"
    assert "На земле Израиля" in russian["first"]
    context.close()


def test_a_word_never_means_what_it_means_in_the_other_language(
    browser, two_languages: Path
) -> None:
    """The whole of it, in one page: the same word, two translations, and never once the
    wrong answer. A meaning is written in one language, and a reader who asked for the
    other must be given theirs or given none."""
    context, page = open_reader(browser, two_languages)

    english = page.evaluate(TAP_FIRST)
    assert english["meaning"] == f"the English of {english['text']}"
    assert english["lang"] == "en"

    page.evaluate(SWITCH, "t1")
    russian = page.evaluate(TAP_FIRST)

    assert russian["text"] == english["text"], "not the same word"
    assert russian["meaning"] == f"по-русски {russian['text']}"
    assert russian["lang"] == "ru", "the meaning was not marked as Russian"
    context.close()


def test_a_word_with_no_meaning_in_this_language_offers_to_find_one(
    browser, two_languages: Path
) -> None:
    """And the case that gives a page away: a word the English glossary answers and the
    Russian one does not. Reaching for "the" meaning of a word hands over the English;
    the card has to say it has nothing and offer to go and ask."""
    context, page = open_reader(browser, two_languages)

    last = page.evaluate("() => [...document.querySelectorAll('.w')].pop().textContent")
    tap = TAP_AGAIN

    page.evaluate(tap, last)
    assert page.evaluate(CARD)["meaning"] == f"the English of {last}"

    page.evaluate(SWITCH, "t1")
    page.evaluate(tap, last)

    said = page.evaluate(CARD)
    assert said["meaning"] == "", f"the card gave {said['meaning']!r} to a Russian reader"
    assert said["asking"], "nothing offered to look it up either — the word just went blank"
    context.close()


#: The word the arrows are standing on: its text, where it is, and whether it still
#: carries the ring, the tab stop and the focus that say the queue is live.
RING = """
() => {
  const w = document.querySelector('.w.queued');
  if (!w) return null;
  return {
    text: w.textContent,
    id: w.closest('.pair').dataset.id,
    top: Math.round(w.getBoundingClientRect().top),
    focused: document.activeElement === w,
    tabbable: w.getAttribute('tabindex') === '0',
  };
}
"""


def test_switching_mode_mid_walk_keeps_the_word_you_are_on(page) -> None:
    """Entering or leaving interlinear rebuilds every span on the page, which used to
    detach the word the arrows were standing on: the ring went out, focus fell back to
    the body, and the reader was walking nothing. It is also the word the place is held
    by, so the walk carries on from the line it was already on."""
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


# -- pages, not a scroll ---------------------------------------------------------


#: What the page control says, and which pairs are on show.
PAGE = """
() => {
  const pairs = [...document.querySelectorAll('.pair')];
  const shown = pairs.map((p, n) => (p.hidden ? null : n)).filter((n) => n !== null);
  const of = document.getElementById('page-of');
  return {
    paged: document.body.classList.contains('paged'),
    of: of ? of.textContent : '',
    first: shown.length ? shown[0] : null,
    last: shown.length ? shown[shown.length - 1] : null,
    count: shown.length,
    total: pairs.length,
    fits: shown.every((n) => pairs[n].getBoundingClientRect().bottom <= window.innerHeight),
  };
}
"""


@pytest.fixture
def paged(browser, built: Path):
    """A reader open with no preference made: pages, as a new reader gets them."""
    context = opened(browser, scrolling=False)
    open_page = context.new_page()
    open_page.goto(built.as_uri())
    open_page.wait_for_selector(".pair")
    open_page.wait_for_function("() => document.body.classList.contains('paged')")
    yield open_page
    context.close()


def test_a_chapter_opens_as_pages_that_fit_the_window(paged) -> None:
    """ "I would prefer pages over an endless scroll" — twice, in five pages of notes. A
    page is the pairs that fit under the bar, and the control says which page this is."""
    seen = paged.evaluate(PAGE)
    assert seen["paged"] is True
    assert seen["first"] == 0
    assert 0 < seen["count"] < seen["total"], "a long chapter is more than one page"
    assert seen["fits"], "every pair on the page is inside the window"
    assert seen["of"].startswith("1 of ")
    assert int(seen["of"].split(" of ")[1]) > 1


def test_space_turns_the_page_and_shift_space_turns_it_back(paged) -> None:
    first = paged.evaluate(PAGE)
    paged.keyboard.press("Space")
    second = paged.evaluate(PAGE)
    assert second["first"] == first["last"] + 1, "the next page starts where this one ended"
    assert second["of"].startswith("2 of ")
    paged.keyboard.press("Shift+Space")
    assert paged.evaluate(PAGE)["first"] == 0


def test_the_page_control_turns_it_too(paged) -> None:
    paged.click('[data-turn="1"]')
    assert paged.evaluate(PAGE)["of"].startswith("2 of ")
    paged.click('[data-turn="-1"]')
    assert paged.evaluate(PAGE)["of"].startswith("1 of ")


def test_a_change_of_type_keeps_you_on_the_same_page(paged) -> None:
    """Held by the pair the reader is on, not by a page number: larger type means fewer
    pairs to a page, and the page you were on is the one that still starts here."""
    paged.keyboard.press("Space")
    paged.keyboard.press("Space")
    before = paged.evaluate(PAGE)
    paged.click('[data-type="larger"]')
    paged.wait_for_timeout(100)
    after = paged.evaluate(PAGE)
    assert after["first"] <= before["first"] <= after["last"], (
        "the pair you were on is still on show"
    )
    assert after["fits"]


def test_the_arrows_turn_the_page_to_the_word_they_reach(paged) -> None:
    """The walk goes through every word in the chapter; a word on the next page is
    reached by turning to it, not by walking off the edge of this one."""
    on = paged.evaluate(PAGE)
    for _ in range(80):
        paged.keyboard.press("ArrowRight")
        now = paged.evaluate(PAGE)
        if now["first"] != on["first"]:
            break
    else:
        raise AssertionError("eighty words in and the page never turned")
    standing = paged.evaluate("() => document.querySelector('.w.queued')?.closest('.pair')?.hidden")
    assert standing is False, "the word the arrows are on is on the page on show"


def test_leaving_and_coming_back_lands_on_the_same_page(paged, built: Path) -> None:
    paged.keyboard.press("Space")
    paged.keyboard.press("Space")
    was = paged.evaluate(PAGE)
    paged.goto(built.as_uri())
    # Not the first pair: on a page further in, the first pair is rightly hidden.
    paged.wait_for_selector(".pair:not([hidden])")
    paged.wait_for_function("() => document.body.classList.contains('paged')")
    assert paged.evaluate(PAGE)["first"] == was["first"]


def test_b_is_the_way_back_to_the_scroll(paged) -> None:
    paged.keyboard.press("b")
    seen = paged.evaluate(PAGE)
    assert seen["paged"] is False
    assert seen["count"] == seen["total"], "every pair is on show again"
