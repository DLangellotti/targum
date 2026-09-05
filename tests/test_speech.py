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
