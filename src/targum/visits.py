"""How many came to the front door, from where, and what they looked at.

The operator's answer to "is anybody arriving", counted off the reverse proxy's own
access log and nothing else. There is no script on any page for this, no cookie, and
nothing sent anywhere: the log is already written for diagnosing faults (the privacy
notice's server access records), and this reads it once an hour and keeps **counts**.

What is kept, per UTC day: page views, distinct visitors, and tallies of pages,
referring sites, `utm_source` campaigns and countries. What is not kept is anything that
names a visitor. A visitor is a distinct (address, browser) pair *within one pass over
one day*, counted in memory and dropped when the pass ends — no hash, no salt, nothing
that could follow the same person from Monday to Tuesday, because there is nothing
stored to compare.

Countries come from DB-IP's free country file (CC BY 4.0, attribution on the page that
shows them), read on this box. An address is looked up here and never sent to anybody.
The file is fetched monthly by the roll-up itself; without it the country table is
empty and everything else is counted as before.

The log rotates by size, so the record of a day lives only as long as the log does.
That is the reason for the roll-up: the counts outlive the lines they were counted from.
"""

from __future__ import annotations

import contextlib
import gzip
import json
import os
import re
import sqlite3
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .errors import TargumError

#: Where Caddy writes the product's requests (`deploy/Caddyfile`). Rotated files sit
#: beside it as `targum-<stamp>.log`, gzipped unless told otherwise.
LOG = Path("/var/log/caddy/targum.log")

#: The roll-up's own file, beside the store rather than inside it: the store is the
#: readers' record and has a schema that migrates; this is the operator's and does not.
FILE = "visits.sqlite"

#: DB-IP's country file, IP to country, CC BY 4.0. Monthly, named by month.
GEOIP_FILE = "dbip-country-lite.mmdb"
GEOIP_SOURCE = "https://download.db-ip.com/free/dbip-country-lite-{month}.mmdb.gz"
GEOIP_CREDIT = "IP Geolocation by DB-IP"
GEOIP_LINK = "https://db-ip.com"
GEOIP_LICENCE = "CC BY 4.0"
#: A month and a bit: the file is published at the start of each month, and a
#: fetch that finds this month's not yet up takes last month's and tries again tomorrow.
GEOIP_STALE = timedelta(days=32)

#: Not visitors. Anything that says what it is, and anything that says nothing.
BOTS = re.compile(
    r"bot|crawl|spider|slurp|preview|scan|monitor|fetch|http|curl|wget|python|go-http|"
    r"java/|okhttp|headless|lighthouse|facebookexternalhit|whatsapp|telegram|"
    r"embedly|quora link|pinterest|bitly|vkshare|feedly|uptime",
    re.IGNORECASE,
)

#: The operator's own page is not a visit.
NOT_PAGES = ("/back-office",)

#: A path segment that is an identifier rather than a place: a hash, a number, a token.
#: Folded to one mark so that a reader's texts are one row, not a thousand.
_IDENTIFIER = re.compile(r"^(?:[0-9a-f]{8,}|\d+|[A-Za-z0-9_-]{24,})$")

KINDS = ("page", "referrer", "campaign", "country")


@dataclass
class Request:
    """One line of the log, as much of it as a count needs."""

    at: datetime
    path: str
    query: str
    visitor: tuple[str, str]
    address: str
    referrer: str


@dataclass
class Tally:
    """One day, counted."""

    day: str
    views: int = 0
    visitors: int = 0
    #: Whether the log reached back to before this day began. A day the log starts in
    #: the middle of is counted from where it starts and says so.
    whole: bool = False
    #: kind -> key -> count. Pages and referrers in views; campaigns and countries in
    #: visitors, since "how many people" is the question those two answer.
    counts: dict[str, dict[str, int]] = field(default_factory=dict)


def _when(stamp: Any) -> datetime | None:
    """Caddy's `ts`: seconds as a float by default, an ISO string if configured so."""
    if isinstance(stamp, int | float):
        return datetime.fromtimestamp(stamp, UTC)
    if isinstance(stamp, str):
        with contextlib.suppress(ValueError):
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _header(headers: dict[str, Any], name: str) -> str:
    values = headers.get(name) or []
    return str(values[0]) if values else ""


def parse(line: str) -> Request | None:
    """A log line, if it is somebody opening a page. None for everything else.

    A page is a successful GET answered with HTML — not a stylesheet, not a fetch from a
    page already open, not a redirect, not a 404 some scanner asked for.
    """
    try:
        record = json.loads(line)
    except ValueError:
        return None
    if not isinstance(record, dict):
        return None
    request = record.get("request") or {}
    if request.get("method") != "GET" or record.get("status") != 200:
        return None
    kind = _header(record.get("resp_headers") or {}, "Content-Type")
    if not kind.startswith("text/html"):
        return None
    at = _when(record.get("ts"))
    if at is None:
        return None
    headers = request.get("headers") or {}
    agent = _header(headers, "User-Agent")
    if not agent or BOTS.search(agent):
        return None
    uri = urlparse(str(request.get("uri") or "/"))
    if uri.path.startswith(NOT_PAGES):
        return None
    address = str(request.get("client_ip") or request.get("remote_ip") or "")
    return Request(
        at=at,
        path=uri.path or "/",
        query=uri.query,
        visitor=(address, agent),
        address=address,
        referrer=_header(headers, "Referer"),
    )


def page_of(path: str) -> str:
    """The row a path is counted under: identifiers folded, so `/r/3fa9…` is `/r/…`."""
    parts = [("…" if _IDENTIFIER.match(part) else part) for part in path.split("/")]
    return "/".join(parts) or "/"


def referrer_of(referrer: str, own: str) -> str:
    """The site that sent somebody, or "" for none and for our own pages.

    `android-app://com.linkedin.android/` is how the LinkedIn app says it, and is kept
    as it comes: it is the answer to the question.
    """
    if not referrer:
        return ""
    host = (urlparse(referrer).hostname or "").lower().removeprefix("www.")
    if not host or host == own or host.endswith("." + own):
        return ""
    return host


def campaign_of(query: str) -> str:
    """`utm_source`, and `/utm_campaign` after it when there is one."""
    asked = parse_qs(query)
    source = (asked.get("utm_source") or [""])[0].strip().lower()[:40]
    if not source:
        return ""
    campaign = (asked.get("utm_campaign") or [""])[0].strip().lower()[:40]
    return f"{source}/{campaign}" if campaign else source


def count(
    requests: Iterable[Request],
    own: str,
    country: Callable[[str], str] | None = None,
    covered_from: datetime | None = None,
) -> dict[str, Tally]:
    """Every day the requests fall on, counted. Nobody is kept past the return.

    `covered_from` is the earliest moment the log was read from, when the caller knows
    it is earlier than the first request counted; a day is whole if that is before it.
    """
    days: dict[str, Tally] = {}
    seen: dict[str, set[tuple[str, str]]] = {}
    counters: dict[str, dict[str, Counter[str]]] = {}
    first = covered_from
    for one in requests:
        first = one.at if first is None or one.at < first else first
        day = one.at.date().isoformat()
        tally = days.setdefault(day, Tally(day=day))
        tally.views += 1
        by_kind = counters.setdefault(day, {kind: Counter() for kind in KINDS})
        by_kind["page"][page_of(one.path)] += 1
        sent = referrer_of(one.referrer, own)
        if sent:
            by_kind["referrer"][sent] += 1
        visitors = seen.setdefault(day, set())
        if one.visitor in visitors:
            continue
        visitors.add(one.visitor)
        campaign = campaign_of(one.query)
        if campaign:
            by_kind["campaign"][campaign] += 1
        if country is not None:
            where = country(one.address)
            if where:
                by_kind["country"][where] += 1
    for day, tally in days.items():
        tally.visitors = len(seen.get(day, ()))
        tally.whole = first is not None and first.date().isoformat() < day
        tally.counts = {kind: dict(counter) for kind, counter in counters[day].items()}
    return days


def log_files(log: Path) -> list[Path]:
    """The live log and every rotated one beside it, oldest first."""
    rotated = sorted(log.parent.glob(f"{log.stem}-*{log.suffix}*"), key=lambda p: p.stat().st_mtime)
    return [*rotated, *([log] if log.exists() else [])]


def lines(files: Iterable[Path], since: datetime | None = None) -> Iterator[str]:
    """Every line of every file that could hold something at or after `since`.

    A rotated file's modification time is its last line's, so one that stopped before
    `since` holds nothing wanted and is not opened at all.
    """
    for path in files:
        if since is not None and datetime.fromtimestamp(path.stat().st_mtime, UTC) < since:
            continue
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8", errors="replace") as packed:
                yield from packed
        else:
            with path.open(encoding="utf-8", errors="replace") as handle:
                yield from handle


SCHEMA = """
CREATE TABLE IF NOT EXISTS visit_day (
    day TEXT PRIMARY KEY,
    views INTEGER NOT NULL,
    visitors INTEGER NOT NULL,
    whole INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS visit_count (
    day TEXT NOT NULL,
    kind TEXT NOT NULL,
    key TEXT NOT NULL,
    n INTEGER NOT NULL,
    PRIMARY KEY (day, kind, key)
);
"""


def open_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db


def resume_from(db: sqlite3.Connection) -> datetime | None:
    """Where the next pass starts: the day before the newest one kept.

    The newest day is still being written, and the one before it may have been cut off
    by the last pass in its final hour. Everything older is settled and is not read again.
    """
    row = db.execute("SELECT MAX(day) FROM visit_day").fetchone()
    if not row or not row[0]:
        return None
    start = date.fromisoformat(str(row[0])) - timedelta(days=1)
    return datetime.combine(start, datetime.min.time(), UTC)


def keep(db: sqlite3.Connection, days: dict[str, Tally]) -> int:
    """Write the counted days, each replacing what was there.

    Except that a day counted from part of itself never replaces the same day counted
    whole — which is what a pass sees once the log has rotated the day's start away.
    """
    kept = 0
    with db:
        for day, tally in sorted(days.items()):
            before = db.execute("SELECT whole FROM visit_day WHERE day = ?", (day,)).fetchone()
            if before and before[0] and not tally.whole:
                continue
            db.execute(
                "INSERT OR REPLACE INTO visit_day (day, views, visitors, whole)"
                " VALUES (?, ?, ?, ?)",
                (day, tally.views, tally.visitors, int(tally.whole)),
            )
            db.execute("DELETE FROM visit_count WHERE day = ?", (day,))
            db.executemany(
                "INSERT INTO visit_count (day, kind, key, n) VALUES (?, ?, ?, ?)",
                [
                    (day, kind, key, n)
                    for kind, counted in tally.counts.items()
                    for key, n in counted.items()
                ],
            )
            kept += 1
    return kept


def roll_up(
    into: Path,
    log: Path = LOG,
    own: str = "targum.page",
    country: Callable[[str], str] | None = None,
) -> int:
    """Count what the log holds since the last pass, and keep it. Returns days written."""
    db = open_db(into)
    try:
        since = resume_from(db)
        read = [one for one in map(parse, lines(log_files(log), since)) if one is not None]
        # A rotated file that straddles `since` is read whole, which is how the pass knows
        # the log reaches back past the start of its first day. Its lines before `since`
        # belong to days already kept whole, and are not counted again.
        earliest = min((one.at for one in read), default=None)
        wanted = [one for one in read if since is None or one.at >= since]
        return keep(db, count(wanted, own.lower().removeprefix("www."), country, earliest))
    finally:
        db.close()


# -- Countries -------------------------------------------------------------------------


def geoip_path(beside: Path) -> Path:
    return beside / GEOIP_FILE


def geoip_stale(path: Path, now: datetime | None = None) -> bool:
    if not path.exists():
        return True
    age = (now or datetime.now(UTC)) - datetime.fromtimestamp(path.stat().st_mtime, UTC)
    return age > GEOIP_STALE


def fetch_geoip(path: Path, today: date | None = None) -> str:
    """This month's file, or last month's if this month's is not out yet. The month got."""
    now = today or datetime.now(UTC).date()
    last = (now.replace(day=1) - timedelta(days=1)).replace(day=1)
    failed = ""
    for month in (now.strftime("%Y-%m"), last.strftime("%Y-%m")):
        try:
            # Named, because DB-IP's Cloudflare answers Python's default agent with 403.
            asked = urllib.request.Request(
                GEOIP_SOURCE.format(month=month),
                headers={"User-Agent": "targum (+https://targum.page)"},
            )
            with urllib.request.urlopen(asked, timeout=120) as answer:
                body = gzip.decompress(answer.read())
        except OSError as error:
            failed = str(error)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            temporary.write_bytes(body)
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
        return month
    raise TargumError("Could not download DB-IP's country file.", failed)


def country_reader(path: Path) -> Callable[[str], str] | None:
    """A lookup from address to country name, or None without the file.

    None rather than a function answering "" so that the caller can tell "no countries
    because nobody came from anywhere" from "no countries because there is no map".
    """
    if not path.exists():
        return None
    import maxminddb

    reader = maxminddb.open_database(str(path))

    def country(address: str) -> str:
        try:
            found = reader.get(address)
        except ValueError:
            return ""
        if not isinstance(found, dict):
            return ""
        place = found.get("country") or {}
        if not isinstance(place, dict):
            return ""
        names = place.get("names") or {}
        name = names.get("en") if isinstance(names, dict) else ""
        return str(name or place.get("iso_code") or "")

    return country


# -- The page's view -------------------------------------------------------------------


@dataclass
class Visits:
    """What the back office shows: a line a day and the leading rows of each tally."""

    days: list[Tally] = field(default_factory=list)
    #: kind -> [(key, total over the window)], most first.
    top: dict[str, list[tuple[str, int]]] = field(default_factory=dict)
    views: int = 0
    #: The sum of each day's visitors. Not distinct over the window, and cannot be: a
    #: visitor is only ever recognised within the day they came.
    visitor_days: int = 0
    has_countries: bool = False

    def any(self) -> bool:
        return self.views > 0


def survey(path: Path, today: date | None = None, days: int = 30, rows: int = 10) -> Visits:
    """The last `days` days, read-only. Empty where the roll-up has never run."""
    found = Visits()
    if not path.exists():
        return found
    now = today or datetime.now(UTC).date()
    window = [(now - timedelta(days=n)).isoformat() for n in range(days)]
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        by_day = {
            str(day): Tally(
                day=str(day), views=int(views), visitors=int(visitors), whole=bool(whole)
            )
            for day, views, visitors, whole in db.execute(
                "SELECT day, views, visitors, whole FROM visit_day WHERE day >= ?", (window[-1],)
            )
        }
        for kind in KINDS:
            found.top[kind] = [
                (str(key), int(n))
                for key, n in db.execute(
                    "SELECT key, SUM(n) AS total FROM visit_count WHERE kind = ? AND day >= ?"
                    " GROUP BY key ORDER BY total DESC, key LIMIT ?",
                    (kind, window[-1], rows),
                )
            ]
    except sqlite3.Error:
        return found
    finally:
        db.close()
    found.days = [by_day.get(day, Tally(day=day)) for day in window]
    found.views = sum(day.views for day in found.days)
    found.visitor_days = sum(day.visitors for day in found.days)
    found.has_countries = bool(found.top.get("country"))
    return found
