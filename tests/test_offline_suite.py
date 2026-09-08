"""The suite's own offline rule, tested — because the thing it guards rotted silently.

`conftest.offline` used to promise the suite stayed offline and only skip the two tests
carrying the `network` marker. When the fetch door stopped being httpx's, three tests in
`test_ssrf.py` went on patching `httpx.Client.stream`, intercepted nothing, and made real
requests to example.com: the checks between a reader's pasted link and a hosted box's
metadata endpoint had stopped running and the suite was green (targum-internal#229).

A guard nobody tests is the same shape as the tests it replaced, so it is tested here.
"""

from __future__ import annotations

import socket

import pytest


def test_a_connection_to_somebody_elses_machine_is_refused() -> None:
    """Not a network error — a sentence saying what the test did, so the next person
    does not read it as flakiness and retry."""
    with pytest.raises(AssertionError, match="The suite runs offline"):
        socket.create_connection(("93.184.216.34", 80), timeout=1)


def test_a_knock_on_the_real_fetch_door_is_refused() -> None:
    """The door does its connecting inside libcurl, where a socket patch cannot see it,
    so it is stopped at its own seam."""
    from targum.ingest import url as url_door

    with pytest.raises(AssertionError, match="real fetch door"):
        url_door._session().get("https://example.com/")


def test_the_door_may_still_be_built() -> None:
    """`ingest.url._open` makes its client before it checks the address. Refusing the
    build would fail every test of an address that is turned away before anything
    leaves — which is most of `test_ssrf.py`."""
    from targum.ingest import url as url_door

    assert url_door._session() is not None
    assert url_door._session(proxy="http://egress.example:8080") is not None


def test_loopback_is_left_alone() -> None:
    """The suite starts real HTTP servers and talks to them; that is the point of
    several files, and a guard that broke it would be worse than none."""
    with socket.socket() as listening:
        listening.bind(("127.0.0.1", 0))
        listening.listen(1)
        with socket.create_connection(listening.getsockname(), timeout=2) as reached:
            assert reached.getpeername()[0] == "127.0.0.1"


@pytest.mark.network
def test_a_marked_test_is_skipped_unless_asked_for() -> None:
    """This body runs only under TARGUM_NETWORK_TESTS; the marker's whole job is that it
    usually does not."""
    import os

    assert os.environ.get("TARGUM_NETWORK_TESTS")
