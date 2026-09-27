"""Visitors, counted off the access log: what counts as a visit, and what is never kept."""

from __future__ import annotations

import gzip
import json
import os
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from targum import visits
from targum.backoffice import Survey
from targum.render.builder import back_office_page

BROWSER = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 Safari/605.1.15"
PHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile"


def line(
    when: datetime,
    uri: str = "/",
    ip: str = "203.0.113.5",
    agent: str = BROWSER,
    referrer: str = "",
    status: int = 200,
    kind: str = "text/html; charset=utf-8",
    method: str = "GET",
) -> str:
    """One line as Caddy's JSON access log writes it."""
    headers = {"User-Agent": [agent]} if agent else {}
    if referrer:
        headers["Referer"] = [referrer]
    return json.dumps(
        {
            "level": "info",
            "ts": when.timestamp(),
            "logger": "http.log.access.log0",
            "msg": "handled request",
            "request": {
                "remote_ip": ip,
                "client_ip": ip,
                "method": method,
                "host": "targum.page",
                "uri": uri,
                "headers": headers,
            },
            "status": status,
            "resp_headers": {"Content-Type": [kind]},
        }
    )


def at(day: int, hour: int = 12) -> datetime:
    return datetime(2026, 9, day, hour, 0, tzinfo=UTC)


def test_only_a_person_opening_a_page_is_a_visit() -> None:
    assert visits.parse(line(at(20))) is not None
    assert visits.parse(line(at(20), kind="text/css")) is None, "a stylesheet"
    assert visits.parse(line(at(20), status=404)) is None, "a scanner's miss"
    assert visits.parse(line(at(20), status=303)) is None, "a redirect"
    assert visits.parse(line(at(20), method="POST")) is None
    assert visits.parse(line(at(20), agent="")) is None, "says nothing about itself"
    assert visits.parse(line(at(20), agent="Googlebot/2.1")) is None
    assert visits.parse(line(at(20), agent="facebookexternalhit/1.1")) is None
    assert visits.parse(line(at(20), uri="/back-office")) is None, "the operator"
    assert visits.parse("not json") is None


def test_identifiers_fold_so_texts_are_one_row() -> None:
    assert visits.page_of("/r/3fa9c2b18d7e") == "/r/…"
    assert visits.page_of("/") == "/"
    assert visits.page_of("/connect") == "/connect"


def test_referrers_are_other_sites_only() -> None:
    assert visits.referrer_of("https://www.linkedin.com/feed/", "targum.page") == "linkedin.com"
    assert visits.referrer_of("https://targum.page/connect", "targum.page") == ""
    assert visits.referrer_of("android-app://com.linkedin.android/", "targum.page") == (
        "com.linkedin.android"
    )
    assert visits.referrer_of("", "targum.page") == ""


def test_campaign_is_the_utm_source() -> None:
    assert visits.campaign_of("utm_source=LinkedIn") == "linkedin"
    assert visits.campaign_of("utm_source=x&utm_campaign=launch") == "x/launch"
    assert visits.campaign_of("lang=ru") == ""


def test_a_visitor_is_counted_once_a_day() -> None:
    read = [
        visits.parse(line(at(20, 9), uri="/?utm_source=x", referrer="https://t.co/abc")),
        visits.parse(line(at(20, 10), uri="/connect")),
        visits.parse(line(at(20, 11), ip="198.51.100.7", agent=PHONE)),
        visits.parse(line(at(21, 9))),
    ]
    days = visits.count([one for one in read if one], "targum.page", country=lambda ip: "Israel")
    first = days["2026-09-20"]
    assert (first.views, first.visitors) == (3, 2)
    assert first.counts["page"] == {"/": 2, "/connect": 1}
    assert first.counts["referrer"] == {"t.co": 1}
    assert first.counts["campaign"] == {"x": 1}
    assert first.counts["country"] == {"Israel": 2}, "countries are counted in visitors"
    assert not first.whole, "the log starts inside it"
    assert days["2026-09-21"].whole
    assert days["2026-09-21"].visitors == 1, "the same person the next day is not recognised"


def write_log(path: Path, lines: list[str], packed: bool = False) -> Path:
    body = "\n".join(lines) + "\n"
    if packed:
        path.write_bytes(gzip.compress(body.encode()))
    else:
        path.write_text(body)
    return path


def test_the_roll_up_keeps_counts_and_no_addresses(tmp_path: Path) -> None:
    logs = tmp_path / "caddy"
    logs.mkdir()
    old = write_log(
        logs / "targum-2026-09-21T00-00-00.000.log.gz",
        [line(at(20, 9)), line(at(20, 23)), line(at(21, 0))],
        packed=True,
    )
    os.utime(old, (at(21, 0).timestamp(),) * 2)
    live = write_log(logs / "targum.log", [line(at(21, 8), ip="198.51.100.7", agent=PHONE)])
    into = tmp_path / "visits.sqlite"

    assert visits.roll_up(into, log=live) == 2
    db = sqlite3.connect(into)
    rows = dict(
        (day, (views, visitors, whole))
        for day, views, visitors, whole in db.execute("SELECT * FROM visit_day")
    )
    assert rows == {"2026-09-20": (2, 1, 0), "2026-09-21": (2, 2, 1)}
    dumped = "\n".join(db.iterdump())
    assert "203.0.113.5" not in dumped and "198.51.100.7" not in dumped
    assert "Mozilla" not in dumped
    db.close()

    # The next pass starts the day before the newest, so both are counted again, and
    # the 21st picks up what the live log gained since.
    write_log(
        live,
        [line(at(21, 8), ip="198.51.100.7", agent=PHONE), line(at(21, 9), ip="192.0.2.1")],
    )
    assert visits.roll_up(into, log=live) == 2
    found = visits.survey(into, today=date(2026, 9, 21), days=3)
    assert [(day.day, day.visitors) for day in found.days] == [
        ("2026-09-21", 3),
        ("2026-09-20", 1),
        ("2026-09-19", 0),
    ]


def test_a_part_of_a_day_never_replaces_the_whole(tmp_path: Path) -> None:
    db = visits.open_db(tmp_path / "visits.sqlite")
    whole = visits.Tally(day="2026-09-20", views=10, visitors=4, whole=True)
    visits.keep(db, {"2026-09-20": whole})
    part = visits.Tally(day="2026-09-20", views=1, visitors=1, whole=False)
    assert visits.keep(db, {"2026-09-20": part}) == 0
    assert db.execute("SELECT views FROM visit_day").fetchone() == (10,)


def test_no_country_file_is_no_countries_and_still_counts(tmp_path: Path) -> None:
    assert visits.country_reader(tmp_path / "missing.mmdb") is None
    assert visits.geoip_stale(tmp_path / "missing.mmdb")


def test_the_country_file_is_this_month_or_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    asked: list[str] = []

    class Answer:
        def __enter__(self) -> Answer:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def read(self) -> bytes:
            return gzip.compress(b"mmdb")

    def urlopen(request: visits.urllib.request.Request, timeout: int) -> Answer:
        url = request.full_url
        assert request.get_header("User-agent"), "DB-IP refuses Python's default agent"
        asked.append(url)
        if "2026-10" in url:
            raise OSError("404")
        return Answer()

    monkeypatch.setattr(visits.urllib.request, "urlopen", urlopen)
    where = tmp_path / visits.GEOIP_FILE
    assert visits.fetch_geoip(where, today=date(2026, 10, 1)) == "2026-09"
    assert where.read_bytes() == b"mmdb"
    assert len(asked) == 2


def test_the_back_office_shows_visitors(tmp_path: Path) -> None:
    db = visits.open_db(tmp_path / "visits.sqlite")
    visits.keep(
        db,
        {
            "2026-09-20": visits.Tally(
                day="2026-09-20",
                views=7,
                visitors=3,
                whole=True,
                counts={
                    "page": {"/": 7},
                    "referrer": {"linkedin.com": 2},
                    "country": {"Israel": 3},
                },
            )
        },
    )
    db.close()
    found = visits.survey(tmp_path / "visits.sqlite", today=date(2026, 9, 21))
    page = back_office_page(Survey(), 30, visits=found)
    assert "Visitors" in page
    assert "linkedin.com" in page and "Israel" in page
    assert "IP Geolocation by DB-IP" in page, "CC BY asks for the credit where it is shown"
    assert 'style="' not in page, "the policy admits no style attribute"


def test_the_back_office_without_a_roll_up(tmp_path: Path) -> None:
    found = visits.survey(tmp_path / "nothing.sqlite")
    assert not found.any()
    page = back_office_page(Survey(), 30, visits=found)
    assert "Nothing counted yet" in page
