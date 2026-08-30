"""Being told when a new issue is out.

The thing under test throughout is that a subscriber is not an account. They are joined
by an address and by nothing else — which is what lets somebody who has never been
invited hear about Monday, and what stops unsubscribing from touching an account.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from targum.accounts import Store
from targum.mail import ConsoleMailer
from targum.weekly.mailout import announce, letter
from targum.weekly.models import Edition, Issue, Level, State, entry_id, folder


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


@pytest.fixture
def issue() -> Issue:
    return Issue(
        id="2026-w36",
        dated="2026-08-31",
        title="השבוע בעברית",
        state=State.published,
        editions=[
            Edition(
                level=level,
                entry_id=entry_id("2026-w36", level),
                folder=folder("2026-w36", level),
                ok=True,
            )
            for level in Level
        ],
    )


class Refusing:
    """A mailer that will not take one address, and takes the rest."""

    def __init__(self, refuse: set[str]) -> None:
        self.refuse = refuse
        self.sent: list[str] = []

    def send(self, to: str, link: str) -> None: ...

    def notify(self, to: str, subject: str, body: str, headers: object = None) -> None:
        if to in self.refuse:
            raise OSError("mailbox unavailable")
        self.sent.append(to)


# -- a subscriber is not an account ---------------------------------------------------


def test_subscribing_makes_no_account_and_no_invitation(store: Store) -> None:
    store.subscribe("stranger@example.com")
    assert store.db.execute("SELECT COUNT(*) AS n FROM person").fetchone()["n"] == 0
    assert store.db.execute("SELECT COUNT(*) AS n FROM invited").fetchone()["n"] == 0
    assert not store.may_join("stranger@example.com"), "hearing about Monday is not an invitation"


def test_an_account_and_a_subscription_meet_at_the_address(store: Store) -> None:
    """Somebody who subscribed signed out and later opens an account finds the box
    already ticked, because both doors write the same row."""
    token = store.subscribe("reader@example.com")
    assert token and store.confirm_subscription(token)

    signed = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert signed is not None
    assert store.following("reader@example.com")


def test_being_forgotten_stops_the_weekly(store: Store) -> None:
    """A subscription outlives an account on purpose. It does not outlive somebody
    asking to be forgotten."""
    signed = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert signed is not None
    person, _ = signed
    store.follow(person.email)
    assert store.following(person.email)

    store.forget(person)
    assert not store.following(person.email)


# -- the public door confirms ---------------------------------------------------------


def test_fetching_the_confirmation_does_not_spend_it(store: Store) -> None:
    """A mail client that fetches every link in a message must not be able to answer
    for the person it was sent to."""
    token = store.subscribe("reader@example.com")
    assert token is not None
    assert store.peek_subscription(token) == "reader@example.com"
    assert not store.following("reader@example.com"), "peeking did not turn it on"
    assert store.confirm_subscription(token) == "reader@example.com"
    assert store.following("reader@example.com")


def test_a_confirmation_works_once(store: Store) -> None:
    token = store.subscribe("reader@example.com")
    assert token is not None
    assert store.confirm_subscription(token)
    assert store.confirm_subscription(token) is None


def test_asking_twice_re_mints_rather_than_making_a_second_row(store: Store) -> None:
    """Asking twice is what somebody does when the first mail did not arrive."""
    first = store.subscribe("reader@example.com")
    second = store.subscribe("reader@example.com")
    assert first != second
    assert store.db.execute("SELECT COUNT(*) AS n FROM subscriber").fetchone()["n"] == 1
    assert store.confirm_subscription(first) is None, "the earlier link is void"
    assert store.confirm_subscription(second) == "reader@example.com"


def test_subscribing_an_address_already_on_mints_nothing(store: Store) -> None:
    token = store.subscribe("reader@example.com")
    assert token and store.confirm_subscription(token)
    assert store.subscribe("reader@example.com") is None


# -- the signed-in door does not ------------------------------------------------------


def test_a_session_is_the_confirmation(store: Store) -> None:
    """Somebody with a session proved they control the address by following a link to
    get in. Mailing to ask would be asking them to confirm what they confirmed."""
    assert store.follow("reader@example.com") is True
    assert store.following("reader@example.com")
    row = store.db.execute(
        "SELECT confirm, state FROM subscriber WHERE email = ?", ("reader@example.com",)
    ).fetchone()
    assert row["state"] == "on"
    assert row["confirm"] is None, "nothing is left outstanding"


def test_the_same_control_unticks(store: Store) -> None:
    store.follow("reader@example.com")
    assert store.follow("reader@example.com", on=False) is False
    assert not store.following("reader@example.com")


def test_stopping_and_starting_again_is_allowed(store: Store) -> None:
    """A row is never deleted: "they asked to stop" and "they were never here" are
    different facts, and only one of them means it is safe to mail again."""
    store.follow("reader@example.com")
    store.follow("reader@example.com", on=False)
    store.follow("reader@example.com")
    assert store.following("reader@example.com")


# -- the way out ----------------------------------------------------------------------


def test_one_click_stops_it(store: Store) -> None:
    store.follow("reader@example.com")
    row = store.db.execute(
        "SELECT stop FROM subscriber WHERE email = ?", ("reader@example.com",)
    ).fetchone()
    assert store.stop_subscription(row["stop"])
    assert not store.following("reader@example.com")


def test_a_stop_token_that_is_not_one_does_nothing(store: Store) -> None:
    assert store.stop_subscription("") is False
    assert store.stop_subscription("made-up") is False


def test_every_letter_carries_the_way_out(store: Store, issue: Issue) -> None:
    _, body = letter(issue, "https://targum.page", "abc123")
    assert "/weekly/stop?t=abc123" in body
    assert "/weekly/2026-w36" in body
    assert "compiled by a model" in body.lower(), "how it was made travels with it"
    assert "/account/signin" not in body, "a subscriber is not being asked to sign in"


# -- the mailout ----------------------------------------------------------------------


def test_announcing_twice_mails_once(store: Store, issue: Issue) -> None:
    """The property everything else here is arranged around. A run that re-sends the
    whole list is the failure that costs a sending domain its reputation — and on this
    box that domain carries the sign-in link too."""
    for who in ("a@example.com", "b@example.com"):
        store.follow(who)
    mailer = Refusing(set())

    first = announce(store, mailer, issue, "https://targum.page")
    assert sorted(first.sent) == ["a@example.com", "b@example.com"]

    second = announce(store, mailer, issue, "https://targum.page")
    assert second.sent == []
    assert len(mailer.sent) == 2


def test_a_run_that_died_halfway_resumes(store: Store, issue: Issue) -> None:
    for who in ("a@example.com", "b@example.com"):
        store.follow(who)
    store.mark_sent("a@example.com", issue.id)

    report = announce(store, ConsoleMailer(stream=io.StringIO()), issue, "https://targum.page")
    assert report.sent == ["b@example.com"]


def test_one_bad_address_does_not_stop_the_run(store: Store, issue: Issue) -> None:
    for who in ("a@example.com", "bad@example.com", "c@example.com"):
        store.follow(who)
    mailer = Refusing({"bad@example.com"})

    report = announce(store, mailer, issue, "https://targum.page")
    assert sorted(report.sent) == ["a@example.com", "c@example.com"]
    assert [who for who, _ in report.failed] == ["bad@example.com"]


def test_an_address_that_keeps_failing_is_dropped(store: Store, issue: Issue) -> None:
    store.follow("bad@example.com")
    for _ in range(3):
        assert store.bounced("bad@example.com") in {True, False}
    assert not store.following("bad@example.com")


def test_a_new_subscriber_gets_the_issue_they_missed(store: Store, issue: Issue) -> None:
    """Selected on "has not had this one" rather than on when they joined."""
    store.follow("early@example.com")
    announce(store, ConsoleMailer(stream=io.StringIO()), issue, "https://targum.page")
    store.follow("late@example.com")

    report = announce(store, ConsoleMailer(stream=io.StringIO()), issue, "https://targum.page")
    assert report.sent == ["late@example.com"]


def test_nobody_subscribed_is_not_a_failure(store: Store, issue: Issue) -> None:
    report = announce(store, ConsoleMailer(stream=io.StringIO()), issue, "https://targum.page")
    assert report.sent == [] and not report.failed and not report.stopped


# -- the gate ---------------------------------------------------------------------------


def _stub_reader(root: Path, week: str, level: Level) -> None:
    """A built reader, so `publish` gets past the gate that asks whether one exists.

    Publishing an issue nobody can open is refused before anything else is checked, so
    a test about the band or about borrowed wording has to put a reader on disk first.
    """
    from targum.weekly.models import folder

    built = root / folder(week, level) / "reader"
    built.mkdir(parents=True, exist_ok=True)
    (built / "index.html").write_text("<!doctype html>", encoding="utf-8")


def test_publishing_refuses_a_level_that_missed_its_band(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A level labelled for a vocabulary it has not got is worse than a missing one:
    the label is the whole promise, and a reader picks by it."""
    import typer

    from targum.cli import weekly_publish
    from targum.weekly import index as weekly_index
    from targum.weekly.models import Index

    monkeypatch.setenv("TARGUM_WEEKLY_DIR", str(tmp_path))
    monkeypatch.setattr(weekly_index, "_cached", None)

    drafted = Issue(
        id="2026-w40",
        dated="2026-10-05",
        title="השבוע",
        editions=[
            Edition(
                level=Level.bet,
                entry_id=entry_id("2026-w40", Level.bet),
                folder=folder("2026-w40", Level.bet),
                difficulty=27,
                ok=False,
            )
        ],
    )
    weekly_index.save(Index(issues=[drafted]))
    _stub_reader(tmp_path, "2026-w40", Level.bet)
    weekly_index._cached = None

    with pytest.raises(typer.Exit):
        weekly_publish("2026-w40", anyway=False)
    weekly_index._cached = None
    still = weekly_index.by_week("2026-w40")
    assert still is not None and still.state is State.draft

    weekly_publish("2026-w40", anyway=True)
    weekly_index._cached = None
    out = weekly_index.by_week("2026-w40")
    assert out is not None and out.state is State.published
    assert out.published_at, "when it went out is recorded"


def test_a_draft_cannot_be_announced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Publishing and announcing are two verbs, and they only go in one order."""
    import typer

    from targum.cli import weekly_announce
    from targum.weekly import index as weekly_index
    from targum.weekly.models import Index

    monkeypatch.setenv("TARGUM_WEEKLY_DIR", str(tmp_path))
    monkeypatch.setenv("TARGUM_PUBLIC_ADDRESS", "https://targum.page")
    monkeypatch.setattr(weekly_index, "_cached", None)
    weekly_index.save(Index(issues=[Issue(id="2026-w41", dated="2026-10-12", title="השבוע")]))
    weekly_index._cached = None

    with pytest.raises(typer.Exit):
        weekly_announce("2026-w41", store=tmp_path / "targum.db")


def test_a_borrowed_run_cannot_be_published_even_with_anyway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missed band is a labelling problem, and publishing through it knowingly is a
    decision somebody is allowed to take. Somebody else's sentence in the issue is not
    the same kind of thing, and `--anyway` does not reach it."""
    import typer

    from targum.cli import weekly_publish
    from targum.weekly import index as weekly_index
    from targum.weekly.models import Index

    monkeypatch.setenv("TARGUM_WEEKLY_DIR", str(tmp_path))
    monkeypatch.setattr(weekly_index, "_cached", None)
    weekly_index.save(
        Index(
            issues=[
                Issue(
                    id="2026-w42",
                    dated="2026-10-19",
                    title="השבוע",
                    editions=[
                        Edition(
                            level=Level.bet,
                            entry_id=entry_id("2026-w42", Level.bet),
                            folder=folder("2026-w42", Level.bet),
                            difficulty=16,
                            ok=False,
                            lifted=["'a run of their words' (from 'their headline')"],
                        )
                    ],
                )
            ]
        )
    )
    _stub_reader(tmp_path, "2026-w42", Level.bet)
    weekly_index._cached = None

    for anyway in (False, True):
        with pytest.raises(typer.Exit):
            weekly_publish("2026-w42", anyway=anyway)
        weekly_index._cached = None
        still = weekly_index.by_week("2026-w42")
        assert still is not None and still.state is State.draft


# -- one week from the next ------------------------------------------------------------


def _issue(week: str, dated: str) -> Issue:
    return Issue(
        id=week,
        dated=dated,
        title="השבוע בעברית",
        state=State.published,
        editions=[
            Edition(
                level=level,
                entry_id=entry_id(week, level),
                folder=folder(week, level),
                ok=True,
            )
            for level in Level
        ],
    )


def test_last_week_does_not_stop_this_week(store: Store) -> None:
    """The rail that makes a mailout safe to resume selects on "has not had *this*
    issue". Written as "has not been sent anything" it would have mailed each subscriber
    once and then gone quiet for ever — a bug that only appears on the second Monday,
    and looks like the feature working until it does."""
    store.follow("reader@example.com")
    last, this = _issue("2026-w35", "2026-08-24"), _issue("2026-w36", "2026-08-31")

    first = announce(store, ConsoleMailer(stream=io.StringIO()), last, "https://targum.page")
    assert first.sent == ["reader@example.com"]

    again = announce(store, ConsoleMailer(stream=io.StringIO()), this, "https://targum.page")
    assert again.sent == ["reader@example.com"], "a new issue is a new send"

    once = announce(store, ConsoleMailer(stream=io.StringIO()), this, "https://targum.page")
    assert once.sent == [], "the same issue is not"


def test_each_letter_names_its_own_issue(store: Store) -> None:
    """Two weeks running, and the second must not link to the first."""
    last, this = _issue("2026-w35", "2026-08-24"), _issue("2026-w36", "2026-08-31")
    _, older = letter(last, "https://targum.page", "abc")
    _, newer = letter(this, "https://targum.page", "abc")

    assert "/weekly/2026-w35" in older and "/weekly/2026-w36" not in older
    assert "/weekly/2026-w36" in newer and "/weekly/2026-w35" not in newer
    assert "2026-08-24" in older and "2026-08-31" in newer


def test_somebody_who_joined_between_issues_gets_the_new_one(store: Store) -> None:
    """And not the old one: the weekly is a subscription, not a back catalogue posted
    all at once to whoever just arrived."""
    last, this = _issue("2026-w35", "2026-08-24"), _issue("2026-w36", "2026-08-31")
    store.follow("early@example.com")
    announce(store, ConsoleMailer(stream=io.StringIO()), last, "https://targum.page")

    store.follow("late@example.com")
    report = announce(store, ConsoleMailer(stream=io.StringIO()), this, "https://targum.page")
    assert sorted(report.sent) == ["early@example.com", "late@example.com"]

    behind = announce(store, ConsoleMailer(stream=io.StringIO()), last, "https://targum.page")
    assert behind.sent == [], "nobody is sent an issue older than the one they have"


def test_announcing_the_wrong_week_posts_nothing(store: Store) -> None:
    """The column holds the last issue sent, not a history — so "has not had this one"
    on its own would post last week to everybody the moment somebody typed the wrong
    week. An email is the one thing here that cannot be taken back."""
    last, this = _issue("2026-w35", "2026-08-24"), _issue("2026-w36", "2026-08-31")
    store.follow("reader@example.com")
    announce(store, ConsoleMailer(stream=io.StringIO()), this, "https://targum.page")

    slip = announce(store, ConsoleMailer(stream=io.StringIO()), last, "https://targum.page")
    assert slip.sent == []
