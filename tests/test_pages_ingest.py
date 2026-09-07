"""Pictures and text-layer PDFs become documents the pipeline reads like any other."""

from __future__ import annotations

from pathlib import Path

import pytest

from targum import ingest, vision
from targum.errors import TargumError, UnsupportedSource
from targum.ingest import pages as pages_module
from targum.ingest import pdf as pdf_module
from targum.models import BlockKind

FIXTURES = Path(__file__).parent / "fixtures" / "pages"
pytest.importorskip("pypdf", reason="the bring extra is not installed: uv sync --extra bring")

HANDOUT = FIXTURES / "handout.txt"


def lines_of(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --- the shape both share ------------------------------------------------------------


def test_lines_group_into_paragraphs_at_blank_lines_and_wrap_into_one_line() -> None:
    assert pages_module.paragraphs_of(["one", "two", "", "", "three "]) == ["one two", "three"]
    assert pages_module.paragraphs_of([]) == []


def test_a_document_from_pages_carries_the_page_on_every_block_and_marks_english() -> None:
    document = pages_module.document_from_pages(
        "set",
        [["שלום עולם", "", "The guide said"], ["פרק ב", "", "עוד שורה."]],
        ingester="picture/1",
        source_hash="abc",
    )
    assert [block.ref for block in document.blocks] == ["p1", "p1", "p2", "p2"]
    assert [block.language for block in document.blocks] == [None, "en", None, None]
    assert document.blocks[2].kind is BlockKind.heading, "a bare chapter line is a heading"
    assert document.language == "he", "decided from the Hebrew, not the English line"
    assert document.title == "שלום עולם"
    assert document.source_hash == "abc"


def test_the_title_is_the_first_line_cut_at_a_word() -> None:
    long = " ".join(["מילה"] * 30)
    assert len(pages_module.title_of([[long]])) <= pages_module.TITLE_CHARS
    assert pages_module.title_of([[""], ["   "], ["כותרת"]]) == "כותרת"


# --- a PDF with a text layer --------------------------------------------------------


def test_a_text_layer_pdf_reads_in_logical_order_with_ayin_folded_back() -> None:
    """Chromium's subset spells ayin as U+FB20; NFKC folds it. And the Hebrew lines come
    back in reading order — pypdf's layout mode and pdfminer both reverse them."""
    document = ingest.load(str(FIXTURES / "handout.pdf"))
    assert document.ingester == "pdf/1"
    assert document.language == "he"
    text = "\n".join(block.text for block in document.blocks)
    assert "ﬠ" not in text and "ע" in text
    for want in ("נָסַעְתִּי לַנֶּגֶב", "בבוקר יצאנו לטיול ארוך בין ההרים", "רָאִינוּ אֶת הַמַּכְתֵּשׁ"):
        assert want in text
    assert all(block.ref == "p1" for block in document.blocks)


def test_a_pdfs_paragraph_gaps_become_paragraphs() -> None:
    document = ingest.load(str(FIXTURES / "handout.pdf"))
    assert len(document.blocks) >= 3, [block.text for block in document.blocks]
    assert document.blocks[-1].text.startswith("בַּיּוֹם הַשֵּׁנִי")


def test_a_mixed_line_counts_as_doubtful_rather_than_passing_as_the_page() -> None:
    pages = pdf_module.page_lines(FIXTURES / "handout.pdf")
    assert pdf_module.doubtful_lines(pages) == 1
    assert pages_module.mixed("The guide said: לֵךְ") and not pages_module.mixed("שלום")


def test_without_positions_a_sentence_end_ends_a_paragraph() -> None:
    assert pdf_module.spaced(["שורה אחת.", "שורה שתיים", "שלוש."], []) == [
        "שורה אחת.",
        "",
        "שורה שתיים",
        "שלוש.",
        "",
    ]


def test_with_positions_a_wide_gap_is_a_paragraph_break() -> None:
    assert pdf_module.spaced(["a", "b", "c", "d"], [0.0, 20.0, 40.0, 100.0]) == [
        "a",
        "b",
        "c",
        "",
        "d",
    ]
    # Runs on one line share a position; a page that is mostly gaps still finds its
    # line height in the one pair of lines that sit close.
    assert pdf_module.spaced(["a", "b", "c", "d"], [0.0, 0.5, 20.0, 60.0, 60.2, 100.0]) == [
        "a",
        "b",
        "",
        "c",
        "",
        "d",
    ]


def test_a_scan_is_refused_by_name_and_nothing_is_read() -> None:
    with pytest.raises(UnsupportedSource, match="scan"):
        ingest.load(str(FIXTURES / "scan.pdf"))


def test_a_pdf_over_thirty_pages_is_refused(tmp_path: Path) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(31):
        writer.add_blank_page(width=200, height=200)
    long = tmp_path / "book.pdf"
    with long.open("wb") as out:
        writer.write(out)
    assert pdf_module.page_count(long) == 31
    with pytest.raises(TargumError, match="31 pages"):
        pdf_module.page_lines(long)


def test_the_source_hash_is_the_files_bytes(tmp_path: Path) -> None:
    document = ingest.load(str(FIXTURES / "handout.pdf"))
    import hashlib

    expected = hashlib.sha256((FIXTURES / "handout.pdf").read_bytes()).hexdigest()
    assert document.source_hash == expected


# --- pictures -----------------------------------------------------------------------


@pytest.fixture
def read_by_name(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The model, answering each picture with its own file name as the page's text."""
    pytest.importorskip("PIL")
    asked: list[str] = []

    def pretend(image: bytes, media_type: str, *, model: str, usage, client):  # noqa: ANN001
        usage.add(model, 10, 5)
        page = f"page for {len(image)}"
        asked.append(page)
        return vision.parse(page + "\n\n?a doubtful line")

    monkeypatch.setattr(vision, "read_one", pretend)
    monkeypatch.setattr(vision, "AnthropicProvider", None, raising=False)
    return asked


def test_a_folder_of_pictures_is_one_text_in_name_order(tmp_path: Path, read_by_name) -> None:
    from PIL import Image

    folder = tmp_path / "set"
    folder.mkdir()
    sizes = [(30, 10), (20, 10), (40, 10)]
    for n, size in enumerate(sizes, start=1):
        Image.new("RGB", size, "white").save(folder / f"{n:02d}-photo.png")
    (folder / "notes.txt").write_text("ignored", encoding="utf-8")

    document = ingest.load(str(folder))
    assert document.ingester == "picture/2"
    assert [block.ref for block in document.blocks] == ["p1", "p1", "p2", "p2", "p3", "p3"]
    expected = [
        f"page for {len(vision.prepared(folder / f'{n:02d}-photo.png')[0])}" for n in (1, 2, 3)
    ]
    assert [block.text for block in document.blocks[::2]] == expected
    assert len(read_by_name) == 3


def test_one_picture_is_a_text_too(read_by_name) -> None:
    document = ingest.load(str(FIXTURES / "screenshot.png"))
    assert document.ingester == "picture/2"
    assert document.blocks and document.blocks[0].ref == "p1"


def test_a_folder_with_no_pictures_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "empty"
    folder.mkdir()
    (folder / "notes.txt").write_text("x", encoding="utf-8")
    with pytest.raises(UnsupportedSource):
        ingest.load(str(folder))


def test_a_picture_with_no_words_is_said_so(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PIL")

    def blank(image, media_type, *, model, usage, client):  # noqa: ANN001
        return vision.parse("?")

    monkeypatch.setattr(vision, "read_one", blank)
    with pytest.raises(TargumError, match="No text could be read"):
        ingest.load(str(FIXTURES / "screenshot.png"))


def test_pdf_and_pictures_are_sources_the_dispatcher_names() -> None:
    named = ingest.sources()
    assert ".pdf" in named and ".png" in named and ".heic" in named


# --- a chat photographed off a phone ------------------------------------------------


def test_a_conversation_is_turns_with_the_speaker_beside_the_line() -> None:
    """A WhatsApp screenshot is a dialogue, and drawn like the shelf's own: the name on
    the block and out of the text, so it is never pointed, counted or read aloud."""
    document = pages_module.document_from_pages(
        "set",
        [["אמא: מה שלומך?", "", "me: הכל טוב, ואת?", "", "אמא: בסדר גמור.", "נתראה מחר"]],
        ingester="picture/2",
        source_hash="x",
        conversation=True,
    )
    assert [block.kind for block in document.blocks] == [BlockKind.turn] * 3
    assert [block.speaker for block in document.blocks] == ["אמא", "me", "אמא"]
    assert [block.text for block in document.blocks] == [
        "מה שלומך?",
        "הכל טוב, ואת?",
        "בסדר גמור. נתראה מחר",
    ]
    assert document.title == "אמא", "the other side names the chat on the shelf"


def test_a_message_with_no_name_is_the_same_person_still_talking() -> None:
    document = pages_module.document_from_pages(
        "set",
        [["דני: היי", "", "אתה בא?", "", "me: כן"]],
        ingester="picture/2",
        source_hash="x",
        conversation=True,
    )
    assert [(b.speaker, b.text) for b in document.blocks] == [
        ("דני", "היי"),
        ("דני", "אתה בא?"),
        ("me", "כן"),
    ]


def test_without_the_mark_a_colon_is_just_a_colon() -> None:
    document = pages_module.document_from_pages(
        "set", [["הערה: זה משפט."]], ingester="picture/2", source_hash="x"
    )
    assert document.blocks[0].kind is BlockKind.paragraph and document.blocks[0].speaker is None
    assert pages_module.turn_of("22:15 שחרית") is None, "a time is not a speaker"
    assert pages_module.turn_of("Note that this is prose.") is None


def test_a_conversation_photographed_over_two_screens_is_one_dialogue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("PIL")
    from PIL import Image

    folder = tmp_path / "chat"
    folder.mkdir()
    for n in (1, 2):
        Image.new("RGB", (10 + n, 10), "white").save(folder / f"{n:02d}-screen.png")
    answers = iter(["[conversation]\nאמא: שלום\n\nme: שלום אמא", "[conversation]\nאמא: מה נשמע?"])

    def pretend(image, media_type, *, model, usage, client):  # noqa: ANN001
        return vision.parse(next(answers))

    monkeypatch.setattr(vision, "read_one", pretend)
    document = ingest.load(str(folder))
    assert document.ingester == "picture/2"
    assert [(b.ref, b.speaker, b.text) for b in document.blocks] == [
        ("p1", "אמא", "שלום"),
        ("p1", "me", "שלום אמא"),
        ("p2", "אמא", "מה נשמע?"),
    ]
