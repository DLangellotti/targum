"""A verse with a ketiv and its qere, marked on the page: every box stands on one word.

Sefaria writes a word the Masoretes read differently as `ketiv [qere]`. The scripture
annotator measured its offsets against the verse with the ketiv cut out, so on the page
every word after one was marked its length too early, and Bereshit 25:23 showed boxes
running from the middle of one word into the middle of the next — "ךְ וּשְׁנֵ֣" for
`לאם` (David, 2026-11-08). The reader drew exactly what it was given; this goes from the
tagging through the render to the drawn page, so it fails wherever the chain breaks.

"Whole word" here includes its marks: the character after a box is never a vowel point
or an accent, so nothing that belongs to the word is left outside it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytest.importorskip("playwright.sync_api")

from test_reader_browser import address, browser, settled  # noqa: E402, F401
from test_scripture import FIXTURES, KETIV_QERE  # noqa: E402

QAMATS = "ָ"
ACCENT = "֙"  # pashta, above
TIPCHA = "֖"  # below


def pointed(text: str) -> str:
    """The verse with a vowel and an accent on every letter, the way a printed Tanakh
    stacks them: the same letters, so every offset maps, and marks both above and
    below for a box to leave out."""
    return re.sub(r"([א-ת])", lambda found: found.group(1) + QAMATS + TIPCHA + ACCENT, text)


@pytest.fixture
def verse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from targum.annotate import oshb
    from targum.annotate.scripture import ScriptureLemmatizer
    from targum.models import (
        Annotation,
        Document,
        Segment,
        SegmentedDocument,
        Translation,
        Vocalization,
    )
    from targum.render import render

    monkeypatch.setenv("TARGUM_MODEL_DIR", str(tmp_path / "models"))
    oshb.forget()
    home = tmp_path / "models" / "oshb"
    home.mkdir(parents=True)
    verses = oshb.parse((FIXTURES / "Gen.xml").read_text(encoding="utf-8"))
    (home / "Gen.json").write_text(json.dumps(verses, ensure_ascii=False), encoding="utf-8")
    (home / oshb.LEXICON_FILE).write_text("{}", encoding="utf-8")

    segment = Segment(
        id="0001.000-aaaaaa",
        block_id="b0001",
        block_index=1,
        index=0,
        text=KETIV_QERE,
        ref="Genesis 8:17",
    )

    class Model:
        name = "none/1"

        def lemmas(self, segments, language):  # type: ignore[no-untyped-def]
            raise AssertionError("the verse lines up with the tagging")

    tokens = ScriptureLemmatizer(Model()).lemmas([segment], "he")
    oshb.forget()
    folder = tmp_path / "out"
    return render(
        Document(source="g.txt", title="A verse", language="he", blocks=[], content_hash="h"),
        SegmentedDocument(document_hash="h", language="he", segmenter="fake/1", segments=[segment]),
        [
            Translation(
                name="English",
                document_hash="h",
                source_language="he",
                target_language="en",
                provider="null",
                segments={segment.id: "Bring out every living thing that is with you."},
            )
        ],
        folder / "reader",
        annotation=Annotation(
            document_hash="h",
            language="he",
            annotator="oshb/9+none/1",
            method="frequency",
            method_note="a test",
            tokens=tokens,
        ),
        vocalization=Vocalization(
            document_hash="h",
            language="he",
            vocalizer="test/1",
            segments={segment.id: pointed(KETIV_QERE)},
        ),
        folder=folder,
    )[0]


DRAWN = """() => {
  const cell = [...document.querySelectorAll('.pair .src')].find(
    (c) => !c.hidden && c.offsetParent !== null && c.querySelector('.w'));
  const text = cell.textContent;
  const out = [];
  let at = 0;
  for (const node of cell.childNodes) {
    const length = node.textContent.length;
    if (node.nodeType === 1 && node.classList.contains('w')) {
      out.push({ word: node.textContent, before: text.slice(at - 1, at),
                 after: text.slice(at + length, at + length + 1) });
    }
    at += length;
  }
  return { form: cell.getAttribute('data-form'), words: out };
}"""


def test_every_box_in_a_ketiv_verse_is_one_whole_word(browser, verse: Path) -> None:  # noqa: F811
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    context.add_init_script(
        "localStorage.setItem('targum:prefs', JSON.stringify("
        "{nikkud: true, marking: true, paged: false, defaults: 4}))"
    )
    page = context.new_page()
    try:
        page.goto(address(verse))
        page.wait_for_selector(".pair .src .w")
        settled(page)
        drawn = page.evaluate(DRAWN)
    finally:
        context.close()

    assert drawn["form"] != "plain", "the pointed verse is the one on show"
    # The points and accents the reader counts as marks (`MARK` in reader.js): not the
    # maqaf, the paseq or the sof pasuq, which stand between words.
    marks = re.compile("[֑-ׇֽֿׁׂׅׄ]")
    written = set(re.split(r"[\s־\[\]׃]+", KETIV_QERE))
    boxed = []
    for one in drawn["words"]:
        bare = marks.sub("", one["word"])
        assert bare in written, f"{one['word']!r} is not one word of the verse"
        # Nothing of the word outside its box: no letter on either side, and no point
        # or accent after it.
        assert not re.match(r"[א-ת]", one["after"] or " "), one
        assert not marks.match(one["after"] or " "), one
        assert not re.match(r"[א-ת]", one["before"] or " "), one
        boxed.append(bare)
    assert "היצא" in boxed and "הוצא" not in boxed, "the qere carries the word"
    assert boxed[-7:] == ["אתך", "ושרצו", "בארץ", "ופרו", "ורבו", "על", "הארץ"]
