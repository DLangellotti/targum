"""The two records "How you got here" counts its words from (targum-internal#603).

design.md §12, "How you got here: two figures, the days active and the words of the
period" (2026-10-30): `word.known_at`, the day a word became known, and `met`, the first
finished section each word was met in. Both start on the day the code first runs and are
never filled from before it. The page half is `test_progress_js.py`.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import test_serve
from test_reading_line import built, word
from test_serve import Postbox, call, sign_in

from targum.accounts import Store

KNOWN = 9

served = test_serve.served
postbox = test_serve.postbox


def _store(tmp_path: Path) -> tuple[Store, Any]:
    store = Store(tmp_path / "db")
    person, _ = store.finish_sign_in(store.start_sign_in("r@example.com"))  # type: ignore[misc]
    return store, person


def _known_at(store: Store, person: Any, lemma: str) -> int | None:
    row = store.db.execute(
        "SELECT known_at FROM word WHERE person = ? AND lemma = ?", (person.id, lemma)
    ).fetchone()
    return None if row["known_at"] is None else int(row["known_at"])


def _word(lemma: str, status: int, seen: int, **more: Any) -> dict[str, Any]:
    return {"language": "he", "lemma": lemma, "status": status, "at": seen, "seen": seen, **more}


def test_known_at_is_the_push_that_made_a_word_known_and_goes_when_it_leaves(
    tmp_path: Path,
) -> None:
    store, person = _store(tmp_path)
    began = store.began()
    store.push(person, {"words": [_word("ספר", 2, began + 10)]})
    assert _known_at(store, person, "ספר") is None
    store.push(person, {"words": [_word("ספר", KNOWN, began + 20)]})
    assert _known_at(store, person, "ספר") == began + 20
    # A later edit of a known word keeps the day it became known, whatever the page sent.
    store.push(person, {"words": [_word("ספר", KNOWN, began + 30, known_at=began + 999)]})
    assert _known_at(store, person, "ספר") == began + 20
    # Out of known, and it has none.
    store.push(person, {"words": [_word("ספר", 3, began + 40)]})
    assert _known_at(store, person, "ספר") is None
    # And a word marked known straight away is known from that push.
    store.push(person, {"words": [_word("בית", KNOWN, began + 50)]})
    assert _known_at(store, person, "בית") == began + 50
    # It travels with the word, to the next device.
    pulled = {row["lemma"]: row for row in store.pull(person)["words"]}
    assert pulled["בית"]["known_at"] == began + 50


def test_known_at_is_never_guessed_for_a_word_known_before_the_record(tmp_path: Path) -> None:
    """A browser signing in with a list it kept before the record began: its words were
    marked before anything was counted, so they have no date rather than `seen`'s."""
    store, person = _store(tmp_path)
    before = store.began() - 86_400_000
    store.push(person, {"words": [_word("ים", KNOWN, before)]})
    assert _known_at(store, person, "ים") is None
    store.push(person, {"words": [_word("ים", KNOWN, store.began() + 5)]})
    assert _known_at(store, person, "ים") is None, "still known, still undated"


def test_an_older_database_gains_the_column_with_every_row_null(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    Store(path)
    raw = sqlite3.connect(path)
    raw.execute("DROP TABLE word")
    raw.execute(
        "CREATE TABLE word (person INTEGER NOT NULL, language TEXT NOT NULL, lemma TEXT NOT"
        " NULL, surface TEXT NOT NULL DEFAULT '', status INTEGER, meaning TEXT NOT NULL"
        " DEFAULT '', note TEXT NOT NULL DEFAULT '', band TEXT NOT NULL DEFAULT '', at"
        " INTEGER NOT NULL DEFAULT 0, seen INTEGER NOT NULL DEFAULT 0, gone INTEGER NOT NULL"
        " DEFAULT 0, revision INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (person, language,"
        " lemma))"
    )
    raw.execute(
        "INSERT INTO word (person, language, lemma, status, seen) VALUES (1, 'he', 'x', 9, 5)"
    )
    raw.commit()
    raw.close()
    store = Store(path)
    row = store.db.execute("SELECT known_at FROM word WHERE lemma = 'x'").fetchone()
    assert row["known_at"] is None


def test_the_record_begins_once_and_does_not_move(tmp_path: Path) -> None:
    first = Store(tmp_path / "db").began()
    time.sleep(0.01)
    assert Store(tmp_path / "db").began() == first > 0


def test_the_first_meeting_keeps_the_earliest_finish(tmp_path: Path) -> None:
    store, person = _store(tmp_path)
    store.keep_met(person, "he", {"ספר": 200, "ים": 300})
    store.keep_met(person, "he", {"ספר": 100, "ים": 400, "בית": 500})
    rows = dict(
        store.db.execute("SELECT lemma, at FROM met WHERE person = ?", (person.id,)).fetchall()
    )
    assert rows == {"ספר": 100, "ים": 300, "בית": 500}
    assert store.everything(person)["met"][0] == {"language": "he", "lemma": "ספר", "at": 100}


def test_the_words_of_a_day_count_from_the_record_and_leave_names_out(tmp_path: Path) -> None:
    store, person = _store(tmp_path)
    began = store.began()
    noon = began + 1000
    store.push(
        person,
        {
            "words": [
                _word("ספר", 2, noon),
                _word("ים", KNOWN, noon + 1),
                _word("דוד", KNOWN, noon + 2, band="name"),
                _word("לא", 0, noon + 3),
            ]
        },
    )
    store.keep_met(person, "he", {"ספר": noon, "ים": noon, "ישן": began - 10})
    days = store.words_by_day(person.id)
    assert len(days) == 1
    assert {k: days[0][k] for k in ("language", "met", "saved", "known")} == {
        "language": "he",
        "met": 2,
        "saved": 2,
        "known": 1,
    }


def test_a_finished_section_keeps_its_first_meetings_and_the_page_is_answered_them(
    served: tuple[int, str, Path], postbox: Postbox
) -> None:
    """Through `/sync`, the door the page uses: a section finished before the record is
    read once when the first one after it is, so a word met then is not new now."""
    port, token, out = served
    built(
        out / "shared" / "book",
        {
            1: [[word("ספר"), word("בית")] * 10],
            2: [[word("ספר"), word("ים"), word("שמש")] * 10],
        },
    )
    cookie = sign_in(port, postbox)
    now = int(time.time() * 1000)
    long_ago = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp() * 1000)

    def sync(**changes: object) -> None:
        status, answer, _ = call(port, "POST", f"/sync?k={token}", changes, cookie=cookie)
        assert status == 200 and answer["signedIn"], answer

    # Section 1 finished long ago, and pushed with section 2 finished now.
    sync(
        words=[{"language": "he", "lemma": "ספר", "status": KNOWN, "at": now, "seen": now}],
        sections=[
            {"hash": "book", "section": "1", "at": long_ago, "seen": long_ago},
        ],
    )
    sync(sections=[{"hash": "book", "section": "2", "at": now, "seen": now}])
    status, said, _ = call(port, "GET", f"/account/totals?k={token}&tz=UTC", cookie=cookie)
    assert status == 200, said
    words = said["words"]
    assert words["began"] > 0
    he = [day for day in words["days"] if day["language"] == "he"]
    # ספר and בית were met in section 1, long ago; ים and שמש are new now.
    assert sum(day["met"] for day in he) == 2
    assert sum(day["known"] for day in he) == 1
    assert sum(day["saved"] for day in he) == 1
