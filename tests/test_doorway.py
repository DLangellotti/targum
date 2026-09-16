"""Letting the next few people in (targum-internal#292).

The front door promises "We'll email you when your turn comes." What is under test is
that the promise is kept exactly once per person, in the order they joined, in the
language they joined in — and that the failures fall the cheap way round: a mail that
could not be sent leaves the row unstamped so the next run tries again, rather than
stamping somebody as invited who never heard and would wait for ever.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from targum.accounts import Store
from targum.doorway import invitation, open_the_door


class Postbox:
    """A mailer that remembers, and can be told to refuse one address."""

    def __init__(self, refuse: str = "") -> None:
        self.sent: list[tuple[str, str, str]] = []
        self.refuse = refuse

    def send(self, to: str, link: str, language: str = "en") -> None:
        raise AssertionError("An invitation is a `notify`, not a sign-in link.")

    def notify(self, to: str, subject: str, body: str, headers: Any = None) -> None:
        if to == self.refuse:
            raise RuntimeError("mailbox full")
        self.sent.append((to, subject, body))


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


def waiting(store: Store, *people: tuple[str, str]) -> None:
    for email, language in people:
        token = store.join_waitlist(email, language)
        assert token and store.confirm_waiting(token)


def test_the_oldest_are_let_in_first_and_only_as_many_as_asked(store: Store) -> None:
    waiting(store, ("a@example.com", ""), ("b@example.com", ""), ("c@example.com", ""))
    post = Postbox()
    opened = open_the_door(store, post, "https://targum.page", 2)
    assert [row.email for row in opened] == ["a@example.com", "b@example.com"]
    assert all(row.ok for row in opened)
    assert [to for to, _, _ in post.sent] == ["a@example.com", "b@example.com"]
    # And they are on the guest list, which is what being let in means.
    assert store.may_join("a@example.com")
    assert not store.may_join("c@example.com")


def test_running_it_again_does_not_write_to_the_same_people(store: Store) -> None:
    waiting(store, ("a@example.com", ""), ("b@example.com", ""))
    post = Postbox()
    open_the_door(store, post, "https://targum.page", 1)
    open_the_door(store, post, "https://targum.page", 5)
    assert [to for to, _, _ in post.sent] == ["a@example.com", "b@example.com"]
    assert open_the_door(store, post, "https://targum.page", 5) == []


def test_a_mail_that_could_not_be_sent_leaves_them_for_the_next_run(store: Store) -> None:
    """The cheap failure: a duplicate in an inbox, never somebody waiting for ever."""
    waiting(store, ("a@example.com", ""), ("b@example.com", ""))
    post = Postbox(refuse="a@example.com")
    opened = open_the_door(store, post, "https://targum.page", 5)
    assert [row.email for row in opened] == ["a@example.com", "b@example.com"]
    assert not opened[0].ok and "mailbox full" in opened[0].failed
    assert opened[1].ok
    # One bad address does not stop the rest.
    assert [to for to, _, _ in post.sent] == ["b@example.com"]
    # Unstamped, so the next run tries them again — with a working postbox this time.
    assert [email for email, _ in store.waiting_for_a_way_in()] == ["a@example.com"]
    again = open_the_door(store, Postbox(), "https://targum.page", 5)
    assert [row.email for row in again] == ["a@example.com"]


def test_the_invitation_is_written_in_the_language_they_joined_in(store: Store) -> None:
    waiting(store, ("dina@example.com", "ru"), ("avi@example.com", ""))
    post = Postbox()
    open_the_door(store, post, "https://targum.page", 5)
    said = {to: (subject, body) for to, subject, body in post.sent}
    assert "targum" in said["dina@example.com"][0]
    assert "очередь" in said["dina@example.com"][0]
    assert "Your turn" in said["avi@example.com"][0]


def test_every_invitation_carries_the_way_in(store: Store) -> None:
    for language in ("en", "ru"):
        subject, body = invitation("https://targum.page/", language)
        assert subject
        assert "https://targum.page/account/signin" in body
        # No token in it: the address is on the guest list by now, and a sign-in link
        # sitting in an inbox would be stale long before it was read.
        assert "?t=" not in body


def test_a_dry_run_changes_nothing(store: Store) -> None:
    waiting(store, ("a@example.com", "ru"))
    opened = open_the_door(store, None, "", 5, dry_run=True)
    assert [(row.email, row.language) for row in opened] == [("a@example.com", "ru")]
    assert not store.may_join("a@example.com")
    assert [email for email, _ in store.waiting_for_a_way_in()] == ["a@example.com"]


def test_nobody_is_let_in_without_a_way_to_tell_them(store: Store) -> None:
    waiting(store, ("a@example.com", ""))
    with pytest.raises(ValueError):
        open_the_door(store, None, "https://targum.page", 5)
    with pytest.raises(ValueError):
        open_the_door(store, Postbox(), "", 5)
    assert not store.may_join("a@example.com")


def test_only_confirmed_addresses_are_let_in(store: Store) -> None:
    """Pending is not a turn, and neither is having left."""
    store.join_waitlist("pending@example.com")
    token = store.join_waitlist("gone@example.com")
    assert token and store.confirm_waiting(token)
    row = store.db.execute(
        "SELECT stop FROM waiting WHERE email = ?", ("gone@example.com",)
    ).fetchone()
    assert store.leave_waitlist(str(row["stop"]))
    post = Postbox()
    assert open_the_door(store, post, "https://targum.page", 5) == []
    assert post.sent == []


def test_asking_for_nobody_lets_nobody_in(store: Store) -> None:
    waiting(store, ("a@example.com", ""))
    post = Postbox()
    assert open_the_door(store, post, "https://targum.page", 0) == []
    assert open_the_door(store, post, "https://targum.page", -1) == []
    assert post.sent == []
