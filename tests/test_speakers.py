"""Speaker attribution, measured on plays (targum-internal#77). Nothing here calls a model."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from targum import speakers
from targum.speakers import Line, Point
from targum.usage import Usage

FIXTURE = Path(__file__).parent / "fixtures" / "speakers" / "play.txt"
CAST = {"רנה": "רנה", "דן": "דן", "השכנה": "השכנה"}


def parsed() -> list[Line]:
    return speakers.parse_play(FIXTURE.read_text(encoding="utf-8"), CAST, opening="(חדר קטן")


def test_every_way_a_play_prints_a_name_is_read() -> None:
    lines = parsed()
    spoken = [(line.id, line.speaker, line.text) for line in lines if line.speaker]
    assert spoken == [
        ("l0000", "רנה", "מי שם בחוץ?"),
        ("l0001", "דן", "אני, רק אני. פתחי את הדלת, כי קר כאן מאוד."),
        ("l0002", "רנה", "(בצחוק) ולמה לא באת קודם?"),
        ("l0003", "דן", "( בלחש ) חיכיתי לך."),
        ("l0004", "השכנה", "(בכעס) כמה רעש!"),
        ("l0005", "דן", "(יושב) הלכה סוף סוף?"),
        ("l0006", "רנה", "הלכה."),
        ("l0007", "רנה", "וגם אני הולכת."),
        # A second turn run on in the same row, its aside wrapped onto the next.
        ("l0008", "דן", "די."),
        ("l0009", "רנה", "(פונה אליו) לא די!"),
    ]


def test_directions_are_kept_and_the_heading_and_rule_are_not() -> None:
    directions = [line.text for line in parsed() if line.speaker is None]
    assert directions == [
        "(חדר קטן. רנה יושבת ליד החלון, ודן עומד בפתח.)",
        "(דממה)",
        "השכנה (נכנסת)",
        "רנה ודן לבדם.",
        "(הוא קם.)",
    ]


def test_the_list_of_characters_is_skipped_and_a_missing_opening_says_so() -> None:
    assert all("הנפשות" not in line.text for line in parsed())
    with pytest.raises(ValueError, match="opening"):
        speakers.parse_play(FIXTURE.read_text(encoding="utf-8"), CAST, opening="אין כזה")


def test_the_model_is_shown_no_names_before_the_lines() -> None:
    shown = speakers.present(parsed())
    assert "[l0000] – מי שם בחוץ?" in shown
    for name in ("רנה:", "רִנָּה:", "דן.", "דן (", "השכנה:"):
        assert name not in shown
    assert "(דממה)" in shown


def test_windows_carry_context_either_side_and_cover_every_line_once() -> None:
    lines = parsed()
    seen: list[str] = []
    for before, batch, after in speakers.windows(lines, 3, before=2, after=1):
        assert len([line for line in batch if line.speaker]) <= 3
        assert len(before) <= 2 and len(after) <= 1
        seen += [line.id for line in batch if line.speaker]
    assert seen == [f"l{index:04d}" for index in range(10)]


def test_alternation_is_the_speaker_two_turns_back() -> None:
    guessed = speakers.alternation(parsed())
    assert "l0000" not in guessed and "l0001" not in guessed
    assert guessed["l0002"] == "רנה" and guessed["l0005"] == "דן"


GOLD = {"a": "x", "b": "y", "c": "x", "d": "y"}
GUESSED = {"a": ("x", 0.99), "b": ("y", 0.9), "c": ("y", 0.6), "d": (speakers.UNKNOWN, 0.95)}


def test_the_curve_counts_what_switches_and_what_is_right() -> None:
    points = {point.threshold: point for point in speakers.curve(GOLD, GUESSED, [0.0, 0.8, 1.0])}
    assert (points[0.0].switched, points[0.0].correct) == (3, 2)
    assert points[0.0].coverage == 0.75 and points[0.0].precision == pytest.approx(2 / 3)
    # An unknown never switches, however sure it claims to be.
    assert (points[0.8].switched, points[0.8].correct, points[0.8].precision) == (2, 2, 1.0)
    assert points[1.0].switched == 0 and points[1.0].coverage == 0.0


def test_accuracy_counts_a_missing_answer_as_wrong() -> None:
    assert speakers.accuracy(GOLD, {"a": "x", "b": "y"}) == 0.5
    assert speakers.accuracy({}, {}) == 0.0


def test_the_lowest_threshold_is_the_first_whose_switched_lines_clear_the_bar() -> None:
    points = [
        Point(0.5, 10, 8, 10),
        Point(0.7, 8, 8, 10),
        Point(0.9, 4, 3, 10),  # a thin tail dipping below the bar does not move it
        Point(0.99, 0, 0, 10),
    ]
    found = speakers.lowest(points, 0.95)
    assert found is not None and found.threshold == 0.7
    assert speakers.lowest([Point(0.9, 4, 1, 10), Point(1.0, 0, 0, 10)], 0.95) is None


class _Messages:
    def __init__(self, lines: list[dict[str, Any]]) -> None:
        self.lines = lines
        self.calls = 0

    def parse(self, **request: Any) -> Any:
        self.calls += 1
        assert request["model"] == speakers.MODEL
        assert request["output_format"] is speakers.Attributions
        parsed = speakers.Attributions.model_validate({"lines": self.lines})
        return SimpleNamespace(
            parsed_output=parsed, usage=SimpleNamespace(input_tokens=1000, output_tokens=200)
        )


def test_an_answer_is_cached_by_its_request_and_a_name_off_the_cast_is_unknown(
    tmp_path: Path,
) -> None:
    lines = parsed()
    before, batch, after = next(speakers.windows(lines, 3))
    client = SimpleNamespace(
        messages=_Messages(
            [
                {"id": "l0000", "speaker": "רנה", "confidence": 0.97},
                {"id": "l0001", "speaker": "המלך", "confidence": 0.99},
                {"id": "l0002", "speaker": "רנה", "confidence": 1.4},
                {"id": "l0099", "speaker": "דן", "confidence": 0.9},
            ]
        )
    )
    usage = Usage()
    cast = speakers.speakers(CAST)
    first = speakers.ask(client, cast, before, batch, after, usage=usage, cache=tmp_path)
    assert first == {
        "l0000": ("רנה", 0.97),
        "l0001": (speakers.UNKNOWN, 0.0),
        "l0002": ("רנה", 1.0),
    }
    assert usage.calls == 1 and usage.cost() > 0
    (cached,) = tmp_path.glob("*.json")
    assert json.loads(cached.read_text(encoding="utf-8"))["tokens"] == [1000, 200]

    again = speakers.ask(client, cast, before, batch, after, usage=usage, cache=tmp_path)
    assert again == first
    assert client.messages.calls == 1 and usage.calls == 1, "a cached answer is not bought twice"


def test_the_measurement_script_parses_every_play_it_names() -> None:
    """The script's cast lists are data; this keeps them importable without a network."""
    import importlib.util

    path = Path(__file__).resolve().parents[1] / "scripts" / "measure_speakers.py"
    spec = importlib.util.spec_from_file_location("measure_speakers", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len({play.id for play in module.PLAYS}) == len(module.PLAYS)
    for play in module.PLAYS:
        assert play.opening and play.cast
