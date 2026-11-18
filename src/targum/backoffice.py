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
long it is kept. It is listed on the Overview with its page, window, language and build,
and nothing else a reader wrote ever joins it. Fault reports from browsers (#457) are
counted under Operations by message and page, never per reader.

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
import unicodedata
from bisect import bisect_right
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields
from datetime import UTC, date, datetime, timedelta
from functools import cache
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
#: And their second (design.md §12, 2026-11-17): the overview's funnel ends on it, the
#: first week a reader came back to on their own rather than on the invitation's pull.
WEEK_TWO = (8, 14)
WEEK_FOUR = (22, 28)
#: The Monday of the week batch one was let in: David sent its invitations himself and
#: confirmed it on 2026-10-21 (targum-internal#460). The beta's own row counts every week
#: from here on, so the go/no-go (targum-internal#486) quotes one line rather than adding
#: weeks, and the alpha's readers before it stay out of the beta's number.
BETA_FROM = date(2026, 10, 19)

GMAIL = frozenset({"gmail.com", "googlemail.com"})

#: How many pages or link tags the waitlist's and the accounts' "from" lines name before
#: the rest are counted together as other (qa-claude on targum#1186): a tag is anything a
#: form says, so the line has to stay one line however many there are.
TAGS_SHOWN = 10

#: The key the rest are counted under. No tag has a space in it, so none can be it.
OTHER_TAGS = "other"


def _top_tags(counted: dict[str, int]) -> dict[str, int]:
    """The `TAGS_SHOWN` biggest, in the order given, and the rest summed as other."""
    shown = dict(list(counted.items())[:TAGS_SHOWN])
    rest = sum(list(counted.values())[TAGS_SHOWN:])
    if rest:
        shown[OTHER_TAGS] = rest
    return shown


#: Where the back office is served. `serve.BACK_OFFICE_ROUTE` says the same, and a test
#: holds the two together.
ROUTE = "/back-office"

#: The back office's pages, in the bar's order, by the last part of their address
#: (design.md §12, 2026-11-17): one desk screen each. The overview is the bare address,
#: and a reader's own page is `readers/<id>`.
PAGES = {
    "overview": "Overview",
    "readers": "Readers",
    "waitlist": "Waitlist",
    "traffic": "Traffic",
    "shelf": "Shelf",
    "operations": "Operations",
}

#: The two searches' names in an address. Never `q` or `wq`: the proxy writes every
#: address it is asked for into `targum.log`, so a search for a reader's address put the
#: address there, and `deploy/Caddyfile` now deletes these two from the log by name.
ACCOUNT_SEARCH = "bq"
WAITING_SEARCH = "bwq"


def page_route(page: str) -> str:
    """A back-office page's address: the overview is the bare one."""
    return ROUTE if page == "overview" else f"{ROUTE}/{page}"


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
    "flags": "Most flags",
}
#: How the waitlist may be ordered. Oldest first is the order the door lets people in.
WAITING_SORTS = {"oldest": "Oldest first", "newest": "Newest first", "flags": "Most flags"}

#: What might make a sign-up fake, each said as a plain reason (targum-internal#544).
#: Read only from what the store already holds — David, 2026-10-27: no address or
#: browser is stored for this, and the privacy notice does not change. A flag is a
#: reason to look, never a verdict: each has an innocent reading on its own.
FLAGS = {
    "unconfirmed": "Never confirmed their email",
    "instant": "Confirmed within 10 seconds of asking",
    "same_inbox": "Same inbox as another address",
    "throwaway": "Throwaway email domain",
    "burst": "One of 5 or more sign-ups within 10 minutes",
    "unused": "Let in, never signed in",
    "idle": "Signed in, nothing done",
    "digits": "Mostly digits before the @",
}
#: David's thresholds, 2026-10-27: 10 seconds, 5 in 10 minutes, 2 days.
CONFIRMED_TOO_FAST_MS = 10_000
BURST = 5
BURST_WITHIN_MS = 10 * 60 * 1000
FLAG_AFTER_DAYS = 2
#: How many flags make an address "Possibly fake" for the filter.
FAKE_AT = 2

#: The throwaway domains, vendored from a CC0 list (see the file's head and NOTICE).
#: Read once, from the package: nothing is fetched at runtime.
DISPOSABLE = Path(__file__).with_name("disposable.txt")


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
    #: What might make this sign-up fake, as reasons (targum-internal#544).
    flags: list[str] = field(default_factory=list)


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
    """One account's credits (`/back-office/readers/<id>`, targum-internal#543): this
    month and all time by kind, and their latest jobs. Counts and stages only."""

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
    #: What might make this sign-up fake, as reasons, and whether the operator turned it
    #: off from here (targum-internal#544).
    flags: list[str] = field(default_factory=list)
    turned_off: bool = False


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
    #: last on a day after the first day they opened a text or kept a word (UTC, as the
    #: opening is), which is not always the day they were let in: somebody who signs in
    #: three days late and opens two texts that evening has not come back yet.
    #: `doc.opened` keeps only the latest opening, so this is as near to "returned to a
    #: second document" as their record goes.
    second_text: int = 0
    #: Of those let in long enough ago for the whole week to have passed, how many read
    #: on some day of it.
    week_one_over: int = 0
    week_one: int = 0
    week_two_over: int = 0
    week_two: int = 0
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
    #: Only those with `FAKE_AT` flags or more: "Possibly fake (2+)".
    fake: bool = False

    @classmethod
    def read(
        cls,
        query: Mapping[str, Sequence[str]],
        search: str,
        order: str,
        page: str,
        sorts: Mapping[str, str],
        fake: str = "",
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
        return cls(q=said, sort=sort, page=number, fake=bool(fake and first(fake)))

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
    #: Addresses with `FAKE_AT` flags or more, across the waitlist and accounts.
    possibly_fake: int = 0
    days: list[Day] = field(default_factory=list)
    taken: str = ""
    #: How many are waiting at the front door, by state (targum-internal#69), and who.
    waiting: dict[str, int] = field(default_factory=dict)
    waiting_list: list[Waiting] = field(default_factory=list)
    #: Confirmed and not yet let in — the number the door's own press would take from.
    waiting_for_a_way_in: int = 0
    #: How many joined through each of targum's pages, or each link's tag (#676); ""
    #: is unknown.
    waiting_by_page: dict[str, int] = field(default_factory=dict)
    #: How many accounts came in by each page or link tag (targum-internal#676): the
    #: open door's signups, and those let in from the waitlist. "" is unknown.
    accounts_by_came_from: dict[str, int] = field(default_factory=dict)
    #: What came in through the connector in the window (targum-internal#408): texts
    #: quoted from a host, how many of those the reader pressed, how many finished, and
    #: sets made there. Read off the job and playlist rows, which say so themselves, so
    #: there is no counter of its own to drift from them.
    connector: dict[str, int] = field(default_factory=dict)
    #: Who to write to (2026-10-15), oldest first.
    follow_up: list[FollowUp] = field(default_factory=list)
    #: Every address Follow up would name, however many are shown: the Readers table's
    #: "Follow-up due" filter (design's plan, 2026-11-17, PR 4).
    follow_up_due: set[str] = field(default_factory=set)
    #: Each week's people, newest first, and how far they got.
    batches: list[Batch] = field(default_factory=list)
    #: Every week from `BETA_FROM` on, added up: the beta's gate in one row
    #: (targum-internal#458). None until a week of the beta has anybody in it.
    beta: Batch | None = None
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
    "flags": "{score} DESC, p.made DESC, p.id DESC",
}

#: An address's count of flags, from the table `_flag` fills for this request.
#: Keyed by `fold`, as `_flag` keys it: SQLite's lower() folds ASCII alone, and a
#: Cyrillic address missed its own flags (qa on targum#957).
SCORE = "IFNULL((SELECT score FROM temp.bo_flags f WHERE f.address = fold(trim({column}))), 0)"

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
    """The addresses on Plan (`plans.paid`), so their month is the plan's: the admins, as
    `Store.is_admin` compares them, the beta readers comped to Plan today (schema 72,
    targum-internal#59), whose comp ends on its day, and the readers whose Paddle plan
    holds (schema 74, `plans.subscribed`), a failed renewal inside its grace included."""
    on_plan: set[str] = set()
    with contextlib.suppress(sqlite3.Error):
        on_plan |= {str(row[0]).strip().lower() for row in db.execute("SELECT email FROM admin")}
    with contextlib.suppress(sqlite3.Error):
        today = datetime.now(UTC).date().isoformat()
        on_plan |= {
            str(row[0]).strip().lower()
            for row in db.execute("SELECT email FROM person WHERE plan_until > ?", (today,))
        }
    from .plans import GRACE_DAYS

    with contextlib.suppress(sqlite3.Error):
        graced = int(datetime.now(UTC).timestamp() * 1000) - GRACE_DAYS * 86_400_000
        on_plan |= {
            str(row[0]).strip().lower()
            for row in db.execute(
                "SELECT person.email FROM plan JOIN person ON person.id = plan.person"
                " WHERE plan.status IN ('active', 'trialing')"
                " OR (plan.status = 'past_due' AND plan.past_due_since > ?)",
                (graced,),
            )
        }
    return on_plan


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


#: The largest id SQLite stores: anything past it is nobody, not an overflow.
ID_MAX = 2**63 - 1


def account_id(said: str) -> int | None:
    """An account id in a reader page's address (or the old `?who=`), or None for
    anything that is not one: `int` accepts "²" from `isdigit` no more than it does a
    30-digit number SQLite cannot bind, and either raised out of the request (qa on
    targum#956)."""
    try:
        who = int(said.strip())
    except ValueError:
        return None
    return who if 1 <= who <= ID_MAX else None


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


@cache
def _disposable() -> frozenset[str]:
    """The vendored throwaway domains, one a line, `#` lines being its head."""
    lines = DISPOSABLE.read_text(encoding="utf-8").splitlines()
    return frozenset(
        line.strip().lower() for line in lines if line.strip() and not line.startswith("#")
    )


def flag_key(email: str) -> str:
    """The key an address's flags are kept under, here and in `SCORE`'s SQL alike."""
    return fold(email.strip())


#: The free consumer mail providers (targum-internal#485). Anybody can make an address at
#: one in a minute, so the open door's per-domain count would only let a script shut them
#: out for everybody else; at these the visitor's own count and the throwaway list hold
#: instead. By `registrable` domain. A list kept here by hand, never fetched: a provider
#: missing from it is counted like any company's domain, so add one when a reader's
#: address turns up refused (qa-claude, round 2 on targum#1160).
WEBMAIL = frozenset(
    {
        *GMAIL,
        # Microsoft
        "outlook.com",
        "outlook.fr",
        "outlook.de",
        "outlook.it",
        "outlook.es",
        "outlook.co.il",
        "hotmail.com",
        "hotmail.co.uk",
        "hotmail.fr",
        "hotmail.de",
        "hotmail.it",
        "hotmail.es",
        "hotmail.co.il",
        "live.com",
        "live.co.uk",
        "live.fr",
        "live.de",
        "live.it",
        "live.ru",
        "msn.com",
        # Yahoo, AOL
        "yahoo.com",
        "yahoo.co.uk",
        "yahoo.fr",
        "yahoo.de",
        "yahoo.it",
        "yahoo.es",
        "yahoo.co.jp",
        "ymail.com",
        "rocketmail.com",
        "aol.com",
        # Apple
        "icloud.com",
        "me.com",
        "mac.com",
        # Private mail
        "proton.me",
        "protonmail.com",
        "pm.me",
        "tuta.io",
        "tutanota.com",
        "tutanota.de",
        "duck.com",
        "fastmail.com",
        "zoho.com",
        "mail.com",
        # Russian and the neighbours'
        "mail.ru",
        "bk.ru",
        "list.ru",
        "inbox.ru",
        "internet.ru",
        "yandex.ru",
        "yandex.com",
        "yandex.by",
        "yandex.ua",
        "yandex.kz",
        "ya.ru",
        "rambler.ru",
        "ukr.net",
        # Israel
        "walla.co.il",
        "walla.com",
        # Europe
        "gmx.com",
        "gmx.de",
        "gmx.net",
        "gmx.fr",
        "web.de",
        "t-online.de",
        "orange.fr",
        "wanadoo.fr",
        "free.fr",
        "laposte.net",
        "sfr.fr",
        "libero.it",
        "virgilio.it",
        "seznam.cz",
        # Asia
        "qq.com",
        "163.com",
        "126.com",
        "naver.com",
    }
)

#: The second-level labels a country's registry sells under (`co.il`, `org.uk`, `ac.il`),
#: so that `registrable` keeps three labels there rather than two.
SECOND_LEVEL = frozenset(
    {"ac", "co", "com", "edu", "gov", "net", "org", "ne", "or", "go", "muni", "k12", "ltd"}
)

#: Suffixes under which unrelated owners each have their own name, beyond the country
#: rule above (qa-claude, round 2 on targum#1160): `eu.org` gives subdomains away with
#: mail, `nhs.uk` is every hospital trust, and a Canadian province's `qc.ca` is a whole
#: province's towns. Merged, one owner could spend everybody's count. A short list
#: rather than the public suffix list, so nothing is fetched at runtime; a miss only
#: makes a domain's count a little wider.
SHARED_SUFFIXES = frozenset(
    {
        "eu.org",
        "us.org",
        "nhs.uk",
        "police.uk",
        "sch.uk",
        "ab.ca",
        "bc.ca",
        "mb.ca",
        "nb.ca",
        "nl.ca",
        "ns.ca",
        "nt.ca",
        "nu.ca",
        "on.ca",
        "pe.ca",
        "qc.ca",
        "sk.ca",
        "yt.ca",
        "github.io",
        "gitlab.io",
        "duckdns.org",
        "no-ip.org",
    }
)


def mail_domain(email: str) -> str:
    """The domain of an address in one form: NFKC-folded, so `mailinator.com` spelt in
    full-width letters or with a full-width dot is `mailinator.com`, its ideographic full
    stops read as dots, case taken off and a trailing dot dropped (qa-claude on
    targum#1160)."""
    domain = unicodedata.normalize("NFKC", email.strip()).rpartition("@")[2]
    return domain.replace("\u3002", ".").casefold().strip(".")


def registrable(domain: str) -> str:
    """The part of a domain somebody registers: `x1.evil.org` is `evil.org`, and
    `mail.walla.co.il` is `walla.co.il`. The open door counts by this, so a catch-all
    under made-up subdomains is one domain and not a new one each time (targum#1160)."""
    labels = [label for label in domain.casefold().split(".") if label]
    if len(labels) <= 2:
        return ".".join(labels)
    shared = ".".join(labels[-2:]) in SHARED_SUFFIXES
    keep = 3 if shared or (len(labels[-1]) == 2 and labels[-2] in SECOND_LEVEL) else 2
    return ".".join(labels[-keep:])


def throwaway(email: str) -> bool:
    """Whether an address is at a throwaway domain, or under one: `x.mailinator.com` is
    as much one as `mailinator.com`, and so is its full-width spelling (`mail_domain`)."""
    domain = mail_domain(email)
    known = _disposable()
    labels = domain.split(".")
    return any(".".join(labels[n:]) in known for n in range(len(labels) - 1))


def mostly_digits(email: str) -> bool:
    """Whether more than half of what is before the @ is digits, four characters or more:
    `48213377@` is, `anna1990@` is not."""
    local = bare(email).partition("@")[0]
    return len(local) >= 4 and 2 * sum(ch.isdigit() for ch in local) > len(local)


def _ids(db: sqlite3.Connection, sql: str) -> set[int]:
    with contextlib.suppress(sqlite3.Error):
        return {int(row[0]) for row in db.execute(sql) if row[0] is not None}
    return set()


def _flag(db: sqlite3.Connection, at: int, mine: frozenset[str]) -> dict[str, list[str]]:
    """What might make each address fake, by its address in lower case: the keys of
    `FLAGS` that hold, in their order. Every address on the waitlist or with an account
    is asked, one row each, and the counts go into `temp.bo_flags` for the lists to
    filter and order by — a table of this connection's own, which a read-only
    connection may still write.

    `at` is the moment "two days ago" is counted back from.
    """
    old = at - FLAG_AFTER_DAYS * DAY_MS
    # The operator's addresses, the admins' and the test accounts' are nobody's sign-up:
    # an admin read as "Signed in, nothing done" (qa on targum#957).
    staff = _staff(db, mine)
    waiting: dict[str, sqlite3.Row] = {}
    if _has_table(db, "waiting"):
        for row in db.execute("SELECT email, state, asked, joined, invited FROM waiting"):
            if bare(str(row["email"])) not in staff:
                waiting[flag_key(str(row["email"]))] = row
    people: dict[str, sqlite3.Row] = {
        flag_key(str(row["email"])): row
        for row in db.execute("SELECT id, email, made FROM person")
        if bare(str(row["email"])) not in staff
    }
    let_in: dict[str, int] = {}
    if _has_table(db, "invited"):
        for row in db.execute("SELECT email, at FROM invited"):
            key = flag_key(str(row[0]))
            let_in[key] = max(let_in.get(key, 0), int(row[1] or 0))
    # Signed in: a session, or a sign-in link that was used. Did something: anything of
    # their own kept, opened, read or asked for.
    signed = _ids(db, "SELECT DISTINCT person FROM session") | _ids(
        db, "SELECT DISTINCT person FROM link WHERE used IS NOT NULL AND purpose = 'sign-in'"
    )
    did = (
        _ids(db, "SELECT DISTINCT person FROM word")
        | _ids(db, "SELECT DISTINCT person FROM doc WHERE opened > 0")
        | _ids(db, "SELECT DISTINCT person FROM day")
        | _ids(db, "SELECT DISTINCT owner FROM job")
    )
    addresses = set(waiting) | set(people)
    inboxes = Counter(bare(each) for each in addresses)
    # In a burst: some ten minutes that hold this sign-up hold five or more. A sliding
    # window over the times in order, not ten minutes either side of each, which is twenty
    # (qa on targum#957).
    asked = sorted(int(row["asked"]) for row in waiting.values())
    bursting: set[int] = set()
    for start, when in enumerate(asked):
        end = bisect_right(asked, when + BURST_WITHIN_MS)
        if end - start >= BURST:
            bursting.update(asked[start:end])

    found: dict[str, list[str]] = {}
    for email in addresses:
        row, person = waiting.get(email), people.get(email)
        held: set[str] = set()
        if row is not None:
            asked_at, joined = int(row["asked"]), int(row["joined"] or 0)
            if row["state"] == "pending" and not joined and asked_at <= old:
                held.add("unconfirmed")
            if joined and 0 <= joined - asked_at < CONFIRMED_TOO_FAST_MS:
                held.add("instant")
            if asked_at in bursting:
                held.add("burst")
        if inboxes[bare(email)] > 1:
            held.add("same_inbox")
        if throwaway(email):
            held.add("throwaway")
        if mostly_digits(email):
            held.add("digits")
        let_at = let_in.get(email) or (int(row["invited"] or 0) if row is not None else 0)
        who = int(person["id"]) if person is not None else None
        active = who is not None and (who in signed or who in did)
        if let_at and let_at <= old and not active:
            held.add("unused")
        if person is not None and who in signed and who not in did and int(person["made"]) <= old:
            held.add("idle")
        if held:
            found[email] = [key for key in FLAGS if key in held]

    db.execute("DROP TABLE IF EXISTS temp.bo_flags")
    db.execute("CREATE TEMP TABLE bo_flags (address TEXT PRIMARY KEY, score INTEGER NOT NULL)")
    db.executemany(
        "INSERT INTO temp.bo_flags (address, score) VALUES (?, ?)",
        [(email, len(keys)) for email, keys in found.items()],
    )
    return found


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

    # What might make each sign-up fake, worked out once for every address and kept in a
    # table of this connection's own, so the lists can filter and order by it.
    stamp = int(datetime.now(UTC).timestamp() * 1000) if today is None else until - 1
    reasons = _flag(db, stamp, mine)
    found.possibly_fake = sum(1 for each in reasons.values() if len(each) >= FAKE_AT)

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
    for who in found.accounts:
        who.flags = [FLAGS[key] for key in reasons.get(flag_key(who.email), [])]
    for row in found.waiting_list:
        row.flags = [FLAGS[key] for key in reasons.get(flag_key(row.email), [])]

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
            score = SCORE.format(column="waiting.email")
            if listing.fake:
                clause += f" AND {score} >= {FAKE_AT}"
            listing.matches = _one(db, f"SELECT COUNT(*) FROM waiting {clause}", args)  # noqa: S608
            listing.page = min(listing.page, listing.pages())
            # Oldest first is the order they would be let in.
            order = {
                "oldest": "asked, rowid",
                "newest": "asked DESC, rowid DESC",
                "flags": f"{score} DESC, asked, rowid",
            }.get(listing.sort, "asked, rowid")
            rows += db.execute(
                f"SELECT rowid AS row_, {score} AS score_, * FROM waiting {clause}"  # noqa: S608
                f" ORDER BY {order} LIMIT :per OFFSET :skip",
                {**args, "per": listing.per, "skip": listing.offset()},
            ).fetchall()
        if still.sort == "flags":
            rows.sort(key=lambda row: (-int(row["score_"]), int(row["asked"]), int(row["row_"])))
        else:
            rows.sort(
                key=lambda row: (int(row["asked"]), int(row["row_"])),
                reverse=still.sort == "newest",
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
                turned_off=bool(_page(row, "turned_off") not in ("", "0")),
            )
            for row in rows
        ]
    # How many joined through each page, so `/aliyah` can be told from the front door
    # (targum-internal#388). Unknown is counted too, under "". Most first, and between
    # two the same, the one that brought somebody first.
    with contextlib.suppress(sqlite3.Error):
        found.waiting_by_page = _top_tags(
            {
                str(row["page"] or ""): int(row["n"])
                for row in db.execute(
                    f"SELECT page, COUNT(*) AS n FROM waiting {mine}"  # noqa: S608
                    " GROUP BY page ORDER BY n DESC, MIN(asked), MIN(rowid)",
                    named,
                )
            }
        )
    # And by account (targum-internal#676): with the door open, a signup never has a
    # waitlist row, so the channel is counted here too. Absent before schema 63.
    with contextlib.suppress(sqlite3.Error):
        people = NOT_MINE.format(column="p.email")
        found.accounts_by_came_from = _top_tags(
            {
                str(row["came_from"] or ""): int(row["n"])
                for row in db.execute(
                    f"SELECT came_from, COUNT(*) AS n FROM person p WHERE {people}"  # noqa: S608
                    " GROUP BY came_from ORDER BY n DESC, MIN(made), MIN(id)",
                    named,
                )
            }
        )


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
    score = SCORE.format(column="p.email")
    if listing.fake:
        clause += f" AND {score} >= {FAKE_AT}"
    listing.matches = _one(db, f"SELECT COUNT(*) FROM person p WHERE {clause}", args)  # noqa: S608
    listing.page = min(listing.page, listing.pages())
    order = ACCOUNT_ORDERS.get(listing.sort, ACCOUNT_ORDERS["joined"]).replace("{score}", score)
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
#:
#: A `day` row is the reader's own local date and a text opened or a word kept is a UTC
#: stamp, so the two are never compared with each other: an evening in New York that
#: crosses Greenwich's midnight would read as two days. `back` counts days within one
#: clock at a time, and `first`, which a second text is later than, is taken from the UTC
#: stamps alone, the same clock as the opening it is compared with (qa on targum#964).
READERS = """
WITH staff(e) AS (SELECT value FROM json_each(:staff)),
inv(e, at) AS ({invited}),
r AS (
  SELECT p.id, p.email, p.made, p.leaving, inv.at AS let_in,
         date(COALESCE(NULLIF(inv.at, 0), p.made) / 1000, 'unixepoch') AS start
  FROM person p LEFT JOIN inv ON inv.e = lower(p.email)
  WHERE bare(p.email) NOT IN (SELECT e FROM staff)
),
acts(person, d, utc) AS (
  SELECT person, day, 0 FROM day WHERE gone = 0
  UNION SELECT person, date(opened / 1000, 'unixepoch'), 1 FROM doc WHERE opened > 0
  UNION SELECT person, date(at / 1000, 'unixepoch'), 1 FROM word WHERE at > 0
),
a AS (
  SELECT r.id AS person, COUNT(DISTINCT acts.d) AS n,
    max(COUNT(DISTINCT CASE WHEN acts.utc = 0 THEN acts.d END),
        COUNT(DISTINCT CASE WHEN acts.utc = 1 THEN acts.d END)) AS back,
    MIN(CASE WHEN acts.utc = 1 THEN acts.d END) AS first, MAX(acts.d) AS last,
    MAX(acts.d BETWEEN date(r.start, '+{one_from} days') AND date(r.start, '+{one_to} days'))
      AS w1,
    MAX(acts.d BETWEEN date(r.start, '+{two_from} days') AND date(r.start, '+{two_to} days'))
      AS w2,
    MAX(acts.d BETWEEN date(r.start, '+{four_from} days') AND date(r.start, '+{four_to} days'))
      AS w4
  FROM r JOIN acts ON acts.person = r.id GROUP BY r.id
)
SELECT r.id, r.email, r.made, r.leaving, r.let_in, r.start,
  IFNULL(a.n, 0) AS days, IFNULL(a.back, 0) AS back,
  IFNULL(a.first, '') AS first, IFNULL(a.last, '') AS last,
  IFNULL(a.w1, 0) AS w1, IFNULL(a.w2, 0) AS w2, IFNULL(a.w4, 0) AS w4,
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


def _since(batches: list[Batch], monday: str) -> Batch | None:
    """The weeks from `monday` on as one batch, every count added up, or None if no week
    from then has anybody in it."""
    weeks = [each for each in batches if each.week >= monday]
    if not weeks:
        return None
    total = Batch(monday)
    for count in fields(Batch):
        if count.name != "week":
            setattr(total, count.name, sum(getattr(each, count.name) for each in weeks))
    return total


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
            two_from=WEEK_TWO[0],
            two_to=WEEK_TWO[1],
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
    found.follow_up_due = {each.email.strip().lower() for each in follow}

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
            batch.came_back += int(row["back"]) >= 2
            last_opened = _day(int(row["last_opened"])) if row["last_opened"] else ""
            batch.second_text += texts >= 2 and last_opened > str(row["first"])
        # A week counts for those who have had the whole of it.
        if (now - when).days > WEEK_ONE[1] and who in signed_in:
            batch.week_one_over += 1
            batch.week_one += bool(row["w1"])
        if (now - when).days > WEEK_TWO[1] and who in signed_in:
            batch.week_two_over += 1
            batch.week_two += bool(row["w2"])
        if (now - when).days > WEEK_FOUR[1] and who in signed_in:
            batch.week_four_over += 1
            batch.week_four += bool(row["w4"])
    found.batches = sorted(weeks.values(), key=lambda each: each.week, reverse=True)
    found.beta = _since(found.batches, BETA_FROM.isoformat())

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
        ("Read on a second day", sum(1 for row in readers if int(row["back"]) >= 2)),
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


# -- the overview (design.md §12, 2026-11-17) ------------------------------------------

#: How many days of activity the overview draws as bars, and how many weeks of new
#: accounts.
OVERVIEW_DAYS = 30
OVERVIEW_WEEKS = 12
#: What share of a reader's day of spend puts them on the overview: $7 of the $10 rail.
NEAR_THE_RAIL = 0.7


@dataclass
class Figure:
    """A figure now, the same figure a day earlier and the same a week earlier. A window
    (seven days, thirty, the last twenty-four hours) is compared with the window of the
    same length ending a day earlier and a week earlier."""

    now: float = 0.0
    yesterday: float = 0.0
    last_week: float = 0.0

    def against_yesterday(self) -> float:
        return self.now - self.yesterday

    def against_last_week(self) -> float:
        return self.now - self.last_week


@dataclass
class Overview:
    """The overview's figures, read off the store and nothing else. Readers only: the
    operator's, admin and test addresses are counted nowhere, save in the box's spend,
    which is money and is counted as `Store.claim` counts it, whoever spent it."""

    #: Today in UTC, and the weekday a week ago, for "vs last Tue".
    today: str = ""
    weekday: str = ""
    #: Readers active today, in the last seven days and in the last thirty.
    active_today: Figure = field(default_factory=Figure)
    active_week: Figure = field(default_factory=Figure)
    active_month: Figure = field(default_factory=Figure)
    #: Readers active on each of the last thirty days, oldest first.
    active_days: list[tuple[str, int]] = field(default_factory=list)
    #: Accounts made today and in the last seven days, and in each of the last twelve
    #: weeks, oldest first, by the week's Monday.
    new_today: Figure = field(default_factory=Figure)
    new_week: Figure = field(default_factory=Figure)
    new_weeks: list[tuple[str, int]] = field(default_factory=list)
    #: The box's spend in the last twenty-four hours, as `claim` holds it to `ceiling`.
    spent_today: Figure = field(default_factory=Figure)
    ceiling: float = 0.0
    #: This month's model spend, and each day's, from the first.
    spent_month: float = 0.0
    month_days: list[tuple[str, float]] = field(default_factory=list)
    #: Readers' credits this month by kind, in seconds, in `KINDS` order.
    credits_by_kind: list[tuple[str, float]] = field(default_factory=list)
    #: Readers past `NEAR_THE_RAIL` of their own day's `rail`: id, address, $ in 24 h.
    near_rail: list[tuple[int, str, float]] = field(default_factory=list)
    rail: float = 0.0


#: Each reader and each day they did anything, over a span of days: a `day` row, or a
#: text opened or updated, or a word saved, that day. A `day` row is the reader's own
#: date and the rest UTC, the rule the readers' strip has always used.
ACTIVE_PAIRS = """
WITH staff(e) AS (SELECT value FROM json_each(:staff)),
acts(person, d) AS (
  SELECT person, day FROM day WHERE gone = 0 AND day BETWEEN :first AND :last
  UNION SELECT person, date(opened / 1000, 'unixepoch') FROM doc
    WHERE gone = 0 AND opened >= :since AND opened < :until
  UNION SELECT person, date(updated / 1000, 'unixepoch') FROM doc
    WHERE gone = 0 AND updated >= :since AND updated < :until
  UNION SELECT person, date(at / 1000, 'unixepoch') FROM word
    WHERE gone = 0 AND at >= :since AND at < :until
)
SELECT acts.person, acts.d FROM acts JOIN person p ON p.id = acts.person
WHERE bare(p.email) NOT IN (SELECT e FROM staff)
"""


def box_spent(db: sqlite3.Connection, since: int, until: int | None = None) -> float:
    """The box's spend from `since`: the sum `Store.claim` holds to the box's ceiling,
    read and never written. `until` closes the window, for the same sum a day or a week
    before; `claim` itself has none."""
    sql = "SELECT COALESCE(SUM(claimed), 0) FROM job WHERE claimed > 0 AND made >= ?"
    args: tuple[int, ...] = (since,)
    if until is not None:
        sql += " AND made < ?"
        args = (since, until)
    return float(db.execute(sql, args).fetchone()[0] or 0)


def _midnight(day: date) -> int:
    return int(datetime.combine(day, datetime.min.time(), UTC).timestamp() * 1000)


def overview(
    db: sqlite3.Connection,
    at: int,
    operators: Iterable[str] = (),
    ceiling: float = 0.0,
    rail: float = 0.0,
    hours: int = 24,
) -> Overview:
    """The overview's figures at `at` (milliseconds): who is active, who is new, and what
    the box has spent, each against a day earlier and a week earlier. Days are UTC.

    Everything is summed in the store over a bounded span, one row per reader and day at
    most, so the cost grows with how many readers are active and never with how much any
    of them has ever done: the 5,000-account test pins it."""
    _functions(db)
    today = datetime.fromtimestamp(at / 1000, UTC).date()
    staff = json.dumps(sorted(_staff(db, frozenset(bare(each) for each in operators))))
    found = Overview(
        today=today.isoformat(),
        weekday=(today - timedelta(days=7)).strftime("%a"),
        ceiling=ceiling,
        rail=rail,
    )

    # Active: a set of readers a day, over the thirty days and the thirty-seven back to
    # the start of the month-long window that ended a week ago.
    span = OVERVIEW_DAYS + 7
    first = today - timedelta(days=span - 1)
    by_day: dict[str, set[int]] = {
        (first + timedelta(days=n)).isoformat(): set() for n in range(span)
    }
    for row in db.execute(
        ACTIVE_PAIRS,
        {
            "staff": staff,
            "first": first.isoformat(),
            "last": today.isoformat(),
            "since": _midnight(first),
            "until": _midnight(today + timedelta(days=1)),
        },
    ):
        if row["d"] in by_day:
            by_day[str(row["d"])].add(int(row["person"]))

    def active(end: date, days: int) -> int:
        seen: set[int] = set()
        for n in range(days):
            seen |= by_day.get((end - timedelta(days=n)).isoformat(), set())
        return len(seen)

    def compared(count: Callable[[date, int], int], days: int) -> Figure:
        """A window of `days` ending today, against the same ending a day and a week ago."""
        return Figure(
            count(today, days),
            count(today - timedelta(days=1), days),
            count(today - timedelta(days=7), days),
        )

    found.active_today = compared(active, 1)
    found.active_week = compared(active, 7)
    found.active_month = compared(active, OVERVIEW_DAYS)
    found.active_days = [
        (day, len(by_day[day]))
        for day in ((today - timedelta(days=n)).isoformat() for n in reversed(range(OVERVIEW_DAYS)))
    ]

    # New accounts, by the UTC day they were made, back to the first of twelve Mondays.
    monday = today - timedelta(days=today.weekday())
    weeks_from = monday - timedelta(weeks=OVERVIEW_WEEKS - 1)
    made: Counter[str] = Counter()
    for row in db.execute(
        "WITH staff(e) AS (SELECT value FROM json_each(:staff))"
        " SELECT date(made / 1000, 'unixepoch') AS d, COUNT(*) AS n FROM person"
        " WHERE made >= :since AND bare(email) NOT IN (SELECT e FROM staff) GROUP BY d",
        {"staff": staff, "since": _midnight(min(weeks_from, today - timedelta(days=13)))},
    ):
        made[str(row["d"])] = int(row["n"])

    def new(end: date, days: int) -> int:
        return sum(made[(end - timedelta(days=n)).isoformat()] for n in range(days))

    found.new_today = compared(new, 1)
    found.new_week = compared(new, 7)
    found.new_weeks = [
        (
            (weeks_from + timedelta(weeks=n)).isoformat(),
            new(weeks_from + timedelta(weeks=n, days=6), 7),
        )
        for n in range(OVERVIEW_WEEKS)
    ]

    # Spend: the box's rolling day as `claim` sums it, then the same day's length ending
    # a day and a week before.
    window = hours * 60 * 60 * 1000
    found.spent_today = Figure(
        box_spent(db, at - window),
        box_spent(db, at - 2 * window, at - window),
        box_spent(db, at - window - 7 * DAY_MS, at - 7 * DAY_MS),
    )
    month = month_from(today)
    spent: dict[str, float] = {}
    for row in db.execute(
        "SELECT date(made / 1000, 'unixepoch') AS d, SUM(spent) AS s FROM job"
        " WHERE made >= ? GROUP BY d",
        (month,),
    ):
        spent[str(row["d"])] = float(row["s"] or 0)
    first_of = date(today.year, today.month, 1)
    found.month_days = [
        (
            (first_of + timedelta(days=n)).isoformat(),
            spent.get((first_of + timedelta(days=n)).isoformat(), 0.0),
        )
        for n in range((today - first_of).days + 1)
    ]
    found.spent_month = sum(value for _, value in found.month_days)

    # Readers' credits this month by kind, as a reader's page counts them.
    kinds: dict[str, float] = {}
    with contextlib.suppress(sqlite3.Error):
        for row in db.execute(
            "WITH staff(e) AS (SELECT value FROM json_each(:staff))"  # noqa: S608 - constants
            f" SELECT {JOB_KIND} AS k, SUM({JOB_SECONDS}) AS s FROM job j"
            " JOIN person p ON p.id = j.owner"
            f" WHERE j.made >= :month AND {JOB_SECONDS} > 0"
            " AND bare(p.email) NOT IN (SELECT e FROM staff) GROUP BY k",
            {"staff": staff, "month": month},
        ):
            kinds[str(row["k"])] = float(row["s"] or 0)
    found.credits_by_kind = [(kind, kinds.get(kind, 0.0)) for kind in KINDS] + [
        (kind, seconds) for kind, seconds in sorted(kinds.items()) if kind not in KINDS
    ]

    # Readers near their own day's rail, as `claim` sums it for them.
    if rail:
        found.near_rail = [
            (int(row["owner"]), str(row["email"]), float(row["s"]))
            for row in db.execute(
                "WITH staff(e) AS (SELECT value FROM json_each(:staff))"
                " SELECT j.owner, p.email, SUM(j.claimed) AS s FROM job j"
                " JOIN person p ON p.id = j.owner"
                " WHERE j.claimed > 0 AND j.made >= :since"
                " AND bare(p.email) NOT IN (SELECT e FROM staff)"
                " GROUP BY j.owner HAVING s >= :near ORDER BY s DESC, j.owner",
                {"staff": staff, "since": at - window, "near": rail * NEAR_THE_RAIL},
            )
        ]
    return found


def overview_store(
    store: Path,
    at: int | None = None,
    operators: Iterable[str] | None = None,
    ceiling: float = 0.0,
    rail: float = 0.0,
    hours: int = 24,
) -> Overview:
    """`overview`, opening the database read-only, as `survey_store` does."""
    db = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        return overview(
            db,
            at if at is not None else int(datetime.now(UTC).timestamp() * 1000),
            operators=operators_from_env() if operators is None else operators,
            ceiling=ceiling,
            rail=rail,
            hours=hours,
        )
    finally:
        db.close()


# -- how well targum estimates difficulty (targum-internal#612, clause 3.7) ------------

#: No count drawn from fewer readers than this is used, and the page shows none of its
#: figures (privacy notice clause 3.7 as amended 2026-11-01).
FIT_FLOOR = 10

#: The bands a finished section is counted in, by the share of its running words the
#: reader was estimated to know when they opened it: `choose`'s floor, aim and ceiling
#: cut it, with two bands under the floor.
FIT_BANDS: tuple[tuple[float, float, str], ...] = (
    (0.0, 0.80, "under 80%"),
    (0.80, 0.90, "80–90%"),
    (0.90, 0.94, "90–94%"),
    (0.94, 0.97, "94–97%"),
    (0.97, 0.995, "97–99.5%"),
    (0.995, 1.01, "99.5% and over"),
)


@dataclass
class Fit:
    """One band of finished sections, pooled across readers and naming none."""

    band: str
    readers: int
    words: int = 0
    looked: int = 0
    #: The words the estimate said the readers did not know, summed over the sections.
    expected: float = 0.0

    @property
    def shown(self) -> bool:
        """Whether this band is drawn from enough readers to be used at all."""
        return self.readers >= FIT_FLOOR

    @property
    def looked_per_100(self) -> float:
        return 100.0 * self.looked / self.words if self.words else 0.0

    @property
    def unknown_per_100(self) -> float:
        """The predicted unknown rate: words per hundred the estimate said were new."""
        return 100.0 * self.expected / self.words if self.words else 0.0


def fit_counts(
    db: sqlite3.Connection,
    documents: Iterable[str],
    operators: Iterable[str] = (),
) -> list[Fit]:
    """Words looked up per hundred read in finished sections, against the share of those
    sections' running words the reader was estimated to know, by band (targum-internal
    #612; privacy notice clause 3.7 as amended 2026-11-01).

    Across every reader and naming nobody: it returns counts and a tally of readers per
    band, never a person, a day or a text. Confined to `documents`, the shared library's
    texts whose licence lets them be redistributed, which leaves out by construction
    everything a reader uploaded. Staff accounts are not readers here. A band drawn from
    fewer than `FIT_FLOOR` readers comes back with its tally alone (`Fit.shown` false),
    and the page draws none of its figures.
    """
    docs = sorted({str(one) for one in documents if one})
    if not docs:
        return []
    _functions(db)
    staff = _staff(db, frozenset(bare(one) for one in operators))
    cases = " ".join(
        f"WHEN coverage < {high} THEN {at}" for at, (_, high, _) in enumerate(FIT_BANDS)
    )
    sql = (
        f"SELECT CASE {cases} ELSE {len(FIT_BANDS) - 1} END AS band,"  # noqa: S608
        " COUNT(DISTINCT person) AS readers, SUM(amount) AS words, SUM(looked) AS looked,"
        " SUM((1 - coverage) * amount) AS expected"
        " FROM event WHERE kind = 'section' AND coverage IS NOT NULL"
        " AND looked IS NOT NULL AND amount > 0"
        " AND document IN (SELECT value FROM json_each(:docs))"
        " AND person IN (SELECT id FROM person WHERE bare(email) NOT IN"
        " (SELECT value FROM json_each(:staff)))"
        " GROUP BY band ORDER BY band"
    )
    try:
        rows = db.execute(
            sql, {"docs": json.dumps(docs), "staff": json.dumps(sorted(staff))}
        ).fetchall()
    except sqlite3.Error:
        return []
    found: list[Fit] = []
    for row in rows:
        label = FIT_BANDS[int(row[0])][2]
        readers = int(row[1] or 0)
        if readers < FIT_FLOOR:
            found.append(Fit(label, readers))
            continue
        found.append(
            Fit(
                label,
                readers,
                words=round(float(row[2] or 0)),
                looked=int(row[3] or 0),
                expected=float(row[4] or 0),
            )
        )
    return found


def fit_counts_store(
    store: Path, documents: Iterable[str], operators: Iterable[str] | None = None
) -> list[Fit]:
    """`fit_counts`, opening the database read-only."""
    db = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        return fit_counts(db, documents, operators_from_env() if operators is None else operators)
    finally:
        db.close()


# -- the Readers table (design's plan, 2026-11-17, §1 and PR 4) -------------------------

#: How the Readers table may be ordered, each in the direction an operator wants first.
#: The first is the default: the reader seen last is the one to look at.
READER_SORTS = {
    "seen": "Last seen",
    "joined": "Newest",
    "words": "Most words",
    "texts": "Most texts",
    "credits": "Most credits",
    "spend": "Most spend",
    "flags": "Most flags",
}
#: Who was active when: any time, in the last 7 or 30 days, or not in the last 30.
READER_ACTIVITY = {
    "": "Any time",
    "7": "Active in 7 days",
    "30": "Active in 30 days",
    "inactive": "Not active in 30 days",
}
#: Which plan a reader is on: Plan paid through Paddle, the beta's comp, or Free.
READER_PLANS = {"": "Any plan", "plan": "Plan", "beta": "Beta", "free": "Free"}
#: How many days the sparkline draws, oldest on the left.
SPARK_DAYS = 14


def languages_shown() -> bool:
    """Whether the published Privacy Notice lets the back office show the languages an
    account reads in: `render.builder.NOTICE_ALLOWS_LANGUAGES`, set beside
    `LEGAL_CHANGED` by the PR that lands the approved clauses 3.2 and 3.7 (qa on
    targum#1309: reading the Notice's template for the words could be tripped by a
    comment or a draft). Until it is True the column and its filter are not drawn."""
    from .render.builder import NOTICE_ALLOWS_LANGUAGES

    return bool(NOTICE_ALLOWS_LANGUAGES)


@dataclass
class ReaderFilter:
    """Which readers the table is narrowed to, read off the address."""

    language: str = ""
    active: str = ""
    follow: bool = False
    flagged: bool = False
    plan: str = ""

    @classmethod
    def read(cls, query: Mapping[str, Sequence[str]]) -> ReaderFilter:
        """Anything unknown is no filter: an address is typed by hand as often as clicked."""

        def first(name: str) -> str:
            return (query.get(name) or [""])[0].strip()

        language = first("lang").lower()
        return cls(
            language=language
            if language.isascii() and language.isalpha() and len(language) <= 8
            else "",
            active=first("active") if first("active") in READER_ACTIVITY else "",
            follow=first("follow") == "1",
            flagged=first("flagged") == "1",
            plan=first("plan") if first("plan") in READER_PLANS else "",
        )


@dataclass
class ReaderRow:
    """One reader in the table: counts and dates, never a word, a title or a source."""

    id: int
    email: str
    name: str
    #: "Plan", "Beta until March 4" or "Free".
    plan: str
    #: The last day anything of theirs moved or a session of theirs was seen.
    last_seen: str
    #: The last `SPARK_DAYS` days, oldest first: whether they were active on each.
    spark: list[bool]
    texts: int
    words: int
    learned: int
    #: This month's credits used in seconds, their allowance (None for none), and the
    #: model spend of their jobs this month in dollars.
    used: float
    allowance: float | None
    spent: float
    #: The languages they read in, where the Notice allows it; else empty.
    languages: list[str]
    flags: list[str]
    leaving: str = ""


@dataclass
class ReadersPage:
    """The Readers table's page: the rows, how they were asked for, and what the filters
    can offer."""

    rows: list[ReaderRow]
    listing: Listing
    filter: ReaderFilter
    #: Every reader, however many match.
    total: int
    languages_shown: bool
    #: The languages any reader reads in, for the filter; empty when not shown.
    languages: list[str]


#: The last time anything of an account moved, or a session of theirs was seen: each
#: table read once and grouped, then joined, never a subquery per person. `session` has
#: no index on its person, and a subquery a row made last seen some 25 million row reads
#: at five thousand accounts.
LAST_SEEN_FROM = (
    "WITH moved(person, at) AS ("
    " SELECT person, MAX(at) FROM word WHERE gone = 0 GROUP BY person"
    " UNION ALL SELECT person, MAX(at) FROM phrase WHERE gone = 0 GROUP BY person"
    " UNION ALL SELECT person, MAX(MAX(updated), MAX(opened)) FROM doc WHERE gone = 0"
    " GROUP BY person"
    " UNION ALL SELECT person, MAX(seen) FROM session GROUP BY person),"
    " last(person, at) AS (SELECT person, MAX(at) FROM moved GROUP BY person) "
)
LAST_SEEN = "IFNULL(l.at, 0)"

#: This month's credits and spend, the sums `_credits` reads, for ordering the whole list.
MONTH_LENGTH = (
    "(SELECT IFNULL(SUM(CASE WHEN length > 0 THEN length ELSE 0 END), 0) FROM job j"
    " WHERE j.owner = p.id AND j.made >= :month)"
)
MONTH_SPENT = "(SELECT IFNULL(SUM(spent), 0) FROM job j WHERE j.owner = p.id AND j.made >= :month)"

READER_ORDERS = {
    "seen": f"{LAST_SEEN} DESC, p.id DESC",
    "joined": "p.made DESC, p.id DESC",
    "words": ACCOUNT_ORDERS["words"],
    "texts": ACCOUNT_ORDERS["texts"],
    "credits": f"{MONTH_LENGTH} DESC, p.id DESC",
    "spend": f"{MONTH_SPENT} DESC, p.id DESC",
    "flags": "{score} DESC, p.made DESC, p.id DESC",
}


def _columns(db: sqlite3.Connection, table: str) -> set[str]:
    with contextlib.suppress(sqlite3.Error):
        return {str(row[1]) for row in db.execute(f"PRAGMA table_info({table})")}  # noqa: S608
    return set()


def _plan_kind(db: sqlite3.Connection) -> str:
    """SQL naming each reader's plan, `plan`, `beta` or `free`, as far as this store can
    say: a Paddle plan that holds (active, trialing, or a failed renewal inside its
    grace), else a comp whose day has not come, else Free."""
    from .plans import GRACE_DAYS

    paid = "0"
    if _has_table(db, "plan"):
        paid = (
            "EXISTS (SELECT 1 FROM plan pl WHERE pl.person = p.id AND (pl.status IN"
            " ('active', 'trialing') OR (pl.status = 'past_due'"
            f" AND pl.past_due_since > :now_ms - {GRACE_DAYS} * {DAY_MS})))"
        )
    comped = "p.plan_until > :today" if "plan_until" in _columns(db, "person") else "0"
    return f"(CASE WHEN {paid} THEN 'plan' WHEN {comped} THEN 'beta' ELSE 'free' END)"


def readers(
    db: sqlite3.Connection,
    listing: Listing,
    wanted: ReaderFilter,
    now: datetime | None = None,
    operators: Iterable[str] = (),
    allowance: float | None = None,
    plan_allowance: float | None = None,
    languages_on: bool | None = None,
) -> ReadersPage:
    """The Readers table (design's plan, 2026-11-17, §1): every account but staff
    (`_staff`: the operators, the admins and the test accounts), searched, filtered,
    ordered and paged in the store, and each row on the page with its plan, last seen, a
    sparkline of `SPARK_DAYS`, texts, words, credits, spend, languages and flags.

    Per-row figures are read for the page's rows only; what orders or filters the whole
    list is asked of the store, never of rows pulled out of it. Nothing read here is a
    word, a title, a source or a note (clause 3.2): counts, dates and language codes."""
    _functions(db)
    moment = now or datetime.now(UTC)
    today = moment.date()
    now_ms = int(moment.timestamp() * 1000)
    staff = _staff(db, frozenset(bare(each) for each in operators))
    shown = languages_shown() if languages_on is None else languages_on
    named: dict[str, object] = {
        "staff": json.dumps(sorted(staff)),
        "month": month_from(today),
        "today": today.isoformat(),
        "now_ms": now_ms,
    }
    clause = "bare(p.email) NOT IN (SELECT value FROM json_each(:staff))"
    total = _one(db, f"SELECT COUNT(*) FROM person p WHERE {clause}", named)  # noqa: S608
    args = dict(named)
    if listing.q:
        clause += (
            " AND (fold(p.email) LIKE :like ESCAPE '\\' OR fold(p.name) LIKE :like ESCAPE '\\')"
        )
        args["like"] = _like(listing.q)
    reasons = _flag(db, now_ms, frozenset(staff))
    score = SCORE.format(column="p.email")
    if wanted.flagged:
        clause += f" AND {score} >= {FAKE_AT}"
    if wanted.active:
        days = 30 if wanted.active == "inactive" else int(wanted.active)
        cut = (today - timedelta(days=days - 1)).isoformat()
        args["cut_day"] = cut
        args["cut_ms"] = int(
            datetime.combine(date.fromisoformat(cut), datetime.min.time(), UTC).timestamp() * 1000
        )
        recent = (
            "p.id IN (SELECT person FROM day WHERE gone = 0 AND day >= :cut_day"
            " UNION SELECT person FROM doc WHERE gone = 0"
            " AND (opened >= :cut_ms OR updated >= :cut_ms)"
            " UNION SELECT person FROM word WHERE gone = 0 AND at >= :cut_ms)"
        )
        clause += f" AND {'NOT ' if wanted.active == 'inactive' else ''}{recent}"
    if wanted.plan:
        clause += f" AND {_plan_kind(db)} = :plan"
        args["plan"] = wanted.plan
    if wanted.language and shown:
        clause += (
            " AND p.id IN (SELECT person FROM doc WHERE gone = 0 AND language = :lang"
            " UNION SELECT person FROM word WHERE gone = 0 AND language = :lang)"
        )
        args["lang"] = wanted.language
    if wanted.follow:
        scratch = Survey()
        _growth(db, scratch, today, frozenset(bare(each) for each in operators))
        args["due"] = json.dumps(sorted(scratch.follow_up_due))
        clause += " AND lower(trim(p.email)) IN (SELECT value FROM json_each(:due))"
    listing.matches = _one(db, f"SELECT COUNT(*) FROM person p WHERE {clause}", args)  # noqa: S608
    listing.page = min(listing.page, listing.pages())
    order = READER_ORDERS.get(listing.sort, READER_ORDERS["seen"]).replace("{score}", score)
    people = db.execute(
        f"{LAST_SEEN_FROM}"  # noqa: S608 - every part is ours
        f"SELECT p.id, p.email, p.name, p.made, p.leaving, {_plan_kind(db)} AS kind,"
        f" {LAST_SEEN} AS seen"
        " FROM person p LEFT JOIN last l ON l.person = p.id"
        f" WHERE {clause} ORDER BY {order} LIMIT :per OFFSET :skip",
        {**args, "per": listing.per, "skip": listing.offset()},
    ).fetchall()
    rows = _reader_rows(db, people, named, today, allowance, plan_allowance, shown, reasons)
    languages: list[str] = []
    if shown:
        # From readers' rows only: a language only staff read in is no reader's.
        languages = sorted(
            {
                str(row[0])
                for row in db.execute(
                    "SELECT language FROM ("
                    " SELECT person, language FROM doc WHERE gone = 0 AND language != ''"
                    " UNION SELECT person, language FROM word WHERE gone = 0 AND language != '')"
                    " JOIN person p ON p.id = person"
                    " WHERE bare(p.email) NOT IN (SELECT value FROM json_each(:staff))"
                    " GROUP BY language",
                    named,
                )
            }
        )
    return ReadersPage(
        rows=rows,
        listing=listing,
        filter=wanted,
        total=total,
        languages_shown=shown,
        languages=languages,
    )


def _reader_rows(
    db: sqlite3.Connection,
    people: Sequence[sqlite3.Row],
    named: Mapping[str, object],
    today: date,
    allowance: float | None,
    plan_allowance: float | None,
    shown: bool,
    reasons: Mapping[str, list[str]],
) -> list[ReaderRow]:
    """The figures for the page's rows, asked of the store for those ids only."""
    if not people:
        return []
    among = ",".join(str(int(row["id"])) for row in people)
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
                "SELECT person, COUNT(*) n FROM word WHERE gone = 0 AND learned = 1"
                " AND person IN ({among}) GROUP BY person",
            ),
            (
                "texts",
                "SELECT person, COUNT(*) n FROM doc"
                " WHERE gone = 0 AND person IN ({among}) GROUP BY person",
            ),
        )
    }
    month: dict[int, tuple[float, float]] = {}
    with contextlib.suppress(sqlite3.Error):
        for row in db.execute(
            "SELECT owner, SUM(CASE WHEN length > 0 THEN length ELSE 0 END) AS used,"  # noqa: S608 - ids are ints
            f" SUM(spent) AS spent FROM job WHERE made >= :month AND owner IN ({among})"
            " GROUP BY owner",
            named,
        ):
            month[int(row["owner"])] = (float(row["used"] or 0), float(row["spent"] or 0))
    # The sparkline: which of the last SPARK_DAYS days each was active on, by the same
    # rule as the overview's (a day row, a text opened or updated, a word saved).
    first = today - timedelta(days=SPARK_DAYS - 1)
    since = int(datetime.combine(first, datetime.min.time(), UTC).timestamp() * 1000)
    active: dict[int, set[str]] = {}
    for row in db.execute(
        "SELECT person, day AS d FROM day"  # noqa: S608 - ids are ints
        f" WHERE gone = 0 AND day >= :first AND person IN ({among})"
        " UNION SELECT person, date(opened / 1000, 'unixepoch') FROM doc"
        f" WHERE gone = 0 AND opened >= :since AND person IN ({among})"
        " UNION SELECT person, date(updated / 1000, 'unixepoch') FROM doc"
        f" WHERE gone = 0 AND updated >= :since AND person IN ({among})"
        " UNION SELECT person, date(at / 1000, 'unixepoch') FROM word"
        f" WHERE gone = 0 AND at >= :since AND person IN ({among})",
        {"first": first.isoformat(), "since": since},
    ):
        active.setdefault(int(row["person"]), set()).add(str(row["d"]))
    window = [(first + timedelta(days=n)).isoformat() for n in range(SPARK_DAYS)]
    spoken: dict[int, set[str]] = {}
    if shown:
        for row in db.execute(
            "SELECT person, language FROM doc"  # noqa: S608 - ids are ints
            f" WHERE gone = 0 AND language != '' AND person IN ({among})"
            " UNION SELECT person, language FROM word"
            f" WHERE gone = 0 AND language != '' AND person IN ({among})"
        ):
            spoken.setdefault(int(row["person"]), set()).add(str(row["language"]))
    comps: dict[int, str] = {}
    if "plan_until" in _columns(db, "person"):
        comps = {
            int(row["id"]): str(row["plan_until"] or "")
            for row in _rows(db, f"SELECT id, plan_until FROM person WHERE id IN ({among})")  # noqa: S608 - ids are ints
        }
    out: list[ReaderRow] = []
    for row in people:
        who = int(row["id"])
        kind = str(row["kind"])
        used, spent = month.get(who, (0.0, 0.0))
        label = {"plan": "Plan", "free": "Free"}.get(kind, "")
        if kind == "beta":
            label = f"Beta until {_said(comps.get(who, ''))}" if comps.get(who) else "Beta"
        out.append(
            ReaderRow(
                id=who,
                email=str(row["email"]),
                name=str(row["name"] or ""),
                plan=label,
                last_seen=_day(int(row["seen"])) if int(row["seen"] or 0) else "",
                spark=[day in active.get(who, set()) for day in window],
                texts=counted["texts"].get(who, 0),
                words=counted["words"].get(who, 0),
                learned=counted["learned"].get(who, 0),
                used=used,
                allowance=plan_allowance if kind in ("plan", "beta") else allowance,
                spent=spent,
                languages=sorted(spoken.get(who, set())),
                flags=[FLAGS[key] for key in reasons.get(flag_key(str(row["email"])), [])],
                leaving=_day(int(row["leaving"])) if row["leaving"] else "",
            )
        )
    return out


def readers_store(
    store: Path,
    listing: Listing,
    wanted: ReaderFilter,
    operators: Iterable[str] | None = None,
    allowance: float | None = None,
    plan_allowance: float | None = None,
) -> ReadersPage:
    """`readers`, opening the database read-only."""
    db = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        return readers(
            db,
            listing,
            wanted,
            operators=operators_from_env() if operators is None else operators,
            allowance=allowance,
            plan_allowance=plan_allowance,
        )
    finally:
        db.close()
