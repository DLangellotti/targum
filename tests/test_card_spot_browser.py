"""The line for a hard spot on a Hebrew word card, in a real browser (targum-internal#438).

Each of Hebrew's seven hard spots says one line under the card's facts, filled with the
tapped word's own letters, and only where the build already worked the fact out. A word
outside every spot says nothing. The tokens here are made by hand with the grammar DICTA
would give them.

Skips itself unless Playwright and its Chromium are installed, as
`test_reader_browser.py` does, whose browser this borrows.
"""

from __future__ import annotations

from pathlib import Path

import test_reader_browser
from test_reader_browser import hebrew_governed, open_reader

from targum import strings
from targum.models import (
    Annotation,
    Document,
    Segment,
    SegmentedDocument,
    Token,
    Translation,
)
from targum.render import render

browser = test_reader_browser.browser

#: What each word's card says under its facts: the spot's line, or None for no line.
SPOT = """
(text) => {
  const word = [...document.querySelectorAll('.pair:not([hidden]) .src .w')]
    .find((w) => w.textContent === text);
  word.click();
  const line = document.querySelector('#gloss-card .card-spot');
  return line ? line.textContent : null;
}
"""


def _reader(out: Path) -> Path:
    """A modern Hebrew line with one word for each spot the card can say from grammar
    alone, and a word in none of them."""
    text = "העיר כותבת שלושה בית שיעורי למד מנהל"
    said = [
        ("העיר", "עיר", "NOUN", "UPOS=NOUN|Gender=Fem|Number=Sing", None),
        ("כותבת", "כתב", "VERB", "UPOS=VERB|Gender=Fem|Number=Sing|Tense=Pres", None),
        ("שלושה", "שלושה", "NUM", "UPOS=NUM|Gender=Masc|Number=Sing", None),
        ("בית", "בית", "NOUN", "UPOS=NOUN|Gender=Masc|Number=Sing", None),
        ("שיעורי", "שיעור", "NOUN", "UPOS=NOUN|Gender=Masc|Number=Plur|Definite=Cons", None),
        ("למד", "למד", "VERB", "UPOS=VERB|Gender=Masc|Number=Sing|Person=3|Tense=Past", "פעל"),
        ("מנהל", "מנהל", "NOUN", "UPOS=NOUN|Gender=Masc|Number=Sing", None),
    ]
    segment = Segment(id="0000.000-aaaaaa", block_id="b0", block_index=0, index=0, text=text)
    tokens, cursor = [], 0
    for surface, lemma, pos, feats, binyan in said:
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
                binyan=binyan,
                root="למד" if binyan else None,
            )
        )
    document = Document(source="memory", title="עיר", language="he", blocks=[], content_hash="s")
    translation = Translation(
        name="English",
        document_hash="s",
        source_language="he",
        target_language="en",
        provider="null",
        segments={segment.id: "The city writes three house lessons he learned manager."},
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


def _said(key: str, **fill: str) -> str:
    return strings.text(key, "en", **fill)


def test_each_spot_says_its_line_with_the_words_own_letters(browser, tmp_path: Path) -> None:
    context, page = open_reader(browser, _reader(tmp_path / "reader"))
    page.wait_for_function("() => !!window.targumReaderRest")
    lines = {word: page.evaluate(SPOT, word) for word in ("העיר", "כותבת", "שלושה", "בית")}
    lines.update({word: page.evaluate(SPOT, word) for word in ("שיעורי", "למד", "מנהל")})
    context.close()
    assert lines["העיר"] == _said(
        "reader.card.spot.he.agreement-fem",
        word="עיר",
        he="ה",
        tav="ת",
        adjective="גדולה",
    )
    assert lines["כותבת"] == _said("reader.card.spot.he.tense", one="אני", other="היא")
    assert lines["שלושה"] == _said("reader.card.spot.he.agreement-number-m")
    assert lines["בית"] == _said(
        "reader.card.spot.he.agreement-masc", word="בית", letter="ת", adjective="גדול"
    )
    assert lines["שיעורי"] == _said("reader.card.spot.he.construct", word="שיעור", he="ה")
    assert lines["למד"] == _said("reader.card.spot.he.binyan", root="ל־מ־ד", binyan="פָּעַל")
    # A masculine noun with a masculine ending is in no spot, and says nothing.
    assert lines["מנהל"] is None


def test_a_verb_says_the_preposition_it_takes_and_its_argument_says_nothing(
    browser, tmp_path: Path
) -> None:
    context, page = open_reader(browser, hebrew_governed(tmp_path / "reader"))
    page.wait_for_function("() => !!window.targumReaderRest")
    verb = page.evaluate(SPOT, "דיבר")
    noun = page.evaluate(SPOT, "המנהל")
    context.close()
    assert verb == _said("reader.card.spot.he.governed", verb="דיבר", preposition="עם")
    assert noun is None
