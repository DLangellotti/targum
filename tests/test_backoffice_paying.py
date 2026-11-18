"""Paying readers by the page or link tag their account came in by (design.md §12,
2026-11-18): the go/no-go asks how many pay their own money, per channel."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from targum.accounts import Store
from targum.backoffice import survey
from targum.render.builder import back_office_page

TODAY = date(2026, 11, 25)
DAY_MS = 86_400_000


def _ms(when: date) -> int:
    return int(datetime(when.year, when.month, when.day, tzinfo=UTC).timestamp() * 1000)


def _id(store: Store, email: str) -> int:
    return int(store.db.execute("SELECT id FROM person WHERE email = ?", (email,)).fetchone()[0])


def _account(store: Store, email: str, came_from: str = "") -> int:
    store.start_sign_in(email, came_from)
    return _id(store, email)


def _bill(store: Store, person: int, status: str, n: int) -> None:
    assert store.set_billing(
        person,
        cadence="month",
        status=status,
        period_end="2026-12-25T00:00:00Z",
        cancel_at_end=False,
        customer=f"ctm_{n}",
        subscription=f"sub_{n}",
        said_at=_ms(TODAY) - DAY_MS,
    )


def _store(tmp_path: Path) -> Store:
    store = Store(tmp_path / "targum.db")
    store.join_waitlist("w@example.com", "en", "meta.after-duolingo")
    _bill(store, _account(store, "a@example.com", "meta.after-duolingo"), "active", 1)
    _account(store, "b@example.com", "meta.after-duolingo")
    _bill(store, _account(store, "c@example.com"), "trialing", 2)
    _bill(store, _account(store, "d@example.com"), "canceled", 3)
    # Comped and paying is paying; comped alone is not.
    _account(store, "e@example.com", "reddit")
    assert store.comp("e@example.com", "2027-02-18")
    _bill(store, _account(store, "f@example.com", "reddit"), "active", 4)
    assert store.comp("f@example.com", "2027-02-18")
    # A comp whose day has come is nothing.
    _account(store, "g@example.com", "reddit")
    assert store.comp("g@example.com", "2026-11-20")
    # The operator pays and is still nobody's number.
    _bill(store, _account(store, "me+x@example.com", "meta.after-duolingo"), "active", 5)
    return store


def test_paying_and_comped_are_counted_by_tag(tmp_path: Path) -> None:
    store = _store(tmp_path)
    found = survey(store.db, today=TODAY, operators=["me@example.com"])
    assert found.accounts_by_came_from == {"reddit": 3, "meta.after-duolingo": 2, "": 2}
    assert found.paying_by_came_from == {"reddit": 1, "meta.after-duolingo": 1, "": 1}
    assert found.comped_by_came_from == {"reddit": 1}
    page = back_office_page(found, 30, section="waitlist")
    assert (
        "Paying from reddit 1 of 3 &middot; meta.after-duolingo 1 of 2 &middot; unknown 1 of 2</p>"
        in page
    )
    assert "Comped from reddit 1</p>" in page


def test_a_failed_renewal_pays_through_its_grace_and_not_after(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    store.join_waitlist("w@example.com", "en", "x")
    late = _account(store, "late@example.com", "x")
    _bill(store, late, "active", 1)
    _bill(store, late, "past_due", 1)
    since = _ms(TODAY) - 3 * DAY_MS
    store.db.execute("UPDATE plan SET past_due_since = ? WHERE person = ?", (since, late))
    store.db.commit()
    assert survey(store.db, today=TODAY).paying_by_came_from == {"x": 1}
    assert survey(store.db, today=date(2026, 12, 10)).paying_by_came_from == {}


def test_nobody_paying_shows_no_line(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    store.join_waitlist("w@example.com", "en", "x")
    _account(store, "a@example.com", "x")
    found = survey(store.db, today=TODAY)
    assert found.paying_by_came_from == {} and found.comped_by_came_from == {}
    page = back_office_page(found, 30, section="waitlist")
    assert "Accounts from x 1" in page
    assert "Paying from" not in page and "Comped from" not in page


def test_a_paying_tag_past_the_ten_is_counted_under_other(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    store.join_waitlist("w@example.com", "en", "x")
    for n in range(12):
        for k in range(12 - n):
            _account(store, f"a{n}-{k}@example.com", f"tag-{n}")
    _bill(store, _id(store, "a11-0@example.com"), "active", 1)
    _bill(store, _id(store, "a0-0@example.com"), "active", 2)
    found = survey(store.db, today=TODAY)
    assert found.paying_by_came_from == {"tag-0": 1, "other": 1}
    page = back_office_page(found, 30, section="waitlist")
    assert "Paying from tag-0 1 of 12 &middot; other 1 of 3</p>" in page
