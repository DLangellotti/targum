"""`/open/<id>`: one door onto a catalogue text, wherever the link was written.

"When I click on any link to a targum anywhere it should open that targum immediately,
and not merely bring me to library" (2026-09-17). Five pages linked at `/library#<id>`,
which marks the row and scrolls to it. This is the route that replaced them, and the
thing worth pinning hardest is the half it must never do: a redirect is not a press, so
an unbuilt text is never built by following a link to it.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from targum.accounts import Store
from targum.serve import Handler, Library


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[int, str, Path]]:
    """A running server with an empty shelf, and the key every local address carries."""
    import io

    from targum.mail import ConsoleMailer

    out = tmp_path / "targum-out"
    out.mkdir()
    token = "test-key"
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    handler = type(
        "TestHandler",
        (Handler,),
        {
            "library": Library(out, store=Store(tmp_path / "ledger.db")),
            "token": token,
            "page": "<html>start</html>",
            "progress": "<html>your progress</html>",
            "catalogue": "<html>library</html>",
            "lists": {k: "<html></html>" for k in ("texts", "words", "phrases")},
            "store": Store(tmp_path / "words.db"),
            "mailer": ConsoleMailer(io.StringIO()),
            "address": f"http://127.0.0.1:{port}",
        },
    )
    server.RequestHandlerClass = handler
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, token, out
    finally:
        server.shutdown()
        server.server_close()


def where(port: int, path: str) -> tuple[int, str]:
    """Follow nothing: the status and the Location are the whole of the answer."""
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        response.read()
        return response.status, response.headers.get("Location", "")
    finally:
        connection.close()


def build_a_reader(out: Path, name: str, source: str, home: str = "local") -> None:
    """A reader on the shelf, as a build leaves one: an index and a document beside it.

    Under `local/`, which is the signed-out home — every home is a directory of its own
    so that none contains another (`Library.home`).
    """
    folder = out / home / name
    (folder / "reader").mkdir(parents=True)
    (folder / "reader" / "index.html").write_text("<html>read</html>", encoding="utf-8")
    (folder / "document.json").write_text(
        json.dumps({"title": name, "language": "he", "source": source, "blocks": []}),
        encoding="utf-8",
    )


def an_entry():
    """One real catalogue entry, whichever the fixture holds."""
    from targum.catalogue import CATALOGUE

    return CATALOGUE[0]


def test_a_text_you_have_built_opens_at_your_copy(served) -> None:
    """The address the library row is a link to, reached without going through the
    library to find it."""
    port, token, out = served
    entry = an_entry()
    build_a_reader(out, "mine-he", entry.source)

    status, location = where(port, f"/open/{entry.id}?k={token}")
    assert status == 302, status
    assert location.startswith("/reader/mine-he/reader/index.html"), location


def test_a_text_on_the_shared_shelf_opens_too(served) -> None:
    """A reader with nothing of their own is handed the shared shelf to start with, and
    a shared text opens like any built one — the library page merges the two into one
    list and links straight at it.

    Found on the running page: the door looked only at the reader's own home, so it sent
    somebody to the offer for a text they could already read. Every Tanakh book on a new
    account is in exactly that position.
    """
    port, token, out = served
    entry = an_entry()
    build_a_reader(out, "shared-he", entry.source, home="shared")

    status, location = where(port, f"/open/{entry.id}?k={token}")
    assert status == 302, status
    assert location.startswith("/reader/shared-he/reader/index.html"), location


def test_your_own_copy_wins_over_the_shared_one(served) -> None:
    """The precedence the library page already uses when it merges the two lists."""
    port, token, out = served
    entry = an_entry()
    build_a_reader(out, "shared-he", entry.source, home="shared")
    build_a_reader(out, "mine-he", entry.source)

    _, location = where(port, f"/open/{entry.id}?k={token}")
    assert location.startswith("/reader/mine-he/reader/index.html"), location


def test_a_text_you_have_not_built_lands_on_its_row_with_the_offer_up(served) -> None:
    """`#build:` rather than a bare id: the row puts its press under the reader's hand.

    And not one step further. What pressing an unbuilt row does is start spending, and a
    redirect nobody pressed is exactly the thing that must not be able to do that.
    """
    port, token, out = served
    entry = an_entry()

    status, location = where(port, f"/open/{entry.id}?k={token}")
    assert status == 302, status
    assert location.startswith("/library"), location
    assert location.endswith(f"#build:{entry.id}"), location
    # Nothing was built by asking.
    assert not list((out / "local").glob("*/reader/index.html"))


def test_the_key_rides_through_the_door(served) -> None:
    """Locally the key is in every address, and a redirect that dropped it would land the
    reader on a 403 instead of on their text."""
    port, token, out = served
    entry = an_entry()
    build_a_reader(out, "mine-he", entry.source)

    _, location = where(port, f"/open/{entry.id}?k={token}")
    assert f"k={token}" in location, location

    _, shelf = where(port, f"/open/nothing-by-this-name?k={token}")
    assert f"k={token}" in shelf, shelf
    # The query goes before the fragment or the browser reads the key as part of it.
    assert shelf.index("?") < (shelf.index("#") if "#" in shelf else len(shelf))


def test_an_id_nobody_has_heard_of_lands_on_the_library(served) -> None:
    """Rather than on a 404: the library is the honest answer to "I could not find it"."""
    port, token, _ = served
    status, location = where(port, f"/open/no-such-text?k={token}")
    assert status == 302, status
    assert location.startswith("/library"), location
    assert "#build:" not in location, "nothing to offer, so nothing is offered"


def test_a_text_in_the_bin_is_not_on_the_shelf(served) -> None:
    """Sending somebody into their own bin is answering a question they did not ask."""
    port, token, out = served
    entry = an_entry()
    build_a_reader(out, "mine-he", entry.source)
    from targum.serve import TRASHED

    (out / "local" / "mine-he" / TRASHED).write_text("1789600000", encoding="utf-8")

    _, location = where(port, f"/open/{entry.id}?k={token}")
    assert location.endswith(f"#build:{entry.id}"), location


def test_the_door_is_shut_to_a_stranger(served) -> None:
    """It says what is on somebody's shelf, so it answers to them and to nobody else."""
    port, _, out = served
    entry = an_entry()
    build_a_reader(out, "mine-he", entry.source)

    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", f"/open/{entry.id}")
        response = connection.getresponse()
        response.read()
        assert response.status == 403, response.status
    finally:
        connection.close()
