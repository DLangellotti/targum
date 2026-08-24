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
GRACE_DAYS = 7
# Asking for a link is the one thing anyone can do without an account, and every ask
# sends mail to an address the asker chose. Enough for someone who mistyped their own
# address twice and is trying again; not enough to use targum as a way to post mail
# into somebody else's inbox.
ASKS_PER_HOUR = 5
SESSION_DAYS = 90

# 2: person.leaving, for a deletion that waits out a grace period.
# 3: job.spent, what a build really cost once the API said so.
# 4: job.chapters, how a text divides — one means it is not a book.
SCHEMA_VERSION = 4

# Columns added to tables that already exist on somebody's disk. `CREATE TABLE IF NOT
# EXISTS` does nothing to a table that is already there, so a new column has to be added
# by hand or the first query naming it fails against every database but a brand new one
# — which is exactly what a test suite full of temporary files does not catch.
# Who may open an account. Hosted, an address has to be here first — see `may_join`.
# A table rather than an environment variable so the list survives a redeploy, gets
# backed up with everything else, and can be changed without one.
INVITED = """
CREATE TABLE IF NOT EXISTS invited (
  email TEXT PRIMARY KEY,
  at    INTEGER NOT NULL
);
"""

MIGRATIONS: tuple[str, ...] = (
    "ALTER TABLE person ADD COLUMN leaving INTEGER",
    # Which shelf somebody reads. On the account rather than in the browser, because
    # sign-out deletes every `targum:*` key but the theme — deliberately — so a local
    # preference would be forgotten every time they signed out on their own machine.
    "ALTER TABLE person ADD COLUMN shelf TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE job ADD COLUMN spent REAL NOT NULL DEFAULT 0",
    "ALTER TABLE job ADD COLUMN chapters INTEGER NOT NULL DEFAULT 1",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS person (
  id       INTEGER PRIMARY KEY,
  email    TEXT    NOT NULL UNIQUE,
  made     INTEGER NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0,
  -- When they asked to be forgotten. Everything goes at the end of the grace period;
  -- until then they are signed out and the account is unusable, so the only thing the
  -- delay buys is the chance to undo a mistake.
  leaving  INTEGER
);

-- How often an address has asked for a link. A sign-in endpoint that anyone can call
-- is a way to send mail from someone else's domain to someone else's inbox.
CREATE TABLE IF NOT EXISTS asked (
  who   TEXT    NOT NULL,
  made  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS asked_when ON asked (who, made);

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

-- The work queue. Builds used to live in a dictionary on the server and money spent
-- in a float beside it, so a restart lost every running build and handed the budget
-- back to whoever asked next. Both belong on disk, and `claimed` is the whole spend
-- accounting: what is still committed is the sum of it, so there is no second counter
-- to drift away from the truth.
CREATE TABLE IF NOT EXISTS job (
  id       TEXT    PRIMARY KEY,
  owner    INTEGER,
  home     TEXT    NOT NULL,
  source   TEXT    NOT NULL,
  options  TEXT    NOT NULL DEFAULT '{}',
  stage    TEXT    NOT NULL DEFAULT 'reading',
  title    TEXT    NOT NULL DEFAULT '',
  language TEXT    NOT NULL DEFAULT '',
  segments INTEGER NOT NULL DEFAULT 0,
  chapters INTEGER NOT NULL DEFAULT 1,
  estimate REAL    NOT NULL DEFAULT 0,
  done     INTEGER NOT NULL DEFAULT 0,
  total    INTEGER NOT NULL DEFAULT 0,
  message  TEXT    NOT NULL DEFAULT '',
  error    TEXT    NOT NULL DEFAULT '',
  reader   TEXT    NOT NULL DEFAULT '',
  lemmas   INTEGER NOT NULL DEFAULT 0,
  meanings REAL    NOT NULL DEFAULT 0,
  blocked  TEXT    NOT NULL DEFAULT '',
  claimed  REAL    NOT NULL DEFAULT 0,
  spent    REAL    NOT NULL DEFAULT 0,
  made     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS word_since   ON word   (person, revision);
CREATE INDEX IF NOT EXISTS phrase_since ON phrase (person, revision);
CREATE INDEX IF NOT EXISTS job_claimed  ON job    (claimed);
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
    # "" means they have not chosen, which is not the same as choosing the Library:
    # the switcher shows both until somebody says otherwise.
    shelf: str = ""


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
        self.db.executescript(INVITED)
        self._migrate()
        self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _migrate(self) -> None:
        """Bring a database written by an older targum up to date.

        Every statement runs every time, and each is written to fail harmlessly when it
        has already been applied. The obvious alternative — skip anything at or below
        the recorded version — was here first and was a trap: a migration that is added
        but never reached still lets the version stamp advance, and the file is then
        marked as migrated while missing a column. That failure is silent until the
        first query naming the column, which is a long way from the cause.

        A few no-op ALTERs on open cost nothing and cannot get this wrong.
        """
        for statement in MIGRATIONS:
            try:
                self.db.execute(statement)
            except sqlite3.OperationalError as error:
                if "duplicate column" not in str(error).lower():
                    raise

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

    def anyone(self) -> bool:
        """Whether anybody has an account here at all.

        The question behind it is what "signed out" means. On a machine nobody has ever
        signed up on, it means nothing — there is one person, it is theirs, and asking
        them to make an account to read their own files would be absurd. Once an account
        exists, the machine is being used as targum-with-accounts and signing out is a
        thing somebody chose to do.
        """
        return self.db.execute("SELECT 1 FROM person LIMIT 1").fetchone() is not None

    def person_by_email(self, email: str) -> Person | None:
        row = self.db.execute(
            "SELECT id, email, shelf FROM person WHERE email = ?", (tidy(email),)
        ).fetchone()
        return Person(row["id"], row["email"], row["shelf"] or "") if row else None

    def asking_too_often(self, who: str, limit: int = ASKS_PER_HOUR) -> bool:
        """Whether this address has asked for too many links in the last hour.

        Recorded per address rather than per connection: an address is the thing that
        receives the mail, and it is the inbox being protected.
        """
        window = now() - 60 * 60 * 1000
        with self.write() as db:
            db.execute("DELETE FROM asked WHERE made < ?", (window,))
            row = db.execute(
                "SELECT COUNT(*) AS n FROM asked WHERE who = ? AND made >= ?", (tidy(who), window)
            ).fetchone()
            if int(row["n"]) >= limit:
                return True
            db.execute("INSERT INTO asked (who, made) VALUES (?, ?)", (tidy(who), now()))
            return False

    def invite(self, email: str) -> str:
        """Let one address open an account. Returns the address as it was stored."""
        address = tidy(email)
        if not address:
            raise ValueError("No address given.")
        with self.write() as db:
            db.execute(
                "INSERT INTO invited (email, at) VALUES (?, ?) ON CONFLICT(email) DO NOTHING",
                (address, now()),
            )
        return address

    def uninvite(self, email: str) -> bool:
        """Take an address off the list. Any account it already has is untouched.

        Deliberately: this decides who may *join*, and someone who has been reading for a
        month should not be locked out of their own words by an edit to a guest list.
        Use `forget` to remove a person.
        """
        with self.write() as db:
            return db.execute("DELETE FROM invited WHERE email = ?", (tidy(email),)).rowcount > 0

    def invitations(self) -> list[str]:
        return [row["email"] for row in self.db.execute("SELECT email FROM invited ORDER BY at")]

    def may_join(self, email: str) -> bool:
        """Whether this address may open an account here.

        Called only in hosted mode. An empty list therefore means *nobody* rather than
        everybody, which is the safe way round: standing a box up on a public address
        with a funded API key should not, by default, let whoever finds it spend money.
        The first invitation comes from the command line on the box itself, which makes
        having the box the root of the whole thing.
        """
        address = tidy(email)
        if not address:
            return False
        found = self.db.execute("SELECT 1 FROM invited WHERE email = ?", (address,)).fetchone()
        return found is not None

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

    def peek_sign_in(self, token: str) -> Person | None:
        """Who this link would sign in, without spending it.

        The landing page has to say whose account it is before anyone presses the
        button, and reading must not be the thing that consumes the link — that is the
        whole reason the link stopped being a plain GET.
        """
        cutoff = now() - LINK_MINUTES * 60 * 1000
        row = self.db.execute(
            "SELECT person.id AS id, person.email AS email, person.shelf AS shelf FROM link "
            "JOIN person ON person.id = link.person "
            "WHERE link.hash = ? AND link.used IS NULL AND link.made >= ? "
            "AND person.leaving IS NULL",
            (digest(token), cutoff),
        ).fetchone()
        return Person(row["id"], row["email"], row["shelf"] or "") if row else None

    def finish_sign_in(self, token: str) -> tuple[Person, str] | None:
        """Spend a link and hand back a session. None if it is spent, stale or wrong."""
        cutoff = now() - LINK_MINUTES * 60 * 1000
        with self.write() as db:
            row = db.execute(
                "SELECT person, made, used FROM link WHERE hash = ?", (digest(token),)
            ).fetchone()
            if row is None or row["used"] is not None or row["made"] < cutoff:
                return None
            leaving = db.execute(
                "SELECT leaving FROM person WHERE id = ?", (row["person"],)
            ).fetchone()
            if leaving is None or leaving["leaving"] is not None:
                return None
            db.execute("UPDATE link SET used = ? WHERE hash = ?", (now(), digest(token)))
            who = db.execute(
                "SELECT id, email, shelf FROM person WHERE id = ?", (row["person"],)
            ).fetchone()
            session = secrets.token_urlsafe(TOKEN_BYTES)
            db.execute(
                "INSERT INTO session (hash, person, made, seen) VALUES (?, ?, ?, ?)",
                (digest(session), who["id"], now(), now()),
            )
        return Person(who["id"], who["email"], who["shelf"] or ""), session

    def whoever(self, session: str | None) -> Person | None:
        """The person holding this session, or nobody.

        Touches `seen`, which is what makes a session last as long as it is used.
        """
        if not session:
            return None
        cutoff = now() - SESSION_DAYS * 24 * 60 * 60 * 1000
        row = self.db.execute(
            "SELECT person.id AS id, person.email AS email, person.shelf AS shelf,"
            " session.seen AS seen"
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
        return Person(row["id"], row["email"], row["shelf"] or "")

    def choose_shelf(self, person: Person, shelf: str) -> None:
        """Remember which room somebody reads in.

        Only the two known values, and "" for undecided. Anything else would be a route
        that does not exist, arriving from a request — so it is refused rather than
        stored and puzzled over later.
        """
        if shelf not in ("", "library", "beit-midrash"):
            raise ValueError(f"No such shelf: {shelf!r}")
        with self.write() as db:
            db.execute("UPDATE person SET shelf = ? WHERE id = ?", (shelf, person.id))

    def sign_out(self, session: str | None) -> None:
        if not session:
            return
        with self.write() as db:
            db.execute("DELETE FROM session WHERE hash = ?", (digest(session),))

    def forget(self, person: Person) -> None:
        """Start forgetting someone. The other half of being allowed to keep it.

        Nothing is deleted yet. They are signed out of everywhere, the account stops
        working, and the data goes at the end of the grace period. Deleting an account
        is one click on a bad day, and the only thing that makes that safe is time.
        """
        with self.write() as db:
            db.execute("UPDATE person SET leaving = ? WHERE id = ?", (now(), person.id))
            db.execute("DELETE FROM session WHERE person = ?", (person.id,))
            db.execute("DELETE FROM link WHERE person = ?", (person.id,))

    def stay(self, person: Person) -> None:
        """Change their mind, while there is still something to change it about."""
        with self.write() as db:
            db.execute("UPDATE person SET leaving = NULL WHERE id = ?", (person.id,))

    def purge(self, days: int = GRACE_DAYS) -> list[int]:
        """Delete everyone whose grace period is up, and say whose files still stand.

        The store knows nothing about the output directory, so the rows go here and the
        ids come back for the caller to finish the job on disk.
        """
        cutoff = now() - days * 24 * 60 * 60 * 1000
        with self.write() as db:
            rows = db.execute(
                "SELECT id FROM person WHERE leaving IS NOT NULL AND leaving < ?", (cutoff,)
            ).fetchall()
            gone = [int(row["id"]) for row in rows]
            for person_id in gone:
                for table in ("word", "phrase", "doc", "session", "link"):
                    db.execute(f"DELETE FROM {table} WHERE person = ?", (person_id,))
                db.execute("DELETE FROM person WHERE id = ?", (person_id,))
        return gone

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

    def everything(self, person: Person) -> dict[str, Any]:
        """Everything targum holds about one person, for them to take away.

        The point is that it needs nobody's help: somebody who wants their data should
        not have to ask the person who runs the server for it.

        Complete except for one deliberate omission. Sessions and sign-in links are
        credentials, not data — writing them into a file somebody downloads, mails to
        themselves and leaves in a downloads folder would be handing out live keys to
        their own account. What is here is everything they wrote or caused.
        """
        account = self.db.execute(
            "SELECT email, made, shelf FROM person WHERE id = ?", (person.id,)
        ).fetchone()
        out: dict[str, Any] = {
            "account": {
                "email": account["email"],
                "joined": account["made"],
                "shelf": account["shelf"] or "",
            },
            "exported": now(),
        }
        for name, kind in KINDS.items():
            columns = [*kind.key, *kind.fields, "seen"]
            rows = self.db.execute(
                f"SELECT {', '.join(columns)} FROM {kind.table}"
                " WHERE person = ? AND gone = 0 ORDER BY at DESC"
                if "at" in kind.fields
                else f"SELECT {', '.join(columns)} FROM {kind.table} WHERE person = ? AND gone = 0",
                (person.id,),
            ).fetchall()
            out[name] = [dict(row) for row in rows]

        # What they built, and what it cost. Theirs as much as their words are, and the
        # only place the spend is written down.
        out["builds"] = [
            dict(row)
            for row in self.db.execute(
                "SELECT source, title, language, stage, spent, made FROM job"
                " WHERE owner = ? ORDER BY made DESC",
                (person.id,),
            )
        ]
        return out

    def marked(self, person: Person, language: str) -> dict[str, int]:
        """Every dictionary form this person has marked in one language, and how well.

        One query per language rather than one per text: a shelf of twenty books in Hebrew
        asks this once and measures all twenty against the answer.
        """
        rows = self.db.execute(
            "SELECT lemma, status FROM word WHERE person = ? AND language = ? AND gone = 0",
            (person.id, language.split("-")[0].lower()),
        )
        return {row["lemma"]: row["status"] for row in rows if row["status"] is not None}

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
            db.execute("DELETE FROM asked WHERE made < ?", (now() - 60 * 60 * 1000,))

    # -- the work queue ---------------------------------------------------------

    def save_job(self, fields: dict[str, Any]) -> None:
        """Write a build's whole state, so a restart can say what became of it."""
        columns = ", ".join(fields)
        holes = ", ".join("?" for _ in fields)
        updates = ", ".join(f"{name} = excluded.{name}" for name in fields if name != "id")
        with self.write() as db:
            db.execute(
                f"INSERT INTO job ({columns}) VALUES ({holes}) "
                f"ON CONFLICT(id) DO UPDATE SET {updates}",
                tuple(fields.values()),
            )

    def jobs(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM job ORDER BY made").fetchall()
        return [dict(row) for row in rows]

    def committed(self, since: int, owner: int | None = -1) -> float:
        """What is still spoken for, counting only the window the budget covers.

        Derived rather than kept: a separate running total is a second source of truth,
        and the two drift the first time a process dies between updating them.

        `owner` of -1 means everyone — the whole box, which is the ceiling that keeps
        one machine from running away. Anything else is that one account.
        """
        if owner == -1:
            row = self.db.execute(
                "SELECT COALESCE(SUM(claimed), 0) AS spent FROM job "
                "WHERE claimed > 0 AND made >= ?",
                (since,),
            ).fetchone()
        else:
            row = self.db.execute(
                "SELECT COALESCE(SUM(claimed), 0) AS spent FROM job "
                "WHERE claimed > 0 AND made >= ? AND owner IS ?",
                (since, owner),
            ).fetchone()
        return float(row["spent"])

    def claim(
        self,
        job_id: str,
        amount: float,
        ceiling: float,
        since: int,
        *,
        owner: int | None = None,
        per_account: float | None = None,
    ) -> str:
        """Take money from both budgets, or say which one refused — in one transaction.

        Two builds starting together would otherwise both read the same balance and
        both pass, which is exactly how a budget is overrun. `BEGIN IMMEDIATE` makes
        the second one wait rather than race, and it holds across processes as well as
        threads, which a lock in one server never did.

        Two ceilings, because they stop different things. The per-account one is what a
        reader is allowed; the whole-box one is what stops every reader at once from
        emptying the card, and no per-account limit can do that on its own.
        """
        with self.write() as db:
            if per_account is not None:
                mine = db.execute(
                    "SELECT COALESCE(SUM(claimed), 0) AS spent FROM job "
                    "WHERE claimed > 0 AND made >= ? AND owner IS ?",
                    (since, owner),
                ).fetchone()
                if float(mine["spent"]) + amount > per_account:
                    return "account"
            row = db.execute(
                "SELECT COALESCE(SUM(claimed), 0) AS spent FROM job "
                "WHERE claimed > 0 AND made >= ?",
                (since,),
            ).fetchone()
            if float(row["spent"]) + amount > ceiling:
                return "everyone"
            db.execute("UPDATE job SET claimed = ? WHERE id = ?", (amount, job_id))
            return ""

    def settle(self, job_id: str, spent: float) -> None:
        """Replace what a build reserved with what it really cost.

        Claiming takes the estimate up front, because the decision to allow a build has
        to be made before it runs. Settling is the other half: once the API has said
        what it charged, the ledger holds that instead of a guess, and the budget stops
        being an approximation of itself.
        """
        with self.write() as db:
            db.execute("UPDATE job SET claimed = ?, spent = ? WHERE id = ?", (spent, spent, job_id))

    def unclaim(self, job_id: str) -> None:
        """Give back what a failed build never spent."""
        with self.write() as db:
            db.execute("UPDATE job SET claimed = 0 WHERE id = ?", (job_id,))

    def interrupt_running(self) -> list[str]:
        """Mark builds that were mid-flight when the process died.

        Called once at start-up. A build cannot be resumed from the middle — the work
        happened in a thread that no longer exists — but it can be told the truth about
        itself instead of sitting at "working" forever.

        **Its claim is kept, deliberately.** A build that was working had very likely
        started paying for batches, and nothing on disk records how much, because usage
        is not plumbed through yet. Releasing the claim would hand the budget back for
        money that really was spent, so a crash loop could spend without limit — which
        is the hole this whole change exists to close. Over-counting a build that died
        early costs a reader one refusal; under-counting costs money. The claim ages out
        of the window on its own within the day.
        """
        with self.write() as db:
            rows = db.execute("SELECT id FROM job WHERE stage = 'working'").fetchall()
            db.execute(
                "UPDATE job SET stage = 'failed', error = ? WHERE stage = 'working'",
                (
                    "targum restarted while this was building. Start it again — "
                    "anything already translated is cached, so it will not be paid for twice.",
                ),
            )
        return [row["id"] for row in rows]
