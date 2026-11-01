"""The shared candidate pool (targum-internal#619; plan §5.3).

One pool per box, shared by every reader and holding nothing about any of them: a find
is a link targum found, its metadata and a bag of lemma counts (`find_lemma`). **Never
the text**, no subtitles and no transcript: the page is fetched, scored in memory and
let go. A derived count is analysis, not a copy.

It lives in `targum.db` as its own tables with an expiry, and nowhere else: not in
`corpus.db`, whose ledger is exported and kept; not in the language tables, which
`tables.public_text` keeps to the public shelf; and not in `forms.json`, which is built
from the public shelf alone.

A row's `screen` is `kept`, or the reason it was dropped (`host`, `words`, `robots`,
`closed`, `unreadable`, `short`, `same`; and for a video, `age`, `gate` and `subs`, no
Hebrew track anybody wrote). A dropped row keeps only its address, so the
next round does not fetch it again, and goes when it expires like any other; the back
office counts the reasons.

**Targum's spend, not a reader's.** Finding is free to the reader. What finding costs
targum — a page read through the residential proxy today; a subtitle file, a whisper
minute or a search query in later slices — is written on the run's own row (`find_run`)
and held to `TARGUM_FINDS_BUDGET_USD` a month. It is not a `job` row and never touches
`Library.claim`: the one-counter rule is about what readers spend, and readers spend
nothing here.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..accounts import Store

SCHEMA = """
-- Things to read targum found on the web (targum-internal#619, design.md §12, "A web find
-- is a pasted link targum found", 2026-10-31). Shared by every reader and naming none.
-- `url` is the link as a server sees it (`weekly.feeds.link_key`); `digest` a hash of the
-- words read off it, so one article at two addresses is pooled once. `tokens` is the
-- running words counted and `unresolved` those the map could not place; `rung` an index
-- into the language's ladder, NULL where the find is not measured. `screen` is `kept` or
-- why it was dropped. Rows go when `expires` passes.
CREATE TABLE IF NOT EXISTS find (
  id         INTEGER PRIMARY KEY,
  language   TEXT    NOT NULL,
  source     TEXT    NOT NULL,
  url        TEXT    NOT NULL UNIQUE,
  digest     TEXT    NOT NULL DEFAULT '',
  title      TEXT    NOT NULL DEFAULT '',
  host       TEXT    NOT NULL DEFAULT '',
  publisher  TEXT    NOT NULL DEFAULT '',
  published  INTEGER NOT NULL DEFAULT 0,
  medium     TEXT    NOT NULL DEFAULT 'text',
  seconds    REAL    NOT NULL DEFAULT 0,
  tokens     INTEGER NOT NULL DEFAULT 0,
  unresolved INTEGER NOT NULL DEFAULT 0,
  credits    INTEGER NOT NULL DEFAULT 0,
  topics     TEXT    NOT NULL DEFAULT '',
  rung       INTEGER,
  found      INTEGER NOT NULL,
  expires    INTEGER NOT NULL,
  screen     TEXT    NOT NULL DEFAULT 'kept'
);
CREATE INDEX IF NOT EXISTS find_pick ON find (language, screen, rung, expires);
CREATE INDEX IF NOT EXISTS find_digest ON find (digest);

-- A find's words as lemma counts: all of it the pool keeps of the page.
CREATE TABLE IF NOT EXISTS find_lemma (
  find  INTEGER NOT NULL REFERENCES find (id) ON DELETE CASCADE,
  lemma TEXT    NOT NULL,
  n     INTEGER NOT NULL,
  PRIMARY KEY (find, lemma)
) WITHOUT ROWID;

-- One round of finding, or one calibration: what it saw, kept and dropped by reason,
-- and what it cost targum in dollars (never a reader's credits). `note` is JSON: a
-- calibration's table, or what stopped a round early.
CREATE TABLE IF NOT EXISTS find_run (
  id       INTEGER PRIMARY KEY,
  source   TEXT    NOT NULL,
  started  INTEGER NOT NULL,
  finished INTEGER NOT NULL DEFAULT 0,
  seen     INTEGER NOT NULL DEFAULT 0,
  kept     INTEGER NOT NULL DEFAULT 0,
  dropped  TEXT    NOT NULL DEFAULT '{}',
  spent    REAL    NOT NULL DEFAULT 0,
  note     TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS find_run_source ON find_run (source, started);
"""

#: A row that was kept.
KEPT = "kept"

#: Why a row was dropped, in the order the back office lists them.
DROPS = (
    "host",
    "words",
    "age",
    "gate",
    "subs",
    "robots",
    "closed",
    "unreadable",
    "short",
    "same",
    "budget",
)

#: How long a find stays, by where it came from (plan §1): a week of news, the YouTube
#: API's thirty days, two months of the open web.
KEEP_DAYS = {"news": 7, "youtube": 30, "podcast": 30, "web": 60}

#: The most rows Home scores for one reader (plan §3): an index walk, never the pool.
PICK_MOST = 300

#: targum's own discovery budget, dollars a month, unless the environment says.
BUDGET_ENV = "TARGUM_FINDS_BUDGET_USD"
BUDGET_DEFAULT = 30.0

DAY_MS = 24 * 60 * 60 * 1000


def now_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


def budget() -> float:
    """The month's discovery budget in dollars: `TARGUM_FINDS_BUDGET_USD`, or 30."""
    raw = os.environ.get(BUDGET_ENV, "").strip()
    try:
        return max(0.0, float(raw)) if raw else BUDGET_DEFAULT
    except ValueError:
        return BUDGET_DEFAULT


def month_from(at_ms: int) -> int:
    day = datetime.fromtimestamp(at_ms / 1000, tz=UTC)
    return int(datetime(day.year, day.month, 1, tzinfo=UTC).timestamp() * 1000)


@dataclass(frozen=True)
class Find:
    """One kept find, as Home reads it."""

    id: int
    language: str
    source: str
    url: str
    title: str
    host: str
    publisher: str
    published: int
    medium: str
    seconds: float
    tokens: int
    unresolved: int
    credits: int
    topics: tuple[str, ...]
    rung: int | None
    found: int
    expires: int
    bag: Mapping[str, int] = field(default_factory=dict, compare=False)

    @property
    def minutes(self) -> int:
        """How long it takes: its own seconds, or its words at 130 a minute
        (`catalogue.py`'s reading pace)."""
        if self.seconds:
            return max(1, round(self.seconds / 60))
        return max(1, round(self.tokens / 130))


_COLUMNS = (
    "id, language, source, url, title, host, publisher, published, medium, seconds, tokens,"
    " unresolved, credits, topics, rung, found, expires"
)


def _find(row: sqlite3.Row, bag: Mapping[str, int] | None = None) -> Find:
    return Find(
        id=int(row["id"]),
        language=str(row["language"]),
        source=str(row["source"]),
        url=str(row["url"]),
        title=str(row["title"]),
        host=str(row["host"]),
        publisher=str(row["publisher"]),
        published=int(row["published"]),
        medium=str(row["medium"]),
        seconds=float(row["seconds"]),
        tokens=int(row["tokens"]),
        unresolved=int(row["unresolved"]),
        credits=int(row["credits"]),
        topics=tuple(one for one in str(row["topics"]).split(",") if one),
        rung=None if row["rung"] is None else int(row["rung"]),
        found=int(row["found"]),
        expires=int(row["expires"]),
        bag=bag or {},
    )


def expires_at(source: str, at: int) -> int:
    return at + KEEP_DAYS.get(source, 7) * DAY_MS


def known(store: Store, url: str) -> bool:
    """Whether the pool already holds this address, kept or dropped."""
    return store.db.execute("SELECT 1 FROM find WHERE url = ?", (url,)).fetchone() is not None


def known_digest(store: Store, digest: str) -> bool:
    if not digest:
        return False
    found = store.db.execute(
        "SELECT 1 FROM find WHERE digest = ? AND screen = ?", (digest, KEPT)
    ).fetchone()
    return found is not None


def add(
    store: Store,
    *,
    language: str,
    source: str,
    url: str,
    bag: Mapping[str, int],
    tokens: int,
    unresolved: int,
    rung: int | None,
    digest: str = "",
    title: str = "",
    host: str = "",
    publisher: str = "",
    published: int = 0,
    medium: str = "text",
    seconds: float = 0.0,
    credits: int = 0,
    topics: Sequence[str] = (),
    at: int | None = None,
) -> int:
    """Keep one find and its lemma counts, in one transaction. Its id; or 0 where the
    address is already held, which is a round that raced another."""
    when = now_ms() if at is None else at
    with store.write() as db:
        try:
            cursor = db.execute(
                "INSERT INTO find (language, source, url, digest, title, host, publisher,"
                " published, medium, seconds, tokens, unresolved, credits, topics, rung, found,"
                " expires, screen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    language,
                    source,
                    url,
                    digest,
                    title[:300],
                    host,
                    publisher[:120],
                    published,
                    medium,
                    seconds,
                    tokens,
                    unresolved,
                    credits,
                    ",".join(topics),
                    rung,
                    when,
                    expires_at(source, when),
                    KEPT,
                ),
            )
        except sqlite3.IntegrityError:
            return 0
        find_id = int(cursor.lastrowid or 0)
        db.executemany(
            "INSERT INTO find_lemma (find, lemma, n) VALUES (?, ?, ?)",
            [(find_id, lemma, int(n)) for lemma, n in bag.items() if n > 0],
        )
    return find_id


def drop(
    store: Store,
    *,
    language: str,
    source: str,
    url: str,
    reason: str,
    host: str = "",
    at: int | None = None,
) -> None:
    """Remember an address the round would not keep, and why, so it is not fetched
    again before it expires. No title and no counts: nothing of it is offered."""
    when = now_ms() if at is None else at
    with store.write() as db:
        db.execute(
            "INSERT OR IGNORE INTO find (language, source, url, host, found, expires, screen)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (language, source, url, host, when, expires_at(source, when), reason),
        )


def expire(store: Store, at: int | None = None) -> int:
    """Delete every find whose time is up, with its counts. How many went."""
    when = now_ms() if at is None else at
    with store.write() as db:
        gone = db.execute("DELETE FROM find WHERE expires <= ?", (when,)).rowcount
    with _BAGS_LOCK:
        _BAGS.clear()
    return int(gone or 0)


def get(store: Store, find_id: int, at: int | None = None) -> Find | None:
    """One kept find that has not expired, with its counts; None otherwise."""
    when = now_ms() if at is None else at
    row = store.db.execute(
        f"SELECT {_COLUMNS} FROM find WHERE id = ? AND screen = ? AND expires > ?",  # noqa: S608 - constant
        (find_id, KEPT, when),
    ).fetchone()
    if row is None:
        return None
    return _find(row, _bags(store, [int(row["id"])]).get(int(row["id"]), {}))


# A find's counts never change once written, so they are read once a process and kept,
# keyed by database and id: Home scores up to `PICK_MOST` finds a request, and reading
# their lemma rows each time was most of the request.
_BAGS: dict[tuple[str, int], dict[str, int]] = {}
_BAGS_LOCK = threading.Lock()
_BAGS_MOST = 20_000


def _bags(store: Store, ids: Iterable[int]) -> dict[int, dict[str, int]]:
    where = str(store.path)
    out: dict[int, dict[str, int]] = {}
    missing: list[int] = []
    with _BAGS_LOCK:
        for find_id in ids:
            held = _BAGS.get((where, find_id))
            if held is None:
                missing.append(find_id)
            else:
                out[find_id] = held
    for start in range(0, len(missing), 500):
        chunk = missing[start : start + 500]
        marks = ",".join("?" * len(chunk))
        read: dict[int, dict[str, int]] = {find_id: {} for find_id in chunk}
        for row in store.db.execute(
            f"SELECT find, lemma, n FROM find_lemma WHERE find IN ({marks})",  # noqa: S608 - marks only
            chunk,
        ):
            read[int(row[0])][str(row[1])] = int(row[2])
        out.update(read)
        with _BAGS_LOCK:
            if len(_BAGS) + len(read) > _BAGS_MOST:
                _BAGS.clear()
            for find_id, bag in read.items():
                _BAGS[(where, find_id)] = bag
    return out


def pick(
    store: Store,
    language: str,
    rung: int | None,
    *,
    at: int | None = None,
    most: int = PICK_MOST,
) -> list[Find]:
    """The kept, measured, unexpired finds in a language near a rung, freshest first, with
    their counts: what Home scores for one reader. An index walk over `find_pick`; with no
    rung, the freshest whatever their rung."""
    when = now_ms() if at is None else at
    if rung is None:
        rows = store.db.execute(
            f"SELECT {_COLUMNS} FROM find WHERE language = ? AND screen = ?"  # noqa: S608 - constant
            " AND rung IS NOT NULL AND expires > ? ORDER BY published DESC, id DESC LIMIT ?",
            (language, KEPT, when, most),
        ).fetchall()
    else:
        rows = store.db.execute(
            f"SELECT {_COLUMNS} FROM find WHERE language = ? AND screen = ?"  # noqa: S608 - constant
            " AND rung BETWEEN ? AND ? AND expires > ? ORDER BY published DESC, id DESC LIMIT ?",
            (language, KEPT, rung - 1, rung + 1, when, most),
        ).fetchall()
    bags = _bags(store, [int(row["id"]) for row in rows])
    return [_find(row, bags.get(int(row["id"]), {})) for row in rows]


# -- runs and spend ---------------------------------------------------------------


def start_run(store: Store, source: str, at: int | None = None) -> int:
    with store.write() as db:
        cursor = db.execute(
            "INSERT INTO find_run (source, started) VALUES (?, ?)",
            (source, now_ms() if at is None else at),
        )
    return int(cursor.lastrowid or 0)


def finish_run(
    store: Store,
    run: int,
    *,
    seen: int = 0,
    kept: int = 0,
    dropped: Mapping[str, int] | None = None,
    note: Any = "",
    at: int | None = None,
) -> None:
    """Close a run. Its spend is what `spend` added as it went, and is left alone."""
    with store.write() as db:
        db.execute(
            "UPDATE find_run SET finished = ?, seen = ?, kept = ?, dropped = ?, note = ?"
            " WHERE id = ?",
            (
                now_ms() if at is None else at,
                seen,
                kept,
                json.dumps(dict(dropped or {}), sort_keys=True),
                note if isinstance(note, str) else json.dumps(note, ensure_ascii=False),
                run,
            ),
        )


def spend(store: Store, run: int, dollars: float) -> None:
    """Add to a run's spend as it happens, so a round killed partway has still said
    what it cost (memory: a run that spends must checkpoint)."""
    if dollars <= 0:
        return
    with store.write() as db:
        db.execute("UPDATE find_run SET spent = spent + ? WHERE id = ?", (dollars, run))


def month_spent(store: Store, at: int | None = None) -> float:
    """What finding has cost targum this calendar month (UTC), in dollars."""
    when = now_ms() if at is None else at
    row = store.db.execute(
        "SELECT COALESCE(SUM(spent), 0) FROM find_run WHERE started >= ?", (month_from(when),)
    ).fetchone()
    return float(row[0] or 0.0)


def left(store: Store, at: int | None = None) -> float:
    """The month's discovery budget still unspent, in dollars, never below nought."""
    return max(0.0, budget() - month_spent(store, at))


# -- the back office --------------------------------------------------------------


@dataclass
class Survey:
    """What the back office shows of the pool (plan §8 A): counts, never a link."""

    #: Kept and unexpired, by language.
    by_language: dict[str, int] = field(default_factory=dict)
    #: Kept and measured, by (language, rung index).
    by_rung: dict[tuple[str, int], int] = field(default_factory=dict)
    #: Kept but not measured, by language.
    unmeasured: dict[str, int] = field(default_factory=dict)
    by_topic: dict[str, int] = field(default_factory=dict)
    #: Dropped rows still held, by reason.
    dropped: dict[str, int] = field(default_factory=dict)
    #: This month's discovery spend by source, in dollars, and the budget.
    spent: dict[str, float] = field(default_factory=dict)
    budget: float = BUDGET_DEFAULT
    #: The last round of each source: when it finished, what it saw and kept.
    last: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: The last calibration's table (`score.Calibration.state`), or None.
    calibration: dict[str, Any] | None = None
    calibrated: int = 0
    #: Finds readers opened in the last thirty days, and of those built: off the job
    #: rows, which say `via: find` themselves, so there is no counter of its own.
    opened: int = 0
    built: int = 0

    def any(self) -> bool:
        return bool(self.by_language or self.dropped or self.last or self.calibration)


def survey(db: sqlite3.Connection, at: int | None = None) -> Survey:
    """The pool counted for the back office, off a read-only connection. A store from
    before the pool existed answers an empty survey."""
    when = now_ms() if at is None else at
    out = Survey(budget=budget())
    try:
        for language, screen, rung, n in db.execute(
            "SELECT language, screen, rung, COUNT(*) FROM find WHERE expires > ?"
            " GROUP BY language, screen, rung",
            (when,),
        ):
            if screen != KEPT:
                out.dropped[str(screen)] = out.dropped.get(str(screen), 0) + int(n)
                continue
            out.by_language[str(language)] = out.by_language.get(str(language), 0) + int(n)
            if rung is None:
                out.unmeasured[str(language)] = out.unmeasured.get(str(language), 0) + int(n)
            else:
                out.by_rung[(str(language), int(rung))] = int(n)
        for (topics,) in db.execute(
            "SELECT topics FROM find WHERE expires > ? AND screen = ? AND topics != ''",
            (when, KEPT),
        ):
            for topic in str(topics).split(","):
                out.by_topic[topic] = out.by_topic.get(topic, 0) + 1
        for source, spent in db.execute(
            "SELECT source, SUM(spent) FROM find_run WHERE started >= ? GROUP BY source",
            (month_from(when),),
        ):
            out.spent[str(source)] = float(spent or 0.0)
        for source, finished, seen, kept, dropped in db.execute(
            "SELECT source, finished, seen, kept, dropped FROM find_run r WHERE finished > 0"
            " AND source != 'calibrate' AND id = (SELECT MAX(id) FROM find_run"
            " WHERE source = r.source AND finished > 0)"
        ):
            out.last[str(source)] = {
                "finished": int(finished),
                "seen": int(seen),
                "kept": int(kept),
                "dropped": json.loads(dropped or "{}"),
            }
        for stage, n in db.execute(
            "SELECT stage, COUNT(*) FROM job WHERE made >= ?"
            " AND json_extract(options, '$.via') = 'find' GROUP BY stage",
            (when - 30 * DAY_MS,),
        ):
            out.opened += int(n)
            if stage == "done":
                out.built += int(n)
        row = db.execute(
            "SELECT finished, note FROM find_run WHERE source = 'calibrate' AND finished > 0"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is not None:
            out.calibrated = int(row[0])
            try:
                out.calibration = json.loads(row[1] or "null")
            except ValueError:
                out.calibration = None
    except sqlite3.Error:
        return Survey(budget=budget())
    return out
