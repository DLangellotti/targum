"""The reader's edition on paper (targum-internal#105)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from targum.errors import TargumError
from targum.models import (
    Annotation,
    BlockKind,
    Document,
    Glossary,
    Segment,
    SegmentedDocument,
    Token,
    Translation,
    Vocalization,
)
from targum.render.printed import first_sense, print_html
from targum.vocalize import has_taamim, strip_nikkud

# Jonah 1:1–2, as the edition writes it: vowels and te'amim.
VERSE_1 = "וַֽיְהִי֙ דְּבַר־יְהוָ֔ה אֶל־יוֹנָ֥ה"
VERSE_2 = "ק֠וּם לֵ֧ךְ אֶל־נִֽינְוֵ֛ה"
# A modern text, pointed by a model, and no te'amim anywhere.
LINE_1 = "שָׁלוֹם רָב שׁוּבֵךְ"
LINE_2 = "צִפֹּרָה נֶחְמֶדֶת"


def _segment(index: int, text: str, kind: BlockKind, ref: str = "") -> Segment:
    return Segment(
        id=f"{index:04d}.000-aaaaaa",
        block_id=f"b{index:04d}",
        block_index=index,
        index=0,
        kind=kind,
        level=2 if kind is BlockKind.heading else None,
        text=text,
        ref=ref,
    )


def _token(lemma: str, band: int, pos: str = "NOUN", headword: str | None = None) -> Token:
    return Token(start=0, end=1, surface=lemma, lemma=lemma, band=band, pos=pos, headword=headword)


def _folder(tmp_path: Path, rows: list[tuple[str, str, BlockKind, str]], scripture: bool) -> Path:
    """A built targum as the disk holds it: every artifact a rebuild reads, and no reader."""
    folder = tmp_path / ("jonah-he" if scripture else "bird-he")
    (folder / "translations").mkdir(parents=True)
    segments = [_segment(i, text, kind, ref) for i, (text, _, kind, ref) in enumerate(rows)]
    Document(
        source="sefaria:Jonah" if scripture else "https://example.org/bird",
        title="יונה" if scripture else "אל הציפור",
        language="he",
    ).write(folder / "document.json")
    SegmentedDocument(
        document_hash="h", language="he", segmenter="fake/1", segments=segments
    ).write(folder / "segments.json")
    Translation(
        name="fixture",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="fake",
        segments={s.id: english for s, (_, english, _, _) in zip(segments, rows, strict=True)},
    ).write(folder / "translations" / "fake.natural.en.json")
    Vocalization(
        document_hash="h",
        language="he",
        vocalizer="source" if scripture else "fake/1",
        segments={s.id: s.text for s in segments if s.kind is not BlockKind.heading},
        machine=[] if scripture else [s.id for s in segments],
    ).write(folder / "vocalization.json")
    body = [s.id for s in segments if s.kind is not BlockKind.heading]
    Annotation(
        document_hash="h",
        language="he",
        annotator="fake/1",
        method="frequency",
        method_note="",
        tokens={
            body[0]: [
                _token("היה", 1, pos="VERB"),
                _token("דבר", 5, headword="דָּבָר"),
                _token("יונה", 6, pos="PROPN"),
            ],
            body[1]: [_token("קום", 5, pos="VERB"), _token("דבר", 5, headword="דָּבָר")],
        },
    ).write(folder / "annotation.json")
    Glossary(
        source_language="he",
        target_language="en",
        provider="fake",
        entries={
            "דָּבָר": "word; by implication a matter spoken of",
            "קום (verb)": "to rise",
            "היה (verb)": "to be",
            "יונה": "Jonah",
        },
        citations={"קום (verb)": "לָקוּם"},
    ).write(folder / "glossary.en.json")
    return folder


@pytest.fixture
def jonah(tmp_path: Path) -> Path:
    return _folder(
        tmp_path,
        [
            ("יונה א׳", "Jonah 1", BlockKind.heading, ""),
            (VERSE_1, "Now the word of the LORD came unto Jonah", BlockKind.verse, "Jonah 1:1"),
            (VERSE_2, "Arise, go to Nineveh", BlockKind.verse, "Jonah 1:2"),
        ],
        scripture=True,
    )


@pytest.fixture
def bird(tmp_path: Path) -> Path:
    return _folder(
        tmp_path,
        [
            ("אל הציפור", "To the Bird", BlockKind.heading, ""),
            (LINE_1, "Welcome back, lovely bird", BlockKind.paragraph, ""),
            (LINE_2, "from the warm lands", BlockKind.paragraph, ""),
        ],
        scripture=False,
    )


def _words(html: str) -> list[tuple[str, str]]:
    return re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", html, re.S)


def test_scripture_prints_with_its_teamim_by_default(jonah: Path) -> None:
    html = print_html(jonah)
    assert VERSE_1 in html and VERSE_2 in html
    # And in the face cut for them, carried in the page.
    assert '--reading-hebrew:"Taamey Frank CLM"' in html


def test_the_accents_and_the_vowels_come_off_when_asked(jonah: Path) -> None:
    without = print_html(jonah, accents=False)
    assert VERSE_1 not in without
    cells = re.findall(r'<p class="src"[^>]*>(?:<span[^>]*>\d+</span>)?(.*?)</p>', without)
    assert cells and not any(has_taamim(cell) for cell in cells)
    # The face stays the one the text needs, as the reader keeps it with its accents off.
    assert '--reading-hebrew:"Taamey Frank CLM"' in without
    bare = print_html(jonah, vowels=False)
    assert strip_nikkud(VERSE_1)[0] in bare and VERSE_1 not in bare


def test_the_translation_stands_beside_its_line_in_the_pages_direction(jonah: Path) -> None:
    html = print_html(jonah)
    assert '<html lang="en" dir="rtl">' in html
    pair = re.search(r'<div class="pair verse">(.*?)</div>', html, re.S)
    assert pair is not None
    # Source first, then the translation: the row follows the page, so the source leads.
    assert pair.group(1).index('class="src"') < pair.group(1).index('class="tr"')
    assert 'lang="en" dir="ltr">Now the word of the LORD' in pair.group(1)
    assert '<span class="verse-number">1</span>' in pair.group(1)
    assert 'class="beside verses"' in html
    assert 'class="under verses"' in print_html(jonah, under=True)


def test_the_word_list_is_the_hard_words_once_each_with_their_first_sense(jonah: Path) -> None:
    words = _words(print_html(jonah))
    # דבר twice in the text, once in the list; היה is an easy word and Jonah is a name.
    assert words == [("דָּבָר", "word"), ("לָקוּם", "to rise")]


def test_a_reader_gets_every_word_they_have_not_marked_known(jonah: Path) -> None:
    words = _words(print_html(jonah, known={"קום"}))
    assert words == [("היה", "to be"), ("דָּבָר", "word")]


def test_a_translation_the_text_has_not_is_refused_in_a_sentence(jonah: Path) -> None:
    with pytest.raises(TargumError, match="no translation into ru"):
        print_html(jonah, into="ru")


def test_a_modern_text_takes_the_modern_face(bird: Path) -> None:
    html = print_html(bird)
    assert '--reading-hebrew:"Noto Sans Hebrew"' in html
    assert LINE_1 in html


def test_the_page_fetches_nothing(jonah: Path) -> None:
    html = print_html(jonah)
    for position in (r'src\s*=\s*["\']', r"url\(", r'<link[^>]+href\s*=\s*["\']'):
        assert not re.search(position + r"(https?:)?//", html, re.I)


def test_first_sense() -> None:
    assert first_sense("wind; by resemblance breath") == "wind"
    assert first_sense("to rise") == "to rise"


def test_the_pdf_is_one_page_and_reads_in_order(bird: Path, tmp_path: Path) -> None:
    """Set for real, where this machine can: WeasyPrint and Pango are an extra, so a
    checkout without them skips this and still runs everything above."""
    from targum.render.printed import _find_pango, write_pdf

    _find_pango()
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        pytest.skip("WeasyPrint or Pango is not installed")
    pypdf = pytest.importorskip("pypdf")

    out = write_pdf(print_html(bird), tmp_path / "bird.pdf")
    reader = pypdf.PdfReader(out)
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    bare = strip_nikkud(text)[0]
    # Every line in the order it was written, the Hebrew in logical order rather than
    # drawn backwards, and the word list after the text.
    order = [
        "Welcome back, lovely bird",
        "from the warm lands",
        "WORDS",
    ]
    positions = [text.index(line) for line in order]
    assert positions == sorted(positions)
    assert bare.index(strip_nikkud(LINE_1)[0]) < bare.index(strip_nikkud(LINE_2)[0])
    assert "to rise" in text and "word" in text
