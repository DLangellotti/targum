"""targum's worker in a real browser (design.md §12, "A worker keeps what the reader saved,
and fetches nothing else", 2026-10-09).

A real server, because a worker needs an origin: a text is saved from its own page, the
connection goes, and the saved text opens, its film answers in slices, and what was not
saved does not open. The server writes down every request it is asked, which is how
"fetches nothing by itself" is held.

    uv sync --extra browser && uv run playwright install chromium
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api")

from playwright.sync_api import Error as PlaywrightError  # noqa: E402
from test_offline import TOKEN, book  # noqa: E402
from test_reader_browser import browser, video_reader  # noqa: E402, F401

from targum.accounts import Store  # noqa: E402
from targum.serve import Handler, Library  # noqa: E402


class Served:
    def __init__(self, out: Path, port: int, server: ThreadingHTTPServer, asked: list[str]):
        self.out = out
        self.port = port
        self.server = server
        self.asked = asked

    def url(self, path: str) -> str:
        joint = "&" if "?" in path else "?"
        return f"http://127.0.0.1:{self.port}{path}{joint}k={TOKEN}"

    def gone(self) -> None:
        """The connection goes: nobody is there to answer."""
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def served(tmp_path: Path) -> Iterator[Served]:
    out = tmp_path / "targum-out"
    out.mkdir()
    asked: list[str] = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]

    def _get(self: Any) -> None:
        asked.append(self.path)
        Handler._get(self)

    server.RequestHandlerClass = type(
        "TestHandler",
        (Handler,),
        {
            "library": Library(out),
            "token": TOKEN,
            "store": Store(tmp_path / "words.db"),
            "address": f"http://127.0.0.1:{port}",
            "translated": {},
            "_get": _get,
        },
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    holder = Served(out, port, server, asked)
    try:
        yield holder
    finally:
        try:
            holder.gone()
        except Exception:
            pass


def opened(browser, served: Served, path: str):  # noqa: F811
    context = browser.new_context(service_workers="allow")
    page = context.new_page()
    page.goto(served.url(path))
    page.wait_for_function(
        "() => navigator.serviceWorker && navigator.serviceWorker.controller !== null",
        timeout=10000,
    )
    return context, page


SAVE = """
async (args) => {
  const seen = [];
  const handle = window.TargumOffline.save(args.page, {
    how: 'you',
    film: args.film,
    progress: (p) => seen.push(p),
  });
  try {
    const item = await handle.done;
    return { item, seen };
  } catch (e) {
    return { failed: e.reason || String(e), seen };
  }
}
"""

KEYS = """
async () => {
  const cache = await caches.open('targum-offline');
  return (await cache.keys()).map((r) => r.url);
}
"""


def test_a_saved_text_opens_without_the_network(browser, served: Served) -> None:  # noqa: F811
    book(served.out / "local" / "book-he")
    book(served.out / "local" / "other-he", chapters=1)
    context, page = opened(browser, served, "/reader/book-he/reader/sec-0002.html")
    try:
        # Registering and opening fetched no file of any text but the page itself.
        readers = [path for path in served.asked if path.startswith("/reader/")]
        assert [path.split("?")[0] for path in readers] == ["/reader/book-he/reader/sec-0002.html"]
        assert "/sw.js" in served.asked

        before = len(served.asked)
        saved = page.evaluate(SAVE, {"page": page.url, "film": True})
        assert "item" in saved, saved
        item = saved["item"]
        assert item["id"] == "/reader/book-he/reader/"
        assert item["how"] == "you" and item["title"] == "A Book"
        assert len(item["files"]) == 4, "the contents and the three chapters"
        assert saved["seen"][-1]["done"] == saved["seen"][-1]["total"] == item["bytes"]

        fetched = [path.split("?")[0] for path in served.asked[before:]]
        assert fetched[0] == "/offline.json"
        assert sorted(fetched[1:]) == sorted(
            f"/reader/book-he/reader/{name}"
            for name in ("index.html", "sec-0001.html", "sec-0002.html", "sec-0003.html")
        ), "each file once, and nothing it was not asked for"

        keys = page.evaluate(KEYS)
        assert keys and not any("k=" in url for url in keys), "the key is never kept"

        served.gone()
        context.set_offline(True)
        for name in ("sec-0003.html", "index.html", "sec-0002.html"):
            page.goto(served.url(f"/reader/book-he/reader/{name}") + "&list=2")
            page.wait_for_selector(".pair, .toc", state="attached")
        assert page.locator(".pair").count() > 0

        with pytest.raises(PlaywrightError):
            page.goto(served.url("/reader/other-he/reader/index.html"))
    finally:
        context.close()


RANGE = """
async (args) => {
  const answer = await fetch(args.url, { headers: { Range: args.range } });
  const body = new Uint8Array(await answer.arrayBuffer());
  return {
    status: answer.status,
    range: answer.headers.get('content-range'),
    length: body.length,
    head: Array.from(body.slice(0, 4)),
  };
}
"""


def test_a_saved_film_answers_in_slices_without_the_network(browser, served: Served) -> None:  # noqa: F811
    folder = served.out / "local" / "talk-he"
    folder.mkdir(parents=True)
    video_reader(folder, spans=[[0.05, 0.45], [0.5, 0.95]])
    film = next((folder / "reader" / "video").iterdir())
    whole = film.read_bytes()
    context, page = opened(browser, served, "/reader/talk-he/reader/index.html")
    try:
        saved = page.evaluate(SAVE, {"page": page.url, "film": True})
        assert saved["item"]["withFilm"], saved
        address = f"/reader/talk-he/reader/video/{film.name}"
        assert any(url.endswith(address) for url in page.evaluate(KEYS))

        served.gone()
        context.set_offline(True)
        probe = page.evaluate(RANGE, {"url": address, "range": "bytes=0-1"})
        assert probe == {
            "status": 206,
            "range": f"bytes 0-1/{len(whole)}",
            "length": 2,
            "head": list(whole[:2]),
        }, "Safari's probe comes back a real 206"
        tail = page.evaluate(RANGE, {"url": address, "range": "bytes=-10"})
        assert tail["status"] == 206 and tail["length"] == 10
        assert tail["range"] == f"bytes {len(whole) - 10}-{len(whole) - 1}/{len(whole)}"
        past = page.evaluate(RANGE, {"url": address, "range": f"bytes={len(whole) + 5}-"})
        assert past["status"] == 416

        page.goto(served.url("/reader/talk-he/reader/index.html"))
        page.wait_for_function(
            "() => { const v = document.querySelector('.video-el');"
            " return v && v.readyState >= 1; }",
            timeout=10000,
        )
    finally:
        context.close()


def test_sound_and_text_leaves_the_picture_behind(browser, served: Served) -> None:  # noqa: F811
    folder = served.out / "local" / "talk-he"
    folder.mkdir(parents=True)
    video_reader(folder)
    context, page = opened(browser, served, "/reader/talk-he/reader/index.html")
    try:
        saved = page.evaluate(SAVE, {"page": page.url, "film": False})
        item = saved["item"]
        assert item["film"] and not item["withFilm"]
        assert not any("/video/" in url for url in item["files"])
        assert not any("/video/" in url for url in page.evaluate(KEYS))
    finally:
        context.close()


def test_stopping_a_save_keeps_nothing_and_remove_takes_it_back(browser, served: Served) -> None:  # noqa: F811
    book(served.out / "local" / "book-he")
    context, page = opened(browser, served, "/reader/book-he/reader/sec-0001.html")
    try:
        stopped = page.evaluate(
            """async (page) => {
                 const handle = window.TargumOffline.save(page, {});
                 handle.stop();
                 try { await handle.done; return 'saved'; } catch (e) { return e.reason; }
               }""",
            page.url,
        )
        assert stopped == "stopped"
        assert [url for url in page.evaluate(KEYS) if "/reader/" in url] == []

        assert "item" in page.evaluate(SAVE, {"page": page.url, "film": True})
        page.evaluate("() => window.TargumOffline.remove('/reader/book-he/reader/')")
        assert [url for url in page.evaluate(KEYS) if "/reader/" in url] == []
        assert page.evaluate("() => window.TargumOffline.list()") == []
    finally:
        context.close()


def test_a_page_opened_off_the_disk_registers_nothing(browser, tmp_path: Path) -> None:  # noqa: F811
    reader = book(tmp_path / "book-he", chapters=1)
    context = browser.new_context(service_workers="allow")
    page = context.new_page()
    try:
        page.goto(sorted(reader.glob("*.html"))[-1].as_uri())
        page.wait_for_selector(".pair")
        assert page.evaluate("() => window.TargumOffline.able") is False
    finally:
        context.close()
