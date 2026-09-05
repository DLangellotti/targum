"""One turn of conversation, against a model that is a script.

The loop in `chat/session.py` is the first thing here to stream, to call tools and to
carry a conversation, so it is run rather than read: a fake client hands back the
messages a test wrote, and what is checked is the shape of what goes back to the API —
which is what the real one will refuse if it is wrong.
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from targum import level
from targum.accounts import Store
from targum.chat import MAX_STEPS, TURN_RESERVE, tools
from targum.chat import session as session_module
from targum.serve import Library


class Stream:
    """What `client.messages.stream(...)` returns: events to walk, then a final message."""

    def __init__(self, reply: Any) -> None:
        self.reply = reply

    def __enter__(self) -> Stream:
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def __iter__(self) -> Any:
        for block in self.reply.content:
            if block.get("type") == "text":
                for piece in block["text"].split(" "):
                    yield SimpleNamespace(
                        type="content_block_delta",
                        delta=SimpleNamespace(type="text_delta", text=piece + " "),
                    )

    def get_final_message(self) -> Any:
        return self.reply


def reply(content: list[dict[str, Any]], stop: str = "end_turn") -> Any:
    return SimpleNamespace(
        content=content,
        stop_reason=stop,
        usage=SimpleNamespace(input_tokens=100, output_tokens=20),
    )


class Script:
    """A client that answers each call with the next scripted reply and keeps the
    requests, so a test can read back what the API would have been sent."""

    def __init__(self, replies: list[Any]) -> None:
        self.replies = list(replies)
        self.requests: list[dict[str, Any]] = []
        self.messages = self

    def stream(self, **request: Any) -> Stream:
        # A copy: the loop keeps appending to the very list it sent, and a request read
        # back later has to say what was sent, not what the list became.
        self.requests.append({**request, "messages": copy.deepcopy(request["messages"])})
        if not self.replies:
            return Stream(reply([{"type": "text", "text": "out of script"}]))
        return Stream(self.replies.pop(0))


def world(tmp_path: Path) -> tuple[Library, Store]:
    store = Store(tmp_path / "words.db")
    out = tmp_path / "out"
    out.mkdir()
    return Library(out, store=store), store


def context(library: Library, store: Store) -> tools.Ctx:
    return tools.Ctx(
        person=None,
        home=library.home(None),
        library=library,
        store=store,
        chat_id="c",
        level=level.EMPTY,
    )


def test_a_plain_answer_streams_and_is_kept(tmp_path: Path) -> None:
    library, store = world(tmp_path)
    client = Script([reply([{"type": "text", "text": "Try Ruth first."}])])
    feed = session_module.Feed()
    kept: list[tuple[str, str]] = []
    usage = session_module.run_turn(
        client,
        context(library, store),
        [{"role": "user", "content": "what should I read"}],
        feed,
        lambda role, content, said: kept.append((role, said)),
    )
    assert feed.text().strip() == "Try Ruth first."
    assert kept == [("assistant", "Try Ruth first.")]
    assert usage.calls == 1 and usage.input_tokens == 100
    sent = client.requests[0]
    assert sent["messages"][-1]["role"] == "user"
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}, "the stable half is cached"
    assert "cache_control" not in sent["system"][1], "the ledger sits after the breakpoint"
    assert [tool["name"] for tool in sent["tools"]] == [tool.name for tool in tools.REGISTRY]


def test_tool_results_go_back_in_one_message_in_order(tmp_path: Path) -> None:
    library, store = world(tmp_path)
    client = Script(
        [
            reply(
                [
                    {"type": "tool_use", "id": "t1", "name": "my_progress", "input": {}},
                    {"type": "tool_use", "id": "t2", "name": "no_such_tool", "input": {}},
                ],
                stop="tool_use",
            ),
            reply([{"type": "text", "text": "You know nothing yet."}]),
        ]
    )
    feed = session_module.Feed()
    kept: list[tuple[str, list[dict[str, Any]], str]] = []
    session_module.run_turn(
        client,
        context(library, store),
        [{"role": "user", "content": "how am I doing"}],
        feed,
        lambda role, content, said: kept.append((role, content, said)),
    )
    assert client.requests[1]["messages"][-1]["role"] == "user"
    results = client.requests[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"], "all of them, in one message"
    assert results[0]["is_error"] is False and results[1]["is_error"] is True
    assert json.loads(results[0]["content"])["ladder"]["note"] == "A guide, not a placement."
    assert [role for role, _, _ in kept] == ["assistant", "user", "assistant"]
    assert kept[0][2] == "" and kept[2][2] == "You know nothing yet.", "said is the text alone"
    assert [kind for kind, _ in feed.events if kind == "tool"] == ["tool", "tool"]


def test_a_paused_turn_is_resumed_and_a_loop_is_cut_off(tmp_path: Path) -> None:
    library, store = world(tmp_path)
    client = Script(
        [reply([{"type": "text", "text": "searching"}], stop="pause_turn")]
        + [
            reply(
                [{"type": "tool_use", "id": f"t{n}", "name": "my_progress", "input": {}}],
                "tool_use",
            )
            for n in range(20)
        ]
    )
    session_module.run_turn(
        client,
        context(library, store),
        [{"role": "user", "content": "x"}],
        session_module.Feed(),
        lambda *_: None,
    )
    assert len(client.requests) == MAX_STEPS, "a pause is resumed; a loop stops at the cap"


def test_chats_answer_a_turn_off_the_request_and_settle_it(tmp_path: Path) -> None:
    library, store = world(tmp_path)
    client = Script([reply([{"type": "text", "text": "Ruth."}])])
    chats = session_module.Chats(library, store, client_factory=lambda: client)
    asked = chats.say(None, library.home(None), "", "what first", admin=False)
    assert asked.n == 1 and asked.chat_id
    chats.answer(asked)
    feed = chats.feed_for(asked.chat_id, asked.n)
    assert feed is not None and feed.closed
    assert [kind for kind, _ in feed.events][-1] == "done"
    turns = store.chat_turns(asked.chat_id)
    assert [(t["role"], t["said"], t["stage"]) for t in turns] == [
        ("user", "what first", "done"),
        ("assistant", "Ruth.", "done"),
    ]
    job = library.jobs[f"chat-{asked.chat_id}-1"]
    assert job.kind == "chat" and job.stage == "done"
    assert 0 < job.spent < TURN_RESERVE, "settled to the receipt, not the reserve"
    assert store.chats(None)[0]["title"] == "what first"
    assert library.mine(None) == [], "a turn is on the ledger, not in the building strip"


def test_the_chat_rail_refuses_and_names_when_it_lifts(tmp_path: Path) -> None:
    library, store = world(tmp_path)
    library.chat_budget = TURN_RESERVE * 1.5
    client = Script(
        [reply([{"type": "text", "text": "a"}]), reply([{"type": "text", "text": "b"}])]
    )
    chats = session_module.Chats(library, store, client_factory=lambda: client)
    first = chats.say(None, library.home(None), "", "one", admin=False)
    chats.answer(first)
    # Settled to a small receipt, so the second turn's reserve fits; force the ledger
    # to hold the reserve to see the rail bite.
    store.settle(f"chat-{first.chat_id}-1", TURN_RESERVE)
    second = chats.say(None, library.home(None), first.chat_id, "two", admin=False)
    chats.answer(second)
    feed = chats.feed_for(first.chat_id, second.n)
    assert feed is not None
    errors = [json.loads(data) for kind, data in feed.events if kind == "error"]
    assert errors and "conversation" in errors[0]["message"]
    assert (
        "Try again in" in errors[0]["message"] and "library is always free" in errors[0]["message"]
    )
    assert "$" not in errors[0]["message"]
    turn = next(t for t in store.chat_turns(first.chat_id) if t["n"] == second.n)
    assert turn["stage"] == "failed" and turn["error"] == errors[0]["message"]


def test_a_chat_turn_counts_against_the_account_rail_too(tmp_path: Path) -> None:
    """The chat's rail is the narrower one; the account rail still sees the spend, so
    neither can be used to get round the other."""
    library, store = world(tmp_path)
    library.chat_budget = 100.0
    library.account_budget = TURN_RESERVE
    chats = session_module.Chats(library, store, client_factory=lambda: Script([]))
    asked = chats.say(None, library.home(None), "", "hi", admin=False)
    chats.answer(asked)
    from targum.serve import Job

    build = Job(id="b1", source="x", estimate=0.01, owner=None)
    library.jobs[build.id] = build
    library.remember(build)
    store.settle(f"chat-{asked.chat_id}-1", TURN_RESERVE)
    assert "Building a lot" in library.claim(build)


def test_a_failing_model_is_said_to_the_reader_and_released(tmp_path: Path) -> None:
    library, store = world(tmp_path)

    class Broken:
        messages = None

        def __init__(self) -> None:
            self.messages = self

        def stream(self, **_: Any) -> Any:
            raise RuntimeError("boom")

    chats = session_module.Chats(library, store, client_factory=Broken)
    asked = chats.say(None, library.home(None), "", "hi", admin=False)
    chats.answer(asked)
    feed = chats.feed_for(asked.chat_id, asked.n)
    assert feed is not None
    said = [json.loads(data) for kind, data in feed.events if kind == "error"]
    assert said[0]["message"] == "The conversation could not continue. Try again."
    assert "boom" not in json.dumps(said), "the library's own words never reach a reader"
    assert library.jobs[f"chat-{asked.chat_id}-1"].stage == "failed"
    assert store.committed(0) == 0.0, "the reserve went back"


def test_a_feed_tail_waits_rather_than_polls() -> None:
    feed = session_module.Feed()
    start = time.monotonic()
    fresh, closed = feed.wait(0, 0.05)
    assert fresh == [] and not closed and time.monotonic() - start >= 0.04
    feed.put("text", "hi")
    feed.close()
    fresh, closed = feed.wait(0, 1.0)
    assert fresh == [(0, "text", "hi")] and closed


def test_a_quote_reaches_the_page_as_its_own_event(tmp_path: Path, monkeypatch: Any) -> None:
    """The card is drawn from the quote, not from what the model says about it."""
    library, store = world(tmp_path)

    def priced(job: Any) -> None:
        job.title = "מאמר"
        job.segments = 12
        job.total = 12
        job.stage = "ready"

    monkeypatch.setattr(library, "prepare", priced)
    client = Script(
        [
            reply(
                [
                    {
                        "type": "tool_use",
                        "id": "q1",
                        "name": "quote_build",
                        "input": {"source": "https://example.com/a"},
                    }
                ],
                stop="tool_use",
            ),
            reply([{"type": "text", "text": "Twelve sentences, about a minute."}]),
        ]
    )
    feed = session_module.Feed()
    session_module.run_turn(
        client,
        context(library, store),
        [{"role": "user", "content": "bring this in"}],
        feed,
        lambda *_: None,
    )
    quotes = [json.loads(data) for kind, data in feed.events if kind == "quote"]
    assert len(quotes) == 1 and quotes[0]["segments"] == 12 and quotes[0]["stage"] == "ready"
    assert store.committed(0) == 0.0, "quoting spends nothing"
