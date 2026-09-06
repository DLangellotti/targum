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

import pytest

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


@pytest.fixture(autouse=True)
def _record_by_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """No DICTA in a unit test: the record reads a turn's words by whitespace, and holds
    no meanings. `tests/test_chat_record.py` is where the reader itself is tested."""
    from test_chat_record import Spaces

    from targum.chat import record

    monkeypatch.setattr(record.Recorder, "lemmatizer", lambda self: Spaces())
    monkeypatch.setattr(
        record.Recorder,
        "gloss",
        lambda self, lemma, language="he", target="en": (
            self._glosses(lemma, language, target) if self._glosses else ""
        ),
    )
    monkeypatch.setattr(record.Recorder, "__init__", _stub_init)


def _stub_init(self: Any, lemmatizer: Any = None, glosses: Any = None, bands: Any = None) -> None:
    import threading

    from test_chat_record import Bands, Spaces

    self._lemmatizer = lemmatizer or Spaces()
    self._glosses = glosses
    self.bands = bands or Bands()
    self.lock = threading.Lock()


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


def test_web_search_rides_along_only_when_asked_and_is_counted(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """The API runs the search, not us: a `server_tool_use` block is never dispatched as a
    tool of ours, and it is counted on its own axis so the turn settles for what it cost."""
    library, store = world(tmp_path)
    plain = tools.anthropic_tools()
    assert all("type" not in tool for tool in plain)
    searching = tools.anthropic_tools(web_search=True)
    assert searching[-1]["type"] == "web_search_20260209" and searching[-1]["allowed_domains"]
    assert searching[-1]["max_uses"] == tools.WEB_SEARCH_USES

    client = Script(
        [
            reply(
                [
                    {
                        "type": "server_tool_use",
                        "id": "s1",
                        "name": "web_search",
                        "input": {"query": "kan"},
                    },
                    {"type": "web_search_tool_result", "tool_use_id": "s1", "content": []},
                    {"type": "text", "text": "Found two."},
                ]
            )
        ]
    )
    feed = session_module.Feed()
    usage = session_module.run_turn(
        client,
        context(library, store),
        [{"role": "user", "content": "x"}],
        feed,
        lambda *_: None,
        web_search=True,
    )
    assert usage.searches == 1 and usage.cost() > 0
    assert len(client.requests) == 1, "a server tool needs no round trip of ours"
    assert client.requests[0]["tools"][-1]["name"] == "web_search"
    assert [kind for kind, _ in feed.events if kind == "tool"] == ["tool"]

    # On unless the box says not (2026-09-06): a reader who asks for something online
    # and is told the box cannot look is being told the product is smaller than it is.
    monkeypatch.delenv("TARGUM_WEB_SEARCH", raising=False)
    assert session_module.Chats(library, store, client_factory=lambda: client).web_search is True
    monkeypatch.setenv("TARGUM_WEB_SEARCH", "0")
    assert session_module.Chats(library, store, client_factory=lambda: client).web_search is False
    monkeypatch.setenv("TARGUM_WEB_SEARCH", "1")
    assert session_module.Chats(library, store, client_factory=lambda: client).web_search is True


def test_a_hebrew_turn_carries_the_contract_and_the_words_and_is_metered_in_seconds(
    tmp_path: Path,
) -> None:
    """The contract rides in the cached block, the reader's words after the breakpoint,
    and the turn's words land in the same seconds sum a recording's do — for every
    conversation, since the two modes became one on 2026-09-06."""
    from targum.chat import hebrew

    library, store = world(tmp_path)
    person, _ = store.finish_sign_in(store.start_sign_in("r@example.com"))  # type: ignore[misc]
    store.push(
        person,
        {
            "words": [
                {"language": "he", "lemma": "שלום", "status": 9, "band": "easy", "at": 1, "seen": 1}
            ]
        },
    )
    reply_text = "שָׁלוֹם, מַה שְּׁלוֹמְךָ?\n= Hello, how are you?"
    client = Script([reply([{"type": "text", "text": reply_text}])])
    chats = session_module.Chats(library, store, client_factory=lambda: client)
    home = library.home(person)
    asked = chats.say(person, home, "", "hello there friend", admin=False)
    chats.answer(asked)

    sent = client.requests[0]
    assert hebrew.CONTRACT.splitlines()[0] in sent["system"][0]["text"], (
        "the contract is in the cached block"
    )
    assert "known words (1): שלום" in sent["system"][1]["text"], "the ledger after the breakpoint"
    job = library.jobs[f"chat-{asked.chat_id}-1"]
    words = hebrew.words_in("hello there friend", reply_text)
    assert job.seconds == pytest.approx(hebrew.seconds_for(words))
    assert store.hours_used(person.id, 0) == pytest.approx(job.seconds), (
        "in the recordings' own sum"
    )

    # A line in English asking for something to read is the same conversation, under the
    # same contract: the reply is Hebrew, with the door under it, whatever was asked in.
    chats.answer(chats.say(person, home, "", "what to read", admin=False))
    assert hebrew.CONTRACT.splitlines()[0] in client.requests[1]["system"][0]["text"]


def test_a_scripture_only_reader_is_answered_in_english_about_the_text(tmp_path: Path) -> None:
    """Nobody converses in the Hebrew of Judges (2026-09-06). A reader whose every text
    is scripture opens a "find" conversation: no contract in the cached block, and the
    page is told not to offer a microphone. A reader with a modern text, or with nothing
    yet, is written Hebrew at."""
    from targum.chat import hebrew

    library, store = world(tmp_path)
    person, _ = store.finish_sign_in(store.start_sign_in("r@example.com"))  # type: ignore[misc]
    home = library.home(person)

    def shelve(name: str, source: str) -> None:
        folder = home / name
        (folder / "reader").mkdir(parents=True)
        (folder / "reader" / "index.html").write_text("<html></html>", encoding="utf-8")
        (folder / "document.json").write_text(
            json.dumps({"title": name, "language": "he", "source": source, "blocks": []}),
            encoding="utf-8",
        )

    assert library.talks(home, person.id), "nothing yet: the conversation is offered"
    shelve("judges-he", "sefaria:Judges")
    assert not library.talks(home, person.id), "scripture and nothing else"

    client = Script([reply([{"type": "text", "text": "Judges 1 is twelve verses from the end."}])])
    chats = session_module.Chats(library, store, client_factory=lambda: client)
    asked = chats.say(person, home, "", "where was I", admin=False)
    assert store.chat_owned(person.id, asked.chat_id)["mode"] == "find"
    chats.answer(asked)
    assert hebrew.CONTRACT.splitlines()[0] not in client.requests[0]["system"][0]["text"], (
        "no Hebrew contract for a reader with no modern Hebrew"
    )

    shelve("article-he", "https://example.org/story")
    assert library.talks(home, person.id), "one modern text of their own, and it is offered"


def test_a_question_from_a_card_carries_where_the_reader_is_and_is_answered_in_english(
    tmp_path: Path,
) -> None:
    """The reader's note — text, section, sentence, word — rides in the turn the model
    sees and not in what the page shows back; and the conversation it opens is in
    English, about the text, whatever the shelf would otherwise have offered."""
    from targum.chat import hebrew

    library, store = world(tmp_path)
    person, _ = store.finish_sign_in(store.start_sign_in("r@example.com"))  # type: ignore[misc]
    home = library.home(person)
    assert library.talks(home, person.id), "this reader would otherwise be written Hebrew at"

    client = Script(
        [reply([{"type": "text", "text": "Plural past: the Amorites are the subject."}])]
    )
    chats = session_module.Chats(library, store, client_factory=lambda: client)
    about = {
        "document": "שופטים",
        "section": "1",
        "sentence": "וַיִּלְחֲצוּ הָאֱמֹרִי אֶת־בְּנֵי־דָן הָהָרָה",
        "surface": "וַיִּלְחֲצוּ",
        "lemma": "לחץ",
    }
    asked = chats.say(person, home, "", "why לחצו and not לחץ?", admin=False, about=about)
    assert store.chat_owned(person.id, asked.chat_id)["mode"] == "find"
    turns = store.chat_turns(asked.chat_id)
    assert turns[0]["said"] == "why לחצו and not לחץ?", "the page shows what was asked"
    assert "The reader is reading the text שופטים, section 1." in turns[0]["content"]
    assert "They tapped the word וַיִּלְחֲצוּ (dictionary form לחץ)." in turns[0]["content"]
    assert about["sentence"] in turns[0]["content"]
    chats.answer(asked)
    assert hebrew.CONTRACT.splitlines()[0] not in client.requests[0]["system"][0]["text"]
    assert "the word they tapped" in client.requests[0]["system"][0]["text"]


def test_the_hours_refuse_a_turn_and_name_conversation(tmp_path: Path) -> None:
    library, store = world(tmp_path)
    library.upload_seconds = 30.0
    client = Script([reply([{"type": "text", "text": "a"}])])
    chats = session_module.Chats(library, store, client_factory=lambda: client)
    long_line = " ".join(["מילה"] * 200)  # 280 words with the assumed reply: 140 seconds
    asked = chats.say(None, library.home(None), "", long_line, admin=False)
    chats.answer(asked)
    feed = chats.feed_for(asked.chat_id, asked.n)
    assert feed is not None
    said = [json.loads(data) for kind, data in feed.events if kind == "error"][0]["message"]
    assert "hours of audio and conversation" in said and "library is always free" in said
    assert "$" not in said
    assert store.hours_used(None, 0) == 0.0, "a refused turn spends no seconds"


def test_a_stored_reply_is_replayed_without_what_the_api_refuses(tmp_path: Path) -> None:
    """The SDK's blocks carry `parsed_output` and `citations: None`; replayed, the API
    answers 400 — on the second turn of every conversation, which is how it was found."""
    library, store = world(tmp_path)

    class Dumped:
        content = []

        def model_dump(self) -> dict[str, Any]:
            return {
                "content": [
                    {"type": "thinking", "thinking": "", "signature": "sig"},
                    {"type": "text", "text": "hi", "citations": None, "parsed_output": None},
                ]
            }

        stop_reason = "end_turn"
        usage = SimpleNamespace(input_tokens=1, output_tokens=1)

    kept: list[list[dict[str, Any]]] = []
    session_module.run_turn(
        Script([Dumped()]),
        context(library, store),
        [{"role": "user", "content": "x"}],
        session_module.Feed(),
        lambda role, content, said: kept.append(content),
    )
    assert kept[0] == [
        {"type": "thinking", "thinking": "", "signature": "sig"},
        {"type": "text", "text": "hi"},
    ]
    old = [{"type": "text", "text": "hi", "citations": None, "parsed_output": None}]
    assert session_module.replayable(old) == [{"type": "text", "text": "hi"}]


def test_a_hebrew_reply_is_read_as_a_text_and_its_words_reach_the_page(tmp_path: Path) -> None:
    """The record forming (2026-09-06): after a reply in Hebrew, its lines are read the
    way a text is read, the words are kept on the reader's turn and put on the feed as
    their own event before "done", the share outside the model's list is measured, and
    what the reader saved lately rides in the ledger block."""
    from test_chat_record import Bands, Spaces

    from targum.chat import record

    library, store = world(tmp_path)
    person, _ = store.finish_sign_in(store.start_sign_in("r@example.com"))  # type: ignore[misc]
    now = int(time.time() * 1000)
    store.push(
        person,
        {
            "words": [
                {
                    "language": "he",
                    "lemma": "חם",
                    "status": 9,
                    "band": "easy",
                    "at": now,
                    "seen": now,
                },
                {
                    "language": "he",
                    "lemma": "מצפה",
                    "status": 1,
                    "band": "hard",
                    "at": now,
                    "seen": now,
                },
            ]
        },
    )
    reply_text = "> נָסַעְתִּי לַנֶּגֶב.\n= I went to the Negev.\nהָיָה חַם?\n= Was it hot?"
    client = Script([reply([{"type": "text", "text": reply_text}])])
    recorder = record.Recorder(
        lemmatizer=Spaces(), glosses=lambda lemma, s, t: {"חם": "hot"}.get(lemma, ""), bands=Bands()
    )
    chats = session_module.Chats(library, store, client_factory=lambda: client, recorder=recorder)
    home = library.home(person)
    asked = chats.say(person, home, "", "I went to the Negev", admin=False)
    chats.answer(asked)

    feed = chats.feed_for(asked.chat_id, asked.n)
    assert feed is not None
    kinds = [kind for kind, _ in feed.events]
    assert "words" in kinds and kinds.index("words") < kinds.index("done"), (
        "the words land before the page is told the turn is done"
    )
    payload = json.loads(next(data for kind, data in feed.events if kind == "words"))
    assert [line["he"] for line in payload["lines"]] == ["נָסַעְתִּי לַנֶּגֶב.", "הָיָה חַם?"]
    hot = next(w for w in payload["lines"][1]["words"] if w["lemma"] == "חם")
    assert hot["surface"] == "חַם" and hot["meaning"] == "hot"
    assert 0.0 <= payload["outside"] <= 1.0
    done = json.loads(next(data for kind, data in feed.events if kind == "done"))
    assert done["seconds"] > 0, "the clock at the foot"

    kept = next(turn for turn in store.chat_turns(asked.chat_id) if turn["n"] == asked.n)
    assert kept["words"] == payload, "kept on the reader's turn, for the page that comes back"
    assert "saved lately" in client.requests[0]["system"][1]["text"]
    assert "מצפה" in client.requests[0]["system"][1]["text"]


def test_on_a_machine_somebody_runs_themselves_the_chat_rail_is_off(tmp_path: Path) -> None:
    """The dollar-a-day chat rail is a hosted account's. Locally the reader is the
    operator, whose `--budget` is the ceiling; `serve.start` passes no chat rail there
    (2026-09-06), and a `Library` told none lets a day of turns through."""
    from targum.serve import Job, Library

    store = Store(tmp_path / "words.db")
    out = tmp_path / "out"
    out.mkdir()
    library = Library(out, store=store, chat_budget=None)
    for n in range(40):
        job = Job(id=f"chat-c-{n}", source="chat:c", title="", estimate=0.05, kind="chat")
        assert library.claim_turn(job) == "", n
        library.settle(job)
    source = (Path(__file__).resolve().parents[1] / "src/targum/serve.py").read_text(
        encoding="utf-8"
    )
    assert "chat_budget=CHAT_BUDGET if require_account else None" in source
