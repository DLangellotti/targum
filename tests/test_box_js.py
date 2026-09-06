"""The front door's box, run rather than read — the same harness as the other pages.

The box on Learn is the same markup as the conversation page's composer, from one file,
with a script of its own: a line typed here opens a conversation and goes to it, and
nothing is answered on Learn.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "box.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def run(
    do: list[dict[str, Any]] | None = None,
    answers: dict[str, Any] | None = None,
    key: str = "k",
    record: bool = False,
) -> dict[str, Any]:
    payload = {
        "key": key,
        "record": record,
        "answers": {"/chat/list": {"chats": [], "usable": True}, **(answers or {})},
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


def test_a_line_opens_a_conversation_and_goes_to_it() -> None:
    page = run(
        do=[{"type": "say", "text": "something short for tonight"}],
        answers={"/chat/say": {"chat": "abc", "turn": 1}},
    )
    assert page["posted"] == [
        {"path": "/chat/say", "body": {"chat": "", "text": "something short for tonight"}}
    ], "no conversation named: a new one"
    assert page["went"] == "/chat?k=k#abc", "the conversation page, that conversation"


def test_hosted_the_address_carries_no_key() -> None:
    page = run(
        do=[{"type": "say", "text": "hi"}],
        answers={"/chat/say": {"chat": "abc", "turn": 1}},
        key="",
    )
    assert page["went"] == "/chat#abc"


def test_a_refusal_is_said_under_the_box_and_the_page_stays() -> None:
    page = run(
        do=[{"type": "say", "text": "hi"}],
        answers={"/chat/say": {"error": "A lot of conversation for one day."}},
    )
    assert page["went"] == "", "nowhere"
    assert page["said"] == {"text": "A lot of conversation for one day.", "hidden": False}
    assert page["sendDisabled"] is False, "and the box can be tried again"


def test_nothing_is_asked_when_nothing_can_be() -> None:
    page = run(
        do=[{"type": "say", "text": "hi"}],
        answers={"/chat/list": {"chats": [], "usable": False}},
    )
    assert page["posted"] == []
    assert "still opens" in page["said"]["text"]


def test_speak_is_offered_where_the_browser_records_and_the_reader_has_modern_hebrew() -> None:
    assert run(record=False)["mic"]["hidden"] is True
    assert run(record=True)["mic"]["hidden"] is False
    assert (
        run(record=True, answers={"/chat/list": {"chats": [], "usable": True, "talk": False}})[
            "mic"
        ]["hidden"]
        is True
    ), "a reader whose every text is scripture is not offered a microphone"


def test_a_spoken_line_opens_a_conversation_too() -> None:
    page = run(
        do=[{"type": "record"}],
        answers={"/chat/hear": {"chat": "abc", "turn": 1, "heard": "שלום"}},
        record=True,
    )
    assert page["posted"] == [{"path": "/chat/hear", "body": "<blob audio/webm>"}]
    assert page["went"] == "/chat?k=k#abc"


def test_the_plus_is_the_add_page_with_the_key_on_it() -> None:
    assert run()["bring"] == "/add?k=k"
