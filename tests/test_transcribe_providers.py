"""The paid transcribers, exercised against canned answers so the suite costs nothing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from targum.transcribe.elevenlabs import ScribeTranscriber
from targum.transcribe.openai_whisper import WhisperTranscriber


class Answers:
    """Stands in for httpx.Client: every post returns the next canned answer."""

    def __init__(self, answers: list[dict[str, Any]]) -> None:
        self.answers = list(answers)
        self.asked: list[dict[str, Any]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Answers:
        return self

    def __enter__(self) -> Answers:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def post(self, url: str, **kwargs: Any) -> Answers:
        self.asked.append({"url": url, **{k: v for k, v in kwargs.items() if k != "files"}})
        self.body = self.answers.pop(0)
        return self

    @property
    def status_code(self) -> int:
        return 200

    @property
    def text(self) -> str:
        return json.dumps(self.body)

    def json(self) -> dict[str, Any]:
        return self.body


def canned(monkeypatch: pytest.MonkeyPatch, answers: list[dict[str, Any]]) -> Answers:
    import httpx

    stub = Answers(answers)
    monkeypatch.setattr(httpx, "Client", stub)
    return stub


def test_whisper_words_are_read_from_verbose_json_and_hallucinated_segments_dropped(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """whisper invents fluent text over silence and confesses in the segment's
    no-speech probability; a reader cannot tell an invented sentence from a heard one."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    recording = tmp_path / "part.mp3"
    recording.write_bytes(b"audio")
    canned(
        monkeypatch,
        [
            {
                "language": "hebrew",
                "duration": 10.0,
                "words": [
                    {"word": "שלום", "start": 0.0, "end": 0.5},
                    {"word": "עולם", "start": 0.6, "end": 1.0},
                    {"word": "invented", "start": 5.0, "end": 5.5},
                ],
                "segments": [
                    {"start": 0.0, "end": 2.0, "no_speech_prob": 0.1, "avg_logprob": -0.2},
                    {"start": 4.0, "end": 6.0, "no_speech_prob": 0.9, "avg_logprob": -0.4},
                ],
            }
        ],
    )
    heard = WhisperTranscriber().transcribe(recording, "he")
    assert [word.text for word in heard.words] == ["שלום", "עולם"]
    assert heard.language == "he"
    assert heard.duration == 10.0


def test_a_part_over_the_api_ceiling_is_chunked_and_its_timings_offset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_audio
) -> None:
    """The API refuses files over 25 MB; the part is cut at pauses and each chunk's
    words come back on the part's own clock."""
    from targum.transcribe import openai_whisper

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(openai_whisper, "MAX_BYTES", 4)
    recording = tmp_path / "part.mp3"
    recording.write_bytes(b"12345678")  # two chunks
    fake_audio.duration = 100.0
    fake_audio.pauses = [(49.0, 51.0)]
    answer = {
        "language": "hebrew",
        "duration": 50.0,
        "words": [{"word": "מילה", "start": 1.0, "end": 2.0}],
        "segments": [],
    }
    canned(monkeypatch, [answer, dict(answer)])
    heard = WhisperTranscriber().transcribe(recording, "he")
    assert [word.start for word in heard.words] == [1.0, 51.0]
    assert heard.duration == 100.0


def test_scribe_audio_events_are_marked_and_speakers_numbered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Music is not speech, and a diarized voice becomes a number a page can show
    without pretending to know anybody's name."""
    monkeypatch.setenv("ELEVENLABS_API_KEY", "xi-test")
    recording = tmp_path / "part.mp3"
    recording.write_bytes(b"audio")
    canned(
        monkeypatch,
        [
            {
                "language_code": "he",
                "words": [
                    {
                        "text": "שלום",
                        "start": 0.0,
                        "end": 0.5,
                        "type": "word",
                        "speaker_id": "speaker_3",
                    },
                    {"text": " ", "start": 0.5, "end": 0.6, "type": "spacing"},
                    {"text": "(music)", "start": 1.0, "end": 4.0, "type": "audio_event"},
                    {
                        "text": "היי",
                        "start": 5.0,
                        "end": 5.4,
                        "type": "word",
                        "speaker_id": "speaker_0",
                    },
                ],
            }
        ],
    )
    engine = ScribeTranscriber()
    heard = engine.transcribe(recording, "he")
    spoken = [word for word in heard.words if not word.event]
    assert [(word.text, word.speaker) for word in spoken] == [("שלום", "1"), ("היי", "2")]
    assert any(word.event for word in heard.words)
    assert engine.spent.seconds_by_model["elevenlabs/scribe_v2"] == pytest.approx(5.4)


def test_each_provider_says_which_key_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    usable, fix = WhisperTranscriber().available()
    assert not usable and "OPENAI_API_KEY" in fix
    usable, fix = ScribeTranscriber().available()
    assert not usable and "ELEVENLABS_API_KEY" in fix
