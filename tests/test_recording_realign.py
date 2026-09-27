"""Re-aligning an attached recording's words without cutting its parts again.

Offline: the aligner and the decoder are stand-ins. What is tested is the promise the
tool makes. The mp3 and the manifest are untouched, the words are the same words in the
same order, the clocks come back on the part's own timeline, and the aligner hears only
the stretch the stored words were found in.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import pytest

from targum.errors import TargumError
from targum.recording import Part, Recording
from targum.recording.index import MANIFEST
from targum.recording.realign import AFTER_S, BEFORE_S, RATE, realign_folder

SECONDS = 20.0


class Stand:
    """An aligner that puts word n at [n, n + 0.5) seconds into what it hears."""

    name = "stand-in/1"

    def __init__(self) -> None:
        self.heard: list[float] = []
        self.words: list[list[str]] = []

    def align(
        self, audio: Path, words: list[str], language: str
    ) -> list[tuple[float, float, float]]:
        with wave.open(str(audio)) as got:
            assert got.getframerate() == RATE and got.getnchannels() == 1
            self.heard.append(got.getnframes() / RATE)
        self.words.append(list(words))
        return [(float(n), n + 0.5, -0.1) for n in range(len(words))]


def silence(path: Path, rate: int) -> list[float]:
    return [0.0] * int(SECONDS * rate)


def folder(tmp_path: Path) -> Path:
    home = tmp_path / "a-book"
    home.mkdir()
    (home / "part-001.mp3").write_bytes(b"not really an mp3")
    (home / "part-002.mp3").write_bytes(b"left over from an older attach")
    rows = [["אחת", 5.0, 5.4, -0.2], ["שתיים", 5.5, 6.0, -0.3], ["–", 6.0, 6.0, -10.0]]
    (home / "words-001.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    (home / "words-002.json").write_text("[]", encoding="utf-8")
    recording = Recording(
        source="https://example.org/1.txt",
        credit="Somebody (LibriVox)",
        licence="public domain",
        parts=[Part(ref="part 1", audio="part-001.mp3", words="words-001.json", blocks=[0, 3])],
    )
    (home / MANIFEST).write_text(recording.model_dump_json(indent=2), encoding="utf-8")
    return home


def test_the_words_stay_and_only_their_clocks_move(tmp_path: Path) -> None:
    home = folder(tmp_path)
    manifest = (home / MANIFEST).read_bytes()
    audio = (home / "part-001.mp3").read_bytes()
    stand = Stand()

    assert realign_folder(home, stand, read=silence, notify=lambda _: None) == 1

    rows = json.loads((home / "words-001.json").read_text(encoding="utf-8"))
    assert [row[0] for row in rows] == ["אחת", "שתיים", "–"]
    assert stand.words == [["אחת", "שתיים", "–"]]
    # Back on the part's own clock: the window opened BEFORE_S ahead of the first word.
    start = 5.0 - BEFORE_S
    assert rows[0][1:3] == [round(start, 3), round(start + 0.5, 3)]
    assert rows[2][1] == round(start + 2, 3)
    assert (home / MANIFEST).read_bytes() == manifest
    assert (home / "part-001.mp3").read_bytes() == audio


def test_the_aligner_hears_only_the_stretch_the_words_were_found_in(tmp_path: Path) -> None:
    stand = Stand()
    realign_folder(folder(tmp_path), stand, read=silence, notify=lambda _: None)
    assert stand.heard == [pytest.approx(6.0 + AFTER_S - (5.0 - BEFORE_S), abs=1 / RATE)]


def test_files_the_manifest_does_not_name_are_left_alone(tmp_path: Path) -> None:
    home = folder(tmp_path)
    realign_folder(home, Stand(), read=silence, notify=lambda _: None)
    assert (home / "words-002.json").read_text(encoding="utf-8") == "[]"
    assert (home / "part-002.mp3").read_bytes() == b"left over from an older attach"
    assert not list(home.glob("*.tmp"))


def test_the_window_is_clamped_to_the_part(tmp_path: Path) -> None:
    home = folder(tmp_path)
    rows = [["אחת", 0.1, 0.5, -0.2], ["שתיים", 19.8, SECONDS, -0.3]]
    (home / "words-001.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    stand = Stand()
    realign_folder(home, stand, read=silence, notify=lambda _: None)
    assert stand.heard == [pytest.approx(SECONDS, abs=1 / RATE)]
    got = json.loads((home / "words-001.json").read_text(encoding="utf-8"))
    assert got[0][1] == 0.0


def test_a_count_mismatch_refuses_and_writes_nothing(tmp_path: Path) -> None:
    home = folder(tmp_path)
    before = (home / "words-001.json").read_bytes()

    class Short(Stand):
        def align(
            self, audio: Path, words: list[str], language: str
        ) -> list[tuple[float, float, float]]:
            return super().align(audio, words, language)[:-1]

    with pytest.raises(TargumError):
        realign_folder(home, Short(), read=silence, notify=lambda _: None)
    assert (home / "words-001.json").read_bytes() == before


def test_a_folder_without_a_manifest_is_refused(tmp_path: Path) -> None:
    with pytest.raises(TargumError):
        realign_folder(tmp_path, Stand(), read=silence, notify=lambda _: None)
