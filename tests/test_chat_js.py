"""The chat page's script, run rather than read — the same harness as the other pages."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest

HARNESS = Path(__file__).resolve().parent / "js" / "chat.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def run(
    do: list[dict[str, Any]] | None = None, answers: dict[str, Any] | None = None, key: str = "k"
) -> dict[str, Any]:
    payload = {
        "key": key,
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


def test_the_page_asks_for_its_conversations_first() -> None:
    page = run()
    assert page["posted"] == []
    assert page["turns"] == []


def test_a_line_is_posted_and_the_stream_is_followed() -> None:
    page = run(
        do=[{"type": "say", "text": "what should I read"}],
        answers={"/chat/say": {"chat": "abc", "turn": 1}},
    )
    assert page["posted"] == [
        {"path": "/chat/say", "body": {"chat": "", "text": "what should I read"}}
    ]
    assert page["streams"] == ["/chat/stream/abc/1?k=k"], "the key rides in the address"
    assert [t["text"] for t in page["turns"]] == ["what should I read", ""]
    assert "working" in page["turns"][1]["cls"]
    assert page["sendDisabled"] is True, "one line at a time"


def test_text_arrives_in_pieces_and_a_path_becomes_a_keyed_link() -> None:
    page = run(
        do=[
            {"type": "say", "text": "hi"},
            {"type": "stream", "event": "text", "data": "Try רות at "},
            {"type": "stream", "event": "text", "data": "/reader/ruth-he/reader/index.html"},
            {
                "type": "stream",
                "event": "done",
                "data": json.dumps({"text": "Try רות at /reader/ruth-he/reader/index.html"}),
            },
        ],
        answers={"/chat/say": {"chat": "abc", "turn": 1}},
    )
    answer = page["turns"][1]
    assert answer["text"] == "Try רות at /reader/ruth-he/reader/index.html"
    assert answer["links"] == ["/reader/ruth-he/reader/index.html?k=k"]
    assert answer["hebrew"] == 1, "the Hebrew run is marked as Hebrew"
    assert "working" not in answer["cls"]
    assert page["sendDisabled"] is False


def test_a_refusal_is_drawn_as_the_answer_and_nothing_is_stuck() -> None:
    page = run(
        do=[
            {"type": "say", "text": "hi"},
            {
                "type": "stream",
                "event": "error",
                "data": json.dumps(
                    {"message": "A lot of conversation for one day. Try again in 24 hours."}
                ),
            },
        ],
        answers={"/chat/say": {"chat": "abc", "turn": 1}},
    )
    assert page["turns"][1]["cls"] == "turn them bad"
    assert page["turns"][1]["text"].startswith("A lot of conversation")
    assert page["sendDisabled"] is False


def test_a_refused_line_is_said_in_place() -> None:
    page = run(
        do=[{"type": "say", "text": "hi"}],
        answers={
            "/chat/say": {"error": "Nothing new can be built now. Everything you have still opens."}
        },
    )
    assert page["streams"] == []
    assert "bad" in page["turns"][1]["cls"] and "still opens" in page["turns"][1]["text"]


def test_hosted_there_is_no_key_in_the_address() -> None:
    page = run(
        do=[{"type": "say", "text": "hi"}],
        answers={"/chat/say": {"chat": "abc", "turn": 1}},
        key="",
    )
    assert page["streams"] == ["/chat/stream/abc/1"]


QUOTE = {
    "id": "j1",
    "title": "מאמר על הים",
    "english": "An article about the sea",
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


def test_a_quote_is_drawn_as_a_card_and_the_press_posts_to_build() -> None:
    """The card is drawn from the quote the server sent, not from the model's words, and
    the button posts to the same door the Add page's button posts to."""
    page = run(
        do=[
            {"type": "say", "text": "bring this in"},
            {"type": "stream", "event": "quote", "data": json.dumps(QUOTE, ensure_ascii=False)},
            {"type": "stream", "event": "done", "data": json.dumps({"text": "Forty sentences."})},
            {"type": "press", "selector": "quote-go"},
        ],
        answers={"/chat/say": {"chat": "abc", "turn": 1}, "/build": {**QUOTE, "stage": "queued"}},
    )
    card = page["cards"][0]
    assert card["title"] == "מאמר על הים" and card["english"] == "An article about the sea"
    assert card["meta"] == "40 sentences · A couple of minutes."
    assert "$" not in json.dumps(card), "never money"
    assert card["button"] == "Read this"
    assert [p["path"] for p in page["posted"]] == ["/chat/say", "/build"]
    assert page["posted"][1]["body"] == {"id": "j1"}
    assert card["note"].startswith("Building.") and card["cls"] == "quote started"
    assert page["stripAsked"] == 1, "the strip is told to look again"


def test_a_blocked_quote_has_no_button() -> None:
    blocked = {
        **QUOTE,
        "stage": "blocked",
        "blocked": "Too long. Try a chapter, or something from the library.",
    }
    page = run(
        do=[
            {"type": "say", "text": "bring this in"},
            {"type": "stream", "event": "quote", "data": json.dumps(blocked, ensure_ascii=False)},
        ],
        answers={"/chat/say": {"chat": "abc", "turn": 1}},
    )
    card = page["cards"][0]
    assert card["button"] == "" and card["note"].startswith("Too long")
    assert card["cls"] == "quote refused"


def test_a_recording_is_quoted_in_hours() -> None:
    spoken = {**QUOTE, "audio": True, "seconds": 5400, "parts": 3, "total": 60}
    page = run(
        do=[
            {"type": "say", "text": "this podcast"},
            {"type": "stream", "event": "quote", "data": json.dumps(spoken, ensure_ascii=False)},
        ],
        answers={"/chat/say": {"chat": "abc", "turn": 1}},
    )
    assert page["cards"][0]["meta"].startswith("1.5 hours of audio · First part in")


def test_a_refused_press_says_why_on_the_card() -> None:
    page = run(
        do=[
            {"type": "say", "text": "bring this in"},
            {"type": "stream", "event": "quote", "data": json.dumps(QUOTE, ensure_ascii=False)},
            {"type": "press", "selector": "quote-go"},
        ],
        answers={
            "/chat/say": {"chat": "abc", "turn": 1},
            "/build": {
                **QUOTE,
                "stage": "blocked",
                "blocked": "Building a lot at once. Try again in 24 hours.",
            },
        },
    )
    card = page["cards"][0]
    assert card["note"].startswith("Building a lot") and card["cls"] == "quote refused"
    assert page["stripAsked"] == 0
