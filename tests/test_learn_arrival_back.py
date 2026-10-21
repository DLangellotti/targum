"""The way back through the arrival's three questions (2026-09-20, 2026-10-09).

A question a reader may not go back to is a one-way door, and the arrival has been argued
out of being a gate twice already (design.md §12, 2026-09-19). Back is drawn on every
screen but the first — "← Back" in the foot at a desk, a chevron in the head on a phone,
the same press — and what was pressed is still pressed when they come back.
"""

from __future__ import annotations

import shutil

import pytest
from test_arrival_js import HEBREW, draw, seeded

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def test_back_returns_to_the_subjects_with_what_was_picked() -> None:
    back = draw(
        [],
        shared=seeded(),
        do=[
            *HEBREW,
            {"subject": "News"},
            {"subject": "History"},
            {"press": "arrival-done"},
            {"back": True},
        ],
    )
    assert back["step"] == "2 of 3"
    assert back["subjectsUp"] and not back["levelUp"]
    assert sorted(back["picked"]) == ["History", "News"], "nothing was unpicked"
    assert back["done"] is True and back["nextShown"], "and Continue is awake to go on again"


def test_back_is_not_drawn_on_the_first_screen_and_does_nothing_there() -> None:
    first = draw([], shared=seeded(), do=[{"back": True}])
    assert first["step"] == "1 of 3" and first["arriving"] and not first["backShown"]


def test_going_back_and_on_again_keeps_the_new_choice() -> None:
    """Continue keeps the subjects each time it is pressed, so a reader who goes back to
    change their mind is kept as they are now and not as they were."""
    again = draw(
        [],
        shared=seeded(),
        do=[
            *HEBREW,
            {"subject": "History"},
            {"press": "arrival-done"},
            {"back": True},
            {"subject": "News"},
            {"press": "arrival-done"},
        ],
    )
    assert again["step"] == "3 of 3"
    kept = [c["body"] for c in again["sent"] if "/account/interest" in c["path"]]
    assert kept == [{"interest": ["history"]}, {"interest": ["history", "news"]}]


def test_a_new_language_asks_its_own_level_after_going_back() -> None:
    page = draw(
        [],
        shared=seeded(),
        do=[
            *HEBREW,
            {"press": "arrival-done"},
            {"back": True},
            {"back": True},
            {"learn": "Italian"},
            {"press": "arrival-done"},
            {"press": "arrival-done"},
        ],
    )
    assert page["levelAsks"] == "How much Italian can you read?"
    assert page["levels"][0] == "I’m just starting"
