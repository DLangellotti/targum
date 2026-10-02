"""Telling the operator when a Monday passes without an issue (targum-internal#404).

The weekly is written on a laptop and read on the box, and between 24 August and 28
September it published two issues in five weeks with nobody told. The run that stopped
on 2026-w40 wrote its reason to `/tmp/targum-weekly.log` and exited 1; the three weeks
before it left no trace at all, so whether the lid was shut, the job unloaded or the run
dead before it wrote anything was a guess.

So two halves, both through `alerts.tell`, the mailer the health watch and the backup
already use:

- **The run says when it stops.** `deploy/weekly-run.sh` hands its last words to
  `targum weekly stopped` on the box, which mails them the same minute. That covers a
  run that started.
- **The box notices a Monday with no issue.** `targum watch-weekly`, hourly from
  `targum-weekly-watch.timer`, looks for this week's issue in the box's own index once it
  is due, and mails once if it is not published. That covers a run that never started,
  which is the case the laptop can say nothing about.

And every week the watch sees is a line in its state file, published or not, with what
it found and whether anybody was told. A missing week is then a fact on the box rather
than a gap in the index.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

#: When an issue is due: Monday at 12:00 UTC. The run starts at 07:00 Israel time
#: (04:00 or 05:00 UTC) and takes minutes, and a laptop that was asleep runs it when it
#: wakes, so noon leaves the morning for that before anybody is mailed.
DUE = timedelta(hours=12)

#: Where the run's own log is, named in every mail so the next step is in it.
LOG = "/tmp/targum-weekly.log"


def week_of(moment: datetime) -> str:
    """The ISO week, as the weekly names it: 2026-w40, as `date +%G-w%V` prints it."""
    year, week, _ = moment.isocalendar()
    return f"{year}-w{week:02d}"


def due(moment: datetime) -> str:
    """The week whose issue should be out by now, or "" before this Monday's noon."""
    monday = (moment - timedelta(days=moment.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return week_of(moment) if moment >= monday + DUE else ""


@dataclass
class Week:
    """What the watch knows about one week."""

    #: published, draft, withdrawn, or missing: what the box's index said last time.
    found: str = ""
    checked: str = ""
    #: When somebody was mailed about it. Empty means nobody has been yet.
    told: str = ""
    #: What the run said when it stopped, if it said anything.
    reason: str = ""


def load(path: Path) -> dict[str, Week]:
    """Every week the watch has seen. An unreadable file starts over: the worst that
    costs is one mail sent twice."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    weeks = raw.get("weeks") if isinstance(raw, dict) else None
    if not isinstance(weeks, dict):
        return {}
    kept: dict[str, Week] = {}
    for name, fields in weeks.items():
        if isinstance(fields, dict):
            known = {key: str(fields[key]) for key in Week.__dataclass_fields__ if key in fields}
            kept[str(name)] = Week(**known)
    return kept


def save(path: Path, weeks: dict[str, Week]) -> None:
    """Written whole and moved into place, so a kill mid-write leaves the old record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = path.with_name(f".{path.name}.tmp")
    body = {"weeks": {name: asdict(weeks[name]) for name in sorted(weeks)}}
    fresh.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    fresh.replace(path)


def missing_mail(week: str, found: str) -> tuple[str, str]:
    said = "has no issue" if found == "missing" else f"has {week} only as a {found}"
    return (
        f"targum: no weekly for {week}",
        f"targum.page {said} for {week}, and it was due by Monday at 07:00.\n\n"
        "Either the run on the laptop did not start (the lid was shut, or "
        "page.targum.weekly is not loaded), or it stopped before it shipped and could "
        "not say so. On the laptop:\n"
        f"  tail -40 {LOG}\n"
        "  launchctl list page.targum.weekly\n\n"
        f"To run it by hand: ./deploy/weekly-run.sh {week}\n",
    )


def stopped_mail(week: str, reason: str) -> tuple[str, str]:
    return (
        f"targum: the weekly run for {week} stopped",
        f"The run for {week} stopped, and said:\n\n{reason.strip()}\n\n"
        f"The whole run is in {LOG} on the laptop. Fix what it names, then run it "
        f"again: ./deploy/weekly-run.sh {week}. It picks up where it stopped.\n",
    )


def check(
    state: Path,
    find: Callable[[str], str],
    send: Callable[[str, str], object],
    *,
    now: datetime | None = None,
) -> str:
    """One look: record what the box has for this week, and mail once if it is due and
    not out. `find` gives the issue's state, or "missing". `send` returning False means
    nobody is configured to hear it: the week is recorded and left untold. Returns a line
    for the journal. Raises if a due mail did not go, after recording the week as untold, so the
    next look owes the same mail."""
    moment = now or datetime.now(UTC)
    week = due(moment)
    if not week:
        return f"{week_of(moment)} is not due until Monday noon UTC"
    weeks = load(state)
    entry = weeks.setdefault(week, Week())
    entry.found = find(week)
    entry.checked = moment.isoformat()
    if entry.found == "published":
        save(state, weeks)
        return f"{week} is out"
    if entry.told:
        save(state, weeks)
        return f"{week} is {entry.found}; told at {entry.told}"
    try:
        sent = send(*missing_mail(week, entry.found))
    finally:
        save(state, weeks)
    if sent is False:
        return f"{week} is {entry.found}, and nobody is configured to hear it"
    entry.told = moment.isoformat()
    save(state, weeks)
    return f"{week} is {entry.found}: mailed"


def stopped(
    state: Path,
    week: str,
    reason: str,
    send: Callable[[str, str], object],
    *,
    now: datetime | None = None,
) -> str:
    """The run says it stopped: mail it now, every time, and record it. A second stop is a
    second run somebody started, and its reason may be new."""
    moment = now or datetime.now(UTC)
    weeks = load(state)
    entry = weeks.setdefault(week, Week())
    entry.reason = reason.strip()
    entry.checked = moment.isoformat()
    try:
        sent = send(*stopped_mail(week, reason))
    finally:
        save(state, weeks)
    if sent is False:
        return f"{week} stopped, and nobody is configured to hear it"
    entry.told = moment.isoformat()
    save(state, weeks)
    return f"{week} stopped: mailed"
