"""A stop finishes what is running before it stops serving (known issues 1.9).

Every deploy restarts the service, and a restart used to fail whatever was building or
answering. These pin the drain: idle stops at once, busy waits until the work is done or
the limit passes, the server answers meanwhile, and a second signal stops at once.
"""

from __future__ import annotations

import queue
import re
import signal
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from targum import serve

UNIT = Path(__file__).resolve().parent.parent / "deploy" / "targum.service"


class Clock:
    def __init__(self) -> None:
        self.at = 0.0

    def __call__(self) -> float:
        return self.at

    def sleep(self, seconds: float) -> None:
        self.at += seconds


def busy_queue(n: int = 1) -> queue.Queue[Any]:
    waiting: queue.Queue[Any] = queue.Queue()
    for item in range(n):
        waiting.put(item)
    return waiting


def test_an_idle_box_stops_at_once() -> None:
    clock = Clock()
    assert serve.drain([queue.Queue(), queue.Queue()], 600, clock=clock, sleep=clock.sleep)
    assert clock.at == 0


def test_a_busy_box_waits_until_the_work_is_done() -> None:
    clock = Clock()
    builds = busy_queue()
    builds.get()

    def sleep(seconds: float) -> None:
        clock.sleep(seconds)
        if clock.at >= 5:
            builds.task_done()

    assert serve.drain([builds, queue.Queue()], 600, clock=clock, sleep=sleep)
    assert clock.at == 5


def test_a_wait_is_bounded() -> None:
    clock = Clock()
    assert not serve.drain([busy_queue(2)], 30, clock=clock, sleep=clock.sleep)
    assert clock.at == 30


def test_a_queued_job_counts_as_well_as_a_running_one() -> None:
    running = busy_queue()
    running.get()
    assert serve.unfinished(running, busy_queue(2)) == 3


class Hello(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args: object) -> None:
        pass


def serving() -> tuple[ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Hello)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05})
    thread.start()
    return server, thread


def answers(server: ThreadingHTTPServer) -> bool:
    port = server.server_address[1]
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5) as response:
        return bool(response.status == 200)


def test_the_server_answers_while_it_drains_and_stops_after() -> None:
    server, thread = serving()
    try:
        builds = busy_queue()
        builds.get()
        stopping = serve.Stopping(server, [builds], limit=60)
        stopping(signal.SIGTERM)
        thread.join(0.3)
        assert thread.is_alive(), "stopped with a build still running"
        assert answers(server)
        builds.task_done()
        thread.join(5)
        assert not thread.is_alive()
    finally:
        server.shutdown()
        server.server_close()


def test_a_second_signal_stops_at_once() -> None:
    server, thread = serving()
    try:
        stopping = serve.Stopping(server, [busy_queue()], limit=60)
        stopping(signal.SIGINT)
        thread.join(0.3)
        assert thread.is_alive()
        stopping(signal.SIGINT)
        thread.join(5)
        assert not thread.is_alive()
    finally:
        server.server_close()


def test_systemd_waits_longer_than_the_drain() -> None:
    said = re.search(r"^TimeoutStopSec=(\d+)$", UNIT.read_text(), re.MULTILINE)
    assert said is not None
    assert int(said.group(1)) > serve.DRAIN_SECONDS


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_a_build_that_raises_still_lets_a_stop_through(tmp_path: Path) -> None:
    library = serve.Library(tmp_path)
    job = serve.Job(id="j", source="x")
    library.jobs = {"j": job}

    def boom(job: serve.Job) -> None:
        raise RuntimeError("broke")

    library.run = boom  # type: ignore[method-assign]
    library.queue.put("j")
    worker = threading.Thread(target=library._drain, daemon=True)
    worker.start()
    worker.join(5)
    assert serve.unfinished(library.queue) == 0
