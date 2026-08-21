from __future__ import annotations

import unicodedata
from pathlib import Path

import pytest

from targum import ingest
from targum.errors import TargumError, UnsupportedSource
from targum.models import BlockKind


def test_reads_markdown_structure(tmp_path: Path) -> None:
    source = tmp_path / "text.md"
    source.write_text(
        "# Title\n\nFirst paragraph\ncontinued on the next line.\n\n"
        "> A quotation.\n\n## Section\n\nSecond paragraph with *emphasis* and "
        "[a link](http://example.com).\n",
        encoding="utf-8",
    )
    document = ingest.load(str(source))

    kinds = [block.kind for block in document.blocks]
    assert kinds == [
        BlockKind.heading,
        BlockKind.paragraph,
        BlockKind.blockquote,
        BlockKind.heading,
        BlockKind.paragraph,
    ]
    assert document.title == "Title"
    assert document.blocks[1].text == "First paragraph continued on the next line."
    assert document.blocks[4].text == "Second paragraph with emphasis and a link."
    assert document.blocks[3].level == 2


def test_plain_text_splits_on_blank_lines(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("One.\n\nTwo.\n\n\nThree.\n", encoding="utf-8")
    document = ingest.load(str(source))
    assert [block.text for block in document.blocks] == ["One.", "Two.", "Three."]


def test_normalizes_to_nfc(tmp_path: Path) -> None:
    # Hebrew with a decomposed holam. Mismatched forms break lookup and alignment.
    decomposed = unicodedata.normalize("NFD", "שָׁלוֹם")
    source = tmp_path / "he.txt"
    source.write_text(decomposed, encoding="utf-8")
    document = ingest.load(str(source))
    text = document.blocks[0].text
    assert text == unicodedata.normalize("NFC", text)


def test_keeps_niqqud(tmp_path: Path) -> None:
    source = tmp_path / "he.txt"
    source.write_text("בְּרֵאשִׁית בָּרָא", encoding="utf-8")
    assert "ְ" in ingest.load(str(source)).blocks[0].text


def test_detects_language_by_script(tmp_path: Path) -> None:
    cases = {
        "he": "בארץ ישראל קם העם היהודי בשנת 1897",
        "ru": "В начале было слово и слово было",
        "en": "In the beginning was the word",
    }
    for expected, text in cases.items():
        source = tmp_path / f"{expected}.txt"
        source.write_text(text, encoding="utf-8")
        assert ingest.load(str(source)).language == expected


def test_source_language_overrides_detection(tmp_path: Path) -> None:
    source = tmp_path / "x.txt"
    source.write_text("Ambiguous 1897", encoding="utf-8")
    assert ingest.load(str(source), language="he-IL").language == "he-IL"


def test_pdf_says_so_without_a_traceback(tmp_path: Path) -> None:
    source = tmp_path / "book.pdf"
    source.write_bytes(b"%PDF-1.4")
    with pytest.raises(UnsupportedSource, match="PDF ingest is not supported yet"):
        ingest.load(str(source))


def test_unknown_suffix_lists_what_works(tmp_path: Path) -> None:
    source = tmp_path / "book.rtf"
    source.write_text("x", encoding="utf-8")
    with pytest.raises(UnsupportedSource) as caught:
        ingest.load(str(source))
    assert ".epub" in (caught.value.hint or "")


def test_sources_lists_files_urls_and_identifiers() -> None:
    listed = ingest.sources()
    assert ".epub" in listed and ".md" in listed
    assert "http(s)://" in listed
    assert "gutenberg:" in listed and "wikisource:" in listed


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(TargumError, match="No such file"):
        ingest.load(str(tmp_path / "nope.txt"))


def test_content_hash_ignores_the_filename(tmp_path: Path) -> None:
    first, second = tmp_path / "a.txt", tmp_path / "b.txt"
    for path in (first, second):
        path.write_text("Same words.", encoding="utf-8")
    assert ingest.load(str(first)).content_hash == ingest.load(str(second)).content_hash


def test_reads_frontmatter_title_and_author(tmp_path: Path) -> None:
    source = tmp_path / "text.md"
    source.write_text(
        '---\ntitle: מגילת העצמאות\nauthor: "דוד בן־גוריון"\nlanguage: he\n---\n\nגוף הטקסט.\n',
        encoding="utf-8",
    )
    document = ingest.load(str(source))
    assert document.title == "מגילת העצמאות"
    assert document.author == "דוד בן־גוריון"
    assert document.language == "he"


def test_title_and_author_become_translatable_blocks(tmp_path: Path) -> None:
    # A reader wants the title in the target language too, so they run through the
    # same segmentation and translation as the body.
    source = tmp_path / "text.md"
    source.write_text("---\ntitle: The Title\nauthor: An Author\n---\n\nBody.\n", encoding="utf-8")
    blocks = ingest.load(str(source)).blocks
    assert blocks[0].kind is BlockKind.heading
    assert blocks[0].text == "The Title"
    assert blocks[1].kind is BlockKind.byline
    assert blocks[1].text == "An Author"


def test_frontmatter_title_does_not_duplicate_an_existing_heading(tmp_path: Path) -> None:
    source = tmp_path / "text.md"
    source.write_text("---\ntitle: The Title\n---\n\n# The Title\n\nBody.\n", encoding="utf-8")
    headings = [b for b in ingest.load(str(source)).blocks if b.kind is BlockKind.heading]
    assert len(headings) == 1


def test_frontmatter_works_in_plain_text(tmp_path: Path) -> None:
    source = tmp_path / "text.txt"
    source.write_text("---\nauthor: Someone\n---\n\nBody.\n", encoding="utf-8")
    document = ingest.load(str(source))
    assert document.author == "Someone"
    assert document.blocks[0].kind is BlockKind.byline


def test_a_stray_dashed_line_is_not_frontmatter(tmp_path: Path) -> None:
    source = tmp_path / "text.md"
    source.write_text("---\nnot closed\n\nBody.\n", encoding="utf-8")
    document = ingest.load(str(source))
    assert document.author is None
    assert "not closed" in document.blocks[0].text


def test_documents_record_their_ingester(tmp_path: Path) -> None:
    source = tmp_path / "text.md"
    source.write_text("# Title\n\nBody.\n", encoding="utf-8")
    assert ingest.load(str(source)).ingester.startswith("markdown/")


def test_the_byline_sits_under_the_title(tmp_path: Path) -> None:
    source = tmp_path / "text.md"
    source.write_text("---\nauthor: An Author\n---\n\n# The Title\n\nBody.\n", encoding="utf-8")
    kinds = [block.kind for block in ingest.load(str(source)).blocks]
    assert kinds == [BlockKind.heading, BlockKind.byline, BlockKind.paragraph]


def test_a_url_keeps_its_double_slash() -> None:
    """pathlib collapses https:// to https:/, which turned every link into a missing
    file when the CLI declared its argument as a Path.

    Checked at the ingest boundary rather than through a real fetch, so the test needs
    no network and no provider.
    """
    from typer.testing import CliRunner

    from targum import cli

    seen: list[str] = []

    def record(source: str, language: str | None = None):  # type: ignore[no-untyped-def]
        seen.append(source)
        raise TargumError("stop here")

    runner = CliRunner()
    original = cli.ingest.load
    cli.ingest.load = record  # type: ignore[assignment]
    try:
        runner.invoke(
            cli.app,
            ["build", "https://example.invalid/a", "--to", "en", "--provider", "null"],
        )
    finally:
        cli.ingest.load = original  # type: ignore[assignment]

    assert seen == ["https://example.invalid/a"]
