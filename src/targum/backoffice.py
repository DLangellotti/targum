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

**At five thousand accounts (2026-10-27, targum-internal#542).** The page read every
account, every waiting address and every word, doc and day row ever written into Python
on each load. Now Accounts and the waitlist are pages of fifty, searched and ordered in
the store; the figures on a row are counted for the rows on the page and no others; and
what is summed across readers — Follow up, the weekly table, the reach, the headline —
is summed in SQL, one row per reader at most. The operator's addresses are left out in
the store too: `bare` is registered on the connection as an SQL function.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
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
#: The days after the day they were let in that are a reader's first week and fourth
#: (targum-internal#458): the beta's gate reads the first, Launch's go/no-go the fourth.
WEEK_ONE = (1, 7)
WEEK_FOUR = (22, 28)

GMAIL = frozenset({"gmail.com", "googlemail.com"})

#: How many rows a list on the page draws at once (targum-internal#542). The page drew
#: every account, every waiting address and a thirty-day row for each on every load,
#: which was fine at eight and is not at five thousand.
PER_PAGE = 50
#: How many people Follow up names at once, oldest first; the rest are counted.
FOLLOW_UP_SHOWN = 50
#: The longest search the page takes. An address is shorter than this.
SEARCH_MAX = 100

#: How Accounts may be ordered, each in the direction an operator wants first, and what
#: the page calls it. The first is the default: the newest account is the one to look at.
ACCOUNT_SORTS = {
    "joined": "Newest",
    "active": "Last active",
    "words": "Most words",
    "texts": "Most texts",
    "days": "Most days",
    "credits": "Most credits",
}
#: How the waitlist may be ordered. Oldest first is the order the door lets people in.
WAITING_SORTS = {"oldest": "Oldest first", "newest": "Newest first"}


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
    #: Seconds of the month's allowance used, the same sum `Store.hours_used` reads and
    #: `claim` holds them to; their allowance in seconds, None where nobody is held to a
    #: month; and what their jobs cost in model spend this month, in dollars
    #: (targum-internal#543, David 2026-10-27: "yes, show $").
    used: float = 0.0
    allowance: float | None = None
    spent: float = 0.0


def credits(seconds: float | None) -> str:
    """Seconds as credits, the way the page writes them: a credit is a minute, whole from
    ten up and to a tenth below, so a few seconds used does not read as nought."""
    if seconds is None:
        return "—"
    count = seconds / SECONDS_A_CREDIT
    said = f"{count:.0f}" if count >= 10 else f"{count:.1f}"
    return said.removesuffix(".0")


#: A credit is a minute of audio or video (2026-09-23), as `accounts.SECONDS_A_CREDIT`.
SECONDS_A_CREDIT = 60

#: The kinds a job is counted under on a reader's page, in this order. `gift` is not a
#: kind of its own on the row: it is any job targum paid for (`job.gift`).
KINDS = ("build", "subscription", "voice", "chat", "gift")


@dataclass
class Use:
    """One kind of job over a span: how many, the seconds they took of the month (or, for
    a gift, of targum's), and their model spend in dollars."""

    kind: str
    jobs: int = 0
    seconds: float = 0.0
    spent: float = 0.0


@dataclass
class Line:
    """One job on a reader's page: never its title or its source (clause 3.14)."""

    day: str
    kind: str
    seconds: float
    spent: float
    stage: str


@dataclass
class Reader:
    """One account's credits (`?who=<id>`, targum-internal#543): this month and all
    time by kind, and their latest jobs. Counts and stages only."""

    id: int
    email: str
    name: str
    joined: str
    allowance: float | None
    used: float
    spent: float
    month: list[Use] = field(default_factory=list)
    ever: list[Use] = field(default_factory=list)
    recent: list[Line] = field(default_factory=list)


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
    #: Of the same, how many came back to a second text: two texts opened, one of them
    #: last on a day after they were let in. `doc.opened` keeps only the latest opening,
    #: so this is as near to "returned to a second document" as their record goes.
    second_text: int = 0
    #: Of those let in long enough ago for the whole week to have passed, how many read
    #: on some day of it.
    week_one_over: int = 0
    week_one: int = 0
    week_four_over: int = 0
    week_four: int = 0


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
class Listing:
    """Which page of a list is asked for, and how many rows answer it
    (targum-internal#542): a search, an order and a page number, read off the address,
    and filled in by `survey` with how many matched."""

    q: str = ""
    sort: str = ""
    page: int = 1
    #: How many rows match the search, filled in by `survey`.
    matches: int = 0
    per: int = PER_PAGE

    @classmethod
    def read(
        cls,
        query: Mapping[str, Sequence[str]],
        search: str,
        order: str,
        page: str,
        sorts: Mapping[str, str],
    ) -> Listing:
        """A listing from a parsed query string, anything unknown taken as the default:
        an address is typed by hand as often as clicked."""

        def first(name: str) -> str:
            return (query.get(name) or [""])[0]

        said = " ".join(first(search).split())[:SEARCH_MAX]
        sort = first(order) if first(order) in sorts else next(iter(sorts))
        try:
            number = max(1, int(first(page) or 1))
        except ValueError:
            number = 1
        return cls(q=said, sort=sort, page=number)

    def pages(self) -> int:
        return max(1, -(-self.matches // self.per))

    def offset(self) -> int:
        return (self.page - 1) * self.per

    def first_row(self) -> int:
        """The number of the first row shown, counting from one; nought when none."""
        return min(self.matches, self.offset() + 1)

    def last_row(self) -> int:
        return min(self.matches, self.page * self.per)


@dataclass
class Survey:
    #: The page of accounts asked for (`account_listing`), with the per-row figures for
    #: those and no others (targum-internal#542).
    accounts: list[Account] = field(default_factory=list)
    #: Every account but the operator's, however many the page shows.
    accounts_total: int = 0
    account_listing: Listing = field(default_factory=lambda: Listing(sort="joined"))
    #: The waitlist's two lists, sharing one search and order: those still waiting, and
    #: those let in, folded beneath (design.md §12, 2026-10-15).
    waiting_listing: Listing = field(default_factory=lambda: Listing(sort="oldest"))
    let_in_listing: Listing = field(default_factory=lambda: Listing(sort="oldest"))
    #: How many on the waitlist have been let in.
    waiting_let_in: int = 0
    #: Waitlist sign-ups by the day they asked, over the window.
    asked_by_day: dict[str, int] = field(default_factory=dict)
    #: Accounts that did anything at all in the window, counted in the store.
    active_count: int = 0
    #: How many Follow up would name, of whom `follow_up` holds the oldest.
    follow_up_total: int = 0
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
        """Accounts that did anything at all in the window: counted in the store, since
        the days hold only the accounts on the page."""
        return self.active_count


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


#: Not one of the operator's addresses, compared bare. `bare` is registered on the
#: connection by `survey`, so the comparison is made in the store rather than over
#: every row pulled out of it (targum-internal#542).
NOT_MINE = "bare({column}) NOT IN (SELECT value FROM json_each(:mine))"

#: The last time anything of an account's moved, across everything that carries a stamp:
#: the same four records `Account.last_active` is read from.
LAST_MOVED = (
    "MAX(IFNULL((SELECT MAX(at) FROM word w WHERE w.person = p.id AND w.gone = 0), 0),"
    " IFNULL((SELECT MAX(at) FROM phrase f WHERE f.person = p.id AND f.gone = 0), 0),"
    " IFNULL((SELECT MAX(MAX(updated), MAX(opened)) FROM doc d"
    " WHERE d.person = p.id AND d.gone = 0), 0))"
)

#: Each of `ACCOUNT_SORTS` as an order, with the id last so a page boundary never moves
#: between two loads.
ACCOUNT_ORDERS = {
    "joined": "p.made DESC, p.id DESC",
    "active": f"{LAST_MOVED} DESC, p.id DESC",
    "words": "(SELECT COUNT(*) FROM word w WHERE w.person = p.id AND w.gone = 0) DESC, p.id DESC",
    "texts": "(SELECT COUNT(*) FROM doc d WHERE d.person = p.id AND d.gone = 0) DESC, p.id DESC",
    "days": "(SELECT COUNT(*) FROM day y WHERE y.person = p.id AND y.gone = 0) DESC, p.id DESC",
    # The month's credits: the sum `Store.hours_used` reads (targum-internal#543).
    "credits": "(SELECT IFNULL(SUM(length), 0) FROM job j"
    " WHERE j.owner = p.id AND j.length > 0 AND j.made >= :month) DESC, p.id DESC",
}

DAY_MS = 24 * 60 * 60 * 1000


def _like(said: str) -> str:
    """A search as a LIKE pattern that matches it anywhere, its own `%` and `_` meant
    literally, folded as `fold` folds what it is compared with."""
    escaped = fold(said).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def fold(text: object) -> str:
    """Text with its case taken off in every script. SQLite's LIKE folds ASCII alone, so
    «Дина» never found «дина» and a Hebrew name with Latin capitals beside it half-matched
    (qa on targum#952); the search compares this on both sides instead."""
    return str(text or "").casefold()


def month_from(today: date) -> int:
    """Midnight UTC on the first of `today`'s month, in milliseconds: `Library._month_from`
    for a day of the caller's choosing."""
    return int(datetime(today.year, today.month, 1, tzinfo=UTC).timestamp() * 1000)


def _functions(db: sqlite3.Connection) -> None:
    """The two functions the page's SQL calls, registered on this connection."""
    db.row_factory = sqlite3.Row
    db.create_function("bare", 1, bare, deterministic=True)
    db.create_function("fold", 1, fold, deterministic=True)


def _admins(db: sqlite3.Connection) -> set[str]:
    """The admins' addresses, as `Store.is_admin` compares them: an admin is on Plan
    (`plans.paid`), so their month is the plan's."""
    with contextlib.suppress(sqlite3.Error):
        return {str(row[0]).strip().lower() for row in db.execute("SELECT email FROM admin")}
    return set()


#: Each job's seconds and kind, as a reader's page counts them: a gift is counted by the
#: seconds it was quoted at, under `gift`, since it claimed none of the month; anything
#: else by the `length` its claim took.
JOB_SECONDS = "CASE WHEN gift = 1 THEN seconds ELSE length END"
JOB_KIND = "CASE WHEN gift = 1 THEN 'gift' ELSE kind END"


def _credits(
    db: sqlite3.Connection,
    found: Survey,
    named: Mapping[str, object],
    allowance: float | None,
    plan_allowance: float | None,
) -> None:
    """Each account on the page's month: credits used of their allowance, and $ spent."""
    if not found.accounts:
        return
    admins = _admins(db)
    for who in found.accounts:
        who.allowance = plan_allowance if who.email.strip().lower() in admins else allowance
    among = ",".join(str(who.id) for who in found.accounts)
    by_id = {who.id: who for who in found.accounts}
    # A store from before job.gift has the same sums: length was all a claim wrote.
    with contextlib.suppress(sqlite3.Error):
        for row in db.execute(
            "SELECT owner, SUM(CASE WHEN length > 0 THEN length ELSE 0 END) AS used,"  # noqa: S608 - ids are ints
            " SUM(spent) AS spent FROM job"
            f" WHERE made >= :month AND owner IN ({among}) GROUP BY owner",
            named,
        ):
            each = by_id[int(row["owner"])]
            each.used = float(row["used"] or 0)
            each.spent = float(row["spent"] or 0)


#: How many of a reader's latest jobs their page lists.
RECENT_JOBS = 50


def reader(
    db: sqlite3.Connection,
    who: int,
    today: date | None = None,
    operators: Iterable[str] = (),
    allowance: float | None = None,
    plan_allowance: float | None = None,
) -> Reader | None:
    """One account's credits, by kind, this month and all time, and its latest jobs —
    None for nobody, or for the operator, whom the page counts nowhere.

    Never the job's title, source, options or message: the columns are not read, so
    they cannot reach the page (clause 3.14).
    """
    _functions(db)
    now = today or datetime.now(UTC).date()
    mine = frozenset(bare(each) for each in operators)
    row = db.execute(
        "SELECT id, email, name, made FROM person p"  # noqa: S608
        f" WHERE id = :who AND {NOT_MINE.format(column='p.email')}",
        {"who": who, "mine": json.dumps(sorted(mine))},
    ).fetchone()
    if row is None:
        return None
    email = str(row["email"])
    month = month_from(now)
    found = Reader(
        id=int(row["id"]),
        email=email,
        name=str(row["name"] or ""),
        joined=_day(int(row["made"])),
        allowance=plan_allowance if email.strip().lower() in _admins(db) else allowance,
        used=0.0,
        spent=0.0,
    )

    def uses(since: int) -> dict[str, Use]:
        return {
            str(each["kind"]): Use(
                str(each["kind"]),
                int(each["n"]),
                float(each["seconds"] or 0),
                float(each["spent"] or 0),
            )
            for each in db.execute(
                f"SELECT {JOB_KIND} AS kind, COUNT(*) AS n, SUM({JOB_SECONDS}) AS seconds,"  # noqa: S608
                " SUM(spent) AS spent FROM job WHERE owner = ? AND made >= ? GROUP BY 1",
                (who, since),
            )
        }

    # The same kinds in the same order in both spans, so they stand side by side.
    ever, this_month = uses(0), uses(month)
    kinds = list(KINDS) + sorted(set(ever) - set(KINDS))
    found.ever = [ever.get(kind, Use(kind)) for kind in kinds]
    found.month = [this_month.get(kind, Use(kind)) for kind in kinds]
    # The month's figure is `Store.hours_used`'s own sum, and its money every job's.
    found.used = float(
        db.execute(
            "SELECT COALESCE(SUM(length), 0) FROM job"
            " WHERE length > 0 AND made >= ? AND owner IS ?",
            (month, who),
        ).fetchone()[0]
    )
    found.spent = sum(each.spent for each in found.month)
    found.recent = [
        Line(
            day=_day(int(each["made"])) if each["made"] else "",
            kind=str(each["kind"]),
            seconds=float(each["seconds"] or 0),
            spent=float(each["spent"] or 0),
            stage=str(each["stage"]),
        )
        for each in db.execute(
            f"SELECT made, {JOB_KIND} AS kind, {JOB_SECONDS} AS seconds, spent, stage"  # noqa: S608
            " FROM job WHERE owner = ? ORDER BY made DESC, rowid DESC LIMIT ?",
            (who, RECENT_JOBS),
        )
    ]
    return found


def reader_store(
    store: Path,
    who: int,
    today: date | None = None,
    operators: Iterable[str] | None = None,
    allowance: float | None = None,
    plan_allowance: float | None = None,
) -> Reader | None:
    """`reader`, opening the database read-only, as `survey_store` does."""
    db = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        return reader(
            db,
            who,
            today=today,
            operators=operators_from_env() if operators is None else operators,
            allowance=allowance,
            plan_allowance=plan_allowance,
        )
    finally:
        db.close()


def _one(db: sqlite3.Connection, sql: str, args: Mapping[str, object]) -> int:
    return int(db.execute(sql, args).fetchone()[0] or 0)


def _has_table(db: sqlite3.Connection, name: str) -> bool:
    return (
        db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
        is not None
    )


def survey(
    db: sqlite3.Connection,
    today: date | None = None,
    days: int = DAYS,
    operators: Iterable[str] = (),
    accounts: Listing | None = None,
    waitlist: Listing | None = None,
    let_in: Listing | None = None,
    allowance: float | None = None,
    plan_allowance: float | None = None,
) -> Survey:
    """Everything the page shows, asked of the store.

    `allowance` is a reader's month in seconds and `plan_allowance` an admin's, as
    `Library.allowance` gives them; None where nobody is held to a month.

    `accounts`, `waitlist` and `let_in` say which page of each list is wanted; each comes
    back with how many matched. Per-account figures are counted for the accounts on the
    page and no others, and everything summed across readers is summed in the store
    (targum-internal#542): the page drew every row of every table on every load.

    `gone` rows are excluded throughout. A word somebody deleted is not a word they
    have, and counting it would make the page disagree with the reader's own list — the
    one number on this page a reader could check.
    """
    _functions(db)
    now = today or datetime.now(UTC).date()
    window = [(now - timedelta(days=n)).isoformat() for n in range(days)]
    since = int(
        datetime.combine(now - timedelta(days=days - 1), datetime.min.time(), UTC).timestamp()
        * 1000
    )
    until = since + days * DAY_MS

    found = Survey(taken=datetime.now(UTC).isoformat(timespec="seconds"))
    # The operator's own addresses are nobody's data here, on any table (2026-10-15).
    mine = frozenset(bare(each) for each in operators)
    named: dict[str, object] = {"mine": json.dumps(sorted(mine)), "month": month_from(now)}

    _waitlist(
        db,
        found,
        named,
        since,
        waitlist or Listing(sort="oldest"),
        let_in or Listing(sort=(waitlist.sort if waitlist else "oldest")),
    )
    ids = _accounts(db, found, named, accounts or Listing(sort="joined"))
    _credits(db, found, named, allowance, plan_allowance)

    # The last thirty days, for the accounts on the page only.
    by_day = {when: Day(day=when) for when in window}
    if ids:
        among = ",".join(str(each) for each in ids)
        bounds = {"since": since, "until": until, "first": window[-1], "last": window[0]}
        for row in db.execute(
            "SELECT person, date(at / 1000, 'unixepoch') AS d, COUNT(*) AS n FROM word"  # noqa: S608 - ids are ints
            f" WHERE gone = 0 AND at >= :since AND at < :until AND person IN ({among})"
            " GROUP BY person, d",
            bounds,
        ):
            if row["d"] in by_day:
                by_day[row["d"]].words[int(row["person"])] = int(row["n"])
        for row in db.execute(
            "SELECT person, date(opened / 1000, 'unixepoch') AS d, COUNT(*) AS n FROM doc"  # noqa: S608 - ids are ints
            f" WHERE gone = 0 AND opened >= :since AND opened < :until AND person IN ({among})"
            " GROUP BY person, d",
            bounds,
        ):
            if row["d"] in by_day:
                by_day[row["d"]].opened[int(row["person"])] = int(row["n"])
        for row in db.execute(
            "SELECT person, day FROM day"  # noqa: S608 - ids are ints
            f" WHERE gone = 0 AND day BETWEEN :first AND :last AND person IN ({among})",
            bounds,
        ):
            by_day[str(row["day"])].read.add(int(row["person"]))
    found.days = [by_day[each] for each in window]

    # Who did anything in the window, counted across every account but the operator's.
    found.active_count = _one(
        db,
        "SELECT COUNT(*) FROM ("
        " SELECT person FROM word WHERE gone = 0 AND at >= :since AND at < :until"
        " UNION SELECT person FROM doc WHERE gone = 0 AND opened >= :since AND opened < :until"
        " UNION SELECT person FROM day WHERE gone = 0 AND day BETWEEN :first AND :last"
        f") a JOIN person p ON p.id = a.person WHERE {NOT_MINE.format(column='p.email')}",
        {**named, "since": since, "until": until, "first": window[-1], "last": window[0]},
    )

    _growth(db, found, now, mine)

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


def _waitlist(
    db: sqlite3.Connection,
    found: Survey,
    named: Mapping[str, object],
    since: int,
    still: Listing,
    done: Listing,
) -> None:
    """The front door's counts, and the page asked for of each of its two lists."""
    found.waiting_listing, found.let_in_listing = still, done
    # The front door, if this database has one yet. A store written before schema 17
    # has no such table, and the page is not the place to find that out.
    if not _has_table(db, "waiting"):
        return
    mine = f"WHERE {NOT_MINE.format(column='email')}"
    with contextlib.suppress(sqlite3.Error):
        counted = {
            str(row["state"]): int(row["n"])
            for row in db.execute(
                f"SELECT state, COUNT(*) AS n FROM waiting {mine} GROUP BY state",  # noqa: S608
                named,
            )
        }
        found.waiting = {state: counted.get(state, 0) for state in ("pending", "on", "off")}
        found.waiting_let_in = _one(
            db,
            f"SELECT COUNT(*) FROM waiting {mine} AND invited != 0",  # noqa: S608
            named,
        )
        # Confirmed and not yet let in — the number the door's own press would take from.
        found.waiting_for_a_way_in = _one(
            db,
            f"SELECT COUNT(*) FROM waiting {mine} AND state = 'on' AND invited = 0",  # noqa: S608
            named,
        )
        found.asked_by_day = {
            str(row["d"]): int(row["n"])
            for row in db.execute(
                "SELECT date(asked / 1000, 'unixepoch') AS d, COUNT(*) AS n FROM waiting"  # noqa: S608
                f" {mine} AND asked >= :since GROUP BY d",
                {**named, "since": since},
            )
        }
        rows: list[sqlite3.Row] = []
        for listing, which in ((still, "invited = 0"), (done, "invited != 0")):
            clause = f"{mine} AND {which}"
            args = dict(named)
            if listing.q:
                clause += " AND fold(email) LIKE :like ESCAPE '\\'"
                args["like"] = _like(listing.q)
            listing.matches = _one(db, f"SELECT COUNT(*) FROM waiting {clause}", args)  # noqa: S608
            listing.page = min(listing.page, listing.pages())
            # Oldest first is the order they would be let in.
            order = "asked, rowid" if listing.sort == "oldest" else "asked DESC, rowid DESC"
            rows += db.execute(
                f"SELECT rowid AS row_, * FROM waiting {clause}"  # noqa: S608
                f" ORDER BY {order} LIMIT :per OFFSET :skip",
                {**args, "per": listing.per, "skip": listing.offset()},
            ).fetchall()
        rows.sort(
            key=lambda row: (int(row["asked"]), int(row["row_"])), reverse=still.sort != "oldest"
        )
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
            for row in rows
        ]
    # How many joined through each page, so `/aliyah` can be told from the front door
    # (targum-internal#388). Unknown is counted too, under "". Most first, and between
    # two the same, the one that brought somebody first.
    with contextlib.suppress(sqlite3.Error):
        found.waiting_by_page = {
            str(row["page"] or ""): int(row["n"])
            for row in db.execute(
                f"SELECT page, COUNT(*) AS n FROM waiting {mine}"  # noqa: S608
                " GROUP BY page ORDER BY n DESC, MIN(asked), MIN(rowid)",
                named,
            )
        }


def _accounts(
    db: sqlite3.Connection, found: Survey, named: Mapping[str, object], listing: Listing
) -> list[int]:
    """The page of accounts asked for, and what each on it has; their ids, in order."""
    mine = NOT_MINE.format(column="p.email")
    found.accounts_total = _one(db, f"SELECT COUNT(*) FROM person p WHERE {mine}", named)  # noqa: S608
    clause = mine
    args = dict(named)
    if listing.q:
        clause += (
            " AND (fold(p.email) LIKE :like ESCAPE '\\' OR fold(p.name) LIKE :like ESCAPE '\\')"
        )
        args["like"] = _like(listing.q)
    listing.matches = _one(db, f"SELECT COUNT(*) FROM person p WHERE {clause}", args)  # noqa: S608
    listing.page = min(listing.page, listing.pages())
    order = ACCOUNT_ORDERS.get(listing.sort, ACCOUNT_ORDERS["joined"])
    people = db.execute(
        f"SELECT p.id, p.email, p.name, p.made, p.leaving FROM person p WHERE {clause}"  # noqa: S608
        f" ORDER BY {order} LIMIT :per OFFSET :skip",
        {**args, "per": listing.per, "skip": listing.offset()},
    ).fetchall()
    found.account_listing = listing
    ids = [int(row["id"]) for row in people]
    if not ids:
        return ids
    among = ",".join(str(each) for each in ids)

    counted = {
        name: {
            int(row["person"]): int(row["n"])
            for row in _rows(db, sql.format(among=among))  # noqa: S608 - ids are ints
        }
        for name, sql in (
            (
                "words",
                "SELECT person, COUNT(*) n FROM word"
                " WHERE gone = 0 AND person IN ({among}) GROUP BY person",
            ),
            (
                "learned",
                "SELECT person, COUNT(*) n FROM word"
                " WHERE gone = 0 AND learned = 1 AND person IN ({among}) GROUP BY person",
            ),
            (
                "phrases",
                "SELECT person, COUNT(*) n FROM phrase"
                " WHERE gone = 0 AND person IN ({among}) GROUP BY person",
            ),
            (
                "texts",
                "SELECT person, COUNT(*) n FROM doc"
                " WHERE gone = 0 AND person IN ({among}) GROUP BY person",
            ),
            (
                "days",
                "SELECT person, COUNT(*) n FROM day"
                " WHERE gone = 0 AND person IN ({among}) GROUP BY person",
            ),
        )
    }
    # A targum finishes at the end of a chapter now, so a document is worth the greater
    # of its old whole-document record and the sections finished since — never their sum
    # (targum-internal#173). The same rule the ledger draws, asked of the server's copy.
    finished: dict[int, int] = {}
    for row in _rows(
        db,
        "SELECT d.person AS person, d.hash AS hash, d.done AS done,"  # noqa: S608 - ids are ints
        " (SELECT COUNT(*) FROM section s WHERE s.person = d.person AND s.hash = d.hash"
        "  AND s.gone = 0) AS parts"
        f" FROM doc d WHERE d.gone = 0 AND d.person IN ({among})",
    ):
        worth = max(1 if row["done"] else 0, int(row["parts"] or 0))
        if worth:
            finished[int(row["person"])] = finished.get(int(row["person"]), 0) + worth

    # The last day anything moved, per person, across everything that carries a stamp.
    moved: dict[int, int] = {}
    for sql in (
        "SELECT person, MAX(at) last FROM word WHERE gone = 0 AND person IN ({among})"
        " GROUP BY person",
        "SELECT person, MAX(at) last FROM phrase WHERE gone = 0 AND person IN ({among})"
        " GROUP BY person",
        "SELECT person, MAX(MAX(updated), MAX(opened)) last FROM doc"
        " WHERE gone = 0 AND person IN ({among}) GROUP BY person",
    ):
        for row in _rows(db, sql.format(among=among)):
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
    return ids


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


#: One row per reader with everything Follow up, the weekly table and the reach need of
#: them, summed in the store (targum-internal#542): their days — marked, opened a text,
#: kept a word — counted, the last of them, and whether any fell in their first week or
#: fourth, counted from the day they were let in or, with no guest list, joined.
READERS = """
WITH staff(e) AS (SELECT value FROM json_each(:staff)),
inv(e, at) AS ({invited}),
r AS (
  SELECT p.id, p.email, p.made, p.leaving, inv.at AS let_in,
         date(COALESCE(NULLIF(inv.at, 0), p.made) / 1000, 'unixepoch') AS start
  FROM person p LEFT JOIN inv ON inv.e = lower(p.email)
  WHERE bare(p.email) NOT IN (SELECT e FROM staff)
),
acts(person, d) AS (
  SELECT person, day FROM day WHERE gone = 0
  UNION SELECT person, date(opened / 1000, 'unixepoch') FROM doc WHERE opened > 0
  UNION SELECT person, date(at / 1000, 'unixepoch') FROM word WHERE at > 0
),
a AS (
  SELECT r.id AS person, COUNT(*) AS n, MAX(acts.d) AS last,
    MAX(acts.d BETWEEN date(r.start, '+{one_from} days') AND date(r.start, '+{one_to} days'))
      AS w1,
    MAX(acts.d BETWEEN date(r.start, '+{four_from} days') AND date(r.start, '+{four_to} days'))
      AS w4
  FROM r JOIN acts ON acts.person = r.id GROUP BY r.id
)
SELECT r.id, r.email, r.made, r.leaving, r.let_in, r.start,
  IFNULL(a.n, 0) AS days, IFNULL(a.last, '') AS last,
  IFNULL(a.w1, 0) AS w1, IFNULL(a.w4, 0) AS w4,
  (SELECT COUNT(*) FROM doc d WHERE d.person = r.id AND d.opened > 0) AS opened,
  (SELECT MAX(opened) FROM doc d WHERE d.person = r.id AND d.opened > 0) AS last_opened,
  EXISTS (SELECT 1 FROM word w WHERE w.person = r.id AND w.source != 'claimed') AS kept,
  EXISTS (SELECT 1 FROM session s WHERE s.person = r.id) AS session
FROM r LEFT JOIN a ON a.person = r.id
ORDER BY r.id
"""

#: The guest list, one row per address, the operator's left out.
INVITED_ROWS = (
    "SELECT lower(email), MAX(at) FROM invited"
    " WHERE bare(email) NOT IN (SELECT e FROM staff) GROUP BY lower(email)"
    # In the order they were let in, as the list was before it was counted here.
    " ORDER BY MIN(rowid)"
)


def _growth(
    db: sqlite3.Connection,
    found: Survey,
    now: date,
    operators: frozenset[str],
) -> None:
    """Who to write to, each week's people, and how far readers reach.

    Everything named here comes from what clause 3.2 holds — texts opened, words kept,
    days read — and from the guest list. The record of use (3.6) is read only for the
    reach, as a count of people with no one in it.
    """
    staff = _staff(db, operators)
    named = {"staff": json.dumps(sorted(staff))}
    guests = _has_table(db, "invited")
    readers = db.execute(
        READERS.format(
            invited=INVITED_ROWS if guests else "SELECT '', 0 WHERE 0",
            one_from=WEEK_ONE[0],
            one_to=WEEK_ONE[1],
            four_from=WEEK_FOUR[0],
            four_to=WEEK_FOUR[1],
        ),
        named,
    ).fetchall()
    found.readers = len(readers)
    # Signed in: a session now, or anything of their own at all. Sessions are pruned, and
    # an account can exist before its first sign-in when a saved link was built for it.
    signed_in = {int(row["id"]) for row in readers if row["session"] or row["days"]}

    let_in: dict[str, int] = {}
    if guests:
        let_in = {
            str(row[0]): int(row[1])
            for row in db.execute(
                f"WITH staff(e) AS (SELECT value FROM json_each(:staff)) {INVITED_ROWS}", named
            )
        }
    by_email = {str(row["email"]).lower(): int(row["id"]) for row in readers}

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
    for row in readers:
        who = int(row["id"])
        if row["leaving"] or who not in signed_in:
            continue
        email = str(row["email"])
        joined = _day(int(row["made"]))
        texts = int(row["opened"])
        if texts <= 1 and not row["kept"]:
            if (now - date.fromisoformat(joined)).days >= NOTHING_KEPT_AFTER:
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
        last = str(row["last"])
        if last and (now - date.fromisoformat(last)).days >= QUIET_AFTER:
            follow.append(FollowUp(email, f"Last read {_said(last)}", "write", last))
    found.follow_up_total = len(follow)
    found.follow_up = sorted(follow, key=lambda each: each.since)[:FOLLOW_UP_SHOWN]

    # Each week's people. The week they were let in, or joined where there was no
    # guest list yet.
    weeks: dict[str, Batch] = {}
    for at in let_in.values():
        when = date.fromisoformat(_day(at))
        batch = weeks.setdefault(_monday(when), Batch(_monday(when)))
        batch.let_in += 1
    for row in readers:
        who = int(row["id"])
        email = str(row["email"]).lower()
        when = date.fromisoformat(str(row["start"]))
        batch = weeks.setdefault(_monday(when), Batch(_monday(when)))
        if email not in let_in:
            batch.let_in += 1
        texts = int(row["opened"])
        batch.signed_in += who in signed_in
        batch.opened += texts > 0
        batch.kept += bool(row["kept"])
        # Only those let in long enough ago to have had a second day.
        if (now - when).days >= CAME_BACK_AFTER and who in signed_in:
            batch.old_enough += 1
            batch.came_back += int(row["days"]) >= 2
            last_opened = _day(int(row["last_opened"])) if row["last_opened"] else ""
            batch.second_text += texts >= 2 and last_opened > str(when)
        # A week counts for those who have had the whole of it.
        if (now - when).days > WEEK_ONE[1] and who in signed_in:
            batch.week_one_over += 1
            batch.week_one += bool(row["w1"])
        if (now - when).days > WEEK_FOUR[1] and who in signed_in:
            batch.week_four_over += 1
            batch.week_four += bool(row["w4"])
    found.batches = sorted(weeks.values(), key=lambda each: each.week, reverse=True)

    # How far readers reach. Counted across everybody and naming nobody (clause 3.7), in
    # the store: a count of people, never a list of them.
    among = (
        "IN (SELECT id FROM person WHERE bare(email) NOT IN (SELECT value FROM json_each(:staff)))"
    )

    def reached(sql: str) -> int:
        with contextlib.suppress(sqlite3.Error):
            return _one(db, sql.format(readers=among), named)
        return 0

    parts = (
        ("Opened a text", sum(1 for row in readers if row["opened"])),
        (
            "Looked up a word",
            reached(
                "SELECT COUNT(DISTINCT person) FROM event"
                " WHERE kind = 'lookup' AND person {readers}"
            ),
        ),
        (
            "Played audio or video",
            reached(
                "SELECT COUNT(DISTINCT person) FROM event"
                " WHERE kind IN ('play', 'replay') AND person {readers}"
            ),
        ),
        ("Kept a word", sum(1 for row in readers if row["kept"])),
        (
            "Marked words they already know",
            reached(
                "SELECT COUNT(DISTINCT person) FROM word"
                " WHERE source = 'claimed' AND person {readers}"
            ),
        ),
        (
            "Practised a hard spot",
            reached("SELECT COUNT(DISTINCT person) FROM practised WHERE person {readers}"),
        ),
        (
            "Talked in the chat",
            reached(
                "SELECT COUNT(DISTINCT owner) FROM job WHERE kind = 'chat' AND owner {readers}"
            ),
        ),
        (
            "Brought a text of their own",
            reached(
                "SELECT COUNT(DISTINCT owner) FROM job"
                " WHERE kind IN ('build', 'subscription') AND owner {readers}"
            ),
        ),
        (
            "Exported their words",
            reached(
                "SELECT COUNT(DISTINCT person) FROM event"
                " WHERE kind = 'control' AND control LIKE 'export:%' AND person {readers}"
            ),
        ),
        ("Read on a second day", sum(1 for row in readers if int(row["days"]) >= 2)),
    )
    found.reach = [Reach(part, people) for part, people in parts]


def survey_store(
    store: Path,
    today: date | None = None,
    days: int = DAYS,
    operators: Iterable[str] | None = None,
    accounts: Listing | None = None,
    waitlist: Listing | None = None,
    let_in: Listing | None = None,
    allowance: float | None = None,
    plan_allowance: float | None = None,
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
            accounts=accounts,
            waitlist=waitlist,
            let_in=let_in,
            allowance=allowance,
            plan_allowance=plan_allowance,
        )
    finally:
        db.close()
