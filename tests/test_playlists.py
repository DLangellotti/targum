"""A playlist is the reader's (targum-internal#364; design.md §12, 2026-09-23).

The store half — made, listed, filled, reordered, emptied, capped, taken away and
forgotten with the account — and the HTTP half, which is the same thing through the door
the page and the swipe use, with the owner taken from the session and never the body.
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
from targum.accounts import MOST_IN_PLAYLIST, MOST_PLAYLISTS, Person, Store

HOST = "targum.page"


def a_store(tmp_path: Path) -> tuple[Store, int, int]:
    store = Store(tmp_path / "targum.db")
    one = store.finish_sign_in(store.start_sign_in("one@example.com"))
    two = store.finish_sign_in(store.start_sign_in("two@example.com"))
    assert one is not None and two is not None
    return store, one[0].id, two[0].id


# --- the store -------------------------------------------------------------------


def test_a_playlist_is_made_filled_and_read_back_in_order(tmp_path: Path) -> None:
    store, me, _ = a_store(tmp_path)
    made = store.make_playlist(me, "  In the   kitchen ")
    assert made is not None and made["name"] == "In the kitchen"
    assert made["made_by"] == "reader" and made["items"] == []
    pid = int(made["id"])
    store.add_to_playlist(me, pid, "Cheese swirls", reader="cheese-swirls")
    store.add_to_playlist(me, pid, "Raiba cookies", job="job-1")
    got = store.playlist(me, pid)
    assert got is not None
    assert [(i["position"], i["reader"], i["job"]) for i in got["items"]] == [
        (0, "cheese-swirls", None),
        (1, None, "job-1"),
    ]
    listed = store.playlists(me)
    assert listed[0]["count"] == 2 and listed[0]["first"] == "cheese-swirls"


def test_a_text_is_not_added_twice(tmp_path: Path) -> None:
    store, me, _ = a_store(tmp_path)
    pid = int((store.make_playlist(me, "x") or {})["id"])
    store.add_to_playlist(me, pid, "A", reader="a")
    again = store.add_to_playlist(me, pid, "A", reader="a")
    assert again is not None and again["position"] == 0
    assert len((store.playlist(me, pid) or {})["items"]) == 1


def test_a_playlist_holds_twenty(tmp_path: Path) -> None:
    """design.md §12: a set is capped, at twenty to start."""
    store, me, _ = a_store(tmp_path)
    pid = int((store.make_playlist(me, "x") or {})["id"])
    for n in range(MOST_IN_PLAYLIST):
        assert store.add_to_playlist(me, pid, f"t{n}", reader=f"r{n}") is not None
    assert store.add_to_playlist(me, pid, "one more", reader="r-more") is None


def test_a_reader_keeps_at_most_fifty(tmp_path: Path) -> None:
    store, me, _ = a_store(tmp_path)
    for n in range(MOST_PLAYLISTS):
        assert store.make_playlist(me, f"p{n}") is not None
    assert store.make_playlist(me, "one more") is None
    assert store.make_playlist(me, "   ") is None


def test_moving_and_dropping_keep_positions_whole(tmp_path: Path) -> None:
    store, me, _ = a_store(tmp_path)
    pid = int((store.make_playlist(me, "x") or {})["id"])
    for name in "abcd":
        store.add_to_playlist(me, pid, name, reader=name)
    assert store.move_in_playlist(me, pid, 2, -1)
    assert not store.move_in_playlist(me, pid, 0, -1), "nothing above the first"
    assert not store.move_in_playlist(me, pid, 3, 1), "nothing below the last"
    order = lambda: [i["reader"] for i in (store.playlist(me, pid) or {})["items"]]  # noqa: E731
    assert order() == ["a", "c", "b", "d"]
    assert store.drop_from_playlist(me, pid, 1)
    assert order() == ["a", "b", "d"]
    assert [i["position"] for i in (store.playlist(me, pid) or {})["items"]] == [0, 1, 2]


def test_another_account_cannot_see_or_touch_it(tmp_path: Path) -> None:
    store, me, them = a_store(tmp_path)
    pid = int((store.make_playlist(me, "mine") or {})["id"])
    store.add_to_playlist(me, pid, "a", reader="a")
    assert store.playlist(them, pid) is None
    assert store.playlists(them) == []
    assert store.add_to_playlist(them, pid, "b", reader="b") is None
    assert not store.move_in_playlist(them, pid, 0, 1)
    assert not store.drop_from_playlist(them, pid, 0)
    assert not store.rename_playlist(them, pid, "theirs")
    assert not store.drop_playlist(them, pid)
    assert (store.playlist(me, pid) or {})["name"] == "mine"


def test_taking_one_away_is_a_tombstone(tmp_path: Path) -> None:
    store, me, _ = a_store(tmp_path)
    pid = int((store.make_playlist(me, "x") or {})["id"])
    assert store.drop_playlist(me, pid)
    assert store.playlist(me, pid) is None and store.playlists(me) == []
    assert not store.drop_playlist(me, pid), "gone once"


def test_a_build_fills_its_place_or_is_passed_over(tmp_path: Path) -> None:
    """The half #365 writes and #366 reads."""
    store, me, _ = a_store(tmp_path)
    pid = int((store.make_playlist(me, "set") or {})["id"])
    store.add_to_playlist(me, pid, "one", job="j1")
    store.add_to_playlist(me, pid, "two", job="j2")
    assert store.playlist_item_built("j1", "reader-one") == 1
    assert store.playlist_item_failed("j2") == 1
    items = (store.playlist(me, pid) or {})["items"]
    assert items[0]["reader"] == "reader-one" and not items[0]["failed"]
    assert items[1]["failed"] is True


def test_forgetting_an_account_forgets_its_playlists(tmp_path: Path) -> None:
    store, me, them = a_store(tmp_path)
    pid = int((store.make_playlist(me, "x") or {})["id"])
    store.add_to_playlist(me, pid, "a", reader="a")
    theirs = int((store.make_playlist(them, "y") or {})["id"])
    person = Person(id=me, email="one@example.com")
    exported = store.everything(person)
    assert exported["playlists"][0]["items"][0]["reader"] == "a"
    store.forget(person)
    left = store.db.execute("SELECT COUNT(*) AS n FROM playlist WHERE person = ?", (me,))
    assert int(left.fetchone()["n"]) == 0
    items = store.db.execute("SELECT COUNT(*) AS n FROM playlist_item WHERE playlist = ?", (pid,))
    assert int(items.fetchone()["n"]) == 0
    assert store.playlist(them, theirs) is not None, "only theirs"


# --- the door --------------------------------------------------------------------


@pytest.fixture(scope="module")
def box(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> tuple[int, str, str]:
    tmp = tmp_path_factory.mktemp("playlists")
    store_path = tmp / "targum.db"
    store = Store(store_path)
    one = store.finish_sign_in(store.start_sign_in("one@example.com"))
    two = store.finish_sign_in(store.start_sign_in("two@example.com"))
    assert one is not None and two is not None
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
    return port, one[1], two[1]


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


def test_a_playlist_is_made_and_read_through_the_door(box: tuple[int, str, str]) -> None:
    port, mine, _ = box
    status, made = send(
        port, "POST", "/playlists", {"name": "Reels", "reader": "a-reel", "title": "A reel"}, mine
    )
    assert status == 200, made
    pid = made["id"]
    assert made["items"][0]["open"] == "/reader/a-reel/reader/index.html"
    status, got = send(port, "GET", f"/playlists/{pid}.json", session=mine)
    assert status == 200 and got["name"] == "Reels"
    status, listed = send(port, "GET", "/playlists.json", session=mine)
    assert status == 200 and pid in [one["id"] for one in listed["playlists"]]


def test_the_door_changes_it(box: tuple[int, str, str]) -> None:
    port, mine, _ = box
    _, made = send(port, "POST", "/playlists", {"name": "Order"}, mine)
    pid = made["id"]
    for name in ("a", "b"):
        send(port, "POST", f"/playlists/{pid}", {"do": "add", "reader": name, "title": name}, mine)
    _, moved = send(
        port, "POST", f"/playlists/{pid}", {"do": "move", "position": 1, "by": -1}, mine
    )
    assert [i["reader"] for i in moved["items"]] == ["b", "a"]
    _, renamed = send(port, "POST", f"/playlists/{pid}", {"do": "rename", "name": "Two"}, mine)
    assert renamed["name"] == "Two"
    _, dropped = send(port, "POST", f"/playlists/{pid}", {"do": "drop", "position": 0}, mine)
    assert [i["reader"] for i in dropped["items"]] == ["a"]
    _, gone = send(port, "POST", f"/playlists/{pid}", {"do": "gone"}, mine)
    assert gone["gone"] is True
    status, _ = send(port, "GET", f"/playlists/{pid}.json", session=mine)
    assert status == 404


def test_another_account_gets_404_everywhere(box: tuple[int, str, str]) -> None:
    port, mine, theirs = box
    _, made = send(port, "POST", "/playlists", {"name": "Private"}, mine)
    pid = made["id"]
    assert send(port, "GET", f"/playlists/{pid}.json", session=theirs)[0] == 404
    for do in ({"do": "add", "reader": "x"}, {"do": "rename", "name": "y"}, {"do": "gone"}):
        assert send(port, "POST", f"/playlists/{pid}", do, theirs)[0] == 404
    assert send(port, "GET", f"/playlists/{pid}.json", session=mine)[0] == 200


def test_a_stranger_is_asked_to_sign_in(box: tuple[int, str, str]) -> None:
    port, _, _ = box
    assert send(port, "GET", "/playlists.json")[0] == 401
    assert send(port, "POST", "/playlists", {"name": "x"})[0] == 401


def test_a_nameless_playlist_says_so(box: tuple[int, str, str]) -> None:
    port, mine, _ = box
    status, said = send(port, "POST", "/playlists", {"name": " "}, mine)
    assert status == 400 and "name" in said["error"].lower()
