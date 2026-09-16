"""The front door's one form (targum-internal#69).

Somebody waiting is not an account and does not become one by waiting: the two are
joined by an address and by nothing else. That is the thing under test throughout —
joining touches no account, being let in is a separate act by a person, and leaving the
list leaves everything else alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from targum.accounts import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


def test_joining_makes_a_pending_row_and_mints_a_token(store: Store) -> None:
    token = store.join_waitlist("Dina@Example.com ")
    assert token
    # Tidied on the way in, the way every other address is.
    assert store.waiting_state("dina@example.com") == "pending"
    assert store.waiting_count() == {"pending": 1, "on": 0, "off": 0}


def test_asking_twice_re_mints_rather_than_making_a_second_row(store: Store) -> None:
    """What somebody does when the first mail did not arrive."""
    first = store.join_waitlist("dina@example.com")
    second = store.join_waitlist("dina@example.com")
    assert first and second and first != second
    assert store.waiting_count()["pending"] == 1
    # And the first token is dead, so a forwarded mail cannot confirm on their behalf.
    assert store.peek_waiting(first) is None
    assert store.peek_waiting(second) == "dina@example.com"


def test_peeking_does_not_spend_the_token(store: Store) -> None:
    """A mail client that fetches every link must not answer for the person."""
    token = store.join_waitlist("dina@example.com")
    assert token
    assert store.peek_waiting(token) == "dina@example.com"
    assert store.waiting_state("dina@example.com") == "pending"
    assert store.confirm_waiting(token) == "dina@example.com"


def test_confirming_puts_them_on_the_list_once(store: Store) -> None:
    token = store.join_waitlist("dina@example.com")
    assert token
    assert store.confirm_waiting(token) == "dina@example.com"
    assert store.waiting_state("dina@example.com") == "on"
    assert store.waiting_count() == {"pending": 0, "on": 1, "off": 0}
    # Spent. A link that works twice is a link somebody else can use.
    assert store.confirm_waiting(token) is None


def test_an_address_already_on_the_list_is_not_asked_again(store: Store) -> None:
    token = store.join_waitlist("dina@example.com")
    assert token and store.confirm_waiting(token)
    assert store.join_waitlist("dina@example.com") is None
    assert store.waiting_count()["on"] == 1


def test_leaving_keeps_the_row(store: Store) -> None:
    """ "Asked to leave" and "never came" are different facts, and only one of them
    means it is safe to mail again."""
    token = store.join_waitlist("dina@example.com")
    assert token and store.confirm_waiting(token)
    assert store.leave_waitlist("nonsense") is False
    stop = store.db.execute(
        "SELECT stop FROM waiting WHERE email = ?", ("dina@example.com",)
    ).fetchone()["stop"]
    assert store.leave_waitlist(stop) is True
    assert store.waiting_state("dina@example.com") == "off"
    assert store.waiting_count() == {"pending": 0, "on": 0, "off": 1}


def test_the_order_they_would_be_let_in_is_the_order_they_asked(store: Store) -> None:
    for name in ("first", "second", "third"):
        token = store.join_waitlist(f"{name}@example.com")
        assert token and store.confirm_waiting(token)
    # Pending and stopped addresses are nobody's turn.
    store.join_waitlist("pending@example.com")
    assert [email for email, _ in store.waiting_for_a_way_in()] == [
        "first@example.com",
        "second@example.com",
        "third@example.com",
    ]
    assert [email for email, _ in store.waiting_for_a_way_in(limit=2)] == [
        "first@example.com",
        "second@example.com",
    ]
    store.waiting_invited("first@example.com")
    assert [email for email, _ in store.waiting_for_a_way_in()] == [
        "second@example.com",
        "third@example.com",
    ]


def test_the_language_the_door_was_in_rides_with_the_address(store: Store) -> None:
    """So the invitation is written in what they read, not in English by default."""
    token = store.join_waitlist("dina@example.com", "ru")
    assert token and store.confirm_waiting(token)
    assert store.waiting_for_a_way_in() == [("dina@example.com", "ru")]
    # Nothing said means English, which is what the door was before it had a second
    # language to be in.
    plain = store.join_waitlist("avi@example.com")
    assert plain and store.confirm_waiting(plain)
    assert ("avi@example.com", "") in store.waiting_for_a_way_in()


def test_coming_back_through_the_other_door_changes_the_language(store: Store) -> None:
    """The door they came through most recently is the better guess at what they read."""
    first = store.join_waitlist("dina@example.com", "en")
    assert first
    store.join_waitlist("dina@example.com", "ru")
    again = store.join_waitlist("dina@example.com", "ru")
    assert again and store.confirm_waiting(again)
    assert store.waiting_for_a_way_in() == [("dina@example.com", "ru")]


def test_waiting_touches_no_account(store: Store) -> None:
    """The list is not a way in, and joining it is not an invitation."""
    token = store.join_waitlist("dina@example.com")
    assert token and store.confirm_waiting(token)
    assert store.may_join("dina@example.com") is False
    assert store.db.execute("SELECT COUNT(*) AS n FROM person").fetchone()["n"] == 0


def test_an_address_with_no_at_sign_is_refused_before_the_store(store: Store) -> None:
    with pytest.raises(ValueError):
        store.join_waitlist("   ")


def test_the_back_office_counts_the_list_and_names_nobody(tmp_path: Path) -> None:
    """Three numbers on the operator's own page. The rest of that page names nobody
    either, and a waitlist is a list of people who have agreed to nothing yet."""
    from targum.backoffice import survey

    store = Store(tmp_path / "targum.db")
    token = store.join_waitlist("dina@example.com")
    assert token and store.confirm_waiting(token)
    store.join_waitlist("not-yet@example.com")
    found = survey(store.db)
    assert found.waiting == {"pending": 1, "on": 1, "off": 0}


def test_the_back_office_lists_who_is_waiting_oldest_first(tmp_path: Path) -> None:
    """The counts answer "how many", which is the one question the operator does not
    have: a waitlist is a list of people to write to, and a list you cannot read is a
    number. Oldest first, which is the order they would be let in."""
    from targum.backoffice import survey

    store = Store(tmp_path / "targum.db")
    first = store.join_waitlist("first@example.com")
    assert first and store.confirm_waiting(first)
    store.join_waitlist("second@example.com")
    found = survey(store.db)
    assert [w.email for w in found.waiting_list] == ["first@example.com", "second@example.com"]
    assert [w.state for w in found.waiting_list] == ["on", "pending"]
    assert found.waiting_list[0].asked and found.waiting_list[0].joined
    assert found.waiting_list[1].joined == "", "an address that has not answered has no date"
    assert all(w.invited == "" for w in found.waiting_list)
    store.waiting_invited("first@example.com")
    assert survey(store.db).waiting_list[0].invited


def test_an_address_with_a_space_in_it_is_not_an_address() -> None:
    """`+` in a posted body means space, so `you+list@example.com` sent unencoded
    arrives as `you list@example.com`. It was being stored and mailed to (found on the
    live box the hour the front door opened, 2026-09-16)."""
    from targum.accounts import plausible

    assert plausible("dina@example.com")
    assert plausible("dina+waitlist@example.com")
    assert not plausible("dina waitlist@example.com")
    assert not plausible("dina@exa mple.com")
    assert not plausible("dina\t@example.com")
