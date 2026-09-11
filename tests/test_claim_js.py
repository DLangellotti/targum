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


FIRST = ["של", "את", "הוא", "על", "זה", "לא", "כל", "גם", "אני", "מה", "יש", "אם"]
SECOND = ["הם", "כן"]
PAGES = {"0": page(FIRST, 0, 12), "12": page(SECOND, 12, None)}


def test_the_commonest_words_not_on_the_ledger_are_drawn_with_their_meanings() -> None:
    got = run(pages=PAGES, ledger={"את": {"status": 9}})
    assert got["asked"] == ["/words/common?offset=0&limit=50"]
    assert [r["form"] for r in got["rows"]] == [f for f in FIRST if f != "את"], (
        "את is on the ledger"
    )
    assert got["rows"][0]["meaning"] == "m-של" and got["rows"][0]["band"] == "easy"
    assert not got["hidden"]
    assert all(not r["checked"] and r["labelled"] for r in got["rows"]), (
        "a checkbox on each, unchecked, with the word as its label"
    )
    assert got["yesDisabled"] and got["all"] == {"checked": False, "some": False}, (
        "nothing to mark until something is checked"
    )


def test_a_page_the_ledger_mostly_holds_is_filled_from_the_next() -> None:
    """2026-09-11: "some weird bug where it only shows one or two words here at a time".
    A page of fifty set against a ledger that holds most of it is not a page; the next
    pages are gathered until at least ten words remain, or the list ends."""
    known = {f: {"status": 9} for f in FIRST[:10]}
    got = run(pages=PAGES, ledger=known)
    assert got["asked"] == ["/words/common?offset=0&limit=50", "/words/common?offset=12&limit=50"]
    assert [r["form"] for r in got["rows"]] == ["יש", "אם", "הם", "כן"], "both pages, together"
    whole = run(pages=PAGES, ledger={f: {"status": 9} for f in FIRST + SECOND})
    assert whole["hidden"], "nothing left to show"


def test_the_checked_words_are_marked_known_for_real_and_the_rest_are_left() -> None:
    """2026-09-11: "this should work with checkboxes, you can mark words you checked as
    known". The checked ones become ordinary known words; the unchecked were looked at
    and left, so they are passed over rather than shown again; the next page comes up."""
    got = run(
        pages=PAGES,
        do=[{"type": "check", "form": "של"}, {"type": "check", "form": "הוא"}, {"type": "yes"}],
    )
    marked = got["ledger"]
    assert sorted(marked) == ["הוא", "של"]
    assert all(row["status"] == 9 and row["learned"] == 0 for row in marked.values())
    assert marked["של"]["surface"] == "של" and marked["של"]["meaning"] == "m-של"
    assert marked["של"]["at"] < marked["הוא"]["at"], "kept in the order they were shown"
    assert sorted(got["passed"]) == sorted(f for f in FIRST if f not in ("של", "הוא")), (
        "looked at and left"
    )
    assert got["touched"] == {"sync": 1, "lists": 1}, "the count above and the sync hear it"
    assert got["said"] == "2 marked known."
    assert [r["form"] for r in got["rows"]] == SECOND, "the next page"
    assert got["yesDisabled"], "a fresh page, nothing checked yet"
    nothing = run(pages=PAGES, do=[{"type": "yes"}])
    assert nothing["ledger"] == {} and [r["form"] for r in nothing["rows"]] == FIRST, (
        "with nothing checked the press is not offered"
    )


def test_check_all_checks_the_page_and_the_head_follows_the_rows() -> None:
    """ "Also option to check all": one box at the head checks every row; unchecking a row
    leaves the head half-checked, and unchecking the head clears the page."""
    got = run(pages=PAGES, do=[{"type": "all"}])
    assert all(r["checked"] for r in got["rows"]) and not got["yesDisabled"]
    assert got["all"] == {"checked": True, "some": False}
    part = run(pages=PAGES, do=[{"type": "all"}, {"type": "check", "form": "על", "on": False}])
    assert [r["form"] for r in part["rows"] if not r["checked"]] == ["על"]
    assert part["all"] == {"checked": False, "some": True}
    cleared = run(pages=PAGES, do=[{"type": "all"}, {"type": "all", "on": False}])
    assert not any(r["checked"] for r in cleared["rows"]) and cleared["yesDisabled"]
    whole = run(pages=PAGES, do=[{"type": "all"}, {"type": "yes"}])
    assert sorted(whole["ledger"]) == sorted(FIRST) and whole["passed"] == {}
    assert whole["said"] == "12 marked known."


def test_none_of_these_leaves_them_unmet_and_does_not_show_them_again() -> None:
    got = run(pages=PAGES, do=[{"type": "no"}])
    assert got["ledger"] == {} and sorted(got["passed"]) == sorted(FIRST)
    assert [r["form"] for r in got["rows"]] == SECOND
    again = run(pages=PAGES, passed={f: 1 for f in FIRST})
    assert [r["form"] for r in again["rows"]] == SECOND, "skipped straight to what is left"


def test_the_end_of_the_list_and_another_language_show_nothing() -> None:
    got = run(pages=PAGES, do=[{"type": "all"}, {"type": "yes"}, {"type": "all"}, {"type": "yes"}])
    assert got["hidden"] and got["said"] == "That is the whole list."
    assert sorted(got["ledger"]) == sorted(FIRST + SECOND)
    russian = run(pages=PAGES, language="ru")
    assert russian["asked"] == [] and russian["hidden"]
