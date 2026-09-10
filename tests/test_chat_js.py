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
    do: list[dict[str, Any]] | None = None,
    answers: dict[str, Any] | None = None,
    key: str = "k",
    record: bool = False,
    hash: str = "",
    ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "key": key,
        "record": record,
        "hash": hash,
        "ledger": ledger,
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
    assert answer["text"] == "Try רות at Open ruth", "the path is drawn as a door, not read"
    assert answer["links"] == ["/reader/ruth-he/reader/index.html?k=k"]
    assert page["doors"] == [
        {"href": "/reader/ruth-he/reader/index.html?k=k", "text": "Open ruth"}
    ], "a path is a door the reader presses, named by its folder"
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
    assert page["turns"][1]["cls"] == "chat-turn them bad"
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
    assert card["note"].startswith("Building.") and card["cls"] == "quote-card started"
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
    assert card["cls"] == "quote-card refused"


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
    assert card["note"].startswith("Building a lot") and card["cls"] == "quote-card refused"
    assert page["stripAsked"] == 0


def test_the_list_carries_the_hours_and_hebrew_is_drawn_in_pairs() -> None:
    page = run(
        do=[
            {"type": "say", "text": "hello"},
            {
                "type": "stream",
                "event": "done",
                "data": json.dumps(
                    {"text": "> שָׁלוֹם\n= hello\nמַה שְּׁלוֹמְךָ?\n= How are you?"}, ensure_ascii=False
                ),
            },
        ],
        answers={
            "/chat/list": {
                "chats": [],
                "usable": True,
                "hours": {"used": 1.5, "allowed": 8, "ends": "1 October"},
            },
            "/chat/say": {"chat": "abc", "turn": 1},
        },
    )
    assert page["hours"] == "1.5 of 8 hours this month"
    pairs = [{k: p[k] for k in ("he", "en", "recast")} for p in page["pairs"]]
    assert pairs == [
        {"he": "שָׁלוֹם", "en": "hello", "recast": True},
        {"he": "מַה שְּׁלוֹמְךָ?", "en": "How are you?", "recast": False},
    ]


def test_in_hebrew_a_path_on_its_own_line_is_a_door_between_the_pairs() -> None:
    """The bug this guards: the pair parser dropped every line without Hebrew in it,
    so a reader who asked to read a text was told it was open and given no way in.
    """
    page = run(
        do=[
            {"type": "say", "text": "let's read the small lie"},
            {
                "type": "stream",
                "event": "done",
                "data": json.dumps(
                    {
                        "text": "> בּוֹא נִקְרָא\n= Let's read\n"
                        "/reader/%D7%94%D7%A9%D7%A7%D7%A8-he/reader/index.html\n"
                        "מָה הָיָה קָשֶׁה?\n= What was hard?"
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        answers={"/chat/say": {"chat": "abc", "turn": 1}},
    )
    assert [p["he"] for p in page["pairs"]] == ["בּוֹא נִקְרָא", "מָה הָיָה קָשֶׁה?"]
    assert page["doors"] == [
        {"href": "/reader/%D7%94%D7%A9%D7%A7%D7%A8-he/reader/index.html?k=k", "text": "Open השקר"}
    ]


def test_a_plain_answer_is_still_a_line() -> None:
    page = run(
        do=[
            {"type": "say", "text": "hi"},
            {"type": "stream", "event": "done", "data": json.dumps({"text": "Try Ruth."})},
        ],
        answers={"/chat/say": {"chat": "abc", "turn": 1}},
    )
    assert page["pairs"] == [] and page["turns"][1]["text"] == "Try Ruth."


def test_the_microphone_appears_where_the_browser_records() -> None:
    page = run(do=[], record=True)
    assert page["mic"]["hidden"] is False
    page = run(do=[], record=False)
    assert page["mic"]["hidden"] is True, "a page never offers what the browser cannot do"


def test_the_microphone_is_kept_from_a_reader_with_no_modern_hebrew() -> None:
    """`talk` on `/chat/list` is the server's word on whether a conversation in Hebrew
    is offered — a reader whose every text is scripture is answered in English about
    the text, and is not offered a microphone to speak Hebrew into."""
    page = run(
        do=[], record=True, answers={"/chat/list": {"chats": [], "usable": True, "talk": False}}
    )
    assert page["mic"]["hidden"] is True
    page = run(
        do=[], record=True, answers={"/chat/list": {"chats": [], "usable": True, "talk": True}}
    )
    assert page["mic"]["hidden"] is False


def test_a_conversation_named_in_the_hash_is_the_one_opened() -> None:
    """The front door's box posts a line and lands here with the new conversation's id
    in the hash; the page opens that one, not the newest on the list."""
    chats = [{"id": "new", "title": "newest"}, {"id": "abc", "title": "from the door"}]
    page = run(
        do=[],
        answers={
            "/chat/list": {"chats": chats, "usable": True},
            "/chat/abc": {
                "chat": {"id": "abc"},
                "turns": [{"n": 1, "role": "user", "said": "hi", "stage": "done"}],
            },
            "/chat/new": {"chat": {"id": "new"}, "turns": []},
        },
        hash="#abc",
    )
    assert [t["text"] for t in page["turns"]] == ["hi"], "the door's conversation, not the newest"
    page = run(
        do=[],
        answers={
            "/chat/list": {"chats": chats, "usable": True},
            "/chat/new": {"chat": {"id": "new"}, "turns": []},
        },
        hash="#nowhere",
    )
    assert page["turns"] == [], "a hash naming no conversation of theirs opens the newest"


def test_a_recording_goes_up_as_itself_and_comes_back_as_the_reader_s_line() -> None:
    page = run(
        do=[{"type": "record"}],
        answers={"/chat/hear": {"chat": "abc", "turn": 1, "heard": "שלום לך"}},
        record=True,
    )
    assert page["posted"] == [{"path": "/chat/hear", "body": "<blob audio/webm>"}]
    assert page["streams"] == ["/chat/stream/abc/1?k=k"]
    assert [t["text"] for t in page["turns"]] == ["שלום לך", ""]
    assert page["mic"]["pressed"] == "false" and page["mic"]["label"] == "Speak"
    assert page["mic"]["text"] == "", "the word is the label, not the face (2026-09-10)"


def test_an_answer_in_hebrew_mode_can_be_heard() -> None:
    page = run(
        do=[
            {"type": "say", "text": "hi"},
            {
                "type": "stream",
                "event": "done",
                "data": json.dumps({"text": "שָׁלוֹם\n= hello"}, ensure_ascii=False),
            },
            {"type": "press", "selector": "chat-play"},
        ],
        answers={"/chat/say": {"chat": "abc", "turn": 1}},
        record=True,
    )
    assert page["plays"] == ["/chat/audio/abc/1?k=k"], (
        "the press asks for the clip and nothing else is posted"
    )
    assert [p["path"] for p in page["posted"]] == ["/chat/say"]


#: A reply in Hebrew, and its words as the server reads them.
RECORD_TEXT = (
    "> נָסַעְתִּי לַנֶּגֶב.\n= I went to the Negev.\nהָיָה חַם בְּמִצְפֵּה רָמוֹן?\n= Was it hot at Mitzpe Ramon?"
)


def spans(line: str) -> list[tuple[int, int]]:
    """Where each word sits in a pointed line: what the server's reader reports."""
    out = []
    at = 0
    for piece in line.split(" "):
        start = line.index(piece, at)
        at = start + len(piece)
        word = piece.rstrip("?.,!")
        out.append((start, start + len(word)))
    return out


def read(line: str, forms: list[tuple[str, str, int, str]]) -> dict[str, Any]:
    return {
        "he": line,
        "words": [
            {
                "start": start,
                "end": end,
                "lemma": lemma,
                "pos": pos,
                "band": band,
                "meaning": meaning,
            }
            for (start, end), (lemma, pos, band, meaning) in zip(spans(line), forms, strict=True)
        ],
    }


RECORD_WORDS = {
    "lines": [
        read("נָסַעְתִּי לַנֶּגֶב.", [("נסע", "VERB", 3, ""), ("נגב", "PROPN", 0, "")]),
        read(
            "הָיָה חַם בְּמִצְפֵּה רָמוֹן?",
            [
                ("היה", "VERB", 1, "was"),
                ("חם", "ADJ", 2, "hot"),
                ("מצפה", "NOUN", 5, ""),
                ("רמון", "PROPN", 0, ""),
            ],
        ),
    ],
    "outside": 0.25,
}
LEDGER = {"היה": {"status": 9}, "חם": {"status": 2}, "נסע": {"status": 9}}


def record_page(extra: list[dict[str, Any]] | None = None, **answers: Any) -> dict[str, Any]:
    return run(
        do=[
            {"type": "say", "text": "I went to the Negev"},
            {"type": "stream", "event": "text", "data": RECORD_TEXT},
            {
                "type": "stream",
                "event": "words",
                "data": json.dumps(RECORD_WORDS, ensure_ascii=False),
            },
            {
                "type": "stream",
                "event": "done",
                "data": json.dumps({"text": RECORD_TEXT, "seconds": 250}, ensure_ascii=False),
            },
        ]
        + (extra or []),
        answers={"/chat/say": {"chat": "abc", "turn": 1}, **answers},
        ledger=LEDGER,
    )


def test_the_words_take_their_state_from_the_reader_s_ledger() -> None:
    """The record forming: each word of a Hebrew line is drawn on the page with what
    the ledger says of it — known bare, learning underlined, not met marked and
    counted — and a name is left alone."""
    page = record_page()
    first, second = page["pairs"]
    assert [w["text"] for w in second["words"]] == ["הָיָה", "חַם", "בְּמִצְפֵּה", "רָמוֹן"], (
        "each word spans its own pointed text, in order"
    )
    assert [w["state"] for w in second["words"]] == ["known", "learning", "new", ""], (
        "known, learning, not met, and a name that is neither"
    )
    assert [w["state"] for w in first["words"]] == ["known", ""]
    assert second["he"] == "הָיָה חַם בְּמִצְפֵּה רָמוֹן?", "the line reads whole"


def test_the_foot_counts_what_was_not_met_and_never_names_a_level() -> None:
    page = record_page()
    foot = page["foot"]
    assert foot is not None and foot["save"]
    assert foot["counts"] == "4 min · 1 word you have not met · you knew 50% of this", (
        "four minutes off the clock; מצפה not met; two of four vocabulary words known"
    )
    assert "level" not in foot["counts"] and "%" in foot["counts"]


def test_a_word_tapped_shows_what_is_held_and_offers_to_look_the_rest_up() -> None:
    page = record_page(
        extra=[{"type": "press", "selector": "chat-w"}],
    )
    # The newest `.chat-w` is רמון, a name with nothing held: the press opens the line
    # with the dictionary form and a look-it-up button, and nothing is posted for it.
    assert page["pairs"][1]["gloss"] == "רמוןlook it up"
    assert [p["path"] for p in page["posted"]] == ["/chat/say"], "nothing bought by a tap"


def test_save_as_targum_is_the_reader_s_press_and_draws_the_quote() -> None:
    page = record_page(
        extra=[{"type": "press", "selector": "chat-save"}],
        **{"/chat/save": {"quote": QUOTE, "lines": 2}},
    )
    assert [p["path"] for p in page["posted"]] == ["/chat/say", "/chat/save"]
    assert page["posted"][1]["body"] == {"chat": "abc"}
    (card,) = page["cards"]
    assert card["title"] == QUOTE["title"] and card["button"] == "Read this", (
        "the same card the model's own save hands the page; the button is the spend"
    )
    assert page["foot"]["save"] is False, "one press; the card stands where it was"


def test_a_conversation_come_back_to_is_drawn_with_its_words() -> None:
    """The words kept on the reader's turn draw the answer that follows it."""
    page = run(
        do=[],
        answers={
            "/chat/list": {"chats": [{"id": "abc", "title": "t"}], "usable": True},
            "/chat/abc": {
                "chat": {"id": "abc", "mode": "talk"},
                "seconds": 130,
                "turns": [
                    {"n": 1, "role": "user", "said": "hi", "stage": "done", "words": RECORD_WORDS},
                    {
                        "n": 2,
                        "role": "assistant",
                        "said": RECORD_TEXT,
                        "stage": "done",
                        "words": None,
                    },
                ],
            },
        },
        ledger=LEDGER,
    )
    assert [w["state"] for w in page["pairs"][1]["words"]] == ["known", "learning", "new", ""]
    assert page["foot"]["counts"].startswith("2 min · 1 word you have not met")


BUILT = {
    "/prepare": QUOTE,
    "/build": dict(QUOTE, stage="working"),
    "/job/j1": dict(QUOTE, stage="done", reader="story-he/reader/index.html"),
}


def test_a_file_chosen_by_the_plus_is_held_and_sent_as_a_card_in_the_thread() -> None:
    """The + on the conversation page: the file is held in the box as a chip, Send
    takes it up and prices it, and the card is a turn of its own — no model in the
    loop, and the same card the model's quote is."""
    page = run(do=[{"type": "file", "file": {"name": "story.txt", "content": "שלום"}}])
    assert page["posted"] == [] and page["held"] == ["story.txt"], "held, not yet brought"
    page = run(
        do=[
            {"type": "file", "file": {"name": "story.txt", "content": "שלום"}},
            {"type": "send"},
        ],
        answers=BUILT,
    )
    assert [p["path"] for p in page["posted"]] == ["/prepare", "/build"], "no line was said"
    (card,) = page["cards"]
    assert card["title"] == QUOTE["title"]
    assert card["button"] == "", "Send was the press: no button to press again"
    assert card["note"] == "Building. It will appear above when it is ready."
    assert "started" in card["cls"]
    assert page["turns"][-1]["cls"] == "chat-turn them"
    assert page["sendDisabled"] is False and page["held"] == []
    assert page["went"] == "/reader/story-he/reader/index.html?k=k", "opened when ready"


def test_a_line_that_only_says_open_this_starts_no_conversation() -> None:
    page = run(
        do=[
            {"type": "file", "file": {"name": "story.txt", "content": "שלום"}},
            {"type": "send", "text": "Open this"},
        ],
        answers=BUILT,
    )
    assert [p["path"] for p in page["posted"]] == ["/prepare", "/build"]
    assert page["went"] == "/reader/story-he/reader/index.html?k=k"


def test_a_quote_the_rails_refused_says_why_on_its_card() -> None:
    page = run(
        do=[{"type": "file", "file": {"name": "story.txt", "content": "שלום"}}, {"type": "send"}],
        answers={"/prepare": dict(QUOTE, stage="blocked", blocked="Too long.")},
    )
    assert [p["path"] for p in page["posted"]] == ["/prepare"], "not pressed"
    (card,) = page["cards"]
    assert card["note"] == "Too long." and "refused" in card["cls"]


def test_a_line_that_says_more_follows_its_card_as_a_specification() -> None:
    """A specification for the model rides after the card with a note of what was
    sent, and the page stays: the reader opens from the card or the strip."""
    page = run(
        do=[
            {"type": "file", "file": {"name": "story.txt", "content": "שלום"}},
            {"type": "send", "text": "what is this about"},
        ],
        answers={**BUILT, "/chat/say": {"chat": "abc", "turn": 1}},
    )
    assert [p["path"] for p in page["posted"]] == ["/prepare", "/build", "/chat/say"]
    assert page["posted"][2]["body"]["brought"] == "j1", "the model is told what was sent"
    assert len(page["cards"]) == 1
    assert page["went"] == "", "a conversation was wanted, so the page stays"
    assert [t["text"] for t in page["turns"] if t["cls"].startswith("chat-turn me")] == [
        "what is this about"
    ]


def test_a_recording_chosen_by_the_plus_goes_up_in_pieces_first() -> None:
    page = run(
        do=[{"type": "file", "file": {"name": "talk.mp3", "size": 10}}, {"type": "send"}],
        answers={
            "/upload/begin": {"upload": "u1", "chunk": 5},
            "/upload/u1/0": {},
            "/upload/u1/1": {},
            "/upload/u1/end": {"upload": "u1"},
            "/prepare": dict(QUOTE, audio=True, seconds=600, parts=1),
            "/build": dict(QUOTE, audio=True, seconds=600, parts=1, stage="working"),
            "/job/j1": dict(QUOTE, audio=True, stage="done", reader="talk-he/reader/index.html"),
        },
    )
    assert [p["path"] for p in page["posted"]] == [
        "/upload/begin",
        "/upload/u1/0",
        "/upload/u1/1",
        "/upload/u1/end",
        "/prepare",
        "/build",
    ]
    assert page["posted"][-2]["body"]["upload"] == "u1"
    (card,) = page["cards"]
    assert card["meta"].startswith("10 minutes of audio")


PAGES = dict(
    QUOTE,
    pages=2,
    segments=12,
    total=12,
    doubtful=1,
    excerpt=["נָסַעְתִּי לַנֶּגֶב בַּשָּׁבוּעַ שֶׁעָבַר", "בבוקר יצאנו לטיול ארוך"],
)


def test_a_text_brought_with_a_line_follows_that_line_in_its_conversation() -> None:
    page = run(
        answers={
            "/chat/list": {"chats": [{"id": "abc", "title": "from the door"}], "usable": True},
            "/chat/abc": {
                "chat": {"id": "abc"},
                "turns": [{"n": 1, "role": "user", "said": "read this with me", "stage": "done"}],
            },
            "/job/j1": PAGES,
        },
        hash="#abc&job=j1",
    )
    assert [t["text"] for t in page["turns"] if t["cls"].startswith("chat-turn me")] == [
        "read this with me"
    ]
    (card,) = page["cards"]
    assert card["title"] == QUOTE["title"]


def test_a_reader_with_nothing_marked_is_not_told_they_knew_nothing() -> None:
    """ "You knew 0% of this" is a score of zero, which the brand rules keep out. On a
    first day the foot says how many words there were and that marking begins in a
    text."""
    page = run(
        do=[
            {"type": "say", "text": "hi"},
            {"type": "stream", "event": "text", "data": RECORD_TEXT},
            {
                "type": "stream",
                "event": "words",
                "data": json.dumps(RECORD_WORDS, ensure_ascii=False),
            },
            {
                "type": "stream",
                "event": "done",
                "data": json.dumps({"text": RECORD_TEXT, "seconds": 70}),
            },
        ],
        answers={"/chat/say": {"chat": "abc", "turn": 1}},
        ledger={},
    )
    assert page["foot"]["counts"] == "1 min · 4 words · none marked yet"
    assert "%" not in page["foot"]["counts"] and "not met" not in page["foot"]["counts"]


def test_pictures_chosen_by_the_plus_are_one_text_and_one_turn() -> None:
    """Two pages photographed one after another: held, then up one at a time on Send,
    priced once, one card in the thread — the same card the front door draws for them."""
    page = run(
        do=[
            {
                "type": "file",
                "files": [{"name": "p1.jpg", "size": 10}, {"name": "p2.png", "size": 10}],
            },
            {"type": "send"},
        ],
        answers={
            "/upload/begin": {"upload": "u1", "chunk": 100},
            "/upload/u1/0": {},
            "/upload/u1/end": {"upload": "u1", "picture": True},
            "/prepare": dict(QUOTE, pages=2, doubtful=0, excerpt=["שורה ראשונה"]),
            "/build": dict(QUOTE, pages=2, stage="working"),
            "/job/j1": dict(QUOTE, pages=2, stage="done", reader="pages-he/reader/index.html"),
        },
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
    assert page["posted"][-2]["body"]["uploads"] == ["u1", "u1"]
    sent = page["turns"][0]
    assert "me" in sent["cls"].split() and sent["pictures"] == ["blob:p1.jpg", "blob:p2.png"], (
        "the pictures sent are seen in the thread, as the reader's own turn"
    )
    (card,) = page["cards"]
    assert card["title"] == QUOTE["title"] and "started" in card["cls"]
    assert card["meta"].startswith("2 pages")


def test_the_chat_page_starts_the_sync_like_every_other_page() -> None:
    """Signed in, the chat used to say "Sign in".

    `TargumSync.start()` is what asks `/account/me`, and the header is rendered with the
    signed-out button and filled from the answer — so a reader talking to targum was
    told to sign in. Every other page calls it: Learn, Library, Progress, Add, Yours.
    This one did not, and the page works either way because it authenticates
    server-side with `TARGUM_KEY`, which is why nothing looked wrong.

    The half that is not cosmetic: `start()` runs the first `exchange()`, so a reader who
    came straight to the chat and stayed had no word sync at all that visit
    (targum-internal#232).
    """
    assert run()["syncStarted"] is True
