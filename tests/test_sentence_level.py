"""How hard a sentence is (targum-internal#320): the asking, the keeping, and the passage
`suggest_next` points into. Offline throughout — the model is never reached; its answers
are written in by hand the shape the API returns them."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from targum import level, sentence_level
from targum.ids import segment_id
from targum.models import BlockKind, Segment, SegmentedDocument
from targum.vocalize.base import has_taamim, strip_taamim


def test_the_levels_are_the_ulpan_ladder_and_one_past_it() -> None:
    names = [name for name, _ in sentence_level.LEVELS]
    assert names[:-1] == [rung.name for rung in level.ULPAN]
    assert sentence_level.BEYOND == len(names) - 1
    # The API takes at most ten levels in a Score.
    assert len(names) <= 10


def test_no_level_narrates_where_it_sits() -> None:
    """#318: a description that says where an option sits pulled the answers toward it
    harder than the gap being measured. Levels are judged one at a time, so a comparison
    with a neighbour means nothing to the model anyway."""
    for _, description in sentence_level.LEVELS:
        lowered = description.lower()
        for word in ("easier", "harder", "previous", "next level", "than the"):
            assert word not in lowered, (word, description)


def test_a_key_is_the_text_and_nothing_else() -> None:
    assert sentence_level.key("שלום.") == sentence_level.key(" שלום. ")
    assert sentence_level.key("שלום.") != sentence_level.key("שלום!")
    assert len(sentence_level.key("x")) == 16


def test_chunks_keep_a_paragraph_whole_and_close_at_the_limit() -> None:
    blocks = [[f"משפט {i}.{j}" for j in range(3)] for i in range(5)]
    got = list(sentence_level.chunks(blocks))
    assert [len(chunk.sentences) for chunk in got] == [6, 6, 3]
    assert got[0].sentences[:3] == blocks[0]
    # A paragraph longer than a request alone is split, never dropped.
    long = [[f"משפט {j}" for j in range(sentence_level.PER_REQUEST + 3)]]
    sizes = [len(chunk.sentences) for chunk in sentence_level.chunks(long)]
    assert sizes == [sentence_level.PER_REQUEST, 3]


def test_the_key_is_of_the_stored_text_and_the_marks_never_travel() -> None:
    """Keyed on the sentence as the reader holds it, so the box finds it; sent without
    its chanting marks, which say how a verse is sung and not what it means."""
    verse = "בְּרֵאשִׁ֖ית בָּרָ֣א אֱלֹהִ֑ים"
    assert has_taamim(verse)
    (chunk,) = sentence_level.chunks([[verse]], show=strip_taamim)
    assert chunk.keys == [sentence_level.key(verse)]
    state, questions = sentence_level.request(chunk)
    assert not has_taamim(json.dumps([state, questions], ensure_ascii=False))
    assert state == {"passage": strip_taamim(verse)}
    (question,) = questions.values()
    assert question["type"] == "score"
    assert question["criteria"] == [
        text for _, text in sentence_level.PROMPTS[sentence_level.PROMPT]
    ]


def test_a_sentence_answered_elsewhere_stays_as_context_and_is_not_asked() -> None:
    (chunk,) = sentence_level.chunks([["אחת.", "שתיים.", "שלוש."]])
    asking = {chunk.keys[1]}
    state, questions = sentence_level.request(chunk, asking)
    assert list(questions) == [chunk.keys[1]]
    assert state["passage"] == "אחת. שתיים. שלוש."


def test_an_answer_is_read_off_its_probabilities() -> None:
    got = sentence_level.answered(
        {"score": 1.4, "confidence": 0.35, "probabilities": {"0": 0.0, "1": 0.6, "2": 0.4}}
    )
    assert got == sentence_level.Level(1, 1.4, 0.35)
    assert got.readable(1) and not got.readable(0)
    assert sentence_level.answered({"choice": "x"}) is None


def test_the_kept_file_round_trips_and_its_absence_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    where = tmp_path / "levels.json"
    monkeypatch.setenv(sentence_level.ENV, str(where))
    assert sentence_level.load() == {}
    kept = {"a" * 16: sentence_level.Level(2, 2.345, 0.8)}
    sentence_level.write(kept, where, "jev-test")
    assert not where.with_name(where.name + ".tmp").exists()
    assert sentence_level.load() == {"a" * 16: sentence_level.Level(2, 2.35, 0.8)}


def built_with_sections(folder: Path, sections: list[list[str]]) -> None:
    """A built text's segments: one heading per section, then its sentences."""
    segments: list[Segment] = []
    block = 0
    for number, sentences in enumerate(sections, start=1):
        heading = f"פרק {number}"
        segments.append(
            Segment(
                id=segment_id(block, 0, heading),
                block_id=f"b{block:04d}",
                block_index=block,
                index=0,
                kind=BlockKind.heading,
                level=2,
                text=heading,
            )
        )
        block += 1
        for text in sentences:
            segments.append(
                Segment(
                    id=segment_id(block, 0, text),
                    block_id=f"b{block:04d}",
                    block_index=block,
                    index=0,
                    kind=BlockKind.verse,
                    text=text,
                )
            )
            block += 1
    folder.mkdir(parents=True, exist_ok=True)
    SegmentedDocument(document_hash="h", language="he", segmenter="test", segments=segments).write(
        folder / "segments.json"
    )


HARD = [f"משפט קשה {i}." for i in range(4)]
EASY = [f"משפט קל {i}." for i in range(4)]


def kept_levels() -> dict[str, sentence_level.Level]:
    out = {sentence_level.key(text): sentence_level.Level(7, 7.1, 0.7) for text in HARD}
    out |= {sentence_level.key(text): sentence_level.Level(0, 0.3, 0.8) for text in EASY}
    return out


def test_the_passage_is_the_section_that_reads_at_the_rung(tmp_path: Path) -> None:
    folder = tmp_path / "text-he"
    built_with_sections(folder, [HARD, EASY])
    found = sentence_level.best_passage(folder, 0, kept_levels())
    assert found is not None
    passage, whole = found
    assert (passage.number, passage.file, passage.share) == (2, "sec-0002.html", 1.0)
    assert whole == 0.5
    # A reader for whom the whole text reads has nothing to be pointed into.
    assert sentence_level.best_passage(folder, 7, kept_levels()) is None
    # Nor does a text nobody has measured.
    assert sentence_level.best_passage(folder, 0, {}) is None


def test_a_section_mostly_unmeasured_is_not_offered(tmp_path: Path) -> None:
    folder = tmp_path / "text-he"
    built_with_sections(folder, [HARD, EASY])
    levels = kept_levels()
    for text in EASY[:2]:
        del levels[sentence_level.key(text)]
    assert sentence_level.best_passage(folder, 0, levels) is None
