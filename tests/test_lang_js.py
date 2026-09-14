"""The language menu in the nav (design.md §13, 2026-09-13), run rather than read.

Same harness shape as `test_progress_js.py`: a stub document in `tests/js/`, not a browser.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "lang.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def menu(**payload: Any) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as where:
        given = Path(where) / "payload.json"
        given.write_text(json.dumps(payload), encoding="utf-8")
        done = subprocess.run(
            ["node", str(HARNESS), str(given)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_menu_lists_every_language_the_reader_learns() -> None:
    """Not only the languages the page has something in: a menu that left out a language
    with nothing on the shelf yet could never be used to go and add the first thing."""
    drawn = menu(stored={"targum:learning": json.dumps(["he", "yi"])}, pageCodes=["he"])
    assert drawn["before"]["hidden"] is False
    assert drawn["before"]["items"] == ["he", "yi"], "Hebrew first, then the rest"
    assert drawn["before"]["label"] == "Hebrew" and drawn["before"]["checked"] == ["he"]
    assert drawn["before"]["more"] == "/you#languages"
    assert drawn["before"]["panelHidden"] and drawn["openedPanel"], "opened by its button"


def test_a_press_is_kept_on_the_page_and_on_the_account() -> None:
    drawn = menu(stored={"targum:learning": json.dumps(["he", "yi"])}, press="yi")
    assert drawn["picked"] == ["yi"], "the page is told"
    assert drawn["stored"] == "yi" and drawn["told"] == ["yi"], "and the account"
    assert drawn["afterPanelHidden"], "and the menu closes"
    assert "yi" in drawn["heard"], "a page listening for the language hears it"


def test_the_current_language_pressed_again_changes_nothing() -> None:
    drawn = menu(stored={"targum:learning": json.dumps(["he", "yi"])}, press="he")
    assert drawn["picked"] == [] and drawn["told"] == []


def test_one_language_draws_no_menu() -> None:
    """A menu with one thing in it asks a question with no other answer."""
    assert menu(stored={"targum:learning": json.dumps(["he"])})["before"]["hidden"] is True


def test_anywhere_but_the_nav_the_same_call_still_draws_tabs() -> None:
    assert set(menu()["tabs"]) == {"tab"}


def test_each_language_wears_a_small_flag_and_a_language_with_no_country_keeps_the_room() -> None:
    """2026-09-14 (design.md §12): a drawn flag beside each name in the menu. Yiddish and
    Aramaic have no country and wear the language flags David chose; a code with no
    flag at all keeps an empty box the flag's width."""
    drawn = menu(stored={"targum:learning": json.dumps(["he", "fr", "yi", "arc", "de"])})
    assert drawn["flags"] == {"he": "flag", "fr": "flag", "yi": "flag", "arc": "flag", "de": "none"}
