"""The rolling window of days, built and on disk.

`/parasha` builds a corpus: fifty-four portions and nine festival readings, fixed
forever, built once and pointed at by a calendar. A learning cycle is not that shape. Six
years of Mishna Yomi is two thousand and ninety-six days, and building them all would be
two thousand folders of ninety words each for a page that shows one of them.

So this is a window. A cron builds today and the days after it, and rolls forward; a day
that has gone by is left where it is until `prune` takes it. What makes that safe is what
makes the parasha's build safe — the same day cut from the same texts produces the same
reader — so running it twice is running it once and writing the files again.

Nothing here fetches a text or asks a model for anything. The books and the tractates are
already built, the translation is already published, and a day is a range of segments
inside one of them.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..parasha.cut import MissingBook
from ..paths import write_atomic
from ..render.builder import render
from .calendar import Day, today, window
from .cut import cut
from .cycles import BY_SLUG, CYCLES, Cycle

#: How many days ahead to build. Two weeks is enough that a box which cannot reach
#: Hebcal for a fortnight still has every page it needs, and few enough that a run is
#: seconds rather than minutes.
DAYS_AHEAD = 14

#: How many past days to keep. A reader who opened yesterday's page and comes back to it
#: should find it; a reader looking for last spring is looking for the text itself, which
#: is on the shelf under its own name.
DAYS_BEHIND = 7


def root() -> Path:
    from ..parasha.calendar import root as corpus

    return corpus() / "daily"


def index_path() -> Path:
    return root() / "index.json"


def folder_for(cycle: str, day: date) -> Path:
    return root() / "read" / cycle / day.isoformat()


def load() -> dict[str, Any]:
    """What is built, by cycle and day. Empty where nothing has been."""
    try:
        found = json.loads(index_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def build(
    *,
    ahead: int = DAYS_AHEAD,
    behind: int = DAYS_BEHIND,
    cycles: Iterable[Cycle] = CYCLES,
    library: Path | None = None,
    notify: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Build the window and write the index."""

    def say(message: str) -> None:
        if notify is not None:
            notify(message)

    wanted = {cycle.slug for cycle in cycles}
    first = today() - timedelta(days=behind)
    last = today() + timedelta(days=ahead - 1)
    days = [one for one in window(first, last) if one.cycle in wanted]
    say(f"{len(days)} days, {first} to {last}")

    built: dict[str, dict[str, object]] = {}
    absent: set[str] = set()
    for one in days:
        try:
            portion = cut(one, library)
        except MissingBook as gone:
            # A text that is not on the shelf takes its days with it and leaves the rest
            # of the window alone. Said once per text rather than once per day.
            if gone.book not in absent:
                absent.add(gone.book)
                say(f"  {gone.book} is not built — every day in it is skipped")
            continue
        folder = folder_for(one.cycle, one.day)
        render(
            portion.document,
            portion.segmented,
            portion.translations,
            folder / "reader",
            annotation=portion.annotation,
            glossaries=portion.glossaries,
            vocalization=portion.vocalization,
            clean=True,
            folder=folder,
        )
        built.setdefault(one.cycle, {})[one.day.isoformat()] = {
            "title": one.title,
            "hebrew": one.hebrew,
            "hdate": one.hdate,
            "reference": one.reference,
            "units": sum(1 for block in portion.document.blocks if block.kind.value != "heading"),
        }

    index: dict[str, Any] = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "first": first.isoformat(),
        "last": last.isoformat(),
        "cycles": built,
    }
    index_path().parent.mkdir(parents=True, exist_ok=True)
    write_atomic(index_path(), json.dumps(index, ensure_ascii=False, indent=1) + "\n")
    prune(first)
    say(f"built {sum(len(v) for v in built.values())} days")
    return index


def prune(before: date) -> int:
    """Take away the days that have fallen out of the window.

    Only whole day folders under a cycle this package built, and only ones named by a
    date older than the window — so a directory somebody put there by hand is left alone
    rather than deleted by a rule it never agreed to.
    """
    gone = 0
    read = root() / "read"
    if not read.is_dir():
        return 0
    for cycle in read.iterdir():
        if not cycle.is_dir() or cycle.name not in BY_SLUG:
            continue
        for day in cycle.iterdir():
            if not day.is_dir():
                continue
            try:
                when = date.fromisoformat(day.name)
            except ValueError:
                continue
            if when < before:
                shutil.rmtree(day, ignore_errors=True)
                gone += 1
    return gone


def readable(cycle: str, day: date) -> bool:
    """Whether this day has a reader on disk right now."""
    return (folder_for(cycle, day) / "reader" / "index.html").is_file()


def opens_at(cycle: str, day: date) -> str:
    """Which file of a built day the page should show first.

    The first section where the day has more than one — seven psalms make seven sections
    and `index.html` is then a list of seven links with a button, which is a poor thing to
    hand somebody who came to read. But a day of Mishna Yomi is one chapter and the
    renderer writes it no `sec-0001.html` at all, so pointing there unconditionally is a
    404 on three cycles out of four. Asked of the disk, which is the only thing that
    knows.
    """
    return (
        "sec-0001.html"
        if (folder_for(cycle, day) / "reader" / "sec-0001.html").is_file()
        else "index.html"
    )


def current(cycle: str) -> tuple[date, dict[str, object]] | None:
    """Today's entry for one cycle, from what was built."""
    when = today()
    held = load().get("cycles", {})
    days = held.get(cycle, {}) if isinstance(held, dict) else {}
    found = days.get(when.isoformat()) if isinstance(days, dict) else None
    return (when, found) if isinstance(found, dict) else None


def days_of(cycle: str) -> dict[str, dict[str, object]]:
    held = load().get("cycles", {})
    days = held.get(cycle, {}) if isinstance(held, dict) else {}
    return days if isinstance(days, dict) else {}


def known(day: Day) -> bool:
    return day.cycle in BY_SLUG
