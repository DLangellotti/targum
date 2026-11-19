"""The line for a hard spot on a Hebrew word card, in a real browser (targum-internal#438).

Each of Hebrew's seven hard spots says one line under the card's facts, filled with the
tapped word's own letters, and only where the build already worked the fact out. A word
outside every spot says nothing, and a spot whose fact does not hold on a page (a
Biblical participle, a number speech does not change) says nothing there. The tokens here
are made by hand with the grammar DICTA or Open Scriptures would give them.

Skips itself unless Playwright and its Chromium are installed, as
`test_reader_browser.py` does, whose browser this borrows.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import test_reader_browser
from test_reader_browser import PHONE, hebrew_governed, open_reader

from targum import strings
from targum.models import (
    Annotation,
    Block,
    BlockKind,
    Document,
    Segment,
    SegmentedDocument,
    Syntax,
    Token,
    Translation,
)
from targum.render import render

browser = test_reader_browser.browser

#: What the nth word's card says under its facts: the spot's line, or None for no line.
SPOT = """
(n) => {
  document.querySelectorAll('.pair:not([hidden]) .src .w')[n].click();
  const line = document.querySelector('#gloss-card .card-spot');
  return line ? line.textContent : null;
}
"""

#: The words of a page's one line, and what each carries beyond its surface and lemma.
Said = list[tuple[str, str, str | None, str | None, dict[str, Any]]]


def _page(out: Path, said: Said, source: str = "memory") -> Path:
    """One line of Hebrew built into a reader, the offsets found in the text as written."""
    text = " ".join(surface for surface, *_ in said)
    biblical = source.startswith("sefaria:")
    kind = BlockKind.verse if biblical else BlockKind.paragraph
    segment = Segment(
        id="0000.000-aaaaaa",
        block_id="b0",
        block_index=0,
        index=0,
        kind=kind,
        text=text,
        **({"ref": "Genesis 1:1"} if biblical else {}),
    )
    tokens, cursor = [], 0
    for surface, lemma, pos, feats, more in said:
        start = text.index(surface, cursor)
        cursor = start + len(surface)
        tokens.append(
            Token(
                start=start,
                end=cursor,
                surface=surface,
                lemma=lemma,
                band=1,
                pos=pos,
                feats=feats,
                **more,
            )
        )
    document = Document(
        source=source,
        title="עיר",
        language="he",
        blocks=[Block(id="b0", kind=kind, text=text)],
        content_hash="s",
    )
    translation = Translation(
        name="English",
        document_hash="s",
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "A line made for the test."},
    )
    annotation = Annotation(
        document_hash="s",
        language="he",
        annotator="test/1",
        method="frequency",
        method_note="a test",
        tokens={segment.id: tokens},
    )
    out.mkdir(parents=True, exist_ok=True)
    segmented = SegmentedDocument(
        document_hash="s", language="he", segmenter="test/1", segments=[segment]
    )
    return render(document, segmented, [translation], out, annotation=annotation)[0]


#: A modern line with a word for each spot the card says from grammar or a reading, and
#: words in none: מנהל, אחד (a number speech does not change), and ספר, whose stress
#: before the end was guessed.
MODERN: Said = [
    ("העיר", "עיר", "NOUN", "UPOS=NOUN|Gender=Fem|Number=Sing", {}),
    ("כותבת", "כתב", "VERB", "UPOS=VERB|Gender=Fem|Number=Sing|Tense=Pres", {}),
    ("שלושה", "שלושה", "NUM", "UPOS=NUM|Gender=Masc|Number=Sing", {}),
    ("בית", "בית", "NOUN", "UPOS=NOUN|Gender=Masc|Number=Sing", {}),
    ("שיעורי", "שיעור", "NOUN", "UPOS=NOUN|Gender=Masc|Number=Plur|Definite=Cons", {}),
    (
        "למד",
        "למד",
        "VERB",
        "UPOS=VERB|Gender=Masc|Number=Sing|Person=3|Tense=Past",
        {"binyan": "פעל", "root": "למד"},
    ),
    ("מנהל", "מנהל", "NOUN", "UPOS=NOUN|Gender=Masc|Number=Sing", {}),
    ("שנים", "שנה", "NOUN", "UPOS=NOUN|Gender=Fem|Number=Plur", {}),
    ("מקומות", "מקום", "NOUN", "UPOS=NOUN|Gender=Masc|Number=Plur", {}),
    ("שלוש", "שלושה", "NUM", "UPOS=NUM|Gender=Fem|Number=Sing", {}),
    ("אחד", "אחד", "NUM", "UPOS=NUM|Gender=Masc|Number=Sing", {}),
    ("מֶ֫לֶךְ", "מלך", "NOUN", "UPOS=NOUN|Gender=Masc|Number=Sing", {"ipa": "ˈmeleχ"}),
    ("ספר", "ספר", "NOUN", "UPOS=NOUN|Gender=Masc|Number=Sing", {"ipa": "ˈsefer"}),
]


def _said(key: str, **fill: str) -> str:
    return strings.text(key, "en", **fill)


def _lines(page: Any, count: int) -> list[str | None]:
    page.wait_for_function("() => !!window.targumReaderRest")
    return [page.evaluate(SPOT, n) for n in range(count)]


def test_each_spot_says_its_line_with_the_words_own_letters(browser, tmp_path: Path) -> None:
    context, page = open_reader(browser, _page(tmp_path / "reader", MODERN))
    lines = _lines(page, len(MODERN))
    context.close()
    assert lines == [
        _said(
            "reader.card.spot.he.agreement-fem",
            word="עיר",
            he="ה",
            tav="ת",
            adjective="גדולה",
        ),
        _said("reader.card.spot.he.tense", one="אני", other="היא"),
        _said("reader.card.spot.he.agreement-number-m"),
        _said("reader.card.spot.he.agreement-masc", word="בית", letter="ת", adjective="גדול"),
        _said("reader.card.spot.he.construct", word="שיעור", he="ה"),
        _said("reader.card.spot.he.binyan", root="ל־מ־ד", binyan="פָּעַל"),
        None,
        _said("reader.card.spot.he.agreement-fem-plural", ending="ים"),
        _said("reader.card.spot.he.agreement-masc-plural", ending="ות"),
        _said("reader.card.spot.he.agreement-number-f"),
        # One: speech says it as writing does.
        None,
        # Its stress placed by the text's own mark, before the last syllable.
        _said("reader.card.spot.he.stress", reading="mé-lekh"),
        # The same stress, guessed: nothing is claimed.
        None,
    ]


def test_a_phones_sheet_carries_the_line_too(browser, tmp_path: Path) -> None:
    context, page = open_reader(browser, _page(tmp_path / "reader", MODERN), viewport=PHONE)
    page.wait_for_function("() => !!window.targumReaderRest")
    said = page.evaluate(SPOT, 0)
    shown = page.evaluate(
        """() => {
          const line = document.querySelector('#gloss-card .card-spot');
          const box = line.getBoundingClientRect();
          const card = document.getElementById('gloss-card').getBoundingClientRect();
          return box.height > 0 && box.left >= card.left - 1 && box.right <= card.right + 1;
        }"""
    )
    context.close()
    assert said and said.startswith("עיר is feminine"), said
    assert shown


def test_on_a_biblical_page_the_present_and_the_number_say_nothing(browser, tmp_path: Path) -> None:
    """A Biblical participle is as often a past going on, and the speech a number line
    describes is modern speech. A spelling the Bible's vowels tell apart says so; a word
    with no headword of its own says nothing."""
    said: Said = [
        ("כותבת", "כתב", "VERB", "UPOS=VERB|Gender=Fem|Number=Sing|Tense=Pres", {}),
        ("שלושה", "שלושה", "NUM", "UPOS=NUM|Gender=Masc|Number=Sing", {}),
        ("אֵלֶּה", "אלה", "PRON", "UPOS=PRON", {"headword": "אֵלֶּה"}),
        ("אור", "אור", "NOUN", "UPOS=NOUN|Gender=Masc|Number=Sing", {}),
    ]
    context, page = open_reader(
        browser, _page(tmp_path / "reader", said, source="sefaria:Genesis 1")
    )
    lines = _lines(page, len(said))
    context.close()
    assert lines == [
        None,
        None,
        _said("reader.card.spot.he.homograph", bare="אלה", pointed="אֵלֶּה"),
        None,
    ]


def test_a_verb_says_the_preposition_it_takes_and_its_argument_says_nothing(
    browser, tmp_path: Path
) -> None:
    context, page = open_reader(browser, hebrew_governed(tmp_path / "reader"))
    lines = _lines(page, 3)
    context.close()
    assert lines[0] == _said("reader.card.spot.he.governed", verb="דיבר", preposition="עם")
    assert lines[2] is None


def test_a_verb_with_et_says_what_et_does(browser, tmp_path: Path) -> None:
    said: Said = [
        (
            "ראה",
            "ראה",
            "VERB",
            "UPOS=VERB|Tense=Past",
            {"syntax": Syntax(head=-1, relation="root")},
        ),
        ("את", "את", "ADP", "UPOS=ADP", {"syntax": Syntax(head=2, relation="case")}),
        (
            "הילד",
            "ילד",
            "NOUN",
            "UPOS=NOUN|Gender=Masc",
            {"syntax": Syntax(head=0, relation="obj", prefixes=("DET",), lead=1)},
        ),
    ]
    context, page = open_reader(browser, _page(tmp_path / "reader", said))
    line = _lines(page, 1)[0]
    context.close()
    assert line == _said("reader.card.spot.he.governed-et", verb="ראה", et="את")
