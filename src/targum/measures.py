"""The six beta measures, read off the store and nothing else.

A beta is a set of questions, and the questions here were written down before there
were readers to ask them of (targum-internal#50): whether a reader comes back for a
second text, how far they got into the first, whether the two shelves share readers,
how often the audio is played, who the readers are, and how much they read a month.
Every answer here is counted from what the store already holds — `doc`, `day`,
`person` — and no model is asked for anything.

Some of the six cannot be answered from what the store holds, and the honest thing is
to say so in the same place the answers are printed rather than to print a number
that stands for something else. A play is never sent to the server. The place in a text
is kept in the browser and never synced. A session carries no device. Each of those is
said in words where its number would have gone, with what would have to be recorded
first; the recording itself is a privacy decision (targum-internal#127) and not one
a report should make by accident.

Everything is counted per person and reported without names. The weekly reading of
this is a table in a notebook, and a table that names readers is a table that cannot
be pasted anywhere.
"""

from __future__ import annotations

import json
import sqlite3
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DAY_MS = 24 * 60 * 60 * 1000

#: Which shelf a text is on, for the question of whether the two share readers. The
#: Tanakh is one register; everything else in Hebrew — rabbinic, medieval, revival,
#: modern — is "the modern shelf" in the sense the question was asked in: Hebrew a
#: reader of scripture would have to learn as a second thing.
BIBLICAL = "biblical"


def shelf(out: Path) -> dict[str, str]:
    """Which register each built text is in, by the identity the reader syncs under.

    `doc.hash` on the store is the document's `content_hash`, and the only place the
    hash meets a source is `document.json` beside the reader. Scanned rather than kept:
    the shelf is rebuilt whenever a text is, and a map written down would be one more
    copy to go stale.
    """
    from . import catalogue as catalogue_module
    from .models import is_biblical

    found: dict[str, str] = {}
    if not out.is_dir():
        return found
    for document in out.glob("*/*/document.json"):
        try:
            data = json.loads(document.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        content_hash = str(data.get("content_hash") or "")
        source = str(data.get("source") or "")
        if not content_hash or not source:
            continue
        entry = catalogue_module.matching(source)
        if entry is not None and entry.register.value:
            found[content_hash] = entry.register.value
        elif str(data.get("language") or "") == "he":
            found[content_hash] = BIBLICAL if is_biblical(source) else "modern"
        else:
            found[content_hash] = "other"
    return found


def _week(stamp_ms: int) -> str:
    """The week a moment falls in, written the way the weekly names its issues."""
    year, week, _ = datetime.fromtimestamp(stamp_ms / 1000, UTC).isocalendar()
    return f"{year}-w{week:02d}"


def _month(stamp_ms: int) -> str:
    return datetime.fromtimestamp(stamp_ms / 1000, UTC).strftime("%Y-%m")


def _day(stamp_ms: int) -> str:
    return datetime.fromtimestamp(stamp_ms / 1000, UTC).strftime("%Y-%m-%d")


@dataclass
class Measures:
    """The six answers, each a small table or a sentence saying why there is none."""

    readers: int = 0
    #: 1. By the week they joined: how many joined, how many have opened a second text.
    returned: list[tuple[str, int, int]] = field(default_factory=list)
    #: 2. Per reader, unnamed: the first text, when, and whether it was finished.
    first: list[tuple[str, str, bool]] = field(default_factory=list)
    #: 3. Readers by which shelves they have opened, and the crossing.
    shelves: dict[str, int] = field(default_factory=dict)
    biblical_readers: int = 0
    biblical_who_crossed: int = 0
    #: 5. Days since joining, per reader.
    ages: list[int] = field(default_factory=list)
    #: 6. Texts finished and days read, per reader per month.
    finished_by_month: dict[str, list[int]] = field(default_factory=dict)
    days_by_month: dict[str, list[int]] = field(default_factory=dict)

    #: 4 and half of 5 are not in the store. Said once, here, so the report and the
    #: code cannot disagree about what is missing.
    not_recorded: dict[str, str] = field(
        default_factory=lambda: {
            "plays per verse": (
                "no play reaches the store. Measuring it needs a play event keyed to "
                "the segment id, kept the way a day is (targum-internal#127)."
            ),
            "device": (
                "a session carries no device. Measuring it needs a coarse class — "
                "phone, tablet, desktop — written on the session, which is a decision "
                "about what is kept (targum-internal#127)."
            ),
            "how far into the first text": (
                "the place in a text is kept in the browser and never synced, so the "
                "store knows opened and finished and nothing between."
            ),
        }
    )


def measure(db: sqlite3.Connection, registers: dict[str, str], at: int) -> Measures:
    """Count the six off a store, against a shelf, as of a moment."""
    out = Measures()
    people = db.execute(
        "SELECT id, made FROM person WHERE leaving IS NULL ORDER BY made"
    ).fetchall()
    out.readers = len(people)

    docs: dict[int, list[sqlite3.Row]] = defaultdict(list)
    for row in db.execute(
        "SELECT person, hash, title, opened, done FROM doc WHERE gone = 0 AND opened > 0"
    ):
        docs[int(row["person"])].append(row)
    days: dict[int, list[str]] = defaultdict(list)
    for row in db.execute("SELECT person, day FROM day WHERE gone = 0"):
        days[int(row["person"])].append(str(row["day"]))

    joined: Counter[str] = Counter()
    second: Counter[str] = Counter()
    shelves: Counter[str] = Counter()
    for person in people:
        pid, made = int(person["id"]), int(person["made"])
        week = _week(made)
        joined[week] += 1
        opened = sorted(docs.get(pid, []), key=lambda row: int(row["opened"]))
        if len(opened) >= 2:
            second[week] += 1

        # 2. The first text is the one with the earliest open still on record. A text
        # opened again loses its first stamp, so this is the earliest a reader has not
        # come back to, which is the text the question is about.
        if opened:
            head = opened[0]
            out.first.append((_day(int(head["opened"])), str(head["title"]), bool(head["done"])))

        # 3. Which shelves, by the register of each text they have opened. A text the
        # shelf cannot place — an upload of their own, or a text since rebuilt — is a
        # register of its own rather than a guess.
        seen = {registers.get(str(row["hash"]), "unplaced") for row in opened}
        hebrew = {name for name in seen if name not in {"other", "unplaced"}}
        if hebrew:
            if hebrew == {BIBLICAL}:
                shelves["biblical only"] += 1
            elif BIBLICAL in hebrew:
                shelves["both"] += 1
            else:
                shelves["not biblical"] += 1
            if BIBLICAL in hebrew:
                out.biblical_readers += 1
                if hebrew - {BIBLICAL}:
                    out.biblical_who_crossed += 1

        # 5. Age, in days.
        out.ages.append(max(0, (at - made) // DAY_MS))

        # 6. Per month: texts finished, and days read. Chapters are not a record the
        # reader sends — a text is opened and a text is finished — so what is counted
        # is what was written down, and the heading says which.
        finished: Counter[str] = Counter()
        for row in opened:
            if int(row["done"]):
                finished[_month(int(row["done"]))] += 1
        read: Counter[str] = Counter()
        for day in days.get(pid, []):
            read[day[:7]] += 1
        for month, n in finished.items():
            out.finished_by_month.setdefault(month, []).append(n)
        for month, n in read.items():
            out.days_by_month.setdefault(month, []).append(n)

    out.returned = [(week, joined[week], second[week]) for week in sorted(joined)]
    out.shelves = dict(shelves)
    return out


def spread(values: list[int]) -> str:
    """A distribution in one line: least, median, most, and how many."""
    if not values:
        return "nobody"
    values = sorted(values)
    median = statistics.median(values)
    shown = f"{median:g}"
    return f"{values[0]}–{values[-1]}, median {shown}, over {len(values)}"


def report(found: Measures) -> str:
    """The six, as plain text, in the order they were asked."""
    lines: list[str] = []
    lines.append(f"readers: {found.readers}")

    lines.append("")
    lines.append("1. a second text, by the week they joined")
    if not found.returned:
        lines.append("   nobody")
    for week, n, back in found.returned:
        lines.append(f"   {week}  joined {n:3}  opened a second text {back:3}")

    lines.append("")
    lines.append("2. the first text")
    lines.append(f"   {found.not_recorded['how far into the first text']}")
    if not found.first:
        lines.append("   nobody has opened one")
    for when, title, done in sorted(found.first):
        lines.append(f"   {when}  {'finished' if done else 'open    '}  {title}")

    lines.append("")
    lines.append("3. the two shelves")
    for name in ("biblical only", "not biblical", "both"):
        lines.append(f"   {name:14} {found.shelves.get(name, 0):3}")
    lines.append(
        f"   of {found.biblical_readers} who opened the Tanakh, "
        f"{found.biblical_who_crossed} opened something else in Hebrew"
    )

    lines.append("")
    lines.append("4. plays per verse")
    lines.append(f"   not measured: {found.not_recorded['plays per verse']}")

    lines.append("")
    lines.append("5. age and device")
    lines.append(f"   days since joining: {spread(found.ages)}")
    lines.append(f"   device not measured: {found.not_recorded['device']}")

    lines.append("")
    lines.append("6. per reader per month")
    lines.append("   chapters are not a record the reader sends; a text is, opened and finished")
    months = sorted(set(found.finished_by_month) | set(found.days_by_month))
    if not months:
        lines.append("   nothing yet")
    for month in months:
        lines.append(
            f"   {month}  texts finished {spread(found.finished_by_month.get(month, []))}"
            f"  ·  days read {spread(found.days_by_month.get(month, []))}"
        )
    return "\n".join(lines) + "\n"


def measure_store(store: Path, out: Path, at: int | None = None) -> Measures:
    """The six off a store on disk, placed against the shelf beside it."""
    from .accounts import Store, now

    keeping = Store(store)
    try:
        return measure(keeping.db, shelf(out), at if at is not None else now())
    finally:
        keeping.close()


def as_state(found: Measures) -> dict[str, Any]:
    """The same answers as data, for a notebook that would rather draw them."""
    return {
        "readers": found.readers,
        "returned": [
            {"week": week, "joined": n, "second": back} for week, n, back in found.returned
        ],
        "first": [
            {"opened": when, "title": title, "finished": done} for when, title, done in found.first
        ],
        "shelves": found.shelves,
        "biblical": {"readers": found.biblical_readers, "crossed": found.biblical_who_crossed},
        "ages": found.ages,
        "months": {
            month: {
                "finished": found.finished_by_month.get(month, []),
                "days": found.days_by_month.get(month, []),
            }
            for month in sorted(set(found.finished_by_month) | set(found.days_by_month))
        },
        "not_recorded": found.not_recorded,
    }
