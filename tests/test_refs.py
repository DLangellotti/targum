"""Backfilling verse refs onto artifacts written before the ingester carried them.

The dangerous failure here is silent: a recording mapped onto the wrong verses plays a
reader words that are not the ones in front of them, and nothing in the page would show
it. So most of what is tested is the refusal — the cases where the mapping is declined
whole rather than guessed at.
"""

from __future__ import annotations

from pathlib import Path

from targum.models import (
    Block,
    BlockKind,
    Document,
    Segment,
    SegmentedDocument,
    Translation,
)
from targum.refs import backfill, refs_from, wants_refs

VERSES = ["בראשית ברא", "והארץ היתה", "ויאמר אלהים"]


def document(with_refs: bool = True, source: str = "sefaria:Genesis") -> Document:
    return Document(
        source=source,
        title="Genesis",
        language="he",
        blocks=[
            Block(
                id=f"b{n:04d}",
                kind=BlockKind.verse,
                text=text,
                ref=f"Genesis 1:{n + 1}" if with_refs else "",
            )
            for n, text in enumerate(VERSES)
        ],
        content_hash="h",
    )


def segmented(texts: list[str] | None = None) -> SegmentedDocument:
    return SegmentedDocument(
        document_hash="h",
        language="he",
        segmenter="test/1",
        segments=[
            Segment(
                id=f"{n:04d}.000-aaaaaa",
                block_id=f"b{n:04d}",
                block_index=n,
                index=0,
                kind=BlockKind.verse,
                text=text,
            )
            for n, text in enumerate(texts or VERSES)
        ],
    )


def test_a_text_with_no_refs_wants_them() -> None:
    assert wants_refs(document(with_refs=False), segmented()) is True


def test_a_text_that_already_has_them_is_left_alone() -> None:
    now = segmented()
    for n, segment in enumerate(now.segments):
        segment.ref = f"Genesis 1:{n + 1}"
    assert wants_refs(document(), now) is False


def test_only_scripture_is_asked_about() -> None:
    """Nothing else is addressed by verse, so nothing else has anything to backfill."""
    assert wants_refs(document(source="https://benyehuda.org/x.txt"), segmented()) is False


def test_the_refs_come_across_in_order() -> None:
    got = refs_from(document(), segmented())
    assert got == {
        "0000.000-aaaaaa": "Genesis 1:1",
        "0001.000-aaaaaa": "Genesis 1:2",
        "0002.000-aaaaaa": "Genesis 1:3",
    }


def test_a_text_that_has_changed_is_declined_whole() -> None:
    """The safety property. Position pairs them and text proves the pairing — where the
    proof fails the answer is None, not the two thirds that happened to line up."""
    changed = segmented([VERSES[0], "something else entirely", VERSES[2]])
    assert refs_from(document(), changed) is None


def test_a_different_number_of_verses_is_declined() -> None:
    assert refs_from(document(), segmented(VERSES[:2])) is None


def test_a_source_that_sends_no_refs_is_declined() -> None:
    """An older fetcher answering. Better nothing than a map of empty strings."""
    assert refs_from(document(with_refs=False), segmented()) is None


def written(home: Path, doc: Document, seg: SegmentedDocument) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    doc.write(home / "document.json")
    seg.write(home / "segments.json")
    Translation(
        name="English",
        document_hash="h",
        source_language="he",
        target_language="en",
        provider="null",
    ).write(home / "translations" / "en.json")
    return home


def test_backfill_fills_and_says_so(tmp_path: Path) -> None:
    written(tmp_path / "genesis-he", document(with_refs=False), segmented())
    said: list[str] = []
    filled, skipped = backfill(tmp_path, lambda source: document(), said.append)
    assert (filled, skipped) == (1, 0)
    back = SegmentedDocument.model_validate_json(
        (tmp_path / "genesis-he" / "segments.json").read_text(encoding="utf-8")
    )
    assert [s.ref for s in back.segments] == ["Genesis 1:1", "Genesis 1:2", "Genesis 1:3"]
    assert "3 verses" in said[0]


def test_backfill_is_safe_to_run_twice(tmp_path: Path) -> None:
    """Idempotent, and the second run asks the source for nothing: a shelf half migrated
    by an interrupted run is the ordinary case, not an error."""
    written(tmp_path / "genesis-he", document(with_refs=False), segmented())
    asked: list[str] = []

    def fetch(source: str) -> Document:
        asked.append(source)
        return document()

    backfill(tmp_path, fetch)
    filled, skipped = backfill(tmp_path, fetch)
    assert (filled, skipped) == (0, 0)
    assert asked == ["sefaria:Genesis"], "the second pass fetched nothing"


def test_a_reader_whose_text_moved_on_is_left_untouched(tmp_path: Path) -> None:
    home = written(
        tmp_path / "genesis-he", document(with_refs=False), segmented(["not", "the", "same"])
    )
    before = (home / "segments.json").read_text(encoding="utf-8")
    filled, skipped = backfill(tmp_path, lambda source: document())
    assert (filled, skipped) == (0, 1)
    assert (home / "segments.json").read_text(encoding="utf-8") == before


def test_a_source_that_cannot_be_reached_stops_that_book_and_nothing_else(tmp_path: Path) -> None:
    written(tmp_path / "genesis-he", document(with_refs=False), segmented())
    written(
        tmp_path / "ruth-he",
        document(with_refs=False, source="sefaria:Ruth"),
        segmented(),
    )

    def fetch(source: str) -> Document:
        if source == "sefaria:Genesis":
            raise OSError("the network is not there")
        return document(source=source)

    said: list[str] = []
    filled, skipped = backfill(tmp_path, fetch, said.append)
    assert filled == 1 and skipped == 1
    assert any("could not fetch" in line for line in said)
