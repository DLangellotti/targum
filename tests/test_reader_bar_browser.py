"""The reader's bar as one calm row (targum-internal#421, David, 2026-10-05).

A. One row: the mark, the title, the count, and at the far end Listen, Aa, print and ⋯.
   Aa holds how the text is set and what stands beside it, in plain rows.
B. The columns beside the verse switch themselves: a × on a column's name under the
   pointer, and a + for a column that is off.
C. The bar steps back while a reader reads on or listens, and comes back for the pointer
   at the top, a scroll up, a pause, Escape or keyboard focus — never while a panel of it
   is out, and always on paper.

What is asserted is what a reader meets in a browser: what opens, where focus goes, what
a screen reader is told, and when the bar is there.
"""

# The fixtures are imported by name from the browser module, which ruff reads as
# redefinitions wherever a test takes one as an argument.
# ruff: noqa: F811

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

# The fixtures live in the browser module rather than a conftest, so they are
# imported by name to register them here.
from test_reader_browser import (  # noqa: E402, F401
    PHONE,
    PREFS,
    VERSES,
    WINDOW,
    Annotation,
    Block,
    BlockKind,
    Document,
    Segment,
    SegmentedDocument,
    Token,
    Translation,
    address,
    browser,
    built,
    coin,
    opened,
    recorded,
    render,
    with_onkelos,
)


def beside_three(out: Path) -> Path:
    """A chapter with its translation and two companions beside the verse: Onkelos and
    Rashi, each in a column of its own, both on for a new reader."""
    segments, tokens = [], {}
    for n in range(VERSES // 10):
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

    return render(
        document,
        segmented,
        [
            translation("English", "en", "In the land of Israel"),
            translation("Onkelos", "arc", "בְּאַרְעָא דְיִשְׂרָאֵל"),
            translation("Rashi on Genesis", "he", "פירוש ראשון"),
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
    )[0]


@pytest.fixture(scope="module")
def columns(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return beside_three(tmp_path_factory.mktemp("columns") / "reader")


def open_page(browser, reader: Path, viewport=None, scrolling=True, touch=False):  # noqa: F811
    if touch:
        made = browser.new_context(
            viewport=viewport or WINDOW, reduced_motion="reduce", is_mobile=True, has_touch=True
        )
    else:
        made = opened(browser, viewport=viewport or WINDOW, scrolling=scrolling)
    page = made.new_page()
    page.goto(address(reader))
    page.wait_for_selector(".pair")
    page.wait_for_timeout(200)
    return made, page


ROW = """
() => {
  const bar = document.querySelector('.bar').getBoundingClientRect();
  const shown = (el) => !!el && el.getClientRects().length > 0;
  const mid = (el) => { const r = el.getBoundingClientRect(); return r.top + r.height / 2; };
  const tools = ['.bar-brand:not([hidden])', '.bar-title', '#aa-open', '.bar-tools [data-more]']
    .map((s) => document.querySelector(s));
  return {
    height: bar.height,
    oneLine: tools.every((t) => shown(t) && Math.abs(mid(t) - (bar.top + bar.height / 2)) < 12),
    background: getComputedStyle(document.querySelector('.bar')).backgroundColor,
    print: shown(document.getElementById('print-open')),
    listen: shown(document.getElementById('listen')),
    pills: [...document.querySelectorAll('.bar button.on')]
      .filter((b) => shown(b) && getComputedStyle(b).backgroundColor === 'rgb(107, 100, 92)')
      .length,
  };
}
"""


# -- A: one row, and Aa ------------------------------------------------------------


@pytest.mark.parametrize("width", [1100, 1280, 1440])
def test_the_bar_is_one_row_with_only_what_the_text_has(browser, built: Path, width: int) -> None:  # noqa: F811
    """Mark, title, count, Aa and ⋯ on one line at every desktop width. This chapter has
    no recording and is not a portion, so there is no Listen and no print; and nothing in
    the row is a filled dark pill."""
    context, page = open_page(browser, built, viewport={"width": width, "height": 800})
    row = page.evaluate(ROW)
    context.close()
    assert row["oneLine"], row
    assert row["height"] <= 60, f"one row, not {row['height']}px"
    assert not row["listen"] and not row["print"], "a control the text does not have"
    assert row["pills"] == 0
    assert row["background"] == "rgb(251, 249, 245)", "paper, solid"


AA = """
() => {
  const panel = document.getElementById('aa');
  const press = document.getElementById('aa-open');
  return {
    open: panel.classList.contains('open') && panel.getClientRects().length > 0,
    expanded: press.getAttribute('aria-expanded'),
    controls: press.getAttribute('aria-controls'),
    role: panel.getAttribute('role'),
    named: panel.getAttribute('aria-label'),
    focusInside: panel.contains(document.activeElement),
    focusOnPress: document.activeElement === press,
    rows: [...panel.querySelectorAll('.aa-label, .aa-name')]
      .filter((e) => e.getClientRects().length).map((e) => e.textContent.trim()),
  };
}
"""


def test_aa_opens_from_the_keyboard_and_escape_brings_focus_back(browser, columns: Path) -> None:
    """A dialog named for what it holds, disclosed by its press; opened from the keyboard,
    focus goes to its first control, and Escape shuts it with focus back on Aa."""
    context, page = open_page(browser, columns)
    page.focus("#aa-open")
    page.keyboard.press("Enter")
    page.wait_for_selector("#aa.open")
    opened_with_keys = page.evaluate(AA)
    page.keyboard.press("Escape")
    shut = page.evaluate(AA)
    context.close()

    assert opened_with_keys["open"] and opened_with_keys["expanded"] == "true"
    assert opened_with_keys["controls"] == "aa" and opened_with_keys["role"] == "dialog"
    assert opened_with_keys["named"] == "Text and columns"
    assert opened_with_keys["focusInside"], "focus goes into the panel"
    assert not shut["open"] and shut["expanded"] == "false"
    assert shut["focusOnPress"], "and comes back to Aa"


def test_aa_holds_the_rows_this_text_has_and_no_others(
    browser,  # noqa: F811
    columns: Path,
    built: Path,  # noqa: F811
) -> None:
    """Beside the verse lists the translation and each companion, by name; a text with no
    companions has no such rows, and a text with one translation has no choice of it."""
    context, page = open_page(browser, columns)
    page.click("#aa-open")
    beside = page.evaluate(AA)["rows"]
    context.close()
    context, page = open_page(browser, built)
    page.click("#aa-open")
    plain = page.evaluate(AA)["rows"]
    context.close()

    assert ["English", "Onkelos", "Rashi"] == [
        r for r in beside if r in ("English", "Onkelos", "Rashi")
    ]
    assert "Text size" in beside and "Line spacing" in beside
    assert "Onkelos" not in plain and "Rashi" not in plain and "Layout" not in plain
    assert "Text size" in plain


def test_aa_stays_up_for_its_own_controls_and_a_press_outside_shuts_it(
    browser, columns: Path
) -> None:
    """A switch in Aa changes the page and leaves the panel where it is; the size line
    moves with the type; a press on the page puts the panel away."""
    context, page = open_page(browser, columns)
    page.click("#aa-open")
    meter = "() => parseFloat(document.querySelector('#aa .aa-meter i').style.inlineSize)"
    before = page.evaluate(meter)
    page.click('#aa [data-type="larger"]')
    assert page.evaluate(meter) > before, "the line says the type grew"
    page.click('#companions [data-companion="targum"]')
    assert page.evaluate("() => document.getElementById('aa').classList.contains('open')")
    assert page.get_attribute('#companions [data-companion="targum"]', "aria-pressed") == "false"
    assert page.evaluate(PREFS)["companions"]["targum"] is False
    page.mouse.click(300, 600)
    assert not page.evaluate("() => document.getElementById('aa').classList.contains('open')")
    context.close()


def test_on_a_phone_aa_is_a_sheet_from_the_foot(browser, columns: Path) -> None:
    context, page = open_page(browser, columns, viewport=PHONE)
    page.click("#aa-open")
    page.wait_for_timeout(300)
    sheet = page.evaluate(
        """() => {
          const r = document.getElementById('aa').getBoundingClientRect();
          return { bottom: r.bottom, left: r.left, width: r.width };
        }"""
    )
    context.close()
    assert sheet["bottom"] == pytest.approx(PHONE["height"], abs=1)
    assert sheet["left"] == pytest.approx(0, abs=1) and sheet["width"] == pytest.approx(
        PHONE["width"], abs=1
    )


# -- B: the columns switch themselves ------------------------------------------------


COLUMNS = """
() => {
  const shown = (name) => [...document.querySelectorAll('.cmp[data-companion="' + name + '"]')]
    .some((c) => !c.hidden && c.getClientRects().length);
  return {
    targum: shown('targum'),
    rashi: shown('rashi'),
    chips: [...document.querySelectorAll('.beside-first .cmp-add')]
      .filter((c) => c.getClientRects().length).map((c) => c.textContent),
    pressed: document.querySelector('#companions [data-companion="targum"]')
      .getAttribute('aria-pressed'),
  };
}
"""


def test_a_column_is_put_away_by_its_x_and_brought_back_by_its_chip(browser, columns: Path) -> None:
    """Under the pointer a column's name shows a quiet ×; pressed, the column goes, the
    Aa switch says so, and a faint "+ Onkelos" waits at the head of the first verse while
    another column stands. Pressing it brings the column back and the chip goes."""
    context, page = open_page(browser, columns)
    assert page.evaluate(COLUMNS)["targum"] and page.evaluate(COLUMNS)["chips"] == []
    name = page.locator('.beside-first .cmp[data-companion="targum"] .cmp-name')
    x = name.locator(".cmp-x")
    assert x.evaluate("(e) => getComputedStyle(e).opacity") == "0", "quiet until hovered"
    name.hover()
    page.wait_for_timeout(250)
    assert float(x.evaluate("(e) => getComputedStyle(e).opacity")) > 0.5
    x.click()
    gone = page.evaluate(COLUMNS)
    assert not gone["targum"] and gone["rashi"]
    assert gone["pressed"] == "false", "one idea of what is on: Aa's switch says it too"
    assert gone["chips"] == ["+ Onkelos"]
    assert page.evaluate(PREFS)["companions"]["targum"] is False, "and it is kept"

    page.click(".beside-first .cmp-add")
    back = page.evaluate(COLUMNS)
    context.close()
    assert back["targum"] and back["pressed"] == "true" and back["chips"] == []


def test_on_a_phone_there_is_no_x_and_aa_is_the_way_in(browser, columns: Path) -> None:
    context, page = open_page(browser, columns, viewport=PHONE, touch=True)
    xs = page.evaluate(
        "() => [...document.querySelectorAll('.cmp-x')].filter((x) => x.getClientRects().length)"
        ".length"
    )
    context.close()
    assert xs == 0


# -- C: the bar steps back -------------------------------------------------------------


QUIET = "() => document.querySelector('.bar').classList.contains('quiet')"


def scroll_by(page, dy: int) -> None:
    page.mouse.wheel(0, dy)
    page.wait_for_timeout(250)


def test_reading_on_steps_the_bar_back_and_a_scroll_up_brings_it(browser, built: Path) -> None:  # noqa: F811
    """Read on down and the bar steps back; its height never changes and its ground is
    paper the whole time. Scrolling up, Escape, or the pointer at the top brings it."""
    context, page = open_page(browser, built, scrolling=True)
    page.mouse.move(600, 500)
    tall = page.evaluate("() => document.querySelector('.bar').getBoundingClientRect().height")
    scroll_by(page, 600)
    assert page.evaluate(QUIET), "reading on"
    stepped = page.evaluate(
        """() => {
          const bar = document.querySelector('.bar');
          return {
            height: bar.getBoundingClientRect().height,
            ground: getComputedStyle(bar).backgroundColor,
            count: getComputedStyle(document.getElementById('known')).opacity,
            aa: getComputedStyle(document.querySelector('.bar-tools')).opacity,
          };
        }"""
    )
    assert stepped["height"] == tall, "nothing on the page moves"
    assert stepped["ground"] == "rgb(251, 249, 245)", "paper, so no text shows through"
    assert stepped["count"] == "1" and stepped["aa"] == "0"

    scroll_by(page, -120)
    assert not page.evaluate(QUIET), "a scroll up brings it back"
    scroll_by(page, 600)
    assert page.evaluate(QUIET)
    page.keyboard.press("Escape")
    assert not page.evaluate(QUIET), "Escape brings it back"
    scroll_by(page, 600)
    assert page.evaluate(QUIET)
    page.mouse.move(600, 20)
    page.wait_for_timeout(100)
    assert not page.evaluate(QUIET), "the pointer at the top brings it back"
    context.close()


def test_the_bar_never_steps_back_with_a_panel_out_or_focus_in_it(browser, built: Path) -> None:  # noqa: F811
    context, page = open_page(browser, built, scrolling=True)
    page.focus("#aa-open")
    page.keyboard.press("Enter")
    page.mouse.move(600, 500)
    scroll_by(page, 600)
    assert not page.evaluate(QUIET), "Aa is out"
    page.keyboard.press("Escape")
    # Escape hands focus back to Aa, from the keyboard: the bar holds while it is there.
    scroll_by(page, 600)
    assert not page.evaluate(QUIET), "keyboard focus is in the bar"
    page.evaluate("() => document.activeElement.blur()")
    scroll_by(page, 600)
    assert page.evaluate(QUIET), "and steps back once focus has left"
    page.keyboard.press("Tab")
    page.evaluate("() => document.getElementById('aa-open').focus()")
    page.wait_for_timeout(50)
    assert not page.evaluate(QUIET), "focus coming into the bar brings it back"
    context.close()


def test_listening_steps_the_bar_back_and_a_pause_brings_it(browser, tmp_path, monkeypatch) -> None:  # noqa: F811
    """Mid-recording the bar is the mark, the count and the player; pausing brings the
    rest back at once."""
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path / "recordings"))
    reader = recorded(tmp_path / "recordings", tmp_path / "reader")
    context, page = open_page(browser, reader, scrolling=True)
    page.click(".listen-play")
    page.mouse.move(600, 500)
    page.wait_for_function("() => document.getElementById('listen').classList.contains('playing')")
    page.wait_for_function(QUIET, timeout=5000)
    player = page.evaluate(
        """() => ({
          play: getComputedStyle(document.querySelector('.listen-play')).opacity,
          line: document.querySelector('.listen-track').getClientRects().length > 0,
        })"""
    )
    assert player["play"] == "1" and player["line"], "the player stays, with its line"
    page.keyboard.press("Space")
    page.wait_for_function("() => !document.getElementById('listen').classList.contains('playing')")
    assert not page.evaluate(QUIET), "a pause brings the bar back"
    context.close()


#: The band on the line being said, and on the line under the pointer.
BANDS = """
() => {
  const now = document.querySelector('.pair.voiced.now');
  const hovered = [...document.querySelectorAll('.pair')].find((p) => p.matches(':hover'));
  const band = (el) => el && getComputedStyle(el).backgroundColor;
  return { now: band(now), hovered: band(hovered), same: !!now && now === hovered };
}
"""


def test_a_line_under_the_pointer_does_not_read_as_the_line_being_said(
    browser, tmp_path, monkeypatch
) -> None:
    """While the voice goes, the raised band is where it is. A hovered line wearing the
    same band read as the voice having jumped there (targum-internal#420); paused, the
    pointer has its band back."""
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path / "recordings"))
    reader = recorded(tmp_path / "recordings", tmp_path / "reader")
    context, page = open_page(browser, reader, scrolling=True)
    page.click(".listen-play")
    page.wait_for_function("() => document.body.classList.contains('voicing')")
    page.wait_for_selector(".pair.voiced.now")
    other = page.evaluate(
        """() => {
          const now = document.querySelector('.pair.voiced.now');
          const other = [...document.querySelectorAll('.pair.voiced')].find((p) => {
            const box = p.getBoundingClientRect();
            return p !== now && box.top > 120 && box.bottom < window.innerHeight - 160;
          });
          const box = other.getBoundingClientRect();
          return { x: box.left + box.width / 2, y: box.top + box.height / 2 };
        }"""
    )
    page.mouse.move(other["x"], other["y"])
    page.wait_for_timeout(100)
    playing = page.evaluate(BANDS)
    assert playing["hovered"] and not playing["same"], playing
    assert playing["hovered"] != playing["now"], f"the hovered line wears the band: {playing}"

    page.keyboard.press("Space")
    page.wait_for_function("() => !document.body.classList.contains('voicing')")
    page.mouse.move(other["x"], other["y"] + 1)
    page.wait_for_timeout(100)
    paused = page.evaluate(BANDS)
    assert paused["hovered"] == playing["now"], f"paused, the pointer has its band back: {paused}"
    context.close()


# -- the strip waits for Listen (David, 2026-10-05) ----------------------------------


STRIP = """
() => {
  const strip = document.getElementById('player');
  return {
    shown: !strip.hidden && strip.getClientRects().length > 0,
    playing: document.getElementById('listen').classList.contains('playing'),
    onListen: document.activeElement === document.querySelector('.listen-play'),
    standing: document.body.classList.contains('has-player'),
  };
}
"""


def test_the_strip_waits_for_listen_and_its_x_puts_it_away(browser, tmp_path, monkeypatch) -> None:
    """Nothing at the foot when a recorded text opens. Listen starts the voice and brings
    the strip up with every control it had; its × stops the voice, puts it away and
    hands focus back to Listen; and nothing is remembered, so the page opens the same
    way again."""
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path / "recordings"))
    reader = recorded(tmp_path / "recordings", tmp_path / "reader")
    context, page = open_page(browser, reader)
    opened_with = page.evaluate(STRIP)
    page.click(".listen-play")
    page.wait_for_function("() => document.getElementById('listen').classList.contains('playing')")
    up = page.evaluate(STRIP)
    controls = page.evaluate(
        """() => ['.player-play', '.player-track', '.player-back', '.player-on',
                  '.player-slower', '.player-rate-now', '.player-faster', '.player-first',
                  '.player-get', '.player-close']
          .filter((s) => { const e = document.querySelector('#player ' + s);
                           return e && e.getClientRects().length > 0; })"""
    )
    page.focus(".player-close")
    page.keyboard.press("Enter")
    away = page.evaluate(STRIP)
    page.reload()
    page.wait_for_selector(".pair")
    again = page.evaluate(STRIP)
    context.close()

    assert not opened_with["shown"] and not opened_with["standing"], "nothing at the foot"
    assert up["shown"] and up["playing"] and up["standing"]
    assert len(controls) == 10, controls
    assert not away["shown"] and not away["playing"] and away["onListen"]
    assert not again["shown"], "put away is not remembered, and neither is up"


# -- shnayim mikra is a practice switch (David, 2026-10-05) ----------------------------


PRACTICE = """
() => {
  const sw = document.getElementById('practice-on');
  const how = document.getElementById('practice-how');
  const held = document.getElementById('columns-held');
  return {
    on: sw.getAttribute('aria-pressed'),
    how: !how.hidden && how.getClientRects().length > 0,
    note: how.querySelector('.aa-note').textContent.trim(),
    held: !held.hidden && held.getClientRects().length > 0,
    heldText: held.textContent.trim(),
    grey: [...document.querySelectorAll('#companions .companion')]
      .every((k) => k.classList.contains('held')),
    layout: [...document.querySelectorAll('#aa .aa-label')]
      .some((l) => l.textContent.trim() === 'Layout'),
    walking: document.body.classList.contains('practice-verse'),
  };
}
"""


def test_shnayim_mikra_is_a_switch_and_a_column_press_puts_it_down(
    browser, with_onkelos: Path
) -> None:
    """Read is the only layout. The practice is its own switch in Aa; on, it says what it
    does and offers By verse and By aliyah, and the column switches go grey with "Shown
    in Read". Pressing one puts the practice down and brings the text back to Read with
    that column on."""
    context, page = open_page(browser, with_onkelos / "sec-0001.html", scrolling=False)
    page.click("#aa-open")
    off = page.evaluate(PRACTICE)
    page.click("#practice-on")
    on = page.evaluate(PRACTICE)
    ways = page.evaluate(
        "() => [...document.querySelectorAll('#practice .practice-key')]"
        ".filter((k) => k.getClientRects().length).map((k) => k.textContent.trim())"
    )
    page.click('#companions [data-companion="targum"]')
    back = page.evaluate(PRACTICE)
    targum = page.get_attribute('#companions [data-companion="targum"]', "aria-pressed")
    context.close()

    assert not off["layout"], "no Layout row: Read is the only layout"
    assert off["on"] == "false" and not off["how"] and not off["held"] and not off["grey"]
    assert on["on"] == "true" and on["how"] and on["walking"]
    assert on["note"] == "Each verse twice in Hebrew, then once in Onkelos"
    assert ways == ["By verse", "By aliyah"]
    assert on["held"] and on["heldText"] == "Shown in Read" and on["grey"]
    assert back["on"] == "false" and not back["walking"] and not back["grey"]
    assert targum == "true", "the column pressed is on"


# -- by how often it is pressed (David, 2026-10-08, design.md §12) ---------------------

DRAWN = """
() => {
  const shown = (el) => !!el && el.getClientRects().length > 0;
  const named = (el) => ({
    label: el.getAttribute('aria-label'),
    title: el.getAttribute('title'),
    words: el.textContent.trim(),
    drawn: !!el.querySelector('svg'),
  });
  const more = [...document.querySelectorAll('#more .group[data-what]')]
    .filter((g) => !g.hidden)
    .map((g) => g.getAttribute('data-what'));
  return {
    play: shown(document.querySelector('.bar .listen-play'))
      && named(document.querySelector('.bar .listen-play')),
    rate: shown(document.querySelector('.bar .bar-rate'))
      && named(document.querySelector('.bar .bar-rate')),
    modes: [...document.querySelectorAll('.bar .bar-tools > .modes button')]
      .filter(shown).map(named),
    aa: [...document.querySelectorAll('#aa .aa-name, #aa .aa-label')]
      .map((e) => e.textContent.trim()),
    more,
  };
}
"""


def test_the_bar_draws_play_the_speed_and_the_view_and_names_each(
    browser, tmp_path, monkeypatch
) -> None:  # noqa: F811
    """Play is a drawing, not the word Listen; the speed stands beside it; the view is three
    drawings, each named for a screen reader and on the hover. The page's settings that
    are not pressed every minute are rows of Aa, and ⋯ keeps the rare things."""
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path / "recordings"))
    reader = recorded(tmp_path / "recordings", tmp_path / "reader")
    context, page = open_page(browser, reader)
    drawn = page.evaluate(DRAWN)
    page.click(".bar .bar-rate")
    page.wait_for_selector("#rates.open")
    page.click('#rates [data-rate="1.5"]')
    after = page.evaluate(
        """() => ({
          figure: document.querySelector('.bar .bar-rate').textContent.trim(),
          kept: localStorage.getItem('targum:player-rate'),
          shut: !document.getElementById('rates').classList.contains('open'),
        })"""
    )
    page.click('.bar [data-mode="inter"]')
    pressed = page.evaluate(
        "() => [...document.querySelectorAll('.bar .bar-tools > .modes button')]"
        ".map((b) => b.getAttribute('aria-pressed'))"
    )
    context.close()

    assert drawn["play"] and drawn["play"]["drawn"] and drawn["play"]["words"] == ""
    assert drawn["play"]["label"], "named for a screen reader"
    assert drawn["rate"] and drawn["rate"]["words"] == "1×" and drawn["rate"]["label"] == "Speed"
    assert [m["label"] for m in drawn["modes"]] == [
        "Translation beside the text",
        "Translation under each line",
        "The text on its own",
    ]
    assert all(m["drawn"] and m["words"] == "" and m["title"] for m in drawn["modes"])
    assert after == {"figure": "1.5×", "kept": "1.5", "shut": True}
    assert pressed == ["false", "true", "false"]
    assert "Pages" in drawn["aa"] and "Text size" in drawn["aa"]
    assert "View" in drawn["more"], "the phone's copy of the view is a row of ⋯"
    assert "Pages, or one long scroll" not in drawn["more"]
