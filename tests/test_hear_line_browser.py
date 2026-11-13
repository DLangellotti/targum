"""One press, hear a line and see its translation (targum-internal#539, design's spec of
2026-11-13, the free version).

In the text on its own a recorded line's ▶ plays the line and opens its translation under
it, one line at a time; Hear first holds the translation back with the line; ⋯'s Step line
by line steps lines and plays them, where it used to step words; and `h` hears the line
you are on. Nothing here spends: it plays only the audio the page already has.

Each test is one of the spec's fourteen acceptance tests, numbered as there.
"""

# The fixtures are imported by name from the browser module, which ruff reads as
# redefinitions wherever a test takes one as an argument.
# ruff: noqa: F811

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from test_reader_browser import (  # noqa: E402, F401
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
    coin,
    press_in_more,
    render,
    strip_up,
    voice,
)

WIDE = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}

#: Long enough that a line is still being said when the test has looked at the page, and
#: that a step back from the middle of one is more than the 1.5 s that keeps it.
SPAN = 3.0
TURNS = 6

SAID = {
    "en": "Line {n}, as the English reads it.",
    "ru": "Строка {n}, как её читают по-русски.",
}


def recorded(
    home: Path,
    out: Path,
    language: str = "en",
    translated: bool = True,
    turns: int = TURNS,
    span: float = SPAN,
    long: bool = False,
    silent: bool = False,
) -> Path:
    """A built dialogue with its recording, a span over each turn, a word list, and — unless
    `translated` is false — a translation in `language`, which is the chrome's language
    too. `long` makes every translation a paragraph, for a page it can overflow, and
    `silent` writes no scene, so the text has no recording at all."""
    from targum.dialogue.models import Cast, Dialogue, Speaker, Turn

    home.mkdir(parents=True, exist_ok=True)
    voice(home / "voice.wav", span * turns)
    english = SAID[language]
    if long:
        english = " ".join([english] * 14)
    scene = Dialogue(
        id="scene",
        title="A scene",
        english="A scene",
        cast=Cast(
            A=Speaker(voice="one", gender="f", name="דנה"),
            B=Speaker(voice="two", gender="m", name="יונתן"),
        ),
        turns=[
            Turn(
                who="A" if n % 2 == 0 else "B",
                text=" ".join(coin(n * 3 + i) for i in range(3)),
                english=english.format(n=n),
                start=n * span,
                end=(n + 1) * span,
            )
            for n in range(turns)
        ],
        audio="voice.wav",
    )
    if not silent:
        (home / "scene.json").write_text(scene.model_dump_json(), encoding="utf-8")
    segments = [
        Segment(
            id=f"{n:04d}.000-aaaaaa",
            block_id=f"b{n:04d}",
            block_index=n,
            index=n,
            text=turn.text,
            kind=BlockKind.turn,
        )
        for n, turn in enumerate(scene.turns)
    ]
    document = Document(
        # A silent text is another scene, so it never finds this one's recording.
        source="dialogue:quiet" if silent else "dialogue:scene",
        title=scene.title,
        language="he",
        blocks=[
            Block(id=f"b{n:04d}", kind=BlockKind.turn, text=turn.text, speaker=turn.who)
            for n, turn in enumerate(scene.turns)
        ],
        content_hash="h",
    )
    segmented = SegmentedDocument(
        document_hash="h", language="he", segmenter="test/1", segments=segments
    )
    translations = []
    if translated:
        translations.append(
            Translation(
                name="Russian" if language == "ru" else "English",
                document_hash="h",
                source_language="he",
                target_language=language,
                provider="authored",
                segments={s.id: t.english for s, t in zip(segments, scene.turns, strict=True)},
            )
        )
    else:
        # A reader always has a rendering; one with nothing in it is a text not translated.
        translations.append(
            Translation(
                name="English",
                document_hash="h",
                source_language="he",
                target_language="en",
                provider="authored",
                segments={},
            )
        )
    tokens = {}
    for segment in segments:
        offset, marks = 0, []
        for word in segment.text.split(" "):
            marks.append(
                Token(start=offset, end=offset + len(word), surface=word, lemma=word, band=2)
            )
            offset += len(word) + 1
        tokens[segment.id] = marks
    annotation = Annotation(
        document_hash="h",
        language="he",
        annotator="test/1",
        method="frequency",
        method_note="a test",
        tokens=tokens,
    )
    return render(document, segmented, translations, out, annotation=annotation)[0]


def line(n: int) -> str:
    return f"{n:04d}.000-aaaaaa"


#: Whether the page asked anything of anybody that spends: the voice, a word said, a claim.
SPENDS = ("/voice", "/say-word", "/claim", "/build", "/press", "/quote")


def opened(browser, reader: Path, viewport=WIDE, paged: bool = False, offline: bool = False):
    """The reader open in Chromium, the strip up, the text on its own unless a test asks
    otherwise later. Every request it makes is kept, so a test can say none of them spent.
    """
    context = browser.new_context(viewport=viewport, reduced_motion="reduce")
    prefs = {"paged": paged, "defaults": 4, "mode": "source"}
    context.add_init_script(
        "try { localStorage.setItem('targum:prefs', " + json.dumps(json.dumps(prefs)) + "); }"
        " catch (e) {}"
    )
    asked: list[str] = []
    context.on("request", lambda request: asked.append(request.url))
    page = context.new_page()
    if offline:
        context.set_offline(True)
        page.goto(reader.as_uri())
    else:
        page.goto(address(reader))
    page.wait_for_selector(".pair.voiced .say", state="attached")
    strip_up(page)
    # Every event the page notes, kept, so a test can ask for the replay.
    page.evaluate(
        """() => {
          window.__noted = [];
          window.TargumEvents = window.TargumEvents || {};
          const was = window.TargumEvents.note;
          window.TargumEvents.note = (event) => {
            window.__noted.push(event.kind);
            if (was) try { was(event); } catch (e) {}
          };
        }"""
    )
    page.__dict__["asked"] = asked
    return context, page


def spent(page) -> list[str]:
    return [url for url in page.__dict__["asked"] if any(door in url for door in SPENDS)]


#: Each pair's translation, and whether it is on show: drawn, and not held back.
TOLD = """
() => [...document.querySelectorAll('#reader .pair.voiced')].map((pair) => {
  const tr = pair.querySelector('.tr');
  const src = [...pair.querySelectorAll('.src')]
    .find((c) => getComputedStyle(c).display !== 'none');
  const seen = (el) => !!el && getComputedStyle(el).display !== 'none'
    && getComputedStyle(el).visibility !== 'hidden' && el.getClientRects().length > 0;
  return {
    id: pair.getAttribute('data-id'),
    tr: !!tr,
    told: seen(tr),
    text: tr ? tr.textContent.trim() : '',
    src: seen(src),
    classes: pair.className,
  };
})
"""


def told(page) -> list[str]:
    return [row["id"] for row in page.evaluate(TOLD) if row["told"]]


def press(page, n: int) -> None:
    """The line's own ▶, the way a reader reaches it: on hover at a desk, always on a phone."""
    page.locator(f'#reader .say[data-id="{line(n)}"]').click()


def at(page) -> float:
    return page.evaluate("() => window.TargumPlayer.at()")


def playing(page) -> bool:
    return page.evaluate("() => !!document.querySelector('.say.saying')")


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("TARGUM_DIALOGUE_DIR", str(tmp_path / "dialogues"))
    return tmp_path / "dialogues"


# -- 1, 2, 3: on its own, ▶ tells one line, and it stays until it goes -------------------


@pytest.mark.parametrize(
    ("viewport", "language"), [(WIDE, "en"), (PHONE, "ru")], ids=["1440-en", "390-ru"]
)
def test_on_its_own_a_lines_play_opens_its_translation(
    browser, home, tmp_path, viewport, language
) -> None:
    """1-3. The audio plays from line 2's span and line 2's translation is shown, and no
    other; line 4's press moves it; it stays after the voice; Esc and a change of view
    put it away."""
    reader = recorded(home, tmp_path / "reader", language=language)
    context, page = opened(browser, reader, viewport)
    try:
        assert page.evaluate("() => document.body.classList.contains('mode-source')")
        assert told(page) == [], "the text on its own shows no translation at rest"
        press(page, 2)
        assert playing(page), "the line plays"
        assert abs(at(page) - 2 * SPAN) < 0.5, "from line 2's span"
        assert told(page) == [line(2)], "and its translation, and only its, is shown"
        row = next(r for r in page.evaluate(TOLD) if r["id"] == line(2))
        assert row["text"] == SAID[language].format(n=2), "the picker's translation"

        press(page, 4)
        assert told(page) == [line(4)], "one line at a time"
        page.wait_for_function(
            "() => !document.querySelector('.say.saying')", timeout=int(SPAN * 2500)
        )
        assert told(page) == [line(4)], "it stays after the voice so it can be read"
        page.keyboard.press("Escape")
        assert told(page) == [], "Esc puts it away"

        press(page, 1)
        assert told(page) == [line(1)]
        page.keyboard.press("p")
        page.keyboard.press("o")
        assert told(page) == [], "a change of view leaves no line told"
        assert spent(page) == []
    finally:
        context.close()


def test_pressing_the_same_line_again_stops_it_and_the_translation_stays(
    browser, home, tmp_path
) -> None:
    """The second press stops the voice as it always has; the translation is still there
    to read, and the next press says the line again."""
    reader = recorded(home, tmp_path / "reader")
    context, page = opened(browser, reader)
    try:
        press(page, 1)
        assert playing(page)
        press(page, 1)
        assert not playing(page), "pressed again, it stops"
        assert told(page) == [line(1)], "and the translation stays"
        press(page, 1)
        assert playing(page) and told(page) == [line(1)]
        assert "replay" in page.evaluate("() => window.__noted")
    finally:
        context.close()


# -- 4: Beside and Under are unchanged ----------------------------------------------------


@pytest.mark.parametrize("mode", ["p", "l"], ids=["beside", "under"])
def test_beside_and_under_are_unchanged(browser, home, tmp_path, mode) -> None:
    """4. The translation is already there, so a press changes nothing but `.saying`."""
    reader = recorded(home, tmp_path / "reader")
    context, page = opened(browser, reader)
    try:
        page.keyboard.press(mode)
        before = page.evaluate(TOLD)
        press(page, 2)
        after = page.evaluate(TOLD)
        assert [r["told"] for r in after] == [r["told"] for r in before]
        assert all(r["told"] for r in after), "every translation is on show, as before"
        assert [r["classes"] for r in after] == [r["classes"] for r in before]
        name = page.get_attribute(f'.say[data-id="{line(2)}"]', "aria-label")
        assert name == "Play this line", "and the ▶ keeps its name"
    finally:
        context.close()


# -- 5: Hear first holds the translation back with the line ------------------------------


def test_hear_first_holds_the_translation_back_with_the_line(browser, home, tmp_path) -> None:
    """5. Hearing before seeing: neither the line nor its translation while it plays, and
    both once it ends."""
    reader = recorded(home, tmp_path / "reader", span=1.0)
    context, page = opened(browser, reader)
    try:
        page.click(".player-first")
        press(page, 2)
        row = next(r for r in page.evaluate(TOLD) if r["id"] == line(2))
        assert row["src"] is False, "the line is held back"
        assert row["told"] is False, "and its translation with it"
        page.wait_for_function("() => !document.querySelector('.say.saying')", timeout=3000)
        row = next(r for r in page.evaluate(TOLD) if r["id"] == line(2))
        assert row["src"] is True and row["told"] is True, "both come back when it ends"
    finally:
        context.close()


# -- 6: Step line by line steps lines ------------------------------------------------------


@pytest.mark.parametrize(
    ("viewport", "language", "names"),
    [
        (WIDE, "en", ("Line before", "Next line")),
        (PHONE, "ru", ("Строка назад", "Строка вперёд")),
    ],
    ids=["1440-en", "390-ru"],
)
def test_step_line_by_line_steps_lines_and_plays_them(
    browser, home, tmp_path, viewport, language, names
) -> None:
    """6. ⋯'s › goes to the next line's start and plays it, and in the text on its own
    tells it; ‹ from the middle of a line goes to its top. Named for what they do."""
    reader = recorded(home, tmp_path / "reader", language=language)
    context, page = opened(browser, reader, viewport)
    try:
        assert page.get_attribute(".more-back", "aria-label") == names[0]
        assert page.get_attribute(".more-on", "aria-label") == names[1]
        press(page, 1)
        press_in_more(page, ".more-on")
        assert abs(at(page) - 2 * SPAN) < 0.3, "at the next line's start"
        assert playing(page), "and playing it"
        assert told(page) == [line(2)], "told, in the text on its own"
        page.wait_for_function(f"() => window.TargumPlayer.at() > {2 * SPAN + 1.6}")
        page.click(".more-back")
        assert abs(at(page) - 2 * SPAN) < 0.3, "back from the middle is the top of the line"
        assert playing(page)
        page.click(".more-back")
        assert abs(at(page) - 1 * SPAN) < 0.3, "and again, the line before"
        assert told(page) == [line(1)]
        assert spent(page) == []
    finally:
        context.close()


def test_the_strips_step_is_still_a_word_or_five_seconds(browser, home, tmp_path) -> None:
    """6, the other half: the strip keeps its own step and its own labels."""
    reader = recorded(home, tmp_path / "reader")
    context, page = opened(browser, reader)
    try:
        assert page.get_attribute(".player-on", "aria-label") == "Forward five seconds"
        assert page.get_attribute(".player-back", "aria-label") == "Back five seconds"
        page.click(".player-on")
        assert abs(at(page) - 5.0) < 0.1, "five seconds, not a line"
        assert told(page) == []
    finally:
        context.close()


# -- 7: the key h ---------------------------------------------------------------------------


def test_h_hears_the_line_you_are_on(browser, home, tmp_path) -> None:
    """7. Walk to a word on line 3 (← is forward in Hebrew), press h: line 3 plays and is
    told; again replays it."""
    reader = recorded(home, tmp_path / "reader")
    context, page = opened(browser, reader)
    try:
        for _ in range(40):
            # Forward on a Hebrew page is ←.
            page.keyboard.press("ArrowLeft")
            on = page.evaluate(
                "() => document.activeElement?.closest?.('.pair')?.getAttribute('data-id')"
            )
            if on == line(3):
                break
        assert on == line(3), "the walk reached line 3"
        page.keyboard.press("h")
        assert playing(page)
        assert abs(at(page) - 3 * SPAN) < 0.5
        assert told(page) == [line(3)]
        page.keyboard.press("h")
        assert playing(page), "again, it is said again, not stopped"
        assert "replay" in page.evaluate("() => window.__noted")
        assert spent(page) == []
    finally:
        context.close()


def test_h_with_nothing_walked_hears_the_line_last_said(browser, home, tmp_path) -> None:
    reader = recorded(home, tmp_path / "reader")
    context, page = opened(browser, reader)
    try:
        press(page, 4)
        page.keyboard.press("Escape")
        page.keyboard.press("h")
        assert playing(page) and abs(at(page) - 4 * SPAN) < 0.5
        assert told(page) == [line(4)]
    finally:
        context.close()


def test_h_in_a_field_is_a_letter(browser, home, tmp_path) -> None:
    reader = recorded(home, tmp_path / "reader")
    context, page = opened(browser, reader)
    try:
        page.evaluate(
            "() => { const i = document.createElement('input'); i.id = 'typed';"
            " document.body.appendChild(i); i.focus(); }"
        )
        page.keyboard.press("h")
        assert not playing(page)
        assert told(page) == []
    finally:
        context.close()


# -- 8: no translation, no tell ------------------------------------------------------------


def test_a_text_with_no_translation_only_plays(browser, home, tmp_path) -> None:
    """8. ▶ plays, and no translation appears, because there is none to show."""
    reader = recorded(home, tmp_path / "reader", translated=False)
    context, page = opened(browser, reader)
    try:
        press(page, 2)
        assert playing(page)
        assert page.locator("#reader .tr").count() == 0
        assert page.get_attribute(f'.say[data-id="{line(2)}"]', "aria-label") == "Play this line"
    finally:
        context.close()


# -- 9, 10: the told line stays in front of the reader, with nothing over it ---------------


#: The told translation's box, and every control at the foot that could stand over it.
SEEN = """
() => {
  const pair = document.querySelector('#reader .pair.told');
  const tr = pair && pair.querySelector('.tr');
  const box = (el) => {
    if (!el || el.hidden || !el.getClientRects().length) return null;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return null;
    return { top: r.top, bottom: r.bottom, left: r.left, right: r.right };
  };
  const over = {};
  for (const s of ['#player', '#turn .back', '#turn .forward', '#page-of', '#list-tab', '.bar']) {
    const b = box(document.querySelector(s));
    if (b) over[s] = b;
  }
  return { pair: pair ? !pair.hidden : null, tr: box(tr), over, height: innerHeight };
}
"""


def clear(seen: dict) -> list[str]:
    tr = seen["tr"]
    hits = []
    for name, c in seen["over"].items():
        x = min(tr["right"], c["right"]) - max(tr["left"], c["left"])
        y = min(tr["bottom"], c["bottom"]) - max(tr["top"], c["top"])
        if x > 1 and y > 2:
            hits.append(name)
    return hits


@pytest.mark.parametrize("viewport", [WIDE, PHONE], ids=["1440", "390"])
def test_on_pages_the_told_line_stays_on_the_page(browser, home, tmp_path, viewport) -> None:
    """9, 10. Pages on, the last line of a page told: its translation does not fit, the page
    is laid out again, and the line and its translation are on the page in front of the
    reader, with nothing at the foot over them."""
    reader = recorded(home, tmp_path / "reader", turns=24, long=True)
    context, page = opened(browser, reader, viewport, paged=True)
    try:
        page.wait_for_function("() => document.body.classList.contains('paged')")
        last = page.evaluate(
            "() => { const shown = [...document.querySelectorAll('#reader .pair.voiced')]"
            ".filter((p) => !p.hidden); return shown[shown.length - 1].getAttribute('data-id'); }"
        )
        page.locator(f'#reader .say[data-id="{last}"]').click()
        page.wait_for_timeout(300)
        seen = page.evaluate(SEEN)
        assert seen["pair"] is True, "the told line is on the page showing"
        assert seen["tr"], "and so is its translation"
        assert seen["tr"]["bottom"] <= seen["height"], "inside the window"
        assert clear(seen) == [], f"nothing stands over it: {seen}"
    finally:
        context.close()


def test_on_a_phone_scroll_nothing_covers_the_told_translation(browser, home, tmp_path) -> None:
    """10. In the long scroll at 390 with the strip up, the translation opened under a line
    near the foot is brought clear of the strip."""
    reader = recorded(home, tmp_path / "reader", turns=24, long=True)
    context, page = opened(browser, reader, PHONE)
    try:
        # The line nearest the strip's top edge, with its translation still to open.
        n = page.evaluate(
            """() => {
              const seat = document.getElementById('player').getBoundingClientRect().top;
              const rows = [...document.querySelectorAll('#reader .pair.voiced')];
              let best = 0;
              rows.forEach((p, i) => { if (p.getBoundingClientRect().bottom < seat) best = i; });
              return best;
            }"""
        )
        press(page, n)
        page.wait_for_timeout(300)
        seen = page.evaluate(SEEN)
        assert seen["tr"], "the translation is open"
        assert clear(seen) == [], f"nothing stands over it: {seen}"
    finally:
        context.close()


# -- 11: it spends nothing, and works offline -----------------------------------------------


def test_a_saved_copy_offline_tells_and_steps(browser, home, tmp_path) -> None:
    """11. Opened from disk with no connection: ▶ tells, and ⋯'s step plays the next line.
    Nothing the page asked for went to a door that spends."""
    reader = recorded(home, tmp_path / "reader")
    context, page = opened(browser, reader, offline=True)
    try:
        press(page, 1)
        assert playing(page) and told(page) == [line(1)]
        press_in_more(page, ".more-on")
        assert playing(page) and abs(at(page) - 2 * SPAN) < 0.3
        assert told(page) == [line(2)]
        assert spent(page) == []
    finally:
        context.close()


# -- 12, 13: a silent text is unchanged; the strings and the Keys card ----------------------


def test_a_silent_text_draws_no_play_and_no_h(home, tmp_path) -> None:
    """12, 13. A recorded text's Keys card lists `h`, and its Esc line names a line's
    translation; a text with no recording draws no ▶ and lists no `h`."""
    html = recorded(home, tmp_path / "reader").read_text(encoding="utf-8")
    assert "<dt>h</dt>" in html
    assert "then a line's translation" in html
    quiet = recorded(home, tmp_path / "quiet", silent=True)
    html = quiet.read_text(encoding="utf-8")
    assert 'class="say"' not in html
    assert "<dt>h</dt>" not in html


def test_the_new_words_are_said_in_english_and_russian() -> None:
    """13. Every new key is in both catalogues, in the words the spec gives."""
    from targum.strings import catalogue

    en, ru = catalogue("en"), catalogue("ru")
    assert en["reader.page.play-this-line-told"] == "Play this line and show its translation"
    assert en["reader.page.line-before"] == "Line before"
    assert en["reader.page.line-after"] == "Next line"
    assert en["reader.page.key-h"].startswith("the line you're on")
    assert "then a line's translation" in en["reader.page.close-this-then-a-word-then-your"]
    for key in (
        "reader.page.play-this-line-told",
        "reader.page.line-before",
        "reader.page.line-after",
        "reader.page.key-h",
    ):
        assert ru.get(key), f"ru has no word for {key}"
    assert ru["reader.page.line-before"] == "Строка назад"
    assert ru["reader.page.line-after"] == "Строка вперёд"
    assert "перевод строки" in ru["reader.page.close-this-then-a-word-then-your"]


# -- 14: what a screen reader is told -------------------------------------------------------


@pytest.mark.parametrize(
    ("language", "name"),
    [
        ("en", "Play this line and show its translation"),
        ("ru", "Прослушать строку и показать перевод"),
    ],
    ids=["en", "ru"],
)
def test_the_play_says_it_shows_the_translation_and_points_at_it(
    browser, home, tmp_path, language, name
) -> None:
    """14. In the text on its own the ▶ is named for both things it does, and while its
    line is told it is described by that line's translation."""
    reader = recorded(home, tmp_path / "reader", language=language)
    context, page = opened(browser, reader)
    try:
        say = f'.say[data-id="{line(2)}"]'
        assert page.get_attribute(say, "aria-label") == name
        press(page, 2)
        described = page.get_attribute(say, "aria-describedby")
        assert described, "described while told"
        assert page.evaluate(
            "(id) => document.getElementById(id)?.closest('.pair')?.getAttribute('data-id')",
            described,
        ) == line(2)
        page.keyboard.press("Escape")
        assert page.get_attribute(say, "aria-describedby") is None
        page.keyboard.press("p")
        assert page.get_attribute(say, "aria-label") == (
            "Play this line" if language == "en" else "Проиграть эту строку"
        )
    finally:
        context.close()
