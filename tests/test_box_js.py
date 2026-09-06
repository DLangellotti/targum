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


QUOTE = {
    "id": "j1",
    "title": "סיפור קצר",
    "english": "A short story",
    "language": "he",
    "segments": 40,
    "total": 40,
    "chapters": 1,
    "estimate": 0.12,
    "stage": "ready",
    "blocked": "",
    "error": "",
    "audio": False,
    "seconds": 0,
    "parts": 0,
}


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


UPLOAD = {
    "/upload/begin": {"upload": "u1", "chunk": 4},
    "/upload/u1/0": {},
    "/upload/u1/1": {},
    "/upload/u1/2": {},
    "/upload/u1/end": {"upload": "u1"},
}


def test_a_file_chosen_by_the_plus_is_priced_under_the_box() -> None:
    """The Add page's job in one press: a text read whole, `/prepare` asked, the card
    drawn under the box with the same button the model's quote has, and the Add page
    one link away for the two things only its form can say."""
    page = run(
        do=[{"type": "file", "file": {"name": "story.txt", "content": "שלום"}}],
        answers={"/prepare": QUOTE},
    )
    assert [p["path"] for p in page["posted"]] == ["/prepare"]
    sent = page["posted"][0]["body"]
    assert sent["name"] == "story.txt" and sent["content"], "read whole, as base64"
    assert sent["words"] is True and sent["gloss"] is False and sent["to"] == "en"
    (card,) = page["brought"]
    assert card["title"] == QUOTE["title"] and card["button"] == "Read this"
    assert card["more"] == "/add?k=k", "the Add page, for a translation of your own"
    assert page["went"] == "", "nowhere: the card is the answer"
    assert page["sendDisabled"] is False


def test_a_recording_chosen_by_the_plus_goes_up_in_pieces() -> None:
    page = run(
        do=[{"type": "file", "file": {"name": "talk.mp3", "size": 10}}],
        answers={**UPLOAD, "/prepare": dict(QUOTE, audio=True, seconds=600, parts=1)},
    )
    paths = [p["path"] for p in page["posted"]]
    assert paths == [
        "/upload/begin",
        "/upload/u1/0",
        "/upload/u1/1",
        "/upload/u1/2",
        "/upload/u1/end",
        "/prepare",
    ]
    assert page["posted"][-1]["body"]["upload"] == "u1", "priced by its upload, not its bytes"
    (card,) = page["brought"]
    assert "minutes of audio" in card["title"] or card["button"] == "Read this"


def test_the_same_bytes_already_brought_open_the_text() -> None:
    page = run(
        do=[{"type": "file", "file": {"name": "talk.mp3", "size": 10}}],
        answers={**UPLOAD, "/upload/u1/end": {"reader": "שיחה-he/reader/index.html"}},
    )
    assert page["went"] == "/reader/%D7%A9%D7%99%D7%97%D7%94-he/reader/index.html?k=k"
    assert "/prepare" not in [p["path"] for p in page["posted"]]


def test_a_refused_file_is_said_under_the_box() -> None:
    page = run(
        do=[{"type": "file", "file": {"name": "story.txt", "content": "x"}}],
        answers={"/prepare": {"error": "Nothing new can be built now."}},
    )
    assert page["brought"] == [] and page["said"]["text"] == "Nothing new can be built now."
