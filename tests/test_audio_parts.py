"""How a recording divides into parts.

The boundaries decide what a page carries and what a transcript keys on, so what is
tested is that they are deterministic, honest about their origin, and never moved once
work has hung off them.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from targum.audio import parts, probe, tools
from targum.audio.probe import Mark, Probe
from targum.errors import TargumError


def described(duration: float, chapters: list[tuple[float, float, str]] | None = None) -> Probe:
    return Probe(
        duration=duration,
        sha256="abc",
        chapters=[Mark(start=a, end=b, title=t) for a, b, t in chapters or []],
    )


def test_an_unchaptered_hour_is_cut_into_parts_of_about_twelve_minutes_at_the_longest_pause(
    fake_audio, tmp_path: Path
) -> None:
    """An hour with no marks is five parts, and each seam lands mid-pause."""
    drafted = parts.plan(described(3600.0))
    assert len(drafted.parts) == 5
    assert not drafted.settled
    fake_audio.pauses = [(715.0, 717.0), (1439.0, 1441.0), (2160.5, 2161.5), (2880.0, 2882.0)]
    settled = parts.settle(tmp_path / "source.mp3", drafted, None)
    assert settled.settled
    assert [round(span.start, 1) for span in settled.parts] == [0.0, 716.0, 1440.0, 2161.0, 2881.0]
    assert [round(span.end, 1) for span in settled.parts][:-1] == [716.0, 1440.0, 2161.0, 2881.0]


def test_the_number_of_parts_is_fixed_before_a_single_pause_is_looked_for() -> None:
    """K comes from arithmetic alone, so the plan a page was priced on cannot grow."""
    drafted = parts.plan(described(3600.0))
    assert len(drafted.parts) == 5
    assert all(span.snap_start for span in drafted.parts[1:])
    assert not drafted.parts[0].snap_start


def test_chapter_marks_name_the_parts_and_short_marks_are_merged_forward() -> None:
    """A ten-second announcement is not a chapter; the chapter it introduces keeps
    its own name."""
    drafted = parts.plan(
        described(1800.0, [(0.0, 30.0, "Intro"), (30.0, 900.0, "One"), (900.0, 1800.0, "Two")])
    )
    assert drafted.origin == "marks"
    assert drafted.settled
    assert [(span.start, span.end, span.title) for span in drafted.parts] == [
        (0.0, 900.0, "One"),
        (900.0, 1800.0, "Two"),
    ]


def test_a_forty_minute_chapter_is_split_so_no_page_carries_more_than_twenty_minutes() -> None:
    """A one-file reader carries its part whole, so a part has a ceiling."""
    drafted = parts.plan(described(2400.0, [(0.0, 2400.0, "One")]))
    assert len(drafted.parts) == 3
    assert all(span.end - span.start <= parts.MAX_PART_S for span in drafted.parts)
    assert [span.title for span in drafted.parts] == ["One · 1", "One · 2", "One · 3"]
    assert not drafted.settled


def test_settling_the_pauses_is_deterministic_for_the_same_file(fake_audio, tmp_path: Path) -> None:
    """The same recording settles the same way twice; nothing depends on the clock."""
    fake_audio.pauses = [(700.0, 704.0), (1500.0, 1501.0)]
    one = parts.settle(tmp_path / "a.mp3", parts.plan(described(1440.0)), None)
    two = parts.settle(tmp_path / "a.mp3", parts.plan(described(1440.0)), None)
    assert one.model_dump() == two.model_dump()


def test_a_recording_over_twelve_hours_is_refused_with_a_reason(fake_audio, tmp_path: Path) -> None:
    fake_audio.duration = 50_000.0
    recording = tmp_path / "long.mp3"
    recording.write_bytes(b"audio")
    with pytest.raises(TargumError, match="over 12 hours"):
        probe.examine(recording)


def test_a_file_ffprobe_cannot_read_is_one_plain_sentence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """ffprobe's stderr is for the terminal; the reader gets a sentence."""

    def refuse(args: object, **kwargs: object) -> None:
        raise subprocess.CalledProcessError(1, "ffprobe")

    monkeypatch.setattr(subprocess, "run", refuse)
    with pytest.raises(TargumError, match="could not read this audio file"):
        tools.ffprobe_json(tmp_path / "noise.mp3")


def test_a_video_container_is_refused(fake_audio, tmp_path: Path) -> None:
    """A film with a soundtrack is a different product; cover art is not a film."""
    original = fake_audio.probe

    def with_video(path: object) -> dict:
        answer = original(path)
        answer["streams"].append({"codec_type": "video", "disposition": {"attached_pic": 0}})
        return answer

    from targum.audio import tools as tools_module

    recording = tmp_path / "film.m4a"
    recording.write_bytes(b"video")
    import pytest as _pytest

    with _pytest.MonkeyPatch.context() as patch:
        patch.setattr(tools_module, "ffprobe_json", with_video)
        with pytest.raises(TargumError, match="could not read"):
            probe.examine(recording)


def test_a_protected_audiobook_is_refused_by_name(tmp_path: Path) -> None:
    locked = tmp_path / "book.aax"
    locked.write_bytes(b"drm")
    with pytest.raises(TargumError, match="protected"):
        probe.examine(locked)
