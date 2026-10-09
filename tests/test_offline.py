"""targum's worker and what a text takes to save, without a browser (design.md §12, "A
worker keeps what the reader saved, and fetches nothing else", 2026-10-09).

The worker itself is driven in `test_offline_browser.py`; this holds what can be read off
the files and the server: the policy, the one route, the list of files and its guards, and
the rules the worker is written to keep.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from targum.accounts import Store
from targum.render.builder import ASSETS
from targum.serve import POLICY, WORKER_POLICY, Handler, Library

TOKEN = "test-key"


def book(folder: Path, chapters: int = 3) -> Path:
    """A built text of `chapters` chapters at `folder`, the way a real one is laid out."""
    from test_chapter_ui import book as made

    from targum.models import Document, SegmentedDocument, Translation, read_artifact
    from targum.render import render

    made(folder, chapters=chapters, translated=chapters)
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    translation = read_artifact(Translation, folder / "translations" / "null.natural.en.json")
    assert segmented is not None and translation is not None
    document = Document(source="m", title="A Book", language="he", blocks=[], content_hash="b")
    render(document, segmented, [translation], folder / "reader")
    return folder / "reader"


@pytest.fixture
def served(tmp_path: Path) -> Iterator[tuple[int, Path]]:
    out = tmp_path / "targum-out"
    out.mkdir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    server.RequestHandlerClass = type(
        "TestHandler",
        (Handler,),
        {
            "library": Library(out),
            "token": TOKEN,
            "store": Store(tmp_path / "words.db"),
            "address": f"http://127.0.0.1:{port}",
            "translated": {},
        },
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield port, out
    finally:
        server.shutdown()
        server.server_close()


def get(port: int, path: str, host: str = "") -> tuple[int, dict[str, str], bytes]:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    connection.request("GET", path, headers={"Host": host} if host else {})
    answer = connection.getresponse()
    body = answer.read()
    connection.close()
    return answer.status, {k.lower(): v for k, v in answer.getheaders()}, body


def test_the_page_policy_names_the_worker_and_nothing_else_moved() -> None:
    assert POLICY.count("worker-src 'self'") == 1
    assert POLICY.count("connect-src 'self'") == 1, "the worker asks nothing of anywhere else"
    assert "unsafe-inline" not in POLICY and "unsafe-eval" not in POLICY
    assert "script-src" not in POLICY, "scripts are still named by hash, page by page"


def test_the_worker_is_served_from_the_root_to_anyone_on_our_name(
    served: tuple[int, Path],
) -> None:
    port, _ = served
    status, head, body = get(port, "/sw.js")
    assert status == 200, "no key: the browser asks for it again by itself"
    assert head["content-type"].startswith("text/javascript")
    assert head["cache-control"] == "no-cache", "a changed worker is always seen"
    assert head["content-security-policy"] == WORKER_POLICY
    assert b'addEventListener("fetch"' in body
    assert b"/*" not in body, "served without its comments, like every baked asset"
    status, _, _ = get(port, "/sw.js", host="elsewhere.example")
    assert status == 404


def test_a_text_lists_every_page_and_sidecar_with_its_size(served: tuple[int, Path]) -> None:
    port, out = served
    reader = book(out / "local" / "book-he")
    (reader / "video").mkdir()
    (reader / "video" / "part-001.webm").write_bytes(b"film" * 10)
    (reader / "audio").mkdir()
    (reader / "audio" / "aliyah-1.mp3").write_bytes(b"sound" * 3)
    (reader / "notes.txt").write_text("not part of the reader", encoding="utf-8")

    page = "/reader/book-he/reader/sec-0002.html?k=whatever&list=3"
    status, _, body = get(port, f"/offline.json?page={page}&k={TOKEN}")
    assert status == 200
    told = json.loads(body)
    assert told["title"] == "A Book"
    assert told["base"] == "/reader/book-he/reader/"
    urls = {file["url"]: file for file in told["files"]}
    assert set(urls) == {
        "/reader/book-he/reader/index.html",
        "/reader/book-he/reader/sec-0001.html",
        "/reader/book-he/reader/sec-0002.html",
        "/reader/book-he/reader/sec-0003.html",
        "/reader/book-he/reader/video/part-001.webm",
        "/reader/book-he/reader/audio/aliyah-1.mp3",
    }, "every page and sidecar, nothing else in the folder"
    assert urls["/reader/book-he/reader/video/part-001.webm"] == {
        "url": "/reader/book-he/reader/video/part-001.webm",
        "bytes": 40,
        "film": True,
    }
    assert not urls["/reader/book-he/reader/audio/aliyah-1.mp3"]["film"]
    assert told["bytes"] == sum(file["bytes"] for file in told["files"])
    for url in urls:
        assert get(port, f"{url}?k={TOKEN}")[0] == 200, f"{url} is a file a reader can open"


def test_the_list_keeps_to_the_roots_a_reader_is_served_from(served: tuple[int, Path]) -> None:
    port, out = served
    book(out / "local" / "book-he")
    book(out / "p9" / "theirs")
    for page in (
        "/reader/..%2Fp9%2Ftheirs/reader/index.html",
        "/reader/../p9/theirs/reader/index.html",
        "/reader/nothing-here/reader/index.html",
        "/library",
    ):
        status, _, _ = get(port, f"/offline.json?page={page}&k={TOKEN}")
        assert status == 404, page
    status, _, body = get(port, "/offline.json?page=/reader/book-he/reader/index.html")
    assert status == 403, "and only to somebody who could open the text"


#: The worker's three answers, and only those: what it is allowed to fetch.
def worker_source() -> str:
    return (ASSETS / "sw.js").read_text(encoding="utf-8")


def test_the_worker_fetches_nothing_by_itself() -> None:
    """No cache filled on install, nothing fetched ahead: two `fetch(` calls, both handing on
    the request the browser was already making."""
    source = worker_source()
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
    assert "addAll" not in code and ".add(" not in code
    assert re.findall(r"\bfetch\(([^)]*)\)", code) == ["request", "request"]
    install = code[code.index('"install"') : code.index('"activate"')]
    assert "caches" not in install and "fetch" not in install
    assert "cache.put(key, kept(copy))" in code, "a saved page is refreshed only when opened"
    assert "saved && saved[key]" in code, "and only a page that was saved"


def test_the_page_and_the_worker_key_a_file_the_same_way() -> None:
    """Written twice because the two never share a scope; a difference would be a saved
    file nobody can find."""
    page = (ASSETS / "offline.js").read_text(encoding="utf-8")
    worker = worker_source()

    def reader_rule(source: str) -> str:
        found = re.search(r"var READER = (/.*/);", source)
        assert found, "no READER"
        return found.group(1)

    def key_rule(source: str) -> str:
        body = source[source.index("function keyOf(address) {") :]
        return re.sub(r"\s+", "", body[: body.index("return url.href;")])

    assert reader_rule(page) == reader_rule(worker)
    assert key_rule(page).replace("location.origin", "ORIGIN") == key_rule(worker).replace(
        "self.location.origin", "ORIGIN"
    )
    assert 'url.searchParams.delete("k")' in worker


def test_signing_out_takes_the_saved_texts_too() -> None:
    sync = (ASSETS / "sync.js").read_text(encoding="utf-8")
    clear = sync[sync.index("function clearLocal() {") : sync.index("var PLACE_EVERY")]
    assert "TargumOffline.removeAll()" in clear


def test_every_page_with_the_bar_and_every_reader_carries_the_saving() -> None:
    from targum.render.builder import TEMPLATES

    assert "asset('offline.js')" in (TEMPLATES / "_nav.html.j2").read_text(encoding="utf-8")
    reader = (TEMPLATES / "reader.html.j2").read_text(encoding="utf-8")
    assert reader.index("asset('sync.js')") < reader.index("asset('offline.js')")
