"""Copies of the two things that cannot be rebuilt, and putting them back.

Readers can be rendered again and models are downloads. Two things cannot: the SQLite
file holding accounts, the words somebody spent months keeping, their phrases and the
spend ledger — and the translation cache, which on a shared box is what makes a public
text free for the second reader and every reader after.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from targum.accounts import Store
from targum.backup import (
    archive_cache,
    check,
    check_archive,
    restore,
    restore_cache,
    snapshot,
    sweep,
)


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


# -- the cache, which is the other thing that cannot be rebuilt ---------------


def _cache(root: Path, entries: int = 3, models_mb: int = 2) -> Path:
    """A cache shaped like a real one: paid JSON, plus a fat models directory."""
    for stage, count in (("translate", entries), ("gloss", entries)):
        for index in range(count):
            path = root / stage / f"{index:02d}" / f"{index}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"segment": f"text {index}"}), encoding="utf-8")
    weights = root / "models" / "stanza" / "he.json"
    weights.parent.mkdir(parents=True, exist_ok=True)
    weights.write_text("x" * (models_mb * 1024 * 1024), encoding="utf-8")
    return root


def test_the_archive_leaves_the_models_behind(tmp_path: Path) -> None:
    """The one that matters, measured on the real machine: 1.1 MB against 5,026 MB.

    Models are downloads. Copying them nightly would bury the megabytes that were
    actually paid for under gigabytes that can be fetched again.
    """
    root = _cache(tmp_path / "cache")
    made = archive_cache(root, tmp_path / "out")
    assert made is not None
    with zipfile.ZipFile(made) as bundle:
        names = bundle.namelist()
    assert names, "the archive should hold the paid entries"
    assert not any(name.split("/")[0] == "models" for name in names)
    assert made.stat().st_size < 1024 * 1024, "a models directory got in"


def test_nothing_bought_means_nothing_to_copy(tmp_path: Path) -> None:
    """Not an error: a fresh install has no cache, and cron runs nightly regardless."""
    assert archive_cache(tmp_path / "missing", tmp_path / "out") is None
    empty = tmp_path / "cache"
    (empty / "models").mkdir(parents=True)
    assert archive_cache(empty, tmp_path / "out") is None, "models alone are not paid work"


def test_a_cache_archive_is_checked_as_it_is_taken(tmp_path: Path) -> None:
    made = archive_cache(_cache(tmp_path / "cache"), tmp_path / "out")
    assert made is not None
    assert check_archive(made) == ""

    assert "missing or empty" in check_archive(tmp_path / "no-such.zip")

    torn = tmp_path / "torn.zip"
    torn.write_bytes(b"this is not a zip file")
    assert check_archive(torn) != ""

    hollow = tmp_path / "hollow.zip"
    with zipfile.ZipFile(hollow, "w"):
        pass
    assert "holds nothing" in check_archive(hollow)


def test_an_archive_carrying_models_is_refused(tmp_path: Path) -> None:
    """Belt and braces on the size rule: if models ever get in, say so rather than ship."""
    wrong = tmp_path / "wrong.zip"
    with zipfile.ZipFile(wrong, "w") as bundle:
        bundle.writestr("models/stanza/he.json", "weights")
    assert "downloads" in check_archive(wrong)


def test_restoring_the_cache_adds_rather_than_replaces(tmp_path: Path) -> None:
    """The cache is content-addressed, so anything bought since the copy must survive it."""
    root = _cache(tmp_path / "cache", entries=2)
    made = archive_cache(root, tmp_path / "out")
    assert made is not None

    later = root / "translate" / "zz" / "bought-later.json"
    later.parent.mkdir(parents=True, exist_ok=True)
    later.write_text('{"segment": "paid for after the backup"}', encoding="utf-8")

    written = restore_cache(made, root)
    assert written > 0
    assert later.is_file(), "restoring must not throw away work bought since"


def test_a_broken_archive_is_never_unpacked(tmp_path: Path) -> None:
    torn = tmp_path / "torn.zip"
    torn.write_bytes(b"not a zip")
    with pytest.raises(ValueError):
        restore_cache(torn, tmp_path / "cache")


def test_the_two_kinds_are_swept_separately(tmp_path: Path) -> None:
    """A night that copied no cache must not let stale databases pile up, and neither
    kind may push the other out of the window."""
    into = tmp_path / "out"
    into.mkdir()
    for index in range(6):
        (into / f"targum-2026010{index}-000000.db").write_text("db", encoding="utf-8")
    for index in range(4):
        (into / f"cache-2026010{index}-000000.zip").write_text("zip", encoding="utf-8")

    sweep(into, keep=3)
    assert len(list(into.glob("targum-*.db"))) == 3
    assert len(list(into.glob("cache-*.zip"))) == 3, "the databases must not evict the caches"


# -- getting the copies off the disk they are a copy of -------------------------


class FakeRclone:
    """rclone, without rclone. Records what it was asked and answers as it would."""

    def __init__(self, *, fail_on: str = "", drop: str = "", short: str = "") -> None:
        self.calls: list[tuple[str, ...]] = []
        self.there: dict[str, int] = {}
        self.fail_on = fail_on
        self.drop = drop
        self.short = short

    def __call__(self, *args: str, timeout: float = 0.0) -> Any:
        self.calls.append(args)
        if args[0] == "copyto":
            source = Path(args[1])
            if self.fail_on and self.fail_on in source.name:
                return SimpleNamespace(returncode=1, stdout="", stderr="quota exceeded")
            if self.drop and self.drop in source.name:
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            size = source.stat().st_size
            if self.short and self.short in source.name:
                size = max(0, size - 1)
            self.there[source.name] = size
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[0] == "lsjson":
            rows = [{"Name": name, "Size": size} for name, size in self.there.items()]
            return SimpleNamespace(returncode=0, stdout=json.dumps(rows), stderr="")
        raise AssertionError(f"unexpected rclone call: {args}")


def copies(tmp_path: Path) -> list[Path]:
    one = tmp_path / "targum-20260826-040000.db"
    one.write_bytes(b"a database" * 40)
    two = tmp_path / "cache-20260826-040000.zip"
    two.write_bytes(b"a cache" * 90)
    return [one, two]


def test_copies_that_leave_are_named_back(tmp_path: Path) -> None:
    from targum.backup import ship

    rclone = FakeRclone()
    arrived = ship(copies(tmp_path), "b2:targum/backups", run=rclone)

    assert arrived == ["targum-20260826-040000.db", "cache-20260826-040000.zip"]
    assert rclone.calls[0][:2] == ("copyto", str(tmp_path / "targum-20260826-040000.db"))
    assert rclone.calls[0][2] == "b2:targum/backups/targum-20260826-040000.db"
    assert rclone.calls[-1][0] == "lsjson", "it reads back what actually landed"


def test_a_copy_that_did_not_go_is_an_error(tmp_path: Path) -> None:
    from targum.backup import NotShipped, ship

    with pytest.raises(NotShipped) as raised:
        ship(copies(tmp_path), "b2:targum/backups", run=FakeRclone(fail_on="cache"))
    assert "cache-" in str(raised.value)
    assert "quota exceeded" in str(raised.value), "the reason comes from the tool, not from us"


def test_a_command_that_succeeded_without_writing_is_caught(tmp_path: Path) -> None:
    """The failure this whole function exists to notice. Exit zero having written
    nothing is what a misconfigured remote looks like from here."""
    from targum.backup import NotShipped, ship

    with pytest.raises(NotShipped) as raised:
        ship(copies(tmp_path), "b2:targum/backups", run=FakeRclone(drop="cache"))
    assert "missing" in str(raised.value)


def test_a_copy_that_arrived_truncated_is_caught(tmp_path: Path) -> None:
    from targum.backup import NotShipped, ship

    with pytest.raises(NotShipped) as raised:
        ship(copies(tmp_path), "b2:targum/backups", run=FakeRclone(short="targum-"))
    assert "bytes here" in str(raised.value)


def test_an_unreadable_listing_is_not_taken_as_success(tmp_path: Path) -> None:
    from targum.backup import NotShipped, ship

    class Gibberish(FakeRclone):
        def __call__(self, *args: str, timeout: float = 0.0) -> Any:
            if args[0] == "lsjson":
                return SimpleNamespace(returncode=0, stdout="<html>404</html>", stderr="")
            return super().__call__(*args, timeout=timeout)

    with pytest.raises(NotShipped):
        ship(copies(tmp_path), "b2:targum/backups", run=Gibberish())


def test_nothing_to_send_is_not_a_failure(tmp_path: Path) -> None:
    """A run that produced no cache archive still produced a database copy, and a night
    with neither is a different alarm than a night that could not reach the bucket."""
    from targum.backup import ship

    rclone = FakeRclone()
    assert ship([], "b2:targum/backups", run=rclone) == []
    assert rclone.calls == [], "it did not go and ask an empty question"


def test_where_copies_go_comes_from_the_flag_or_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from targum.backup import destination

    monkeypatch.delenv("TARGUM_BACKUP_TO", raising=False)
    assert destination() == "", "nowhere is a state, not a default"
    assert destination("b2:one") == "b2:one"

    monkeypatch.setenv("TARGUM_BACKUP_TO", "b2:two")
    assert destination() == "b2:two"
    assert destination("b2:one") == "b2:one", "the flag wins over the environment"
