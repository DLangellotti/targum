"""What has to be true before this runs on a box that is not a laptop.

Everything here failed, or would have, against the loopback-only server: these are the
things that only break once there is a domain in front of it.
"""

from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest

from targum import serve
from targum.accounts import Store

PUBLIC = "https://targum.page"


@pytest.fixture(scope="module")
def hosted(tmp_path_factory: pytest.TempPathFactory) -> tuple[int, str]:
    """A server started the way the deployment starts it, with somebody signed in."""
    tmp = tmp_path_factory.mktemp("hosted")
    store_path = tmp / "targum.db"
    store = Store(store_path)
    token = store.start_sign_in("reader@example.com")
    signed_in = store.finish_sign_in(token)
    assert signed_in is not None
    port = 8491

    threading.Thread(
        target=lambda: serve.start(
            out=tmp / "out",
            port=port,
            open_browser=False,
            store=store_path,
            require_account=True,
            public_address=PUBLIC,
        ),
        daemon=True,
    ).start()
    for _ in range(60):
        try:
            HTTPConnection("127.0.0.1", port, timeout=1).request("GET", "/health")
            break
        except OSError:
            time.sleep(0.1)
    return port, signed_in[1]


def ask(port: int, path: str, host: str, session: str = "") -> tuple[int, bytes]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("GET", path, skip_host=True)
    conn.putheader("Host", host)
    if session:
        conn.putheader("Cookie", f"targum_session={session}")
    conn.endheaders()
    response = conn.getresponse()
    body = response.read()
    conn.close()
    return response.status, body


# -- the allowlist ----------------------------------------------------------


def test_the_allowlist_follows_the_public_address() -> None:
    assert serve.hosts_for("") == frozenset(serve.SAFE_HOSTS)
    for address in (PUBLIC, "https://www.targum.page"):
        allowed = serve.hosts_for(address)
        assert "targum.page" in allowed
        # A registrar's www redirect is not always in place on the first day.
        assert "www.targum.page" in allowed
        assert "127.0.0.1" in allowed, "the proxy and the laptop both still connect over loopback"


def test_the_allowlist_admits_nothing_else() -> None:
    allowed = serve.hosts_for(PUBLIC)
    for other in ("evil.com", "targum.page.evil.com", "targumpage", ""):
        assert other not in allowed


def test_www_is_not_prefixed_onto_an_address() -> None:
    """`www.127.0.0.1` is not a thing anybody can reach, so it should not be admitted."""
    assert serve.hosts_for("http://127.0.0.1:8420") == frozenset(serve.SAFE_HOSTS)


@pytest.mark.parametrize("path", ["/", "/library", "/words"])
def test_a_signed_in_reader_is_served_at_the_public_domain(
    hosted: tuple[int, str], path: str
) -> None:
    """The one that was broken.

    A reader who has signed in correctly, arriving at the domain they were sent, got 403
    on every page — and the body told them to open a Terminal, which a hosted reader does
    not have. Loopback worked, so nothing local ever showed it.
    """
    port, session = hosted
    status, body = ask(port, path, "targum.page", session)
    assert status == 200, f"{path} refused a signed-in reader at the public domain"
    assert b"earlier session" not in body


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_loopback_still_works(hosted: tuple[int, str], host: str) -> None:
    port, session = hosted
    assert ask(port, "/library", host, session)[0] == 200


def test_a_stranger_host_is_still_refused(hosted: tuple[int, str]) -> None:
    """The property the allowlist exists for, kept while widening it."""
    port, session = hosted
    status, _ = ask(port, "/library", "evil.example.com", session)
    assert status == 403


# -- health -----------------------------------------------------------------


def test_health_needs_no_key_and_no_account(hosted: tuple[int, str]) -> None:
    """A monitor has neither, and asks from off the box."""
    port, _ = hosted
    status, body = ask(port, "/health", "targum.page")
    assert status == 200
    assert json.loads(body)["ok"] is True


def test_health_reports_the_store_rather_than_only_the_process() -> None:
    """A process running against a database it cannot read is the failure worth catching.

    An endpoint that only proves a socket is open would call that healthy.
    """
    assert "self.store.anyone()" in Path("src/targum/serve.py").read_text()
