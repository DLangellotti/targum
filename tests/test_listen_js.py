"""The listening view's arithmetic (design.md §12, "Listening is a view of its own",
2026-10-10), run rather than read: which lines stand either side of the voice, where a
step of a line lands, when a held line sends the voice back, and what comes after a part."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "listen.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

LINES = [
    {"id": "a", "start": 0.0, "end": 4.0},
    {"id": "b", "start": 5.0, "end": 9.0},
    {"id": "c", "start": 9.0, "end": 12.0},
]


def run(*calls: tuple[str, list[Any]]) -> list[Any]:
    with tempfile.TemporaryDirectory() as where:
        path = Path(where) / "payload.json"
        path.write_text(
            json.dumps({"calls": [{"fn": fn, "args": args} for fn, args in calls]}),
            encoding="utf-8",
        )
        done = subprocess.run(
            ["node", str(HARNESS), str(path)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def ids(spot: dict[str, Any]) -> list[str | None]:
    return [(spot[k] or {}).get("id") for k in ("before", "now", "after")]


def test_the_line_said_is_held_through_the_silence_after_it() -> None:
    first, gap, last, nothing = run(
        ("around", [LINES, 0.0]),
        ("around", [LINES, 4.5]),
        ("around", [LINES, 11.0]),
        ("around", [[], 3.0]),
    )
    assert ids(first) == [None, "a", "b"]
    assert ids(gap) == [None, "a", "b"], "between lines the last one begun stays"
    assert ids(last) == ["b", "c", None]
    assert nothing["now"] is None


def test_back_from_the_middle_of_a_line_is_its_top_and_from_its_top_the_line_before() -> None:
    middle, top, first, forward, past = run(
        ("lineStep", [LINES, 7.0, -1]),
        ("lineStep", [LINES, 5.5, -1]),
        ("lineStep", [LINES, 1.0, -1]),
        ("lineStep", [LINES, 1.0, 1]),
        ("lineStep", [LINES, 10.0, 1]),
    )
    assert middle == 5.0
    assert top == 0.0
    assert first == 0.0
    assert forward == 5.0
    assert past is None, "there is no line after the last"


def test_a_held_line_sends_the_voice_back_once_it_leaves() -> None:
    inside, out, before, unheld = run(
        ("looped", [[5.0, 9.0], 7.0]),
        ("looped", [[5.0, 9.0], 9.0]),
        ("looped", [[5.0, 9.0], 3.0]),
        ("looped", [None, 3.0]),
    )
    assert inside is None
    assert out == 5.0
    assert before == 5.0, "a step back past it while held comes back too"
    assert unheld is None


def test_what_comes_after_a_part_and_where_it_is_written() -> None:
    ahead, last, name, clock = run(
        ("partsAhead", [2, 4]),
        ("partsAhead", [4, 4]),
        ("partFile", [3]),
        ("clocked", [252.7]),
    )
    assert ahead == [3, 4]
    assert last == []
    assert name == "sec-0003.html"
    assert clock == "4:12"
