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
import re
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
# 5: the day table, which days somebody read on. A new table rather than a new column,
#    so it needs no entry in MIGRATIONS below: `CREATE TABLE IF NOT EXISTS` does add a
#    table that is not there yet, and it is only columns on existing tables it skips.
# 6: who a person is beyond an address — a display name and a picture. Reading
#    preferences rode along here for a day and were taken out again: a setting that
#    lives in two places is a setting that can disagree with itself. They stay in the
#    browser. A database that ran the old migration keeps two unused columns, which is
#    cheaper than another migration to drop them.
# 7: word.learned — whether a word was saved at a level below known and got there. It
#    is the difference between a word targum taught somebody and a word they already had
#    and ticked off, and it cannot be worked out after the fact from status and dates.
# 8: the meaning table — a meaning belongs to a language pair, a word to a language — and
#    the reads table, an allowlist of which languages an address may be translated into.
# 9: the chosen table, which replaces that allowlist with the person's own answer: what
#    they are learning and what they read into. The objection at 6 still stands and this
#    is not a second place for the setting — it is the one place, and the browser keeps a
#    copy of it the way it keeps a copy of the words. Old `reads` rows are read across
#    once for anybody who has signed in; the table stays on disk, empty of meaning.
#
# Not to be confused with `models.SCHEMA_VERSION`, which is a cache key: bumping that one
# invalidates every stage and forces paid re-translation of every text. This one versions
# the sqlite file behind an account and costs a column.
SCHEMA_VERSION = 10

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

# Who is not a reader but the person running the box. An address here is exempt from the
# per-account spend rails — see `serve.Library.claim` — because the limits exist to stop
# a reader running up somebody else's bill, and the person paying it is not that reader.
#
# An address rather than a column on `person`, for the same reason `invited` is a table:
# it has to be settable before anybody has signed in, and it has to survive `uninvite`,
# which deliberately leaves an existing account alone. Nobody's own address is written
# down here in the source — this repository is public — so the first admin is made from
# the command line on the box, the same way the first invitation is.
ADMIN = """
CREATE TABLE IF NOT EXISTS admin (
  email TEXT PRIMARY KEY,
  at    INTEGER NOT NULL
);

-- The allowlist `chosen` replaced: which languages an address had been marked as
-- reading, from the command line. Still created so the migration below has something
-- to read on a database that never had it; nothing writes here any more.
CREATE TABLE IF NOT EXISTS reads (
  email    TEXT NOT NULL,
  language TEXT NOT NULL,
  at       INTEGER NOT NULL,
  PRIMARY KEY (email, language)
);
"""

# What a person said about their languages: which they are learning, and which they read
# well enough to be handed a translation in. The reader's own answer, from the profile
# page, where the `reads` table above was somebody else's answer from a terminal.
#
# Keyed by person rather than by address, unlike `admin` and `invited`: those say
# something about an address before anybody has signed in, and a preference cannot
# exist before its owner does. One row per language per kind; the next language is a
# row. Absent means the default — see `learning` and `reads` on the store.
CHOSEN = """
CREATE TABLE IF NOT EXISTS chosen (
  person   INTEGER NOT NULL,
  kind     TEXT    NOT NULL,
  language TEXT    NOT NULL,
  at       INTEGER NOT NULL,
  PRIMARY KEY (person, kind, language)
);
"""

MIGRATIONS: tuple[str, ...] = (
    "ALTER TABLE person ADD COLUMN leaving INTEGER",
    "ALTER TABLE job ADD COLUMN spent REAL NOT NULL DEFAULT 0",
    "ALTER TABLE job ADD COLUMN chapters INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE person ADD COLUMN name TEXT NOT NULL DEFAULT ''",
    # A URL, for the day a sign-in provider hands one over. Empty until then, and the
    # avatar falls back to initials — which is what it draws either way when the picture
    # will not load.
    "ALTER TABLE person ADD COLUMN picture TEXT NOT NULL DEFAULT ''",
    # Whether a word was worked up to known from a level below it, rather than ticked off
    # as already known. Nothing can recover this for words marked before it existed, so
    # it starts at nought for everybody and counts forward.
    "ALTER TABLE word ADD COLUMN learned INTEGER NOT NULL DEFAULT 0",
    # When the reader said they had finished a text, or 0. One press at the foot of the
    # last part; pressing again takes it back, so a text is finished once however often
    # the button is pressed. Synced and exported with the rest of what they did.
    "ALTER TABLE doc ADD COLUMN done INTEGER NOT NULL DEFAULT 0",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS person (
  id         INTEGER PRIMARY KEY,
  email      TEXT    NOT NULL UNIQUE,
  made       INTEGER NOT NULL,
  revision   INTEGER NOT NULL DEFAULT 0,
  -- What to call them and what to show, neither of which an email can answer. Both
  -- empty until somebody says otherwise; the avatar draws initials in the meantime.
  name       TEXT    NOT NULL DEFAULT '',
  picture    TEXT    NOT NULL DEFAULT '',
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
  learned  INTEGER NOT NULL DEFAULT 0,
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
  done     INTEGER NOT NULL DEFAULT 0,
  seen     INTEGER NOT NULL DEFAULT 0,
  gone     INTEGER NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (person, hash)
);

-- What a word or a phrase means, to somebody reading one language in another.
--
-- A word belongs to a language; a meaning belongs to a language pair. `word.meaning` was
-- one slot for a fact that has an answer per language, and the merge below is
-- last-write-wins on a whole row — so a reader with an English text and a Russian one had
-- two devices overwriting each other's meanings under a rule that could not tell them
-- apart. Splitting the meaning off leaves the word, its level and every count that reads
-- them exactly where they were: a Hebrew word known is a Hebrew word, whichever language
-- it was learned through.
--
-- `term` is a dictionary form, or `phrase:<id>` for what a kept phrase reads as. One
-- table rather than two: it is the same fact about the same pair, and a second table for
-- a handful of rows is furniture. `note` is here beside `meaning` because a note is a
-- meaning the reader wrote themselves, and one written in Russian is no more use on an
-- English page than a Russian gloss would be.
CREATE TABLE IF NOT EXISTS meaning (
  person   INTEGER NOT NULL,
  source   TEXT    NOT NULL,
  target   TEXT    NOT NULL,
  term     TEXT    NOT NULL,
  meaning  TEXT    NOT NULL DEFAULT '',
  note     TEXT    NOT NULL DEFAULT '',
  at       INTEGER NOT NULL DEFAULT 0,
  seen     INTEGER NOT NULL DEFAULT 0,
  gone     INTEGER NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (person, source, target, term)
);

-- The days somebody read on. One row per calendar day, and the day is the reader's own
-- local one rather than UTC, because "did I read yesterday" is a question about the
-- reader's evening and not about Greenwich.
--
-- `count` is always 1. It is presence, not a tally: `_merge` below is last-write-wins on
-- `seen`, so a real per-day count would be lost the moment two devices both read on the
-- same day and the second one pushed a smaller number. A constant makes the merge
-- harmless, and how many times you opened a text on a Tuesday is not something anything
-- asks. `gone` is carried because the generic sync code selects it; nothing ever sets
-- it, because a day that happened cannot un-happen.
CREATE TABLE IF NOT EXISTS day (
  person   INTEGER NOT NULL,
  day      TEXT    NOT NULL,
  count    INTEGER NOT NULL DEFAULT 0,
  seen     INTEGER NOT NULL DEFAULT 0,
  gone     INTEGER NOT NULL DEFAULT 0,
  revision INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (person, day)
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
CREATE INDEX IF NOT EXISTS meaning_since ON meaning (person, revision);
CREATE INDEX IF NOT EXISTS job_claimed  ON job    (claimed);
CREATE INDEX IF NOT EXISTS doc_since    ON doc    (person, revision);
CREATE INDEX IF NOT EXISTS day_since    ON day    (person, revision);
CREATE INDEX IF NOT EXISTS link_person  ON link   (person);
CREATE INDEX IF NOT EXISTS session_seen ON session(seen);

-- Who asked for the weekly issue. Deliberately not a person: a subscriber has no
-- account, no words and no library, and nothing here may turn into one. The two are
-- joined by an address and by nothing else, which is the point — unsubscribing must not
-- touch an account, and closing an account must not leave targum still mailing them.
--
-- Schema 10 adds this. It is a new table, so `CREATE TABLE IF NOT EXISTS` is the whole
-- of it and MIGRATIONS gets nothing: that list is for columns on tables already sitting
-- on somebody's disk.
CREATE TABLE IF NOT EXISTS subscriber (
  email   TEXT    PRIMARY KEY,
  -- pending until the address is confirmed, on once it is, off once they stop. A row
  -- is never deleted: "they asked to stop" and "they were never here" are different
  -- facts, and only one of them means it is safe to mail again.
  state   TEXT    NOT NULL DEFAULT 'pending',
  -- Hashed, like a sign-in link, because it grants "yes, mail this address".
  confirm TEXT,
  -- In the clear, and deliberately asymmetric with the line above. Its only power is to
  -- stop mail to its own address, and hashing it would make it unmintable at send time —
  -- every issue carries an unsubscribe link, so the token has to be readable to be put
  -- in one. The worst it allows somebody who can read this table is unsubscribing an
  -- address they can already see, which is strictly less than they can already do.
  stop    TEXT    NOT NULL,
  asked   INTEGER NOT NULL,
  joined  INTEGER NOT NULL DEFAULT 0,
  ended   INTEGER NOT NULL DEFAULT 0,
  -- When the last issue went, and which one it was. Together these are what make a
  -- resumed mailout skip whoever already has it: a run that re-sends the whole list is
  -- the failure that costs a sending domain its reputation.
  sent    INTEGER NOT NULL DEFAULT 0,
  issue   TEXT    NOT NULL DEFAULT '',
  bounces INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS subscriber_state ON subscriber (state);
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
    #: Whether the spend rails apply to them. Resolved from the `admin` table when the
    #: person is loaded, rather than stored on the row: it is a fact about who runs the
    #: box, not about the account.
    admin: bool = False


# The four kinds of thing a person accumulates, and the columns each one syncs. Kept as
# data rather than four near-identical functions, because the merge is the same
# argument four times and the only thing that differs is the shape.
# Fields that default to a number rather than to empty text when nothing is known.
NUMERIC = frozenset({"at", "updated", "opened", "done", "span_start", "span_end", "count"})


def initials(name: str, email: str) -> str:
    """One or two letters for an avatar, from whatever there is to go on.

    A name gives its first letters; an address gives the first letter of the part before
    the @, and the letter after a dot or underscore where the address has one — which is
    how most people's addresses are shaped, and it turns djlangellotti into DL rather
    than into D.
    """
    words = [word for word in str(name).split() if word]
    if words:
        return "".join(word[0] for word in words[:2]).upper()
    local = str(email).split("@")[0]
    parts = [part for part in re.split(r"[._-]+", local) if part]
    if len(parts) > 1:
        return (parts[0][0] + parts[1][0]).upper()
    return local[:2].upper() if local else "?"


@dataclass(frozen=True)
class Kind:
    table: str
    key: tuple[str, ...]
    fields: tuple[str, ...]


KINDS: dict[str, Kind] = {
    "words": Kind(
        table="word",
        key=("language", "lemma"),
        fields=("surface", "status", "meaning", "note", "band", "learned", "at"),
    ),
    "meanings": Kind(
        table="meaning",
        key=("source", "target", "term"),
        fields=("meaning", "note", "at"),
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
        fields=("title", "language", "updated", "opened", "done"),
    ),
    # A set, written as a table. The day string is the whole record; see the `day` table
    # above for why the count beside it is always 1.
    "days": Kind(table="day", key=("day",), fields=("count",)),
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
        self.db.executescript(ADMIN)
        self.db.executescript(CHOSEN)
        self._migrate()
        self._adopt_reads()
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

    def _adopt_reads(self) -> None:
        """Carry the old allowlist across as the person's own choice.

        A marking on an address that has since signed in becomes that person's
        `reading` rows — with English beside it, because the allowlist always offered
        English and a Russian-only row read across on its own would take it away. An
        address nobody has signed in with is left where it is: they get the default when
        they arrive and tick Russian themselves.

        Runs on every open and does nothing the second time: the insert ignores rows
        that are already there, and a person who has since unticked a language has
        rows of their own that say so — which is why this only writes for a person
        with no `reading` rows at all.
        """
        with self.write() as db:
            marked = db.execute(
                "SELECT person.id AS id, reads.language AS language"
                " FROM reads JOIN person ON person.email = reads.email"
                " WHERE NOT EXISTS ("
                "   SELECT 1 FROM chosen WHERE chosen.person = person.id AND kind = 'reading')"
            ).fetchall()
            for row in marked:
                for code in (str(row["language"]), "en"):
                    db.execute(
                        "INSERT OR IGNORE INTO chosen (person, kind, language, at)"
                        " VALUES (?, 'reading', ?, ?)",
                        (int(row["id"]), code, now()),
                    )

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

    def person_by_id(self, person_id: int) -> Person | None:
        """Who a job belongs to. The thread that ran it has no session to ask."""
        row = self.db.execute("SELECT id, email FROM person WHERE id = ?", (person_id,)).fetchone()
        return Person(row["id"], row["email"], self.is_admin(row["email"])) if row else None

    def person_by_email(self, email: str) -> Person | None:
        row = self.db.execute(
            "SELECT id, email FROM person WHERE email = ?", (tidy(email),)
        ).fetchone()
        return Person(row["id"], row["email"], self.is_admin(row["email"])) if row else None

    # -- who somebody is ---------------------------------------------------

    #: Longest display name kept. Room for any real name; short enough that a corner
    #: pill and a greeting cannot be made to hold a paragraph.
    NAME_LIMIT = 60

    def profile(self, person: Person) -> dict[str, Any]:
        """Who this person is, for the corner and the profile page.

        Read separately from `Person` rather than folded into it: a Person is the answer
        to "who is asking", which every request needs, and this is the answer to "who are
        they", which two pages need.
        """
        row = self.db.execute(
            "SELECT email, name, picture, made FROM person WHERE id = ?", (person.id,)
        ).fetchone()
        if row is None:
            return {}
        return {
            "email": row["email"],
            "name": row["name"],
            "picture": row["picture"],
            "initials": initials(row["name"], row["email"]),
            "since": row["made"],
        }

    def rename(self, person: Person, name: str) -> str:
        """Set what to call them, and return what was stored.

        Empty is allowed and means "go back to having none": the avatar falls back to the
        address, which is what it did before anybody typed anything.
        """
        tidied = " ".join(str(name).split())[: self.NAME_LIMIT]
        with self.write() as db:
            db.execute("UPDATE person SET name = ? WHERE id = ?", (tidied, person.id))
        return tidied

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

    # -- the weekly ------------------------------------------------------------
    #
    # A subscriber is not an account and never becomes one. Different table, no foreign
    # key, no `person` row, `invited` untouched, and the mail carries no sign-in link —
    # only the public issue and the way out. The one thing the two share is an address,
    # which is what makes the pleasant case work by itself: somebody who subscribed
    # signed out and later opens an account finds the box already ticked, because both
    # doors write the same row.

    def following(self, email: str) -> bool:
        address = tidy(email)
        row = self.db.execute("SELECT state FROM subscriber WHERE email = ?", (address,)).fetchone()
        return row is not None and str(row["state"]) == "on"

    def subscribe(self, email: str) -> str | None:
        """The public door. Mint a token to confirm this address, or None if it is on.

        Idempotent: asking twice re-mints rather than making a second row, because
        asking twice is what somebody does when the first mail did not arrive.
        """
        address = tidy(email)
        if not address:
            raise ValueError("No address given.")
        if self.following(address):
            return None
        token = secrets.token_urlsafe(TOKEN_BYTES)
        with self.write() as db:
            db.execute(
                """
                INSERT INTO subscriber (email, state, confirm, stop, asked)
                VALUES (?, 'pending', ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET state = 'pending', confirm = ?, asked = ?
                """,
                (
                    address,
                    digest(token),
                    secrets.token_urlsafe(TOKEN_BYTES),
                    now(),
                    digest(token),
                    now(),
                ),
            )
        return token

    def follow(self, email: str, on: bool = True) -> bool:
        """The signed-in door, and it confirms nothing.

        Somebody with a session proved they control this address by following a link to
        get in. Mailing them to ask whether they control it would be asking them to
        confirm what they confirmed at the door.
        """
        address = tidy(email)
        if not address:
            raise ValueError("No address given.")
        with self.write() as db:
            if not on:
                db.execute(
                    "UPDATE subscriber SET state = 'off', ended = ? WHERE email = ?",
                    (now(), address),
                )
                return False
            db.execute(
                """
                INSERT INTO subscriber (email, state, confirm, stop, asked, joined)
                VALUES (?, 'on', NULL, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET state = 'on', confirm = NULL, joined = ?
                """,
                (address, secrets.token_urlsafe(TOKEN_BYTES), now(), now(), now()),
            )
        return True

    def peek_subscription(self, token: str) -> str | None:
        """Whose address this token would confirm, without spending it.

        The same reason `/account/enter` stopped being a bare GET: a mail client that
        fetches every link in a message would otherwise confirm the subscription before
        the person had read the sentence asking whether they wanted it.
        """
        row = self.db.execute(
            "SELECT email FROM subscriber WHERE confirm = ? AND state = 'pending'",
            (digest(token),),
        ).fetchone()
        return str(row["email"]) if row else None

    def confirm_subscription(self, token: str) -> str | None:
        """Spend a confirmation. Returns the address, or None if it was not one."""
        with self.write() as db:
            row = db.execute(
                "SELECT email FROM subscriber WHERE confirm = ? AND state = 'pending'",
                (digest(token),),
            ).fetchone()
            if row is None:
                return None
            db.execute(
                "UPDATE subscriber SET state = 'on', confirm = NULL, joined = ? WHERE email = ?",
                (now(), row["email"]),
            )
            return str(row["email"])

    def stop_subscription(self, token: str) -> bool:
        """One click, from an email, with no account and no JavaScript."""
        if not token:
            return False
        with self.write() as db:
            row = db.execute("SELECT email FROM subscriber WHERE stop = ?", (token,)).fetchone()
            if row is None:
                return False
            db.execute(
                "UPDATE subscriber SET state = 'off', ended = ? WHERE email = ?",
                (now(), row["email"]),
            )
            return True

    def subscribers(self, not_sent: str = "") -> list[tuple[str, str]]:
        """Everyone to mail about this issue, with the token that stops it.

        Selecting on "has not had this one" rather than on "is subscribed" is what makes
        a mailout safe to resume: a run that died halfway picks up where it stopped, and
        one started twice sends nothing the second time.

        And on "has not had a later one", which is what makes announcing the wrong week
        harmless. Rows carry the last issue sent, not a history, so a plain "not this
        one" would post last week's issue to everybody who already had this week's.
        """
        rows = self.db.execute(
            "SELECT email, stop FROM subscriber WHERE state = 'on' "
            # Not this issue, and not one already past it. The column holds the last
            # issue sent rather than a history, so "not this one" alone would re-send
            # last week to everybody the moment somebody typed the wrong week — and an
            # email is the one thing here that cannot be taken back. Issue ids are
            # `YYYY-wNN`, zero-padded, so they sort in the order the weeks happened.
            "AND (issue IS NULL OR issue < ?) "
            "ORDER BY joined",
            (not_sent,),
        ).fetchall()
        return [(str(row["email"]), str(row["stop"])) for row in rows]

    def mark_sent(self, email: str, issue_id: str) -> None:
        with self.write() as db:
            db.execute(
                "UPDATE subscriber SET sent = ?, issue = ?, bounces = 0 WHERE email = ?",
                (now(), issue_id, tidy(email)),
            )

    def bounced(self, email: str, limit: int = 3) -> bool:
        """Count a failure, and stop mailing an address that keeps failing.

        Returns whether this was the one that stopped it. Three, because a full mailbox
        and a domain that is briefly unreachable both clear up, and an address that has
        genuinely gone will fail every time.
        """
        address = tidy(email)
        with self.write() as db:
            db.execute("UPDATE subscriber SET bounces = bounces + 1 WHERE email = ?", (address,))
            row = db.execute(
                "SELECT bounces FROM subscriber WHERE email = ?", (address,)
            ).fetchone()
            if row is None or int(row["bounces"]) < limit:
                return False
            db.execute(
                "UPDATE subscriber SET state = 'off', ended = ? WHERE email = ?",
                (now(), address),
            )
            return True

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

    def make_admin(self, email: str) -> str:
        """Put an address beyond the spend rails, and on the guest list while we are here.

        Both, because an admin who cannot sign in is not an admin. Making somebody an
        admin is a statement that they may be here, and having to say it twice is a way
        of getting it half done.
        """
        address = tidy(email)
        if not address:
            raise ValueError("No address given.")
        with self.write() as db:
            db.execute(
                "INSERT INTO admin (email, at) VALUES (?, ?) ON CONFLICT(email) DO NOTHING",
                (address, now()),
            )
            db.execute(
                "INSERT INTO invited (email, at) VALUES (?, ?) ON CONFLICT(email) DO NOTHING",
                (address, now()),
            )
        return address

    def unadmin(self, email: str) -> bool:
        """Put an address back under the rails. The invitation and the account stay."""
        with self.write() as db:
            return db.execute("DELETE FROM admin WHERE email = ?", (tidy(email),)).rowcount > 0

    def admins(self) -> list[str]:
        return [row["email"] for row in self.db.execute("SELECT email FROM admin ORDER BY at")]

    # -- languages ----------------------------------------------------------------

    def _chosen(
        self, person_id: int | None, kind: str, offered: set[str], default: str
    ) -> set[str]:
        """What a person said for one kind, kept to the languages targum still has.

        Nobody — no id — is an empty set rather than the default, because the callers
        that work from a home directory use "nothing" to mean "no one to ask" and
        offer everything. A person with no rows gets the default: the app's own
        assumption until they say otherwise.
        """
        if not person_id:
            return set()
        rows = self.db.execute(
            "SELECT language FROM chosen WHERE person = ? AND kind = ?", (int(person_id), kind)
        )
        said = {str(row["language"]) for row in rows} & offered
        return said or {default}

    def learning(self, person_id: int | None) -> set[str]:
        """Which languages this person is learning: what the reading pages offer a
        switcher for, and what an upload may claim to be."""
        from .translate.prompts import READING

        return self._chosen(person_id, "learning", {code for code, _ in READING}, "he")

    def reads(self, person_id: int | None) -> set[str]:
        """Which languages this person reads well enough to be handed a translation in.

        The cost of guessing is a reader handed a page in a language they cannot read
        — and a definition in it following them around every text they own. So this is
        their own answer, and English until they give one.
        """
        from .translate.prompts import INTO

        return self._chosen(person_id, "reading", {code for code, _ in INTO}, "en")

    def choose(self, person: Person, kind: str, languages: list[str]) -> set[str]:
        """Replace one kind wholesale, which is the shape a form that submits a set wants.

        Refuses rather than repairs: an empty set is not a state a reader can be in,
        because a page with no translation beside the source is not a reader at all,
        and a learner of nothing has nothing to be shown. The sentence raised is the one
        the page shows.
        """
        from .translate.prompts import INTO, READING, REQUIRED_LEARNING, language_name

        if kind == "learning":
            offered = {code for code, _ in READING}
        elif kind == "reading":
            offered = {code for code, _ in INTO}
        else:
            raise ValueError("No such choice.")
        wanted = {str(code or "").strip().lower() for code in languages}
        wanted.discard("")
        strange = sorted(wanted - offered)
        if strange:
            raise ValueError(f"targum does not have {language_name(strange[0])}.")
        if not wanted:
            raise ValueError("Keep at least one.")
        if kind == "learning" and not wanted >= set(REQUIRED_LEARNING):
            raise ValueError(f"{language_name(REQUIRED_LEARNING[0])} stays on.")
        with self.write() as db:
            db.execute("DELETE FROM chosen WHERE person = ? AND kind = ?", (person.id, kind))
            db.executemany(
                "INSERT INTO chosen (person, kind, language, at) VALUES (?, ?, ?, ?)",
                [(person.id, kind, code, now()) for code in sorted(wanted)],
            )
        return wanted

    def is_admin(self, email: str) -> bool:
        address = tidy(email)
        if not address:
            return False
        found = self.db.execute("SELECT 1 FROM admin WHERE email = ?", (address,)).fetchone()
        return found is not None

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
            "SELECT person.id AS id, person.email AS email FROM link "
            "JOIN person ON person.id = link.person "
            "WHERE link.hash = ? AND link.used IS NULL AND link.made >= ? "
            "AND person.leaving IS NULL",
            (digest(token), cutoff),
        ).fetchone()
        return Person(row["id"], row["email"], self.is_admin(row["email"])) if row else None

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
                "SELECT id, email FROM person WHERE id = ?", (row["person"],)
            ).fetchone()
            session = secrets.token_urlsafe(TOKEN_BYTES)
            db.execute(
                "INSERT INTO session (hash, person, made, seen) VALUES (?, ?, ?, ?)",
                (digest(session), who["id"], now(), now()),
            )
        return Person(who["id"], who["email"], self.is_admin(who["email"])), session

    def whoever(self, session: str | None) -> Person | None:
        """The person holding this session, or nobody.

        Touches `seen`, which is what makes a session last as long as it is used.
        """
        if not session:
            return None
        cutoff = now() - SESSION_DAYS * 24 * 60 * 60 * 1000
        row = self.db.execute(
            "SELECT person.id AS id, person.email AS email,"
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
        return Person(row["id"], row["email"], self.is_admin(row["email"]))

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
            # The weekly stops too. A subscription is deliberately not part of the
            # account — it outlives one, and that is the point of keeping it in its own
            # table — but somebody who asked to be forgotten did not mean "keep mailing
            # me". Reversed by subscribing again, which they can do without an account.
            db.execute(
                "UPDATE subscriber SET state = 'off', ended = ? WHERE email = ?",
                (now(), person.email),
            )

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
                for table in (
                    "word",
                    "meaning",
                    "phrase",
                    "doc",
                    "day",
                    "chosen",
                    "session",
                    "link",
                ):
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
            "SELECT email, made FROM person WHERE id = ?", (person.id,)
        ).fetchone()
        out: dict[str, Any] = {
            "account": {
                "email": account["email"],
                "joined": account["made"],
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

    def spending(self, since: int) -> list[dict[str, Any]]:
        """What every account has cost since a moment, most expensive first.

        Two numbers, because they answer different questions. `spent` is what the API
        really charged, once it said — the one that reconciles against a bill. `claimed`
        is what the ceilings actually count, which is the same figure after a build
        settles, the estimate while one is still running, and nothing at all for a build
        that failed and handed its reservation back.

        Left joined, so work done before there were accounts — or by somebody since
        forgotten — still shows up rather than quietly leaving the total short.
        """
        rows = self.db.execute(
            "SELECT person.email AS email, "
            "       COUNT(job.id) AS jobs, "
            "       COALESCE(SUM(job.spent), 0) AS spent, "
            "       COALESCE(SUM(job.claimed), 0) AS claimed, "
            "       MAX(job.made) AS last "
            "FROM job LEFT JOIN person ON person.id = job.owner "
            "WHERE job.made >= ? "
            "GROUP BY job.owner "
            "ORDER BY spent DESC, claimed DESC",
            (since,),
        ).fetchall()
        return [dict(row) for row in rows]

    def claim(
        self,
        job_id: str,
        amount: float,
        ceiling: float,
        since: int,
        *,
        owner: int | None = None,
        per_account: float | None = None,
        month_from: int | None = None,
        per_month: float | None = None,
    ) -> str:
        """Take money from every budget, or say which one refused — in one transaction.

        Two builds starting together would otherwise both read the same balance and
        both pass, which is exactly how a budget is overrun. `BEGIN IMMEDIATE` makes
        the second one wait rather than race, and it holds across processes as well as
        threads, which a lock in one server never did.

        Three ceilings, because they stop three different things. The per-account day is
        a rate limit: it stops one afternoon running away. The per-account month is the
        plan limit — what a reader is actually allowed — and until it existed the daily
        rail was doing that job badly, since thirty days of it is thirty times the number
        anybody had agreed to. The whole-box day is what stops every reader at once from
        emptying the card, and no per-account limit can do that on its own.

        Any of them may be `None`, which is how an admin passes: the rails exist to stop
        a reader running up somebody else's bill, and the person paying it is not that
        reader. The box ceiling is not waived for anybody — it is the runaway guard.
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
            if per_month is not None and month_from is not None:
                monthly = db.execute(
                    "SELECT COALESCE(SUM(claimed), 0) AS spent FROM job "
                    "WHERE claimed > 0 AND made >= ? AND owner IS ?",
                    (month_from, owner),
                ).fetchone()
                if float(monthly["spent"]) + amount > per_month:
                    return "month"
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
