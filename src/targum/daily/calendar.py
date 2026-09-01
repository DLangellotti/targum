"""What each daily cycle reads today, and on any day either side of it.

The same shape as `parasha/calendar.py` and for the same reasons: the Hebrew calendar is
not something to reimplement, Hebcal has done it and publishes it, so this fetches once a
year into a cache beside the corpus and nothing here runs while a reader waits.

Three things differ from the portion.

**One fetch, every cycle.** Hebcal answers for all of them in one call, told apart by a
`category`, so the four are one request rather than four. `cycles.flags()` is the query.

**A year comes back whole.** The leyning endpoint silently clamps a range to six months
and still returns 200, which is why the portion is fetched in quarters. This endpoint
does not: asked for 2026-09-01 to 2027-08-31 it answers with all three hundred and
sixty-five days. Measured, not assumed — and fetched a year at a time anyway, because
what is being defended against is a cap changing, not a cap that is there today.

**The day turns on the portion's clock.** Midnight in `FLIP_ZONE`, which is the same
reference `/parasha` measures its own turn on. Not because midnight in New York is when a
Jewish day begins — it is not, and no fixed hour is — but because one clock for everybody
is the only way two readers on the same evening see the same page, and because a daily
page and the weekly one disagreeing about what day it is would be worse than either being
an hour out.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from ..errors import TargumError
from ..parasha.calendar import FLIP_ZONE, now_in_flip_zone, root
from ..paths import write_atomic
from .cycles import BY_CATEGORY, CYCLES, Cycle, Span, parse_reference, reference_of

__all__ = ["Day", "FLIP_ZONE", "current", "for_day", "refresh", "window", "year"]

#: Hebcal's calendar endpoint. Four cycles for a year is about 90 kB.
ENDPOINT = "https://www.hebcal.com/hebcal"

TIMEOUT = 30.0


@dataclass(frozen=True, slots=True)
class Day:
    """One cycle's reading on one day."""

    day: date
    cycle: str
    #: Hebcal's own English name for it: `Kelim 28:2-3`, `Ezra and Nehemiah Seder 10`.
    title: str
    #: The same in Hebrew, as Hebcal writes it.
    hebrew: str
    #: The Hebrew date: `19 Elul 5786`.
    hdate: str
    #: What it actually points at, which for Tanakh Yomi is not the title.
    reference: str
    #: That reference resolved, or None where its shape was not recognised.
    span: Span | None

    @property
    def slug(self) -> str:
        """The day in a URL, which is the date: `/mishna-yomi/2026-09-01`."""
        return self.day.isoformat()


def _cache_path(year_number: int) -> Path:
    return root() / "daily" / f"{year_number}.json"


def parse(payload: dict[str, Any]) -> list[Day]:
    """Hebcal's answer, as days. Anything from a cycle this shelf does not carry is
    dropped rather than kept — the request asks for four and a fifth would be noise."""
    out: list[Day] = []
    for item in payload.get("items", []):
        cycle = BY_CATEGORY.get(str(item.get("category", "")))
        if cycle is None:
            continue
        try:
            when = date.fromisoformat(str(item.get("date", ""))[:10])
        except ValueError:
            continue
        reference = reference_of(item)
        out.append(
            Day(
                day=when,
                cycle=cycle.slug,
                title=str(item.get("title", "")),
                hebrew=str(item.get("hebrew", "")),
                hdate=str(item.get("hdate", "")),
                reference=reference,
                span=parse_reference(reference),
            )
        )
    return sorted(out, key=lambda one: (one.day, one.cycle))


def fetch(year_number: int) -> dict[str, Any]:
    """One year of every cycle, in one call. The only network call in the package."""
    import httpx

    # The cycle flags go in `params` with everything else. Put in the URL's own query
    # string they are silently dropped: httpx replaces a query rather than merging one,
    # so the request went out asking for no cycles at all and came back empty.
    params = {
        "cfg": "json",
        "v": "1",
        "start": f"{year_number}-01-01",
        "end": f"{year_number}-12-31",
        # Everything that is not a learning cycle. The endpoint's default is a calendar
        # of holidays, which this does not want and would page through by the thousand.
        "maj": "off",
        "min": "off",
        "mod": "off",
        "nx": "off",
        "s": "off",
        "c": "off",
        **{cycle.flag: "on" for cycle in CYCLES},
    }
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            answer = client.get(ENDPOINT, params=params)
            answer.raise_for_status()
            payload: dict[str, Any] = answer.json()
    except Exception as error:  # noqa: BLE001 — one message, whatever went wrong
        raise TargumError(
            f"Could not reach Hebcal for {year_number}.",
            f"{type(error).__name__}: {error}",
        ) from error
    if not payload.get("items"):
        raise TargumError(f"Hebcal returned no learning for {year_number}.")
    return payload


def refresh(year_number: int) -> list[Day]:
    """Fetch a year and write it beside the corpus."""
    payload = fetch(year_number)
    path = _cache_path(year_number)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, json.dumps(payload, ensure_ascii=False))
    return parse(payload)


def year(year_number: int, *, allow_fetch: bool = True) -> list[Day]:
    """A year, from the cache where it is there and from Hebcal where it is not.

    A build with no network and a warm cache works; one with a cold cache says so rather
    than guessing, because a guessed day is the wrong text under today's date.
    """
    path = _cache_path(year_number)
    if path.is_file():
        try:
            return parse(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass  # a half-written cache is refetched, not served
    if not allow_fetch:
        return []
    return refresh(year_number)


def window(first: date, last: date, *, allow_fetch: bool = True) -> list[Day]:
    """Every cycle's readings across a span of dates, however many years it crosses."""
    out: list[Day] = []
    for number in range(first.year, last.year + 1):
        out.extend(one for one in year(number, allow_fetch=allow_fetch) if first <= one.day <= last)
    return sorted(out, key=lambda one: (one.day, one.cycle))


def for_day(cycle: Cycle | str, when: date, *, allow_fetch: bool = True) -> Day | None:
    """One cycle on one day."""
    slug = cycle if isinstance(cycle, str) else cycle.slug
    for one in year(when.year, allow_fetch=allow_fetch):
        if one.day == when and one.cycle == slug:
            return one
    return None


def today(moment: datetime | None = None) -> date:
    """The day the pages are showing, on the one clock they are all measured on."""
    return now_in_flip_zone(moment).date()


def current(
    cycle: Cycle | str, moment: datetime | None = None, *, allow_fetch: bool = True
) -> Day | None:
    """What this cycle reads right now."""
    return for_day(cycle, today(moment), allow_fetch=allow_fetch)


def upcoming(cycle: Cycle | str, days: int, moment: datetime | None = None) -> list[Day]:
    """Today and the days after it, which is what a rolling build walks."""
    slug = cycle if isinstance(cycle, str) else cycle.slug
    first = today(moment)
    return [one for one in window(first, first + timedelta(days=days - 1)) if one.cycle == slug]
