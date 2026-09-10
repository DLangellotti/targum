"""Words you may already know (targum-internal#245), run rather than read."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "claim.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def run(**payload: Any) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as where:
        path = Path(where) / "payload.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        done = subprocess.run(
            ["node", str(HARNESS), str(path)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def page(forms: list[str], offset: int, next_at: int | None) -> dict[str, Any]:
    return {
        "words": [{"form": f, "meaning": f"m-{f}", "band": "easy"} for f in forms],
        "offset": offset,
        "next": next_at,
    }


PAGES = {"0": page(["של", "את", "הוא", "על"], 0, 4), "4": page(["זה", "לא"], 4, None)}


def test_the_commonest_words_not_on_the_ledger_are_drawn_with_their_meanings() -> None:
    got = run(pages=PAGES, ledger={"את": {"status": 9}})
    assert got["asked"] == ["/words/common?offset=0&limit=50"]
    assert [r["form"] for r in got["rows"]] == ["של", "הוא", "על"], "את is on the ledger"
    assert got["rows"][0] == {"form": "של", "meaning": "m-של", "band": "easy"}
    assert not got["hidden"]


def test_i_know_all_of_these_marks_the_page_known_for_real_and_moves_on() -> None:
    got = run(pages=PAGES, do=[{"type": "yes"}])
    marked = got["ledger"]
    assert sorted(marked) == ["את", "הוא", "על", "של"]
    assert all(row["status"] == 9 and row["learned"] == 0 for row in marked.values())
    assert marked["של"]["surface"] == "של" and marked["של"]["meaning"] == "m-של"
    assert marked["של"]["at"] < marked["הוא"]["at"], "kept in the order they were shown"
    assert got["touched"] == {"sync": 1, "lists": 1}, "the count above and the sync hear it"
    assert got["said"] == "4 marked known."
    assert [r["form"] for r in got["rows"]] == ["זה", "לא"], "the next page"


def test_not_these_leaves_them_unmet_and_does_not_show_them_again() -> None:
    got = run(pages=PAGES, do=[{"type": "no"}])
    assert got["ledger"] == {} and sorted(got["passed"]) == ["את", "הוא", "על", "של"]
    assert [r["form"] for r in got["rows"]] == ["זה", "לא"]
    again = run(pages=PAGES, passed={"של": 1, "את": 1, "הוא": 1, "על": 1})
    assert [r["form"] for r in again["rows"]] == ["זה", "לא"], (
        "skipped straight to a page with rows"
    )


def test_the_end_of_the_list_and_another_language_show_nothing() -> None:
    got = run(pages=PAGES, do=[{"type": "yes"}, {"type": "yes"}])
    assert got["hidden"] and got["said"] == "That is the whole list."
    assert sorted(got["ledger"]) == ["את", "הוא", "זה", "לא", "על", "של"]
    russian = run(pages=PAGES, language="ru")
    assert russian["asked"] == [] and russian["hidden"]
