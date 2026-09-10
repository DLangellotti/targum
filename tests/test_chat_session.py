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
    assert sent["system"][1]["cache_control"] == {"type": "ephemeral"}, (
        "the ledger after its own breakpoint, since it holds still for a conversation (#239)"
    )
    assert sent["messages"][-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}, (
        "and the last message, so the next turn reads the history back from the cache"
    )
    # The whole registry: this turn was answered on a box with no web_search.
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
    assert searching[-1]["type"] == "web_search_20260209"
    assert "allowed_domains" not in searching[-1], "the whole web, since 2026-09-08"
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
    assert "met once, not yet known (1): מצפה" in client.requests[0]["system"][1]["text"]


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


def test_sentences_a_hebrew_speaker_wrote_ride_with_the_ledger_only_in_hebrew(
    tmp_path: Path,
) -> None:
    """targum-internal#218: with a pool on the box, a Hebrew turn carries a few Tatoeba
    sentences inside the reader's words after the breakpoint; a conversation opened in
    English about a text carries none; a box with no pool carries none."""
    from targum.chat import exemplars

    pool = exemplars.load(Path(__file__).parent / "fixtures" / "exemplars.jsonl")
    library, store = world(tmp_path)
    person, _ = store.finish_sign_in(store.start_sign_in("r@example.com"))  # type: ignore[misc]
    now = int(time.time() * 1000)
    store.push(
        person,
        {
            "words": [
                {"language": "he", "lemma": w, "status": 9, "band": "easy", "at": now, "seen": now}
                for w in ("בוקר", "טוב", "מה", "את", "עושה")
            ]
        },
    )
    reply_text = "> בּוֹקֶר טוֹב.\n= Good morning.\nמָה שְׁלוֹמְךָ?\n= How are you?"
    client = Script([reply([{"type": "text", "text": reply_text}])] * 3)
    chats = session_module.Chats(library, store, client_factory=lambda: client, exemplars=pool)
    home = library.home(person)
    asked = chats.say(person, home, "", "Good morning", admin=False)
    chats.answer(asked)
    block = client.requests[0]["system"][1]["text"]
    assert "Sentences a Hebrew speaker wrote" in block and "בוקר טוב. = Good morning." in block
    assert client.requests[0]["system"][1]["cache_control"] == {"type": "ephemeral"}, (
        "after the stable half's breakpoint, under its own"
    )
    assert "הסערה" not in block, "a sentence outside the reader's words is not picked"

    found = chats.say(
        person,
        home,
        "",
        "What is this word?",
        admin=False,
        about={"document": "genesis", "section": "1", "surface": "בָּרָא", "lemma": "ברא"},
    )
    chats.answer(found)
    assert "Sentences a Hebrew speaker wrote" not in client.requests[1]["system"][1]["text"]

    bare = session_module.Chats(library, store, client_factory=lambda: client, exemplars=[])
    again = bare.say(person, home, "", "Good morning", admin=False)
    bare.answer(again)
    assert "Sentences a Hebrew speaker wrote" not in client.requests[2]["system"][1]["text"]


def test_a_brought_text_is_framed_as_a_fact_the_model_can_use() -> None:
    """The reader gave the model a text; the note says what it is and that it is on its
    way, so the model never asks for it (2026-09-07)."""
    framed = session_module.framed(
        "help me learn it",
        None,
        {"title": "מכתב", "pages": 1, "segments": 4, "excerpt": ["א", "ב"], "stage": "working"},
    )
    assert framed.startswith("The reader has just sent a text through the box")
    assert "It is called: מכתב (1 pages, 4 sentences)" in framed
    assert "Its first lines, as read: א / ב" in framed
    assert "being built now" in framed
    assert framed.endswith("Their line:\nhelp me learn it")
    waiting = session_module.framed("?", None, {"title": "t", "stage": "ready"})
    assert "waiting on their press" in waiting
    refused = session_module.framed(
        "?", None, {"title": "t", "stage": "blocked", "blocked": "Too long."}
    )
    assert "could not be built: Too long." in refused

    # And what was sent is named as what it was: a screenshot is a picture, read.
    shot = session_module.framed(
        "help me understand this",
        None,
        {"title": "הודעה", "from": "pictures", "pages": 1, "doubtful": 2, "stage": "working"},
    )
    assert "sent a picture (a screenshot or a photograph), read into words" in shot
    assert "2 lines could not be read clearly" in shot
    assert "(1 pages" not in shot, "a picture is not counted in pages"
    chat = session_module.framed(
        "?", None, {"title": "t", "from": "pictures", "pages": 3, "conversation": True}
    )
    assert "a screenshot of a messaging conversation, read into its messages" in chat
    assert "sent 3 pictures" in session_module.framed(
        "?", None, {"title": "t", "from": "pictures", "pages": 3}
    )
    assert "sent a recording" in session_module.framed(
        "?", None, {"title": "t", "from": "recording"}
    )


def test_a_card_s_meaning_is_in_the_note_so_the_model_can_dispute_it() -> None:
    """A reader wrote "the definition here is change, not teachings" under a card and
    the model parsed the verb correctly without knowing what the card said
    (2026-09-08). The note now carries the card's line, and says the model cannot
    change it."""
    framed = session_module.framed(
        "I think the definition here is change, not teachings",
        {
            "document": "youtube-he",
            "sentence": "המתחרות משנות את הדרך",
            "surface": "משנות",
            "lemma": "משנה",
            "meaning": "doctrine; teachings",
        },
    )
    assert "The card shows the meaning: doctrine; teachings." in framed
    assert "you cannot change the card" in framed
    assert framed.endswith("Their question:\nI think the definition here is change, not teachings")
    bare = session_module.framed("?", {"surface": "משנות", "sentence": "s"})
    assert "The card shows" not in bare


def test_a_byte_the_model_could_not_write_never_reaches_the_reader(tmp_path: Path) -> None:
    """A byte-level tokenizer emits a byte that is not a character and the API hands it
    back as U+FFFD. It happened in pointed Hebrew on 2026-09-07 — מָסָךְ שֶ�ל, the shin
    dot gone and a black diamond in its place, which the annotator then lemmatised as
    `[unk]` and put on the reader's ledger. Dropped on the way in, in the stream and in
    what is kept, so nothing downstream ever sees one."""
    library, store = world(tmp_path)
    broken = "מָסָךְ שֶ�ל וָואטְסְאַפּ."
    client = Script([reply([{"type": "text", "text": broken}])])
    feed = session_module.Feed()
    kept: list[tuple[str, list[dict[str, Any]], str]] = []
    session_module.run_turn(
        client,
        context(library, store),
        [{"role": "user", "content": "מה זה"}],
        feed,
        lambda role, content, said: kept.append((role, content, said)),
    )
    assert "�" not in feed.text(), "the live stream shows no diamond"
    assert kept[0][2] == "מָסָךְ שֶל וָואטְסְאַפּ.", "the point is not guessed back, only the byte goes"
    assert "�" not in kept[0][1][0]["text"], "nor does what is replayed to the API"


def test_a_thinking_block_is_never_touched_on_the_way_through(tmp_path: Path) -> None:
    """Its signature is over what the model wrote; a block changed by us is a 400."""
    library, store = world(tmp_path)
    signed = {"type": "thinking", "thinking": "a�b", "signature": "sig"}
    client = Script([reply([signed, {"type": "text", "text": "ok"}])])
    kept: list[list[dict[str, Any]]] = []
    session_module.run_turn(
        client,
        context(library, store),
        [{"role": "user", "content": "hi"}],
        session_module.Feed(),
        lambda role, content, said: kept.append(content),
    )
    assert kept[0][0]["thinking"] == "a�b"


def test_the_model_is_told_which_doors_are_shut(tmp_path: Path) -> None:
    """After the breakpoint with the ledger, because it changes as the box knocks and a
    changing block before the breakpoint throws the cached prefix away each time."""
    library, store = world(tmp_path)
    store.reach("hebrew-academy.org.il", False, "403")
    store.reach("nli.org.il", False, "403")
    store.reach("he.wikipedia.org", True)
    chats = session_module.Chats(
        library, store, client_factory=lambda: Script([reply([{"type": "text", "text": "ok"}])])
    )
    chats.answer(chats.say(None, library.home(None), "", "מה לקרוא", admin=False))
    (client,) = [chats._client]
    ledger = client.requests[0]["system"][1]["text"]
    assert "hebrew-academy.org.il" in ledger and "nli.org.il" in ledger
    assert "he.wikipedia.org" not in ledger, "a host that answers is not on the list"
    assert client.requests[0]["system"][1]["cache_control"] == {"type": "ephemeral"}


def test_no_shut_doors_means_no_block_at_all(tmp_path: Path) -> None:
    library, store = world(tmp_path)
    chats = session_module.Chats(
        library, store, client_factory=lambda: Script([reply([{"type": "text", "text": "ok"}])])
    )
    chats.answer(chats.say(None, library.home(None), "", "מה לקרוא", admin=False))
    assert "did not answer targum" not in chats._client.requests[0]["system"][1]["text"]


# --- a turn that fails where `answer` is not watching ---------------------------------


def test_a_conversation_in_a_language_wordfreq_cannot_band_is_still_answered() -> None:
    """Aramaic has no wordfreq list, and wordfreq raises rather than answering nothing.

    `common_words` runs before `answer`'s own guard, so this arrived in `_drain` — which
    caught nothing. The thread died, the turn stayed `working` with no error against it,
    and the reader watched three dots for ever (targum-internal#228).
    """
    from targum.chat.hebrew import common_words

    assert common_words(language="arc") == [], "a missing list is not an error"
    assert common_words(language="he"), "and Hebrew still has one"


def test_the_conversation_is_held_in_hebrew_when_the_reader_is_learning_it() -> None:
    """The pick was `sorted(...)[0]`, which is alphabetical and therefore arbitrary.

    Since the scripture path learned to read Daniel and Ezra, a reader who opens either is
    learning `arc` as well as `he` — and `arc` sorts first, so their conversations were
    held in Aramaic. The chat's contract, record and ledger are all Hebrew.
    """
    assert session_module._conversing_in({"arc", "he"}) == "he"
    assert session_module._conversing_in({"he"}) == "he"
    assert session_module._conversing_in(set()) == "he"
    assert session_module._conversing_in({"arc"}) == "arc", "someone learning only that"


def test_a_worker_outlives_the_turn_it_lost(tmp_path: Path, monkeypatch: Any) -> None:
    """The pool is four threads. Four turns that raise outside `answer` and the chat is
    gone for everybody until the service restarts — which is what happened on the box.

    Driven through the real pool rather than around it: one worker, a turn that raises
    the way Aramaic did, and then a second turn. The second is the whole point — before
    this the thread was dead and the second turn was never picked up at all.
    """
    library, store = world(tmp_path)
    chats = session_module.Chats(library, store, client_factory=lambda: Script([]))

    lost: list[str] = []

    def explode(asked: Any) -> None:
        lost.append(asked.chat_id)
        raise LookupError("No wordlist 'best' available for language 'arc'")

    monkeypatch.setattr(chats, "answer", explode)
    chats.start_workers(1)

    first = chats.say(None, library.home(None), "", "hi", admin=False)
    chats.queue.join()

    row = next(r for r in store.chat_turns(first.chat_id) if r["n"] == first.n)
    assert row["stage"] == "failed", "the page stops waiting"
    assert row["error"] == "The conversation could not continue. Try again."
    feed = chats.feed_for(first.chat_id, first.n)
    assert feed is not None
    said = [json.loads(data) for kind, data in feed.events if kind == "error"]
    assert said and said[0]["message"] == "The conversation could not continue. Try again."
    assert "wordlist" not in json.dumps(said), "the library's own words never reach a reader"

    second = chats.say(None, library.home(None), "", "again", admin=False)
    chats.queue.join()
    assert len(lost) == 2, "the worker came back for the next turn rather than dying with the last"
    after = next(r for r in store.chat_turns(second.chat_id) if r["n"] == second.n)
    assert after["stage"] == "failed"


def test_the_ledger_block_holds_still_for_a_conversation_and_moves_for_the_next(
    tmp_path: Path,
) -> None:
    """targum-internal#239. The bring-back slice and the exemplars were drawn afresh every
    turn, which redrew the block after the breakpoint every turn — and the history comes
    after that block, so the whole conversation fell out of the cache each time. One
    conversation now sees one draw; a second conversation sees another."""
    from targum.chat import exemplars

    pool = exemplars.load(Path(__file__).parent / "fixtures" / "exemplars.jsonl")
    library, store = world(tmp_path)
    person, _ = store.finish_sign_in(store.start_sign_in("r@example.com"))  # type: ignore[misc]
    now = int(time.time() * 1000)
    store.push(
        person,
        {
            "words": [
                {"language": "he", "lemma": w, "status": 9, "band": "easy", "at": now, "seen": now}
                for w in ("בוקר", "טוב", "מה", "את", "עושה")
            ]
        },
    )
    reply_text = "> בּוֹקֶר טוֹב.\n= Good morning.\nמָה שְׁלוֹמְךָ?\n= How are you?"
    client = Script([reply([{"type": "text", "text": reply_text}])] * 4)
    chats = session_module.Chats(library, store, client_factory=lambda: client, exemplars=pool)
    home = library.home(person)
    first = chats.say(person, home, "", "Good morning", admin=False)
    chats.answer(first)
    chats.answer(chats.say(person, home, first.chat_id, "Good morning again", admin=False))
    one, two = (request["system"][1]["text"] for request in client.requests[:2])
    assert one == two, "the same block on both turns of one conversation"
    assert exemplars.conversation_seed("a") != exemplars.conversation_seed("b")
    assert exemplars.conversation_seed("a") == exemplars.conversation_seed("a")


def test_a_marked_message_is_a_copy_and_the_store_s_is_untouched() -> None:
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "x"}]},
    ]
    sent = session_module.marked(history)
    assert sent[-1]["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in history[-1]["content"][-1], "the stored history is as it was"
    assert sent[:-1] == history[:-1]
    plain = session_module.marked([{"role": "user", "content": "hello"}])
    assert plain[0]["content"] == [
        {"type": "text", "text": "hello", "cache_control": {"type": "ephemeral"}}
    ]
    assert session_module.marked([]) == []


def test_what_the_cache_did_reaches_the_receipt(tmp_path: Path) -> None:
    """Cache reads and writes were read past, so the receipt could not say whether
    caching saved anything (targum-internal#239). Now they are counted and priced."""
    library, store = world(tmp_path)
    answer = reply([{"type": "text", "text": "Try Ruth first."}])
    answer.usage = SimpleNamespace(
        input_tokens=100,
        output_tokens=20,
        cache_read_input_tokens=4000,
        cache_creation_input_tokens=300,
    )
    client = Script([answer])
    usage = session_module.run_turn(
        client,
        context(library, store),
        [{"role": "user", "content": "what should I read"}],
        session_module.Feed(),
        lambda role, content, said: None,
    )
    assert usage.cache_read_tokens == 4000 and usage.cache_write_tokens == 300
    assert usage.state()["cache_read"] == 4000 and usage.state()["cache_write"] == 300
