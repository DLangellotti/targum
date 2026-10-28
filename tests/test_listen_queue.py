"""The server's listen queue holds a page's worth of connections (targum-internal#495).

/library asks for a couple of hundred thumbnails within a second, and Caddy opens a
connection to us for each. With `socketserver`'s backlog of five, the connection a
`/sync` happened to ride was dropped in the handshake and reset a second later, and the
reader's browser saw a 502.
"""

from __future__ import annotations

import inspect
import socket
from http.server import BaseHTTPRequestHandler

from targum import serve

#: The Library's thumbnails at once: 206 requests started in the second around the
#: 2026-10-20 reset, 121 around 2026-10-24.
SHELF = 206
#: How many the test opens without accepting: twenty times the old backlog, and under
#: macOS's own cap of 128 (`kern.ipc.somaxconn`), so the test means the same on a laptop
#: as on CI.
AT_ONCE = 100


def test_the_queue_is_longer_than_a_shelf_of_thumbnails() -> None:
    assert serve.Server.request_queue_size >= 2 * SHELF


def test_a_burst_is_queued_while_the_accept_loop_is_busy() -> None:
    """Nobody accepts here, which is the accept loop at its busiest: every connection has
    to wait in the queue, and each must still complete its handshake."""
    server = serve.Server(("127.0.0.1", 0), BaseHTTPRequestHandler)
    clients: list[socket.socket] = []
    try:
        for _ in range(AT_ONCE):
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(2.0)
            client.connect(server.server_address)
            clients.append(client)
        assert len(clients) == AT_ONCE
    finally:
        for client in clients:
            client.close()
        server.server_close()


def test_the_running_server_is_this_one() -> None:
    assert 'Server(("127.0.0.1", port), handler)' in inspect.getsource(serve.start)
