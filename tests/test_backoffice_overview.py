"""The back office's overview (design.md §12, 2026-11-17): who is active and new, each
figure against yesterday and the same day last week; the funnel to days 8–14; and the
box's spend, summed as `Store.claim` sums it."""

from __future__ import annotations

import datetime as dt
import sqlite3
import time
from datetime import date
from pathlib import Path

import pytest

from targum.accounts import Store
from targum.backoffice import (
    NEAR_THE_RAIL,
    Survey,
    box_spent,
    overview,
    overview_store,
    survey,
)
from targum.render.builder import back_office_page

DAY_MS = 24 * 60 * 60 * 1000
TODAY = date(2026, 11, 18)  # a Wednesday


def noon(when: date) -> int:
    return int(dt.datetime.combine(when, dt.time(12, 0), dt.UTC).timestamp() * 1000)


AT = noon(TODAY) + 60 * 60 * 1000  # 13:00 UTC today


def ago(days: int) -> date:
    return TODAY - dt.timedelta(days=days)


@pytest.fixture
def store(tmp_path: Path) -> Store:
    """Four readers and three staff, each doing something on chosen days.

    - 1 saves a word today and yesterday, and a day row eight days ago.
    - 2 opens a text yesterday, and seven days ago.
    - 3 updates a text today, and was made today.
    - 4 marks a day 20 days ago and nothing since, and was made eight days ago.
    - 5, 6 and 7 are the operator, an admin and a test account, active every day.
    """
    kept = Store(tmp_path / "targum.db")
    db = kept.db
    db.execute("BEGIN")
    for n, email, made in (
        (1, "one@example.com", ago(60)),
        (2, "two@example.com", ago(40)),
        (3, "three@example.com", TODAY),
        (4, "four@example.com", ago(8)),
        (5, "operator@gmail.com", TODAY),
        (6, "boss@example.com", TODAY),
        (7, "tester@example.com", TODAY),
    ):
        db.execute("INSERT INTO person (id, email, made) VALUES (?, ?, ?)", (n, email, noon(made)))
    db.execute("INSERT INTO admin (email, at) VALUES ('boss@example.com', 1)")
    db.execute("INSERT INTO test_account (email, at) VALUES ('tester@example.com', 1)")
    for person, when in ((1, TODAY), (1, ago(1))):
        db.execute(
            "INSERT INTO word (person, language, lemma, at) VALUES (?, 'he', ?, ?)",
            (person, f"x{when}", noon(when) - 1000 * person),
        )
    db.execute("INSERT INTO day (person, day, count) VALUES (1, ?, 1)", (ago(8).isoformat(),))
    db.execute("INSERT INTO day (person, day, count) VALUES (4, ?, 1)", (ago(20).isoformat(),))
    db.execute(
        "INSERT INTO doc (person, hash, opened, updated) VALUES (2, 'a', ?, ?)",
        (noon(ago(1)), noon(ago(1))),
    )
    db.execute(
        "INSERT INTO doc (person, hash, opened, updated) VALUES (2, 'b', ?, ?)",
        (noon(ago(7)), noon(ago(7))),
    )
    db.execute(
        "INSERT INTO doc (person, hash, opened, updated) VALUES (3, 'c', ?, ?)",
        (noon(ago(3)), noon(TODAY)),
    )
    for staff in (5, 6, 7):
        for n in range(40):
            db.execute(
                "INSERT INTO day (person, day, count) VALUES (?, ?, 1)",
                (staff, ago(n).isoformat()),
            )
    db.execute("COMMIT")
    return kept


def job(
    store: Store,
    name: str,
    owner: int,
    made: int,
    claimed: float,
    spent: float = 0.0,
    kind: str = "build",
    length: float = 0.0,
    gift: int = 0,
    seconds: float = 0.0,
) -> None:
    store.db.execute(
        "INSERT INTO job (id, owner, home, source, kind, made, claimed, spent, length, gift,"
        " seconds) VALUES (?, ?, 'h', 's', ?, ?, ?, ?, ?, ?, ?)",
        (name, owner, kind, made, claimed, spent, length, gift, seconds),
    )
    store.db.commit()


def test_active_is_counted_against_yesterday_and_last_week(store: Store) -> None:
    found = overview(store.db, AT, operators=["operator@gmail.com"])
    # Today: 1 (word) and 3 (updated). Yesterday: 1 and 2. Seven days ago: 2.
    assert (found.active_today.now, found.active_today.yesterday) == (2, 2)
    assert found.active_today.last_week == 1
    assert found.active_today.against_yesterday() == 0
    assert found.active_today.against_last_week() == 1
    # Seven days to today: 1, 2, 3. To yesterday: the same, 3 having opened its text three
    # days ago. To a week ago (ago 13..7): 1 (a day row eight days ago) and 2.
    assert (found.active_week.now, found.active_week.yesterday) == (3, 3)
    assert found.active_week.last_week == 2
    # Thirty days: everybody but staff, and 4's day twenty days ago.
    assert found.active_month.now == 4
    assert dict(found.active_days)[TODAY.isoformat()] == 2
    assert dict(found.active_days)[ago(20).isoformat()] == 1
    assert len(found.active_days) == 30 and found.active_days[-1][0] == TODAY.isoformat()
    assert found.weekday == "Wed"


def test_staff_are_counted_nowhere_but_the_box_s_spend(store: Store) -> None:
    job(store, "r", 1, AT - 1000, claimed=1.0, spent=1.0, length=600)
    job(store, "s", 6, AT - 1000, claimed=9.0, spent=9.0, length=6000)
    found = overview(store.db, AT, operators=["operator@gmail.com"])
    assert found.active_month.now == 4, "the operator, admin and test account are not readers"
    assert found.new_today.now == 1, "3 is new today; the three staff made today are not"
    assert dict(found.credits_by_kind)["build"] == 600
    assert found.near_rail == []
    # But the box's spend is the box's, whoever spent it, as `claim` holds it.
    assert found.spent_today.now == 10.0


def test_new_accounts_by_day_and_week(store: Store) -> None:
    found = overview(store.db, AT, operators=["operator@gmail.com"])
    assert (found.new_today.now, found.new_today.yesterday, found.new_today.last_week) == (1, 0, 0)
    # Seven days to today: 3. To a week ago: 4, made eight days ago.
    assert (found.new_week.now, found.new_week.last_week) == (1, 1)
    weeks = dict(found.new_weeks)
    assert len(found.new_weeks) == 12
    monday = TODAY - dt.timedelta(days=TODAY.weekday())
    assert weeks[monday.isoformat()] == 1
    assert weeks[(monday - dt.timedelta(weeks=1)).isoformat()] == 1


def test_the_days_spend_is_the_sum_claim_holds_to_the_ceiling(store: Store) -> None:
    """The overview's "today" is `claim`'s rolling day, read and never written: the same
    rows and the same sum as `Store.committed`, which is the read `claim` makes."""
    job(store, "now", 1, AT - 60_000, claimed=2.5, spent=2.0)
    job(store, "edge", 2, AT - DAY_MS, claimed=1.25, spent=1.0)  # on the window's edge
    job(store, "before", 2, AT - DAY_MS - 1, claimed=4.0, spent=4.0)
    job(store, "lastweek", 2, AT - 7 * DAY_MS - 1000, claimed=3.0, spent=3.0)
    job(store, "free", 2, AT - 1000, claimed=0.0, spent=0.0)
    found = overview(store.db, AT, ceiling=40.0, rail=10.0)
    since = AT - DAY_MS
    assert found.spent_today.now == store.committed(since) == box_spent(store.db, since) == 3.75
    assert found.spent_today.yesterday == 4.0
    assert found.spent_today.last_week == 3.0
    assert found.ceiling == 40.0
    # The month: every day from the first, each day's settled spend.
    assert found.month_days[0][0] == "2026-11-01" and found.month_days[-1][0] == "2026-11-18"
    assert found.spent_month == pytest.approx(10.0)


def test_a_reader_near_their_days_rail_is_named_and_linked(store: Store) -> None:
    job(store, "a", 2, AT - 1000, claimed=10.0 * NEAR_THE_RAIL)
    job(store, "b", 1, AT - 1000, claimed=6.99)
    job(store, "c", 6, AT - 1000, claimed=9.5)  # an admin: past the rails by design
    found = overview(store.db, AT, rail=10.0)
    assert found.near_rail == [(2, "two@example.com", 7.0)]
    page = back_office_page(Survey(), 30, overview=found)
    assert '<a href="/back-office/readers/2">two@example.com</a>' in page
    assert "over $7 of their $10 a day" in page


def test_credits_by_kind_count_a_gift_at_its_quote(store: Store) -> None:
    job(store, "b", 1, AT - 1000, 0.1, length=1200)
    job(store, "g", 1, AT - 1000, 0.1, gift=1, seconds=900)
    job(store, "c", 2, AT - 1000, 0.1, kind="chat", length=95)
    job(
        store,
        "old",
        2,
        dt.datetime(2026, 10, 30, tzinfo=dt.UTC).timestamp() * 1000,
        0.1,
        length=999,
    )
    found = overview(store.db, AT)
    kinds = dict(found.credits_by_kind)
    assert (kinds["build"], kinds["gift"], kinds["chat"]) == (1200, 900, 95)
    assert list(kinds)[:5] == ["build", "subscription", "voice", "chat", "gift"]
    page = back_office_page(Survey(), 30, overview=found)
    assert ">95 s<" in page and ">20<" in page


def test_the_funnel_ends_on_days_eight_to_fourteen(tmp_path: Path) -> None:
    kept = Store(tmp_path / "targum.db")
    db = kept.db
    let = TODAY - dt.timedelta(days=20)
    for n, back in ((1, 10), (2, 3), (3, None)):
        email = f"r{n}@example.com"
        db.execute("INSERT INTO invited (email, at) VALUES (?, ?)", (email, noon(let)))
        db.execute("INSERT INTO person (id, email, made) VALUES (?, ?, ?)", (n, email, noon(let)))
        db.execute(
            "INSERT INTO doc (person, hash, opened, updated) VALUES (?, 'a', ?, ?)",
            (n, noon(let), noon(let)),
        )
        if back is not None:
            when = (let + dt.timedelta(days=back)).isoformat()
            db.execute("INSERT INTO day (person, day, count) VALUES (?, ?, 1)", (n, when))
    db.commit()
    found = survey(db, today=TODAY)
    week = found.batches[0]
    assert (week.let_in, week.signed_in, week.opened) == (3, 3, 3)
    assert (week.week_two, week.week_two_over) == (1, 3), "only the one back on day 10"
    page = back_office_page(found, 30, overview=overview(db, AT))
    funnel = page[page.index("Funnel") : page.index("Spend")]
    assert ">1 of 3<" in funnel and ">3 of 3<" in funnel
    young = survey(db, today=let + dt.timedelta(days=10))
    assert young.batches[0].week_two_over == 0
    assert "too soon" in back_office_page(young, 30, overview=overview(db, AT))


def test_the_overview_draws_each_row_with_its_comparisons(store: Store) -> None:
    found = overview(store.db, AT, operators=["operator@gmail.com"], ceiling=40.0, rail=10.0)
    page = back_office_page(Survey(follow_up_total=3), 30, overview=found)
    for head in ("Needs doing", "Active", "Funnel", "Spend"):
        assert f'<h2 class="row-head">{head}</h2>' in page
    assert 'href="#follow"' in page and 'href="#told"' in page
    assert 'href="/back-office/operations#faults"' in page
    assert 'href="/back-office/operations#incidents"' in page
    assert "±0 vs yesterday &middot; +1 vs last Wed" in page
    assert "of $40 in the last 24 hours" in page
    assert page.count('<svg class="days"') == 3, "active days, new weeks, the month's spend"
    assert "style=" not in page[page.index("Needs doing") :], "the policy admits no style"
    assert "−" not in page or "vs" in page


def test_a_minus_is_a_minus() -> None:
    from targum.render.builder import _signed

    assert _signed(3) == "+3" and _signed(-2) == "−2" and _signed(0) == "±0"
    assert _signed(1.2, money=True) == "+$1.20" and _signed(-0.5, money=True) == "−$0.50"
    assert _signed(0.001, money=True) == "±$0.00"


def test_five_thousand_accounts_in_under_300_ms(tmp_path: Path) -> None:
    """5,000 readers, 200,000 words over ninety days, 15,000 texts and 20,000 jobs: the
    overview reads a span of days, so it must not grow with all that was ever done."""
    path = tmp_path / "targum.db"
    kept = Store(path)
    db = kept.db
    start = noon(TODAY)
    db.execute("BEGIN")
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
        "INSERT INTO day (person, day, count) VALUES (?, ?, 1)",
        [
            (n, (TODAY - dt.timedelta(days=(n + k) % 60)).isoformat())
            for n in range(1, 5001)
            for k in range(4)
        ],
    )
    db.executemany(
        "INSERT INTO job (id, owner, home, source, made, claimed, spent, length)"
        " VALUES (?, ?, 'h', 's', ?, 0.01, 0.01, 60)",
        [(f"j{n}", n % 5000 + 1, start - (n % 120) * DAY_MS) for n in range(20000)],
    )
    db.execute("COMMIT")
    kept.close()

    overview_store(path, at=AT, operators=(), ceiling=40.0, rail=10.0)  # warm the page cache
    began = time.perf_counter()
    found = overview_store(path, at=AT, operators=(), ceiling=40.0, rail=10.0)
    took = time.perf_counter() - began
    assert found.active_month.now == 5000
    assert took < 0.3, f"the overview took {took:.3f}s over 5,000 accounts"


def test_the_overview_reads_the_store_read_only(tmp_path: Path) -> None:
    path = tmp_path / "targum.db"
    Store(path).close()
    found = overview_store(path, at=AT, operators=())
    assert found.active_today.now == 0 and found.spent_today.now == 0


def test_the_indexes_carry_the_span(tmp_path: Path) -> None:
    db = sqlite3.connect(tmp_path / "x.db")
    Store(tmp_path / "x.db").close()

    def plan(sql: str) -> str:
        return " ".join(str(row[-1]) for row in db.execute("EXPLAIN QUERY PLAN " + sql))

    assert "word_at" in plan("SELECT person FROM word WHERE at >= 5 AND at < 9")
    assert "doc_opened" in plan("SELECT person FROM doc WHERE opened >= 5 AND opened < 9")
    assert "doc_updated" in plan("SELECT person FROM doc WHERE updated >= 5 AND updated < 9")
    assert "day_day" in plan("SELECT person FROM day WHERE day BETWEEN 'a' AND 'b'")
