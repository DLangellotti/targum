"""The month's hours on Your Progress and in the account panel, run rather than read.

Same harness shape as `test_lang_js.py`: a stub document in `tests/js/`, not a browser.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "account.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

READER = {"email": "reader@example.com", "initials": "RE"}


def drawn(**payload: Any) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as where:
        given = Path(where) / "payload.json"
        given.write_text(json.dumps(payload), encoding="utf-8")
        done = subprocess.run(
            ["node", str(HARNESS), str(given)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_your_progress_shows_the_hours_whenever_there_is_an_allowance() -> None:
    """Whatever share is used, with the day it resets (targum-internal#237, criterion 3):
    the count left the chat page, and this is where it went."""
    hours = {"used": 0.5, "allowed": 8, "ends": "October 1"}
    seen = drawn(who={**READER, "hours": hours})
    assert seen["ledger"] == {
        "hidden": False,
        "text": "30 minutes of your 8 hours used this month · resets October 1",
    }
    assert seen["panel"] == {"hidden": False, "text": "30 minutes of your 8 hours used this month"}


def test_your_progress_says_nothing_about_hours_without_an_allowance() -> None:
    """An admin, or anybody the box does not cap, has no allowance to report; and a
    reader who is not signed in has no hours at all."""
    for who in ({**READER, "hours": {"used": 2, "allowed": None, "ends": ""}}, None):
        seen = drawn(who=who)
        assert seen["ledger"] == {"hidden": True, "text": ""}, who
        assert seen["panel"]["hidden"] is True, who
