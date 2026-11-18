"""The back office at five thousand accounts (targum-internal#542).

Paged, searchable and sortable lists; per-row figures for the page alone; summaries
counted in the store; and the indexes that keep each of those from reading every row.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import time
from datetime import date
from pathlib import Path

import pytest

from targum.accounts import Store
from targum.backoffice import (
    ACCOUNT_ORDERS,
    ACCOUNT_SEARCH,
    ACCOUNT_SORTS,
    NOT_MINE,
    PER_PAGE,
    WAITING_SEARCH,
    WAITING_SORTS,
    Listing,
    bare,
    survey,
    survey_store,
)
from targum.render.builder import back_office_page

TODAY = date(2026, 10, 27)
DAY_MS = 24 * 60 * 60 * 1000


def stamp(when: date) -> int:
    return int(dt.datetime.combine(when, dt.time(12, 0), dt.UTC).timestamp() * 1000)


def accounts(**asked: str) -> Listing:
    """A listing as the readers page reads it: `q=` here is the address's `bq=`."""
    query = {(ACCOUNT_SEARCH if k == "q" else k): [v] for k, v in asked.items()}
    return Listing.read(query, ACCOUNT_SEARCH, "sort", "page", ACCOUNT_SORTS)


@pytest.fixture
def five_hundred(tmp_path: Path) -> sqlite3.Connection:
    """500 accounts, one made each day back from today, account n keeping n % 7 words;
    and 120 waiting, of whom the first 60 have been let in."""
    store = Store(tmp_path / "targum.db")
    db = store.db
    start = stamp(TODAY)
    db.execute("BEGIN")  # the store writes each statement on its own otherwise
    db.executemany(
        "INSERT INTO person (id, email, name, made) VALUES (?, ?, ?, ?)",
        [
            (n, f"reader{n:03d}@example.com", "Dina" if n == 250 else "", start - n * DAY_MS)
            for n in range(1, 501)
        ],
    )
    db.executemany(
        "INSERT INTO word (person, language, lemma, at) VALUES (?, 'he', ?, ?)",
        [(n, f"w{k}", start - k * DAY_MS) for n in range(1, 501) for k in range(n % 7)],
    )
    db.executemany(
        "INSERT INTO waiting (email, state, stop, asked, invited) VALUES (?, 'on', 's', ?, ?)",
        [
            (f"waiting{n:03d}@example.com", start - (200 - n) * 1000, 1 if n < 60 else 0)
            for n in range(120)
        ],
    )
    db.execute("COMMIT")
    return db


def test_accounts_are_drawn_fifty_at_a_time_newest_first(five_hundred: sqlite3.Connection) -> None:
    found = survey(five_hundred, today=TODAY)
    assert len(found.accounts) == PER_PAGE == 50
    assert found.accounts_total == 500
    assert found.accounts[0].email == "reader001@example.com", "newest first"
    listing = found.account_listing
    assert (listing.matches, listing.pages(), listing.first_row(), listing.last_row()) == (
        500,
        10,
        1,
        50,
    )

    second = survey(five_hundred, today=TODAY, accounts=accounts(page="2"))
    assert second.accounts[0].email == "reader051@example.com"
    # The Readers page draws its own table (`readers`); see test_backoffice_readers.py.

    # A page past the end is the last page, not an empty one.
    past = survey(five_hundred, today=TODAY, accounts=accounts(page="99"))
    assert past.account_listing.page == 10 and len(past.accounts) == 50


def test_per_row_figures_are_counted_for_the_page_alone(five_hundred: sqlite3.Connection) -> None:
    found = survey(five_hundred, today=TODAY)
    on_page = {who.id for who in found.accounts}
    for day in found.days:
        assert set(day.words) <= on_page, "the strip draws the page's accounts only"
    by_id = {who.id: who for who in found.accounts}
    assert by_id[6].words == 6 and by_id[7].words == 0
    # But the window's activity is counted over everybody.
    assert found.active_count > len([who for who in found.accounts if who.words])


def test_accounts_are_searched_by_address_or_name(five_hundred: sqlite3.Connection) -> None:
    found = survey(five_hundred, today=TODAY, accounts=accounts(q="READER12"))
    assert {who.email for who in found.accounts} == {
        f"reader{n}@example.com" for n in range(120, 130)
    }
    assert found.account_listing.matches == 10
    named = survey(five_hundred, today=TODAY, accounts=accounts(q="dina"))
    assert [who.email for who in named.accounts] == ["reader250@example.com"]
    # The search's own wildcards are only characters.
    assert survey(five_hundred, today=TODAY, accounts=accounts(q="%")).accounts == []


def test_accounts_sort_by_what_is_asked(five_hundred: sqlite3.Connection) -> None:
    most = survey(five_hundred, today=TODAY, accounts=accounts(sort="words"))
    assert [who.words for who in most.accounts[:3]] == [6, 6, 6]
    assert most.accounts[0].id == 496, "ties fall to the newest id"
    active = survey(five_hundred, today=TODAY, accounts=accounts(sort="active"))
    assert active.accounts[0].last_active == TODAY.isoformat()
    assert all(
        a.last_active >= b.last_active
        for a, b in zip(active.accounts, active.accounts[1:], strict=False)
        if b.last_active
    )
    for sort in ACCOUNT_SORTS:
        assert len(survey(five_hundred, today=TODAY, accounts=accounts(sort=sort)).accounts) == 50


def test_the_address_is_read_and_anything_odd_is_the_default() -> None:
    read = accounts(q="  a   b  ", sort="sideways", page="-3")
    assert (read.q, read.sort, read.page) == ("a b", "joined", 1)
    assert accounts(page="two").page == 1
    assert len(accounts(q="x" * 500).q) == 100
    waiting = Listing.read({"wsort": ["newest"]}, WAITING_SEARCH, "wsort", "wpage", WAITING_SORTS)
    assert waiting.sort == "newest"


def test_the_waitlist_pages_its_two_lists_apart(five_hundred: sqlite3.Connection) -> None:
    found = survey(five_hundred, today=TODAY)
    still = [who for who in found.waiting_list if not who.invited]
    done = [who for who in found.waiting_list if who.invited]
    assert len(still) == 50 and len(done) == 50
    assert still[0].email == "waiting060@example.com", "oldest first, the order they are let in"
    assert found.waiting_listing.matches == 60 and found.let_in_listing.matches == 60
    assert found.waiting_let_in == 60
    page = back_office_page(found, 30, section="waitlist")
    assert "Let in (60)" in page and "60 let in" in page
    assert 'href="/back-office/waitlist?wpage=2"' in page
    assert 'href="/back-office/waitlist?ipage=2"' in page

    # Each list is on its own page now, so a link carries its own list's settings only.
    later = survey(
        five_hundred,
        today=TODAY,
        accounts=accounts(q="reader1", page="2"),
        waitlist=Listing(q="waiting", sort="oldest", page=2),
    )
    drawn = back_office_page(later, 30, section="waitlist")
    assert 'rel="prev" href="/back-office/waitlist?bwq=waiting"' in drawn
    assert "reader1" not in drawn and 'name="q"' not in drawn and 'name="wq"' not in drawn

    searched = survey(
        five_hundred,
        today=TODAY,
        waitlist=Listing(q="waiting00", sort="oldest"),
        let_in=Listing(q="waiting00", sort="oldest"),
    )
    assert {who.email for who in searched.waiting_list} == {
        f"waiting00{n}@example.com" for n in range(10)
    }
    folded = back_office_page(searched, 30, section="waitlist")
    assert '<details class="let-in" open>' in folded, "the only rows found are let in"
    assert "Let in (10)" in folded


def test_the_new_indexes_are_used(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    db = store.db
    db.create_function("bare", 1, bare, deterministic=True)
    mine = {"mine": json.dumps([])}

    def plan(sql: str, args: dict[str, object] | None = None) -> str:
        return " ".join(str(row[-1]) for row in db.execute("EXPLAIN QUERY PLAN " + sql, args or {}))

    assert "person_made" in plan(
        f"SELECT p.id FROM person p WHERE {NOT_MINE.format(column='p.email')}"
        f" ORDER BY {ACCOUNT_ORDERS['joined']} LIMIT 50",
        mine,
    )
    assert "waiting_asked" in plan(
        f"SELECT * FROM waiting WHERE {NOT_MINE.format(column='email')} AND invited = 0"
        " ORDER BY asked, rowid LIMIT 50",
        mine,
    )
    assert "job_owner" in plan("SELECT COUNT(*) FROM job WHERE owner = 3")
    assert "job_made" in plan("SELECT stage FROM job WHERE kind = 'build' AND made >= 5")
    assert "event_kind" in plan("SELECT COUNT(DISTINCT person) FROM event WHERE kind = 'lookup'")


def test_five_thousand_accounts_draw_in_time(tmp_path: Path) -> None:
    """5,000 accounts and 200,000 words, the page drawn under its budget. Every row read
    into Python on each load was the page before; this is what it must not go back to."""
    path = tmp_path / "targum.db"
    store = Store(path)
    db = store.db
    start = stamp(TODAY)
    db.execute("BEGIN")  # the store writes each statement on its own otherwise
    db.executemany(
        "INSERT INTO person (id, email, made) VALUES (?, ?, ?)",
        [(n, f"r{n}@example.com", start - (n % 400) * DAY_MS) for n in range(1, 5001)],
    )
    db.executemany(
        "INSERT INTO word (person, language, lemma, at) VALUES (?, 'he', ?, ?)",
        [(n, f"w{k}", start - ((n + k) % 90) * DAY_MS) for n in range(1, 5001) for k in range(40)],
    )
    db.executemany(
        "INSERT INTO doc (person, hash, opened, updated) VALUES (?, ?, ?, ?)",
        [
            (n, f"h{k}", start - k * DAY_MS, start - k * DAY_MS)
            for n in range(1, 5001)
            for k in range(3)
        ],
    )
    db.executemany(
        "INSERT INTO invited (email, at) VALUES (?, ?)",
        [(f"r{n}@example.com", start - (n % 400) * DAY_MS) for n in range(1, 5001)],
    )
    db.execute("COMMIT")
    store.close()

    began = time.perf_counter()
    found = survey_store(path, today=TODAY, operators=())
    page = back_office_page(found, 30)
    took = time.perf_counter() - began
    assert found.accounts_total == 5000 and len(found.accounts) == 50
    assert found.readers == 5000
    assert len(found.follow_up) <= 50
    assert page.count("<tr") < 600, "the page draws its fifty, not five thousand"
    assert took < 5.0, f"the back office took {took:.2f}s over 5,000 accounts"
