"""`scripts/scene_nikkud_gold.py` turns the scene corrections into gold lines.

Loaded by path because `scripts/` is not a package. No store is opened: these are the
builder on hand-written rows, so the set `measure_pointing.py` scores against holds
the line a person settled and marks the words they settled (targum-internal#351).
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest


@pytest.fixture(scope="module")
def script() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "scene_nikkud_gold.py"
    spec = importlib.util.spec_from_file_location("scene_nikkud_gold", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


#: Invented for the test: the scenes themselves are private and never in the repository.
LINE = "הוּא קָרָא לִי לִפְנֵי יוֹמַיִים."


def row(before: str, after: str, *, span: str = "09 t4", context: str = LINE, id: int = 1):
    return {
        "id": id,
        "at": id,
        "span": span,
        "text": "He called me two days ago.",
        "before": before,
        "after": after,
        "context": context,
    }


def test_a_points_only_correction_is_applied_and_marked(script: ModuleType) -> None:
    (line,), left_out = script.build([row("לִפְנֵי", "לִפְנֶי")])
    assert line["line"] == "הוּא קָרָא לִי לִפְנֶי יוֹמַיִים."
    (one,) = line["settled"]
    assert line["line"][one["start"] : one["end"]] == "לִפְנֶי"
    assert one["kind"] == "points" and one["was"] == "לִפְנֵי"
    assert not left_out


def test_the_kinds_are_points_letters_and_kept(script: ModuleType) -> None:
    assert script.kind_of("לִפְנֵי", "לִפְנֶי") == "points"
    assert script.kind_of("יוֹמַיִים", "יוֹמַיִם") == "letters"
    assert script.kind_of("לִי", "לִי") == "kept"


def test_a_later_correction_shifts_an_earlier_one(script: ModuleType) -> None:
    (line,), _ = script.build(
        [row("לִי", "לִיי", id=1), row("קָרָא", "קוֹרֵא", id=2), row("יוֹמַיִים", "יוֹמַיִם", id=3)]
    )
    for one in line["settled"]:
        assert line["line"][one["start"] : one["end"]] in {"לִיי", "קוֹרֵא", "יוֹמַיִם"}
    assert [one["kind"] for one in line["settled"]] == ["letters", "letters", "letters"]


def test_a_word_inside_another_is_not_a_match(script: ModuleType) -> None:
    assert script.find_word("שֶׁלּוֹ לוֹ", "לוֹ") == len("שֶׁלּוֹ ")
    assert script.find_word("שֶׁלּוֹ", "לוֹ") == -1


def test_a_correction_that_cannot_be_placed_drops_the_whole_line(script: ModuleType) -> None:
    lines, left_out = script.build([row("לִפְנֵי", "לִפְנֶי", id=1), row("אַיִן", "אֵין", id=2)])
    assert lines == []
    assert left_out["correction not placed"] == 2


def test_the_same_judgement_twice_is_one_settled_word(script: ModuleType) -> None:
    (line,), _ = script.build([row("לִפְנֵי", "לִפְנֶי", id=1), row("לִפְנֵי", "לִפְנֶי", id=2)])
    assert len(line["settled"]) == 1


def test_a_row_with_no_line_is_counted_not_used(script: ModuleType) -> None:
    lines, left_out = script.build([row("cast.A.name", "רותי", context="")])
    assert lines == [] and left_out["no line"] == 1


def test_the_store_is_read_only_and_only_the_authors_scene_rows(
    script: ModuleType, tmp_path: Path
) -> None:
    path = tmp_path / "targum.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE correction (id INTEGER PRIMARY KEY, at INTEGER, stage TEXT,"
            " language TEXT, span TEXT, text TEXT, before TEXT, after TEXT, who TEXT,"
            " context TEXT, reason TEXT)"
        )
        rows: list[tuple[Any, ...]] = [
            (1, "scene", "he", "author"),
            (2, "scene", "he", "reader"),
            (3, "gloss", "he", "author"),
        ]
        for id_, stage, language, who in rows:
            db.execute(
                "INSERT INTO correction VALUES (?, ?, ?, ?, 's t0', '', 'א', 'ב', ?, 'א', '')",
                (id_, id_, stage, language, who),
            )
    assert [one["id"] for one in script.read_store(path)] == [1]
