"""The local page, and the one endpoint a reader talks back to.

A reader opens before its word meanings are looked up and then asks for them. That
request crosses the only door this server has, so the containment and the key matter as
much as the answer.
"""

from __future__ import annotations

import io
import json
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from targum.accounts import Store
from targum.mail import ConsoleMailer
from targum.serve import Handler, Library


class Postbox(io.StringIO):
    """Somewhere for the sign-in link to land where a test can read it back."""

    @property
    def link(self) -> str:
        """The most recent link sent, since asking again is what voids the one before."""
        for line in reversed(self.getvalue().splitlines()):
            if "/account/enter?t=" in line:
                return line.strip()
        raise AssertionError(f"no link was sent:\n{self.getvalue()}")


@pytest.fixture
def postbox() -> Postbox:
    return Postbox()


@pytest.fixture
def served(tmp_path: Path, postbox: Postbox) -> Iterator[tuple[int, str, Path]]:
    """A running server on a free port. Returns the port, the key, and the output dir."""
    out = tmp_path / "targum-out"
    out.mkdir()
    token = "test-key"
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    handler = type(
        "TestHandler",
        (Handler,),
        {
            "library": Library(out),
            "token": token,
            "page": "<html>start</html>",
            "words": "<html>words</html>",
            "shelf": "<html>library</html>",
            "store": Store(tmp_path / "words.db"),
            "mailer": ConsoleMailer(postbox),
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


def get(port: int, path: str) -> tuple[int, Any]:
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read()
        try:
            return response.status, json.loads(body)
        except json.JSONDecodeError:
            return response.status, body
    finally:
        connection.close()


def write_glossary(out: Path, folder: str, entries: dict[str, str]) -> None:
    build = out / folder
    build.mkdir(parents=True, exist_ok=True)
    (build / "glossary.json").write_text(
        json.dumps(
            {
                "schema_version": 4,
                "source_language": "he",
                "target_language": "en",
                "provider": "test",
                "entries": entries,
                "parts_of_speech": {},
            }
        ),
        encoding="utf-8",
    )


def test_the_glossary_needs_the_key(served: tuple[int, str, Path]) -> None:
    port, _, out = served
    write_glossary(out, "book-he", {"שלום": "peace"})
    status, _ = get(port, "/glossary/book-he")
    assert status == 403


def test_not_yet_is_a_normal_answer(served: tuple[int, str, Path]) -> None:
    """The file appears when the lookups finish. Until then the reader keeps asking."""
    port, key, _ = served
    status, body = get(port, f"/glossary/book-he?k={key}")
    assert status == 200
    assert body == {"ready": False}


def test_it_hands_over_the_meanings_once_they_exist(served: tuple[int, str, Path]) -> None:
    port, key, out = served
    write_glossary(out, "book-he", {"שלום": "peace", "עם": "people"})
    status, body = get(port, f"/glossary/book-he?k={key}")
    assert status == 200
    assert body == {"ready": True, "entries": {"שלום": "peace", "עם": "people"}}


def test_it_will_not_climb_out_of_the_output_directory(
    served: tuple[int, str, Path], tmp_path: Path
) -> None:
    """The same containment `_serve_reader` has, on a path that also names a file."""
    (tmp_path / "glossary.json").write_text('{"entries": {"secret": "leaked"}}', encoding="utf-8")
    port, key, _ = served
    for attempt in ("..", "%2e%2e", "../..", "book-he/../.."):
        status, body = get(port, f"/glossary/{attempt}?k={key}")
        assert (status, body) in [
            (404, {"error": "not found"}),
            (200, {"ready": False}),
        ], attempt
        assert body != {"ready": True, "entries": {"secret": "leaked"}}


def test_a_half_written_file_reads_as_not_yet(served: tuple[int, str, Path]) -> None:
    """Written while the reader happens to ask. It will ask again in a moment."""
    port, key, out = served
    build = out / "book-he"
    build.mkdir(parents=True)
    (build / "glossary.json").write_text('{"entries": {"שלו', encoding="utf-8")
    status, body = get(port, f"/glossary/book-he?k={key}")
    assert (status, body) == (200, {"ready": False})


def test_the_words_page_is_behind_the_key(served: tuple[int, str, Path]) -> None:
    """It is a view of everything you have kept, so it is a door like any other."""
    port, token, _ = served
    status, _ = get(port, "/words")
    assert status == 403
    status, body = get(port, f"/words?k={token}")
    assert status == 200
    assert b"words" in body


# --- accounts ---------------------------------------------------------------
#
# The point of all of this is one sentence: the same account shows the same words on a
# second device, and a browser nobody is signed into shows nothing. Everything below is
# some part of that claim.


def call(
    port: int, method: str, path: str, body: Any = None, cookie: str = ""
) -> tuple[int, Any, str]:
    """A request that can carry a session and report the one it is handed back."""
    connection = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        headers = {"Content-Type": "application/json"}
        if cookie:
            headers["Cookie"] = cookie
        connection.request(
            method, path, json.dumps(body).encode("utf-8") if body is not None else None, headers
        )
        response = connection.getresponse()
        raw = response.read()
        handed = response.getheader("Set-Cookie") or ""
        location = response.getheader("Location") or ""
        try:
            return response.status, json.loads(raw), handed or location
        except json.JSONDecodeError:
            return response.status, raw, handed or location
    finally:
        connection.close()


def sign_in(port: int, postbox: Postbox, email: str = "reader@example.com") -> str:
    """Go all the way through the front door, and come back with a session cookie."""
    status, payload, _ = call(port, "POST", "/account/sign-in", {"email": email})
    assert status == 200 and payload["sent"], payload
    link = postbox.link
    _, _, handed = call(port, "GET", link[link.index("/account/enter") :])
    assert "targum_session=" in handed, handed
    return handed.split(";", 1)[0]


def test_a_signed_out_browser_is_shown_nothing(served: tuple[int, str, Path]) -> None:
    """No session, no word list. The whole reason there is a session at all."""
    port, token, _ = served
    status, payload = get(port, f"/account/me?k={token}")
    assert status == 200
    assert payload == {"signedIn": False}

    status, payload, _ = call(port, "POST", f"/sync?k={token}", {"since": 0})
    assert status == 401
    assert payload["signedIn"] is False


def test_a_link_signs_you_in_and_only_once(served: tuple[int, str, Path], postbox: Postbox) -> None:
    """A magic link is a bearer token that has to survive being in an inbox.

    Single use is what stops a forwarded email, a shared screenshot, or a mail server
    that keeps a copy from being a way in later.
    """
    port, token, _ = served
    cookie = sign_in(port, postbox)
    status, payload = get(port, f"/account/me?k={token}")
    assert payload == {"signedIn": False}, "the key alone is not a person"

    status, payload, _ = call(port, "GET", f"/account/me?k={token}", cookie=cookie)
    assert payload["signedIn"] is True
    assert payload["email"] == "reader@example.com"

    # The same link a second time is spent, and lands back on the page rather than on
    # an error: clicking an old email twice is an ordinary thing to do.
    link = postbox.link
    status, _, where = call(port, "GET", link[link.index("/account/enter") :])
    assert status == 303
    assert "signin=expired" in where


def test_an_address_is_never_confirmed_or_denied(served: tuple[int, str, Path]) -> None:
    """The sign-in form must not become a way of asking who has an account here."""
    port, _, _ = served
    first = call(port, "POST", "/account/sign-in", {"email": "known@example.com"})[1]
    second = call(port, "POST", "/account/sign-in", {"email": "stranger@example.com"})[1]
    assert first == second

    status, payload, _ = call(port, "POST", "/account/sign-in", {"email": "not-an-address"})
    assert status == 400


def test_words_follow_the_account_to_another_device(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """The done-when for the whole feature, written as a test.

    Two cookies for one account stand in for a laptop and a phone. What one keeps, the
    other is handed on its next sync, and neither has to know the other exists.
    """
    port, token, _ = served
    laptop = sign_in(port, postbox)
    phone = sign_in(port, postbox)  # same address, second browser

    status, pushed, _ = call(
        port,
        "POST",
        f"/sync?k={token}",
        {
            "since": 0,
            "words": [
                {
                    "language": "he",
                    "lemma": "ספר",
                    "surface": "הספר",
                    "status": 2,
                    "meaning": "book",
                    "at": 1000,
                    "seen": 1000,
                }
            ],
            "docs": [{"hash": "abc", "title": "A text", "language": "he", "seen": 1000}],
        },
        cookie=laptop,
    )
    assert status == 200

    status, got, _ = call(port, "POST", f"/sync?k={token}", {"since": 0}, cookie=phone)
    assert [word["lemma"] for word in got["words"]] == ["ספר"]
    assert got["words"][0]["meaning"] == "book"
    assert [doc["hash"] for doc in got["docs"]] == ["abc"]

    # And having taken it, the phone is not handed it again on every sync afterwards.
    status, again, _ = call(
        port, "POST", f"/sync?k={token}", {"since": got["revision"]}, cookie=phone
    )
    assert again["words"] == []


def test_a_newer_edit_wins_and_a_delete_sticks(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """Last-write-wins, and tombstones.

    Without the tombstone, deleting a word on one device is indistinguishable from a
    word the other device has not heard of, and it comes straight back.
    """
    port, token, _ = served
    laptop = sign_in(port, postbox)
    phone = sign_in(port, postbox)

    base = {"language": "he", "lemma": "אור", "meaning": "light", "at": 100, "seen": 100}
    call(port, "POST", f"/sync?k={token}", {"since": 0, "words": [base]}, cookie=laptop)

    # An edit made earlier does not overwrite one made later, whichever order they land.
    call(
        port,
        "POST",
        f"/sync?k={token}",
        {"since": 0, "words": [{**base, "status": 3, "seen": 300}]},
        cookie=phone,
    )
    call(
        port,
        "POST",
        f"/sync?k={token}",
        {"since": 0, "words": [{**base, "status": 1, "seen": 200}]},
        cookie=laptop,
    )
    _, state, _ = call(port, "POST", f"/sync?k={token}", {"since": 0}, cookie=laptop)
    assert state["words"][0]["status"] == 3
    assert state["words"][0]["meaning"] == "light", "a partial push must not erase"

    call(
        port,
        "POST",
        f"/sync?k={token}",
        {"since": 0, "words": [{**base, "gone": 1, "seen": 400}]},
        cookie=laptop,
    )
    _, state, _ = call(port, "POST", f"/sync?k={token}", {"since": 0}, cookie=phone)
    assert state["words"][0]["gone"] == 1


def test_signing_out_ends_it_on_that_browser_only(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """One browser signing out must not sign out the other, or lose anything."""
    port, token, _ = served
    laptop = sign_in(port, postbox)
    phone = sign_in(port, postbox)

    call(
        port,
        "POST",
        f"/sync?k={token}",
        {"since": 0, "words": [{"language": "he", "lemma": "בית", "seen": 10}]},
        cookie=laptop,
    )
    status, payload, handed = call(port, "POST", "/account/sign-out", {}, cookie=laptop)
    assert status == 200 and "Max-Age=0" in handed

    _, mine, _ = call(port, "GET", f"/account/me?k={token}", cookie=laptop)
    assert mine == {"signedIn": False}

    _, theirs, _ = call(port, "GET", f"/account/me?k={token}", cookie=phone)
    assert theirs["signedIn"] is True
    assert theirs["counts"]["words"] == 1


def test_a_session_outlives_a_restart_where_the_key_does_not(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """Signing in has to fix the thing it looks like it should fix.

    The start-up key changes every run, which is why a bookmark never worked. A session
    is on disk, so once somebody has signed in their bookmark starts working — and that
    means the key cannot be the only thing that opens the door.
    """
    port, _, _ = served
    cookie = sign_in(port, postbox)

    status, payload, _ = call(port, "GET", "/account/me", cookie=cookie)
    assert status == 200
    assert payload["signedIn"] is True

    status, body, _ = call(port, "GET", "/words", cookie=cookie)
    assert status == 200 and b"words" in body

    # And without either, still nothing.
    status, body, _ = call(port, "GET", "/words")
    assert status == 403
