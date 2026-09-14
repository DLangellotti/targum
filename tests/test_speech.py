"""Speech out: the clip is what is measured, and it costs its seconds at the voice's rate."""

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
    with pytest.raises(TargumError, match="can't make a voice"):
        speech.say("שָׁלוֹם")


def test_render_keeps_the_wav_where_there_is_no_ffmpeg(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setattr(
        speech,
        "say",
        lambda text, voice=speech.VOICE, language="he": speech.wav(
            b"\x00" * speech.BYTES_PER_SECOND
        ),
    )
    monkeypatch.setattr(speech.shutil, "which", lambda name: None)
    clip = speech.render("שָׁלוֹם", tmp_path / "audio" / "c-1")
    assert clip.path == tmp_path / "audio" / "c-1.wav" and clip.kind == "audio/wav"
    assert clip.seconds == 1.0 and clip.path.is_file()


def test_the_voice_is_priced_by_the_minute_of_speech() -> None:
    """$20 per million audio tokens at 25 a second is $0.03 a minute (2026-09-13). Until
    that day it was counted and charged nothing, and no money ceiling could see it."""
    spent = Usage()
    spent.add_seconds(speech.NAME, 90.0)
    assert spent.cost() == pytest.approx(0.045) and spent.state()["seconds"] == 90.0


def test_the_voice_is_not_a_transcriber() -> None:
    """Its row lives beside the voice. `transcribe.PRICES`'s dearest row is the rate a
    recording is quoted at when no transcriber has a key, and speech in that table would
    have raised every such quote."""
    from targum import transcribe

    assert speech.NAME not in transcribe.PRICES and speech.NAME in speech.PRICES


def test_a_voice_that_stops_part_way_says_how_much_it_made(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """Google charges for each line said. When the third fails the first two were paid
    for, and the worker has to know to settle them rather than release the claim."""

    def say(text: str, voice: str = speech.VOICE, language: str = "he") -> bytes:
        if text == "ג":
            raise TargumError("The voice did not answer.", "Try again in a moment.")
        return speech.wav(b"\x00" * speech.BYTES_PER_SECOND * 2)

    monkeypatch.setattr(speech, "say", say)
    monkeypatch.setattr(speech.shutil, "which", lambda name: None)
    with pytest.raises(speech.Interrupted) as stopped:
        speech.render_lines(["א", "ב", "ג"], tmp_path / "audio" / "voice-001")
    assert stopped.value.seconds == 4.0 and stopped.value.message == "The voice did not answer."

    def unwritable(spoken: bytes, into: Path) -> speech.Clip:
        raise OSError("disk full")

    monkeypatch.setattr(speech, "write", unwritable)
    with pytest.raises(speech.Interrupted) as lost:
        speech.render("א", tmp_path / "audio" / "c-1")
    assert lost.value.seconds == 2.0, "said, paid for, and not kept"


def test_many_lines_become_one_clip_with_exact_spans(monkeypatch: Any, tmp_path: Path) -> None:
    """targum-internal#246: one request a line, the seconds of each read off its own WAV,
    so a section's spans need no aligner; an empty line takes no time."""
    lengths = {"א": 1, "ב": 2, "": 0}
    monkeypatch.setattr(
        speech,
        "say",
        lambda text, voice=speech.VOICE, language="he": speech.wav(
            b"\x00" * (speech.BYTES_PER_SECOND * lengths[text])
        ),
    )
    monkeypatch.setattr(speech.shutil, "which", lambda name: None)
    clip, spans = speech.render_lines(["א", "", "ב"], tmp_path / "audio" / "voice-001")
    assert spans == [(0.0, 1.0), (1.0, 1.0), (1.0, 3.0)]
    assert clip.seconds == 3.0 and clip.path.name == "voice-001.wav" and clip.path.is_file()
    assert speech.duration(clip.path.read_bytes()) == 3.0


def test_the_voice_is_for_sale_only_while_it_has_a_price(monkeypatch: Any) -> None:
    """Decided 2026-09-10 (targum-internal#246): nothing on a page offers the voice
    without its rate in `speech.PRICES`."""
    assert speech.priced() is True
    monkeypatch.delitem(speech.PRICES, speech.NAME)
    assert speech.priced() is False


def test_the_voice_is_told_which_language_it_is_reading() -> None:
    """French, Russian and Italian since 2026-09-13; Hebrew's instruction is unchanged,
    and a language the voice does not read is refused rather than read as Hebrew."""
    assert speech.ask("he") == speech.ASK
    assert speech.ask("fr-FR").startswith("Read this French aloud")
    assert speech.ask("ru").startswith("Read this Russian aloud")
    assert speech.speaks("it") and not speech.speaks("yi") and not speech.speaks("arc")
    with pytest.raises(TargumError, match="can't read that language aloud"):
        speech.say("װאָס", language="yi")
