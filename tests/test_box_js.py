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


def test_the_front_door_says_the_hours_only_when_they_are_nearly_gone() -> None:
    """The same line the conversation page draws, above the same box (targum-internal#237)."""
    page = run(
        answers={
            "/chat/list": {
                "chats": [],
                "usable": True,
                "hours": {"used": 7, "allowed": 8, "ends": "1 October"},
            }
        }
    )
    assert page["hours"] == {
        "text": "7 of 8 hours used this month. Resets 1 October.",
        "hidden": False,
    }
    quiet = run(
        answers={
            "/chat/list": {
                "chats": [],
                "usable": True,
                "hours": {"used": 1.5, "allowed": 8, "ends": "1 October"},
            }
        }
    )
    assert quiet["hours"]["hidden"] and quiet["hours"]["text"] == ""


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


def test_a_file_chosen_by_the_plus_is_held_until_send() -> None:
    """Choosing is not bringing (2026-09-07): the file sits in the box as a chip, the
    way a typed line sits in the field, and nothing goes up until Send."""
    page = run(do=[{"type": "file", "file": {"name": "story.txt", "content": "שלום"}}])
    assert page["posted"] == [] and page["went"] == ""
    assert page["held"] == ["story.txt"] and page["heldHidden"] is False


def test_the_x_on_a_chip_lets_that_file_go() -> None:
    page = run(
        do=[
            {"type": "file", "files": [{"name": "a.png"}, {"name": "b.png"}]},
            {"type": "drop", "index": 0},
        ]
    )
    assert page["held"] == ["b.png"]
    page = run(do=[{"type": "file", "file": {"name": "a.png"}}, {"type": "drop", "index": 0}])
    assert page["held"] == [] and page["heldHidden"] is True


STARTED = dict(QUOTE, stage="working")
DONE = dict(QUOTE, stage="done", reader="story-he/reader/index.html")
BUILT = {"/prepare": QUOTE, "/build": STARTED, "/job/j1": DONE}


def test_send_with_a_file_opens_it() -> None:
    """The Add page's job in one press, from the box: the file read whole, `/prepare`
    asked, `/build` pressed — Send with a file is the press (2026-09-07) — the build
    followed, and the reader opened when it is ready. No conversation is started:
    "when I wrote 'open this' with a file, I didn't want that to be the start of a
    conversation." """
    page = run(
        do=[
            {"type": "file", "file": {"name": "story.txt", "content": "שלום"}},
            {"type": "send"},
        ],
        answers=BUILT,
    )
    assert [p["path"] for p in page["posted"]] == ["/prepare", "/build"], "no line was said"
    assert page["posted"][0]["body"]["name"] == "story.txt"
    assert page["posted"][1]["body"] == {"id": "j1"}
    assert page["went"] == "/reader/story-he/reader/index.html?k=k"
    assert page["held"] == []


def test_a_line_that_only_says_open_this_is_the_files_own_meaning() -> None:
    for line in ("Open this", "read it please", "תפתח את זה", "Open the pdf."):
        page = run(
            do=[
                {"type": "file", "file": {"name": "story.txt", "content": "שלום"}},
                {"type": "send", "text": line},
            ],
            answers=BUILT,
        )
        assert [p["path"] for p in page["posted"]] == ["/prepare", "/build"], line
        assert page["went"] == "/reader/story-he/reader/index.html?k=k", line


def test_a_quote_the_rails_refused_is_said_under_the_box() -> None:
    page = run(
        do=[{"type": "file", "file": {"name": "story.txt", "content": "שלום"}}, {"type": "send"}],
        answers={"/prepare": dict(QUOTE, stage="blocked", blocked="Too long.")},
    )
    assert [p["path"] for p in page["posted"]] == ["/prepare"], "not pressed"
    assert page["went"] == ""
    assert page["said"] == {"text": "Too long.", "hidden": False}
    assert page["held"] == ["story.txt"] and page["sendDisabled"] is False


def test_a_build_that_fails_is_said_under_the_box() -> None:
    page = run(
        do=[{"type": "file", "file": {"name": "story.txt", "content": "שלום"}}, {"type": "send"}],
        answers={**BUILT, "/job/j1": dict(QUOTE, stage="failed", error="Something went wrong.")},
    )
    assert page["went"] == ""
    assert page["said"]["text"] == "Something went wrong."


def test_a_line_that_says_more_is_a_specification_and_opens_the_conversation() -> None:
    """ "I still want the possibility for the user to send specifications in the chat":
    a line that says more than "open this" is said, with a note of what was sent, and
    the conversation page opens on it with the card as a turn. The text still builds."""
    page = run(
        do=[
            {"type": "file", "file": {"name": "story.txt", "content": "שלום"}},
            {"type": "send", "text": "Open this and help me learn it."},
        ],
        answers={**BUILT, "/chat/say": {"chat": "abc", "turn": 1}},
    )
    assert [p["path"] for p in page["posted"]] == ["/prepare", "/build", "/chat/say"]
    assert page["posted"][2]["body"] == {
        "chat": "",
        "text": "Open this and help me learn it.",
        "brought": "j1",
    }, "the model is told what was sent"
    assert page["went"] == "/chat?k=k#abc&job=j1"


def test_a_recording_chosen_by_the_plus_goes_up_in_pieces() -> None:
    page = run(
        do=[{"type": "file", "file": {"name": "talk.mp3", "size": 10}}, {"type": "send"}],
        answers={
            **UPLOAD,
            **BUILT,
            "/prepare": dict(QUOTE, audio=True, seconds=600, parts=1),
        },
    )
    assert [p["path"] for p in page["posted"]] == [
        "/upload/begin",
        "/upload/u1/0",
        "/upload/u1/1",
        "/upload/u1/2",
        "/upload/u1/end",
        "/prepare",
        "/build",
    ]
    assert page["posted"][-2]["body"]["upload"] == "u1"
    assert page["went"] == "/reader/story-he/reader/index.html?k=k"


def test_the_same_bytes_already_brought_open_the_text() -> None:
    page = run(
        do=[{"type": "file", "file": {"name": "talk.mp3", "size": 10}}, {"type": "send"}],
        answers={**UPLOAD, "/upload/u1/end": {"reader": "talk-he/reader/index.html"}},
    )
    assert page["went"] == "/reader/talk-he/reader/index.html?k=k"
    assert not any(p["path"] == "/prepare" for p in page["posted"])


def test_a_refused_file_is_said_under_the_box_and_kept() -> None:
    page = run(
        do=[
            {"type": "file", "file": {"name": "story.txt", "content": "שלום"}},
            {"type": "send"},
        ],
        answers={"/prepare": {"error": "targum cannot read '.rtf' files."}},
    )
    assert page["went"] == ""
    assert page["said"] == {"text": "targum cannot read '.rtf' files.", "hidden": False}
    assert page["held"] == ["story.txt"], "still in the box, to try again or let go"
    assert page["sendDisabled"] is False


PICTURES = {
    "/upload/begin": {"upload": "u1", "chunk": 100},
    "/upload/u1/0": {},
    "/upload/u1/end": {"upload": "u1", "picture": True},
}


def test_several_pictures_chosen_together_are_one_text() -> None:
    """Two photos of one handout: each goes up the chunked door on Send, `/prepare` is
    asked once with both, and the conversation page opens on the card."""
    page = run(
        do=[
            {"type": "file", "files": [{"name": "page1.jpg", "size": 10}]},
            {"type": "file", "files": [{"name": "page2.HEIC", "size": 10}]},
            {"type": "send"},
        ],
        answers={**PICTURES, **BUILT, "/prepare": dict(QUOTE, pages=2)},
    )
    assert [p["path"] for p in page["posted"]] == [
        "/upload/begin",
        "/upload/u1/0",
        "/upload/u1/end",
        "/upload/begin",
        "/upload/u1/0",
        "/upload/u1/end",
        "/prepare",
        "/build",
    ]
    assert page["posted"][-2]["body"]["uploads"] == ["u1", "u1"], "one text, in order"
    assert page["went"] == "/reader/story-he/reader/index.html?k=k"


def test_a_pdf_goes_up_the_chunked_door_and_is_priced_as_one_upload() -> None:
    page = run(
        do=[{"type": "file", "file": {"name": "handout.pdf", "size": 10}}, {"type": "send"}],
        answers={**PICTURES, **BUILT, "/upload/u1/end": {"upload": "u1", "pages": 3}},
    )
    assert [p["path"] for p in page["posted"]][-3:] == ["/upload/u1/end", "/prepare", "/build"]
    assert page["posted"][-2]["body"]["upload"] == "u1"
    assert "content" not in page["posted"][-2]["body"], "not read whole as base64"


def test_pictures_and_a_text_chosen_together_are_refused_under_the_box() -> None:
    page = run(
        do=[
            {"type": "file", "files": [{"name": "page1.png", "size": 10}, {"name": "notes.txt"}]},
            {"type": "send"},
        ],
        answers={**PICTURES, "/prepare": QUOTE},
    )
    assert page["posted"] == [], "nothing went up"
    assert page["said"]["text"] == "Several files at once must all be pictures of one text."
    assert page["held"] == ["page1.png", "notes.txt"], "kept, so one can be let go"
    assert page["sendDisabled"] is False
