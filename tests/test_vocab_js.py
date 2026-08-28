"""The vocabulary editor, run rather than read.

One control serves the word card, the phrase card, the list beside the text and the
words page, so a change here reaches four surfaces at once — and a reader who cannot
finish with it cannot finish with any of them. Which is what happened: the field kept
what you typed as you typed it, correctly and invisibly, and nothing on the card said
where the end was.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "vocab.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def run(**payload: Any) -> dict[str, Any]:
    where = Path(subprocess.run(["mktemp"], capture_output=True, text=True).stdout.strip())
    where.write_text(json.dumps(payload), encoding="utf-8")
    try:
        done = subprocess.run(
            ["node", str(HARNESS), str(where)], capture_output=True, text=True, timeout=60
        )
    finally:
        where.unlink(missing_ok=True)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def moved(stored: dict[str, Any], runs: int = 1) -> dict[str, Any]:
    """Run the one-time move `runs` times over that store, and say what is left."""
    return run(
        migrate=True,
        runs=runs,
        stored={name: json.dumps(value, ensure_ascii=False) for name, value in stored.items()},
    )["stored"]


def test_a_meaning_moves_out_of_the_word_and_into_the_pair() -> None:
    """A word belongs to a language; a meaning belongs to a language pair.

    Everything built before this was built into English, so what is untagged is read as
    English. The word keeps its level, its band and its dates — that is the half that
    must not move, or the same Hebrew word learned through two languages becomes two
    words and every count doubles.
    """
    after = moved(
        {
            "targum:vocab:he": {
                "ספר": {
                    "status": 2,
                    "surface": "הספר",
                    "meaning": "book",
                    "note": "scroll",
                    "band": "moderate",
                    "at": 100,
                    "seen": 200,
                }
            }
        }
    )

    assert after["targum:meanings:he:en"] == {
        "ספר": {"meaning": "book", "note": "scroll", "at": 100, "seen": 200}
    }
    word = after["targum:vocab:he"]["ספר"]
    assert word["status"] == 2 and word["band"] == "moderate" and word["at"] == 100
    assert "meaning" not in word, "the meaning is a cache and should not sit in two places"


def test_the_answers_this_browser_paid_for_move_too() -> None:
    """`targum:looked:<source>` held bought meanings under the source language alone, so
    a Russian answer would have been handed to an English reader. It goes."""
    after = moved({"targum:looked:he": {"אור": "light"}})

    assert after["targum:meanings:he:en"]["אור"]["meaning"] == "light"
    assert "targum:looked:he" not in after, "the old store was left where it could be read"


def test_running_the_move_twice_is_running_it_once() -> None:
    """Every page runs it on load, and a reader opens more than one page."""
    store = {
        "targum:vocab:he": {
            "ספר": {"status": 2, "meaning": "book", "note": "", "at": 100, "seen": 200}
        },
        "targum:looked:he": {"אור": "light"},
    }

    once = moved(store, runs=1)
    twice = moved(store, runs=3)

    # Everything but the ledger, whose two entries are wall-clock stamps of when the move
    # ran and differ between two runs of the harness by design.
    assert once.pop("targum:migrated").keys() == twice.pop("targum:migrated").keys()
    assert once == twice


def test_the_move_never_overwrites_a_newer_edit() -> None:
    """A browser that has already synced has the newer answer under the pair; the word's
    own copy is what it looked like before that edit. The same rule the account merges
    by, applied here so running this after a sync cannot undo one."""
    after = moved(
        {
            "targum:vocab:he": {
                "ספר": {"status": 2, "meaning": "book", "note": "", "at": 100, "seen": 100}
            },
            "targum:meanings:he:en": {
                "ספר": {"meaning": "a written book", "note": "", "at": 100, "seen": 900}
            },
        }
    )

    assert after["targum:meanings:he:en"]["ספר"]["meaning"] == "a written book"


def test_the_field_offers_a_way_to_finish() -> None:
    """A field that saves silently is a field nobody can tell they have finished with."""
    built = run()
    assert built["hasField"]
    assert built["hasSave"], "there is no way to say you are done"
    # §6 wants one or two words on a button.
    assert built["saveLabel"] == "Save"


def test_pressing_save_keeps_what_was_typed() -> None:
    built = run(type="most of the leadership", press=True)
    assert built["kept"] == ["most of the leadership"]


def test_the_placeholder_says_what_to_do() -> None:
    assert run()["placeholder"] == "Enter text"
    assert run(placeholder="Your own reading")["placeholder"] == "Your own reading"


def test_enter_also_finishes_the_field() -> None:
    """The button is the visible way and the key is the quick one, and they cannot
    disagree about whether anything was kept."""
    assert run(type="a reading", enter=True)["kept"] == ["a reading"]


def test_nothing_is_kept_when_nothing_changed() -> None:
    """Pressing Save on a field you have not touched must not write a record, or every
    glance at a word becomes an edit of it."""
    assert run(press=True)["kept"] == []
    assert run(note="already said", type="already said", press=True)["kept"] == []


def test_the_editor_is_only_a_form_when_it_is_asked_to_be() -> None:
    """The levels alone, where the caller wants no note. A Save button drawn beside no
    field would be a button that saves nothing."""
    built = run(noNote=True)
    assert not built["hasField"]
    assert not built["hasSave"]


def test_a_level_pressed_over_a_definition_keeps_both() -> None:
    """The two ways of finishing must agree. Reaching straight for a level after typing
    is the ordinary way to use this card — you write what a word means and then say how
    well you know it — and it has to keep the definition, not throw it away.
    """
    built = run(status=2, note="", type="second thoughts", level=2)
    assert built["kept"] == ["second thoughts"]
    # 2, not None: a level pressed over something you have just written is a save, and
    # never a second press of the level that happened to be set already.
    assert built["levels"] == [2]


def test_pressing_the_level_you_already_have_still_takes_it_off() -> None:
    """The toggle is worth keeping — the same press both grades a word and undoes a
    mistake. It just must not fire because you wrote something."""
    assert run(status=2, note="", level=2)["levels"] == [None]


def test_a_level_is_still_a_toggle_after_the_note_has_saved_itself() -> None:
    """The note commits 400ms after the last keystroke, so a field that has been typed in
    and a field that matches the store are the same field by the time a level is pressed.
    Whether it was written in is the question, not whether it currently differs.
    """
    # `note` already holds what was typed: the debounce has been and gone.
    built = run(status=2, note="second thoughts", type="second thoughts", level=2)
    assert built["levels"] == [2], "written in, so this is a save"
    assert run(status=2, note="second thoughts", level=2)["levels"] == [None], "untouched"


def test_a_level_press_keeps_the_note_before_it_sets_the_level() -> None:
    """Order matters: setting a level rebuilds the card from the store, so a note still
    sitting in the field when that happens is a note that never existed."""
    built = run(status=None, note="", type="my definition", level=1)
    assert built["kept"] == ["my definition"]
    assert built["levels"] == [1]


def test_the_button_says_it_saved() -> None:
    """ "Pop up card is a mess, can't understand when you successfully saved definition."
    The field always saved; the button always said "Save". Now it says which side of the
    line the field is on, and it tells the card, which redraws with the meaning marked as
    yours — `onSaved` had a definition and no caller."""
    done = run(status=2, type="scroll", press=True)
    assert done["kept"] == ["scroll"]
    assert done["saveLabel"] == "Saved"
    assert done["saveDisabled"] is True
    assert done["saved"] == 1, "and the card was told"


def test_typing_again_offers_to_save_again() -> None:
    done = run(status=2, type="scroll", press=True, again="scroll, roll")
    assert done["saveLabel"] == "Save"
    assert done["saveDisabled"] is False


def test_the_scale_says_what_the_pressed_step_means() -> None:
    """ "Explain what the 1, 2, 3 stages of how well you know a word mean." The names were
    in the buttons' tooltips, which is nowhere on a phone."""
    assert run(status=2, legend=True)["legend"] == "2 · getting there"
    assert run(status=9, legend=True)["legend"] == "known · known"
    assert run(legend=True)["legend"] == "1 just met it · 2 getting there · 3 nearly know it"
    assert run(status=2)["legend"] is None, "the list beside the text has no room for it"
