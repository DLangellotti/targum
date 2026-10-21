"""Sunday's triage, as one page to read (targum-internal#459).

The beta's rhythm is a release on Tuesday and a triage on Sunday: every message a reader
sent through Tell us and every way a page broke in a browser becomes a `beta-found` card
or gets an answer saying why not. This draws the week's open messages and the faults
counted in it, each with a draft card for the operator to finish and file.

A draft names a message by its number, page and build, never by what the reader wrote or
who they are: the words and the address stay in our database (clause 3.14), and the card
goes to a tracker the privacy notice does not list as a recipient. The operator reads the
message here and writes the card in their own words. A fault's message is our script's,
not the reader's, and travels.

Read-only: the database is opened as a file nobody can write through, so a triage run on
the box cannot change what the site is serving.
"""

from __future__ import annotations

import contextlib
import shlex
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

#: The tracker the drafts are filed in.
TRACKER = "DLangellotti/targum-internal"
#: A week, the span between two triages.
WEEK_DAYS = 7


def _day(stamp_ms: int) -> str:
    return datetime.fromtimestamp(stamp_ms / 1000, UTC).date().isoformat()


def _rows(db: sqlite3.Connection, sql: str, params: tuple[object, ...]) -> list[sqlite3.Row]:
    """The rows a query returns, or none where the store predates its table."""
    with contextlib.suppress(sqlite3.Error):
        return list(db.execute(sql, params).fetchall())
    return []


def _draft(title: str, body: str) -> str:
    return (
        f"gh issue create -R {TRACKER} --label beta-found"
        f" --title {shlex.quote(title)} --body {shlex.quote(body)}"
    )


def report(store: Path, *, days: int = WEEK_DAYS, now_ms: int | None = None) -> str:
    """The week's triage as Markdown: open messages first, then faults by count."""
    db = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        now_ms = now_ms if now_ms is not None else int(datetime.now(UTC).timestamp() * 1000)
        since = now_ms - days * 24 * 60 * 60 * 1000
        told = _rows(
            db,
            "SELECT t.id, t.at, t.said, t.page, t.build, t.viewport, t.language, p.email"
            " FROM told t LEFT JOIN person p ON p.id = t.person"
            " WHERE t.state = 'open' ORDER BY t.at",
            (),
        )
        faults = _rows(
            db,
            "SELECT message, page, COUNT(*) AS count, COUNT(DISTINCT person) AS people,"
            " MAX(at) AS last, MAX(place) AS place, MAX(build) AS build"
            " FROM fault WHERE at >= ?"
            # Only what came after a fix: one marked fixed in the back office is settled.
            " AND at > COALESCE("
            "(SELECT x.at FROM fault_fixed x WHERE x.message = fault.message), 0)"
            " GROUP BY message, page ORDER BY count DESC, last DESC",
            (since,),
        )
    finally:
        db.close()

    lines = [f"# Triage, the {days} days to {_day(now_ms)}", ""]
    lines += [f"## Tell us: {len(told)} open", ""]
    if not told:
        lines += ["Nothing waiting.", ""]
    for row in told:
        where = row["page"] or "an unknown page"
        facts = ", ".join(
            each
            for each in (
                _day(int(row["at"])),
                where,
                f"build {row['build']}" if row["build"] else "",
                row["viewport"],
                row["language"],
            )
            if each
        )
        lines += [f"### Tell us #{row['id']}: {facts}", ""]
        lines += ["> " + line for line in str(row["said"]).splitlines() or [""]]
        lines += ["", f"From {row['email'] or 'an account since deleted'}.", ""]
        body = (
            f"From Tell us #{row['id']} ({facts})."
            " What is wrong, in our words: . Priority, P0 to P2: "
        )
        lines += ["```", _draft("Write what the reader met", body), "```", ""]
        lines += [
            "Or answer them and settle it as asked or won't in the back office.",
            "",
        ]

    lines += [f"## Broken in browsers: {len(faults)} messages", ""]
    if not faults:
        lines += ["Nothing reported.", ""]
    for row in faults:
        place = f" at {row['place']}" if row["place"] else ""
        build = f", build {row['build']}" if row["build"] else ""
        said = (
            f"{row['count']} reports from {row['people']} reader(s), last {_day(int(row['last']))}"
        )
        lines += [f"### {row['message']}", "", f"On {row['page']}{place}{build}. {said}.", ""]
        body = (
            f"A browser reported `{row['message']}` on {row['page']}{place}{build}: {said}."
            " Priority, P0 to P2: "
        )
        lines += ["```", _draft(f"Broken in browsers: {row['message'][:60]}", body), "```", ""]
    return "\n".join(lines).rstrip() + "\n"
