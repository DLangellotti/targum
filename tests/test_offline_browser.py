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


# -- saving: on its own, by a press, and a playlist (design.md §12, 2026-10-09) ------------

LIST = """async () => (await window.TargumOffline.list())
  .map((i) => ({ id: i.id, how: i.how, kind: i.kind || '', held: i.held || [],
                 members: i.members || [], files: (i.files || []).length }))"""

#: Nothing kept on its own, so a test about the press sees only the press.
NONE_ON_ITS_OWN = (
    "try { localStorage.setItem('targum:offline',"
    " JSON.stringify({ recent: 0, playlist: false })); } catch (e) {}"
)


def kept(page, id_: str):
    # Off the index as this page last wrote it: the saving is this page's own.
    page.wait_for_function("(id) => !!window.TargumOffline.saved(id)", arg=id_, timeout=15000)


def test_the_last_five_texts_opened_are_kept_on_their_own(browser, served: Served) -> None:  # noqa: F811
    for n in range(6):
        book(served.out / "local" / f"text-{n}", chapters=1)
    context, page = opened(browser, served, "/reader/text-0/reader/index.html")
    try:
        for n in range(6):
            page.goto(served.url(f"/reader/text-{n}/reader/index.html"))
            kept(page, f"/reader/text-{n}/reader/")
        # The sixth's save and the first's eviction are two writes; on a slow runner the
        # list was read between them (master went red on it, 2026-10-09). Wait for the
        # room to have been made, then say so if it never was.
        try:
            page.wait_for_function(
                "async () => (await window.TargumOffline.list()).length === 5", timeout=15000
            )
        except Exception:  # noqa: BLE001 - the assertion below says what is wrong
            pass
        saved = page.evaluate(LIST)
        assert sorted(item["id"] for item in saved) == [
            f"/reader/text-{n}/reader/" for n in range(1, 6)
        ], "the first one opened made room for the sixth"
        assert {item["how"] for item in saved} == {"auto"}
        keys = page.evaluate(KEYS)
        assert not any("/text-0/" in url for url in keys), "and its files went with it"

        # Opened again, it is only marked: nothing of it is fetched.
        before = len(served.asked)
        opened_before = page.evaluate(
            "() => window.TargumOffline.saved('/reader/text-3/reader/').opened"
        )
        page.goto(served.url("/reader/text-3/reader/index.html"))
        page.evaluate(f"() => {{ window.OPENED_BEFORE = {opened_before}; }}")
        page.wait_for_function(
            "() => { const it = window.TargumOffline.saved('/reader/text-3/reader/');"
            " return it && it.opened > window.OPENED_BEFORE; }",
            timeout=15000,
        )
        fetched = [p.split("?")[0] for p in served.asked[before:] if p.startswith("/reader/")]
        assert fetched == ["/reader/text-3/reader/index.html"], "only the page, by opening it"

        page.evaluate("() => window.TargumOffline.choose({ recent: 3 })")
        assert len(page.evaluate(LIST)) == 3, "three, when the reader chose three"
    finally:
        context.close()


PARTS = """(id) => { const it = window.TargumOffline.saved(id);
  return it ? { part: !!it.part, how: it.how, pages: it.pages,
                files: (it.files || []).map((f) => new URL(f).pathname) } : null; }"""


def test_a_book_opened_keeps_only_its_opened_parts_until_saved_whole(
    browser,  # noqa: F811
    served: Served,
) -> None:
    """David, 2026-10-10: opening a contents page or a chapter keeps what was opened, and
    the whole book is saved only by the press."""
    book(served.out / "local" / "book-he")
    base = "/reader/book-he/reader/"
    context, page = opened(browser, served, f"{base}index.html")
    try:
        page.wait_for_function(
            "(id) => { const it = window.TargumOffline.saved(id); return it && it.part; }",
            arg=base,
            timeout=15000,
        )
        assert page.evaluate(PARTS, base)["files"] == [f"{base}index.html"], (
            "the contents page alone, not the book"
        )
        page.goto(served.url(f"{base}sec-0002.html"))
        page.wait_for_function(
            "(id) => (window.TargumOffline.saved(id) || {}).pages === 2", arg=base, timeout=15000
        )
        kept_now = page.evaluate(PARTS, base)
        assert kept_now["part"] and kept_now["how"] == "auto"
        assert sorted(kept_now["files"]) == [f"{base}index.html", f"{base}sec-0002.html"]
        cached = {u.split("?")[0] for u in page.evaluate(KEYS) if "/reader/" in u}
        assert not any("sec-0001" in u or "sec-0003" in u for u in cached), "nothing unopened"

        # The row still offers the whole, and the press saves it.
        page.click(".bar-tools [data-more]")
        row = page.locator("#offline-row")
        page.wait_for_selector("#offline-row.offline-idle")
        assert row.locator(".offline-label").inner_text() == "Save for offline"
        row.locator(".offline-go").click()
        page.wait_for_selector("#offline-row.offline-saved")
        whole = page.evaluate(PARTS, base)
        assert not whole["part"] and whole["how"] == "you"
        assert len([f for f in whole["files"] if f.endswith(".html")]) == 4
    finally:
        context.close()


def test_save_for_offline_says_the_room_then_saves_and_removes(browser, served: Served) -> None:  # noqa: F811
    book(served.out / "local" / "book-he")
    context = browser.new_context(service_workers="allow")
    context.add_init_script(NONE_ON_ITS_OWN)
    page = context.new_page()
    try:
        page.goto(served.url("/reader/book-he/reader/sec-0001.html"))
        page.wait_for_function("() => navigator.serviceWorker.controller !== null")
        page.click(".bar-tools [data-more]")
        row = page.locator("#offline-row")
        page.wait_for_function(
            "() => /MB/.test(document.querySelector('#offline-row .offline-size').textContent)"
        )
        assert row.locator(".offline-label").inner_text() == "Save for offline"
        planned = page.evaluate("() => window.TargumOffline.plan(location.href)")
        assert (
            row.locator(".offline-size").inner_text() == f"{round(planned['bytes'] / 1e6, 1):g} MB"
        )
        row.locator(".offline-go").click()
        page.wait_for_selector("#offline-row.offline-saved")
        assert row.locator(".offline-label").inner_text() == "Saved on this device"
        assert page.evaluate(LIST)[0]["how"] == "you"
        row.locator(".offline-remove").click()
        page.wait_for_selector("#offline-row.offline-idle")
        assert page.evaluate(LIST) == []
    finally:
        context.close()


HANG = """
(() => {
  const real = window.fetch;
  window.fetch = (url, options) => {
    const saving = options && options.headers && options.headers['X-Targum-Save'];
    if (saving && window.FAIL_ON && String(url).includes(window.FAIL_ON)) {
      return Promise.resolve(new Response('', { status: 500 }));
    }
    if (saving && String(url).includes(window.HANG_ON || '\\u0000')) {
      return new Promise((resolve, reject) => {
        options.signal && options.signal.addEventListener('abort', () => {
          reject(new DOMException('stopped', 'AbortError'));
        });
      });
    }
    return real(url, options);
  };
})();
"""


def test_a_save_can_be_stopped_and_a_failure_tried_again(browser, served: Served) -> None:  # noqa: F811
    book(served.out / "local" / "book-he")
    context = browser.new_context(service_workers="allow")
    context.add_init_script(NONE_ON_ITS_OWN)
    context.add_init_script(HANG)
    page = context.new_page()
    try:
        page.goto(served.url("/reader/book-he/reader/sec-0001.html"))
        page.wait_for_function("() => navigator.serviceWorker.controller !== null")
        page.click(".bar-tools [data-more]")
        row = page.locator("#offline-row")
        page.evaluate("() => { window.HANG_ON = 'sec-0003'; }")
        row.locator(".offline-go").click()
        page.wait_for_selector("#offline-row.offline-saving")
        assert "of" in row.locator(".offline-size").inner_text()
        assert row.locator(".offline-note").inner_text() == "Keep this page open until it's saved."
        row.locator(".offline-stop").click()
        page.wait_for_selector("#offline-row.offline-idle")
        assert [url for url in page.evaluate(KEYS) if "/reader/" in url] == []

        page.evaluate("() => { window.HANG_ON = ''; window.FAIL_ON = 'sec-0002'; }")
        row.locator(".offline-go").click()
        page.wait_for_selector("#offline-row.offline-failed")
        assert "We couldn't save this for offline." in row.inner_text()
        assert [url for url in page.evaluate(KEYS) if "/reader/" in url] == [], "nothing half-kept"
        page.evaluate("() => { window.FAIL_ON = ''; }")
        row.locator(".fault-act").click()
        page.wait_for_selector("#offline-row.offline-saved")
    finally:
        context.close()


FULL = """
(() => {
  const put = Cache.prototype.put;
  Cache.prototype.put = function (request, response) {
    const url = typeof request === 'string' ? request : request.url;
    if (window.FULL && url.includes('/reader/')) {
      return Promise.reject(new DOMException('full', 'QuotaExceededError'));
    }
    return put.call(this, request, response);
  };
})();
"""


def test_a_full_device_is_said_with_the_text_s_name(browser, served: Served) -> None:  # noqa: F811
    book(served.out / "local" / "book-he")
    context = browser.new_context(service_workers="allow")
    context.add_init_script(NONE_ON_ITS_OWN)
    context.add_init_script(FULL)
    page = context.new_page()
    try:
        page.goto(served.url("/reader/book-he/reader/sec-0001.html"))
        page.wait_for_function("() => navigator.serviceWorker.controller !== null")
        page.evaluate("() => { window.FULL = true; }")
        page.click(".bar-tools [data-more]")
        page.locator("#offline-row .offline-go").click()
        page.wait_for_selector("#offline-row.offline-full")
        said = page.locator("#offline-row").inner_text()
        title = page.locator("#offline-row").get_attribute("data-title")
        assert f"This device is full, so we couldn't save {title}." in said
        assert page.evaluate(LIST) == []
    finally:
        context.close()


PLAYLIST = """
(() => {
  const real = window.fetch;
  window.fetch = (url, options) => {
    if (/\\/playlists\\/7\\.json/.test(String(url))) {
      return Promise.resolve(new Response(JSON.stringify({
        id: 7, name: 'Mornings',
        items: [
          { position: 0, title: 'One', open: '/reader/one-he/reader/index.html',
            facts: { kind: 'story' } },
          { position: 1, title: 'Two', open: '/reader/two-he/reader/index.html',
            facts: { kind: 'article' } },
          { position: 2, title: 'Waiting', open: null, job: 'j' },
        ],
      }), { headers: { 'Content-Type': 'application/json' } }));
    }
    return real(url, options);
  };
})();
"""


def test_a_playlist_opened_is_kept_whole_and_its_page_saves_and_removes_it(
    browser,  # noqa: F811
    served: Served,
) -> None:
    book(served.out / "local" / "one-he", chapters=1)
    book(served.out / "local" / "two-he", chapters=2)
    context = browser.new_context(service_workers="allow")
    context.add_init_script(PLAYLIST)
    page = context.new_page()
    try:
        page.goto(served.url("/reader/one-he/reader/index.html") + "&list=7&at=0")
        page.wait_for_function("() => navigator.serviceWorker.controller !== null")
        kept(page, "playlist:7")
        saved = {item["id"]: item for item in page.evaluate(LIST)}
        assert saved["playlist:7"]["kind"] == "playlist"
        assert saved["playlist:7"]["how"] == "auto"
        assert saved["playlist:7"]["members"] == [
            "/reader/one-he/reader/",
            "/reader/two-he/reader/",
        ]
        assert saved["/reader/two-he/reader/"]["held"] == ["playlist:7"]
        assert saved["/reader/two-he/reader/"]["kind"] == "article"

        # The playlist's own page: what is so, and Remove.
        page.evaluate(
            """() => { const slot = document.createElement('span'); slot.id = 'slot';
                 document.body.appendChild(slot);
                 window.TargumOffline.playlist({ id: 7, name: 'Mornings' }, slot, 'page'); }"""
        )
        page.wait_for_selector("#slot.offline-saved")
        assert page.locator("#slot .offline-label").inner_text() == "Saved for offline"
        page.locator("#slot .offline-remove").click()
        page.wait_for_selector("#slot.offline-idle")
        left = [item["id"] for item in page.evaluate(LIST)]
        assert left == ["/reader/one-he/reader/"], "the text opened stays; the one only held goes"

        page.locator("#slot .offline-go").click()
        page.wait_for_selector("#slot.offline-saved")
        saved = {item["id"]: item for item in page.evaluate(LIST)}
        assert saved["playlist:7"]["how"] == "you"
        card = page.evaluate(
            """() => { const slot = document.createElement('span');
                 window.TargumOffline.playlist({ id: 7, name: 'Mornings' }, slot, 'card');
                 return new Promise((r) => setTimeout(() => r(slot.textContent), 300)); }"""
        )
        assert card.startswith("Saved for offline · ") and card.endswith("MB")
    finally:
        context.close()


# -- Saved on this device (design.md §12, 2026-10-09) ------------------------------------

PERSIST = """
(() => {
  window.PERSIST_ASKED = 0;
  if (navigator.storage) {
    navigator.storage.persisted = () => Promise.resolve(false);
    navigator.storage.persist = () => { window.PERSIST_ASKED += 1; return Promise.resolve(true); };
  }
})();
"""


@pytest.fixture
def saved_served(tmp_path: Path) -> Iterator[Served]:
    """The fixture server with the Saved page drawn, as `start()` draws it."""
    from targum.render.builder import saved_page

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
            "saved_html": saved_page(TOKEN),
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


def test_the_saved_page_lists_both_groups_and_moves_one_with_keep(
    browser,  # noqa: F811
    saved_served: Served,
) -> None:
    served = saved_served
    book(served.out / "local" / "mine-he")
    book(served.out / "local" / "recent-he", chapters=1)
    context = browser.new_context(service_workers="allow")
    context.add_init_script(PERSIST)
    page = context.new_page()
    try:
        page.goto(served.url("/reader/mine-he/reader/sec-0001.html"))
        page.wait_for_function("() => navigator.serviceWorker.controller !== null")
        page.evaluate("(p) => window.TargumOffline.save(p, { how: 'you' }).done", page.url)
        page.goto(served.url("/reader/recent-he/reader/index.html"))
        kept(page, "/reader/recent-he/reader/")

        page.goto(served.url("/you/saved"))
        page.wait_for_selector("#saved-mine:not([hidden]) .saved-row")
        assert page.locator("h1").inner_text() == "Saved on this device"
        assert page.locator("#saved-mine .saved-row").count() == 1
        assert page.locator("#saved-auto .saved-row").count() == 1
        assert (
            "Your last 5 texts and the playlist you're in."
            in page.locator("#saved-auto-says").inner_text()
        )
        mine = page.locator("#saved-mine .saved-row").inner_text()
        assert "A Book" in mine and "By you" in mine and "MB" in mine
        page.wait_for_selector("#saved-room:not([hidden])")
        assert " used of about " in page.locator("#saved-used").inner_text()
        assert page.evaluate("() => window.PERSIST_ASKED") == 0, "asked only from its button"
        page.click("#saved-ask")
        page.wait_for_function("() => window.PERSIST_ASKED === 1")
        assert page.locator("#saved-persist-says").inner_text() == "Your browser will keep them."

        page.locator("#saved-auto .saved-keep-it").click()
        page.wait_for_function(
            "() => document.querySelectorAll('#saved-mine .saved-row').length === 2"
        )
        assert page.locator("#saved-auto").is_hidden()

        page.locator("#saved-mine .saved-remove").first.click()
        page.wait_for_function(
            "() => document.querySelectorAll('#saved-mine .saved-row').length === 1"
        )
        page.click("#saved-all")
        page.wait_for_selector("#saved-none:not([hidden])")
        texts = [item for item in page.evaluate(LIST) if item["kind"] != "page"]
        assert texts == [], "and the line that the account keeps the rest stood beside it"
    finally:
        context.close()


def test_the_saved_page_s_choices_are_this_device_s(browser, saved_served: Served) -> None:  # noqa: F811
    served = saved_served
    context = browser.new_context(service_workers="allow")
    page = context.new_page()
    try:
        page.goto(served.url("/you/saved"))
        page.wait_for_selector("#saved-choices:not([hidden])")
        assert page.locator('[data-recent="5"]').get_attribute("aria-checked") == "true"
        page.click('[data-recent="10"]')
        page.click("#saved-playlist")
        page.click('[data-film="0"]')
        page.wait_for_function(
            "() => document.querySelector('[data-film=\"0\"]')"
            ".getAttribute('aria-checked') === 'true'"
        )
        assert page.evaluate("() => JSON.parse(localStorage.getItem('targum:offline'))") == {
            "recent": 10,
            "playlist": False,
            "film": False,
        }
        assert page.locator("#saved-playlist").get_attribute("aria-checked") == "false"
        assert page.locator("#saved-auto-says").inner_text() == (
            "Your last 10 texts. Newer ones take their place."
        )
    finally:
        context.close()


def test_with_no_connection_an_unsaved_page_opens_the_saved_one(
    browser,  # noqa: F811
    saved_served: Served,
) -> None:
    served = saved_served
    book(served.out / "local" / "kept-he", chapters=1)
    book(served.out / "local" / "away-he", chapters=1)
    context = browser.new_context(service_workers="allow")
    page = context.new_page()
    try:
        page.goto(served.url("/reader/kept-he/reader/index.html"))
        kept(page, "/reader/kept-he/reader/")
        page.goto(served.url("/you/saved"))
        kept(page, "page:/you/saved")

        served.gone()
        context.set_offline(True)
        page.goto(served.url("/reader/away-he/reader/index.html"))
        page.wait_for_selector("#saved-away:not([hidden])")
        assert page.url.split("?")[0].endswith("/you/saved")
        assert "isn't on this device" in page.locator("#saved-away").inner_text()
        assert page.locator("#saved-auto .saved-row").count() == 1
        page.locator("#saved-auto .saved-name").click()
        page.wait_for_selector(".pair, .toc", state="attached")
        assert "/reader/kept-he/" in page.url
    finally:
        context.close()


# -- with no connection (design.md §12, 2026-10-09) --------------------------------------


@pytest.fixture
def words_served(saved_served: Served) -> Served:
    """The Saved page's server, with a reader that has words to tap and the posts it is
    sent written down too."""
    from test_reader_browser import chapter

    chapter(saved_served.out / "local" / "words-he" / "reader")
    handler = saved_served.server.RequestHandlerClass
    asked = saved_served.asked

    def _post(self: Any) -> None:
        asked.append("POST " + self.path)
        Handler._post(self)

    handler._post = _post  # type: ignore[attr-defined]
    return saved_served


def test_with_no_connection_the_band_says_what_still_works(browser, words_served: Served) -> None:  # noqa: F811
    served = words_served
    book(served.out / "local" / "other-he", chapters=1)
    context = browser.new_context(service_workers="allow")
    page = context.new_page()
    try:
        page.goto(served.url("/reader/words-he/reader/index.html"))
        kept(page, "/reader/words-he/reader/")
        page.goto(served.url("/you/saved"))
        kept(page, "page:/you/saved")
        # A shelf of two texts, one of them on this device.
        page.evaluate(
            """() => {
                 const list = document.createElement('ul');
                 list.id = 'shelf';
                 list.innerHTML = '<li><a href="/reader/words-he/reader/index.html">Here</a></li>'
                   + '<li><a href="/reader/other-he/reader/index.html">Away</a></li>';
                 document.querySelector('main').appendChild(list);
               }"""
        )
        context.set_offline(True)
        band = page.locator("#fault-banner")
        band.wait_for()
        assert "We can't reach targum. This page stays open." in band.inner_text()
        assert band.locator(".offline-to-saved").get_attribute("href").startswith("/you/saved")
        page.wait_for_selector('#shelf li[data-offline="away"]')
        away = page.locator('#shelf li[data-offline="away"]')
        assert "Not on this device" in away.inner_text()
        assert "offline-away" in away.get_attribute("class")
        assert "On this device" in page.locator('#shelf li[data-offline="here"]').inner_text()
        talk = page.locator("#talk-open")
        assert talk.get_attribute("aria-disabled") == "true"
        assert talk.get_attribute("data-why") == "Talk needs the connection."
        upload = page.locator('.site-nav a[href*="/add"]').first
        assert upload.get_attribute("data-why") == "Uploading needs the connection."

        # A press on the text that is not here says why, and goes nowhere.
        away.locator("a").click(force=True)
        assert page.locator("#offline-why").inner_text() == (
            "This text isn't on this device, so it opens when you're back online."
        )
        assert page.url.split("?")[0].endswith("/you/saved")

        # Back: the band goes, the marks go, and the back band says it is sending until
        # the push has been answered.
        page.evaluate(
            "() => { window.TargumSync.flush = () =>"
            " new Promise((done) => setTimeout(() => done(true), 600)); }"
        )
        context.set_offline(False)
        page.wait_for_selector("#offline-back:not([hidden])")
        assert page.locator("#offline-back").inner_text() == (
            "We're back. Sending what you did offline."
        )
        page.wait_for_selector("#fault-banner", state="hidden")
        assert page.locator("[data-offline]").count() == 0
        assert talk.get_attribute("aria-disabled") is None
        page.wait_for_selector("#offline-back", state="hidden")
    finally:
        context.close()


def test_a_word_with_no_meaning_is_looked_up_when_the_reader_is_back(
    browser,  # noqa: F811
    words_served: Served,
) -> None:
    served = words_served
    context = browser.new_context(service_workers="allow", reduced_motion="reduce")
    # Every look-up the page sends, with what it asked.
    context.add_init_script(
        """(() => {
             const real = window.fetch;
             window.LOOKED = [];
             window.fetch = (url, options) => {
               if (String(url).includes('/gloss')) window.LOOKED.push(JSON.parse(options.body));
               return real(url, options);
             };
           })();"""
    )
    page = context.new_page()
    try:
        page.goto(served.url("/reader/words-he/reader/index.html"))
        kept(page, "/reader/words-he/reader/")
        context.set_offline(True)
        page.wait_for_selector("#fault-banner:not([hidden])")
        page.click(".w[data-lemma]")
        card = page.locator(".gloss-card")
        card.locator(".fault-act").wait_for()
        assert "Looking this word up needs the connection." in card.inner_text()
        assert "Saved here, sent when you're back" in card.inner_text()
        card.locator(".fault-act").click()
        page.wait_for_function(
            "() => /We'll look it up when you're back/.test("
            "document.querySelector('.gloss-card').textContent)"
        )
        held = page.evaluate("() => JSON.parse(localStorage.getItem('targum:offline:asks'))")
        assert len(held) == 1 and held[0]["body"]["document"]
        lemma = held[0]["body"]["lemma"]

        page.evaluate("() => { window.LOOKED = []; }")
        context.set_offline(False)
        page.wait_for_function("() => !localStorage.getItem('targum:offline:asks')")
        asked = [one for one in page.evaluate("() => window.LOOKED") if not one.get("free")]
        assert asked == [held[0]["body"]], "the press, made once, as a tap makes it"
        assert lemma
    finally:
        context.close()


#: Somebody signed in on this browser, with changes the account has not had.
OWING = """
try {
  localStorage.setItem('targum:sync',
    JSON.stringify({ email: 'r@example.com', revision: 1, pushed: 1 }));
  localStorage.setItem('targum:days', JSON.stringify({ '2026-10-07': 1, '2026-10-08': 1 }));
  localStorage.setItem('targum:vocab:he',
    JSON.stringify({ 'מילה': { status: 'known', at: 5 } }));
} catch (e) {}
"""


def test_what_is_owed_is_counted_in_the_band(browser, words_served: Served) -> None:  # noqa: F811
    served = words_served
    context = browser.new_context(service_workers="allow")
    # Somebody signed in on this browser, with three changes the account has not had.
    context.add_init_script(OWING)
    page = context.new_page()
    try:
        page.goto(served.url("/you/saved"))
        page.wait_for_function("() => window.TargumSync && window.TargumSync.owed() > 0")
        owed = page.evaluate("() => window.TargumSync.owed()")
        context.set_offline(True)
        page.wait_for_selector("#fault-banner .offline-owed:not([hidden])")
        changes = "change" if owed == 1 else "changes"
        assert page.locator("#fault-banner .offline-owed").inner_text() == (
            f"{owed} {changes} saved here, sent when you're back"
        )
    finally:
        context.close()
