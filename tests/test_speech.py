"""Speech out: the clip is what is measured, and an unknown price is counted, not guessed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from targum import speech
from targum.errors import TargumError
from targum.usage import Usage


def test_the_seconds_are_read_off_the_clip() -> None:
    two_seconds = speech.wav(b"\x00" * (speech.BYTES_PER_SECOND * 2))
    assert speech.duration(two_seconds) == 2.0
    assert speech.duration(b"not a wav") == 0.0 and speech.duration(b"") == 0.0


def test_no_key_means_no_voice_and_says_where_the_key_goes(monkeypatch: Any) -> None:
    monkeypatch.delenv(speech.KEY, raising=False)
    usable, why = speech.available()
    assert usable is False and speech.KEY in why
    with pytest.raises(TargumError, match="No voice"):
        speech.say("שָׁלוֹם")


def test_render_keeps_the_wav_where_there_is_no_ffmpeg(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(
        speech,
        "say",
        lambda text, voice=speech.VOICE: speech.wav(b"\x00" * speech.BYTES_PER_SECOND),
    )
    monkeypatch.setattr(speech.shutil, "which", lambda name: None)
    clip = speech.render("שָׁלוֹם", tmp_path / "audio" / "c-1")
    assert clip.path == tmp_path / "audio" / "c-1.wav" and clip.kind == "audio/wav"
    assert clip.seconds == 1.0 and clip.path.is_file()


def test_the_voice_is_counted_and_not_priced() -> None:
    """No rate is written for it yet, and `usage.py` says an unknown price is counted
    rather than invented. The day one is read off the console it goes beside
    `transcribe.PRICES`, and this test changes."""
    spent = Usage()
    spent.add_seconds(speech.NAME, 90.0)
    assert spent.cost() == 0.0 and spent.state()["seconds"] == 90.0


def test_many_lines_become_one_clip_with_exact_spans(monkeypatch: Any, tmp_path: Path) -> None:
    """targum-internal#246: one request a line, the seconds of each read off its own WAV,
    so a section's spans need no aligner; an empty line takes no time."""
    lengths = {"א": 1, "ב": 2, "": 0}
    monkeypatch.setattr(
        speech,
        "say",
        lambda text, voice=speech.VOICE: speech.wav(
            b"\x00" * (speech.BYTES_PER_SECOND * lengths[text])
        ),
    )
    monkeypatch.setattr(speech.shutil, "which", lambda name: None)
    clip, spans = speech.render_lines(["א", "", "ב"], tmp_path / "audio" / "voice-001")
    assert spans == [(0.0, 1.0), (1.0, 1.0), (1.0, 3.0)]
    assert clip.seconds == 3.0 and clip.path.name == "voice-001.wav" and clip.path.is_file()
    assert speech.duration(clip.path.read_bytes()) == 3.0


def test_the_voice_is_for_sale_only_once_it_has_a_price(monkeypatch: Any) -> None:
    """Decided 2026-09-10 (targum-internal#246): nothing on a page offers the voice
    until its rate is beside `transcribe.PRICES`."""
    from targum import transcribe

    assert speech.priced() is False
    monkeypatch.setitem(transcribe.PRICES, speech.NAME, 0.02)
    assert speech.priced() is True
