"""Where a reader left off, kept on the account (targum-internal#430).

The place was a chapter number in one browser's `localStorage`. It is a row a text on the
account now — the part, the sentence and the second of its recording — written through
`/sync` like every other thing a reader keeps, read back newest first for Continue, and
taken away whole in the export.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import test_serve
from test_serve import Postbox, call, sign_in

from targum.accounts import SCHEMA_VERSION, Person, Store

served = test_serve.served
postbox = test_serve.postbox


def somebody(store: Store, email: str = "reader@example.com") -> Person:
    signed = store.finish_sign_in(store.start_sign_in(email))
    assert signed is not None
    return signed[0]


def place(hash_: str, at: int, **fields: object) -> dict[str, object]:
    return {"hash": hash_, "at": at, "seen": at, **fields}


def test_the_newer_place_wins_whichever_device_sent_it(tmp_path: Path) -> None:
    """The laptop read chapter three; the phone, later, chapter four. A push from the
    laptop that arrives after the phone's — it was offline on a train — must not put the
    reader back in chapter three."""
    store = Store(tmp_path / "words.db")
    person = somebody(store)
    store.push(person, {"places": [place("gen", 200, section="4", segment="b9", seconds=61.5)]})
    store.push(person, {"places": [place("gen", 100, section="3", segment="b2")]})

    [row] = store.places(person.id)
    assert (row["section"], row["segment"], row["seconds"]) == ("4", "b9", 61.5)


def test_places_come_back_newest_first_with_their_titles(tmp_path: Path) -> None:
    """What home's Continue reads: the last few texts, newest first, each named by the
    `doc` row the reader's sync already writes. A text taken off the shelf is left out."""
    store = Store(tmp_path / "words.db")
    person = somebody(store)
    store.push(
        person,
        {
            "docs": [
                {"hash": "gen", "title": "Genesis", "language": "he", "updated": 1, "seen": 1},
                {"hash": "ruth", "title": "Ruth", "language": "he", "updated": 1, "seen": 1},
                {"hash": "gone", "title": "Gone", "language": "he", "updated": 1, "seen": 1},
            ],
            "places": [
                place("gen", 100, section="2", path="/reader/gen/reader/sec-2.html"),
                place("ruth", 300, section="1", segment="b4"),
                place("film", 200, section="1", seconds=12.0),
                place("gone", 400, section="1"),
            ],
        },
    )
    store.push(person, {"docs": [{"hash": "gone", "gone": 1, "seen": 2}]})

    rows = store.places(person.id)
    assert [row["hash"] for row in rows] == ["ruth", "film", "gen"]
    assert rows[0]["title"] == "Ruth" and rows[0]["language"] == "he"
    assert rows[1]["title"] == "", "a place outruns its title, and is still a place"
    assert rows[2]["path"] == "/reader/gen/reader/sec-2.html"

    assert [row["hash"] for row in store.places(person.id, limit=1)] == ["ruth"]
    assert [row["hash"] for row in store.places(person.id, document="gen")] == ["gen"]
    assert store.places(None) == []


def test_the_export_carries_every_place(tmp_path: Path) -> None:
    """`Store.everything` loops the sync kinds, so a place is in it by being one."""
    store = Store(tmp_path / "words.db")
    person = somebody(store)
    store.push(person, {"places": [place("gen", 100, section="2", segment="b7", seconds=3.25)]})

    [row] = store.everything(person)["places"]
    assert row["hash"] == "gen" and row["section"] == "2"
    assert row["segment"] == "b7" and row["seconds"] == 3.25 and row["at"] == 100


def test_a_database_from_before_places_is_brought_up_to_date(tmp_path: Path) -> None:
    """A box on schema 40 has no `place` table. Opening it adds one, empty, and stamps
    the file with the version that has it."""
    path = tmp_path / "words.db"
    Store(path).close()
    old = sqlite3.connect(path)
    old.execute("DROP TABLE place")
    old.execute("PRAGMA user_version = 40")
    old.commit()
    old.close()

    store = Store(path)
    assert int(store.db.execute("PRAGMA user_version").fetchone()[0]) == SCHEMA_VERSION >= 41
    person = somebody(store)
    store.push(person, {"places": [place("gen", 1, section="1")]})
    assert [row["hash"] for row in store.places(person.id)] == ["gen"]


def test_a_place_synced_on_one_device_is_read_back_on_another(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """Through the server's own doors: `/sync` takes a place, the pull hands it to the
    other browser, and `/account/places` answers Continue. Nobody signed out is told
    anything."""
    port, token, _ = served
    status, answer, _ = call(port, "GET", f"/account/places?k={token}")
    assert status == 401 and answer == {"signedIn": False}

    cookie = sign_in(port, postbox)
    status, answer, _ = call(
        port,
        "POST",
        f"/sync?k={token}",
        {"since": 0, "places": [place("gen", 500, section="3", segment="b12", seconds=4)]},
        cookie=cookie,
    )
    assert status == 200
    assert [row["hash"] for row in answer["places"]] == ["gen"], "and a second browser pulls it"

    status, answer, _ = call(
        port, "GET", f"/account/places?k={token}&document=gen&limit=1", cookie=cookie
    )
    assert status == 200 and answer["signedIn"] is True
    [row] = answer["places"]
    assert (row["section"], row["segment"], row["seconds"], row["at"]) == ("3", "b12", 4, 500)

    status, answer, _ = call(port, "GET", f"/account/places?k={token}&limit=x", cookie=cookie)
    assert status == 200 and len(answer["places"]) == 1, "a limit that is not a number is 5"


def test_words_due_a_look_are_the_ones_still_learned_and_untouched_since(tmp_path: Path) -> None:
    """Home's welcome back (design.md §12, 2026-10-09): not a schedule, a count of words at
    steps 1 to 3 not marked since the reader was last in a text."""
    store = Store(tmp_path / "words.db")
    signed = store.finish_sign_in(store.start_sign_in("a@example.org"))
    assert signed is not None
    person = signed[0]
    with store.write() as db:
        for lemma, status, seen, language in (
            ("old", 1, 100, "he"),
            ("older", 3, 50, "he"),
            ("known", 5, 50, "he"),
            ("marked-since", 2, 900, "he"),
            ("russian", 1, 50, "ru"),
        ):
            db.execute(
                "INSERT INTO word (person, language, lemma, status, seen) VALUES (?, ?, ?, ?, ?)",
                (person.id, language, lemma, status, seen),
            )
    assert store.due_a_look(person.id, "he", since=500) == 2
    assert store.due_a_look(person.id, "he") == 3
    assert store.due_a_look(person.id, "ru", since=500) == 1
