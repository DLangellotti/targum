"""The Playlists tab and one playlist's page (targum-internal#434).

The store half — a drag from one place to another, where the reader is in a playlist and
which one they are in, and "Play next" — and the door: each playlist answered with what
its card and its page draw (its first four for the cover, its minutes, how much of it the
reader knows, whose hand made it, what is still waiting), `/playlists/current.json`, and
`/playlists/<id>` as a page.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from http.client import HTTPConnection
from pathlib import Path

import pytest

from targum import serve
from targum.accounts import Store

HOST = "targum.page"


def a_store(tmp_path: Path) -> tuple[Store, int]:
    store = Store(tmp_path / "targum.db")
    one = store.finish_sign_in(store.start_sign_in("one@example.com"))
    assert one is not None
    return store, one[0].id


def filled(store: Store, me: int, names: str = "abcde") -> int:
    pid = int((store.make_playlist(me, "x") or {})["id"])
    for name in names:
        store.add_to_playlist(me, pid, name, reader=name)
    return pid


def order(store: Store, me: int, pid: int) -> list[str]:
    return [str(i["reader"]) for i in (store.playlist(me, pid) or {})["items"]]


# --- the store -------------------------------------------------------------------


def test_a_drag_moves_one_text_and_closes_up_behind_it(tmp_path: Path) -> None:
    store, me = a_store(tmp_path)
    pid = filled(store, me)
    assert store.move_to_in_playlist(me, pid, 0, 3)
    assert order(store, me, pid) == ["b", "c", "d", "a", "e"]
    assert store.move_to_in_playlist(me, pid, 4, 1)
    assert order(store, me, pid) == ["b", "e", "c", "d", "a"]
    assert [i["position"] for i in (store.playlist(me, pid) or {})["items"]] == [0, 1, 2, 3, 4]
    assert not store.move_to_in_playlist(me, pid, 0, 5), "no sixth place"
    assert not store.move_to_in_playlist(me + 1, pid, 0, 1), "not theirs"


def test_where_the_reader_is_follows_the_text_they_are_on(tmp_path: Path) -> None:
    store, me = a_store(tmp_path)
    pid = filled(store, me)
    assert store.playlist_here(me, pid, 2)  # on "c"
    assert (store.current_playlist(me) or {})["at"] == 2
    store.move_to_in_playlist(me, pid, 2, 0)
    assert (store.playlist(me, pid) or {})["at"] == 0, "c moved to the top, and so did they"
    store.move_to_in_playlist(me, pid, 3, 0)  # something in front of them
    assert (store.playlist(me, pid) or {})["at"] == 1
    store.move_in_playlist(me, pid, 1, 1)
    assert (store.playlist(me, pid) or {})["at"] == 2
    store.drop_from_playlist(me, pid, 0)
    assert (store.playlist(me, pid) or {})["at"] == 1
    assert order(store, me, pid)[1] == "c"


def test_the_one_you_are_in_is_the_last_one_opened_until_it_is_gone_through(
    tmp_path: Path,
) -> None:
    store, me = a_store(tmp_path)
    assert store.current_playlist(me) is None
    first = filled(store, me, "ab")
    second = filled(store, me, "cd")
    store.playlist_here(me, first, 0)
    time.sleep(0.002)
    store.playlist_here(me, second, 1)
    assert (store.current_playlist(me) or {})["id"] == second
    store.playlist_here(me, second, 2)  # past the last: the end card
    assert store.current_playlist(me) is None, "a playlist gone through is not one you're in"
    store.drop_playlist(me, first)
    assert store.current_playlist(me) is None


def test_play_next_puts_a_text_straight_after_the_one_you_are_on(tmp_path: Path) -> None:
    store, me = a_store(tmp_path)
    pid = filled(store, me, "abcd")
    store.playlist_here(me, pid, 1)  # on "b"
    store.play_next(me, pid, "New", "new")
    assert order(store, me, pid) == ["a", "b", "new", "c", "d"]
    store.play_next(me, pid, "D", "d")  # already in it, further on: moved up
    assert order(store, me, pid) == ["a", "b", "d", "new", "c"]
    store.play_next(me, pid, "A", "a")  # already in it, behind: moved after "b"
    assert order(store, me, pid) == ["b", "a", "d", "new", "c"]
    assert (store.playlist(me, pid) or {})["at"] == 0, "still on b"
    fresh = filled(store, me, "xy")
    store.play_next(me, fresh, "Z", "z")
    assert order(store, me, fresh) == ["z", "x", "y"], "nowhere yet is before the first"


def test_a_database_from_before_the_place_in_a_playlist_is_brought_up_to_date(
    tmp_path: Path,
) -> None:
    """Schema 41 had no `at` or `visited` on a playlist. Opening it adds both, empty, and
    a playlist made before them is nobody's current one until it is opened."""
    import sqlite3

    from targum.accounts import SCHEMA_VERSION

    store, me = a_store(tmp_path)
    pid = filled(store, me, "ab")
    store.close()
    old = sqlite3.connect(tmp_path / "targum.db")
    old.execute("ALTER TABLE playlist DROP COLUMN at")
    old.execute("ALTER TABLE playlist DROP COLUMN visited")
    old.execute("PRAGMA user_version = 41")
    old.commit()
    old.close()
    store = Store(tmp_path / "targum.db")
    assert int(store.db.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_VERSION >= 42
    assert store.current_playlist(me) is None
    assert store.playlist_here(me, pid, 0)
    assert (store.current_playlist(me) or {})["id"] == pid


# --- the door --------------------------------------------------------------------


@pytest.fixture(scope="module")
def box(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> tuple[int, str, Path]:
    tmp = tmp_path_factory.mktemp("playlist-tab")
    store_path = tmp / "targum.db"
    store = Store(store_path)
    one = store.finish_sign_in(store.start_sign_in("one@example.com"))
    assert one is not None
    # Two texts on the shared shelf, which a playlist can point at as targum's own sets do.
    for name, words in (("story", 260), ("article", 650)):
        folder = tmp / "out" / "shared" / name
        (folder / "reader").mkdir(parents=True)
        (folder / "reader" / "index.html").write_text("<html></html>", encoding="utf-8")
        (folder / "document.json").write_text(
            json.dumps(
                {
                    "title": name.title(),
                    "language": "he",
                    "source": f"file:{name}.txt",
                    "blocks": [{"text": "שלום " * words}],
                }
            ),
            encoding="utf-8",
        )
    port = free_port()
    threading.Thread(
        target=lambda: serve.start(
            out=tmp / "out",
            port=port,
            open_browser=False,
            store=store_path,
            require_account=True,
            public_address=f"https://{HOST}",
        ),
        daemon=True,
    ).start()
    for _ in range(60):
        try:
            probe = HTTPConnection("127.0.0.1", port, timeout=1)
            probe.request("GET", "/health")
            probe.getresponse().read()
            probe.close()
            break
        except OSError:
            time.sleep(0.1)
    return port, one[1], tmp


def send(port: int, method: str, path: str, body: object = None, session: str = "") -> tuple:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest(method, path, skip_host=True)
    conn.putheader("Host", HOST)
    raw = json.dumps(body).encode() if body is not None else b""
    if raw:
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(len(raw)))
    if session:
        conn.putheader("Cookie", f"targum_session={session}")
    conn.endheaders()
    if raw:
        conn.send(raw)
    response = conn.getresponse()
    got = response.read()
    conn.close()
    try:
        return response.status, json.loads(got)
    except json.JSONDecodeError:
        return response.status, got


def test_a_playlist_says_what_its_card_draws(box: tuple[int, str, Path]) -> None:
    port, mine, _ = box
    _, made = send(port, "POST", "/playlists", {"name": "Mornings"}, mine)
    pid = made["id"]
    for name in ("story", "article", "not-built-yet"):
        send(port, "POST", f"/playlists/{pid}", {"do": "add", "reader": name, "title": name}, mine)
    status, one = send(port, "GET", f"/playlists/{pid}.json", session=mine)
    assert status == 200
    story = one["items"][0]["facts"]
    assert story["language"] == "he" and story["minutes"] == 2
    assert one["items"][2]["open"] and one["items"][2]["facts"] is None, "not on any shelf"
    # Seven minutes, two and five, and the cover's four: three texts and nothing.
    assert one["seconds"] == 7 * 60
    assert [c["title"] for c in one["covers"]] == ["story", "article", "not-built-yet"]
    _, listed = send(port, "GET", "/playlists.json", session=mine)
    card = next(p for p in listed["playlists"] if p["id"] == pid)
    assert card["made_by"] == "reader" and card["seconds"] == 7 * 60 and card["count"] == 3
    assert "items" not in card, "a card is the playlist added up, not its texts"
    assert listed["current"] is None


def test_where_you_are_is_told_and_marks_the_one_you_are_in(box: tuple[int, str, Path]) -> None:
    port, mine, _ = box
    _, made = send(port, "POST", "/playlists", {"name": "Evenings"}, mine)
    pid = made["id"]
    for name in ("story", "article"):
        send(port, "POST", f"/playlists/{pid}", {"do": "add", "reader": name, "title": name}, mine)
    assert send(port, "POST", f"/playlists/{pid}", {"do": "here", "position": 1}, mine)[0] == 200
    _, current = send(port, "GET", "/playlists/current.json", session=mine)
    assert current["current"] == {"id": pid, "name": "Evenings", "at": 1}
    _, listed = send(port, "GET", "/playlists.json", session=mine)
    assert listed["current"]["id"] == pid
    _, next_one = send(
        port, "POST", f"/playlists/{pid}", {"do": "next", "reader": "x", "title": "X"}, mine
    )
    assert [i["reader"] for i in next_one["items"]] == ["story", "article", "x"]
    _, dragged = send(
        port, "POST", f"/playlists/{pid}", {"do": "move", "position": 2, "to": 0}, mine
    )
    assert [i["reader"] for i in dragged["items"]] == ["x", "story", "article"]
    assert dragged["at"] == 2, "still on the article"
    assert send(port, "GET", "/playlists/current.json")[0] == 401


def test_a_playlist_is_a_page_of_its_own(box: tuple[int, str, Path]) -> None:
    port, mine, _ = box
    _, made = send(port, "POST", "/playlists", {"name": "Own page"}, mine)
    status, page = send(port, "GET", f"/playlists/{made['id']}", session=mine)
    assert status == 200 and b'id="one"' in page
    # Signed out, a person looking at it meets a page, not a 401 in JSON.
    status, page = send(port, "GET", f"/playlists/{made['id']}")
    assert status == 200 and not page.startswith(b"{")
