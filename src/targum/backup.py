"""Copies of the one file that cannot be rebuilt.

Everything else targum keeps can be made again. Readers are rendered from artifacts on
disk; the cache is paid work but the readers hold the same translations; models are
downloads. The database is the exception: accounts, the words somebody has spent months
keeping, their phrases, the job queue and the spend ledger exist nowhere else.

**A copy of the file is not a backup.** In WAL mode the recent writes live in
`targum.db-wal`, not in `targum.db` — on this machine the log was 1 MB against an 86 KB
database, so `cp targum.db` would have saved almost nothing and looked like it worked.
SQLite's own backup API reads a consistent snapshot of a live database, and that is what
this uses.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

STAMP = "%Y%m%d-%H%M%S"
KEEP = 14


def snapshot(store: Path, into: Path, now: datetime | None = None) -> Path:
    """A consistent copy of the database, taken while it is in use.

    Returns the file written. Raises if the source is missing, because a backup command
    that quietly writes nothing is worse than one that fails.
    """
    if not store.is_file():
        raise FileNotFoundError(store)
    into.mkdir(parents=True, exist_ok=True)
    stamped = (now or datetime.now()).strftime(STAMP)
    target = into / f"targum-{stamped}.db"

    source = sqlite3.connect(store)
    try:
        copy = sqlite3.connect(target)
        try:
            # Not a file copy: this reads through SQLite, so the write-ahead log is
            # included and the result is a database rather than a torn page of one.
            source.backup(copy)
        finally:
            copy.close()
    finally:
        source.close()
    return target


def check(path: Path) -> str:
    """What is wrong with this backup, or "" if nothing is.

    Run on every snapshot as it is taken. A backup nobody has opened is a rumour.
    """
    if not path.is_file() or path.stat().st_size == 0:
        return "the file is missing or empty"
    try:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as error:
        return str(error)
    try:
        answer = db.execute("PRAGMA integrity_check").fetchone()
        if not answer or answer[0] != "ok":
            return f"integrity check said {answer[0] if answer else 'nothing'}"
        # The tables have to be there, not merely the file. An empty but valid database
        # passes an integrity check and restores nothing.
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = {"person", "word", "phrase"} - tables
        if missing:
            return f"no {', '.join(sorted(missing))} table"
    except sqlite3.Error as error:
        return str(error)
    finally:
        db.close()
    return ""


def sweep(into: Path, keep: int = KEEP) -> list[Path]:
    """Drop the oldest, keep the newest `keep`. Returns what was removed."""
    found = sorted(into.glob("targum-*.db"))
    gone = found[: max(0, len(found) - keep)]
    for path in gone:
        path.unlink(missing_ok=True)
    return gone


def restore(backup: Path, store: Path) -> Path:
    """Put a backup back, keeping what is there now.

    The displaced database is moved aside rather than deleted, because restoring the
    wrong file is a thing people do at four in the morning. Returns where it went.
    """
    problem = check(backup)
    if problem:
        raise ValueError(f"That backup is not usable: {problem}")

    store.parent.mkdir(parents=True, exist_ok=True)
    aside = store.with_name(f"{store.name}.replaced-{datetime.now().strftime(STAMP)}")
    if store.is_file():
        shutil.move(str(store), aside)
    # The log and shared-memory files belong to the database being replaced. Left
    # behind, SQLite would try to recover the old one's writes into the new one.
    for suffix in ("-wal", "-shm"):
        store.with_name(store.name + suffix).unlink(missing_ok=True)
    shutil.copy2(backup, store)
    return aside
