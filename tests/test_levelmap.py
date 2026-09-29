"""The level map: where the catalogue sits on the weekly's levels (targum-internal#382).

Pinned here: that a text is placed by both halves and never by the share alone, that
an unmeasured text is never counted as easy, that the Easy spec is the strict count with
its floors and its length, and that a sentence length the catalogue lacks is read off a
build without anything fetched.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum import levelmap
from targum.annotate.difficulty import sentence_length
from targum.catalogue import Entry
from targum.models import BlockKind, Segment, SegmentedDocument
from targum.weekly.models import Level


def entry(
    source: str = "url:x",
    *,
    language: str = "he",
    difficulty: int = 10,
    sentence: float = 7.0,
    words: int = 260,
) -> Entry:
    return Entry(
        id=source,
        title="t",
        author="a",
        language=language,
        source=source,
        blurb="b",
        words=words,
        difficulty=difficulty,
        sentence=sentence,
    )


def segmented(*texts: str, heading: str = "") -> SegmentedDocument:
    segments = [
        Segment(id=f"s{i}", block_id="b", block_index=0, index=i, text=text)
        for i, text in enumerate(texts, start=1)
    ]
    if heading:
        segments.insert(
            0,
            Segment(
                id="s0", block_id="h", block_index=0, index=0, kind=BlockKind.heading, text=heading
            ),
        )
    return SegmentedDocument(document_hash="h", language="he", segmenter="r", segments=segments)


def nothing(source: str) -> bool:
    return False


# The measure.


def test_sentence_length_is_words_per_sentence_without_the_title() -> None:
    assert sentence_length(segmented("a b c", "a b c d e", heading="a b c d e f g h")) == 4.0


def test_no_sentences_is_unmeasured_not_zero_words() -> None:
    assert sentence_length(segmented(heading="only a title")) == 0.0
    assert sentence_length(segmented("   ")) == 0.0


# Placing a text.


@pytest.mark.parametrize(
    ("difficulty", "sentence", "level"),
    [
        (10, 7.0, Level.aleph),
        # Under both floors is easier, not unplaceable.
        (2, 3.0, Level.aleph),
        # Easy words, long sentences: the share alone would have called this Easy.
        (10, 12.0, Level.bet),
        # Short sentences, hard words.
        (18, 7.0, Level.bet),
        (25, 7.0, Level.gimel),
        (10, 20.0, Level.gimel),
    ],
)
def test_a_text_is_placed_by_both_halves(difficulty: int, sentence: float, level: Level) -> None:
    assert levelmap.place(difficulty, sentence) == level


def test_zero_on_either_half_is_unmeasured() -> None:
    assert levelmap.place(0, 7.0) is None
    assert levelmap.place(10, 0.0) is None


def test_the_easy_spec_keeps_its_floors_and_its_length() -> None:
    assert levelmap.meets_easy(10, 7.0, 2)
    assert not levelmap.meets_easy(2, 7.0, 2), "under the share's floor"
    assert not levelmap.meets_easy(10, 3.0, 2), "under the sentence floor"
    assert not levelmap.meets_easy(10, 7.0, 4), "too long to finish in a sitting"
    assert not levelmap.meets_easy(10, 7.0, 0)


def test_medium_is_asked_the_way_the_library_asks() -> None:
    assert levelmap.medium("video:abc", spoken=nothing, video=nothing) == "video"
    assert levelmap.medium("recording", spoken=lambda s: True, video=lambda s: True) == "video"
    assert levelmap.medium("dialogue:1", spoken=lambda s: True, video=nothing) == "audio"
    assert levelmap.medium("url:x", spoken=nothing, video=nothing) == "text"


# Counting a shelf.


def test_tally_counts_levels_media_and_the_easy_spec() -> None:
    entries = [
        entry("url:a"),
        entry("video:b"),
        entry("url:c", difficulty=25),
        entry("url:d", difficulty=0),
        entry("url:e", words=1000),  # Easy by its bands, too long for the spec
        entry("url:f", language="ru"),
    ]
    shelves = levelmap.tally(entries, sentence=lambda e: e.sentence, spoken=nothing, video=nothing)
    assert list(shelves) == ["he", "ru"], "largest shelf first"
    he = shelves["he"]
    assert he.cells[("aleph", "text")] == 2
    assert he.cells[("aleph", "video")] == 1
    assert he.cells[("gimel", "text")] == 1
    assert he.cells[(levelmap.UNMEASURED, "text")] == 1
    assert he.easy == {"text": 1, "video": 1}
    rows = dict(levelmap.rows(he))
    assert rows["Easy"] == [2, 0, 1, 3]
    assert rows["Unmeasured"] == [1, 0, 0, 1]
    assert rows[f"Easy spec (target {levelmap.TARGET})"] == [1, 0, 1, 2]


def test_a_language_with_no_target_is_counted_and_not_held_to_one() -> None:
    shelves = levelmap.tally(
        [entry("sefaria:Onkelos", language="arc")],
        sentence=lambda e: e.sentence,
        spoken=nothing,
        video=nothing,
    )
    assert not shelves["arc"].targeted
    assert "Easy spec" in dict(levelmap.rows(shelves["arc"]))


# Where a missing sentence length comes from.


def build_at(root: Path, home: str, source: str, *texts: str) -> Path:
    folder = root / home / "text"
    folder.mkdir(parents=True)
    (folder / "document.json").write_text(json.dumps({"source": source}), encoding="utf-8")
    (folder / "segments.json").write_text(segmented(*texts).model_dump_json(), encoding="utf-8")
    return folder


def test_the_catalogue_row_wins(tmp_path: Path) -> None:
    build_at(tmp_path, "library", "url:a", "a b")
    assert levelmap.Sentences(tmp_path)(entry("url:a", sentence=9.0)) == 9.0


def test_a_missing_length_is_read_off_the_build_library_first(tmp_path: Path) -> None:
    build_at(tmp_path, "aaa", "url:a", "a b c d e f")
    build_at(tmp_path, "library", "url:a", "a b")
    assert levelmap.Sentences(tmp_path)(entry("url:a", sentence=0.0)) == 2.0


def test_a_curated_video_is_segmented_on_the_spot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The video shelf keeps its document and not its segmentation, which the box makes
    again for free. So does the map — with the rules, and no download."""
    from targum import segment
    from targum.models import Document

    folder = tmp_path / "videos" / "abc"
    folder.mkdir(parents=True)
    document = Document(source="video:abc", title="t", language="he", ingester="i", blocks=[])
    (folder / "document.json").write_text(document.model_dump_json(), encoding="utf-8")
    made: list[bool] = []

    class Rules:
        def __init__(self, *, auto_download: bool) -> None:
            made.append(auto_download)

    monkeypatch.setattr(segment, "HebrewSegmenter", Rules)
    monkeypatch.setattr(segment, "segment_document", lambda document, segmenter: segmented("a b c"))
    sentences = levelmap.Sentences(tmp_path / "out", tmp_path / "videos")
    assert sentences(entry("video:abc", sentence=0.0)) == 3.0
    assert sentences(entry("video:abc", sentence=0.0)) == 3.0
    assert made == [False], "one segmenter, and it may not download"


def test_nothing_on_disk_is_unmeasured(tmp_path: Path) -> None:
    sentences = levelmap.Sentences(tmp_path / "missing", tmp_path / "missing")
    assert sentences(entry("url:a", sentence=0.0)) == 0.0
    assert sentences(entry("video:zzz", sentence=0.0)) == 0.0
