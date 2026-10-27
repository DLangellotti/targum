"""Which sign-ups might be fake (targum-internal#544).

Eight flags, each from what the store already holds and each said as a plain reason; a
"Possibly fake (2+)" filter on both lists; and Turn off, which sets a waitlist row off,
deletes nothing and can be undone.
"""

from __future__ import annotations

import datetime as dt
from datetime import date
from pathlib import Path

import pytest

from targum.accounts import Store
from targum.backoffice import (
    ACCOUNT_SORTS,
    DISPOSABLE,
    FLAGS,
    WAITING_SORTS,
    Listing,
    mostly_digits,
    survey,
    throwaway,
)
from targum.render.builder import back_office_page

TODAY = date(2026, 10, 27)
DAY_MS = 24 * 60 * 60 * 1000
NOON = int(dt.datetime.combine(TODAY, dt.time(12, 0), dt.UTC).timestamp() * 1000)


def waiting(
    store: Store,
    email: str,
    asked: int,
    *,
    state: str = "on",
    joined: int = 0,
    invited: int = 0,
) -> None:
    store.db.execute(
        "INSERT INTO waiting (email, state, stop, asked, joined, invited)"
        " VALUES (?, ?, 's', ?, ?, ?)",
        (email, state, asked, joined, invited),
    )


def person(store: Store, who: int, email: str, made: int) -> None:
    store.db.execute("INSERT INTO person (id, email, made) VALUES (?, ?, ?)", (who, email, made))


def flags_of(store: Store, email: str) -> list[str]:
    found = survey(store.db, today=TODAY)
    rows = {row.email: row.flags for row in found.waiting_list}
    rows |= {who.email: who.flags for who in found.accounts}
    return rows.get(email, [])


@pytest.fixture
def store(tmp_path: Path) -> Store:
    store = Store(tmp_path / "targum.db")
    # Somebody ordinary: asked a week ago, confirmed a minute later, let in, reading.
    waiting(
        store,
        "anna@example.com",
        NOON - 7 * DAY_MS,
        joined=NOON - 7 * DAY_MS + 60_000,
        invited=NOON - 6 * DAY_MS,
    )
    person(store, 1, "anna@example.com", NOON - 6 * DAY_MS)
    store.db.execute("INSERT INTO session (hash, person, made, seen) VALUES ('s1', 1, 1, 1)")
    store.db.execute("INSERT INTO day (person, day, count) VALUES (1, '2026-10-22', 1)")
    return store


def test_an_ordinary_sign_up_has_no_flags(store: Store) -> None:
    assert flags_of(store, "anna@example.com") == []


def test_never_confirmed_after_two_days(store: Store) -> None:
    waiting(store, "slow@example.com", NOON - 3 * DAY_MS, state="pending")
    waiting(store, "today@example.com", NOON - DAY_MS, state="pending")
    assert flags_of(store, "slow@example.com") == [FLAGS["unconfirmed"]]
    assert flags_of(store, "today@example.com") == [], "a day is not yet two"


def test_confirmed_within_ten_seconds(store: Store) -> None:
    waiting(store, "quick@example.com", NOON - 5 * DAY_MS, joined=NOON - 5 * DAY_MS + 4_000)
    waiting(store, "human@example.com", NOON - 4 * DAY_MS, joined=NOON - 4 * DAY_MS + 40_000)
    assert flags_of(store, "quick@example.com") == [FLAGS["instant"]]
    assert flags_of(store, "human@example.com") == []


def test_the_same_inbox_as_another_address(store: Store) -> None:
    waiting(store, "anna+second@example.com", NOON - 2 * DAY_MS, joined=NOON)
    assert FLAGS["same_inbox"] in flags_of(store, "anna+second@example.com")
    assert FLAGS["same_inbox"] in flags_of(store, "anna@example.com"), "both are said"
    waiting(store, "j.o.e@gmail.com", NOON - 4 * DAY_MS, joined=NOON)
    waiting(store, "joe@gmail.com", NOON - 3 * DAY_MS, joined=NOON)
    assert flags_of(store, "joe@gmail.com") == [FLAGS["same_inbox"]]


def test_a_throwaway_domain(store: Store) -> None:
    waiting(store, "x@mailinator.com", NOON - 4 * DAY_MS, joined=NOON)
    assert flags_of(store, "x@mailinator.com") == [FLAGS["throwaway"]]
    assert throwaway("y@inbox.mailinator.com"), "under one is one"
    assert not throwaway("z@gmail.com") and not throwaway("z@example.com")


def test_a_burst_of_five_in_ten_minutes(store: Store) -> None:
    start = NOON - 4 * DAY_MS
    for n in range(5):
        waiting(store, f"wave{n}@example.com", start + n * 60_000, joined=NOON)
    waiting(store, "later@example.com", start + 3 * 60 * 60_000, joined=NOON)
    assert flags_of(store, "wave0@example.com") == [FLAGS["burst"]]
    assert flags_of(store, "wave4@example.com") == [FLAGS["burst"]]
    assert flags_of(store, "later@example.com") == []


def test_let_in_and_never_signed_in(store: Store) -> None:
    waiting(
        store,
        "absent@example.com",
        NOON - 9 * DAY_MS,
        joined=NOON - 9 * DAY_MS + 60_000,
        invited=NOON - 5 * DAY_MS,
    )
    store.db.execute(
        "INSERT INTO invited (email, at) VALUES (?, ?)", ("absent@example.com", NOON - 5 * DAY_MS)
    )
    # A person row with a link that was never used is still nobody signed in.
    person(store, 2, "absent@example.com", NOON - 5 * DAY_MS)
    store.db.execute("INSERT INTO link (hash, person, made, used) VALUES ('l2', 2, 1, NULL)")
    assert flags_of(store, "absent@example.com") == [FLAGS["unused"]]
    store.db.execute("UPDATE link SET used = 5 WHERE hash = 'l2'")
    assert FLAGS["unused"] not in flags_of(store, "absent@example.com")


def test_signed_in_and_nothing_done(store: Store) -> None:
    person(store, 3, "idle@example.com", NOON - 4 * DAY_MS)
    store.db.execute("INSERT INTO session (hash, person, made, seen) VALUES ('s3', 3, 1, 1)")
    person(store, 4, "busy@example.com", NOON - 4 * DAY_MS)
    store.db.execute("INSERT INTO session (hash, person, made, seen) VALUES ('s4', 4, 1, 1)")
    store.db.execute("INSERT INTO word (person, language, lemma, at) VALUES (4, 'he', 'שלום', 1)")
    assert flags_of(store, "idle@example.com") == [FLAGS["idle"]]
    assert flags_of(store, "busy@example.com") == []


def test_mostly_digits_before_the_at(store: Store) -> None:
    waiting(store, "48213377@example.com", NOON - 4 * DAY_MS, joined=NOON)
    assert flags_of(store, "48213377@example.com") == [FLAGS["digits"]]
    assert mostly_digits("a1234567@x.com") and not mostly_digits("anna1990@x.com")
    assert not mostly_digits("123@x.com"), "too short to say"


def test_possibly_fake_filters_both_lists_and_flags_sort_them(store: Store) -> None:
    waiting(store, "12345678@mailinator.com", NOON - 4 * DAY_MS, state="pending")  # three
    waiting(store, "x@mailinator.com", NOON - 4 * DAY_MS, joined=NOON)  # one
    person(store, 5, "99887766@mailinator.com", NOON - 4 * DAY_MS)  # two
    found = survey(
        store.db,
        today=TODAY,
        accounts=Listing(sort="joined", fake=True),
        waitlist=Listing(sort="oldest", fake=True),
        let_in=Listing(sort="oldest", fake=True),
    )
    assert [row.email for row in found.waiting_list] == ["12345678@mailinator.com"]
    assert [who.email for who in found.accounts] == ["99887766@mailinator.com"]
    assert found.possibly_fake == 2
    page = back_office_page(found, 30)
    assert "2 possibly fake" in page
    assert 'name="wfake" value="1" checked' in page and 'name="fake" value="1" checked' in page
    assert "3 flags:" in page and FLAGS["throwaway"] in page

    assert "flags" in ACCOUNT_SORTS and "flags" in WAITING_SORTS
    ordered = survey(store.db, today=TODAY, waitlist=Listing(sort="flags"))
    assert [row.email for row in ordered.waiting_list][:2] == [
        "12345678@mailinator.com",
        "x@mailinator.com",
    ]
    accounts = survey(store.db, today=TODAY, accounts=Listing(sort="flags"))
    assert accounts.accounts[0].email == "99887766@mailinator.com"


def test_turn_off_sets_the_row_off_and_undo_puts_it_back(store: Store) -> None:
    store.join_waitlist("12345678@mailinator.com")
    assert store.turn_off_waiting("12345678@mailinator.com")
    row = store.db.execute(
        "SELECT state, was, turned_off FROM waiting WHERE email = '12345678@mailinator.com'"
    ).fetchone()
    assert (row["state"], row["was"]) == ("off", "pending") and row["turned_off"]
    assert store.db.execute("SELECT COUNT(*) FROM waiting").fetchone()[0] == 2, "never deleted"
    # Asking again is answered with nothing sent, and it stays off.
    assert store.join_waitlist("12345678@mailinator.com") is None
    assert store.waiting_state("12345678@mailinator.com") == "off"

    page = back_office_page(survey(store.db, today=TODAY), 30)
    assert "Turned off" in page and 'action="/back-office/turn-on"' in page

    assert store.undo_turn_off("12345678@mailinator.com")
    assert store.waiting_state("12345678@mailinator.com") == "pending"
    assert not store.undo_turn_off("12345678@mailinator.com"), "once"
    page = back_office_page(survey(store.db, today=TODAY), 30)
    assert 'action="/back-office/turn-off"' in page


def test_turn_off_is_only_for_a_row_still_waiting(store: Store) -> None:
    assert not store.turn_off_waiting("anna@example.com"), "already let in"
    assert not store.turn_off_waiting("nobody@example.com")
    page = back_office_page(survey(store.db, today=TODAY), 30)
    assert 'action="/back-office/turn-off"' not in page, "an unflagged row has no press"


def test_leaving_is_theirs_and_no_undo_brings_them_back(store: Store) -> None:
    store.join_waitlist("leaver@example.com")
    assert store.turn_off_waiting("leaver@example.com")
    stop = store.db.execute(
        "SELECT stop FROM waiting WHERE email = 'leaver@example.com'"
    ).fetchone()[0]
    assert store.leave_waitlist(stop)
    assert not store.undo_turn_off("leaver@example.com")


def test_only_an_admin_turns_off_or_back() -> None:
    """The press's door is the page's: an admin session, 404 for anyone else, and a form
    post from this origin, as Let in and Send again are."""
    served = Path(__file__).resolve().parent.parent / "src" / "targum" / "serve.py"
    text = served.read_text(encoding="utf-8")
    handler = text[text.index("def _turn_off") : text.index("def _resend")]
    assert "not person.admin" in handler
    assert 'self._send(404, b"not found"' in handler
    routes = text[text.index("def _post(") :]
    assert (
        'BACK_OFFICE_ROUTE + "/turn-off"' in routes and 'BACK_OFFICE_ROUTE + "/turn-on"' in routes
    )


def test_the_throwaway_list_is_vendored_and_says_where_it_came_from() -> None:
    head = DISPOSABLE.read_text(encoding="utf-8").splitlines()[:5]
    assert any("CC0" in line for line in head)
    assert any("disposable-email-domains" in line for line in head)
    notice = (Path(__file__).resolve().parent.parent / "NOTICE").read_text(encoding="utf-8")
    assert "src/targum/disposable.txt" in notice and "CC0" in notice
    backoffice = (
        Path(__file__).resolve().parent.parent / "src" / "targum" / "backoffice.py"
    ).read_text(encoding="utf-8")
    assert "urlopen" not in backoffice and "requests" not in backoffice, "nothing fetched"
