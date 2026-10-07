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
import re
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
LEDGER_SCHEMA = 2

#: The stages the ledger records, and the table each one's values head. `tokens` since
#: 2026-10-08 (David's third answer of 2026-10-03): one annotator's pass over a text,
#: written where the pipeline writes `annotation.json`, since annotation has no cache.
_HEAD = {"vocalize": "vocalizations", "tokens": "annotations"}
STAGES = frozenset(_HEAD)

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
-- so a new row; the old one stays (targum-internal#162, criterion 2). The same key
-- written again keeps the old row too, stamped `superseded_at` (David, 2026-10-03), so a
-- forced rebuild leaves a comparison behind. One row a key is current: the one with no
-- stamp.
CREATE TABLE IF NOT EXISTS vocalizations (
    id             INTEGER PRIMARY KEY,
    stage          TEXT NOT NULL,
    cache_key      TEXT NOT NULL,
    document_hash  TEXT NOT NULL,
    language       TEXT NOT NULL,
    tool           TEXT NOT NULL,
    tool_version   TEXT,
    schema_version INTEGER NOT NULL,
    written_at     TEXT NOT NULL,
    superseded_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS vocalizations_current
    ON vocalizations (cache_key) WHERE superseded_at IS NULL;
CREATE INDEX IF NOT EXISTS vocalizations_by_text
    ON vocalizations (document_hash, tool, tool_version);
-- A segment of that pointing. `pointed` is null for a segment that is only listed as
-- rejected; each *_ord is the segment's place in its list, null when not in it.
-- One annotator's pass over one text (`tokens`). `head_json` is the annotation without
-- its tokens, so the fields only a reader of the file wants — the method, its note, the
-- band count — come back exactly without a column each.
CREATE TABLE IF NOT EXISTS annotations (
    id             INTEGER PRIMARY KEY,
    stage          TEXT NOT NULL,
    cache_key      TEXT NOT NULL,
    document_hash  TEXT NOT NULL,
    language       TEXT NOT NULL,
    tool           TEXT NOT NULL,
    tool_version   TEXT,
    schema_version INTEGER NOT NULL,
    head_json      TEXT NOT NULL,
    written_at     TEXT NOT NULL,
    superseded_at  TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS annotations_current
    ON annotations (cache_key) WHERE superseded_at IS NULL;
CREATE INDEX IF NOT EXISTS annotations_by_text ON annotations (document_hash, tool);
-- One token of that pass. The query columns are what the agreement between two
-- annotators is asked of (criterion 2: a self-join on document, segment and place);
-- `token_json` is the token whole, which is what gives the file back byte for byte.
CREATE TABLE IF NOT EXISTS tokens (
    annotation_id INTEGER NOT NULL REFERENCES annotations (id),
    segment_id    TEXT NOT NULL,
    segment_ord   INTEGER NOT NULL,
    ord           INTEGER NOT NULL,
    form          TEXT NOT NULL,
    lemma         TEXT,
    pos           TEXT,
    features      TEXT,
    band          INTEGER,
    token_json    TEXT NOT NULL,
    PRIMARY KEY (annotation_id, segment_id, ord)
);
CREATE INDEX IF NOT EXISTS tokens_by_lemma ON tokens (lemma);
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
        _migrate(db)
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
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with closing(self._connect()) as db, db:
            # What the key held stays, as history; it is only no longer the answer.
            db.execute(
                f"UPDATE {_HEAD[stage]} SET superseded_at = ?"  # noqa: S608 - a fixed name
                " WHERE cache_key = ? AND superseded_at IS NULL",
                (stamp, key),
            )
            if stage == "vocalize":
                _insert_vocalization(db, stage, key, value, stamp)
            else:
                _insert_annotation(db, stage, key, value, stamp)
            back = _read(db, stage, key)
            if _bytes(back) != _bytes(value):
                # Leaving the `with db` block by an exception rolls the write back.
                raise ValueError("the rows do not give the value back exactly")

    def get(self, stage: str, key: str) -> dict[str, Any] | None:
        """The value a cache key holds, rebuilt from rows. None if there is no row."""
        if stage not in STAGES or not self.file.is_file():
            return None
        with closing(self._connect()) as db:
            return _read(db, stage, key)

    def drop(self, stage: str, key: str) -> bool:
        """Stop answering for one value — the cache's `drop`, so a wrong answer is not
        rebuilt. Kept as history, like any value a key no longer holds: a wrong answer is
        exactly the one worth comparing the next against."""
        if stage not in STAGES or not self.file.is_file():
            return False
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with closing(self._connect()) as db, db:
            dropped = db.execute(
                f"UPDATE {_HEAD[stage]} SET superseded_at = ?"  # noqa: S608 - a fixed name
                " WHERE cache_key = ? AND superseded_at IS NULL",
                (stamp, key),
            )
            return dropped.rowcount > 0

    def history(self, stage: str, key: str) -> list[tuple[str, str | None, dict[str, Any]]]:
        """Every value one key has held, oldest first, as (written, superseded, value);
        the current one, where there is one, is last and has no superseded stamp."""
        if stage not in STAGES or not self.file.is_file():
            return []
        with closing(self._connect()) as db:
            heads = db.execute(
                f"SELECT id, written_at, superseded_at FROM {_HEAD[stage]}"  # noqa: S608
                " WHERE cache_key = ? ORDER BY id",
                (key,),
            ).fetchall()
            return [(written, gone, _read_row(db, stage, row)) for row, written, gone in heads]

    def entries(self, stage: str) -> Iterator[tuple[str, dict[str, Any]]]:
        """Every (cache key, value) the ledger holds for a stage, oldest first."""
        if stage not in STAGES or not self.file.is_file():
            return
        with closing(self._connect()) as db:
            keys = [
                row[0]
                for row in db.execute(
                    f"SELECT cache_key FROM {_HEAD[stage]}"  # noqa: S608 - a fixed name
                    " WHERE stage = ? AND superseded_at IS NULL ORDER BY id",
                    (stage,),
                )
            ]
            for key in keys:
                value = _read(db, stage, key)
                if value is not None:
                    yield key, value


#: The rows a value is made of, by the head table they hang off and the column that
#: names it: what has to go when a head row goes.
_UNITS = {
    "vocalizations": ("pointings", "vocalization_id"),
    "annotations": ("tokens", "annotation_id"),
}


def forget(hashes: set[str]) -> int:
    """Delete everything the ledger holds about these documents, history and all.

    For an account that is gone (decided 2026-10-03: `corpus.db` is its own file, and
    account deletion has to reach it). Unlike `drop`, nothing is kept: these are a
    private bucket, and the person they came from asked for them to go. Returns how many
    values went; does nothing with the flag off.
    """
    file = path()
    if file is None or not hashes or not file.is_file():
        return 0
    gone = 0
    with closing(Ledger(file)._connect()) as db, db:
        wanted = sorted(hashes)
        marks = ",".join("?" for _ in wanted)
        for head, (units, link) in _UNITS.items():
            ids = [
                row[0]
                for row in db.execute(
                    f"SELECT id FROM {head} WHERE document_hash IN ({marks})",  # noqa: S608
                    wanted,
                )
            ]
            for start in range(0, len(ids), 500):
                chunk = ids[start : start + 500]
                holes = ",".join("?" for _ in chunk)
                db.execute(f"DELETE FROM {units} WHERE {link} IN ({holes})", chunk)  # noqa: S608
                db.execute(f"DELETE FROM {head} WHERE id IN ({holes})", chunk)  # noqa: S608
            gone += len(ids)
    return gone


#: A document's hash where an artifact names it, read from the head of the file: every
#: artifact writes it among its first fields, and an annotation can be tens of megabytes.
_NAMED = re.compile(r'"(?:document_hash|content_hash)":\s*"([0-9a-f]{16,})"')
_ARTIFACTS = ("document.json", "segments.json", "vocalization.json", "annotation.json")


def documents_under(root: Path) -> set[str]:
    """Every document hash a folder of built texts names, one level down."""
    found: set[str] = set()
    try:
        folders = [one for one in root.iterdir() if one.is_dir()]
    except OSError:
        return found
    for folder in folders:
        for name in _ARTIFACTS:
            try:
                with (folder / name).open("rb") as handle:
                    head = handle.read(2048).decode("utf-8", "ignore")
            except OSError:
                continue
            found.update(_NAMED.findall(head))
    return found


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


def _migrate(db: sqlite3.Connection) -> None:
    """Bring a ledger written under an older schema up to this one, in place.

    1 → 2 (2026-10-08): `cache_key` loses its UNIQUE and rows gain `superseded_at`, so a
    key written again keeps what it held. SQLite cannot drop a column constraint, so the
    table is copied: made anew, filled, the old one dropped and the new one renamed into
    its place, which keeps `pointings`' reference to it by name. Every row comes across as
    current, which is what it was.
    """
    if not db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'meta'"
    ).fetchone():
        return  # a new file: the schema makes it current
    found = db.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()
    if found is None or int(found[0]) >= LEDGER_SCHEMA:
        return
    with db:
        db.execute(
            "CREATE TABLE vocalizations_2 (id INTEGER PRIMARY KEY, stage TEXT NOT NULL,"
            " cache_key TEXT NOT NULL, document_hash TEXT NOT NULL, language TEXT NOT NULL,"
            " tool TEXT NOT NULL, tool_version TEXT, schema_version INTEGER NOT NULL,"
            " written_at TEXT NOT NULL, superseded_at TEXT)"
        )
        db.execute(
            "INSERT INTO vocalizations_2 (id, stage, cache_key, document_hash, language, tool,"
            " tool_version, schema_version, written_at) SELECT id, stage, cache_key,"
            " document_hash, language, tool, tool_version, schema_version, written_at"
            " FROM vocalizations"
        )
        db.execute("DROP TABLE vocalizations")
        db.execute("ALTER TABLE vocalizations_2 RENAME TO vocalizations")
        db.execute("UPDATE meta SET value = ? WHERE key = 'schema'", (str(LEDGER_SCHEMA),))


def _read(db: sqlite3.Connection, stage: str, key: str) -> dict[str, Any] | None:
    """The value a key holds now: its one row with no superseded stamp."""
    head = db.execute(
        f"SELECT id FROM {_HEAD[stage]}"  # noqa: S608 - a fixed name
        " WHERE cache_key = ? AND superseded_at IS NULL",
        (key,),
    ).fetchone()
    return _read_row(db, stage, head[0]) if head is not None else None


def _read_row(db: sqlite3.Connection, stage: str, row_id: int) -> dict[str, Any]:
    """One value, rebuilt from its rows, current or not."""
    if stage == "tokens":
        return _read_annotation(db, row_id)
    return _read_vocalization(db, row_id)


def _insert_vocalization(
    db: sqlite3.Connection, stage: str, key: str, value: Any, stamp: str
) -> None:
    header, rows = _to_rows(value)
    cursor = db.execute(
        "INSERT INTO vocalizations (stage, cache_key, document_hash, language, tool,"
        " tool_version, schema_version, written_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (stage, key, *header, stamp),
    )
    db.executemany(
        "INSERT INTO pointings (vocalization_id, segment_id, pointed, segment_ord,"
        " machine_ord, rejected_ord) VALUES (?, ?, ?, ?, ?, ?)",
        [(cursor.lastrowid, *row) for row in rows],
    )


#: The fields an annotation has besides its tokens, in the order the file writes them.
_ANNOTATION = ("schema_version", "document_hash", "language", "annotator")


def _insert_annotation(
    db: sqlite3.Connection, stage: str, key: str, value: Any, stamp: str
) -> None:
    if not isinstance(value, Mapping) or list(value)[-1:] != ["tokens"]:
        raise ValueError("not an annotation as the pipeline writes one")
    if any(name not in value for name in _ANNOTATION):
        raise ValueError("not an annotation as the pipeline writes one")
    tokens = value["tokens"]
    if not isinstance(tokens, Mapping):
        raise ValueError("not an annotation as the pipeline writes one")
    head = {name: field for name, field in value.items() if name != "tokens"}
    cursor = db.execute(
        "INSERT INTO annotations (stage, cache_key, document_hash, language, tool,"
        " tool_version, schema_version, head_json, written_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            stage,
            key,
            value["document_hash"],
            value["language"],
            value["annotator"],
            None,
            value["schema_version"],
            json.dumps(head, ensure_ascii=False),
            stamp,
        ),
    )
    rows = []
    for segment_ord, (segment, run) in enumerate(tokens.items()):
        if not isinstance(run, list):
            raise ValueError("a segment's tokens are not a list")
        for ord_, token in enumerate(run):
            if not isinstance(token, Mapping):
                raise ValueError("a token is not an object")
            rows.append(
                (
                    cursor.lastrowid,
                    segment,
                    segment_ord,
                    ord_,
                    str(token.get("surface") or ""),
                    token.get("lemma"),
                    token.get("pos"),
                    token.get("feats"),
                    token.get("band"),
                    json.dumps(token, ensure_ascii=False),
                )
            )
    db.executemany(
        "INSERT INTO tokens (annotation_id, segment_id, segment_ord, ord, form, lemma, pos,"
        " features, band, token_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )


def _read_annotation(db: sqlite3.Connection, row_id: int) -> dict[str, Any]:
    head_json = db.execute("SELECT head_json FROM annotations WHERE id = ?", (row_id,)).fetchone()
    value: dict[str, Any] = json.loads(head_json[0])
    tokens: dict[str, list[Any]] = {}
    for segment, token in db.execute(
        "SELECT segment_id, token_json FROM tokens WHERE annotation_id = ?"
        " ORDER BY segment_ord, ord",
        (row_id,),
    ):
        tokens.setdefault(segment, []).append(json.loads(token))
    value["tokens"] = tokens
    return value


def _read_vocalization(db: sqlite3.Connection, row_id: int) -> dict[str, Any]:
    """One pointing, rebuilt from its row and its pointings."""
    head = db.execute(
        "SELECT id, schema_version, document_hash, language, tool, tool_version"
        " FROM vocalizations WHERE id = ?",
        (row_id,),
    ).fetchone()
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
