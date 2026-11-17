"""Catalogue rows the box writes for itself, in a file of its own under /var/lib/targum.

The catalogue file is curated data that arrives from a laptop with every deploy, and on
the box it is `/etc/targum/catalogue.json`, root's, which the service may read and must
never write (`ProtectSystem=strict`). So what the box adds to the shelf by itself — a find
that joins the library (`promote.join_find`), a proposal accepted in the back office
(`promote.accept`) — goes in a file beside what it shelves, and `catalogue.everything`
joins it on the way the weekly's issues are: a new row appears without a deploy, and the
next deploy's catalogue never writes over it (targum-internal#738).

One shape for every such file: `{"entries": [...]}` and whatever else its owner keeps
beside them, read again only when it changed, and changed only under a lock, re-read
first, so two writers never undo each other.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .paths import write_atomic

if TYPE_CHECKING:
    from .catalogue import Entry


@contextmanager
def locked(path: Path, *, wait: bool = True) -> Iterator[bool]:
    """An exclusive lock on `path`, across processes: True where it was taken. With
    `wait=False`, False at once where somebody else holds it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class ShelfFile:
    """One file of rows, found afresh on every call (`locate`), so a test or a second
    Library pointing it elsewhere is read where it points."""

    def __init__(self, locate: Callable[[], Path]) -> None:
        self._locate = locate
        self._held: dict[Path, tuple[tuple[int, int, int], list[Entry], list[dict[str, Any]]]] = {}

    def path(self) -> Path:
        return self._locate()

    def read(self) -> dict[str, Any]:
        """The whole file, or an empty one where there is none or it cannot be read."""
        path = self.path()
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if not isinstance(loaded, dict):
            loaded = {}
        if not isinstance(loaded.get("entries"), list):
            loaded["entries"] = []
        return loaded

    def _loaded(self) -> tuple[list[Entry], list[dict[str, Any]]]:
        from .catalogue import _entry

        path = self.path()
        try:
            stat = path.stat()
        except OSError:
            return [], []
        # The inode too: every write is a rename onto the path (`write_atomic`), so a new
        # file of the same size inside one clock tick is still a new file.
        stamp = (stat.st_ino, stat.st_mtime_ns, stat.st_size)
        held = self._held.get(path)
        if held is not None and held[0] == stamp:
            return held[1], held[2]
        entries: list[Entry] = []
        rows: list[dict[str, Any]] = []
        for raw in self.read()["entries"]:
            try:
                entries.append(_entry(raw))
            except (KeyError, ValueError, TypeError):
                continue
            rows.append(raw)
        self._held[path] = (stamp, entries, rows)
        return entries, rows

    def entries(self) -> list[Entry]:
        """Every row, as a catalogue entry; a row the loader cannot read is left out."""
        return list(self._loaded()[0])

    def rows(self) -> list[dict[str, Any]]:
        """Every readable row, as written."""
        return [dict(row) for row in self._loaded()[1]]

    def update(self, change: Callable[[dict[str, Any]], None]) -> None:
        """Read the file afresh, change it and write it, under its lock."""
        path = self.path()
        with locked(path.with_name(f".{path.name}.lock")):
            held = self.read()
            change(held)
            path.parent.mkdir(parents=True, exist_ok=True)
            write_atomic(path, json.dumps(held, ensure_ascii=False, indent=1) + "\n")

    def merge(self, entry: dict[str, Any]) -> None:
        """One row in, field by field over a row of the same id, as the catalogue file is
        merged (`promote.merge_into_catalogue`): what somebody wrote later survives, and
        a row arriving now is dated now."""

        def change(held: dict[str, Any]) -> None:
            rows: list[dict[str, Any]] = held["entries"]
            for index, row in enumerate(rows):
                if row.get("id") == entry["id"]:
                    kept = {k: v for k, v in entry.items() if v not in ("", 0, [])}
                    rows[index] = {**row, **kept}
                    return
            rows.append({"added": date.today().isoformat(), **entry})

        self.update(change)

    def remove(self, entry_id: str) -> bool:
        """Take one row out; whether it was there."""
        gone: list[bool] = []

        def change(held: dict[str, Any]) -> None:
            rows: list[dict[str, Any]] = held["entries"]
            kept = [row for row in rows if row.get("id") != entry_id]
            gone.append(len(kept) != len(rows))
            held["entries"] = kept

        self.update(change)
        return gone[0]


def shared_dir() -> Path:
    """The shared shelf, as `Library` names it in the environment (`TARGUM_SHARED_DIR`),
    the way the weekly's root is named, else the working directory's."""
    named = os.environ.get("TARGUM_SHARED_DIR", "").strip()
    if named:
        return Path(named).expanduser()
    return Path.cwd() / "targum-out" / "shared"


#: What joined the shelf on the box: finds and accepted proposals, beside their copies.
JOINED = ShelfFile(lambda: shared_dir() / "joined.json")
