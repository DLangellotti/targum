"""The profile page's script, run rather than read.

The two things on this page that matter are a name that has to actually save and a
delete button that has no second chance. Same harness as `test_learn_js.py` — a stub
document under node, not a browser.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "you.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

SIGNED_IN = {
    "signedIn": True,
    "email": "yosef@example.com",
    "name": "Yosef Cohen",
    "picture": "",
    "initials": "YC",
    "counts": {"words": 512, "phrases": 24, "docs": 3, "days": 12},
}


def run(
    who: dict[str, Any] | None = None,
    do: list[dict[str, Any]] | None = None,
    answers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "answers": {"/account/me": who if who is not None else SIGNED_IN, **(answers or {})},
        "do": do or [],
    }
    with tempfile.TemporaryDirectory() as where:
        path = Path(where) / "payload.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        done = subprocess.run(
            ["node", str(HARNESS), str(path)], capture_output=True, text=True, timeout=60
        )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_a_stranger_is_told_rather_than_shown_an_empty_form() -> None:
    page = run(who={"signedIn": False})
    assert page["stranger"] is False, "the one thing a signed-out visitor sees"
    assert all(page["panels"].values()), "and nothing else"
    assert page["name"] == "" and page["posted"] == []


def test_the_page_fills_itself_in_for_whoever_is_signed_in() -> None:
    page = run()
    assert page["stranger"] is True
    assert not any(page["panels"].values())
    assert page["name"] == "Yosef Cohen"
    assert page["email"] == "yosef@example.com"
    assert page["avatar"] == "YC"
    assert page["kept"] == "512 words, 24 phrases"


def test_typing_a_name_is_one_request_and_not_one_per_keystroke() -> None:
    """A field that posted per keystroke would post nine times for one name."""
    typed = [{"type": "name", "value": "Yosef Cohe" + "n" * n} for n in range(1, 10)]
    page = run(
        do=typed,
        answers={"/account/name": {**SIGNED_IN, "name": "Yosef Cohennnnnnnnn", "initials": "YC"}},
    )
    names = [post for post in page["posted"] if post["path"] == "/account/name"]
    assert len(names) == 1, names
    assert names[0]["body"]["name"] == "Yosef Cohennnnnnnnn", "the last thing typed, not the first"
    assert page["said"] == {"text": "Saved.", "hidden": False}


def test_a_refused_name_says_so_rather_than_claiming_it_saved() -> None:
    page = run(
        do=[{"type": "name", "value": "x" * 200}],
        answers={"/account/name": {"error": "That name is too long."}},
    )
    assert page["said"] == {"text": "That name is too long.", "hidden": False}


def test_the_corner_is_told_when_the_name_changes() -> None:
    """The initials in the corner come from /account/me, so the corner has to be asked
    again or it goes on showing the initials of a name nobody has any more."""
    quiet = run()
    page = run(
        do=[{"type": "name", "value": "Dov"}],
        answers={"/account/name": {**SIGNED_IN, "name": "Dov", "initials": "D"}},
    )
    assert page["restarted"]["count"] > quiet["restarted"]["count"]


def test_deleting_an_account_asks_twice() -> None:
    once = run(do=[{"type": "press", "id": "you-forget"}])
    assert once["posted"] == [], "the first press asks; it does not delete"
    assert once["forget"]["label"] == "Delete for good?"
    assert once["forget"]["disabled"] is False

    twice = run(
        do=[{"type": "press", "id": "you-forget"}, {"type": "press", "id": "you-forget"}],
        answers={"/account/forget": {"message": "Your account is closing."}},
    )
    assert [post["path"] for post in twice["posted"]] == ["/account/forget"]
    assert twice["forget"]["disabled"] is True, "and cannot be pressed a third time"
    assert twice["ending"]["text"] == "Your account is closing."


def test_signing_out_goes_through_sync_rather_than_the_endpoint() -> None:
    """Signing out empties this browser's word store as well as ending the session, and
    only sync knows how to do both."""
    page = run(do=[{"type": "press", "id": "you-out"}])
    assert page["restarted"]["signedOut"] == 1
    assert [post["path"] for post in page["posted"]] == []
