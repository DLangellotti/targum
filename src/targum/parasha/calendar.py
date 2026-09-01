"""Which reading is this Shabbat, on either schedule.

The Hebrew calendar is not something to reimplement. Leap months, the four postponement
rules, the doubled portions that undouble in a leap year, and the weeks after Pesach and
Shavuot where Israel and the diaspora read different portions until a doubled one puts
them back in step — each is a rule with exceptions, and getting the set right is a year
of somebody's life. Hebcal has done it, publishes it, and gives the aliyah ranges in the
same answer, which is what makes the cut and the calendar agree by construction instead
of against a table maintained by hand.

So this fetches, once a year, into a cache beside the corpus. A build with no network
and a warm cache is a build that works; a build with no network and a cold cache says so
rather than guessing. Nothing here runs while a reader waits — the page is served from
what the last build wrote.

**Israel and the diaspora.** Fetched as two separate years, because the divergence is
not a shift by one: the diaspora reads a festival on a day Israel reads a portion, and
for the six weeks after they are a portion apart until a week the diaspora doubles and
Israel does not. Measured on 2026: six Shabbatot apart, closing at Chukat-Balak. 2028 has
none at all. Both are fixtures in the tests.

**When the portion turns over.** Motzei Shabbat, on one clock for everybody:
`FLIP_AT` past midnight Saturday in `America/New_York`. A fixed reference beats reading
the visitor's clock, which would show two people different portions on the same evening
and cache badly besides. The hour is late enough that the turn never lands inside Shabbat
anywhere in the continental United States — nightfall in the Pacific timezone in June is
about 22:30 local, which is 01:30 in New York — and early enough to still be Saturday
night where most readers are.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..errors import TargumError
from ..paths import write_atomic

#: Hebcal's leyning endpoint. A whole year comes back in one answer, about 60 kB.
ENDPOINT = "https://www.hebcal.com/leyning"

TIMEOUT = 30.0

#: The clock the turn is measured on, and the moment it happens on it. See the module
#: docstring: 02:00 Sunday in New York is 23:00 Saturday in the Pacific timezone, which
#: is after nightfall across the continental United States on every night of the year.
FLIP_ZONE = "America/New_York"
FLIP_AT = time(2, 0)

#: The five books, as Hebcal names them, in the order they are read. A reading that
#: names anything else is not Torah — a haftarah, or one of the megillot — and this
#: package does not carry it: see `ReadingKind` and `Reading.aliyot`.
TORAH_BOOKS = ("Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy")


class Schedule(StrEnum):
    """Which of the two calendars. Values are identifiers — URLs, folders, cache keys."""

    diaspora = "diaspora"
    israel = "israel"


class ReadingKind(StrEnum):
    """What kind of Shabbat this is.

    A festival that falls on Shabbat displaces the portion entirely: the congregation
    reads the festival's own reading and the cycle waits a week. A page that named the
    portion anyway would be telling its one reader the wrong thing to prepare.
    """

    parasha = "parasha"
    festival = "festival"


@dataclass(frozen=True, slots=True)
class Aliyah:
    """One of the seven, as a verse range in one book."""

    number: int
    book: str
    begin: str
    end: str
    verses: int


@dataclass(frozen=True, slots=True)
class Reading:
    """What is read on one Shabbat, on one schedule."""

    #: The Shabbat itself, not the week it opens.
    day: date
    schedule: Schedule
    kind: ReadingKind
    #: Hebcal's English name: "Nitzavim-Vayeilech", "Pesach Shabbat Chol ha-Moed".
    name: str
    #: The same name pointed, as it is written: נִצָּבִים־וַיֵּלֶךְ.
    hebrew: str
    #: The Hebrew date, as Hebcal says it: "23 Elul 5786".
    hdate: str
    #: Hebcal's own one-line range, kept for the page's dateline.
    summary: str
    #: Which portions of the annual cycle this is, 1-54. Two where a week is doubled,
    #: none at all on a festival.
    numbers: tuple[int, ...]
    aliyot: tuple[Aliyah, ...]

    @property
    def doubled(self) -> bool:
        return len(self.numbers) > 1

    @property
    def slug(self) -> str:
        """The name in a URL: `nitzavim-vayeilech`, `pesach-shabbat-chol-ha-moed`."""
        return slug(self.name)

    @property
    def books(self) -> tuple[str, ...]:
        """Every book the aliyot touch, in the order they are first read."""
        seen: list[str] = []
        for one in self.aliyot:
            if one.book not in seen:
                seen.append(one.book)
        return tuple(seen)


#: The one portion the Shabbat cycle never produces.
#:
#: וזאת הברכה is read on Simchat Torah and on no ordinary Shabbat ever, so a calendar
#: walked for a century would never hand it over and the last two chapters of
#: Deuteronomy would simply be missing from the shelf. Its span is fixed and its
#: division is the traditional one, so it is written down here rather than asked for.
#: Hebcal does carry it inside the Simchat Torah reading, which is a different reading —
#: it runs on into the opening of Bereshit — and is built under that name besides.
ALWAYS = (
    {
        "name": {"en": "V'Zot HaBerachah", "he": "וְזֹאת הַבְּרָכָה"},
        "type": "shabbat",
        "parshaNum": 54,
        "summary": "Deuteronomy 33:1-34:12",
        "hdate": "",
        "fullkriyah": {
            "1": {"k": "Deuteronomy", "b": "33:1", "e": "33:7", "v": 7},
            "2": {"k": "Deuteronomy", "b": "33:8", "e": "33:12", "v": 5},
            "3": {"k": "Deuteronomy", "b": "33:13", "e": "33:17", "v": 5},
            "4": {"k": "Deuteronomy", "b": "33:18", "e": "33:21", "v": 4},
            "5": {"k": "Deuteronomy", "b": "33:22", "e": "33:26", "v": 5},
            "6": {"k": "Deuteronomy", "b": "33:27", "e": "33:29", "v": 3},
            "7": {"k": "Deuteronomy", "b": "34:1", "e": "34:12", "v": 12},
        },
    },
)


def always(schedule: Schedule = Schedule.diaspora) -> list[Reading]:
    """The readings that belong to the corpus but never to a Shabbat."""
    out = []
    for item in ALWAYS:
        one = _reading({**item, "date": date(1, 1, 6).isoformat()}, schedule)
        if one is not None:
            out.append(one)
    return out


def slug(name: str) -> str:
    """A reading's name as an identifier.

    Hebcal's names carry apostrophes and spaces — "Sh'lach", "Achrei Mot-Kedoshim",
    "Pesach Shabbat Chol ha-Moed". Lowercased, punctuation dropped, spaces to hyphens,
    the doubled portions keep the hyphen that joins them.
    """
    kept = [c.lower() if c.isalnum() else "-" if c in " -" else "" for c in name]
    out = "".join(kept)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")


def root() -> Path:
    """Where the corpus and this cache live.

    Named in the environment the way the weekly's is, so a test and a server can each
    have their own and neither writes where the other reads.
    """
    named = os.environ.get("TARGUM_PARASHA_DIR", "").strip()
    if named:
        return Path(named).expanduser()
    return Path.cwd() / "targum-out" / "parasha"


def _cache_path(year: int, schedule: Schedule) -> Path:
    return root() / "calendar" / f"{year}-{schedule.value}.json"


def _aliyot(item: dict[str, Any]) -> tuple[Aliyah, ...]:
    """The numbered aliyot, in order, Torah only.

    `fullkriyah` is keyed by strings: "1" through "7", plus "M" for the maftir. The
    maftir is deliberately dropped — on a portion it repeats the end of the seventh,
    and on a festival it is the additional offering from Numbers, which is a different
    reading from the one this page is for. A festival's megillah and every haftarah
    arrive in their own fields and are not read here at all.
    """
    out: list[Aliyah] = []
    for key, value in sorted((item.get("fullkriyah") or {}).items()):
        if not key.isdigit():
            continue
        book = str(value.get("k", ""))
        if book not in TORAH_BOOKS:
            # A numbered aliyah outside the Torah would mean Hebcal changed shape under
            # us. Skip it rather than cut a span out of a book we do not carry.
            continue
        out.append(
            Aliyah(
                number=int(key),
                book=book,
                begin=str(value.get("b", "")),
                end=str(value.get("e", "")),
                verses=int(value.get("v", 0) or 0),
            )
        )
    return tuple(sorted(out, key=lambda one: one.number))


def _reading(item: dict[str, Any], schedule: Schedule) -> Reading | None:
    """One Hebcal item as a reading, or None if it is not one we show.

    Hebcal returns three kinds: `shabbat` (a portion), `holiday` (a festival reading,
    which on a Shabbat is what is actually read), and `weekday` — the Monday and
    Thursday readings, which are a shortened version of the coming Shabbat's portion and
    would otherwise arrive as duplicates.
    """
    kind = str(item.get("type", ""))
    if kind == "weekday":
        return None
    day = date.fromisoformat(str(item["date"]))
    if kind == "holiday" and day.weekday() != 5:
        # A festival on a weekday is read that morning, and leaves the Shabbat cycle
        # alone. Only a festival that falls on Shabbat displaces a portion.
        return None
    aliyot = _aliyot(item)
    if not aliyot:
        return None
    name = item.get("name") or {}
    # One portion comes back as a bare number and a doubled week as a list of two, so
    # the shape of this field is itself the answer to "is this week doubled".
    raw = item.get("parshaNum")
    if raw is None:
        numbers: tuple[int, ...] = ()
    elif isinstance(raw, int):
        numbers = (raw,)
    else:
        numbers = tuple(int(n) for n in raw)
    return Reading(
        day=day,
        schedule=schedule,
        kind=ReadingKind.parasha if kind == "shabbat" else ReadingKind.festival,
        name=str(name.get("en", "")),
        hebrew=str(name.get("he", "")),
        hdate=str(item.get("hdate", "")),
        summary=str(item.get("summary", "")),
        numbers=numbers,
        aliyot=aliyot,
    )


def parse(payload: dict[str, Any], schedule: Schedule) -> list[Reading]:
    """Hebcal's answer as readings, in date order."""
    out = [_reading(item, schedule) for item in payload.get("items", [])]
    return sorted((one for one in out if one is not None), key=lambda one: one.day)


def fetch(year: int, schedule: Schedule) -> dict[str, Any]:
    """One year from Hebcal. The only network call in the package.

    In quarters, because the endpoint silently clamps a range to six months: ask it for
    a year and it answers for January to June, says so in a `range` field nobody reads,
    and returns 200. A year fetched in one call is a year whose autumn is missing and
    nothing anywhere says so — the portions from Rosh Hashanah on simply are not there,
    and the page for those weeks comes out empty. Four windows have margin over the cap
    and cost four requests once a year.
    """
    import httpx

    windows = [
        (date(year, 1, 1), date(year, 3, 31)),
        (date(year, 4, 1), date(year, 6, 30)),
        (date(year, 7, 1), date(year, 9, 30)),
        (date(year, 10, 1), date(year, 12, 31)),
    ]
    merged: dict[str, Any] = {}
    items: list[dict[str, Any]] = []
    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
            for first, last in windows:
                params = {
                    "cfg": "json",
                    "start": first.isoformat(),
                    "end": last.isoformat(),
                }
                if schedule is Schedule.israel:
                    params["i"] = "on"
                answer = client.get(ENDPOINT, params=params)
                answer.raise_for_status()
                payload = answer.json()
                if not merged:
                    merged = {k: v for k, v in payload.items() if k != "items"}
                items.extend(payload.get("items") or [])
    except Exception as bad:  # noqa: BLE001 — every failure here is the same failure
        raise TargumError(
            f"The reading calendar for {year} could not be fetched.",
            f"{ENDPOINT} said: {bad}. The cached years already on disk still build.",
        ) from bad
    if not items:
        raise TargumError(
            f"The reading calendar for {year} came back empty.",
            "Hebcal answered, with nothing in it. Nothing was written to the cache.",
        )
    # One entry per date and type: the windows abut rather than overlap, but a boundary
    # that shifts under us should not put a Shabbat in twice.
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        unique.setdefault((str(item.get("date")), str(item.get("type"))), item)
    merged["items"] = [unique[key] for key in sorted(unique)]
    merged["range"] = {"start": f"{year}-01-01", "end": f"{year}-12-31"}
    return merged


def refresh(year: int, schedule: Schedule) -> list[Reading]:
    """Fetch a year and write it to the cache, replacing whatever was there."""
    payload = fetch(year, schedule)
    readings = parse(payload, schedule)
    write_atomic(_cache_path(year, schedule), json.dumps(payload, ensure_ascii=False))
    return readings


def year(year: int, schedule: Schedule, *, allow_fetch: bool = True) -> list[Reading]:
    """A year's readings, from the cache, fetching once if it is not there.

    `allow_fetch=False` is what a server passes: a page being served must never wait on
    somebody else's website, and a year that is missing at that point is a build that
    did not run.
    """
    path = _cache_path(year, schedule)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        if not allow_fetch:
            return []
        return refresh(year, schedule)
    return parse(payload, schedule)


def _span(first: date, last: date, schedule: Schedule, *, allow_fetch: bool) -> list[Reading]:
    """Readings across a date range, crossing the year boundary where it falls."""
    out: list[Reading] = []
    for one in range(first.year, last.year + 1):
        out.extend(year(one, schedule, allow_fetch=allow_fetch))
    return [one for one in out if first <= one.day <= last]


def for_shabbat(
    day: date, schedule: Schedule = Schedule.diaspora, *, allow_fetch: bool = True
) -> Reading | None:
    """What is read on the Shabbat of the week `day` falls in.

    The Shabbat this looks for is the coming one: `day` on a Tuesday finds the Shabbat
    four days later, and `day` on a Shabbat finds that same day. Turning the page over
    on Saturday night is `current`'s job, not this one's.
    """
    ahead = (5 - day.weekday()) % 7
    shabbat = day + timedelta(days=ahead)
    for one in _span(shabbat, shabbat, schedule, allow_fetch=allow_fetch):
        return one
    return None


def now_in_flip_zone(moment: datetime | None = None) -> datetime:
    """The current time on the one clock the turn is measured on."""
    try:
        zone = ZoneInfo(FLIP_ZONE)
    except Exception:  # noqa: BLE001 — a box with no tz database still has to serve
        return moment or datetime.now()
    if moment is None:
        return datetime.now(zone)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=zone)
    return moment.astimezone(zone)


def pointing_at(moment: datetime | None = None) -> date:
    """Which Shabbat a moment points at.

    Sunday through Saturday-daytime: the coming Shabbat, which on Saturday is today.
    Past `FLIP_AT` on Sunday morning — motzei Shabbat where the readers are — the week
    that just ended is over and the next one begins.
    """
    local = now_in_flip_zone(moment)
    today = local.date()
    if today.weekday() == 6 and local.time() < FLIP_AT:
        # Still Saturday night: the Shabbat that has just gone out is the one showing.
        return today - timedelta(days=1)
    ahead = (5 - today.weekday()) % 7
    return today + timedelta(days=ahead)


def current(
    schedule: Schedule = Schedule.diaspora,
    moment: datetime | None = None,
    *,
    allow_fetch: bool = True,
) -> Reading | None:
    """The reading to show right now."""
    return for_shabbat(pointing_at(moment), schedule, allow_fetch=allow_fetch)
