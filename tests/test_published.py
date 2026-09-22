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


def test_a_book_named_in_the_translation_titles_its_chapters_in_that_language() -> None:
    """A Russian reader meets «Руфь 1» over Russian verses, while every ref stays Sefaria's
    and the book still pairs with the Hebrew."""
    russian = published.document_for("ru", "Ruth", russian_ruth(), "Пятикнижие", "Руфь")
    headings = [b.text for b in russian.blocks if b.kind is BlockKind.heading]
    assert russian.title == "Руфь" and headings[0] == "Руфь 1"
    assert next(b.ref for b in russian.blocks if b.kind is BlockKind.verse) == "Ruth 1:1"
    assert parallel.parallel_key(russian) == parallel.parallel_key(document("he"))


# -- a commentary pairs with the book it comments on (targum-internal#200) --------------


def test_a_commentary_keys_as_the_book_it_comments_on() -> None:
    """A commentary is numbered *by* the book it comments on — that is what its reference
    is — so it pairs with that book by construction, exactly as Onkelos does.

    Without this it went to the machine aligner, which matches by similarity: a comment is
    *about* a verse rather than a rendering of it, so the links would have been arbitrary
    and nothing would have said so. Declared, `pair` links verse to verse and raises
    rather than guessing if the two ever stop lining up.
    """
    from types import SimpleNamespace

    from targum.align.parallel import parallel_key

    def document(source: str) -> object:
        return SimpleNamespace(ingester="sefaria/1", source=source)

    base = parallel_key(document("sefaria:Genesis"))
    assert parallel_key(document("sefaria:Rashi on Genesis")) == base
    assert parallel_key(document("sefaria:arc:Genesis")) == base, "Onkelos still does too"
    assert parallel_key(document("published:ru:Genesis")) == base, "and the Russian Torah"

    # A commentary on something else keys on that something else, not on Genesis.
    assert parallel_key(document("sefaria:Rashi on Berakhot")) == "sefaria:berakhot"

    # And a book whose own name has small words in it is not mistaken for one.
    assert parallel_key(document("sefaria:Song of Songs")) == "sefaria:song of songs"
    assert parallel_key(document("sefaria:Ecclesiastes")) == "sefaria:ecclesiastes"


def test_a_rashi_verse_is_one_unit_so_the_two_sides_still_count_the_same() -> None:
    """The pairing only works because both sides count the same, and a verse of Rashi is
    several comments joined. It survives because `BlockKind.verse` is in `UNSPLIT`: a
    verse is never broken into sentences, however many full stops it has — and Rashi's
    catchwords end in one, so a sentence split would have turned three verses into eleven
    units and made the pairing impossible."""
    import json
    from pathlib import Path

    from targum.ingest.fetch.sefaria import document_from_payload
    from targum.models import BlockKind
    from targum.segment.base import UNSPLIT

    assert BlockKind.verse in UNSPLIT

    fixture = Path(__file__).parent / "fixtures" / "sefaria" / "rashi-genesis-1.he.json"
    body = json.loads(fixture.read_text(encoding="utf-8"))
    payload = {
        "edition": body["versions"][0],
        "body": body,
        "licence": "Public Domain",
        "version": "x",
    }
    document = document_from_payload(payload, "Rashi on Genesis", "he")
    verses = [block for block in document.blocks if block.kind is BlockKind.verse]
    assert len(verses) == 3, "one unit a verse, whatever the comments number"
    assert verses[0].text.count("\n") == 2, "and its comments are still separable"
