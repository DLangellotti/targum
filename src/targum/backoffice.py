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

**One exception: what a reader writes to us (2026-10-18, targum-internal#456).** A message
sent through Tell us is addressed to the operator, so showing it to the operator is the
whole of what the reader asked for; clause 3.14 of the privacy notice says so, and how
long it is kept. It is listed under People with its page, window, language and build, and
nothing else a reader wrote ever joins it. Fault reports from browsers (#457) are counted
under Operations by message and page, never per reader.

**What it is for, since the first readers came in (2026-10-15).** Three questions: who
should I write to, did this week's people come back, and which parts of targum does
nobody reach. The first is asked of each account, and only of what clause 3.2 of the
privacy notice already holds — texts opened, words kept, days read, and whether they
signed in at all. The other two are counted across everybody and name nobody, which is
the only way the record of use at clause 3.6 is read here (clause 3.7). The operator's
own addresses are left out of all three (`TARGUM_OPERATORS`), since a beta of eight in
which two are the person running it says nothing about strangers.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

#: How much of the past the day table shows. A month is what fits on a page without
#: scrolling and is long enough for "did they come back" to be visible.
DAYS = 30

#: How long after being let in somebody may take to sign in before the page asks the
#: operator to write again. A day is long enough for a mail to be read in any timezone.
NO_ACCOUNT_AFTER = 2
#: How long after joining a reader who opened at most one text and kept nothing is worth
#: a word from the operator: long enough to have come back, short enough to remember.
NOTHING_KEPT_AFTER = 2
#: How long a reader who read on some day has been quiet before the page says so.
QUIET_AFTER = 5
#: How old a week's people must be before "came back" is counted for them: until then
#: nobody has had the chance, and a nought reads as a failure that has not happened.
CAME_BACK_AFTER = 2

GMAIL = frozenset({"gmail.com", "googlemail.com"})


def bare(email: str) -> str:
    """An address with its `+tag` taken off and, at Gmail, its dots: one person's
    `name+test2@gmail.com` and `n.ame@gmail.com` are the same inbox and so the same
    person."""
    local, at, domain = email.strip().lower().partition("@")
    if not at:
        return local
    local = local.split("+", 1)[0]
    if domain in GMAIL:
        local = local.replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def operators_from_env() -> frozenset[str]:
    """The operator's own addresses, from `TARGUM_OPERATORS`, comma or space separated.

    A setting on the box rather than a list in the code, because the code is public and
    the addresses are a person's. Admins and test accounts are left out without being
    named here; this is for the address somebody signs up with to see what a stranger
    sees.
    """
    said = os.environ.get("TARGUM_OPERATORS", "")
    return frozenset(bare(each) for each in said.replace(",", " ").split() if each)


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
class Waiting:
    """One address at the front door, and where it has got to.

    The counts alone answered "how many", which is the one question the operator does
    not have: a waitlist is a list of people to write to, and a list you cannot read is
    a number. This page already names accounts, for the reason its own docstring gives,
    and these are the same kind of fact about the same kind of person.
    """

    email: str
    #: pending until the address answers its confirmation, on once it has, off once they
    #: asked to come off.
    state: str
    asked: str
    joined: str = ""
    invited: str = ""
    #: The language the front door was in when they joined, so the operator can see what
    #: the invitation will be written in. Empty means English.
    language: str = ""
    #: Which of targum's pages they pressed Join on (targum-internal#388). Empty is
    #: unknown, which every row before schema 37 is.
    page: str = ""
    #: The link they tried on the front page and joined with (targum-internal#399).
    link: str = ""


@dataclass
class Batch:
    """The people let in during one week, and how far they got.

    Counted, never named: this is the table that says whether a change between one
    week's people and the next helped, and it answers that without anybody in it.
    """

    #: The Monday of the week they were let in.
    week: str
    let_in: int = 0
    signed_in: int = 0
    opened: int = 0
    kept: int = 0
    #: Of those who signed in long enough ago to have had a second day, how many did:
    #: a nought from people let in yesterday is not a nought.
    old_enough: int = 0
    came_back: int = 0


@dataclass
class Reach:
    """How many readers have used one part of targum at least once."""

    part: str
    people: int


@dataclass
class FollowUp:
    """Somebody worth writing to, and why."""

    email: str
    #: What the operator is told, in a line: "Let in October 12, not signed in yet".
    why: str
    #: `resend` sends the invitation again; `write` opens a mail to them.
    action: str
    #: When the thing that makes them worth writing to began, for the order of the list.
    since: str


@dataclass
class Survey:
    accounts: list[Account] = field(default_factory=list)
    days: list[Day] = field(default_factory=list)
    taken: str = ""
    #: How many are waiting at the front door, by state (targum-internal#69), and who.
    waiting: dict[str, int] = field(default_factory=dict)
    waiting_list: list[Waiting] = field(default_factory=list)
    #: Confirmed and not yet let in — the number the door's own press would take from.
    waiting_for_a_way_in: int = 0
    #: How many joined through each of targum's pages; "" is unknown.
    waiting_by_page: dict[str, int] = field(default_factory=dict)
    #: What came in through the connector in the window (targum-internal#408): texts
    #: quoted from a host, how many of those the reader pressed, how many finished, and
    #: sets made there. Read off the job and playlist rows, which say so themselves, so
    #: there is no counter of its own to drift from them.
    connector: dict[str, int] = field(default_factory=dict)
    #: Who to write to (2026-10-15), oldest first.
    follow_up: list[FollowUp] = field(default_factory=list)
    #: Each week's people, newest first, and how far they got.
    batches: list[Batch] = field(default_factory=list)
    #: How many readers reached each part of targum, out of `readers`.
    reach: list[Reach] = field(default_factory=list)
    readers: int = 0

    def active(self) -> int:
        """Accounts that did anything at all in the window."""
        who = set()
        for day in self.days:
            who |= day.read
            who |= {who_ for who_, n in day.words.items() if n}
            who |= {who_ for who_, n in day.opened.items() if n}
        return len(who)


def _spoken(row: sqlite3.Row) -> str:
    """The language a waiting row joined in, empty where the store predates the column.

    `SELECT *` on a database written before schema 18 has no `language` at all, and
    reaching for it raises IndexError rather than an `sqlite3.Error` the caller suppresses.
    """
    try:
        return str(row["language"] or "")
    except (IndexError, KeyError):
        return ""


def _page(row: sqlite3.Row, column: str = "page") -> str:
    """The page a waiting row joined from, or the link it joined with, empty where the
    store predates the column."""
    try:
        return str(row[column] or "")
    except (IndexError, KeyError):
        return ""


def _rows(db: sqlite3.Connection, sql: str, *args: object) -> list[sqlite3.Row]:
    return list(db.execute(sql, args).fetchall())


def survey(
    db: sqlite3.Connection,
    today: date | None = None,
    days: int = DAYS,
    operators: Iterable[str] = (),
) -> Survey:
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
    # The operator's own addresses are nobody's data here, on any table (2026-10-15).
    mine = frozenset(bare(each) for each in operators)
    # The front door, if this database has one yet. A store written before schema 17
    # has no such table, and the page is not the place to find that out.
    with contextlib.suppress(sqlite3.Error):
        counted_waiting = Counter(
            str(row["state"])
            for row in _rows(db, "SELECT state, email FROM waiting")
            if bare(str(row["email"])) not in mine
        )
        found.waiting = {state: counted_waiting.get(state, 0) for state in ("pending", "on", "off")}
        found.waiting_list = [
            Waiting(
                email=str(row["email"]),
                state=str(row["state"]),
                asked=_day(int(row["asked"])),
                joined=_day(int(row["joined"])) if row["joined"] else "",
                invited=_day(int(row["invited"])) if row["invited"] else "",
                language=_spoken(row),
                page=_page(row),
                link=_page(row, "link"),
            )
            # Oldest first: that is the order they would be let in.
            for row in _rows(db, "SELECT * FROM waiting ORDER BY asked")
            if bare(str(row["email"])) not in mine
        ]
        # How many joined through each page, so `/aliyah` can be told from the front
        # door (targum-internal#388). Unknown is counted too, under "".
        found.waiting_by_page = dict(Counter(who.page for who in found.waiting_list).most_common())
        found.waiting_for_a_way_in = sum(
            1 for who in found.waiting_list if who.state == "on" and not who.invited
        )

    people = [
        row
        for row in _rows(db, "SELECT id, email, name, made, leaving FROM person ORDER BY id")
        if bare(str(row["email"])) not in mine
    ]
    shown = {int(row["id"]) for row in people}
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
        if fell in by_day and int(row["person"]) in shown:
            who = int(row["person"])
            by_day[fell].words[who] = by_day[fell].words.get(who, 0) + 1
    for row in _rows(db, "SELECT person, opened FROM doc WHERE gone = 0 AND opened >= ?", since):
        fell = _day(int(row["opened"]))
        if fell in by_day and int(row["person"]) in shown:
            who = int(row["person"])
            by_day[fell].opened[who] = by_day[fell].opened.get(who, 0) + 1
    for row in _rows(db, "SELECT person, day FROM day WHERE gone = 0"):
        fell = str(row["day"])
        if fell in by_day and int(row["person"]) in shown:
            by_day[fell].read.add(int(row["person"]))

    found.days = [by_day[each] for each in window]
    _growth(db, found, now, people, mine)

    # A store from before the rows said where they came from has nothing to count.
    with contextlib.suppress(sqlite3.Error):
        quoted = _rows(
            db,
            "SELECT stage, claimed FROM job WHERE kind = 'build' AND made >= ?"
            " AND json_extract(options, '$.via') = 'connector'",
            since,
        )
        found.connector = {
            "quoted": len(quoted),
            # Pressed is anything past the quote: claimed, waiting its turn, under way,
            # finished, or stopped after it began.
            "pressed": sum(
                1
                for row in quoted
                if row["stage"] not in ("reading", "ready", "blocked")
                and (row["stage"] != "failed" or float(row["claimed"] or 0) > 0)
            ),
            "finished": sum(1 for row in quoted if row["stage"] == "done"),
            "sets": int(
                _rows(
                    db,
                    "SELECT COUNT(*) AS n FROM playlist WHERE made_by = 'connector' AND made >= ?",
                    since,
                )[0]["n"]
            ),
        }
    return found


def _monday(day: date) -> str:
    return (day - timedelta(days=day.weekday())).isoformat()


def _said(day: str) -> str:
    """ "October 12", the way the rest of the product writes a date."""
    when = date.fromisoformat(day)
    return f"{when.strftime('%B')} {when.day}"


def _staff(db: sqlite3.Connection, operators: frozenset[str]) -> set[str]:
    """Every address that is the operator's rather than a reader's, compared bare."""
    staff = set(operators)
    for table in ("admin", "test_account"):
        with contextlib.suppress(sqlite3.Error):
            staff |= {bare(str(row["email"])) for row in _rows(db, f"SELECT email FROM {table}")}  # noqa: S608
    return staff


def _people_with(db: sqlite3.Connection, sql: str) -> set[int]:
    """The ids a query returns, or none where the store predates its table."""
    with contextlib.suppress(sqlite3.Error):
        return {int(row[0]) for row in db.execute(sql).fetchall() if row[0] is not None}
    return set()


def _growth(
    db: sqlite3.Connection,
    found: Survey,
    now: date,
    people: list[sqlite3.Row],
    operators: frozenset[str],
) -> None:
    """Who to write to, each week's people, and how far readers reach.

    Everything named here comes from what clause 3.2 holds — texts opened, words kept,
    days read — and from the guest list. The record of use (3.6) is read only for the
    reach, as a count of people with no one in it.
    """
    staff = _staff(db, operators)
    readers = {int(row["id"]): row for row in people if bare(str(row["email"])) not in staff}
    found.readers = len(readers)

    # Each reader's days, from their own record: days they marked, texts they opened,
    # words they kept. Not the record of use, which is theirs for their own page.
    days: dict[int, set[str]] = {who: set() for who in readers}
    for row in _rows(db, "SELECT person, day FROM day WHERE gone = 0"):
        days.setdefault(int(row["person"]), set()).add(str(row["day"]))
    for sql in (
        "SELECT person, opened AS at FROM doc WHERE opened > 0",
        "SELECT person, at FROM word WHERE at > 0",
    ):
        for row in _rows(db, sql):
            days.setdefault(int(row["person"]), set()).add(_day(int(row["at"])))
    opened = {
        int(row["person"]): int(row["n"])
        for row in _rows(db, "SELECT person, COUNT(*) n FROM doc WHERE opened > 0 GROUP BY person")
    }
    kept = _people_with(db, "SELECT DISTINCT person FROM word WHERE source != 'claimed'")
    # Signed in: a session now, or anything of their own at all. Sessions are pruned, and
    # an account can exist before its first sign-in when a saved link was built for it.
    signed_in = _people_with(db, "SELECT DISTINCT person FROM session") | {
        who for who, on in days.items() if on
    }

    let_in: dict[str, int] = {}
    with contextlib.suppress(sqlite3.Error):
        let_in = {
            str(row["email"]).lower(): int(row["at"])
            for row in _rows(db, "SELECT email, at FROM invited")
            if bare(str(row["email"])) not in staff
        }
    by_email = {str(row["email"]).lower(): who for who, row in readers.items()}

    # Who to write to.
    follow: list[FollowUp] = []
    for email, at in let_in.items():
        who_ = by_email.get(email)
        if who_ is not None and who_ in signed_in:
            continue
        if (now - date.fromisoformat(_day(at))).days >= NO_ACCOUNT_AFTER:
            follow.append(
                FollowUp(email, f"Let in {_said(_day(at))}, not signed in yet", "resend", _day(at))
            )
    for who, row in readers.items():
        if row["leaving"] or who not in signed_in:
            continue
        email = str(row["email"])
        joined = _day(int(row["made"]))
        if opened.get(who, 0) <= 1 and who not in kept:
            if (now - date.fromisoformat(joined)).days >= NOTHING_KEPT_AFTER:
                texts = opened.get(who, 0)
                follow.append(
                    FollowUp(
                        email,
                        f"Joined {_said(joined)}, opened {texts} text{'' if texts == 1 else 's'}"
                        " and kept no words",
                        "write",
                        joined,
                    )
                )
            continue
        last = max(days.get(who) or {""})
        if last and (now - date.fromisoformat(last)).days >= QUIET_AFTER:
            follow.append(FollowUp(email, f"Last read {_said(last)}", "write", last))
    found.follow_up = sorted(follow, key=lambda each: each.since)

    # Each week's people. The week they were let in, or joined where there was no
    # guest list yet.
    weeks: dict[str, Batch] = {}
    for at in let_in.values():
        when = date.fromisoformat(_day(at))
        batch = weeks.setdefault(_monday(when), Batch(_monday(when)))
        batch.let_in += 1
    for who, row in readers.items():
        email = str(row["email"]).lower()
        when = date.fromisoformat(_day(let_in.get(email) or int(row["made"])))
        batch = weeks.setdefault(_monday(when), Batch(_monday(when)))
        if email not in let_in:
            batch.let_in += 1
        batch.signed_in += who in signed_in
        batch.opened += who in opened
        batch.kept += who in kept
        # Only those let in long enough ago to have had a second day.
        if (now - when).days >= CAME_BACK_AFTER and who in signed_in:
            batch.old_enough += 1
            batch.came_back += len(days.get(who, ())) >= 2
    found.batches = sorted(weeks.values(), key=lambda each: each.week, reverse=True)

    # How far readers reach. Counted across everybody and naming nobody (clause 3.7).
    ids = set(readers)
    parts = (
        ("Opened a text", set(opened)),
        (
            "Looked up a word",
            _people_with(db, "SELECT DISTINCT person FROM event WHERE kind = 'lookup'"),
        ),
        (
            "Played audio or video",
            _people_with(db, "SELECT DISTINCT person FROM event WHERE kind IN ('play', 'replay')"),
        ),
        ("Kept a word", kept),
        (
            "Marked words they already know",
            _people_with(db, "SELECT DISTINCT person FROM word WHERE source = 'claimed'"),
        ),
        ("Practised a hard spot", _people_with(db, "SELECT DISTINCT person FROM practised")),
        (
            "Talked in the chat",
            _people_with(db, "SELECT DISTINCT owner FROM job WHERE kind = 'chat'"),
        ),
        (
            "Brought a text of their own",
            _people_with(
                db, "SELECT DISTINCT owner FROM job WHERE kind IN ('build', 'subscription')"
            ),
        ),
        (
            "Exported their words",
            _people_with(
                db,
                "SELECT DISTINCT person FROM event"
                " WHERE kind = 'control' AND control LIKE 'export:%'",
            ),
        ),
        ("Read on a second day", {who for who, on in days.items() if len(on) >= 2}),
    )
    found.reach = [Reach(part, len(who & ids)) for part, who in parts]


def survey_store(
    store: Path,
    today: date | None = None,
    days: int = DAYS,
    operators: Iterable[str] | None = None,
) -> Survey:
    """`survey`, opening the database read-only.

    Read-only because this is a page anybody refreshing could hit while a reader is
    mid-sync, and because nothing here has any business writing to the store.
    """
    db = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        return survey(
            db,
            today=today,
            days=days,
            operators=operators_from_env() if operators is None else operators,
        )
    finally:
        db.close()
