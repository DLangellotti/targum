"""The language tables' one writer: `contribution` and `tally` in the corpus ledger.

They live in `corpus.db`, the file `TARGUM_LEDGER` names, beside #162's rows and under
their own schema key, `meta.tables_schema`, so neither schema moves the other. They are
corpus data, not personal data: the backup copies them and an account deletion has
nothing to take out, because only public texts are ever folded (`tables.public_text`).

Rows are append-only. A count is a contribution, never an edited total, and a current
count is `SUM(n)` over the contributions nobody has superseded. Folding a text again
under a new annotator name supersedes what the old name gave, so a rename never counts a
text twice, and the old rows stay to compare the two annotators by.

Nothing here is exported or served: `corpus_export` names its tables one by one and
these are not among them, and no route reads them.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterable, Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .. import ledger as ledger_module
from . import weights

#: The tables' own schema, independent of the ledger's and of `models.SCHEMA_VERSION`.
TABLES_SCHEMA = 1

_SCHEMA = """
-- One measurement: what one fold of one unit by one tool counted. `id` is a content hash
-- of (table, unit, tool, rule), so the same fold twice is one row. At most one row per
-- (table, unit) is current.
CREATE TABLE IF NOT EXISTS contribution (
    id            TEXT PRIMARY KEY,
    tbl           TEXT NOT NULL,
    register      TEXT NOT NULL,
    unit          TEXT NOT NULL,
    source        TEXT NOT NULL,
    licence       TEXT NOT NULL,
    tool          TEXT NOT NULL,
    origin        TEXT NOT NULL,
    written_at    TEXT NOT NULL,
    superseded_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS contribution_current
    ON contribution (tbl, unit) WHERE superseded_at IS NULL;
CREATE INDEX IF NOT EXISTS contribution_by_register
    ON contribution (tbl, register) WHERE superseded_at IS NULL;
-- What it counted: a key (a lemma, a sequence of lemmas, a root) in a variant (its part
-- of speech, or theirs, or a root's binyan), n times.
CREATE TABLE IF NOT EXISTS tally (
    contribution_id TEXT NOT NULL REFERENCES contribution (id),
    key             TEXT NOT NULL,
    variant         TEXT NOT NULL,
    n               INTEGER NOT NULL,
    PRIMARY KEY (contribution_id, key, variant)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS tally_by_key ON tally (key);
"""

#: Where the box keeps its state; a ledger under it was written by the box.
_BOX = Path("/var/lib/targum")


def contribution_id(table: str, unit: str, tool: str, rule: str) -> str:
    """The content hash a contribution is keyed by."""
    raw = "\0".join((table, unit, tool, rule)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Contribution:
    """One measurement's provenance, before it is written."""

    table: str
    register: str
    unit: str
    source: str
    licence: str
    tool: str
    #: The version of the rule that counted it, so a changed fold is a new row.
    rule: str

    @property
    def id(self) -> str:
        return contribution_id(self.table, self.unit, self.tool, self.rule)


class Store:
    """The tables in one corpus ledger file."""

    def __init__(self, file: Path, *, timeout: float = 30) -> None:
        self.file = file
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> Store | None:
        """The store in the file `TARGUM_LEDGER` names, or None: the ledger is off."""
        file = ledger_module.path()
        return cls(file) if file is not None else None

    def _connect(self) -> sqlite3.Connection:
        # Through the ledger, so a file an older schema left is brought up to date first
        # and the two sets of tables always sit in one file.
        db = ledger_module.Ledger(self.file, timeout=self.timeout)._connect()
        db.executescript(_SCHEMA)
        db.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('tables_schema', ?)",
            (str(TABLES_SCHEMA),),
        )
        db.commit()
        return db

    def origin(self) -> str:
        """`box` for the box's own ledger, `laptop` for any other."""
        try:
            self.file.resolve().relative_to(_BOX)
        except (ValueError, OSError):
            return "laptop"
        return "box"

    def is_current(self, contribution: str) -> bool:
        """Whether a contribution id is written and nobody has superseded it."""
        if not self.file.is_file():
            return False
        with closing(self._connect()) as db:
            row = db.execute(
                "SELECT 1 FROM contribution WHERE id = ? AND superseded_at IS NULL",
                (contribution,),
            ).fetchone()
        return row is not None

    def write(self, contribution: Contribution, counts: Mapping[tuple[str, str], int]) -> bool:
        """Write one contribution and its tallies, superseding whatever was current for
        its (table, unit). Returns False, and writes nothing, when it is already current.

        A contribution written before and since superseded — an annotator renamed back —
        is made current again rather than written twice, since its id says it counted
        exactly this.
        """
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            held = db.execute(
                "SELECT superseded_at FROM contribution WHERE id = ?", (contribution.id,)
            ).fetchone()
            if held is not None and held[0] is None:
                return False
            db.execute(
                "UPDATE contribution SET superseded_at = ?"
                " WHERE tbl = ? AND unit = ? AND superseded_at IS NULL",
                (stamp, contribution.table, contribution.unit),
            )
            if held is not None:
                db.execute(
                    "UPDATE contribution SET superseded_at = NULL WHERE id = ?",
                    (contribution.id,),
                )
                return True
            db.execute(
                "INSERT INTO contribution (id, tbl, register, unit, source, licence, tool,"
                " origin, written_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    contribution.id,
                    contribution.table,
                    contribution.register,
                    contribution.unit,
                    contribution.source,
                    contribution.licence,
                    contribution.tool,
                    self.origin(),
                    stamp,
                ),
            )
            db.executemany(
                "INSERT INTO tally (contribution_id, key, variant, n) VALUES (?, ?, ?, ?)",
                [(contribution.id, key, variant, n) for (key, variant), n in counts.items()],
            )
        return True

    def total(self, table: str, register: str | None = None) -> int:
        """The current count of everything in one table, in one register or all."""
        if not self.file.is_file():
            return 0
        query = (
            "SELECT COALESCE(SUM(t.n), 0) FROM tally t JOIN contribution c"
            " ON c.id = t.contribution_id WHERE c.superseded_at IS NULL AND c.tbl = ?"
        )
        args: list[str] = [table]
        if register is not None:
            query += " AND c.register = ?"
            args.append(register)
        with closing(self._connect()) as db:
            return int(db.execute(query, args).fetchone()[0])

    def top(
        self, table: str, register: str, *, limit: int = 50, weighed: bool = True
    ) -> list[tuple[str, int]]:
        """The commonest keys in one table and register now, with their counts.

        `weighed` leaves out what `weights.weighed` does (words only: a phrase made only
        of function words was never counted). Raw, every key is there.
        """
        if not self.file.is_file():
            return []
        with closing(self._connect()) as db:
            rows: Iterable[tuple[str, str, int]] = db.execute(
                "SELECT t.key, t.variant, SUM(t.n) FROM tally t JOIN contribution c"
                " ON c.id = t.contribution_id WHERE c.superseded_at IS NULL"
                " AND c.tbl = ? AND c.register = ? GROUP BY t.key, t.variant",
                (table, register),
            ).fetchall()
        totals: dict[str, int] = {}
        for key, variant, n in rows:
            if weighed and table == "words" and not weights.weighed(key, variant):
                continue
            totals[key] = totals.get(key, 0) + int(n)
        return sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:limit]

    def registers(self, table: str) -> dict[str, int]:
        """How many units each register holds a current contribution for, in one table."""
        if not self.file.is_file():
            return {}
        with closing(self._connect()) as db:
            return {
                register: int(n)
                for register, n in db.execute(
                    "SELECT register, COUNT(*) FROM contribution WHERE superseded_at IS NULL"
                    " AND tbl = ? GROUP BY register ORDER BY register",
                    (table,),
                )
            }
