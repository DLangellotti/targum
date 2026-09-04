"""Who has an account, and what they did on which day.

The operator's own view of the box, at `bo.<domain>`. Everything here is counted off
the store and nothing else — the same records `measures.py` reads, asked a different
question.

**`measures.py` is deliberately anonymous and this is deliberately not.** That report is
the weekly table in a notebook: it answers "how is the beta going" and it names nobody,
because a table that names readers is a table that cannot be pasted anywhere. This page
answers "who is on my box and are they using it", which cannot be answered without
saying who. The two exist side by side on purpose; neither is the other with a flag
flipped.

The reason that distinction is safe to draw is the door in front of it: this is served
on its own name, behind a password held by one person, from an origin that listens on
loopback only. Nothing here is reachable from the product, and no route on the product's
own name reaches it.

What it does not hold, and will not: the words themselves, the texts anybody read, the
notes they wrote. Counts of those things, and no more. A back office that shows an
operator what a reader wrote is a back office that has to be justified to that reader,
and there is no version of "how much are they reading" that needs it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

#: How much of the past the day table shows. A month is what fits on a page without
#: scrolling and is long enough for "did they come back" to be visible.
DAYS = 30


def _day(stamp_ms: int) -> str:
    """The UTC day a millisecond stamp falls on."""
    return datetime.fromtimestamp(stamp_ms / 1000, UTC).date().isoformat()


@dataclass
class Account:
    """One person, and the size of what they have accumulated."""

    id: int
    email: str
    name: str
    joined: str
    #: The last day anything of theirs changed, from the records themselves rather than
    #: from a session: a session says somebody opened a tab, and these say they did
    #: something once it was open.
    last_active: str
    words: int
    learned: int
    phrases: int
    texts_opened: int
    targums_finished: int
    days_read: int
    #: When they asked to be forgotten, or "". The grace period is the only window in
    #: which that is undoable, so it belongs on the first screen rather than in a query.
    leaving: str = ""


@dataclass
class Day:
    """One day, and what each account did on it."""

    day: str
    #: person id -> words saved that day.
    words: dict[int, int] = field(default_factory=dict)
    #: person id -> texts opened that day.
    opened: dict[int, int] = field(default_factory=dict)
    #: Which accounts marked the day as one they read on. The reader's own record, which
    #: is the only one that knows about reading that saved nothing.
    read: set[int] = field(default_factory=set)

    def busy(self) -> bool:
        return bool(self.read) or any(self.words.values()) or any(self.opened.values())


@dataclass
class Survey:
    accounts: list[Account] = field(default_factory=list)
    days: list[Day] = field(default_factory=list)
    taken: str = ""

    def active(self) -> int:
        """Accounts that did anything at all in the window."""
        who = set()
        for day in self.days:
            who |= day.read
            who |= {who_ for who_, n in day.words.items() if n}
            who |= {who_ for who_, n in day.opened.items() if n}
        return len(who)


def _rows(db: sqlite3.Connection, sql: str, *args: object) -> list[sqlite3.Row]:
    return list(db.execute(sql, args).fetchall())


def survey(db: sqlite3.Connection, today: date | None = None, days: int = DAYS) -> Survey:
    """Everything the page shows, in one pass over the store.

    `gone` rows are excluded throughout. A word somebody deleted is not a word they
    have, and counting it would make the page disagree with the reader's own list — the
    one number on this page a reader could check.
    """
    db.row_factory = sqlite3.Row
    now = today or datetime.now(UTC).date()
    window = [(now - timedelta(days=n)).isoformat() for n in range(days)]
    since = int(
        datetime.combine(now - timedelta(days=days - 1), datetime.min.time(), UTC).timestamp()
        * 1000
    )

    found = Survey(taken=datetime.now(UTC).isoformat(timespec="seconds"))

    people = _rows(db, "SELECT id, email, name, made, leaving FROM person ORDER BY id")
    counted = {
        name: {
            int(row["person"]): int(row["n"])
            for row in _rows(db, sql)  # noqa: S608 - no interpolation, these are literals
        }
        for name, sql in (
            ("words", "SELECT person, COUNT(*) n FROM word WHERE gone = 0 GROUP BY person"),
            (
                "learned",
                "SELECT person, COUNT(*) n FROM word"
                " WHERE gone = 0 AND learned = 1 GROUP BY person",
            ),
            ("phrases", "SELECT person, COUNT(*) n FROM phrase WHERE gone = 0 GROUP BY person"),
            ("texts", "SELECT person, COUNT(*) n FROM doc WHERE gone = 0 GROUP BY person"),
            ("days", "SELECT person, COUNT(*) n FROM day WHERE gone = 0 GROUP BY person"),
        )
    }
    # A targum finishes at the end of a chapter now, so a document is worth the greater
    # of its old whole-document record and the sections finished since — never their sum
    # (targum-internal#173). The same rule the ledger draws, asked of the server's copy.
    finished: dict[int, int] = {}
    for row in _rows(
        db,
        "SELECT d.person AS person, d.hash AS hash, d.done AS done,"
        " (SELECT COUNT(*) FROM section s WHERE s.person = d.person AND s.hash = d.hash"
        "  AND s.gone = 0) AS parts"
        " FROM doc d WHERE d.gone = 0",
    ):
        worth = max(1 if row["done"] else 0, int(row["parts"] or 0))
        if worth:
            finished[int(row["person"])] = finished.get(int(row["person"]), 0) + worth

    # The last day anything moved, per person, across everything that carries a stamp.
    moved: dict[int, int] = {}
    for sql in (
        "SELECT person, MAX(at) last FROM word WHERE gone = 0 GROUP BY person",
        "SELECT person, MAX(at) last FROM phrase WHERE gone = 0 GROUP BY person",
        "SELECT person, MAX(updated) last FROM doc WHERE gone = 0 GROUP BY person",
        "SELECT person, MAX(opened) last FROM doc WHERE gone = 0 GROUP BY person",
    ):
        for row in _rows(db, sql):
            when = int(row["last"] or 0)
            if when > moved.get(int(row["person"]), 0):
                moved[int(row["person"])] = when

    for row in people:
        who = int(row["id"])
        found.accounts.append(
            Account(
                id=who,
                email=str(row["email"]),
                name=str(row["name"] or ""),
                joined=_day(int(row["made"])),
                last_active=_day(moved[who]) if moved.get(who) else "",
                words=counted["words"].get(who, 0),
                learned=counted["learned"].get(who, 0),
                phrases=counted["phrases"].get(who, 0),
                texts_opened=counted["texts"].get(who, 0),
                targums_finished=finished.get(who, 0),
                days_read=counted["days"].get(who, 0),
                leaving=_day(int(row["leaving"])) if row["leaving"] else "",
            )
        )

    by_day = {when: Day(day=when) for when in window}
    for row in _rows(db, "SELECT person, at FROM word WHERE gone = 0 AND at >= ?", since):
        fell = _day(int(row["at"]))
        if fell in by_day:
            who = int(row["person"])
            by_day[fell].words[who] = by_day[fell].words.get(who, 0) + 1
    for row in _rows(db, "SELECT person, opened FROM doc WHERE gone = 0 AND opened >= ?", since):
        fell = _day(int(row["opened"]))
        if fell in by_day:
            who = int(row["person"])
            by_day[fell].opened[who] = by_day[fell].opened.get(who, 0) + 1
    for row in _rows(db, "SELECT person, day FROM day WHERE gone = 0"):
        fell = str(row["day"])
        if fell in by_day:
            by_day[fell].read.add(int(row["person"]))

    found.days = [by_day[each] for each in window]
    return found


def survey_store(store: Path, today: date | None = None, days: int = DAYS) -> Survey:
    """`survey`, opening the database read-only.

    Read-only because this is a page anybody refreshing could hit while a reader is
    mid-sync, and because nothing here has any business writing to the store.
    """
    db = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        return survey(db, today=today, days=days)
    finally:
        db.close()
