"""Subscriptions on the account (design.md §12, "A subscription is the account's, and
what it brings comes under Continue", 2026-10-09): the rows, the follows carried across,
and the doors the tab and a subscription's own page read and press."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Callable
from http.client import HTTPConnection
from pathlib import Path

import pytest

from targum import serve
from targum.accounts import DEFAULT_CAP, SCHEMA_VERSION, Person, Store

HOST = "targum.page"


def a_store(tmp_path: Path) -> tuple[Store, int, int]:
    store = Store(tmp_path / "targum.db")
    one = store.finish_sign_in(store.start_sign_in("one@example.com"))
    two = store.finish_sign_in(store.start_sign_in("two@example.com"))
    assert one is not None and two is not None
    return store, one[0].id, two[0].id


# --- the rows ----------------------------------------------------------------------


def test_every_follow_is_carried_to_its_account_with_its_stop_token(tmp_path: Path) -> None:
    """A link in a mail already sent still stops the series it named, and what the
    per-series mail last sent is kept so nothing is mailed twice."""
    path = tmp_path / "targum.db"
    store, me, _ = a_store(tmp_path)
    with store.write() as db:
        db.execute("DELETE FROM subscription")
        db.execute(
            "INSERT INTO follow (email, series, state, stop, since, sent, instalment, language)"
            " VALUES ('one@example.com', 'parasha', 'on', 'stop-1', 5, 6, 'noach', 'ru')"
        )
        db.execute(
            "INSERT INTO follow (email, series, state, stop, since, ended)"
            " VALUES ('one@example.com', 'tehillim', 'off', 'stop-2', 5, 9)"
        )
        db.execute(
            "INSERT INTO follow (email, series, state, stop, since)"
            " VALUES ('nobody@example.com', 'parasha', 'on', 'stop-3', 5)"
        )
        db.execute(
            "INSERT INTO subscriber (email, state, stop, asked, joined)"
            " VALUES ('two@example.com', 'on', 'weekly-stop', 1, 2)"
        )
    store.close()

    again = Store(path)
    rows = {(row["person"], row["key"]): row for row in again.subscriptions(None, every=True)}
    assert rows == {}, "nobody's"
    mine = {row["key"]: row for row in again.subscriptions(me, every=True)}
    assert mine["parasha"]["stop"] == "stop-1" and mine["parasha"]["state"] == "on"
    assert mine["parasha"]["instalment"] == "noach" and mine["parasha"]["said"] == "ru"
    assert mine["tehillim"]["state"] == "off", "a follow that was stopped stays stopped"
    assert again.following_series("stop-1") == "parasha"
    assert again.followers("parasha") == [("one@example.com", "stop-1", "ru")]
    # The weekly of an account that had it, as a row the tab shows; its mail stays put.
    them = again.person_by_email("two@example.com")
    assert them is not None
    weekly = again.subscription_for(them.id, "series", "weekly")
    assert weekly is not None and weekly["state"] == "on"
    assert again.following("two@example.com")
    count = again.db.execute("SELECT COUNT(*) AS n FROM subscription").fetchone()["n"]
    again.close()

    # Opening it again carries nothing twice, and never turns a stopped one back on.
    third = Store(path)
    assert third.db.execute("SELECT COUNT(*) AS n FROM subscription").fetchone()["n"] == count
    version = sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0]
    assert version == SCHEMA_VERSION == 43


def test_subscribing_pausing_and_stopping(tmp_path: Path) -> None:
    store, me, them = a_store(tmp_path)
    row = store.add_subscription(
        me, "channel", "UC123", name="כאן ארכיון", language="he", cap=DEFAULT_CAP, said="ru-RU"
    )
    sub = int(row["id"])
    assert row["cap"] == 60 and row["said"] == "ru" and row["state"] == "on"
    assert store.subscription(them, sub) is None, "never somebody else's"
    assert not store.set_subscription_state(them, sub, "paused")

    store.add_sub_items(
        sub, [{"key": "v1", "title": "one", "state": "due"}, {"key": "v2", "title": "two"}]
    )
    assert store.add_sub_items(sub, [{"key": "v1", "title": "again"}]) == 0, "found once"
    assert store.set_subscription_state(me, sub, "paused")
    items = {item["key"]: item for item in store.sub_items(sub)}
    assert items["v1"]["state"] == "listed" and items["v1"]["came"] == "paused", (
        "a paused subscription builds nothing; a resume lists it for a press"
    )
    assert store.set_subscription_state(me, sub, "on")
    assert store.subscription(me, sub)["paused"] == 0  # type: ignore[index]
    assert not store.set_subscription_cap(me, sub, 77), "only the caps on the page"
    assert store.set_subscription_cap(me, sub, 120)
    assert store.set_subscription_state(me, sub, "off")
    assert store.subscriptions(me) == []
    assert not store.set_subscription_state(me, sub, "paused"), "an ended one is not paused"
    # Subscribing again starts it from now: what came before is from before.
    again = store.add_subscription(me, "channel", "UC123")
    assert again["id"] == sub and again["state"] == "on" and again["cap"] == 120
    series = store.add_subscription(me, "series", "parasha")
    with pytest.raises(sqlite3.IntegrityError):
        with store.write() as db:
            db.execute(
                "INSERT INTO subscription (person, kind, key, stop, since)"
                " VALUES (?, 'series', 'parasha', 'x', 1)",
                (me,),
            )
    assert not store.set_subscription_cap(me, int(series["id"]), 60), "a series has no cap"


def test_new_items_are_the_readers_until_opened(tmp_path: Path) -> None:
    store, me, them = a_store(tmp_path)
    sub = int(store.add_subscription(me, "topic", "sport", language="he")["id"])
    store.add_sub_items(
        sub,
        [
            {"key": "a", "title": "first", "link": "https://x.example/a", "published": 1},
            {"key": "b", "title": "second", "link": "https://x.example/b", "published": 2},
            {"key": "c", "title": "older", "came": "before"},
        ],
    )
    fresh = store.new_sub_items(me)
    assert [item["key"] for item in fresh] == ["b", "a"], "newest first, never what was before"
    assert store.new_sub_items(them) == []
    assert not store.saw_sub_item(them, sub, "b"), "nobody else marks it"
    assert store.saw_sub_item(me, sub, "b")
    assert [item["key"] for item in store.new_sub_items(me)] == ["a"]
    rows = store.subscriptions(me)
    assert rows[0]["new"] == 1 and rows[0]["latest"]["key"] == "b"


def test_the_months_credits_are_read_off_its_own_job_rows(tmp_path: Path) -> None:
    """One ledger: what a channel has built with is the `length` of its own jobs."""
    store, me, _ = a_store(tmp_path)
    sub = int(store.add_subscription(me, "channel", "UC1", cap=60)["id"])
    other = int(store.add_subscription(me, "channel", "UC2", cap=60)["id"])
    month = 1_000
    for job, owner, length, made, which, kind in (
        ("j1", me, 240.0, 2_000, sub, "subscription"),
        ("j2", me, 600.0, 2_000, sub, "subscription"),
        ("j3", me, 600.0, 500, sub, "subscription"),
        ("j4", me, 600.0, 2_000, other, "subscription"),
        ("j5", me, 600.0, 2_000, sub, "build"),
    ):
        store.save_job(
            {
                "id": job,
                "owner": owner,
                "home": "h",
                "source": "s",
                "length": length,
                "made": made,
                "kind": kind,
                "options": json.dumps({"subscription": which}),
            }
        )
    assert store.month_credits(me, sub, month) == 14
    assert store.month_credits(me, other, month) == 10


def test_the_weekly_row_follows_the_weekly_mail(tmp_path: Path) -> None:
    store, me, _ = a_store(tmp_path)
    store.follow("one@example.com", True, "en")
    assert store.subscription_for(me, "series", "weekly")["state"] == "on"  # type: ignore[index]
    stop = store.db.execute(
        "SELECT stop FROM subscriber WHERE email = 'one@example.com'"
    ).fetchone()["stop"]
    assert store.stop_subscription(stop)
    assert store.subscription_for(me, "series", "weekly")["state"] == "off"  # type: ignore[index]
    # A follow by an address with no account is answered False and writes nothing.
    assert not store.follow_series("nobody@example.com", "parasha")


def test_forgetting_an_account_forgets_what_it_subscribed_to(tmp_path: Path) -> None:
    store, me, them = a_store(tmp_path)
    sub = int(store.add_subscription(me, "podcast", "https://feed.example/rss")["id"])
    store.add_sub_items(sub, [{"key": "e1", "title": "one"}])
    store.add_subscription(them, "series", "parasha")
    exported = store.everything(Person(id=me, email="one@example.com"))
    assert exported["subscriptions"][0]["kind"] == "podcast", "theirs to take away"
    assert "stop" not in exported["subscriptions"][0]
    store.forget(Person(id=me, email="one@example.com"))
    left = store.db.execute("SELECT COUNT(*) AS n FROM sub_item").fetchone()["n"]
    assert left == 0 and store.subscriptions(me, every=True) == []
    assert len(store.subscriptions(them)) == 1, "only theirs"


# --- the doors -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def box(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> tuple[int, str, str, Path]:
    tmp = tmp_path_factory.mktemp("subscriptions")
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
    return port, one[1], two[1], store_path


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


def test_the_tab_lists_what_the_reader_subscribed_to(box: tuple[int, str, str, Path]) -> None:
    port, mine, theirs, store_path = box
    status, _ = send(port, "GET", "/subscriptions.json")
    assert status != 200, "signed out, there is nothing to list"
    status, answer = send(port, "POST", "/account/follows", {"series": "parasha"}, mine)
    assert status == 200 and answer["follows"] == ["parasha"]
    status, listed = send(port, "GET", "/subscriptions.json", session=mine)
    assert status == 200 and listed["signedIn"] is True
    (row,) = listed["subscriptions"]
    assert row["kind"] == "series" and row["key"] == "parasha" and row["every"] == "week"
    assert row["builds"] is False and row["page"] == f"/subscriptions/{row['id']}"
    assert any(one["id"] == "weekly" for one in listed["series"]), "what can be taken"
    assert "back" in listed["credits"]
    status, other = send(port, "GET", "/subscriptions.json", session=theirs)
    assert other["subscriptions"] == []
    status, _ = send(port, "GET", f"/subscriptions/{row['id']}.json", session=theirs)
    assert status == 404, "another account's subscription is not there"


def test_a_subscription_is_paused_resumed_and_stopped_from_its_page(
    box: tuple[int, str, str, Path],
) -> None:
    port, mine, theirs, store_path = box
    store = Store(store_path)
    me = store.person_by_email("one@example.com")
    assert me is not None
    sub = int(store.add_subscription(me.id, "channel", "UCabc", name="Kan", cap=60)["id"])
    store.add_sub_items(sub, [{"key": "v1", "title": "פלאפל", "link": "https://youtu.be/v1"}])
    status, page = send(port, "GET", f"/subscriptions/{sub}", session=mine)
    assert status == 200 and b"subs.js" not in page and b"sub-one" in page
    status, got = send(port, "GET", f"/subscriptions/{sub}.json", session=mine)
    one = got["subscription"]
    assert one["builds"] and one["cap"] == 60 and one["used"] == 0
    assert one["items"][0]["title"] == "פלאפל" and one["caps"] == [30, 60, 120, 240]
    status, _ = send(port, "POST", f"/subscriptions/{sub}", {"action": "pause"}, theirs)
    assert status == 404
    status, got = send(port, "POST", f"/subscriptions/{sub}", {"action": "pause"}, mine)
    assert status == 200 and got["subscription"]["state"] == "paused"
    status, got = send(port, "POST", f"/subscriptions/{sub}", {"action": "resume"}, mine)
    assert got["subscription"]["state"] == "on"
    status, got = send(port, "POST", f"/subscriptions/{sub}", {"action": "jump"}, mine)
    assert status == 400 and "error" in got
    status, got = send(port, "POST", f"/subscriptions/{sub}", {"action": "unsubscribe"}, mine)
    assert got["subscription"]["state"] == "off"
    status, listed = send(port, "GET", "/subscriptions.json", session=mine)
    assert all(row["id"] != sub for row in listed["subscriptions"])


def test_an_item_opened_from_home_is_no_longer_new(box: tuple[int, str, str, Path]) -> None:
    port, mine, theirs, store_path = box
    store = Store(store_path)
    me = store.person_by_email("one@example.com")
    assert me is not None
    sub = int(store.add_subscription(me.id, "outlet", "globes", name="Globes")["id"])
    store.add_sub_items(sub, [{"key": "a1", "title": "כתבה", "link": "https://g.example/a1"}])
    status, got = send(
        port, "POST", "/subscriptions/seen", {"subscription": sub, "key": "a1"}, theirs
    )
    assert got == {"seen": False}
    status, got = send(
        port, "POST", "/subscriptions/seen", {"subscription": sub, "key": "a1"}, mine
    )
    assert got == {"seen": True}
    assert all(item["key"] != "a1" for item in store.new_sub_items(me.id))
