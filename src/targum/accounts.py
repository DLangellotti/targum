"""Who someone is, and everything they have kept.

Until now a reader's vocabulary lived in their browser. That was right while targum was
a thing you ran on your own machine: nothing to sign into, nothing to leak, and the
words sat next to the readers they came from. It stops being right the moment someone
pays monthly for it. A word list that a cleared browser can end is not something to
charge for, it never reaches a second device, and there is no way to back it up.

So this is the other half: a per-person store, and enough identity to know whose it is.

**Identity is a link in an email, never a password.** There is nothing here to steal
that is worth a password's failure modes, and a password is one more thing for someone
who wants to read Hebrew to manage. A link is minted, hashed, mailed, and dies on first
use or after twenty minutes.

**Nothing is stored in the clear that arrives from outside.** Link and session tokens
are held as SHA-256 digests, so a copy of the database does not let anyone in. The
tokens themselves exist only in the email and the cookie.

**Merging is last-write-wins on the client's own clock.** Every record carries `seen`,
the moment the person last touched it, and a write only lands if it is newer than what
is already there. Two devices with badly skewed clocks can therefore lose an edit, which
is the accepted cost of a sync that needs no coordination and no conflict UI. What it
buys is that a phone that has been offline all week can push its week and take everyone
else's without either side having to reason about order.

**Deletes are tombstones.** Taking a word off the list sets `gone`, and the row stays.
Without that, a delete on the laptop is indistinguishable from a word the phone has not
heard of yet, and the phone puts it back on the next sync.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Long enough that guessing is not a strategy, short enough to paste into a browser.
TOKEN_BYTES = 32

# A link is for the person who just asked for it, in the next few minutes. Twenty is
# long enough to switch to a mail client and back, short enough that a link sitting in
# an inbox a month later is not a way in.
LINK_MINUTES = 20

# A session lasts until it is not used. Someone who reads every few days stays signed
# in indefinitely; a browser abandoned for three months does not.
SESSION_DAYS = 90

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS person (
  id       INTEGER PRIMARY KEY,
  email    TEXT    NOT NULL UNIQUE,
  made     INTEGER NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS link (
  hash   TEXT    PRIMARY KEY,
  person INTEGER NOT NULL REFERENCES person(id),
  made   INTEGER NOT NULL,
  used   INTEGER
);

CREATE TABLE IF NOT EXISTS session (
  hash   TEXT    PRIMARY KEY,
  person INTEGER NOT NULL REFERENCES person(id),
  made   INTEGER NOT NULL,
  seen   INTEGER NOT NULL
);

-- A word is one row per person per language per dictionary form. The client keys its
-- own store exactly this way, so nothing has to be reshaped in either direction.
CREATE TABLE IF NOT EXISTS word (
  person   INTEGER NOT NULL,
  language TEXT    NOT NULL,
  lemma    TEXT    NOT NULL,
  surface  TEXT    NOT NULL DEFAULT '',
  status   INTEGER,
  meaning  TEXT    NOT NULL DEFAULT '',
  note     TEXT    NOT NULL DEFAULT '',
  band     TEXT    NOT NULL DEFAULT '',
  at       INTEGER NOT NULL DEFAULT 0,
  seen     INTEGER NOT NULL DEFAULT 0,
  gone     INTEGER NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (person, language, lemma)
);

-- A phrase belongs to the sentence it was cut from, so it carries the document and
-- segment it came from and the span within that segment. `id` is minted by whichever
-- browser first kept it: position in a list is not a name, because deleting the first
-- phrase renames every phrase after it.
CREATE TABLE IF NOT EXISTS phrase (
  person     INTEGER NOT NULL,
  id         TEXT    NOT NULL,
  document   TEXT    NOT NULL DEFAULT '',
  segment    TEXT    NOT NULL DEFAULT '',
  span_start INTEGER NOT NULL DEFAULT 0,
  span_end   INTEGER NOT NULL DEFAULT 0,
  text       TEXT    NOT NULL DEFAULT '',
  status     INTEGER,
  note       TEXT    NOT NULL DEFAULT '',
  meaning    TEXT    NOT NULL DEFAULT '',
  at         INTEGER NOT NULL DEFAULT 0,
  seen       INTEGER NOT NULL DEFAULT 0,
  gone       INTEGER NOT NULL DEFAULT 0,
  revision   INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (person, id)
);

-- Which texts someone has open, and when they last looked at one. The library sorts by
-- it, and the words page uses it to tell which language a phrase belongs to.
CREATE TABLE IF NOT EXISTS doc (
  person   INTEGER NOT NULL,
  hash     TEXT    NOT NULL,
  title    TEXT    NOT NULL DEFAULT '',
  language TEXT    NOT NULL DEFAULT '',
  updated  INTEGER NOT NULL DEFAULT 0,
  opened   INTEGER NOT NULL DEFAULT 0,
  seen     INTEGER NOT NULL DEFAULT 0,
  gone     INTEGER NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (person, hash)
);

CREATE INDEX IF NOT EXISTS word_since   ON word   (person, revision);
CREATE INDEX IF NOT EXISTS phrase_since ON phrase (person, revision);
CREATE INDEX IF NOT EXISTS doc_since    ON doc    (person, revision);
CREATE INDEX IF NOT EXISTS link_person  ON link   (person);
CREATE INDEX IF NOT EXISTS session_seen ON session(seen);
"""


def now() -> int:
    """Milliseconds, because the client's own timestamps are `Date.now()`."""
    return int(time.time() * 1000)


def digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tidy(email: str) -> str:
    """An address in the one form it is stored and compared in.

    Addresses are case-insensitive in practice whatever the RFC permits, and somebody
    signing in from their phone will capitalise the first letter. Two accounts for one
    person is a worse outcome than a rare over-merge.
    """
    return email.strip().lower()


def plausible(email: str) -> bool:
    """Enough of a check to catch a typo, and no more.

    Validating an address properly means sending to it, which is what the next step
    does anyway. This only rejects what cannot possibly be one.
    """
    address = tidy(email)
    if len(address) < 3 or len(address) > 254 or address.count("@") != 1:
        return False
    local, _, host = address.partition("@")
    return bool(local) and "." in host and not host.startswith(".") and not host.endswith(".")


@dataclass(frozen=True)
class Person:
    id: int
    email: str


# The three kinds of thing a person accumulates, and the columns each one syncs. Kept as
# data rather than three near-identical functions, because the merge is the same
# argument three times and the only thing that differs is the shape.
# Fields that default to a number rather than to empty text when nothing is known.
NUMERIC = frozenset({"at", "updated", "opened", "span_start", "span_end"})


@dataclass(frozen=True)
class Kind:
    table: str
    key: tuple[str, ...]
    fields: tuple[str, ...]


KINDS: dict[str, Kind] = {
    "words": Kind(
        table="word",
        key=("language", "lemma"),
        fields=("surface", "status", "meaning", "note", "band", "at"),
    ),
    "phrases": Kind(
        table="phrase",
        key=("id",),
        fields=(
            "document",
            "segment",
            "span_start",
            "span_end",
            "text",
            "status",
            "note",
            "meaning",
            "at",
        ),
    ),
    "docs": Kind(
        table="doc",
        key=("hash",),
        fields=("title", "language", "updated", "opened"),
    ),
}


class Store:
    """The database, and the only thing that touches it.

    One file, opened once per thread. `ThreadingHTTPServer` hands each request to
    whichever thread is free and SQLite connections are not safe to share across
    threads, so the connection is thread-local rather than guarded by a lock: a lock
    would serialise reads that have no reason to wait for each other.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        # Not inside `write()`: executescript issues its own COMMIT first, which ends
        # the transaction out from under whoever opened it.
        self.db.executescript(SCHEMA)
        self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    # -- plumbing ---------------------------------------------------------------

    @property
    def db(self) -> sqlite3.Connection:
        connection = getattr(self._local, "db", None)
        if connection is None:
            connection = sqlite3.connect(self.path, isolation_level=None)
            connection.row_factory = sqlite3.Row
            # Readers do not block the writer, which matters the moment two tabs sync
            # at once. Off by default, and it survives in the file, but setting it on
            # every connection costs nothing and removes a way to get this wrong.
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            self._local.db = connection
        return connection

    class _Transaction:
        def __init__(self, db: sqlite3.Connection) -> None:
            self.db = db

        def __enter__(self) -> sqlite3.Connection:
            self.db.execute("BEGIN IMMEDIATE")
            return self.db

        def __exit__(self, kind: Any, value: Any, trace: Any) -> None:
            if kind is None:
                self.db.execute("COMMIT")
            else:
                self.db.execute("ROLLBACK")

    def write(self) -> Store._Transaction:
        """A write transaction, taken immediately rather than on first write.

        `BEGIN IMMEDIATE` up front turns a lost race into a wait; deferred, the same
        race is an error partway through, after some of the work is done.
        """
        return Store._Transaction(self.db)

    def close(self) -> None:
        connection = getattr(self._local, "db", None)
        if connection is not None:
            connection.close()
            self._local.db = None

    # -- signing in -------------------------------------------------------------

    def person_by_email(self, email: str) -> Person | None:
        row = self.db.execute(
            "SELECT id, email FROM person WHERE email = ?", (tidy(email),)
        ).fetchone()
        return Person(row["id"], row["email"]) if row else None

    def start_sign_in(self, email: str) -> str:
        """Mint a link for this address, making the account if there is not one.

        Signing up and signing in are the same act on purpose. There is no form to
        fill in, nothing to confirm, and no state where an account half exists.
        """
        address = tidy(email)
        token = secrets.token_urlsafe(TOKEN_BYTES)
        with self.write() as db:
            db.execute(
                "INSERT INTO person (email, made) VALUES (?, ?) ON CONFLICT(email) DO NOTHING",
                (address, now()),
            )
            row = db.execute("SELECT id FROM person WHERE email = ?", (address,)).fetchone()
            # Any link minted earlier is void: asking for a new one is what someone does
            # when the first did not arrive, and two live links is one more than needed.
            db.execute("DELETE FROM link WHERE person = ?", (row["id"],))
            db.execute(
                "INSERT INTO link (hash, person, made, used) VALUES (?, ?, ?, NULL)",
                (digest(token), row["id"], now()),
            )
        return token

    def finish_sign_in(self, token: str) -> tuple[Person, str] | None:
        """Spend a link and hand back a session. None if it is spent, stale or wrong."""
        cutoff = now() - LINK_MINUTES * 60 * 1000
        with self.write() as db:
            row = db.execute(
                "SELECT person, made, used FROM link WHERE hash = ?", (digest(token),)
            ).fetchone()
            if row is None or row["used"] is not None or row["made"] < cutoff:
                return None
            db.execute("UPDATE link SET used = ? WHERE hash = ?", (now(), digest(token)))
            who = db.execute(
                "SELECT id, email FROM person WHERE id = ?", (row["person"],)
            ).fetchone()
            session = secrets.token_urlsafe(TOKEN_BYTES)
            db.execute(
                "INSERT INTO session (hash, person, made, seen) VALUES (?, ?, ?, ?)",
                (digest(session), who["id"], now(), now()),
            )
        return Person(who["id"], who["email"]), session

    def whoever(self, session: str | None) -> Person | None:
        """The person holding this session, or nobody.

        Touches `seen`, which is what makes a session last as long as it is used.
        """
        if not session:
            return None
        cutoff = now() - SESSION_DAYS * 24 * 60 * 60 * 1000
        row = self.db.execute(
            "SELECT person.id AS id, person.email AS email, session.seen AS seen"
            " FROM session JOIN person ON person.id = session.person"
            " WHERE session.hash = ?",
            (digest(session),),
        ).fetchone()
        if row is None or row["seen"] < cutoff:
            return None
        # Written at most once a minute: every read of every page would otherwise be a
        # write, and the only thing this timestamp decides is a ninety-day expiry.
        if now() - row["seen"] > 60_000:
            with self.write() as db:
                db.execute("UPDATE session SET seen = ? WHERE hash = ?", (now(), digest(session)))
        return Person(row["id"], row["email"])

    def sign_out(self, session: str | None) -> None:
        if not session:
            return
        with self.write() as db:
            db.execute("DELETE FROM session WHERE hash = ?", (digest(session),))

    def forget(self, person: Person) -> None:
        """Everything about someone, gone. The other half of being allowed to keep it."""
        with self.write() as db:
            for table in ("word", "phrase", "doc"):
                db.execute(f"DELETE FROM {table} WHERE person = ?", (person.id,))
            db.execute("DELETE FROM session WHERE person = ?", (person.id,))
            db.execute("DELETE FROM link WHERE person = ?", (person.id,))
            db.execute("DELETE FROM person WHERE id = ?", (person.id,))

    # -- syncing ----------------------------------------------------------------

    def _next_revision(self, db: sqlite3.Connection, person: Person) -> int:
        db.execute("UPDATE person SET revision = revision + 1 WHERE id = ?", (person.id,))
        row = db.execute("SELECT revision FROM person WHERE id = ?", (person.id,)).fetchone()
        return int(row["revision"])

    def revision(self, person: Person) -> int:
        row = self.db.execute("SELECT revision FROM person WHERE id = ?", (person.id,)).fetchone()
        return int(row["revision"]) if row else 0

    def push(self, person: Person, changes: dict[str, list[dict[str, Any]]]) -> int:
        """Take a browser's changes, keeping whichever version of each record is newer.

        Everything lands in one transaction and under one revision number, so a client
        pulling at the same moment sees either all of a push or none of it. Half a
        push is how a phrase arrives without the document it belongs to.
        """
        with self.write() as db:
            stamp = self._next_revision(db, person)
            for name, items in changes.items():
                kind = KINDS.get(name)
                if kind is None:
                    continue
                for item in items:
                    self._merge(db, person, kind, item, stamp)
            return stamp

    def _merge(
        self,
        db: sqlite3.Connection,
        person: Person,
        kind: Kind,
        item: dict[str, Any],
        stamp: int,
    ) -> None:
        key = tuple(str(item.get(name, "")) for name in kind.key)
        if not all(key):
            return  # a record with no name is not a record
        seen = int(item.get("seen") or item.get("at") or 0)
        where = " AND ".join(f"{name} = ?" for name in kind.key)
        existing = db.execute(
            f"SELECT * FROM {kind.table} WHERE person = ? AND {where}", (person.id, *key)
        ).fetchone()
        # The whole of the merge rule, in one line: an older edit does not overwrite a
        # newer one, whichever browser it came from and whichever order they arrive in.
        if existing is not None and int(existing["seen"]) >= seen:
            return

        # A field the push does not mention keeps whatever is already stored, rather
        # than reverting to a default. Clients send whole records, so this should never
        # fire — but the cost of being wrong about that is a browser quietly erasing a
        # meaning somebody typed on another device, and the cost of the guard is a
        # dictionary lookup.
        def value(name: str) -> Any:
            if name in item:
                return item[name]
            if existing is not None:
                return existing[name]
            return None if name == "status" else (0 if name in NUMERIC else "")

        columns = ["person", *kind.key, *kind.fields, "seen", "gone", "revision"]
        row = [
            person.id,
            *key,
            *(value(name) for name in kind.fields),
            seen,
            1 if item.get("gone") else 0,
            stamp,
        ]
        marks = ", ".join("?" for _ in columns)
        db.execute(
            f"INSERT OR REPLACE INTO {kind.table} ({', '.join(columns)}) VALUES ({marks})",
            row,
        )

    def pull(self, person: Person, since: int = 0) -> dict[str, Any]:
        """Everything that changed after `since`, and the revision that reaches.

        A client that has never synced passes 0 and gets the lot. One that synced a
        minute ago passes what it got back then and gets almost nothing, which is what
        makes it reasonable to do this on every page load.
        """
        out: dict[str, Any] = {"revision": self.revision(person)}
        for name, kind in KINDS.items():
            columns = [*kind.key, *kind.fields, "seen", "gone"]
            rows = self.db.execute(
                f"SELECT {', '.join(columns)} FROM {kind.table}"
                " WHERE person = ? AND revision > ? ORDER BY revision",
                (person.id, since),
            ).fetchall()
            out[name] = [dict(row) for row in rows]
        return out

    def counts(self, person: Person) -> dict[str, int]:
        """What someone has, for the sake of saying so on the page."""
        out = {}
        for name, kind in KINDS.items():
            row = self.db.execute(
                f"SELECT COUNT(*) AS n FROM {kind.table} WHERE person = ? AND gone = 0",
                (person.id,),
            ).fetchone()
            out[name] = int(row["n"])
        return out

    # -- housekeeping -----------------------------------------------------------

    def sweep(self) -> None:
        """Drop what has expired. Cheap, and safe to call whenever."""
        with self.write() as db:
            db.execute("DELETE FROM link WHERE made < ?", (now() - LINK_MINUTES * 60 * 1000,))
            db.execute(
                "DELETE FROM session WHERE seen < ?",
                (now() - SESSION_DAYS * 24 * 60 * 60 * 1000,),
            )
