"""EPUB, against a real file with footnotes and a spine that disagrees with file order."""

from __future__ import annotations

from pathlib import Path

import pytest

from targum import ingest
from targum.errors import TargumError
from targum.models import BlockKind


@pytest.fixture
def document(epub_source: Path):
    return ingest.load(str(epub_source))


def test_reads_metadata(document) -> None:
    assert document.title == "On the Reading of Old Books"
    assert document.author == "A Nineteenth Century Author"
    assert document.language == "en"
    assert document.ingester.startswith("epub/")


def test_chapters_come_in_spine_order(document) -> None:
    # Chapter Two is written into the archive first. Reading order is the spine.
    headings = [b.text for b in document.blocks if b.kind is BlockKind.heading]
    assert headings == ["Chapter One", "Chapter Two"]


def test_footnotes_and_markers_are_gone(document) -> None:
    body = " ".join(block.text for block in document.blocks)
    assert "apparatus" not in body
    assert "See the earlier literature" not in body
    # The marker digit must not survive inside the sentence either.
    assert "means peace. He was not" in body


def test_the_table_of_contents_is_not_text(document) -> None:
    assert not any(block.text.strip() == "Contents" for block in document.blocks)


def test_structure_is_preserved(document) -> None:
    kinds = [block.kind for block in document.blocks]
    assert BlockKind.blockquote in kinds
    assert kinds[0] is BlockKind.heading
    assert kinds[1] is BlockKind.byline


def test_embedded_hebrew_survives(document) -> None:
    assert any("שלום" in block.text for block in document.blocks)


def test_a_broken_epub_says_so(tmp_path: Path) -> None:
    fake = tmp_path / "broken.epub"
    fake.write_bytes(b"not an epub at all")
    with pytest.raises(TargumError, match="Could not read the EPUB"):
        ingest.load(str(fake))


def test_it_builds_end_to_end(epub_source: Path, tmp_path: Path, fake_segmenter: object) -> None:
    from targum.pipeline import Build

    result = Build(
        str(epub_source),
        target_language="he",
        provider_name="null",
        out=tmp_path / "out",
        segmenter=fake_segmenter,  # type: ignore[arg-type]
    ).run()
    assert result.index.exists()
    assert len(result.pages) == 3  # index plus a section per chapter
