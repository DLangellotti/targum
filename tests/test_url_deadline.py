"""The fetch door's deadline: a host that trickles bytes cannot hold a build.

`TIMEOUT` is a speed floor on a streamed response, not a cap, so a host sending a byte
every so often passes it for as long as it likes (targum-internal#511). These tests knock
on the real client, against a server on loopback that answers slowly on purpose, with the
deadline lowered so the suite does not wait a minute and a half to see it work.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from targum.errors import Unreachable
from targum.ingest import url as door

#: How long the slow server waits between the things it sends.
DRIP_S = 0.4
#: The deadline the tests give the door: a few drips, so a trickle overruns it fast.
DEADLINE_S = 1.2


class Slow(BaseHTTPRequestHandler):
    """`/drip` sends a long body a byte at a time; `/hop/<n>` redirects, slowly, n times;
    `/fast` answers at once."""

    protocol_version = "HTTP/1.1"
    stop: threading.Event

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the base's name
        pass

    def do_GET(self) -> None:  # noqa: N802 - the base's name
        if self.path == "/fast":
            body = b"<p>quick</p>"
            self.send_response(200)
            self.send_header("content-type", "text/html")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/hop/"):
            left = int(self.path.rsplit("/", 1)[1])
            self.stop.wait(DRIP_S)
            self.send_response(302)
            self.send_header("location", f"/hop/{left - 1}" if left > 1 else "/fast")
            self.send_header("content-length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("content-type", "text/html")
        self.send_header("content-length", "1000")
        self.end_headers()
        try:
            for _ in range(1000):
                if self.stop.wait(DRIP_S):
                    return
                self.wfile.write(b"x")
                self.wfile.flush()
        except OSError:
            return  # the door hung up, which is the point


@pytest.fixture
def slow(monkeypatch: Any) -> Iterator[str]:
    """A slow server on loopback, the real client, and a short deadline."""
    from curl_cffi import requests

    stop = threading.Event()
    handler = type("Handler", (Slow,), {"stop": stop})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(door, "POLITE_S", 0.0)
    monkeypatch.setattr(door, "_reachable", lambda url: None)  # loopback is refused
    monkeypatch.setattr(door, "_session", lambda proxy="": requests.Session())
    monkeypatch.setattr(door, "DEADLINE_S", DEADLINE_S)
    monkeypatch.setattr(door, "DOWNLOAD_DEADLINE_S", DEADLINE_S)
    monkeypatch.delenv(door.FETCH_PROXY_ENV, raising=False)
    monkeypatch.delenv("TARGUM_YTDLP_PROXY", raising=False)
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        stop.set()
        server.shutdown()
        server.server_close()


def _overran(error: Unreachable, began: float) -> None:
    took = time.monotonic() - began
    assert error.status is None, "no status, so it reads as a shut door"
    assert error.key == "fetch.would-not-open"
    assert error.hint == "It was taking too long"
    assert DEADLINE_S <= took < DEADLINE_S + 3 * DRIP_S, f"held for {took:.1f} s"


def test_a_trickled_page_is_given_up_at_the_deadline(slow: str) -> None:
    began = time.monotonic()
    with pytest.raises(Unreachable) as caught:
        door.fetch(f"{slow}/drip")
    _overran(caught.value, began)
    assert door.shut(caught.value)


def test_a_trickled_opening_is_given_up_at_the_deadline(slow: str) -> None:
    began = time.monotonic()
    with pytest.raises(Unreachable) as caught:
        door.opening(f"{slow}/drip", most=1000)
    _overran(caught.value, began)


def test_a_trickled_download_is_given_up_and_leaves_nothing(slow: str, tmp_path: Path) -> None:
    into = tmp_path / "episode.mp3"
    began = time.monotonic()
    with pytest.raises(Unreachable) as caught:
        door.download(f"{slow}/drip", into)
    _overran(caught.value, began)
    assert not into.exists(), "half a file is not left behind"


def test_the_deadline_covers_the_redirects_too(slow: str) -> None:
    """Five slow hops are within `MAX_REDIRECTS` and each is quick enough for `TIMEOUT`;
    together they are past the deadline, and the door says so before the last."""
    began = time.monotonic()
    with pytest.raises(Unreachable) as caught:
        door.fetch(f"{slow}/hop/{door.MAX_REDIRECTS}")
    _overran(caught.value, began)


def test_a_quick_page_is_untouched_by_the_deadline(slow: str) -> None:
    got = door.fetch(f"{slow}/hop/1")
    assert got.text == "<p>quick</p>" and got.via == "direct"
