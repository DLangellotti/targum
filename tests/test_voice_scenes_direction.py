"""`voice_scenes`' director, gaps and levelling (targum-internal#566), with no model
called: the director is a fake, the audio is a made-up tone, and ffmpeg is the only
thing run."""

from __future__ import annotations

import importlib.util
import json
import math
import struct
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "voice_scenes.py"


def load_script() -> Any:
    spec = importlib.util.spec_from_file_location("voice_scenes_direction", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = load_script()


def scene(*lines: tuple[str, str]) -> dict[str, Any]:
    return {
        "id": "t-01",
        "english": "A test",
        "gloss": "Two people talk.",
        "cast": {
            "A": {"voice": "Leda", "gender": "f", "name": "דָּנָה"},
            "B": {"voice": "Orus", "gender": "m", "name": "יוֹנָתָן"},
        },
        "turns": [{"who": who, "text": text, "english": ""} for who, text in lines],
    }


THREE = scene(("A", "שָׁלוֹם, מָה שְׁלוֹמְךָ?"), ("B", "טוֹב, תּוֹדָה."), ("B", "וְאַתְּ?"))


def test_the_director_is_asked_once_and_its_answer_is_kept(tmp_path: Path) -> None:
    asked: list[str] = []

    def ask(text: str, key: str) -> tuple[str, float]:
        asked.append(text)
        return '["Calm, friendly.", "relaxed", "warm, unhurried"]', 0.001

    first, cost = script.direct(THREE, "k", tmp_path, ask)
    again, free = script.direct(THREE, "k", tmp_path, ask)
    assert first == again == ["calm, friendly", "relaxed", "warm, unhurried"]
    assert cost == 0.001 and free == 0.0 and len(asked) == 1
    # It reads the scene unpointed, and with the default spelled out.
    assert "שלום, מה שלומך?" in asked[0] and "Never excited" in asked[0]


def test_a_re_pointed_scene_keeps_its_directions_and_a_re_worded_one_does_not() -> None:
    pointed = json.loads(json.dumps(THREE))
    pointed["turns"][1]["text"] = "טוֹב, תודה."
    worded = json.loads(json.dumps(THREE))
    worded["turns"][1]["text"] = "רַע, תּוֹדָה."
    assert script.scene_key(pointed) == script.scene_key(THREE)
    assert script.scene_key(worded) != script.scene_key(THREE)


def test_an_unreadable_answer_is_asked_again_then_falls_back_and_is_not_kept(
    tmp_path: Path,
) -> None:
    answers = iter(["sure!", '["one"]'])
    directions, _ = script.direct(THREE, "k", tmp_path, lambda t, k: (next(answers), 0.0))
    assert directions == [script.NEUTRAL] * 3
    assert not list(tmp_path.iterdir())


def test_a_direction_is_tidied_and_cut_at_a_word() -> None:
    assert script.tidy('  "Calm,   a little TIRED." ') == "calm, a little tired"
    long = script.tidy("quietly irritated but trying hard to stay polite about it")
    assert len(long) <= script.DIRECTION_MOST and not long.endswith(" ")
    assert script.tidy(None) == ""


def test_a_direction_never_pushes_a_prompt_over_the_limit_and_gives_way_first() -> None:
    plain = script.prompt_for(THREE, 0)
    directed = script.prompt_for(THREE, 0, "calm, a little tired")
    assert directed == plain.replace("in conversation.", "in conversation, calm, a little tired.")
    # A line with a long pronunciation hint: the direction is shortened or dropped, the
    # hint never.
    hinted = scene(("B", "אָמַרְתְּ שֶׁעָזַבְתְּ וְשָׁכַחְתְּ, אַתְּ וְהַחֲבֵרָה שֶׁלָּךְ"), ("A", "כֵּן."))
    bare = script.prompt_for(hinted, 0)
    guide = bare[bare.index(" Read ") :]
    assert len(guide) > 40, "the line was meant to carry a long hint"
    widest = "x" * script.DIRECTION_MOST
    said = script.prompt_for(hinted, 0, widest)
    assert said.endswith(guide)
    # A hint the corpus never reaches can be longer than the limit on its own; then the
    # direction is the part left out, and the prompt is no longer than without it.
    assert len(said) <= max(script.LONGEST, len(bare))
    assert widest not in said


def test_the_gaps_follow_the_conversation() -> None:
    talk = scene(
        ("A", "אַתָּה בָּא?"),
        ("B", "כֵּן."),
        ("A", "טוֹב."),
        ("A", "אָז —"),
        ("B", "רֶגַע."),
    )
    after_question, reply, same, cut_in = (script.gap(talk, n) for n in range(4))
    low, high = script.BETWEEN
    assert low <= reply <= high
    assert low + script.AFTER_QUESTION <= after_question <= high + script.AFTER_QUESTION
    assert same == cut_in == script.SAME
    # Over write.py's 0.18s floor, and the same on every run.
    assert min(after_question, reply, same) > 0.18
    assert [script.gap(talk, n) for n in range(4)] == [after_question, reply, same, cut_in]


def tone(seconds: float, amplitude: int) -> bytes:
    count = int(script.RATE * seconds)
    return struct.pack(
        f"<{count}h",
        *(round(amplitude * math.sin(2 * math.pi * 220 * i / script.RATE)) for i in range(count)),
    )


def test_each_turn_is_levelled_to_the_same_loudness_without_moving_a_sample() -> None:
    quiet, loud = tone(1.5, 1500), tone(1.5, 20000)
    a, b = script.level(quiet), script.level(loud)
    assert len(a) == len(quiet) and len(b) == len(loud)
    (ia, pa), (ib, pb) = script.loudness(a), script.loudness(b)
    assert abs(ia - ib) < 1.0
    assert abs(ia - script.LOUDNESS) < 1.5
    assert max(pa, pb) <= script.CEILING + 1.0


def test_silence_is_left_alone() -> None:
    hush = b"\0\0" * script.RATE
    assert script.level(hush) == hush


@pytest.mark.parametrize("n", [0, 1])
def test_a_turn_is_kept_by_what_made_it(tmp_path: Path, n: int) -> None:
    one = script.take_path(tmp_path, THREE, n, "Leda", "Read.")
    assert one == script.take_path(tmp_path, THREE, n, "Leda", "Read.")
    assert one != script.take_path(tmp_path, THREE, n, "Leda", "Read, calmly.")
    assert one.parent == tmp_path / "t-01"


def test_one_loud_peak_does_not_hold_a_quiet_line_down() -> None:
    """he-06 t13: by gain alone, a single loud consonant kept the line 3 LU under."""
    spiky = bytearray(tone(2.0, 1500))
    for at in range(4000, len(spiky), 24000):
        spiky[at : at + 2] = struct.pack("<h", 32000)
    levelled = script.level(bytes(spiky))
    assert len(levelled) == len(spiky)
    assert abs(script.loudness(levelled)[0] - script.LOUDNESS) < 1.0
