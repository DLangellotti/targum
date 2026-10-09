"""What a series' page says about one reader (design.md §12, "A series is one page of the
desk, for everyone", 2026-10-09; boards SeriesWeekly, SeriesPortion and SeriesCycle).

The page is the same for everyone; this is the part of it that is the account's — which
sections a reader finished, where they stopped, how much of each reading they would
follow — and the part that is the calendar's, read off what is built and never off the
network: the aliyot of a Shabbat, the Shabbatot before it, the days of a cycle's month.

Every function answers with plain data and no words. The page says the words, in the
reader's language, so nothing here needs a catalogue. A reader with no account gets the
calendar's half and nothing of the account's: no marks, no known share.

Read marks are Read and Started, never "missed" (David, 2026-10-08): a reading not opened
is not marked at all.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .accounts import Person, Store
    from .parasha.models import Index, Portion
    from .weekly.models import Issue, Level

log = logging.getLogger(__name__)

#: Where the reader's page writes its document id, as `parasha.build.document_of` reads it.
_DOCUMENT = re.compile(r'"document":\s*"([0-9a-f]{16,})"')

#: The share known at which a weekly level is one the reader would follow: the Library's
#: "Read it now" (`search.BANDS`).
FOLLOWS_AT = 0.9

#: How many past ones a page lists before See all.
PAST = 5


class Reader:
    """Who is asking, and what the account knows that a page needs: the sections they
    finished and where they stopped, by document, and the words they marked, by language.
    Built once a request and asked many times; empty for a stranger."""

    def __init__(self, store: Store | None, person: Person | None) -> None:
        self.store = store
        self.person = person
        self._marked: dict[str, dict[str, int]] = {}

    @property
    def signed_in(self) -> bool:
        return self.store is not None and self.person is not None

    def finished(self, document: str) -> set[str]:
        if not self.signed_in or not document:
            return set()
        assert self.store is not None and self.person is not None
        return self.store.finished_sections(self.person.id, document)

    def place(self, document: str) -> dict[str, Any] | None:
        if not self.signed_in or not document:
            return None
        assert self.store is not None and self.person is not None
        found = self.store.places(self.person.id, limit=1, document=document)
        return found[0] if found else None

    def marked(self, language: str = "he") -> dict[str, int]:
        if not self.signed_in:
            return {}
        if language not in self._marked:
            assert self.store is not None and self.person is not None
            self._marked[language] = self.store.marked(self.person, language)
        return self._marked[language]

    def mark(self, document: str, sections: int) -> dict[str, Any]:
        """Read, Started or nothing for one reading, and where in it the reader stopped.

        `sections` is how many the reading has; 0 or 1 is a reading written whole, which
        is read when its one section is."""
        finished = self.finished(document)
        place = self.place(document)
        whole = max(1, sections)
        if finished and len(finished) >= whole:
            state = "read"
        elif finished or place is not None:
            state = "started"
        else:
            state = ""
        here = str(place.get("section") or "") if place else ""
        return {"state": state, "finished": finished, "here": here}


def reader_document(reader: Path, opens: str = "sec-0001.html") -> tuple[str, int]:
    """The document id a built reader keeps its finished sections under, and how many
    section files it has; ("", 0) where it has no reader. The weekly and a cycle's day
    read it off the page the way `parasha.build.document_of` does for a portion."""
    page = reader / opens
    if not page.is_file():
        page = reader / "index.html"
    try:
        stamp = page.stat().st_mtime_ns
    except OSError:
        return "", 0
    return _document(page, stamp)


@lru_cache(maxsize=256)
def _document(page: Path, stamp: int) -> tuple[str, int]:
    try:
        found = _DOCUMENT.search(page.read_text(encoding="utf-8"))
    except OSError:
        return "", 0
    return (found.group(1) if found else "", len(list(page.parent.glob("sec-*.html"))))


def _share(lemmas: list[str] | tuple[str, ...], marked: dict[str, int]) -> int | None:
    """How much of a list of words the reader knows, as a whole percent, or None where
    they have marked nothing to measure against."""
    from .coverage import KNOWN

    if not marked or not lemmas:
        return None
    hits = sum(1 for lemma in lemmas if marked.get(lemma) == KNOWN)
    return int(hits * 100 / len(lemmas))


def _folder_share(folder: Path, marked: dict[str, int]) -> int | None:
    """How much of a built text the reader knows, off its own annotation, the way a
    contents page measures a part (`coverage.sections_lemmas`)."""
    from . import coverage

    if not marked:
        return None
    every: list[str] = []
    for lemmas in coverage.sections_lemmas(folder).values():
        every.extend(lemmas)
    return _share(every, marked)


def band(known: int | None) -> str:
    """The Library's band for a share known: now, stretch, hard, or ""."""
    from .search import band as search_band

    return search_band(None if known is None else known / 100)


# -- the weekly -------------------------------------------------------------------------


def weekly_known(reader: Reader, issue: Issue) -> dict[str, int | None]:
    """How much of each level of one issue the reader knows, by level."""
    from .weekly import index as weekly
    from .weekly.models import folder

    marked = reader.marked("he")
    out: dict[str, int | None] = {}
    for edition in issue.editions:
        level = edition.level
        out[level.value] = _folder_share(weekly.root() / folder(issue.id, level), marked)
    return out


def _weekly_document(issue_id: str, level: Level) -> tuple[str, int]:
    from .weekly import index as weekly
    from .weekly.models import folder

    found = weekly.root() / folder(issue_id, level)
    try:
        said = json.loads((found / "document.json").read_text(encoding="utf-8"))
        document = str(said.get("content_hash") or "")
    except (OSError, ValueError, AttributeError):
        document = ""
    sections = len(list((found / "reader").glob("sec-*.html")))
    if not document:
        document, sections = reader_document(found / "reader")
    return document, sections


def weekly_level(reader: Reader, issue: Issue, published: list[Issue], default: Level) -> Level:
    """The level to open an issue at for this reader (design.md §12, 2026-10-09): the
    hardest one whose words they would follow; where they have marked words but would
    follow none, the easiest; with nothing to measure, the one they read last; else
    `default` where the issue has it, else its first."""
    levels = [edition.level for edition in issue.editions]
    if not levels:
        return default
    known = weekly_known(reader, issue) if reader.signed_in else {}
    measured = {level: known.get(level.value) for level in levels}
    if any(share is not None for share in measured.values()):
        following = [level for level in levels if (measured[level] or 0) >= FOLLOWS_AT * 100]
        return following[-1] if following else levels[0]
    if reader.signed_in:
        last: tuple[int, Level] | None = None
        for one in published[:8]:
            for edition in one.editions:
                document, _ = _weekly_document(one.id, edition.level)
                place = reader.place(document)
                at = int(place.get("at") or 0) if place else 0
                if at and (last is None or at > last[0]) and edition.level in levels:
                    last = (at, edition.level)
        if last is not None:
            return last[1]
    return default if default in levels else levels[0]


def weekly_view(
    reader: Reader, issue: Issue, level: Level, published: list[Issue]
) -> dict[str, Any]:
    """The weekly's page for one reader: how much of each level they know, and Read or
    Started on each past issue, with the level they read it at."""
    known = weekly_known(reader, issue) if reader.signed_in else {}
    past: list[dict[str, Any]] = []
    for one in [other for other in published if other.dated < issue.dated][:PAST]:
        marked: dict[str, Any] = {"state": "", "level": ""}
        share: int | None = None
        if reader.signed_in:
            for edition in one.editions:
                document, sections = _weekly_document(one.id, edition.level)
                got = reader.mark(document, sections)
                if got["state"] == "read" or (got["state"] and not marked["state"]):
                    marked = {"state": got["state"], "level": edition.level.value}
            shown_at = marked["level"] or level.value
            share = weekly_known(reader, one).get(shown_at)
        past.append({"issue": one, "mark": marked, "known": share})
    following = [value for value in (row["known"] for row in past) if value is not None]
    return {
        "known": known,
        "past": past,
        # "You'd follow about 92% of it", going by the issues before it.
        "next_known": round(sum(following) / len(following)) if following else None,
        "next_counted": len(following),
    }


# -- the weekly portion -----------------------------------------------------------------


def aliyot_of(portion: Portion, shabbat: date | None, schedule: Any) -> list[dict[str, Any]]:
    """The aliyot of a reading as verse ranges, off the calendar's cache: this Shabbat's
    where the page is a week, else the next Shabbat in the cache that reads the portion.
    Empty where the cache has none, and the page then names the aliyot alone."""
    from .parasha import calendar

    reading = None
    try:
        if shabbat is not None:
            reading = calendar.for_shabbat(shabbat, schedule, allow_fetch=False)
            if reading is not None and calendar.slug(reading.name) != portion.slug:
                reading = None
        if reading is None:
            reading = _reading_named(portion.slug, schedule.value)
    except Exception as error:  # noqa: BLE001 — a calendar that cannot be read is no aliyot
        log.warning("series: no aliyot for %s: %s", portion.slug, error)
        return []
    if reading is None:
        return []
    return [
        {
            "number": one.number,
            "book": one.book,
            "begin": one.begin,
            "end": one.end,
            "verses": one.verses,
        }
        for one in reading.aliyot
    ]


@lru_cache(maxsize=4)
def _readings(year: int, schedule: str) -> tuple[Any, ...]:
    from .parasha import calendar

    return tuple(calendar.year(year, calendar.Schedule(schedule), allow_fetch=False))


def _reading_named(slug: str, schedule: str) -> Any:
    from .parasha import calendar

    this = date.today().year
    for year in (this, this + 1, this - 1):
        for one in _readings(year, schedule):
            if calendar.slug(one.name) == slug and one.aliyot:
                return one
    return None


def portion_view(
    reader: Reader,
    portion: Portion,
    *,
    index: Index,
    schedule: Any,
    shabbat: date | None,
    haftarah: Any,
    readable: set[str],
) -> dict[str, Any]:
    """The weekly portion's page for one reader: each aliyah Read, Started or where they
    stopped; how much of the portion, the next one and each past one they know; and the
    Shabbatot before this one."""
    from .parasha import build as corpus
    from .parasha.calendar import pointing_at

    marked = reader.marked("he")

    def known(one: Portion) -> int | None:
        if not marked:
            return None
        words = corpus.lemmas_of(one)
        return _share(words, marked) if words else None

    document, sections = corpus.document_of(portion.folder)
    mark = reader.mark(document, sections)
    aliyot = aliyot_of(portion, shabbat, schedule)
    haftarah_mark: dict[str, Any] = {"state": "", "finished": set(), "here": ""}
    if haftarah is not None and haftarah.folder in readable:
        kept, count = corpus.document_of(haftarah.folder, haftarah.opens)
        haftarah_mark = reader.mark(kept, count)

    week = shabbat or pointing_at()
    following = corpus.following(portion.folder, schedule, index=index)
    past: list[dict[str, Any]] = []
    for back in range(1, 12):
        if len(past) >= PAST:
            break
        day = week - timedelta(days=7 * back)
        found = index.week(day.isoformat(), schedule)
        one = index.portions.get(found.slug) if found is not None else None
        if one is None or one.folder not in readable or one.slug == portion.slug:
            continue
        kept, count = corpus.document_of(one.folder)
        past.append(
            {
                "portion": one,
                "day": day,
                "mark": reader.mark(kept, count),
                "known": known(one),
            }
        )
    return {
        "sections": sections,
        "mark": mark,
        "aliyot": aliyot,
        "haftarah_mark": haftarah_mark,
        "known": known(portion),
        "next": following,
        "next_day": (shabbat + timedelta(days=7)) if shabbat is not None else None,
        "next_known": known(following) if following is not None else None,
        "past": past,
    }


# -- a learning cycle -------------------------------------------------------------------


def _day_mark(reader: Reader, cycle: str, day: date) -> dict[str, Any]:
    from .daily import build as corpus

    if not reader.signed_in:
        return {"state": "", "finished": set(), "here": ""}
    document, sections = reader_document(
        corpus.folder_for(cycle, day) / "reader", corpus.opens_at(cycle, day)
    )
    return reader.mark(document, sections)


def _month_of(hdate: str) -> tuple[str, str]:
    """The month and the year of a Hebrew date as Hebcal writes it: "27 Tishrei 5787"."""
    parts = hdate.split()
    if len(parts) < 3:
        return "", ""
    return " ".join(parts[1:-1]), parts[-1]


def cycle_view(reader: Reader, cycle: Any, day: Any) -> dict[str, Any]:
    """A cycle's page for one reader: the Hebrew month the day is in, a cell a day with
    what it reads, which of them are built and which the reader read; the days before
    this one that are built, newest first; and tomorrow's reading."""
    from .daily import build as corpus
    from .daily.calendar import for_day, year

    month, hyear = _month_of(day.hdate)
    cells: list[dict[str, Any]] = []
    if month:
        try:
            days = [
                one
                for when in (day.day.year - 1, day.day.year, day.day.year + 1)
                for one in year(when, allow_fetch=False)
                if one.cycle == cycle.slug and _month_of(one.hdate) == (month, hyear)
            ]
        except Exception as error:  # noqa: BLE001 — no calendar is no month, not a 500
            log.warning("series: no month for %s: %s", cycle.slug, error)
            days = []
        seen: set[date] = set()
        for one in sorted(days, key=lambda found: found.day):
            if one.day in seen:
                continue
            seen.add(one.day)
            built = corpus.readable(cycle.slug, one.day)
            cells.append(
                {
                    "day": one,
                    "number": one.hdate.split()[0],
                    "built": built,
                    "mark": _day_mark(reader, cycle.slug, one.day) if built else {"state": ""},
                    "here": one.day == day.day,
                }
            )
    past: list[dict[str, Any]] = []
    for iso in sorted(corpus.days_of(cycle.slug), reverse=True):
        if len(past) >= PAST:
            break
        try:
            when = date.fromisoformat(iso)
        except ValueError:
            continue
        if when >= day.day or not corpus.readable(cycle.slug, when):
            continue
        found = for_day(cycle, when, allow_fetch=False)
        if found is not None:
            past.append({"day": found, "mark": _day_mark(reader, cycle.slug, when)})
    tomorrow = for_day(cycle, day.day + timedelta(days=1), allow_fetch=False)
    return {
        "month": month,
        "cells": cells,
        "past": past,
        "mark": _day_mark(reader, cycle.slug, day.day),
        "tomorrow": tomorrow,
        "tomorrow_built": tomorrow is not None and corpus.readable(cycle.slug, tomorrow.day),
    }
