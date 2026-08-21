from __future__ import annotations

import pytest

from targum.ids import segment_id
from targum.models import BlockKind, Document, SegmentedDocument
from targum.segment import segment_document, stanza_code


def test_headings_are_never_split(document: Document, fake_segmenter: object) -> None:
    segmented = segment_document(document, fake_segmenter)  # type: ignore[arg-type]
    headings = [s for s in segmented.segments if s.kind is BlockKind.heading]
    assert len(headings) == 1
    assert headings[0].text == "הכרזה על הקמת מדינת ישראל"


def test_splits_paragraphs_into_sentences(segmented: SegmentedDocument) -> None:
    from_block_one = [s for s in segmented.segments if s.block_index == 1]
    assert len(from_block_one) == 2
    assert [s.index for s in from_block_one] == [0, 1]


def test_ids_are_stable_across_runs(document: Document, fake_segmenter: object) -> None:
    first = segment_document(document, fake_segmenter)  # type: ignore[arg-type]
    second = segment_document(document, fake_segmenter)  # type: ignore[arg-type]
    assert [s.id for s in first.segments] == [s.id for s in second.segments]


def test_id_changes_when_the_text_changes() -> None:
    # An edit upstream must not silently rebind a translation to different words.
    assert segment_id(1, 0, "one text") != segment_id(1, 0, "another text")
    assert segment_id(1, 0, "same") != segment_id(2, 0, "same")


def test_ids_are_unique(segmented: SegmentedDocument) -> None:
    ids = [s.id for s in segmented.segments]
    assert len(ids) == len(set(ids))


def test_carries_the_document_hash(document: Document, segmented: SegmentedDocument) -> None:
    assert segmented.document_hash == document.content_hash


@pytest.mark.parametrize(("given", "expected"), [("he", "he"), ("he-IL", "he"), ("iw", "he")])
def test_language_tags_map_onto_stanza_codes(given: str, expected: str) -> None:
    assert stanza_code(given) == expected


@pytest.mark.stanza
def test_hebrew_abbreviations_do_not_split(needs_hebrew_model: None) -> None:
    from targum.ids import content_hash
    from targum.models import Block
    from targum.segment import StanzaSegmenter

    # Gershayim (״) and geresh (׳) look like quote marks and are not.
    text = "בשנת תרנ״ז (1897) נתכנס הקונגרס. ד״ר אברהם גרנובסקי חתם ביום ה׳ אייר תש״ח."
    document = Document(
        source="memory",
        language="he",
        blocks=[Block(id="b0000", text=text)],
        content_hash=content_hash(text),
    )
    segmented = segment_document(document, StanzaSegmenter())
    assert len(segmented.segments) == 2
    assert "תרנ״ז" in segmented.segments[0].text
