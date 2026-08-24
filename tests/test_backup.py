"""Copies of the one file that cannot be rebuilt, and putting one back.

Readers can be rendered again, the cache is regenerable, models are downloads. Accounts,
the words somebody spent months keeping, their phrases and the spend ledger exist in one
SQLite file and nowhere else.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from targum.accounts import Store
from targum.backup import check, restore, snapshot, sweep


def kept(store: Store, words: int) -> int:
    store.start_sign_in("reader@example.com")
    person = store.person_by_email("reader@example.com")
    assert person is not None
    with store.write() as db:
        for n in range(words):
            db.execute(
                "INSERT INTO word (person, language, lemma, status, seen) VALUES (?,?,?,?,?)",
                (person.id, "he", f"w{n}", 3, n),
            )
    return int(store.db.execute("SELECT COUNT(*) FROM word").fetchone()[0])


def test_a_snapshot_holds_what_a_plain_copy_would_lose(tmp_path: Path) -> None:
    """The trap this exists to avoid.

    In WAL mode the recent writes live in `targum.db-wal`, not in `targum.db`. On the
    machine this was written on the log was 1 MB against an 86 KB database — so
    `cp targum.db` saved a file that opens, passes an integrity check, and is missing
    the most recent account and word.
    """
    live = tmp_path / "targum.db"
    store = Store(live)
    words = kept(store, 30)

    naive = tmp_path / "naive.db"
    shutil.copy2(live, naive)  # what a backup script would do by mistake
    taken = snapshot(live, tmp_path / "backups")

    def count(path: Path) -> int:
        """How many words a copy actually holds. -1 when it holds nothing usable."""
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            return int(db.execute("SELECT COUNT(*) FROM word").fetchone()[0])
        except sqlite3.OperationalError:
            return -1
        finally:
            db.close()

    assert count(taken) == words, "the snapshot must hold everything"
    # Starker than losing a row: the schema itself was still in the log, so the plain
    # copy has no tables at all — a file that exists, opens, and contains nothing.
    assert count(naive) < words, "if a plain copy were enough this module would not exist"
    assert check(naive) != "", "and the check has to catch it"


def test_a_snapshot_is_checked_as_it_is_taken(tmp_path: Path) -> None:
    """A backup nobody has opened is a rumour."""
    live = tmp_path / "targum.db"
    kept(Store(live), 5)
    assert check(snapshot(live, tmp_path / "backups")) == ""

    empty = tmp_path / "nothing.db"
    empty.write_bytes(b"")
    assert check(empty) != ""

    rubbish = tmp_path / "rubbish.db"
    rubbish.write_bytes(b"this is not a database at all, not even a little bit")
    assert check(rubbish) != ""

    # Valid SQLite, but not targum's: an integrity check alone would pass this.
    hollow = tmp_path / "hollow.db"
    empty_db = sqlite3.connect(hollow)
    empty_db.execute("CREATE TABLE unrelated (x)")
    empty_db.commit()
    empty_db.close()
    assert "no person" in check(hollow)


def test_restoring_brings_the_words_back(tmp_path: Path) -> None:
    """Run, not assumed. The plan asks for a restore that has actually happened once."""
    live = tmp_path / "targum.db"
    store = Store(live)
    words = kept(store, 40)
    taken = snapshot(live, tmp_path / "backups")

    with store.write() as db:
        for table in ("word", "session", "link", "person"):
            db.execute(f"DELETE FROM {table}")
    store.close()
    assert Store(live).db.execute("SELECT COUNT(*) FROM word").fetchone()[0] == 0

    aside = restore(taken, live)
    back = Store(live)
    assert back.db.execute("SELECT COUNT(*) FROM word").fetchone()[0] == words
    assert back.person_by_email("reader@example.com") is not None
    assert aside.is_file(), "what was replaced must be kept, not deleted"


def test_a_bad_backup_is_refused_rather_than_restored(tmp_path: Path) -> None:
    """Restoring rubbish over a working database is the worst outcome available."""
    live = tmp_path / "targum.db"
    kept(Store(live), 7)
    rubbish = tmp_path / "rubbish.db"
    rubbish.write_bytes(b"not a database")

    with pytest.raises(ValueError):
        restore(rubbish, live)
    assert Store(live).db.execute("SELECT COUNT(*) FROM word").fetchone()[0] == 7


def test_old_copies_are_dropped_and_the_newest_kept(tmp_path: Path) -> None:
    from datetime import datetime, timedelta

    live = tmp_path / "targum.db"
    kept(Store(live), 3)
    into = tmp_path / "backups"
    when = datetime(2026, 8, 1, 3, 0)
    for day in range(6):
        snapshot(live, into, now=when + timedelta(days=day))

    dropped = sweep(into, keep=4)
    left = sorted(p.name for p in into.glob("targum-*.db"))
    assert len(dropped) == 2 and len(left) == 4
    assert left[-1].endswith("20260806-030000.db"), "the newest must survive"


def test_a_missing_database_is_an_error_not_an_empty_backup(tmp_path: Path) -> None:
    """A backup command that quietly writes nothing is worse than one that fails."""
    with pytest.raises(FileNotFoundError):
        snapshot(tmp_path / "nothing-here.db", tmp_path / "backups")
