"""The reader's findings from the live QA pass before the weekly portion's post (2026-10-05).

Rashi stays on by default, at full length (David, 2026-10-05), so a verse with its Rashi
beside it is taller than a page — and that is what the reader has to cope with:

B1. Listen keeps the verse being chanted on screen: its own Hebrew line, near the top,
    on pages and on a scroll, and not the middle of a verse-and-Rashi block.
B2. Nothing at the foot — the arrows, the count, the words tab, the player — stands over
    a line of text: a verse taller than the page is cut across pages between two lines.
B3. The sheet printed from any page is the view the reader is in, read from the reader's
    state rather than from a verse that may be hidden on another page.
S1, S3. On a phone every press of the bar stays on the screen while the voice plays,
    and a tap on Listen does not hold the bar out for ever.
S4. Chanted to Spoken while playing goes on playing, from the start of the same verse.
S5. Download PDF says "Preparing PDF…" while the box sets the sheet, and a refusal is
    the box's one sentence.
"""

# The fixtures are imported by name from the browser module, which ruff reads as
# redefinitions wherever a test takes one as an argument.
# ruff: noqa: F811

from __future__ import annotations

import functools
import socketserver
import threading
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api")

from test_reader_browser import (  # noqa: E402, F401
    QAMATS,
    SCROLLING,
    ZAQEF,
    Annotation,
    Block,
    BlockKind,
    Document,
    Ranged,
    Segment,
    SegmentedDocument,
    Token,
    Translation,
    browser,
    coin,
    render,
    voice,
)

#: Verses in the portion, and how long each is in each reading: long enough that a
#: verse is still being said when the test has looked at the page.
VERSES = 12
CHANTED = 3.0
SPOKEN = 2.0
#: Words of Rashi on each verse: a page of commentary on a phone, more than a window on
#: a laptop — the shape of Bereshit's first verses.
RASHI_WORDS = 160

DESK = {"width": 1280, "height": 800}
WIDE = {"width": 1440, "height": 900}
TABLET = {"width": 820, "height": 1180}
PHONE = {"width": 390, "height": 844}
SMALL = {"width": 360, "height": 740}


def commented_portion(home: Path, parasha: Path, monkeypatch) -> str:
    """Ruth 1:1-12 cut as a portion is: pointed and accented, the English beside it,
    Onkelos and a long Rashi under it, chanted and spoken. Built where the corpus keeps
    a portion's reader, so the page offers its sheet; the path it is served at."""
    from targum.errors import TargumError
    from targum.models import Vocalization
    from targum.recording import Part, Recording
    from targum.recording import index as recording_index
    from targum.recording import splice as splicing

    def no_splice(*_: object) -> None:
        raise TargumError("no ffmpeg here")

    monkeypatch.setattr(splicing, "splice", no_splice)
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(home))
    portion = "sefaria:Ruth 1:1-12"
    for source, name, span, credit in (
        (portion, "chanted.wav", CHANTED, "Somebody Chanting"),
        ("sefaria:Ruth", "spoken.wav", SPOKEN, "Somebody Reading"),
    ):
        folder = home / recording_index.slug(source)
        folder.mkdir(parents=True, exist_ok=True)
        voice(folder / name, span * VERSES)
        recording = Recording(
            source=source,
            credit=credit,
            licence="CC BY-SA 3.0",
            parts=[
                Part(
                    ref="Ruth 1",
                    audio=name,
                    spans={f"Ruth 1:{n + 1}": [n * span, (n + 1) * span] for n in range(VERSES)},
                )
            ],
        )
        (folder / recording_index.MANIFEST).write_text(
            recording.model_dump_json(), encoding="utf-8"
        )
    segments, pointed, tokens = [], {}, {}
    for n in range(VERSES):
        words = [coin(n * 10 + i) for i in range(10)]
        segment = Segment(
            id=f"{n:04d}.000-aaaaaa",
            block_id=f"b{n:04d}",
            block_index=n,
            index=0,
            kind=BlockKind.verse,
            text=" ".join(words),
            ref=f"Ruth 1:{n + 1}",
        )
        segments.append(segment)
        pointed[segment.id] = " ".join(QAMATS.join(word) + QAMATS + ZAQEF for word in words)
        offset, marks = 0, []
        for word in words:
            marks.append(
                Token(start=offset, end=offset + len(word), surface=word, lemma=word, band=2)
            )
            offset += len(word) + 1
        tokens[segment.id] = marks
    document = Document(
        source=portion,
        title="Ruth",
        language="he",
        blocks=[Block(id=s.block_id, kind=s.kind, text=s.text, ref=s.ref) for s in segments],
        content_hash="h",
    )
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="test/1", segments=segments
    )

    def rendering(name: str, code: str, said) -> Translation:
        return Translation(
            name=name,
            document_hash="h",
            source_language="he",
            target_language=code,
            provider="null",
            segments={s.id: said(n) for n, s in enumerate(segments)},
        )

    out = parasha / "read" / "ruth" / "reader"
    built = render(
        document,
        segmented,
        [
            rendering("English", "en", lambda n: f"And it came to pass in verse {n + 1}."),
            rendering("Onkelos", "arc", lambda n: "והוה ביומי " + coin(900 + n)),
            rendering(
                "Rashi on Ruth",
                "he",
                lambda n: " ".join(coin(2000 + n * RASHI_WORDS + i) for i in range(RASHI_WORDS)),
            ),
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
        vocalization=Vocalization(
            document_hash="h", language="he", vocalizer="test/1", segments=pointed, machine=[]
        ),
        recordings_beside=True,
    )[0]
    return "/parasha/" + str(built.relative_to(parasha))


@pytest.fixture(scope="module")
def served(tmp_path_factory: pytest.TempPathFactory):
    """The portion's reader served the way the box serves the corpus, at
    `/parasha/read/ruth/reader/…`, which is the address the print press is offered on."""
    root = tmp_path_factory.mktemp("qa")
    monkeypatch = pytest.MonkeyPatch()
    path = commented_portion(root / "recordings", root / "parasha", monkeypatch)
    monkeypatch.undo()
    parasha = root / "parasha"

    class Corpus(Ranged):
        def translate_path(self, path: str) -> str:  # type: ignore[override]
            path = path.split("?", 1)[0].split("#", 1)[0]
            if path.startswith("/parasha/"):
                path = path[len("/parasha") :]
            return str(parasha) + path

    server = socketserver.ThreadingTCPServer(
        ("127.0.0.1", 0), functools.partial(Corpus, directory=str(parasha))
    )
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}{path}"
    server.shutdown()


def opened(browser, url: str, viewport: dict[str, int], scrolling: bool = False, touch=False):
    context = browser.new_context(
        viewport=viewport,
        reduced_motion="reduce",
        has_touch=touch,
        is_mobile=touch and viewport["width"] < 500,
    )
    if scrolling:
        context.add_init_script(SCROLLING)
    page = context.new_page()
    page.goto(url)
    page.wait_for_function("() => !!document.querySelector('.pair.verse:not([hidden])')")
    page.wait_for_function("() => !!(window.TargumPlayer && window.TargumPlayer.length() > 0)")
    page.wait_for_timeout(300)
    return context, page


def listen(page, touch: bool = False) -> None:
    # The bar's play at a desk; on a phone the foot bar's (design.md §12, 2026-10-09).
    press = ".listen-play" if page.locator(".listen-play").is_visible() else "#player .player-play"
    if touch:
        page.tap(press)
    else:
        page.click(press)
        page.mouse.move(600, 500)
    page.wait_for_function("() => document.getElementById('listen').classList.contains('playing')")


# -- B1: the verse being chanted is in front of the reader --------------------------------

#: Where the verse being said stands: its Hebrew as showing, the window's room under the
#: bar and above whatever stands at the foot.
SAYING = """
() => {
  const pair = document.querySelector('.pair.voiced.now');
  if (!pair) return null;
  const cell = [...pair.querySelectorAll('.src')].find((c) => c.getClientRects().length);
  const bar = document.querySelector('.bar').getBoundingClientRect().bottom;
  let floor = innerHeight;
  for (const s of ['#player', '#turn']) {
    const el = document.querySelector(s);
    if (!el || el.hidden || !el.getClientRects().length) continue;
    floor = Math.min(floor, el.getBoundingClientRect().top);
  }
  if (!cell) return { id: pair.id, shown: false };
  const box = cell.getBoundingClientRect();
  const tall = pair.getBoundingClientRect().height;
  return { id: pair.id, shown: true, top: box.top, bottom: box.bottom, bar, floor, tall };
}
"""


@pytest.mark.parametrize("scrolling", [False, True], ids=["pages", "scroll"])
@pytest.mark.parametrize("viewport", [DESK, PHONE], ids=["desk", "phone"])
def test_listen_keeps_the_verse_being_chanted_on_screen(
    browser, served: str, viewport, scrolling: bool
) -> None:
    """Five verses in, the verse being chanted is on the screen, its Hebrew line in the
    top half of the room — whether the reader turns pages or scrolls. The voice used to
    centre the whole verse-and-Rashi block, which put the Hebrew off the top, and on
    pages it never turned to the verse at all."""
    context, page = opened(browser, served, viewport, scrolling=scrolling)
    listen(page)
    for verse in (5, 9):
        page.evaluate(f"() => window.TargumPlayer.seek({(verse - 1) * CHANTED + 0.2})")
        page.wait_for_function(
            f"() => document.querySelector('.pair.voiced.now')?.id === '1:{verse}'"
        )
        page.wait_for_timeout(400)
        at: dict[str, Any] = page.evaluate(SAYING)
        # Over half the window: on pages the piece shown is the page's height, which the
        # word list's tab at the foot takes a strip of since the list starts closed
        # (2026-10-09).
        assert at["tall"] > viewport["height"] * 0.55, "the fixture's verses are tall"
        assert at["shown"], f"1:{verse} is on a page nobody can see"
        assert at["top"] >= at["bar"] - 1, f"1:{verse} is behind the bar: {at}"
        assert at["bottom"] <= at["floor"] + 1, f"1:{verse} is under the foot: {at}"
        half = at["bar"] + (at["floor"] - at["bar"]) / 2
        assert at["top"] <= half, f"1:{verse} is not near the top: {at}"
    context.close()


# -- B2: nothing at the foot covers a line ------------------------------------------------

#: Every line of text on the screen that a control at the foot, or the bar, stands over.
#: A line of a verse cut across pages counts only where its piece shows.
COVERED = """
() => {
  const SEEN = { checkOpacity: true, checkVisibilityCSS: true };
  const CHROME = '.bar, #turn, #player, #list-tab, .bar-pop, .bar-more, #card, script, [hidden]';
  const controls = [];
  for (const s of ['#turn .back', '#turn .forward', '#page-of', '#player', '#list-tab', '.bar']) {
    const el = document.querySelector(s);
    if (!el || !el.checkVisibility(SEEN)) continue;
    const r = el.getBoundingClientRect();
    if (r.width && r.height) controls.push([s, r]);
  }
  const hits = [];
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walk.nextNode(); n; n = walk.nextNode()) {
    if (!n.data.trim()) continue;
    const el = n.parentElement;
    if (!el || el.closest(CHROME) || !el.checkVisibility(SEEN)) continue;
    const cut = el.closest('.pair.sliced');
    const window_ = cut && cut.getBoundingClientRect();
    const range = document.createRange();
    range.selectNodeContents(n);
    for (const r of range.getClientRects()) {
      const top = window_ ? Math.max(r.top, window_.top) : r.top;
      const bottom = window_ ? Math.min(r.bottom, window_.bottom) : r.bottom;
      if (r.width < 2 || bottom - top < 2 || bottom <= 0 || top >= innerHeight) continue;
      for (const [s, c] of controls) {
        const x = Math.min(r.right, c.right) - Math.max(r.left, c.left);
        const y = Math.min(bottom, c.bottom) - Math.max(top, c.top);
        if (x > 1 && y > 2) hits.push(s + ' over "' + n.data.trim().slice(0, 12) + '"');
      }
    }
  }
  return { hits, page: document.getElementById('page-of').textContent,
           blank: document.documentElement.scrollHeight - innerHeight };
}
"""


def every_page(page) -> list[dict[str, Any]]:
    seen = []
    for _ in range(200):
        seen.append(page.evaluate(COVERED))
        here, _, last = seen[-1]["page"].partition(" of ")
        if here == last:
            return seen
        page.click("#turn .forward")
        page.wait_for_timeout(30)
    raise AssertionError("the pages never ended")


@pytest.mark.parametrize(
    "viewport", [WIDE, DESK, TABLET, PHONE], ids=["1440", "1280", "820", "390"]
)
def test_no_page_has_a_line_under_the_controls(browser, served: str, viewport) -> None:
    """On every page of the aliyah, at rest, no line is under the arrows, the count, the
    words tab or the bar — and no page scrolls into a blank where a verse was cut."""
    touch = viewport["width"] < 900
    context, page = opened(browser, served, viewport, touch=touch)
    seen = every_page(page)
    assert len(seen) > VERSES, "a verse with its Rashi is cut across pages"
    for one in seen:
        assert not one["hits"], f"page {one['page']}: {one['hits'][:4]}"
    context.close()


@pytest.mark.parametrize("viewport", [WIDE, PHONE], ids=["1440", "390"])
def test_nothing_covers_a_line_while_it_plays(browser, served: str, viewport) -> None:
    """With the player out too: the page is cut around it, at every verse it turns to."""
    touch = viewport["width"] < 900
    context, page = opened(browser, served, viewport, touch=touch)
    listen(page, touch=touch)
    for verse in (1, 4, 8):
        page.evaluate(f"() => window.TargumPlayer.seek({(verse - 1) * CHANTED + 0.2})")
        page.wait_for_function(
            f"() => document.querySelector('.pair.voiced.now')?.id === '1:{verse}'"
        )
        page.wait_for_timeout(400)
        covered = page.evaluate(COVERED)
        assert not covered["hits"], f"at 1:{verse}: {covered['hits'][:4]}"
    context.close()


def test_a_cut_verse_keeps_the_place_it_was_read_to(browser, served: str) -> None:
    """On the second piece of a cut verse, a change of layout — the player coming up —
    leaves the reader on the commentary they were reading, not back at the verse."""
    context, page = opened(browser, served, PHONE, touch=True)
    page.click("#turn .forward")
    page.wait_for_timeout(100)
    on = page.evaluate("() => document.querySelector('.pair.sliced')?.id")
    assert on == "1:1", "the second page carries on verse one's Rashi"
    page.evaluate("() => window.TargumPlayer.show()")
    page.wait_for_selector("#player")
    page.wait_for_timeout(300)
    piece = page.evaluate(
        "() => getComputedStyle(document.querySelector('.pair.sliced'))"
        ".getPropertyValue('--cut-top')"
    )
    assert piece and float(piece.replace("px", "")) > 0, "still on the commentary"
    context.close()


# -- B3: the sheet is the view the reader is in --------------------------------------------

#: The press for this aliyah's sheet where the page has one, the whole portion's where not.
SHEET = "#more-sheet-aliyah, #more-sheet"


def asked_for_sheet(page) -> list[str]:
    asked: list[str] = []

    def answer(route) -> None:
        asked.append(route.request.url)
        route.fulfill(status=200, body=b"%PDF-1.4\n", headers={"Content-Type": "application/pdf"})

    page.route("**/*.pdf*", answer)
    return asked


def test_the_sheet_from_a_later_page_keeps_the_vowels_and_the_teamim(browser, served: str) -> None:
    """From page four, as from page one: the vowels and the te'amim the reader sees. The
    press read them off the first verse's cell, hidden on every page but the first."""
    context, page = opened(browser, served, DESK)
    asked = asked_for_sheet(page)
    for _ in range(3):
        page.click("#turn .forward")
    assert page.evaluate("() => document.getElementById('1:1').hidden"), "verse one is away"
    page.click("#print-open")
    page.locator(SHEET).first.click()
    page.wait_for_timeout(300)
    assert asked, "the sheet was asked for"
    assert "vowels=1" in asked[-1] and "taamim=1" in asked[-1], asked[-1]
    # And the view still goes with it: te'amim off is te'amim off.
    if not page.locator(SHEET).first.is_visible():
        page.click("#print-open")
    page.evaluate("() => window.targumReader.setTaamim(false)")
    page.locator(SHEET).first.click()
    page.wait_for_timeout(300)
    assert "vowels=1" in asked[-1] and "taamim=0" in asked[-1], asked[-1]
    context.close()


# -- S1 and S3: the bar on a phone ---------------------------------------------------------

TOOLS = """
() => [...document.querySelectorAll('.bar .listen > *, .bar-tools > *')]
  .filter((el) => el.getClientRects().length && getComputedStyle(el).display !== 'none')
  .map((el) => { const r = el.getBoundingClientRect();
                 return { what: el.className || el.id, left: r.left, right: r.right }; })
"""


@pytest.mark.parametrize("viewport", [PHONE, SMALL], ids=["390", "360"])
def test_every_press_of_the_bar_stays_on_a_phone_while_it_plays(
    browser, served: str, viewport
) -> None:
    """⋯ used to ride off the right edge once the voice's line and clock came in."""
    context, page = opened(browser, served, viewport, touch=True)
    for state in ("idle", "playing"):
        if state == "playing":
            listen(page, touch=True)
            page.wait_for_timeout(1200)
        for tool in page.evaluate(TOOLS):
            assert tool["left"] >= -0.5, f"{state}: {tool}"
            assert tool["right"] <= viewport["width"] + 0.5, f"{state}: {tool}"
    context.close()


def test_a_tap_on_listen_does_not_hold_the_bar_out(browser, served: str) -> None:
    """On a phone the bar steps back after Listen, as it does under a mouse: the tap on
    Listen is not a pointer resting at the top, and a touch leaves no hover behind."""
    context, page = opened(browser, served, PHONE, touch=True)
    listen(page, touch=True)
    page.wait_for_function(
        "() => document.querySelector('.bar').classList.contains('quiet')", timeout=5000
    )
    # A finger at the top brings it back, and lifting it lets it step back again.
    # On the bar's own edge, which presses nothing.
    page.touchscreen.tap(4, 20)
    page.wait_for_function("() => !document.querySelector('.bar').classList.contains('quiet')")
    assert page.evaluate("() => document.getElementById('listen').classList.contains('playing')")
    page.wait_for_function(
        "() => document.querySelector('.bar').classList.contains('quiet')", timeout=5000
    )
    context.close()


# -- S4: chanted to spoken while it plays ---------------------------------------------------

PLAYER = """
() => ({ playing: document.getElementById('listen').classList.contains('playing'),
         at: window.TargumPlayer.at(), length: window.TargumPlayer.length(),
         now: document.querySelector('.pair.voiced.now')?.id || null })
"""


def switch_to_spoken(page) -> None:
    page.keyboard.press("Escape")
    page.click("#voices-open")
    page.click('[data-recording="spoken"]')
    page.wait_for_function(
        f"() => Math.abs(window.TargumPlayer.length() - {SPOKEN * VERSES}) < 0.05"
    )


def test_switching_to_spoken_while_playing_goes_on_from_the_same_verse(
    browser, served: str
) -> None:
    context, page = opened(browser, served, DESK)
    listen(page)
    page.evaluate(f"() => window.TargumPlayer.seek({4 * CHANTED + 1.0})")
    page.wait_for_function("() => document.querySelector('.pair.voiced.now')?.id === '1:5'")
    switch_to_spoken(page)
    page.wait_for_function(
        "() => document.getElementById('listen').classList.contains('playing')", timeout=3000
    )
    page.wait_for_timeout(300)
    now = page.evaluate(PLAYER)
    assert now["playing"], "it goes on playing"
    assert 4 * SPOKEN <= now["at"] < 5 * SPOKEN, f"from the start of 1:5 in the other: {now}"
    assert now["now"] == "1:5"
    context.close()


def test_switching_while_paused_stays_paused(browser, served: str) -> None:
    context, page = opened(browser, served, DESK)
    listen(page)
    page.evaluate(f"() => window.TargumPlayer.seek({4 * CHANTED + 1.0})")
    page.wait_for_function("() => document.querySelector('.pair.voiced.now')?.id === '1:5'")
    page.keyboard.press("Escape")
    page.click(".listen-play")
    page.wait_for_function("() => !document.getElementById('listen').classList.contains('playing')")
    switch_to_spoken(page)
    page.wait_for_timeout(600)
    assert not page.evaluate(PLAYER)["playing"], "paused is paused"
    context.close()


# -- S5: Preparing PDF… ---------------------------------------------------------------------


def test_the_sheet_says_it_is_being_made_until_it_comes(browser, served: str) -> None:
    """The box takes five or six seconds over a portion's sheet. The press says
    "Preparing PDF…" until the file is in hand, then is itself again, and the file is
    saved under the box's name for it."""
    context, page = opened(browser, served, DESK)
    held: list[Any] = []
    page.route("**/*.pdf*", lambda route: held.append(route))
    page.click("#print-open")
    press = page.locator(SHEET).first
    named = press.locator(".pick-name").inner_text()
    press.click()
    page.wait_for_timeout(300)
    assert held, "the sheet was asked for"
    assert press.locator(".pick-name").inner_text() == "Preparing PDF…"
    assert press.get_attribute("aria-busy") == "true"
    with page.expect_download() as saving:
        held[0].fulfill(
            status=200,
            body=b"%PDF-1.4\n",
            headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": 'attachment; filename="ruth-aliyah-1.pdf"',
            },
        )
    assert saving.value.suggested_filename == "ruth-aliyah-1.pdf"
    # All of the file before the context closes, as in `test_parasha_russian_browser`:
    # closing on a download still being written is where CI's Chromium died
    # (targum-internal#427, 2026-10-07).
    assert Path(saving.value.path()).read_bytes() == b"%PDF-1.4\n"
    assert press.locator(".pick-name").inner_text() == named, "and the press is itself again"
    assert press.get_attribute("aria-busy") is None
    context.close()


def test_a_sheet_the_box_cannot_make_says_so_in_one_sentence(browser, served: str) -> None:
    context, page = opened(browser, served, DESK)
    sentence = "We can't make the PDF right now. Try again in a minute."
    page.route(
        "**/*.pdf*",
        lambda route: route.fulfill(
            status=503, body=sentence, headers={"Content-Type": "text/plain; charset=utf-8"}
        ),
    )
    page.click("#print-open")
    press = page.locator(SHEET).first
    named = press.locator(".pick-name").inner_text()
    press.click()
    page.wait_for_selector("#sheet-said:not([hidden])")
    assert page.inner_text("#sheet-said") == sentence
    assert press.locator(".pick-name").inner_text() == named
    context.close()
