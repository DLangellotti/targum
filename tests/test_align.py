"""The aligner's logic, against a deterministic encoder so the suite runs offline."""

from __future__ import annotations

import pytest

from targum.align import Aligner, to_translation
from targum.align.base import (
    Candidate,
    align_sequences,
    length_penalty,
    length_ratio,
    to_links,
)
from targum.align.score import as_indices, score
from targum.models import BlockKind, Segment, SegmentedDocument


class WordOverlapEncoder:
    """Similarity by shared words. Crude, deterministic, and needs no model."""

    name = "overlap/test"

    def similarity(self, source, target):  # type: ignore[no-untyped-def]
        def words(text: str) -> set[str]:
            return set(text.lower().replace(".", "").replace(",", "").split())

        return [
            [len(words(s) & words(t)) / max(1, len(words(s) | words(t))) for t in target]
            for s in source
        ]


def document(rows: list[tuple[int, int, str]], language: str, kind=BlockKind.paragraph):
    segments = [
        Segment(
            id=f"{block:04d}.{index:03d}-x{n:04d}",
            block_id=f"b{block:04d}",
            block_index=block,
            index=index,
            kind=kind,
            text=text,
        )
        for n, (block, index, text) in enumerate(rows)
    ]
    return SegmentedDocument(
        document_hash=f"h-{language}", language=language, segmenter="fake/1", segments=segments
    )


def aligner() -> Aligner:
    return Aligner(encoder=WordOverlapEncoder())


# --- the length prior --------------------------------------------------------


def test_ratio_is_measured_not_assumed() -> None:
    # Hebrew says in fewer characters what English needs more of. A prior tuned on
    # European pairs would call every correct Hebrew link too short.
    ratio = length_ratio(["בארץ־ישראל קם העם היהודי"], ["The Land of Israel was the birthplace"])
    assert ratio > 1.4


def test_ratio_survives_an_empty_side() -> None:
    assert length_ratio([], ["text"]) == 1.0
    assert length_ratio(["text"], []) == 1.0


def test_penalty_is_zero_at_the_expected_length() -> None:
    assert length_penalty(100, 150, 1.5) == pytest.approx(0.0, abs=0.01)


def test_penalty_grows_with_divergence() -> None:
    close = length_penalty(100, 150, 1.5)
    far = length_penalty(100, 400, 1.5)
    assert far > close


# --- link shapes -------------------------------------------------------------


def test_finds_a_one_to_one_run() -> None:
    source = ["the cat sat", "the dog ran", "the bird flew"]
    target = ["the cat sat", "the dog ran", "the bird flew"]
    encoder = WordOverlapEncoder()
    links = align_sequences(source, target, encoder.similarity(source, target), 1.0)
    assert [(c.source, c.target) for c in links] == [([0], [0]), ([1], [1]), ([2], [2])]


def test_finds_a_merge() -> None:
    source = ["the dog ran fast", "then it slept"]
    target = ["the dog ran fast then it slept"]
    encoder = WordOverlapEncoder()
    links = align_sequences(source, target, encoder.similarity(source, target), 1.0)
    assert [(c.source, c.target) for c in links] == [([0, 1], [0])]


def test_finds_a_split() -> None:
    source = ["the dog ran fast then it slept"]
    target = ["the dog ran fast", "then it slept"]
    encoder = WordOverlapEncoder()
    links = align_sequences(source, target, encoder.similarity(source, target), 1.0)
    assert [(c.source, c.target) for c in links] == [([0], [0, 1])]


def test_an_unrelated_sentence_is_not_absorbed_into_its_neighbour() -> None:
    # Two lines a translator dropped are cheaper to staple onto the next sentence than
    # to pay the null penalty twice, unless a merge has to justify every member.
    source = ["in congress july 1776", "the unanimous declaration", "when in the course of events"]
    target = ["when in the course of events"]
    encoder = WordOverlapEncoder()
    links = align_sequences(source, target, encoder.similarity(source, target), 1.0)
    paired = [c for c in links if c.source and c.target]
    assert len(paired) == 1
    assert paired[0].source == [2]


def test_confidence_falls_when_lengths_disagree() -> None:
    source = ["the cat sat on the mat"]
    long_target = ["the cat sat on the mat " * 8]
    encoder = WordOverlapEncoder()
    good = align_sequences(source, source, encoder.similarity(source, source), 1.0)
    bad = align_sequences(source, long_target, encoder.similarity(source, long_target), 1.0)
    assert good[0].confidence > bad[0].confidence


# --- the two-pass aligner ----------------------------------------------------


def test_pairs_sentences_inside_matching_blocks() -> None:
    source = document([(0, 0, "the cat sat"), (1, 0, "the dog ran"), (2, 0, "the bird flew")], "en")
    target = document([(0, 0, "the cat sat"), (1, 0, "the dog ran"), (2, 0, "the bird flew")], "en")
    alignment = aligner().align(source, target, "Test")
    assert [link.kind for link in alignment.links] == ["1:1", "1:1", "1:1"]
    assert alignment.coverage() == 1.0


def test_block_anchoring_is_skipped_when_structures_disagree() -> None:
    from targum.align import comparable_structure

    assert comparable_structure(20, 22)
    assert not comparable_structure(5, 37)  # one side transcribed as a single run
    assert not comparable_structure(2, 2)  # too few blocks to anchor on


def test_a_translation_with_no_paragraphs_still_aligns() -> None:
    rows = [
        (i, 0, text)
        for i, text in enumerate(
            ["the cat sat", "the dog ran", "the bird flew", "the fish swam", "the horse stood"]
        )
    ]
    source = document(rows, "en")
    target = document(
        [
            (0, i, text)
            for i, text in enumerate(
                ["the cat sat", "the dog ran", "the bird flew", "the fish swam", "the horse stood"]
            )
        ],
        "en",
    )
    alignment = aligner().align(source, target, "Test")
    assert alignment.coverage() == 1.0
    assert len(alignment.links) == 5


def test_records_its_provenance() -> None:
    source = document([(0, 0, "one"), (1, 0, "two"), (2, 0, "three")], "he")
    target = document([(0, 0, "one"), (1, 0, "two"), (2, 0, "three")], "en")
    alignment = aligner().align(source, target, "Some Edition")
    assert alignment.name == "Some Edition"
    assert alignment.source_language == "he"
    assert alignment.target_language == "en"
    assert "overlap/test" in alignment.aligner


# --- projecting into the reader ----------------------------------------------


def test_every_source_segment_gets_text() -> None:
    source = document([(0, 0, "the cat sat"), (1, 0, "the dog ran"), (2, 0, "the bird flew")], "en")
    target = document([(0, 0, "the cat sat"), (1, 0, "the dog ran"), (2, 0, "the bird flew")], "en")
    alignment = aligner().align(source, target, "Test")
    translation = to_translation(alignment, target)
    assert set(translation.segments) == {segment.id for segment in source.segments}
    assert translation.kind == "aligned"


def test_a_merge_shows_the_same_text_on_both_sources() -> None:
    source = document([(0, 0, "the dog ran fast"), (0, 1, "then it slept")], "en")
    target = document([(0, 0, "the dog ran fast then it slept")], "en")
    translation = to_translation(aligner().align(source, target, "T"), target)
    assert len(set(translation.segments.values())) == 1


def test_coarse_regions_are_carried_through() -> None:
    from targum.models import Alignment, Link

    target = document([(0, 0, "some text")], "en")
    alignment = Alignment(
        name="T",
        document_hash="h",
        translation_hash="h2",
        source_language="he",
        target_language="en",
        aligner="test",
        links=[
            Link(source=["s1", "s2"], target=[target.segments[0].id], confidence=0.2, coarse=True)
        ],
    )
    translation = to_translation(alignment, target)
    assert set(translation.coarse) == {"s1", "s2"}
    assert translation.confidence["s1"] == 0.2


# --- scoring -----------------------------------------------------------------


def test_scoring_counts_strict_and_pairwise_separately() -> None:
    gold = [((0,), (0,)), ((1,), (1, 2)), ((2,), (3,))]
    # The middle link finds only half of a split: wrong strictly, half right pairwise.
    predicted = [((0,), (0,)), ((1,), (1,)), ((2,), (3,))]
    result = score(predicted, gold, "test")
    assert result.strict_recall == pytest.approx(2 / 3)
    assert result.pair_recall == pytest.approx(3 / 4)
    assert result.pair_precision == 1.0


def test_scoring_tracks_nulls_separately() -> None:
    gold = [((0,), (0,)), ((1,), ())]
    assert score([((0,), (0,)), ((1,), ())], gold, "t").null_recall == 1.0
    assert score([((0,), (0,)), ((1,), (1,))], gold, "t").null_recall == 0.0


def test_indices_come_back_in_gold_form() -> None:
    links = to_links(
        [Candidate([0], [0, 1], 0.9)],
        document([(0, 0, "a")], "he").segments,
        document([(0, 0, "b"), (0, 1, "c")], "en").segments,
    )
    source_ids = [s.id for s in document([(0, 0, "a")], "he").segments]
    target_ids = [s.id for s in document([(0, 0, "b"), (0, 1, "c")], "en").segments]
    assert as_indices(links, source_ids, target_ids) == [((0,), (0, 1))]
