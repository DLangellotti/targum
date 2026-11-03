"""A person's own copy of a shelf text, built without its words, never hides the shelf's.

David opened the Mishneh Torah's Foundations of the Torah on 2026-11-03 and no word on
the page could be tapped or marked, and no chapter on its contents said how much of it he
knew. The shared build had all of it. His own folder of the same name, built on
2026-09-03 with no annotation, won the lookup, as a person's own copy always does, and
served a page with an empty word table over the shelf's full one.
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
from targum.serve import Handler, Library, _shelf_supersedes

NAME = "הלכות-יסודי-התורה-he"


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[int, str, Path]]:
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
            "welcome": "<html>start</html>",
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


def build(out: Path, home: str, *, page: str, document: str, words: bool) -> Path:
    """A built reader: one part, its contents naming the document by hash, and an
    annotation beside it where the build reached the words."""
    folder = out / home / NAME
    (folder / "reader").mkdir(parents=True)
    (folder / "reader" / "sec-0001.html").write_text(page, encoding="utf-8")
    (folder / "reader" / "contents.json").write_text(
        json.dumps({"version": 1, "document": document, "sections": []}), encoding="utf-8"
    )
    if words:
        (folder / "annotation.json").write_text("{}", encoding="utf-8")
    return folder


def get(port: int, path: str) -> str:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.read().decode("utf-8")
    finally:
        connection.close()


def page(port: int, token: str) -> str:
    from urllib.parse import quote

    return get(port, f"/reader/{quote(NAME)}/reader/sec-0001.html?k={token}")


def test_a_wordless_copy_of_the_same_document_gives_way_to_the_shelf(served) -> None:
    port, token, out = served
    build(out, "shared", page="<html>shelf, with words</html>", document="abc", words=True)
    build(out, "local", page="<html>mine, no words</html>", document="abc", words=False)

    assert "shelf, with words" in page(port, token)


def test_your_own_copy_with_its_words_still_wins(served) -> None:
    """The precedence is unchanged for every copy that has anything to show."""
    port, token, out = served
    build(out, "shared", page="<html>shelf</html>", document="abc", words=True)
    build(out, "local", page="<html>mine</html>", document="abc", words=True)

    assert "mine" in page(port, token)


def test_your_own_copy_of_a_different_document_still_wins(served) -> None:
    """An edited copy is a different document, and it is theirs whatever it lacks."""
    port, token, out = served
    build(out, "shared", page="<html>shelf</html>", document="abc", words=True)
    build(out, "local", page="<html>mine, edited</html>", document="def", words=False)

    assert "mine, edited" in page(port, token)


def test_nothing_gives_way_to_a_shelf_without_words_either(tmp_path: Path) -> None:
    """Two wordless builds: the person's own stays theirs."""
    build(tmp_path, "shared", page="", document="abc", words=False)
    build(tmp_path, "local", page="", document="abc", words=False)

    assert not _shelf_supersedes(tmp_path / "local", tmp_path / "shared", f"{NAME}/reader/x")


def test_a_name_that_climbs_out_is_never_looked_at(tmp_path: Path) -> None:
    assert not _shelf_supersedes(tmp_path / "local", tmp_path / "shared", "../x/reader/y")
    assert not _shelf_supersedes(tmp_path / "local", tmp_path / "shared", "")
