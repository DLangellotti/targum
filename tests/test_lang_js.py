"""The language menu in the nav (design.md §13, 2026-09-13), run rather than read.

Same harness shape as `test_progress_js.py`: a stub document in `tests/js/`, not a browser.
"""

from __future__ import annotations

import json
import re
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
    assert drawn["before"]["heads"] == ["Your languages", "Start another language"]
    assert drawn["before"]["starts"] == ["arc", "fr", "ru", "it"], "the rest targum teaches"
    assert drawn["before"]["panelHidden"] and drawn["openedPanel"], "opened by its button"


def test_every_language_wears_how_far_along_it_is() -> None:
    """design.md §12, 2026-10-09: Hebrew Beta; Russian, Italian, French Alpha; Aramaic and
    Yiddish Experimental. A badge, on the menu's button and on every row, and nothing
    more."""
    learning = ["he", "ru", "it", "fr", "arc", "yi"]
    drawn = menu(stored={"targum:learning": json.dumps(learning)}, pageCodes=["he"])
    said = dict(zip(drawn["before"]["items"], drawn["before"]["badges"], strict=True))
    assert said == {
        "he": "Beta",
        "ru": "Alpha",
        "it": "Alpha",
        "fr": "Alpha",
        "arc": "Experimental",
        "yi": "Experimental",
    }
    assert drawn["before"]["badge"] == "Beta", "the button wears the one it is showing"


def test_a_press_is_kept_on_the_page_and_on_the_account() -> None:
    drawn = menu(stored={"targum:learning": json.dumps(["he", "yi"])}, press="yi")
    assert drawn["picked"] == ["yi"], "the page is told"
    assert drawn["stored"] == "yi" and drawn["told"] == ["yi"], "and the account"
    assert drawn["afterPanelHidden"], "and the menu closes"
    assert "yi" in drawn["heard"], "a page listening for the language hears it"


def test_the_current_language_pressed_again_changes_nothing() -> None:
    drawn = menu(stored={"targum:learning": json.dumps(["he", "yi"])}, press="he")
    assert drawn["picked"] == [] and drawn["told"] == []


def test_a_language_chosen_stands_on_a_page_with_nothing_in_it_yet() -> None:
    """Every desk page lists the languages it has something in — readers, kept words —
    and asked `current` of that list. A language chosen in the menu with nothing built
    in it yet was not on it, so the next page settled on Hebrew and wrote Hebrew back:
    every change of page put the reader back in Hebrew (2026-09-14). A language the
    reader learns is a language a page can be in."""
    drawn = menu(
        stored={"targum:learning": json.dumps(["he", "arc"]), "targum:language": "arc"},
        currentOf=["he"],
    )
    assert drawn["current"] == "arc"


def test_a_language_no_longer_learned_falls_back_to_hebrew() -> None:
    drawn = menu(
        stored={"targum:learning": json.dumps(["he"]), "targum:language": "arc"},
        currentOf=["he"],
    )
    assert drawn["current"] == "he"


def test_one_language_still_draws_the_menu_with_its_badge() -> None:
    """design.md §12, "The boards are the desk" (2026-10-09): always shown, with its badge,
    for a reader of one language too — it is also where another is started."""
    drawn = menu(stored={"targum:learning": json.dumps(["he"])})
    assert drawn["before"]["hidden"] is False and drawn["before"]["badge"] == "Beta"
    assert drawn["before"]["items"] == ["he"]
    assert drawn["before"]["starts"] == ["arc", "yi", "fr", "ru", "it"]


def test_another_language_is_started_from_the_menu() -> None:
    """A press under Start another language turns it on, in this browser and on the
    account, and opens it as any press does."""
    drawn = menu(stored={"targum:learning": json.dumps(["he"])}, press="ru")
    assert drawn["picked"] == ["ru"] and drawn["told"] == ["ru"] and drawn["stored"] == "ru"
    assert json.loads(drawn["learning"]) == ["he", "ru"]


def test_anywhere_but_the_nav_the_same_call_still_draws_tabs() -> None:
    assert set(menu()["tabs"]) == {"tab"}


def test_each_language_wears_its_flag_and_is_met_with_its_greeting() -> None:
    """design.md §12: each row of the menu carries its flag (David, 2026-10-10, back from
    2026-09-14) and ends in the greeting it is met with (LangMenuDesk, 2026-10-09)."""
    drawn = menu(stored={"targum:learning": json.dumps(["he", "ru"])})
    assert drawn["before"]["flags"] == 6, "one per row: he, ru, then arc, yi, fr, it"
    assert drawn["before"]["greetings"] == {
        "he": "שָׁלוֹם",
        "ru": "Здравствуйте",
        "arc": "בְּקַדְמִין",
        "yi": "אַ גוטן טאָג",
        "fr": "Bonjour",
        "it": "Ciao",
    }


# -- a text's language, carried out of its reader (design.md §12, 2026-10-07) ----------


def test_a_page_arrived_at_from_a_russian_text_is_in_russian() -> None:
    """David left a Russian text by the mark in its corner and landed on Learn in Hebrew.
    The mark now carries `?learning=ru`, and the page takes it as the menu takes a press:
    kept in this browser, said to be what the page is in, and gone from the address."""
    drawn = menu(
        stored={"targum:learning": json.dumps(["he", "ru"]), "targum:language": "he"},
        href="http://learn.test/?learning=ru&k=key",
        currentOf=["he", "ru"],
    )
    assert drawn["carried"] == "ru" and drawn["current"] == "ru"
    assert drawn["stored"] == "ru", "the next page opens in it too"
    assert drawn["replaced"] == ["/?k=key"], "a reload is the plain page, key kept"
    assert "ru" in drawn["heard"]


def test_a_page_arrived_at_from_a_hebrew_text_is_in_hebrew() -> None:
    drawn = menu(
        stored={"targum:learning": json.dumps(["he", "ru"]), "targum:language": "ru"},
        href="http://learn.test/?learning=he",
        currentOf=["he", "ru"],
    )
    assert drawn["current"] == "he" and drawn["stored"] == "he"


def test_a_language_not_on_the_list_is_the_page_s_and_goes_on_it() -> None:
    """A text imported over the connector, in a language the account has not ticked: the
    page is in it before the account has answered, and on a page with nothing else in
    it, and the browser's list carries it for the next page. The account is told by
    `sync.js` (see `test_sync_js.py`)."""
    drawn = menu(
        stored={"targum:learning": json.dumps(["he"]), "targum:language": "he"},
        href="http://learn.test/?learning=fr",
        currentOf=["he"],
    )
    assert drawn["current"] == "fr" and drawn["stored"] == "fr"
    assert json.loads(drawn["learning"]) == ["he", "fr"]


@pytest.mark.parametrize("code", ["en", "es", "und", "%3Cscript%3E"])
def test_a_language_with_no_desk_leaves_the_page_where_it_was(code: str) -> None:
    """A text in English or Spanish has no Learn of its own: the page stays in the
    language it was in, and the word still comes off the address."""
    drawn = menu(
        stored={"targum:learning": json.dumps(["he", "ru"]), "targum:language": "ru"},
        href=f"http://learn.test/?learning={code}",
        currentOf=["he", "ru"],
    )
    assert drawn["carried"] == "" and drawn["current"] == "ru"
    assert drawn["stored"] == "ru" and drawn["replaced"] == ["/"]
    assert json.loads(drawn["learning"]) == ["he", "ru"]


def test_a_page_arrived_at_with_nothing_carried_is_untouched() -> None:
    """What a reader built before 2026-10-07 sends: the page opens as it always did, and
    its address is left alone."""
    drawn = menu(
        stored={"targum:learning": json.dumps(["he", "ru"]), "targum:language": "he"},
        href="http://learn.test/?k=key",
        currentOf=["he", "ru"],
    )
    assert drawn["carried"] == "" and drawn["current"] == "he" and drawn["replaced"] == []


def test_the_languages_a_page_takes_are_the_ones_targum_teaches() -> None:
    """`lang.js` keeps its own copy of `READING`, because a desk page has no other way to
    know it; held to the source here so the two cannot drift."""
    from targum.render.builder import ASSETS
    from targum.translate.prompts import READING

    source = (ASSETS / "lang.js").read_text(encoding="utf-8")
    found = re.search(r"var LEARNABLE = \[([^\]]*)\]", source)
    assert found is not None
    listed = re.findall(r'"([a-z]+)"', found.group(1))
    assert sorted(listed) == sorted(code for code, _ in READING)
