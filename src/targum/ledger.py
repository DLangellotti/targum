"""The corpus ledger, first slice: the pointing a vocalizer made, as rows.

targum-internal#162 wants one store every stage writes and the renderer reads, so the
pipeline's exhaust can be asked "what do we know about this text" rather than only "was
this paid for already". `LEDGER.md` is the design. This is the first stage of it,
and it is deliberately small:

- **One stage, `vocalize`.** Its artefact is self-describing — the document it points,
  the tool and the model are fields of the value, not only parts of a hashed key — it
  costs nothing to remake, and both the Hebrew vowels and the Russian stress marks go
  through it, so one writer covers two tools.
- **Behind a flag, off by default.** `TARGUM_LEDGER` names the SQLite file. Unset, no
  file is opened and `Cache` behaves exactly as it did before this module existed.
- **Dual-write, never read.** `Cache.put` still writes its JSON first and the cache is
  still the only read path; the ledger is a second copy written beside it. A ledger
  that fails to write says so in the log and costs the build nothing.
- **Rows that rebuild the value exactly.** A value is recorded only if the rows read
  back as the same JSON, byte for byte; `rebuild` writes the cache back from rows, and
  `backfill` reads today's cache into rows, which is the migration path in small.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .cache import Cache

log = logging.getLogger(__name__)

#: The flag, and where the file is. Empty or unset is off.
ENV = "TARGUM_LEDGER"

#: The ledger's own schema, independent of `models.SCHEMA_VERSION`: the rows can change
#: shape without the cache key moving, which is the point of having rows.
LEDGER_SCHEMA = 1

#: The stages the ledger records. One, for now.
STAGES = frozenset({"vocalize"})

# Every field of a `Vocalization` as it is dumped. A value with any other key is refused
# rather than half-recorded: a field added to the model must be given a column first.
_FIELDS = (
    "schema_version",
    "document_hash",
    "language",
    "vocalizer",
    "model",
    "segments",
    "machine",
    "rejected",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- One pointing of one document by one tool. A rename of the tool is a new cache key,
-- so a new row; the old one stays (targum-internal#162, criterion 2).
CREATE TABLE IF NOT EXISTS vocalizations (
    id             INTEGER PRIMARY KEY,
    stage          TEXT NOT NULL,
    cache_key      TEXT NOT NULL UNIQUE,
    document_hash  TEXT NOT NULL,
    language       TEXT NOT NULL,
    tool           TEXT NOT NULL,
    tool_version   TEXT,
    schema_version INTEGER NOT NULL,
    written_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS vocalizations_by_text
    ON vocalizations (document_hash, tool, tool_version);
-- A segment of that pointing. `pointed` is null for a segment that is only listed as
-- rejected; each *_ord is the segment's place in its list, null when not in it.
CREATE TABLE IF NOT EXISTS pointings (
    vocalization_id INTEGER NOT NULL REFERENCES vocalizations (id),
    segment_id      TEXT NOT NULL,
    pointed         TEXT,
    segment_ord     INTEGER,
    machine_ord     INTEGER,
    rejected_ord    INTEGER,
    PRIMARY KEY (vocalization_id, segment_id)
);
"""


def path() -> Path | None:
    """The ledger file the environment names, or None: the flag is off."""
    raw = os.environ.get(ENV, "").strip()
    return Path(raw).expanduser() if raw else None


class Ledger:
    def __init__(self, file: Path) -> None:
        self.file = file

    def _connect(self) -> sqlite3.Connection:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        # Warm workers share the cache directory, so they share this file too.
        db = sqlite3.connect(self.file, timeout=30)
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(_SCHEMA)
        db.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema', ?)", (str(LEDGER_SCHEMA),)
        )
        return db

    def record(self, stage: str, key: str, value: Any) -> None:
        """Write one cache value as rows, replacing what that cache key held before.

        Raises ValueError, and writes nothing, for a value the rows could not give back
        exactly — an unknown field, a repeated segment, anything that would make the
        ledger a lossy copy of the cache it is meant to replace.
        """
        if stage not in STAGES:
            raise ValueError(f"the ledger does not record {stage!r} yet")
        header, rows = _to_rows(value)
        with closing(self._connect()) as db, db:
            db.execute(
                "DELETE FROM pointings WHERE vocalization_id IN "
                "(SELECT id FROM vocalizations WHERE cache_key = ?)",
                (key,),
            )
            db.execute("DELETE FROM vocalizations WHERE cache_key = ?", (key,))
            cursor = db.execute(
                "INSERT INTO vocalizations (stage, cache_key, document_hash, language, tool,"
                " tool_version, schema_version, written_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (stage, key, *header, datetime.now(UTC).isoformat(timespec="seconds")),
            )
            db.executemany(
                "INSERT INTO pointings (vocalization_id, segment_id, pointed, segment_ord,"
                " machine_ord, rejected_ord) VALUES (?, ?, ?, ?, ?, ?)",
                [(cursor.lastrowid, *row) for row in rows],
            )
            back = _read(db, key)
            if _bytes(back) != _bytes(value):
                # Leaving the `with db` block by an exception rolls the write back.
                raise ValueError("the rows do not give the value back exactly")

    def get(self, stage: str, key: str) -> dict[str, Any] | None:
        """The value a cache key holds, rebuilt from rows. None if there is no row."""
        if stage not in STAGES or not self.file.is_file():
            return None
        with closing(self._connect()) as db:
            return _read(db, key)

    def drop(self, stage: str, key: str) -> bool:
        """Forget one value — the cache's `drop`, so a wrong answer is not rebuilt."""
        if stage not in STAGES or not self.file.is_file():
            return False
        with closing(self._connect()) as db, db:
            db.execute(
                "DELETE FROM pointings WHERE vocalization_id IN "
                "(SELECT id FROM vocalizations WHERE cache_key = ?)",
                (key,),
            )
            return db.execute("DELETE FROM vocalizations WHERE cache_key = ?", (key,)).rowcount > 0

    def entries(self, stage: str) -> Iterator[tuple[str, dict[str, Any]]]:
        """Every (cache key, value) the ledger holds for a stage, oldest first."""
        if stage not in STAGES or not self.file.is_file():
            return
        with closing(self._connect()) as db:
            keys = [
                row[0]
                for row in db.execute(
                    "SELECT cache_key FROM vocalizations WHERE stage = ? ORDER BY id", (stage,)
                )
            ]
            for key in keys:
                value = _read(db, key)
                if value is not None:
                    yield key, value


def mirror_put(stage: str, key: str, value: Any) -> None:
    """`Cache.put`'s second write. Does nothing with the flag off or for another stage;
    never raises, because the cache already holds the value and the build goes on."""
    file = path()
    if file is None or stage not in STAGES:
        return
    try:
        Ledger(file).record(stage, key, value)
    except (sqlite3.Error, OSError, ValueError, TypeError) as error:
        log.warning("corpus ledger: %s %s not recorded: %s", stage, key[:12], error)


def mirror_drop(stage: str, key: str) -> None:
    """`Cache.drop`'s second hand, on the same terms as `mirror_put`."""
    file = path()
    if file is None or stage not in STAGES:
        return
    try:
        Ledger(file).drop(stage, key)
    except (sqlite3.Error, OSError) as error:
        log.warning("corpus ledger: %s %s not dropped: %s", stage, key[:12], error)


def rebuild(ledger: Ledger, cache: Cache, stage: str = "vocalize") -> int:
    """Write the cache back from rows. Returns how many entries were written."""
    written = 0
    for key, value in ledger.entries(stage):
        cache.put(stage, key, value)
        written += 1
    return written


def backfill(ledger: Ledger, cache: Cache, stage: str = "vocalize") -> tuple[int, int]:
    """Read today's cache into rows: the migration, for one stage. Reads the cache only.

    Returns (recorded, refused). A refused entry is one the rows could not give back
    exactly; it stays in the cache, which is still the read path, and is logged.
    """
    recorded = refused = 0
    folder = cache.root / stage
    if not folder.is_dir():
        return 0, 0
    for file in sorted(folder.glob("*/*.json")):
        try:
            value = json.loads(file.read_text(encoding="utf-8"))
            ledger.record(stage, file.stem, value)
        except (ValueError, TypeError) as error:
            log.warning("corpus ledger: %s not backfilled: %s", file.name, error)
            refused += 1
        else:
            recorded += 1
    return recorded, refused


def _bytes(value: Any) -> str:
    # What `Cache.put` writes, so "the same" means the same file.
    return json.dumps(value, ensure_ascii=False)


def _to_rows(
    value: Any,
) -> tuple[
    tuple[str, str, str, str | None, int],
    list[tuple[str, str | None, int | None, int | None, int | None]],
]:
    if not isinstance(value, Mapping) or tuple(value) != _FIELDS:
        raise ValueError("not a vocalization as the cache writes one")
    segments, machine, rejected = value["segments"], value["machine"], value["rejected"]
    if not isinstance(segments, Mapping) or not isinstance(machine, list):
        raise ValueError("not a vocalization as the cache writes one")
    if not isinstance(rejected, list):
        raise ValueError("not a vocalization as the cache writes one")
    if len(set(machine)) != len(machine) or len(set(rejected)) != len(rejected):
        raise ValueError("a segment is listed twice")
    order: dict[str, list[Any]] = {}
    for place, (segment, pointed) in enumerate(segments.items()):
        order[segment] = [segment, pointed, place, None, None]
    for place, segment in enumerate(machine):
        order.setdefault(segment, [segment, None, None, None, None])[3] = place
    for place, segment in enumerate(rejected):
        order.setdefault(segment, [segment, None, None, None, None])[4] = place
    header = (
        value["document_hash"],
        value["language"],
        value["vocalizer"],
        value["model"],
        value["schema_version"],
    )
    return header, [tuple(row) for row in order.values()]


def _read(db: sqlite3.Connection, key: str) -> dict[str, Any] | None:
    head = db.execute(
        "SELECT id, schema_version, document_hash, language, tool, tool_version"
        " FROM vocalizations WHERE cache_key = ?",
        (key,),
    ).fetchone()
    if head is None:
        return None
    rows = db.execute(
        "SELECT segment_id, pointed, segment_ord, machine_ord, rejected_ord"
        " FROM pointings WHERE vocalization_id = ?",
        (head[0],),
    ).fetchall()

    def ordered(column: int) -> list[Any]:
        return sorted((row for row in rows if row[column] is not None), key=lambda r: r[column])

    return {
        "schema_version": head[1],
        "document_hash": head[2],
        "language": head[3],
        "vocalizer": head[4],
        "model": head[5],
        "segments": {row[0]: row[1] for row in ordered(2)},
        "machine": [row[0] for row in ordered(3)],
        "rejected": [row[0] for row in ordered(4)],
    }
