"""The chat's routes: a page, a line up, a stream back, and nobody else's conversation.

The server is stdlib `http.server`, so the stream is written past `_send` by hand; this
is where the shape of that is held — the headers, the event framing, that a closed feed
ends the response — and where the door is checked from the outside.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from test_chat_session import Script, reply

from targum.accounts import Store
from targum.chat import session as session_module
from targum.mail import ConsoleMailer
from targum.serve import POLICY, Handler, Library


@pytest.fixture
def chatting(tmp_path: Path) -> Iterator[tuple[int, str, Store, session_module.Chats]]:
    out = tmp_path / "out"
    out.mkdir()
    store = Store(tmp_path / "words.db")
    library = Library(out, store=store)
    script = Script(
        [reply([{"type": "text", "text": "Read Ruth at /reader/ruth-he/reader/index.html"}])]
    )
    chats = session_module.Chats(library, store, client_factory=lambda: script)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    handler = type(
        "ChatHandler",
        (Handler,),
        {
            "library": library,
            "token": "k",
            "page": "<html>start</html>",
            "chatting": "<html>chat</html>",
            "chats": chats,
            "store": store,
            "mailer": ConsoleMailer(),
            "address": f"http://127.0.0.1:{port}",
        },
    )
    server.RequestHandlerClass = handler
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield port, "k", store, chats
    finally:
        server.shutdown()
        server.server_close()


def call(
    port: int, method: str, path: str, body: dict[str, Any] | None = None
) -> tuple[int, Any, Any]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    payload = json.dumps(body).encode() if body is not None else None
    connection.request(method, path, body=payload, headers={"Content-Type": "application/json"})
    response = connection.getresponse()
    raw = response.read()
    connection.close()
    try:
        return response.status, json.loads(raw), response
    except (json.JSONDecodeError, UnicodeDecodeError):
        # A page, or a clip: not JSON, and a clip is not text either.
        return response.status, raw, response


def test_the_page_and_the_list_answer_behind_the_key(chatting) -> None:
    port, key, _, _ = chatting
    assert call(port, "GET", f"/chat?k={key}")[0] == 200
    status, answer, _ = call(port, "GET", f"/chat/list?k={key}")
    assert status == 200 and answer["chats"] == [] and answer["usable"] is True
    assert set(answer["hours"]) == {"used", "allowed", "ends"}
    assert call(port, "GET", "/chat/list")[0] == 403, "no key, no list"


def test_a_line_goes_up_and_the_answer_streams_back(chatting) -> None:
    port, key, store, chats = chatting
    status, asked, _ = call(port, "POST", f"/chat/say?k={key}", {"chat": "", "text": "what first"})
    assert status == 200 and asked["turn"] == 1 and asked["chat"]
    chats.answer(chats.queue.get())  # the worker's job, done here so the test is deterministic
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", f"/chat/stream/{asked['chat']}/1?k={key}")
    response = connection.getresponse()
    assert response.status == 200
    assert response.getheader("Content-Type") == "text/event-stream"
    assert response.getheader("X-Accel-Buffering") == "no"
    assert response.getheader("Content-Length") is None, "a stream has no length"
    body = response.read().decode("utf-8")
    connection.close()
    assert "event: text\n" in body and "event: done\n" in body
    assert "id: 0\n" in body, "events are numbered so a tab can say where it got to"
    done = [line for line in body.splitlines() if line.startswith("data: {")]
    assert json.loads(done[-1][len("data: ") :])["text"].strip().startswith("Read Ruth")

    status, state, _ = call(port, "GET", f"/chat/turn/{asked['chat']}/1?k={key}")
    assert state["done"] is True and state["text"].strip().startswith("Read Ruth")
    status, whole, _ = call(port, "GET", f"/chat/{asked['chat']}?k={key}")
    assert [t["role"] for t in whole["turns"]] == ["user", "assistant"]
    assert whole["chat"]["title"] == "what first"


def test_a_lost_feed_answers_from_the_store(chatting) -> None:
    port, key, store, chats = chatting
    _, asked, _ = call(port, "POST", f"/chat/say?k={key}", {"chat": "", "text": "hi"})
    chats.answer(chats.queue.get())
    chats.feeds.clear()  # as after a restart
    status, state, _ = call(port, "GET", f"/chat/turn/{asked['chat']}/1?k={key}")
    assert state["done"] is True and state["text"].startswith("Read Ruth")
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request("GET", f"/chat/stream/{asked['chat']}/1?k={key}")
    body = connection.getresponse().read().decode("utf-8")
    connection.close()
    assert "event: done\n" in body


def test_somebody_else_s_conversation_is_not_found(chatting) -> None:
    port, key, store, _ = chatting
    theirs = store.chat_open(42)
    store.chat_say(theirs, "user", "secret", "secret")
    assert call(port, "GET", f"/chat/{theirs}?k={key}")[0] == 404
    assert call(port, "GET", f"/chat/turn/{theirs}/1?k={key}")[0] == 404
    assert call(port, "GET", f"/chat/stream/{theirs}/1?k={key}")[0] == 404
    assert call(port, "POST", f"/chat/say?k={key}", {"chat": theirs, "text": "x"})[0] == 404


def test_an_empty_line_and_a_missing_key_are_refused(chatting) -> None:
    port, key, _, chats = chatting
    assert call(port, "POST", f"/chat/say?k={key}", {"text": "   "})[0] == 400
    chats.usable = False
    status, answer, _ = call(port, "POST", f"/chat/say?k={key}", {"text": "hi"})
    assert status == 402 and "still opens" in answer["error"]


def test_the_policy_did_not_move_for_the_chat() -> None:
    """The chat page streams from its own origin under the policy every page already
    takes. `connect-src 'self'` was already there; nothing else may be added for this."""
    assert "connect-src 'self'" in POLICY
    assert "unsafe-inline" not in POLICY and "unsafe-eval" not in POLICY
    assert POLICY.count("connect-src") == 1


def test_a_handler_without_a_chat_answers_not_found(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    handler = type(
        "PlainHandler",
        (Handler,),
        {
            "library": Library(out),
            "token": "k",
            "page": "<html></html>",
            "store": Store(tmp_path / "w.db"),
            "mailer": ConsoleMailer(),
            "address": f"http://127.0.0.1:{port}",
        },
    )
    server.RequestHandlerClass = handler
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert call(port, "GET", "/chat?k=k")[0] == 404
        assert call(port, "GET", "/chat/list?k=k")[0] == 404
        assert call(port, "POST", "/chat/say?k=k", {"text": "hi"})[0] == 404
    finally:
        server.shutdown()
        server.server_close()


def test_the_export_and_the_purge_carry_conversations(tmp_path: Path) -> None:
    store = Store(tmp_path / "w.db")
    token = store.start_sign_in("reader@example.com")
    signed = store.finish_sign_in(token)
    assert signed is not None
    person = signed[0]
    chat = store.chat_open(person.id)
    store.chat_say(chat, "user", "hello", "hello")
    store.chat_say(chat, "assistant", [{"type": "text", "text": "shalom"}], "shalom")
    store.chat_say(chat, "user", [{"type": "tool_result", "tool_use_id": "t"}], "")
    everything = store.everything(person)
    assert [t["said"] for t in everything["chats"][0]["turns"]] == ["hello", "shalom"]
    store.forget(person)
    store.purge(days=-1)
    assert store.chats(person.id) == [] and store.chat_turns(chat) == []


def test_the_list_carries_the_hours_and_every_conversation_is_in_hebrew(chatting) -> None:
    port, key, store, chats = chatting
    status, answer, _ = call(port, "GET", f"/chat/list?k={key}")
    assert answer["hours"] == {"used": 0.0, "allowed": 8.0, "ends": answer["hours"]["ends"]}
    assert answer["hours"]["ends"]
    assert answer["talk"] is True, "the page is told whether to offer Speak"
    status, shelf, _ = call(port, "GET", f"/readers?k={key}")
    assert shelf["talk"] is True, "and the front door is told the same"
    status, asked, _ = call(port, "POST", f"/chat/say?k={key}", {"chat": "", "text": "שלום"})
    assert status == 200
    status, whole, _ = call(port, "GET", f"/chat/{asked['chat']}?k={key}")
    assert whole["chat"]["mode"] == "talk", "there is one kind of conversation"
    # A line that asks for a mode is asking for something that no longer exists.
    status, _, _ = call(
        port, "POST", f"/chat/say?k={key}", {"chat": asked["chat"], "text": "x", "mode": "find"}
    )
    assert status == 200
    status, whole, _ = call(port, "GET", f"/chat/{asked['chat']}?k={key}")
    assert whole["chat"]["mode"] == "talk"


# -- push-to-talk ------------------------------------------------------------------


class Heard:
    """A transcriber that hears what the test says it should."""

    name = "test/ears"
    model = "ears"
    needs_key = False

    def __init__(self, text: str = "שלום לך") -> None:
        from targum.usage import Usage

        self.text = text
        self.spent = Usage()
        self.heard: list[Path] = []

    def available(self) -> tuple[bool, str]:
        return True, self.model

    def price_per_minute(self) -> float:
        return 0.006

    def transcribe(self, audio: Path, language: str = "", on_progress: Any = None) -> Any:
        self.heard.append(audio)
        self.spent.add_seconds(self.name, 4.0)
        return SimpleNamespace(words=[SimpleNamespace(text=w) for w in self.text.split()])


def test_a_spoken_line_is_written_down_metered_once_and_asked(chatting, monkeypatch: Any) -> None:
    from targum import transcribe
    from targum.audio import probe

    port, key, store, chats = chatting
    ears = Heard()
    monkeypatch.setattr(transcribe, "build", lambda name, **options: ears)
    monkeypatch.setattr(
        probe, "examine", lambda path, allow_video=False: SimpleNamespace(duration=4.0)
    )

    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(
        "POST",
        f"/chat/hear?chat=&k={key}",
        body=b"\x1aE\xdf\xa3 fake webm",
        headers={"Content-Type": "audio/webm"},
    )
    response = connection.getresponse()
    answer = json.loads(response.read())
    connection.close()
    assert response.status == 200 and answer["heard"] == "שלום לך" and answer["turn"] == 1
    assert ears.heard and ears.heard[0].suffix == ".webm"
    assert store.chat_owned(None, answer["chat"])["mode"] == "talk"  # type: ignore[index]
    assert store.hours_used(None, 0) == pytest.approx(4.0), "the clip's seconds, once"

    chats.answer(chats.queue.get())
    turn = chats.library.jobs[f"chat-{answer['chat']}-1"]
    from targum.chat import hebrew

    assert turn.seconds == pytest.approx(
        hebrew.seconds_for(hebrew.words_in("Read Ruth at /reader/ruth-he/reader/index.html"))
    )
    assert store.hours_used(None, 0) == pytest.approx(4.0 + turn.seconds), (
        "reply alone, on top of the clip"
    )


def test_hearing_refuses_what_cannot_be_heard(chatting, monkeypatch: Any) -> None:
    from targum import transcribe
    from targum.audio import probe
    from targum.errors import TargumError

    port, key, store, chats = chatting

    def cannot(path: Path, allow_video: bool = False) -> Any:
        raise TargumError("That is not a recording.")

    monkeypatch.setattr(probe, "examine", cannot)
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(
        "POST", f"/chat/hear?k={key}", body=b"junk", headers={"Content-Type": "audio/webm"}
    )
    response = connection.getresponse()
    assert response.status == 400 and "recording" in json.loads(response.read())["error"]
    connection.close()

    monkeypatch.setattr(
        probe, "examine", lambda path, allow_video=False: SimpleNamespace(duration=2.0)
    )
    deaf = Heard()
    deaf.available = lambda: (False, "set ELEVENLABS_API_KEY")  # type: ignore[method-assign]
    monkeypatch.setattr(transcribe, "build", lambda name, **options: deaf)
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(
        "POST", f"/chat/hear?k={key}", body=b"clip", headers={"Content-Type": "audio/webm"}
    )
    response = connection.getresponse()
    assert response.status == 402 and "ELEVENLABS_API_KEY" in json.loads(response.read())["error"]
    connection.close()
    assert store.hours_used(None, 0) == 0.0


def test_an_answer_is_read_aloud_once_and_kept(chatting, monkeypatch: Any, tmp_path: Path) -> None:
    from targum import speech

    port, key, store, chats = chatting
    _, asked, _ = call(port, "POST", f"/chat/say?k={key}", {"chat": "", "text": "hi"})
    chats.answer(chats.queue.get())
    rendered: list[str] = []

    def render(text: str, into: Path, voice: str = speech.VOICE) -> speech.Clip:
        rendered.append(text)
        into.parent.mkdir(parents=True, exist_ok=True)
        target = into.with_suffix(".wav")
        target.write_bytes(speech.wav(b"\x00" * speech.BYTES_PER_SECOND * 3))
        return speech.Clip(target, "audio/wav", 3.0)

    monkeypatch.setattr(speech, "render", render)
    monkeypatch.setenv(speech.KEY, "k")
    status, body, response = call(port, "GET", f"/chat/audio/{asked['chat']}/1?k={key}")
    assert status == 200 and response.getheader("Content-Type") == "audio/wav"
    assert rendered == ["Read Ruth at /reader/ruth-he/reader/index.html"], "the answer's text, once"
    assert store.hours_used(None, 0) == pytest.approx(
        3.0 + chats.library.jobs[f"chat-{asked['chat']}-1"].seconds
    )
    call(port, "GET", f"/chat/audio/{asked['chat']}/1?k={key}")
    assert len(rendered) == 1, "kept, not made again"

    monkeypatch.delenv(speech.KEY, raising=False)
    _, asked2, _ = call(port, "POST", f"/chat/say?k={key}", {"chat": asked["chat"], "text": "more"})
    chats.answer(chats.queue.get())
    status, body, _ = call(port, "GET", f"/chat/audio/{asked['chat']}/{asked2['turn']}?k={key}")
    assert status == 402 and "No voice" in body["error"]
    assert call(port, "GET", f"/chat/audio/{store.chat_open(42)}/1?k={key}")[0] == 404
