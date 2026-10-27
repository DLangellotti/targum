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
from collections.abc import Callable, Iterator, Mapping
from contextlib import closing
from dataclasses import dataclass, replace
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
LEDGER_SCHEMA = 5

#: The stages the ledger records, and the table each one's values head. `tokens` since
#: 2026-10-08 (David's third answer of 2026-10-03): one annotator's pass over a text,
#: written where the pipeline writes `annotation.json`, since annotation has no cache.
_HEAD = {"vocalize": "vocalizations", "tokens": "annotations", "translations": "translations"}
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
    superseded_at  TEXT,
    exportable     INTEGER NOT NULL DEFAULT 0,
    research       INTEGER NOT NULL DEFAULT 0
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
    superseded_at  TEXT,
    exportable     INTEGER NOT NULL DEFAULT 0,
    research       INTEGER NOT NULL DEFAULT 0
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
-- One source document, and what its licence lets the corpus do with it (schema 3,
-- 2026-10-27). Every other table copies `exportable` from here, so this is the row an
-- export asks first. The bits are computed from `licence` and `private` by
-- `licensing.export_terms`, never typed. `private` marks a reader's import, held only in
-- readers' homes: the private bucket (#161). Which homes hold it is `text_homes`, never a
-- column here, so a departed reader's id leaves no trace in any row or any history.
-- `tool` is the ingester. History on change, like every head table: a licence corrected,
-- or a rule that now reads it differently, leaves the old verdict behind it.
CREATE TABLE IF NOT EXISTS texts (
    id                 INTEGER PRIMARY KEY,
    stage              TEXT NOT NULL,
    cache_key          TEXT NOT NULL,
    document_hash      TEXT NOT NULL,
    source             TEXT NOT NULL,
    licence            TEXT NOT NULL,
    private            INTEGER NOT NULL,
    exportable         INTEGER NOT NULL,
    research           INTEGER NOT NULL,
    reader_publishable INTEGER NOT NULL,
    tool               TEXT NOT NULL,
    tool_version       TEXT,
    schema_version     INTEGER NOT NULL,
    written_at         TEXT NOT NULL,
    superseded_at      TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS texts_current
    ON texts (cache_key) WHERE superseded_at IS NULL;
CREATE INDEX IF NOT EXISTS texts_exportable ON texts (exportable, research);
-- The homes a private text is held in, one row each: current only, no history, so an
-- account deletion takes its home out of every row in one statement.
CREATE TABLE IF NOT EXISTS text_homes (
    document_hash TEXT NOT NULL,
    home          TEXT NOT NULL,
    PRIMARY KEY (document_hash, home)
);
-- One rendering of one text (schema 5, 2026-10-27): a machine translation, an authored
-- English or a published translation matched to it, as its `translations/*.json` holds
-- it. Keyed `<document_hash>:<file stem>`, the name the build writes it under. `licence`
-- is the rendering's own: the catalogue's for a published one, the text's for one targum
-- made. `own_exportable`/`own_research` are that licence's bits; `exportable`/`research`
-- are those AND the text's, so a translation of a private text exports nowhere.
-- `head_json` is the file with its segments emptied, so every other field comes back
-- exactly and in place.
CREATE TABLE IF NOT EXISTS translations (
    id              INTEGER PRIMARY KEY,
    stage           TEXT NOT NULL,
    cache_key       TEXT NOT NULL,
    document_hash   TEXT NOT NULL,
    source_language TEXT NOT NULL,
    target_language TEXT NOT NULL,
    kind            TEXT NOT NULL,
    tool            TEXT NOT NULL,
    tool_version    TEXT,
    style           TEXT,
    schema_version  INTEGER NOT NULL,
    licence         TEXT NOT NULL,
    own_exportable  INTEGER NOT NULL,
    own_research    INTEGER NOT NULL,
    head_json       TEXT NOT NULL,
    written_at      TEXT NOT NULL,
    superseded_at   TEXT,
    exportable      INTEGER NOT NULL DEFAULT 0,
    research        INTEGER NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS translations_current
    ON translations (cache_key) WHERE superseded_at IS NULL;
CREATE INDEX IF NOT EXISTS translations_by_text ON translations (document_hash);
-- One aligned pair of that rendering: the source sentence and its target. `source` is
-- the segment's text where the build's segments were at hand, null where not.
CREATE TABLE IF NOT EXISTS pairs (
    translation_id INTEGER NOT NULL REFERENCES translations (id),
    segment_id     TEXT NOT NULL,
    ord            INTEGER NOT NULL,
    source         TEXT,
    target         TEXT NOT NULL,
    confidence     REAL,
    coarse         INTEGER NOT NULL,
    PRIMARY KEY (translation_id, segment_id)
);
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
    def __init__(self, file: Path, *, timeout: float = 30) -> None:
        self.file = file
        #: How long to wait for another process's write lock before giving up.
        self.timeout = timeout

    def _connect(self) -> sqlite3.Connection:
        self.file.parent.mkdir(parents=True, exist_ok=True)
        # Warm workers share the cache directory, so they share this file too.
        db = sqlite3.connect(self.file, timeout=self.timeout)
        db.execute("PRAGMA journal_mode=WAL")
        _migrate(db)
        db.executescript(_SCHEMA)
        _add_bits(db)
        db.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('schema', ?)", (str(LEDGER_SCHEMA),)
        )
        return db

    def record(
        self,
        stage: str,
        key: str,
        value: Any,
        *,
        licence: str = "",
        sources: Mapping[str, str] | None = None,
    ) -> None:
        """Write one cache value as rows, replacing what that cache key held before.

        `licence` and `sources` are for `translations` only: the rendering's own licence,
        and each segment's source text for its pair.

        Raises ValueError, and writes nothing, for a value the rows could not give back
        exactly — an unknown field, a repeated segment, anything that would make the
        ledger a lossy copy of the cache it is meant to replace.
        """
        if stage not in STAGES:
            raise ValueError(f"the ledger does not record {stage!r} yet")
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with closing(self._connect()) as db, db:
            # The same value again is not history: a rebuild that changed nothing writes
            # nothing, or every `rebuild --words` would add a copy of every text.
            if _bytes(_read(db, stage, key)) == _bytes(value) and (
                stage != "translations" or _licence_held(db, key) == licence
            ):
                return
            # What the key held stays, as history; it is only no longer the answer.
            db.execute(
                f"UPDATE {_HEAD[stage]} SET superseded_at = ?"  # noqa: S608 - a fixed name
                " WHERE cache_key = ? AND superseded_at IS NULL",
                (stamp, key),
            )
            if stage == "vocalize":
                _insert_vocalization(db, stage, key, value, stamp)
            elif stage == "translations":
                _insert_translation(db, stage, key, value, stamp, licence, sources or {})
            else:
                _insert_annotation(db, stage, key, value, stamp)
            back = _read(db, stage, key)
            if _bytes(back) != _bytes(value):
                # Leaving the `with db` block by an exception rolls the write back.
                raise ValueError("the rows do not give the value back exactly")
            _stamp(db, str(value["document_hash"]))

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

    def record_text(self, text: Text) -> bool:
        """Write one source document's row, keeping what it said before as history.

        The two export bits and `reader_publishable` are computed here from the licence
        and whether it is private, so nothing can record a verdict the licence does not
        give. Returns False, and writes no row, when the facts and the verdict the rule
        gives now are both what the row already says; a rule that changed supersedes it.
        The homes are kept current in `text_homes` either way.
        """
        if not text.document_hash or not text.source:
            raise ValueError("a text needs its document hash and its source")
        with closing(self._connect()) as db, db:
            return _write_text(db, text)

    def hold(self, text: Text, home: str | None) -> bool:
        """Record a text a build has just written, into `home` or, with None, into one of
        the library's own public folders. `text.homes` is not read: it is worked out here.

        A public build makes the text public. A build in a reader's home adds that home
        to the ones holding it, unless the text is already public, which a reader's copy
        of a shelf text does not change. Read and written in one transaction, so two
        builds of one text finishing together cannot lose a home.
        """
        if not text.document_hash or not text.source:
            raise ValueError("a text needs its document hash and its source")
        with closing(self._connect()) as db, db:
            db.commit()  # what opening left open, so the lock below is taken from the start
            db.execute("BEGIN IMMEDIATE")
            homes: frozenset[str] = frozenset()
            if home is not None:
                held = self._row(db, text.document_hash)
                if held is None or held[0][2]:
                    known = db.execute(
                        "SELECT home FROM text_homes WHERE document_hash = ?",
                        (text.document_hash,),
                    )
                    homes = frozenset({home, *(row[0] for row in known)})
            return _write_text(db, replace(text, homes=homes))

    def text(self, document_hash: str) -> Text | None:
        """What the ledger holds about one source document now, or None."""
        if not self.file.is_file():
            return None
        with closing(self._connect()) as db:
            row = self._row(db, document_hash)
            if row is None:
                return None
            homes = frozenset(
                home
                for (home,) in db.execute(
                    "SELECT home FROM text_homes WHERE document_hash = ?", (document_hash,)
                )
            )
        source, licence, _private, ingester, schema_version = row[0]
        return Text(document_hash, source, licence, homes, ingester, schema_version)

    def terms(self, document_hash: str) -> tuple[bool, bool] | None:
        """(exportable, research) for one document as recorded, or None if unrecorded."""
        if not self.file.is_file():
            return None
        with closing(self._connect()) as db:
            row = self._row(db, document_hash)
        return (bool(row[1][0]), bool(row[1][1])) if row is not None else None

    @staticmethod
    def _row(
        db: sqlite3.Connection, document_hash: str
    ) -> tuple[tuple[str, str, int, str, int], tuple[int, int, int]] | None:
        """(facts, verdict) of a document's current row."""
        row = db.execute(
            "SELECT source, licence, private, tool, schema_version,"
            " exportable, research, reader_publishable FROM texts"
            " WHERE cache_key = ? AND superseded_at IS NULL",
            (document_hash,),
        ).fetchone()
        if row is None:
            return None
        return (row[0], row[1], row[2], row[3], row[4]), (row[5], row[6], row[7])


@dataclass(frozen=True)
class Text:
    """One source document as the `texts` table holds it: the facts, not the verdict.

    The verdict — the two export bits and `reader_publishable` — is a column the ledger
    computes from `licence` and `homes` on the way in, so it is not a field here.
    """

    document_hash: str
    source: str
    licence: str
    #: The readers' homes holding a private import; empty for anything public.
    homes: frozenset[str] = frozenset()
    ingester: str = ""
    schema_version: int = 0


def _write_text(db: sqlite3.Connection, text: Text) -> bool:
    """`record_text` inside a transaction the caller holds."""
    verdict = _verdict(text)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    db.execute("DELETE FROM text_homes WHERE document_hash = ?", (text.document_hash,))
    db.executemany(
        "INSERT INTO text_homes (document_hash, home) VALUES (?, ?)",
        [(text.document_hash, home) for home in sorted(text.homes)],
    )
    held = Ledger._row(db, text.document_hash)
    if held is not None and held == (_facts(text), verdict):
        # Unchanged, but the rows under it may predate it (or schema 4): stamp anyway.
        _stamp(db, text.document_hash)
        return False
    db.execute(
        "UPDATE texts SET superseded_at = ? WHERE cache_key = ? AND superseded_at IS NULL",
        (stamp, text.document_hash),
    )
    db.execute(
        "INSERT INTO texts (stage, cache_key, document_hash, source, licence, private,"
        " exportable, research, reader_publishable, tool, tool_version,"
        " schema_version, written_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "texts",
            text.document_hash,
            text.document_hash,
            text.source,
            text.licence,
            int(bool(text.homes)),
            *verdict,
            text.ingester,
            None,
            text.schema_version,
            stamp,
        ),
    )
    _stamp(db, text.document_hash)
    return True


#: The head tables whose rows carry their text's export bits, copied from `texts`.
_STAMPED = ("vocalizations", "annotations")


def _stamp(db: sqlite3.Connection, document_hash: str) -> None:
    """Copy a text's current export bits onto every row made from it, history included,
    so an export of any table is one `WHERE` with no join. A text with no `texts` row
    exports nowhere: its rows read 0 until one is written."""
    found = db.execute(
        "SELECT exportable, research FROM texts WHERE cache_key = ? AND superseded_at IS NULL",
        (document_hash,),
    ).fetchone()
    bits = (found[0], found[1]) if found is not None else (0, 0)
    for head in _STAMPED:
        db.execute(
            f"UPDATE {head} SET exportable = ?, research = ?"  # noqa: S608 - a fixed name
            " WHERE document_hash = ? AND (exportable != ? OR research != ?)",
            (*bits, document_hash, *bits),
        )
    # A translation is the text's bits AND its own licence's: a published rendering under
    # a licence of its own may be narrower than the text it is beside.
    db.execute(
        "UPDATE translations SET exportable = ? AND own_exportable,"
        " research = ? AND own_research WHERE document_hash = ?",
        (*bits, document_hash),
    )


def _add_bits(db: sqlite3.Connection) -> None:
    """Schema 4 (2026-10-27): the export bits on every head table made from a text.
    Asked of the columns rather than of `meta`, and inside the write lock, so a file any
    older schema left — or a second process racing this one — ends up with them once."""

    def missing() -> list[str]:
        return [
            head
            for head in _STAMPED
            if "exportable" not in {row[1] for row in db.execute(f"PRAGMA table_info({head})")}
        ]

    if not missing():
        return
    db.execute("BEGIN IMMEDIATE")
    try:
        for head in missing():
            for column in ("exportable", "research"):
                db.execute(f"ALTER TABLE {head} ADD COLUMN {column} INTEGER NOT NULL DEFAULT 0")
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


#: How long a build waits for the ledger's write lock before going on without the row
#: (qa-claude on #943): another process holding it cost a reader's build the full 30 s
#: before its vowels. The row is lost, not the build; the next backfill writes it.
MIRROR_TIMEOUT = 2.0


def mirror_text(folder: Path) -> None:
    """A build's `texts` row (targum-internal#162, slice 2): called once a build has
    written `document.json` and anything beside it a licence is read from. Does nothing
    with the flag off; never raises, because the reader matters more than the ledger.

    The folder's parent says whose it is: a reader's home (`is_home`) or the library's
    own, as `backfill_texts` reads the same tree.
    """
    file = path()
    if file is None:
        return
    try:
        document = json.loads((folder / "document.json").read_text(encoding="utf-8"))
        source = str(document.get("source") or "")
        text = Text(
            document_hash=str(document.get("content_hash") or ""),
            source=source,
            licence=_licence_of(folder, source),
            ingester=str(document.get("ingester") or ""),
            schema_version=int(document.get("schema_version") or 0),
        )
        home = folder.parent.name if is_home(folder.parent.name) else None
        Ledger(file, timeout=MIRROR_TIMEOUT).hold(text, home)
    except (sqlite3.Error, OSError, ValueError, TypeError, AttributeError) as error:
        log.warning("corpus ledger: %s not recorded as a text: %s", folder.name, error)


def _facts(text: Text) -> tuple[str, str, int, str, int]:
    return (text.source, text.licence, int(bool(text.homes)), text.ingester, text.schema_version)


def _verdict(text: Text) -> tuple[int, int, int]:
    from .licensing import export_terms
    from .screen import licence_flags

    terms = export_terms(text.licence, private=bool(text.homes))
    publishable = licence_flags(text.licence).reader_publishable
    return int(terms.exportable), int(terms.research), int(publishable)


def disown(home: str) -> int:
    """Take one departed reader's home out of every text it held (clause 3.14).

    `forget` deletes what was theirs alone; this is the rest, a text somebody else
    still holds. Its rows stay, as corpus or as the other reader's, and keep no trace of
    this home: the homes live only in `text_homes`, never in a row or its history.
    Returns how many texts it was taken out of; does nothing with the flag off.
    """
    file = path()
    if file is None or not home or not file.is_file():
        return 0
    with closing(Ledger(file)._connect()) as db, db:
        return db.execute("DELETE FROM text_homes WHERE home = ?", (home,)).rowcount


#: The rows a value is made of, by the head table they hang off and the column that
#: names it: what has to go when a head row goes.
_UNITS = {
    "translations": ("pairs", "translation_id"),
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
        db.execute(f"DELETE FROM texts WHERE document_hash IN ({marks})", wanted)  # noqa: S608
        db.execute(
            f"DELETE FROM text_homes WHERE document_hash IN ({marks})",  # noqa: S608
            wanted,
        )
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


#: A reader's home under the library, as `Library.home` names it: `p<account id>`, or
#: `local` for whoever is signed out on a machine somebody runs themselves. Every other
#: folder is the library's own — the shared shelf, the weekly, and on the laptop the
#: parasha, the Russian shelf, the dialogues — and holds nothing private.
_HOME = re.compile(r"p\d+|local")


def is_home(name: str) -> bool:
    """Whether a folder under the library is a reader's home."""
    return _HOME.fullmatch(name) is not None


def _built_folders(out: Path) -> list[tuple[Path, str | None]]:
    """Every built text's folder under the library, with the home it is in, or None for
    one of the library's own public folders (or a text built straight into `out`)."""
    try:
        roots = sorted(one for one in out.iterdir() if one.is_dir())
    except OSError:
        return []
    folders: list[tuple[Path, str | None]] = []
    for root in roots:
        home = root.name if is_home(root.name) else None
        if home is None and (root / "document.json").is_file():
            folders.append((root, None))
            continue
        folders += [(one, home) for one in sorted(root.iterdir()) if one.is_dir()]
    return folders


def backfill_texts(
    ledger: Ledger,
    out: Path,
    *,
    licence_of: Callable[[Path, str], str] | None = None,
) -> tuple[int, int]:
    """Record a `texts` row for every built text under an output folder. Reads only.

    `out` is the library's root. A reader's home (`is_home`) holds private imports;
    every other folder is the library's own and public, and so is a text built straight
    into `out`. A document any public folder holds is public, whatever homes also hold
    it; one held only in homes is private, held by them. The licence is the
    catalogue's for the source, else what the manifest beside the reader records
    (`promote.licence_of`), else empty, which exports nowhere.

    Returns (recorded, unchanged). A folder with no readable `document.json` is skipped.
    """
    if licence_of is None:
        licence_of = _licence_of
    found: dict[str, tuple[Path, dict[str, Any]]] = {}
    held_in: dict[str, set[str]] = {}
    public: set[str] = set()
    for folder, home in _built_folders(out):
        try:
            document = json.loads((folder / "document.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(document, Mapping):
            continue
        hash_ = str(document.get("content_hash") or "")
        if not hash_ or not document.get("source"):
            continue
        if home is None:
            public.add(hash_)
        else:
            held_in.setdefault(hash_, set()).add(home)
        # A public copy is the one the licence is read beside, where there is one.
        if hash_ not in found or home is None:
            found[hash_] = (folder, dict(document))
    recorded = unchanged = 0
    for hash_, (folder, document) in found.items():
        source = str(document["source"])
        text = Text(
            document_hash=hash_,
            source=source,
            licence=licence_of(folder, source),
            homes=frozenset() if hash_ in public else frozenset(held_in[hash_]),
            ingester=str(document.get("ingester") or ""),
            schema_version=int(document.get("schema_version") or 0),
        )
        if ledger.record_text(text):
            recorded += 1
        else:
            unchanged += 1
    return recorded, unchanged


def _licence_of(folder: Path, source: str) -> str:
    """The catalogue's licence for a source, else the one recorded beside the reader."""
    from . import catalogue
    from .promote import licence_of

    try:
        entry = catalogue.matching(source)
    except Exception:  # noqa: BLE001 - a private catalogue is absent on a public checkout
        entry = None
    if entry is not None:
        # The entry answers for its renderings too; a rendering is its own work under
        # its own licence (targum-internal#234), so it is asked for by its own source.
        wanted = _source_key(source)
        if _source_key(entry.source) == wanted:
            return entry.licence
        for rendering in entry.translations:
            if _source_key(rendering.source) == wanted:
                return rendering.licence
    return licence_of(folder, source)


def _source_key(source: str) -> str:
    # `catalogue._key`'s flattening, so a match there is a match here.
    return source.strip().lower().replace("_", " ").rstrip("/")


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
    if int(found[0]) >= 2:
        # 2 → 3 (2026-10-27) only adds `texts`, which the schema script makes; nothing
        # already written changes shape.
        with db:
            db.execute("UPDATE meta SET value = ? WHERE key = 'schema'", (str(LEDGER_SCHEMA),))
        return
    # One transaction, opened by hand and holding the write lock from the start. Python's
    # sqlite3 commits a CREATE TABLE on its own outside an explicit BEGIN, so a copy that
    # failed after it left `vocalizations_2` behind, and every later open then failed on
    # it (review, 2026-10-08). Asked again inside the lock, because another process may
    # have migrated while this one waited for it.
    db.execute("BEGIN IMMEDIATE")
    try:
        again = db.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()
        if again is None or int(again[0]) >= LEDGER_SCHEMA:
            db.execute("ROLLBACK")
            return
        db.execute("DROP TABLE IF EXISTS vocalizations_2")
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
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


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
    if stage == "translations":
        return _read_translation(db, row_id)
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


#: The fields a translation file has, which a translation row must hold all of.
_TRANSLATION = ("name", "document_hash", "source_language", "target_language", "provider")


def _licence_held(db: sqlite3.Connection, key: str) -> str | None:
    row = db.execute(
        "SELECT licence FROM translations WHERE cache_key = ? AND superseded_at IS NULL", (key,)
    ).fetchone()
    return row[0] if row is not None else None


def _insert_translation(
    db: sqlite3.Connection,
    stage: str,
    key: str,
    value: Any,
    stamp: str,
    licence: str,
    sources: Mapping[str, str],
) -> None:
    from .licensing import export_terms

    if not isinstance(value, Mapping) or any(name not in value for name in _TRANSLATION):
        raise ValueError("not a translation as the pipeline writes one")
    segments = value.get("segments")
    coarse = value.get("coarse") or []
    confidence = value.get("confidence") or {}
    if not isinstance(segments, Mapping) or not isinstance(coarse, list):
        raise ValueError("not a translation as the pipeline writes one")
    if not isinstance(confidence, Mapping):
        raise ValueError("not a translation as the pipeline writes one")
    head = dict(value)
    head["segments"] = {}
    own = export_terms(licence)
    cursor = db.execute(
        "INSERT INTO translations (stage, cache_key, document_hash, source_language,"
        " target_language, kind, tool, tool_version, style, schema_version, licence,"
        " own_exportable, own_research, head_json, written_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            stage,
            key,
            value["document_hash"],
            value["source_language"],
            value["target_language"],
            str(value.get("kind") or "machine"),
            value["provider"],
            value.get("model"),
            value.get("style"),
            int(value.get("schema_version") or 0),
            licence,
            int(own.exportable),
            int(own.research),
            json.dumps(head, ensure_ascii=False),
            stamp,
        ),
    )
    flagged = set(coarse)
    db.executemany(
        "INSERT INTO pairs (translation_id, segment_id, ord, source, target, confidence,"
        " coarse) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (
                cursor.lastrowid,
                segment,
                ord_,
                sources.get(segment),
                target,
                confidence.get(segment),
                int(segment in flagged),
            )
            for ord_, (segment, target) in enumerate(segments.items())
        ],
    )


def _read_translation(db: sqlite3.Connection, row_id: int) -> dict[str, Any]:
    """One rendering, rebuilt from its head and its pairs, segments back in their place."""
    head_json = db.execute("SELECT head_json FROM translations WHERE id = ?", (row_id,)).fetchone()
    value: dict[str, Any] = json.loads(head_json[0])
    value["segments"] = {
        segment: target
        for segment, target in db.execute(
            "SELECT segment_id, target FROM pairs WHERE translation_id = ? ORDER BY ord",
            (row_id,),
        )
    }
    return value


def mirror_translations(folder: Path) -> None:
    """A build's renderings, from its `translations/*.json` (slice 4): called once a build
    has written them, and after a chapter is bought. Reads files only; nothing is
    translated. Does nothing with the flag off; never raises."""
    file = path()
    if file is None:
        return
    try:
        record_translations(Ledger(file, timeout=MIRROR_TIMEOUT), folder)
    except (sqlite3.Error, OSError, ValueError, TypeError, AttributeError) as error:
        log.warning("corpus ledger: %s translations not recorded: %s", folder.name, error)


def record_translations(ledger: Ledger, folder: Path) -> tuple[int, int]:
    """Record every rendering one built folder holds. Returns (recorded, refused).

    Reads `document.json` for the text, `segments.json` for each pair's source sentence
    and `translations/*.json` for the renderings. A rendering targum made (`machine`,
    `authored`) is under the text's licence; a published one under its own, which only
    the catalogue knows; one it does not know is under none and exports nowhere.
    """
    translations = sorted((folder / "translations").glob("*.json"))
    if not translations:
        return 0, 0
    document = json.loads((folder / "document.json").read_text(encoding="utf-8"))
    source = str(document.get("source") or "")
    sources = _segment_texts(folder)
    text_licence: str | None = None
    recorded = refused = 0
    for one in translations:
        try:
            value = json.loads(one.read_text(encoding="utf-8"))
            if not isinstance(value, Mapping):
                raise ValueError("not a translation")
            if str(value.get("kind") or "machine") in ("machine", "authored"):
                if text_licence is None:
                    text_licence = _licence_of(folder, source)
                licence = text_licence
            else:
                licence = _rendering_licence(source, value)
            ledger.record(
                "translations",
                f"{value.get('document_hash')}:{one.stem}",
                value,
                licence=licence,
                sources=sources,
            )
        except (ValueError, TypeError, OSError) as error:
            log.warning("corpus ledger: %s not recorded: %s", one.name, error)
            refused += 1
        else:
            recorded += 1
    return recorded, refused


def _segment_texts(folder: Path) -> dict[str, str]:
    try:
        held = json.loads((folder / "segments.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    segments = held.get("segments") if isinstance(held, Mapping) else None
    if not isinstance(segments, list):
        return {}
    return {
        str(one["id"]): str(one["text"])
        for one in segments
        if isinstance(one, Mapping) and "id" in one and "text" in one
    }


def _rendering_licence(source: str, value: Mapping[str, Any]) -> str:
    """A published rendering's own licence, from the catalogue entry of the text it is
    beside: the one rendering in its language, or the one of that name among several.
    Empty where the catalogue does not say, which exports nowhere."""
    from . import catalogue

    try:
        entry = catalogue.matching(source)
    except Exception:  # noqa: BLE001 - a private catalogue is absent on a public checkout
        entry = None
    if entry is None:
        return ""
    language = str(value.get("target_language") or "")
    beside = [one for one in entry.translations if one.language == language]
    if len(beside) == 1:
        return beside[0].licence
    name = _source_key(str(value.get("name") or ""))
    named = [one for one in beside if _source_key(one.name) == name]
    return named[0].licence if len(named) == 1 else ""


def backfill_translations(ledger: Ledger, out: Path) -> tuple[int, int]:
    """Read every built folder's renderings under the library into rows: the migration
    for `translations`, from what is already on disk. Nothing is translated or fetched.
    Returns (recorded, refused)."""
    recorded = refused = 0
    for folder, _home in _built_folders(out):
        if not (folder / "document.json").is_file():
            continue
        try:
            done, failed = record_translations(ledger, folder)
        except (OSError, ValueError) as error:
            log.warning("corpus ledger: %s not read: %s", folder.name, error)
            continue
        recorded += done
        refused += failed
    return recorded, refused
