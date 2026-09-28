"""The reader's edition on paper (targum-internal#105)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from targum.accounts import Person, Store
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
from targum.parasha import calendar as cal
from targum.parasha import cut as cutmod
from targum.render.printed import Word, first_sense, mikra_html, print_html, week_words
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


# -- the week's shnayim mikra sheet ----------------------------------------------------

# Onkelos, beside every verse of the fixture's portion.
ONKELOS = "אַתּוּן קָיְמִין יוֹמָא דֵין"


@pytest.fixture
def shelf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Deuteronomy with Onkelos beside it and enough of Isaiah for its haftarah, and the
    calendar for 2026 where the portion page keeps it — the same books and the same
    calendar `test_parasha_cut` cuts from."""
    import shutil

    from test_parasha_cut import FIXTURES, a_book

    monkeypatch.setenv("TARGUM_PARASHA_DIR", str(tmp_path / "parasha"))
    (tmp_path / "parasha" / "calendar").mkdir(parents=True)
    for one in FIXTURES.glob("*.json"):
        shutil.copy(one, tmp_path / "parasha" / "calendar" / one.name)
    library = tmp_path / "library"
    a_book(library / "דברים-he", "Deuteronomy", "דברים", {29: 29, 30: 20, 31: 30})
    a_book(library / "ישעיהו-he", "Isaiah", "ישעיהו", {61: 11, 62: 12, 63: 9})
    english = next((library / "דברים-he" / "translations").glob("*.en.json"))
    onkelos = Translation.model_validate_json(english.read_text(encoding="utf-8"))
    onkelos.model_copy(
        update={
            "name": "Onkelos Deuteronomy",
            "target_language": "arc",
            "segments": {sid: ONKELOS for sid in onkelos.segments},
        }
    ).write(english.parent / "onkelos.deuteronomy.arc.json")
    return library


def _week(library: Path) -> tuple[cal.Reading, cutmod.Portion, cutmod.Portion]:
    """Nitzavim-Vayeilech, 5 September 2026, and its haftarah, cut as the command cuts."""
    reading = cal.for_shabbat(date(2026, 9, 5), cal.Schedule.diaspora)
    assert reading is not None and reading.haftarah is not None
    portion = cutmod.cut(reading, cutmod.books_for(reading, library))
    haftarah = cutmod.cut_haftarah(reading.haftarah, cutmod.books_for(reading.haftarah, library))
    return reading, portion, haftarah


def _began() -> int:
    """When that week began, in the milliseconds a kept word carries."""
    return int(cal.week_began(date(2026, 9, 5)).timestamp() * 1000)


def _kept(tmp_path: Path) -> tuple[Store, Person]:
    store = Store(tmp_path / "db")
    signed = store.finish_sign_in(store.start_sign_in("r@example.com"))
    assert signed is not None
    person = signed[0]
    began, hour = _began(), 3_600_000

    def word(lemma: str, status: int, at: int, language: str = "he", band: str = "") -> dict:
        return {"language": language, "lemma": lemma, "status": status, "band": band, "at": at}

    store.push(
        person,
        {
            "words": [
                word("אתם", 1, began + hour),  # this week, with no meaning of its own
                word("שלום", 2, began + 2 * hour),  # this week, with the reader's note
                word("רעב", 1, began + 3 * hour),  # this week, with no meaning anywhere
                word("בית", 9, began + 4 * hour),  # this week, and known already
                word("דוד", 1, began + 5 * hour, band="name"),  # a name
                word("ארץ", 1, began - hour),  # last week
                word("קום", 1, began + 8 * 24 * hour),  # next week
                word("אנון", 2, began + 6 * hour, language="arc"),  # from the Onkelos column
            ],
            "meanings": [
                {
                    "source": "he",
                    "target": "en",
                    "term": "שלום",
                    "meaning": "hello",
                    "note": "peace; wellbeing",
                    "at": began,
                },
                {"source": "arc", "target": "en", "term": "אנון", "meaning": "they", "at": began},
            ],
        },
    )
    return store, person


def test_the_sheet_sets_the_portion_beside_onkelos_and_the_haftarah_beside_english(
    shelf: Path,
) -> None:
    reading, portion, haftarah = _week(shelf)
    html = mikra_html(
        portion, haftarah, name="Nitzavim-Vayeilech", hebrew="נִצָּבִים", when="23 Elul 5786"
    )
    # The chrome is the reader's language, and the portion's name leads the page.
    assert '<html lang="en" dir="rtl">' in html
    assert "Nitzavim-Vayeilech · 23 Elul 5786" in html
    torah, _, prophets = html.partition('<header class="title part">')
    assert prophets, "the haftarah stands under a title of its own"
    # Twice the text, once the targum: Onkelos beside every verse of the portion, and no
    # English there.
    assert torah.count('<p class="tr" lang="arc" dir="rtl">') >= portion.verses
    assert ONKELOS in torah and "Deuteronomy 29 verse 9" not in torah
    assert torah.count('<div class="pair verse">') == sum(a.verses for a in reading.aliyot)
    # The haftarah, read once and never beside a targum: English beside it, and its range
    # as a chumash prints it.
    assert "Isaiah 61:10-63:9" in prophets
    assert "Isaiah 61 verse 10" in prophets and ONKELOS not in prophets
    # No list after an aliyah: the one list on the sheet is the reader's week.
    assert 'class="words' not in html


def test_the_portion_can_stand_beside_english_when_asked(shelf: Path) -> None:
    _, portion, haftarah = _week(shelf)
    torah = mikra_html(portion, haftarah, name="N", hebrew="נ", into="en").partition(
        '<header class="title part">'
    )[0]
    assert "Deuteronomy 29 verse 9" in torah and ONKELOS not in torah


def test_the_week_is_the_words_kept_in_it_and_still_being_learned(tmp_path: Path) -> None:
    store, person = _kept(tmp_path)
    kept = store.kept_between(
        person.id, _began(), _began() + 7 * 86_400_000, languages=("he", "arc"), target="en"
    )
    assert [(one.language, one.lemma) for one in kept] == [
        ("he", "אתם"),
        ("he", "שלום"),
        ("he", "רעב"),
        ("arc", "אנון"),
    ]
    # The reader's own note before the meaning the page gave.
    assert kept[1].meaning == "peace; wellbeing"


def test_the_sheets_list_takes_its_meanings_from_the_reader_or_the_week(
    shelf: Path, tmp_path: Path
) -> None:
    _, portion, haftarah = _week(shelf)
    store, person = _kept(tmp_path)
    week = week_words(
        store.kept_between(
            person.id, _began(), _began() + 7 * 86_400_000, languages=("he", "arc"), target="en"
        ),
        [portion, haftarah],
    )
    # אתם takes the portion's meaning, שלום the first sense of the reader's note, and רעב,
    # with a meaning nowhere, is left off: paper cannot look one up.
    assert [(w.form, w.meaning, w.language) for w in week] == [
        ("אתם", "you", "he"),
        ("שלום", "peace", "he"),
        ("אנון", "they", "arc"),
    ]
    listed = mikra_html(portion, haftarah, name="N", hebrew="נ", week=week).partition(
        '<aside class="words week">'
    )[2]
    assert "Your words this week" in listed
    assert ("שלום", "peace") in _words(listed)
    assert '<dt lang="arc" dir="rtl">אנון</dt>' in listed


def test_export_mikra_finds_the_week_and_writes_one_sheet(
    shelf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from typer.testing import CliRunner

    from targum.cli import app
    from targum.render import printed

    _kept(tmp_path)
    written: dict[str, object] = {}

    def fake(html: str, out: Path) -> Path:
        written["html"], written["out"] = html, out
        return out

    monkeypatch.setattr(printed, "write_pdf", fake)
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        app,
        [
            *("export", "mikra", "--on", "2026-09-01", "--library", str(shelf)),
            *("--for", "r@example.com", "--store", str(tmp_path / "db")),
        ],
    )
    assert result.exit_code == 0, result.output
    # A Tuesday finds the Shabbat after it, and the file is named for both.
    assert written["out"] == tmp_path / "nitzavim-vayeilech-2026-09-05.pdf"
    html = str(written["html"])
    assert ONKELOS in html and "Isaiah 61:10-63:9" in html
    assert ("שלום", "peace") in _words(html)


def test_export_mikra_refuses_a_shelf_without_the_book(shelf: Path, tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from targum.cli import app

    result = CliRunner().invoke(
        app, ["export", "mikra", "--on", "2026-09-01", "--library", str(tmp_path / "none")]
    )
    assert result.exit_code == 1
    assert "Deuteronomy is not built" in result.output


def test_the_sheet_on_paper_reads_portion_then_haftarah_then_words(
    shelf: Path, tmp_path: Path
) -> None:
    """Set for real where the machine can, as the edition's own PDF test is."""
    from targum.render.printed import _find_pango, write_pdf

    _find_pango()
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        pytest.skip("WeasyPrint or Pango is not installed")
    pypdf = pytest.importorskip("pypdf")

    _, portion, haftarah = _week(shelf)
    week = [Word(form="שָׁלוֹם", meaning="peace")]
    html = mikra_html(portion, haftarah, name="Nitzavim-Vayeilech", hebrew="נצבים", week=week)
    out = write_pdf(html, tmp_path / "sheet.pdf")
    text = "".join(page.extract_text() for page in pypdf.PdfReader(out).pages)
    order = ["Nitzavim-Vayeilech", "Isaiah 61:10-63:9", "Isaiah 61 verse 10", "peace"]
    positions = [text.index(line) for line in order]
    assert positions == sorted(positions)
