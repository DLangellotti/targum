"""The way back from the arrival's second question to its first (2026-09-20).

The arrival went one way: a reader who pressed Next a subject early, or wanted to see
what they had chosen before saying how much Hebrew they have, could only go on. A
question a reader may not go back to is a one-way door, and the arrival has been argued
out of being a gate twice already (design.md §12, 2026-09-19).
"""

from __future__ import annotations

import shutil

import pytest
from test_learn_js import THREE, draw, seeded

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def test_back_returns_to_the_subjects_with_what_was_picked() -> None:
    back = draw(
        [], shared=seeded(), do=[*THREE, {"press": "arrival-done"}, {"press": "arrival-back"}]
    )
    assert back["step"] == "1 of 2"
    assert back["subjectsUp"] and back["levels"] == []
    assert sorted(back["picked"]) == ["Archaeology", "History", "Sport"], "nothing was unpicked"
    assert back["done"] is True and back["nextShown"], "and Next is awake to go on again"


def test_back_is_not_drawn_on_the_first_screen_and_does_nothing_there() -> None:
    first = draw([], shared=seeded(), do=[{"press": "arrival-back"}])
    assert first["step"] == "1 of 2" and first["arriving"]


def test_going_back_and_on_again_keeps_the_new_choice() -> None:
    """Next keeps the subjects each time it is pressed, so a reader who goes back to
    change their mind is kept as they are now and not as they were."""
    again = draw(
        [],
        shared=seeded(),
        do=[
            *THREE,
            {"press": "arrival-done"},
            {"press": "arrival-back"},
            {"subject": "Sport"},
            {"subject": "News"},
            {"press": "arrival-done"},
        ],
    )
    assert again["step"] == "2 of 2"
    posted = [str(where) for where in again["posted"] if "/account/interest" in str(where)]
    assert len(posted) == 2, "kept once each time Next was pressed"


def test_back_after_skipping_the_subjects_leaves_next_asleep() -> None:
    back = draw([], shared=seeded(), do=[{"press": "arrival-skip"}, {"press": "arrival-back"}])
    assert back["step"] == "1 of 2"
    assert back["done"] is False and back["counted"] == "Pick 3 more"
