"""A paid Plan's credits run per month of the Plan, from the day it began (Terms of sale
clause 2, David 2026-11-19), not per calendar month. Free, comped beta readers and the
operator keep the calendar month. `Store.month_window` cuts the months, and `claim`, the
account page, the refusals and the top-ups all read it."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from targum import accounts
from targum.accounts import Store
from targum.serve import Library

FULL = 480 * 60.0
FREE = 60 * 60.0


def ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def day(year: int, month: int, date: int, hour: int = 0) -> datetime:
    return datetime(year, month, date, hour, tzinfo=UTC)


def reader(store: Store, email: str = "a@example.com") -> int:
    assert store.finish_sign_in(store.start_sign_in(email)) is not None
    me = store.person_by_email(email)
    assert me is not None
    return me.id


def paid(store: Store, who: int, starts: datetime, ends: datetime, sub: str = "sub_1") -> None:
    """A paid period, as `set_billing` keeps one from Paddle's subscription event."""
    store.set_billing(
        who,
        cadence="month",
        status="active",
        period_end=ends.isoformat(),
        cancel_at_end=False,
        customer="ctm_1",
        subscription=sub,
        said_at=ms(starts),
        period_start=starts.isoformat(),
    )


def job(store: Store, who: int, seconds: float, at: datetime, ident: str) -> None:
    store.db.execute(
        "INSERT INTO job (id, owner, home, source, length, made, claimed)"
        " VALUES (?, ?, '', 'upload:x', ?, ?, 0.1)",
        (ident, who, seconds, ms(at)),
    )
    store.db.commit()


def window(store: Store, who: int | None, at: datetime) -> tuple[datetime, datetime, bool]:
    start, end, paying = store.month_window(who, ms(at))
    return (
        datetime.fromtimestamp(start / 1000, UTC),
        datetime.fromtimestamp(end / 1000, UTC),
        paying,
    )


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


# -- the months -------------------------------------------------------------------------


def test_free_keeps_the_calendar_month(store: Store) -> None:
    me = reader(store)
    assert window(store, me, day(2026, 11, 19, 9)) == (day(2026, 11, 1), day(2026, 12, 1), False)
    assert window(store, None, day(2026, 12, 31, 23)) == (day(2026, 12, 1), day(2027, 1, 1), False)


def test_a_paid_month_runs_from_the_day_the_plan_began(store: Store) -> None:
    me = reader(store)
    paid(store, me, day(2026, 11, 15), day(2026, 12, 15))
    assert window(store, me, day(2026, 11, 15)) == (day(2026, 11, 15), day(2026, 12, 15), True)
    assert window(store, me, day(2026, 12, 14, 23)) == (day(2026, 11, 15), day(2026, 12, 15), True)
    # The first of the calendar month is no boundary inside it.
    assert window(store, me, day(2026, 12, 1))[0] == day(2026, 11, 15)


def test_a_renewal_starts_the_next_month_at_its_own_period(store: Store) -> None:
    me = reader(store)
    paid(store, me, day(2026, 11, 15), day(2026, 12, 15))
    paid(store, me, day(2026, 12, 15), day(2027, 1, 15))
    assert window(store, me, day(2026, 12, 15)) == (day(2026, 12, 15), day(2027, 1, 15), True)
    assert window(store, me, day(2026, 12, 14, 23))[1] == day(2026, 12, 15)


def test_february_keeps_the_day_where_it_can_and_its_last_where_it_cannot(store: Store) -> None:
    """A Plan begun on 31 January. Paddle's own periods end on 28 February (29 in a leap
    year) and 31 March; a period longer than a month is cut the same way here."""
    me = reader(store)
    paid(store, me, day(2027, 1, 31), day(2027, 4, 30))
    assert window(store, me, day(2027, 2, 10)) == (day(2027, 1, 31), day(2027, 2, 28), True)
    assert window(store, me, day(2027, 3, 1)) == (day(2027, 2, 28), day(2027, 3, 31), True)
    assert window(store, me, day(2027, 4, 2)) == (day(2027, 3, 31), day(2027, 4, 30), True)
    leap = reader(store, "b@example.com")
    paid(store, leap, day(2028, 1, 31), day(2028, 3, 31), sub="sub_2")
    assert window(store, leap, day(2028, 2, 28, 12)) == (day(2028, 1, 31), day(2028, 2, 29), True)
    assert window(store, leap, day(2028, 2, 29)) == (day(2028, 2, 29), day(2028, 3, 31), True)


def test_between_periods_it_is_the_calendar_from_where_the_plan_stopped(store: Store) -> None:
    """A Plan that ended on the 11th: Free's month runs from then to the first, so the
    paid days are counted once, in the Plan's month, and never again in Free's."""
    me = reader(store)
    paid(store, me, day(2026, 10, 11), day(2026, 11, 11))
    assert window(store, me, day(2026, 11, 20)) == (day(2026, 11, 11), day(2026, 12, 1), False)
    assert window(store, me, day(2026, 12, 2)) == (day(2026, 12, 1), day(2027, 1, 1), False)
    # A free reader who subscribes mid-month: Free's month stops where the Plan begins.
    later = reader(store, "c@example.com")
    paid(store, later, day(2026, 11, 15), day(2026, 12, 15), sub="sub_3")
    assert window(store, later, day(2026, 11, 3)) == (day(2026, 11, 1), day(2026, 11, 15), False)


def test_the_months_tile_time(store: Store) -> None:
    """Walking from window to window covers every moment once: no gap, no overlap."""
    me = reader(store)
    paid(store, me, day(2026, 10, 20), day(2026, 11, 20))
    paid(store, me, day(2026, 11, 20), day(2026, 12, 5))  # cancelled part way
    at = ms(day(2026, 9, 1))
    seen = []
    while at < ms(day(2027, 2, 1)):
        start, end, _ = store.month_window(me, at)
        assert start <= at < end
        seen.append((start, end))
        at = end
    for (_, one_end), (two_start, _) in zip(seen, seen[1:], strict=False):
        assert one_end == two_start


def test_a_comped_reader_and_the_operator_keep_the_calendar(store: Store) -> None:
    me = reader(store)
    store.comp("a@example.com", "2027-03-04")
    assert window(store, me, day(2026, 11, 19)) == (day(2026, 11, 1), day(2026, 12, 1), False)
    store.make_admin("ops@example.com")
    boss = reader(store, "ops@example.com")
    assert window(store, boss, day(2026, 11, 19))[0] == day(2026, 11, 1)


# -- what reads them --------------------------------------------------------------------


def test_the_library_counts_a_payers_credits_from_their_own_month(
    store: Store, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spent on 10 December by a reader whose month began on 15 November: it counts in
    the month, and the calendar's first of December resets nothing. The account page's
    "resets on" is their own day."""
    me = reader(store)
    paid(store, me, day(2026, 11, 15), day(2026, 12, 15))
    job(store, me, 300 * 60, day(2026, 11, 25), "before-the-first")
    library = Library(tmp_path / "out", max_cost=1000.0, budget=1000.0, store=store)
    monkeypatch.setattr(accounts, "now", lambda: ms(day(2026, 12, 10)))
    monkeypatch.setattr("targum.serve.now", lambda: ms(day(2026, 12, 10)))
    assert library.month_from_for(me) == ms(day(2026, 11, 15))
    assert store.hours_used(me, library.month_from_for(me)) == 300 * 60
    assert library.month_ends_for("en", me) == "December 15"
    # Everyone else, and a missing owner, still have the calendar's.
    free = reader(store, "free@example.com")
    assert library.month_from_for(free) == ms(day(2026, 12, 1))
    assert library.month_from_for(None) == Library._month_from()
    assert library.month_ends_for("en", free) == "January 1"


def test_a_top_up_is_spent_against_each_paid_month_not_each_calendar_month(store: Store) -> None:
    """300 credits bought. Plan from 15 October, renewed on 15 November. Each paid month
    spends 30 minutes past its 480, wherever the calendar's first falls in it, so 240
    are left on 15 December."""
    me = reader(store)
    store.grant_credits(me, 300, "txn_1")
    store.db.execute("UPDATE credit_grant SET at = ?", (ms(day(2026, 10, 15)),))
    store.db.commit()
    paid(store, me, day(2026, 10, 15), day(2026, 11, 15))
    paid(store, me, day(2026, 11, 15), day(2026, 12, 15))
    # Spread over each month's calendar first, which used to split them.
    job(store, me, FULL / 2, day(2026, 10, 20), "o1")
    job(store, me, FULL / 2 + 30 * 60, day(2026, 11, 3), "o2")
    job(store, me, FULL / 2, day(2026, 11, 20), "n1")
    job(store, me, FULL / 2 + 30 * 60, day(2026, 12, 3), "n2")
    left = store.grant_seconds(me, ms(day(2026, 12, 15)), FULL, FREE)
    assert round(left / 60) == 240


def test_a_quarter_long_period_is_three_months_of_credits(store: Store) -> None:
    """A period longer than a month (none is sold now) is still three months, not one
    month of credits stretched over three."""
    me = reader(store)
    paid(store, me, day(2026, 9, 10), day(2026, 12, 10))
    months = set()
    at = day(2026, 9, 10)
    while at < day(2026, 12, 10):
        months.add(window(store, me, at)[:2])
        at += timedelta(days=5)
    assert months == {
        (day(2026, 9, 10), day(2026, 10, 10)),
        (day(2026, 10, 10), day(2026, 11, 10)),
        (day(2026, 11, 10), day(2026, 12, 10)),
    }
