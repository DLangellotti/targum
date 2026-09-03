"""Copies of the two things that cannot be rebuilt.

Readers are rendered from artifacts on disk and models are downloads, so neither is
backed up. Two things are not like that:

**The database.** Accounts, the words somebody has spent months keeping, their phrases,
the days they read on, the job queue and the spend ledger exist nowhere else. It is
copied whole rather than table by table, on purpose: the progress page is drawn from
these same records and keeps nothing of its own, so a copy of the file is a copy of
everything that page will ever count, including a table nobody has added yet.

**The translation cache.** This module used to say the cache did not need copying,
because "the readers hold the same translations" — which was true of a tool one person
ran on their own laptop, and is false hosted. On a shared box the cache is what makes a
public text free for the *second* reader and every reader after: `Build.plan()` looks
there before pricing, so a cache hit is quoted at nothing. Lose it and everyone pays
again for work already bought. It is paid inventory, not scratch, whatever
`paths.cache_dir()` says about being safe to delete.

**A copy of the database file is not a backup.** In WAL mode the recent writes live in
`targum.db-wal`, not in `targum.db` — on this machine the log was 1 MB against an 86 KB
database, so `cp targum.db` would have saved almost nothing and looked like it worked.
SQLite's own backup API reads a consistent snapshot of a live database, and that is what
this uses. The cache is ordinary JSON and needs no such care, only excluding the models
directory, which is gigabytes of things that can simply be downloaded again.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import zipfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

STAMP = "%Y%m%d-%H%M%S"
KEEP = 14

# How long one file gets to leave. The database is tens of kilobytes and the cache
# archive is megabytes; a copy still running after this is a network that is not going
# to finish, and a nightly job that hangs is a nightly job that stops running.
SHIP_TIMEOUT = 600.0

# Downloaded weights, not paid work. Stanza and LaBSE together are gigabytes, and
# copying them nightly would bury the thing actually worth keeping.
NOT_PAID_FOR = "models"


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


def archive_cache(root: Path, into: Path, now: datetime | None = None) -> Path | None:
    """Zip the paid half of the cache. Returns the file, or None if there is nothing yet.

    One file rather than a directory tree, because the copy has to leave the box and
    `rclone` moving one archive beats it walking thousands of small JSON files.

    The models directory is excluded deliberately — gigabytes of downloads that would
    bury the megabytes that were actually paid for.
    """
    if not root.is_dir():
        return None
    paid = sorted(
        path for path in root.rglob("*.json") if NOT_PAID_FOR not in path.relative_to(root).parts
    )
    if not paid:
        return None

    into.mkdir(parents=True, exist_ok=True)
    stamped = (now or datetime.now()).strftime(STAMP)
    target = into / f"cache-{stamped}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in paid:
            bundle.write(path, path.relative_to(root).as_posix())
    return target


def archive_weekly(root: Path, into: Path, now: datetime | None = None) -> Path | None:
    """Zip the weekly. Returns the file, or None if no issue has been made yet.

    The cache can be re-bought and the readers can be rebuilt from it. An issue cannot
    be either: it is the output of a model on a particular morning, from feeds that have
    since moved on, and asking the same model the same question tomorrow does not return
    it. Losing a week of the weekly loses that week permanently.

    The composed markdown and the index only — not the built readers under it, which are
    rebuilt from the markdown for nothing. Kilobytes, so it rides with the nightly copy
    rather than waiting for somebody to think of it.
    """
    if not root.is_dir():
        return None
    kept = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".md", ".json"} and "reader" not in path.parts
    )
    if not kept:
        return None

    into.mkdir(parents=True, exist_ok=True)
    stamped = (now or datetime.now()).strftime(STAMP)
    target = into / f"weekly-{stamped}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in kept:
            bundle.write(path, path.relative_to(root).as_posix())
    return target


# The one file in a weekly archive that is a list rather than a thing. Unpacking it
# the way everything else is unpacked replaces the list, which is why it is merged.
WEEKLY_INDEX = "index.json"


def restore_weekly(archive: Path, root: Path) -> int:
    """Unpack a weekly archive over the weekly. Returns how many files were written.

    Additive, like the cache: an issue that is already there is the same issue, and one
    published since the archive was taken should survive being restored onto.

    `index.json` is the exception that has to be handled rather than extracted. Every
    other member is one issue's own file, so unpacking it over an existing copy writes
    the same bytes back. The index is the list of *all* issues, so unpacking it replaces
    what is standing with what was true on the night of the copy -- and a week published
    since then keeps its files on disk while disappearing from the product entirely.
    That is this month's issue vanishing during the restore run to save last month's,
    which is the failure the whole archive exists to prevent. So the two lists are
    merged and what is standing wins, because it is the more recent account of the same
    issue: withdrawing an issue and then restoring must not put it back on sale.
    """
    problem = check_archive(archive)
    if problem:
        raise ValueError(f"That weekly archive is not usable: {problem}")
    root.mkdir(parents=True, exist_ok=True)
    standing = _issues_in(root / WEEKLY_INDEX)
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        bundle.extractall(root)
    if standing:
        _merge_issues(root / WEEKLY_INDEX, standing)
    return len(names)


def _issues_in(path: Path) -> dict[str, object]:
    """The issues in an index file, by id -- empty if there is no readable index.

    Read as plain JSON rather than through the weekly models on purpose: a restore must
    not fail because the standing index carries a field this version has never heard of.
    Unreadable counts as absent, which is the right reading -- an index nobody can parse
    is what somebody is restoring to get away from, and it should not veto the archive.
    """
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    issues = loaded.get("issues")
    if not isinstance(issues, list):
        return {}
    return {
        one["id"]: one for one in issues if isinstance(one, dict) and isinstance(one.get("id"), str)
    }


def _merge_issues(path: Path, standing: dict[str, object]) -> None:
    """Put the issues that were standing back into a freshly unpacked index."""
    restored = _issues_in(path)
    together = {**restored, **standing}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(loaded, dict):
        return
    # Sorted by id, which for "2026-w36" is also date order.
    loaded["issues"] = [together[key] for key in sorted(together)]
    path.write_text(json.dumps(loaded, ensure_ascii=False, indent=2), encoding="utf-8")


def check_archive(path: Path) -> str:
    """What is wrong with this cache archive, or "" if nothing is.

    Same rule as the database: opened and read as it is taken. A zip that was written
    while something was being deleted underneath it is a zip that fails on the night it
    is needed.
    """
    if not path.is_file() or path.stat().st_size == 0:
        return "the file is missing or empty"
    try:
        with zipfile.ZipFile(path) as bundle:
            broken = bundle.testzip()
            if broken is not None:
                return f"{broken} is corrupt"
            names = bundle.namelist()
            if not names:
                return "it holds nothing"
            if any(name.split("/")[0] == NOT_PAID_FOR for name in names):
                return f"it holds the {NOT_PAID_FOR} directory, which is downloads"
    except (zipfile.BadZipFile, OSError) as error:
        return str(error)
    return ""


def restore_cache(archive: Path, root: Path) -> int:
    """Unpack a cache archive over the cache. Returns how many entries were written.

    Deliberately additive rather than a replacement: the cache is content-addressed, so
    an entry that is already there is the same entry, and anything bought since the
    archive was taken should survive being restored onto.
    """
    problem = check_archive(archive)
    if problem:
        raise ValueError(f"That cache archive is not usable: {problem}")
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        bundle.extractall(root)
    return len(names)


def check(path: Path) -> str:
    """What is wrong with this database backup, or "" if nothing is.

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


class NotShipped(RuntimeError):
    """A copy did not leave the box, and nobody would otherwise have known."""


def _rclone(*args: str, timeout: float = SHIP_TIMEOUT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["rclone", *args], capture_output=True, text=True, timeout=timeout, check=False
    )


def ship(
    files: Sequence[Path],
    to: str,
    *,
    run: object = None,
    timeout: float = SHIP_TIMEOUT,
) -> list[str]:
    """Send finished copies somewhere that is not this disk. Returns what arrived.

    A nightly backup written beside the database it copies survives the mistakes and
    none of the disasters: `provision.sh` says so about itself, and it has been true
    since the box went up.

    Through `rclone`, and only `rclone`, because it is one binary that speaks S3, B2,
    R2, SFTP and a dozen others — so the destination is a decision that can be changed
    without changing this, and none of it is written down here. **Encryption belongs in
    the remote, not here.** A backup holds addresses and every word somebody has kept;
    an rclone `crypt` remote in front of the bucket is where that is handled, and this
    passes the files to whatever it is pointed at without opinion.

    Verified rather than assumed: it asks the destination what it now holds and checks
    the size against what was sent. A copy command that exits zero having written
    nothing is the failure this whole function exists to notice.
    """
    if not files:
        return []
    runner = run or _rclone
    if run is None and shutil.which("rclone") is None:
        raise NotShipped("rclone is not installed. `apt-get install rclone`, then configure it.")

    for path in files:
        done = runner(  # type: ignore[operator]
            "copyto", str(path), f"{to.rstrip('/')}/{path.name}", timeout=timeout
        )
        if done.returncode != 0:
            raise NotShipped(f"{path.name} did not leave: {(done.stderr or '').strip()[:200]}")

    listed = runner("lsjson", to, timeout=timeout)  # type: ignore[operator]
    if listed.returncode != 0:
        raise NotShipped(f"Could not read back {to}: {(listed.stderr or '').strip()[:200]}")
    try:
        there = {row["Name"]: int(row.get("Size", -1)) for row in json.loads(listed.stdout or "[]")}
    except (json.JSONDecodeError, TypeError, KeyError) as error:
        raise NotShipped(f"{to} answered with something unreadable: {error}") from error

    arrived: list[str] = []
    for path in files:
        size = path.stat().st_size
        if there.get(path.name) != size:
            raise NotShipped(
                f"{path.name} is {size} bytes here and {there.get(path.name, 'missing')} at {to}."
            )
        arrived.append(path.name)
    return arrived


def destination(given: str = "") -> str:
    """Where copies go, from the flag or the environment. Empty means nowhere."""
    return (given or os.environ.get("TARGUM_BACKUP_TO", "")).strip()


def sweep(into: Path, keep: int = KEEP) -> list[Path]:
    """Drop the oldest, keep the newest `keep`. Returns what was removed.

    Counted per kind, not across both: databases and cache archives are taken together
    but a run that produced no cache must not let stale databases pile up, nor let one
    kind push the other out.
    """
    gone: list[Path] = []
    for pattern in ("targum-*.db", "cache-*.zip"):
        found = sorted(into.glob(pattern))
        for path in found[: max(0, len(found) - keep)]:
            path.unlink(missing_ok=True)
            gone.append(path)
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
