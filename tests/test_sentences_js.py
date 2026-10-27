"""The Sentences tab's comparison (design.md §12, "Sentences: dictation and fill the gap",
2026-10-27), run rather than read: what is forgiven, what is not, and which words are
marked."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "sentences.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


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


def test_points_finals_and_full_spelling_are_forgiven() -> None:
    answers = run(
        ("same", ["שָׁלוֹם", "שלום"]),
        ("same", ["שלום", "שלומ"]),
        ("same", ["שֻׁלְחָן", "שולחן"]),
        ("same", ["אִמָּא", "אימא"]),
        ("same", ["צ׳יפס", "צ'יפס"]),
        ("same", ["Ёлка", "елка"]),
        ("same", ["доро́га", "дорога"]),
    )
    assert answers == [True] * 7


def test_a_changed_letter_is_another_word() -> None:
    answers = run(
        ("same", ["הוּא", "היא"]),
        ("same", ["לו", "לי"]),
        ("same", ["כתב", "כתוב ספר"]),
        ("same", ["été", "ete"]),
        ("same", ["דבר", "דברים"]),
    )
    assert answers == [False] * 5


def test_the_line_marks_what_was_missed_and_what_was_written_besides() -> None:
    (said,) = run(("compare", ["הַיֶּלֶד הָלַךְ אֶל־הַבַּיִת.", "הילד הלך לבית"]))
    line = [(p["text"], p["found"]) for p in said["line"] if p["word"]]
    assert line == [("הַיֶּלֶד", True), ("הָלַךְ", True), ("אֶל", False), ("הַבַּיִת.", False)]
    written = [(p["text"], p["found"]) for p in said["written"] if p["word"]]
    assert written == [("הילד", True), ("הלך", True), ("לבית", False)]
    assert not said["whole"]
    assert "".join(p["text"] for p in said["line"]) == "הַיֶּלֶד הָלַךְ אֶל־הַבַּיִת.", (
        "the line is drawn back exactly as written, maqaf and all"
    )


def test_every_word_written_is_whole_and_nothing_written_is_not() -> None:
    whole, empty, extra = run(
        ("compare", ["Он пришёл домой.", "он пришел домой"]),
        ("compare", ["Он пришёл домой.", ""]),
        ("compare", ["Он пришёл домой.", "он пришел домой вчера"]),
    )
    assert whole["whole"]
    assert not empty["whole"] and all(not p["found"] for p in empty["line"] if p["word"])
    assert not extra["whole"]
    assert [p["found"] for p in extra["written"] if p["word"]] == [True, True, True, False]
