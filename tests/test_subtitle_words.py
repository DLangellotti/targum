"""Word clocks for a subtitle-timed video, from the aligner on the laptop (#572).

The aligner is faked: what is under test is what is done with its answer — which words
keep a clock, what the manifest then says, and that the text never moves.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from targum.audio import manifest as manifest_module
from targum.audio.align import MATCH_FLOOR
from targum.audio.subtitle_words import (
    CUE_SLACK_S,
    WORD_FLOOR,
    aligned_name,
    kept_lines,
    retime_folder,
    retimed,
    tokens,
)
from targum.errors import TargumError
from targum.ids import audio_block_id
from targum.ingest.subtitles import Cue, refined_from
from targum.models import Segment, SegmentedDocument
from targum.transcribe.models import Refined
from targum.transcribe.models import load as load_model
from targum.transcribe.models import write as write_model

#: Two cues, and the sentence break inside the second: a cue runs across sentences.
CUES = [
    Cue(start=10.0, end=12.0, text="אני רוצה ללכת"),
    Cue(start=12.0, end=15.0, text="הביתה. אתה בא"),
]
#: Where the aligner puts each of the six words, and how sure it was.
SURE = -0.05


def heard(*rows: tuple[float, float, float]) -> list[tuple[float, float, float]]:
    return list(rows)


GOOD = heard(
    (10.1, 10.4, SURE),
    (10.4, 10.9, SURE),
    (11.0, 11.6, SURE),
    (12.1, 12.8, SURE),
    (13.2, 13.6, SURE),
    (13.6, 14.0, SURE),
)


class Fake:
    name = "ctc-fake/1"

    def __init__(self, rows: list[tuple[float, float, float]]) -> None:
        self.rows = rows
        self.asked: list[list[str]] = []

    def align(self, audio: Path, words: list[str], language: str):
        self.asked.append(words)
        return self.rows


def folder(tmp_path: Path, provider: str = "subtitles") -> Path:
    refined = refined_from(CUES, language="he")
    refined.provider = provider
    write_model(tmp_path / "audio" / "refined" / "part-001.json", refined)
    (tmp_path / "audio" / "parts").mkdir(parents=True)
    (tmp_path / "audio" / "parts" / "part-001.mp3").write_bytes(b"x")
    block = audio_block_id(1, 1)
    segments = [
        Segment(
            id="10001.000-aaaaaa",
            block_id=block,
            block_index=10001,
            index=0,
            text="אני רוצה ללכת הביתה.",
            ref="part 1:1",
        ),
        Segment(
            id="10001.001-bbbbbb",
            block_id=block,
            block_index=10001,
            index=1,
            text="אתה בא",
            ref="part 1:1",
        ),
    ]
    SegmentedDocument(
        document_hash="h", language="he", segmenter="test/1", segments=segments
    ).write(tmp_path / "segments.json")
    manifest_module.write(
        tmp_path,
        manifest_module.AudioManifest(
            source="source.mp4",
            sha256="s",
            duration=20.0,
            language="he",
            parts=[
                manifest_module.ManifestPart(
                    number=1,
                    start=0.0,
                    end=20.0,
                    audio="audio/parts/part-001.mp3",
                    transcribed=True,
                    provider=provider,
                    refiner="subtitles/1",
                    # What the build made of the cues: every word the cue's clock.
                    spans={"10001.000-aaaaaa": [10.0, 15.0], "10001.001-bbbbbb": [12.0, 15.0]},
                )
            ],
        ),
    )
    return tmp_path


def test_every_sure_word_gets_its_own_clock_and_the_text_stays(tmp_path) -> None:
    built = folder(tmp_path)
    fake = Fake(GOOD)
    report = retime_folder(built, fake)
    assert fake.asked == [["אני", "רוצה", "ללכת", "הביתה.", "אתה", "בא"]]
    assert (report.words, report.kept) == (6, 6)
    fresh = load_model(Refined, built / "audio" / "refined" / "part-001.json")
    assert fresh is not None
    assert fresh.refiner == aligned_name("ctc-fake/1")
    assert fresh.provider == "subtitles", "the words are still the subtitles'"
    assert fresh.paragraphs[0].text == "אני רוצה ללכת הביתה. אתה בא"
    assert [w.text for w in fresh.paragraphs[0].words] == tokens(fresh)
    part = manifest_module.load(built).parts[0]
    assert part.words == {
        "10001.000-aaaaaa": [
            [0, 3, 10.1, 10.4],
            [4, 8, 10.4, 10.9],
            [9, 13, 11.0, 11.6],
            [14, 20, 12.1, 12.8],
        ],
        "10001.001-bbbbbb": [[0, 3, 13.2, 13.6], [4, 6, 13.6, 14.0]],
    }
    # The two lines no longer overlap: each ends where its own last word does.
    assert part.spans == {"10001.000-aaaaaa": [10.1, 12.8], "10001.001-bbbbbb": [13.2, 14.0]}
    assert part.refiner == aligned_name("ctc-fake/1")


def test_a_word_the_aligner_was_unsure_of_keeps_no_clock(tmp_path) -> None:
    built = folder(tmp_path)
    rows = list(GOOD)
    rows[1] = (10.4, 10.9, WORD_FLOOR - 0.5)  # scored low
    rows[4] = (15.0 + CUE_SLACK_S + 1, 15.0 + CUE_SLACK_S + 2, SURE)  # far outside its cue
    report = retime_folder(built, Fake(rows))
    assert report.kept == 4
    fresh = load_model(Refined, built / "audio" / "refined" / "part-001.json")
    words = fresh.paragraphs[0].words
    # No length, standing at the clock before it, so the line's span is unharmed.
    assert (words[1].start, words[1].end) == (10.4, 10.4)
    assert (words[4].start, words[4].end) == (12.8, 12.8)
    part = manifest_module.load(built).parts[0]
    assert [row[:2] for row in part.words["10001.000-aaaaaa"]] == [[0, 3], [9, 13], [14, 20]]
    assert [row[:2] for row in part.words["10001.001-bbbbbb"]] == [[4, 6]]
    assert part.spans["10001.001-bbbbbb"] == [12.8, 14.0]


def test_a_word_just_outside_its_cue_is_believed(tmp_path) -> None:
    """A cue's edges are set by ear: a word a little past them is still the word."""
    rows = list(GOOD)
    rows[3] = (12.0 - CUE_SLACK_S + 0.1, 12.6, SURE)
    fresh, kept = retimed(refined_from(CUES, language="he"), rows, "ctc-fake/1")
    assert kept == 6


def test_a_part_that_matches_its_recording_badly_is_left_as_its_cues(tmp_path) -> None:
    built = folder(tmp_path)
    before = (built / "audio.json").read_text()
    rows = [(start, end, MATCH_FLOOR - 1) for start, end, _ in GOOD]
    report = retime_folder(built, Fake(rows))
    assert "matched its recording" in report.parts[0].skipped
    assert (built / "audio.json").read_text() == before
    kept = load_model(Refined, built / "audio" / "refined" / "part-001.json")
    assert kept.refiner == "subtitles/1"


def test_a_second_run_and_a_heard_part_are_left_alone(tmp_path) -> None:
    built = folder(tmp_path)
    retime_folder(built, Fake(GOOD))
    again = Fake(GOOD)
    report = retime_folder(built, again)
    assert again.asked == [] and report.parts[0].skipped == "already re-timed"

    heard_part = folder(tmp_path / "heard", provider="")
    other = Fake(GOOD)
    assert "not subtitles" in retime_folder(heard_part, other).parts[0].skipped
    assert other.asked == []


def test_cues_that_do_not_spell_the_text_are_refused() -> None:
    refined = refined_from(CUES, language="he")
    refined.paragraphs[0].text = "אני רוצה ללכת הביתה. אתה לא בא"
    with pytest.raises(TargumError):
        retimed(refined, GOOD + [(14.0, 14.2, SURE)], "ctc-fake/1")


def test_a_line_with_no_sure_word_keeps_what_its_cues_leave(tmp_path) -> None:
    """A lone «כן.» over the other voice: no word of it is sure, so the aligner gives it
    no span, and it keeps the stretch of its cue its aligned neighbours leave."""
    built = folder(tmp_path)
    segmented = SegmentedDocument.model_validate_json((built / "segments.json").read_text())
    first, second = (segment.id for segment in segmented.segments)
    assert kept_lines(
        segmented, {first: [10.0, 15.0], second: [12.0, 15.0]}, {first: [10.1, 12.8]}
    ) == {
        first: [10.1, 12.8],
        second: [12.8, 15.0],
    }
    # Where the neighbours leave nothing of it, it has no span rather than an overlap.
    assert kept_lines(
        segmented, {first: [10.0, 12.0], second: [12.0, 12.5]}, {first: [10.1, 12.8]}
    ) == {first: [10.1, 12.8]}
