"""A published translation held as a file of verses (targum-internal#187)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_sefaria import _WholeBlocks, document

from targum.align import parallel
from targum.errors import TargumError
from targum.ingest.fetch import published
from targum.models import BlockKind
from targum.segment import segment_document


def russian_ruth() -> dict[str, str]:
    """Ruth's verses as a published file keys them: the English fixture's refs, with a
    stand-in Russian line for each."""
    english = document("en")
    return {
        block.ref: f"Стих {block.ref}" for block in english.blocks if block.kind is BlockKind.verse
    }


def test_a_book_is_shaped_as_sefaria_shapes_it_and_pairs_with_the_hebrew() -> None:
    """Chapters under headings, one verse block per verse, each carrying its ref, so the
    Hebrew pairs with it verse for verse and nothing is guessed."""
    held = russian_ruth()
    russian = published.document_for("ru", "Ruth", held, "Книга Руфь")
    assert russian.source == "published:ru:Ruth" and russian.language == "ru"
    verses = [b for b in russian.blocks if b.kind is BlockKind.verse]
    assert len(verses) == len(held) and verses[0].ref == "Ruth 1:1"
    assert sum(1 for b in russian.blocks if b.kind is BlockKind.heading) == 4

    hebrew = document("he")
    assert parallel.parallel_key(russian) == parallel.parallel_key(hebrew)
    alignment = parallel.pair(
        segment_document(hebrew, _WholeBlocks()), segment_document(russian, _WholeBlocks()), "Ruth"
    )
    assert alignment.coverage() == 1.0


def test_a_verse_the_file_lacks_keeps_its_place() -> None:
    """A verse missing from the middle of a chapter is kept as a dash, so every verse after
    it still pairs with its own Hebrew."""
    held = russian_ruth()
    del held["Ruth 1:5"]
    russian = published.document_for("ru", "Ruth", held, "")
    by_ref = {b.ref: b.text for b in russian.blocks if b.kind is BlockKind.verse}
    assert by_ref["Ruth 1:5"] == "—" and by_ref["Ruth 1:6"] == "Стих Ruth 1:6"


def test_the_file_is_read_from_where_the_content_lives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "ru.json").write_text(
        json.dumps({"title": "Пятикнижие", "verses": russian_ruth()}, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGUM_PUBLISHED", str(tmp_path))
    published.edition.cache_clear()
    try:
        loaded = published.PublishedFetcher().load("published:ru:Ruth")
        assert loaded.title == "Пятикнижие, Ruth" and loaded.ingester == "published/1"
        with pytest.raises(TargumError):
            published.PublishedFetcher().load("published:ru:Esther")
        with pytest.raises(TargumError):
            published.PublishedFetcher().load("published:fr:Ruth")
    finally:
        published.edition.cache_clear()
