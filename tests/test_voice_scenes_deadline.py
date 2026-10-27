"""`voice_scenes.say` against a fake model on 127.0.0.1: a request that trickles bytes
forever is cut off by wall clock, reported, retried a bounded number of times, and a
stall that clears is answered. A socket timeout alone never trips on a trickle, which is
how the Hebrew B1 re-voicing hung on 2026-10-26."""

from __future__ import annotations

import base64
import importlib.util
import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "voice_scenes.py"
PCM = b"\x01\x00" * 480


def load_script() -> Any:
    spec = importlib.util.spec_from_file_location("voice_scenes", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Model:
    """What the fake answers: `stalls` trickled answers first, then a real one."""

    def __init__(self) -> None:
        self.stalls = 0
        self.asked = 0
        self.refuse: tuple[int, bytes] | None = None


@pytest.fixture
def model() -> Iterator[tuple[Model, str]]:
    state = Model()
    done = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def do_POST(self) -> None:  # noqa: N802 - the http.server name
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            state.asked += 1
            if state.refuse is not None:
                code, body = state.refuse
                state.refuse = None
                self.send_response(code)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if state.stalls > 0:
                state.stalls -= 1
                # Headers, then a byte at a time: each read succeeds well inside any
                # socket timeout, and the answer never finishes.
                self.send_response(200)
                self.send_header("Content-Length", "100000")
                self.end_headers()
                try:
                    while not done.is_set():
                        self.wfile.write(b" ")
                        self.wfile.flush()
                        time.sleep(0.05)
                except OSError:
                    pass
                return
            data = base64.b64encode(PCM).decode()
            body = json.dumps(
                {"candidates": [{"content": {"parts": [{"inlineData": {"data": data}}]}}]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield state, f"http://127.0.0.1:{server.server_address[1]}/{{model}}"
    finally:
        done.set()
        server.shutdown()
        server.server_close()


def door(script: Any, url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(script.DOORS, "vertex", (url, "TARGUM_VERTEX_TTS_KEY"))
    monkeypatch.setattr(script, "CUTOFF_WAIT", 0)
    monkeypatch.setattr(script, "WAIT", 0)


def test_a_trickle_is_cut_off_by_wall_clock_and_retried_a_bounded_number_of_times(
    model: tuple[Model, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    state, url = model
    script = load_script()
    door(script, url, monkeypatch)
    state.stalls = 99
    cut: list[Any] = []
    began = time.monotonic()
    with pytest.raises(script.CutOff) as raised:
        script.say("שלום", "Kore", "k", "Read.", "vertex", deadline=0.5, on_cutoff=cut.append)
    took = time.monotonic() - began
    assert len(cut) == script.CUTOFFS == state.asked
    assert all(c.received > 0 for c in cut), "the trickle did arrive; the deadline cut it"
    assert raised.value is cut[-1]
    assert isinstance(raised.value, TimeoutError)
    assert took < script.CUTOFFS * 0.5 + 3


def test_a_stall_that_clears_is_answered_and_the_cut_off_is_still_reported(
    model: tuple[Model, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    state, url = model
    script = load_script()
    door(script, url, monkeypatch)
    state.stalls = 1
    cut: list[Any] = []
    pcm = script.say("שלום", "Kore", "k", "Read.", "vertex", deadline=0.5, on_cutoff=cut.append)
    assert pcm == PCM
    assert len(cut) == 1 and state.asked == 2


def test_an_answer_inside_the_deadline_is_unchanged(
    model: tuple[Model, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, url = model
    script = load_script()
    door(script, url, monkeypatch)
    assert script.say("שלום", "Kore", "k", "Read.", "vertex", deadline=5) == PCM


def test_a_refusal_still_says_what_the_model_disliked(
    model: tuple[Model, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    state, url = model
    script = load_script()
    door(script, url, monkeypatch)
    state.refuse = (403, json.dumps({"error": {"message": "no such voice"}}).encode())
    with pytest.raises(RuntimeError, match="HTTP 403 on this turn: no such voice"):
        script.say("שלום", "Kore", "k", "Read.", "vertex", deadline=5)


def test_a_429_is_backed_off_and_then_answered(
    model: tuple[Model, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    state, url = model
    script = load_script()
    door(script, url, monkeypatch)
    state.refuse = (429, json.dumps({"error": {"message": "slow down"}}).encode())
    assert script.say("שלום", "Kore", "k", "Read.", "vertex", deadline=5) == PCM
    assert state.asked == 2
