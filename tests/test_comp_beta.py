"""The beta comped to Plan (design.md §12, "Signup opens before payments, and the beta is
comped to Plan", 2026-11-15; targum-internal#59).

Every account that exists on switch day, and anybody let in from the waitlist while
invitations are still going out, is on Plan until 2027-03-04; a new sign-up is on Free.
With `TARGUM_PLANS` off a comp changes nothing anybody sees. On its day the comp simply
ends: no mail, nothing automatic."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from targum import plans
from targum.accounts import Person, Store
from targum.cli import app
from targum.doorway import _comp, let_in, open_the_door
from targum.render.builder import plans_page
from targum.serve import UPLOAD_SECONDS, Library

UNTIL = "2027-03-04"


class Postbox:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def notify(
        self, to: str, subject: str, body: str, headers: Any = None, html: Any = None
    ) -> None:
        self.sent.append(to)


def signed_up(store: Store, email: str) -> Person:
    assert store.finish_sign_in(store.start_sign_in(email)) is not None
    me = store.person_by_email(email)
    assert me is not None
    return me


def waiting(store: Store, *emails: str) -> None:
    for email in emails:
        token = store.join_waitlist(email, "")
        assert token and store.confirm_waiting(token)


def a_library(tmp_path: Path, store: Store) -> Library:
    return Library(
        tmp_path / "out", max_cost=1000.0, budget=1000.0, store=store, account_budget=None
    )


# -- targum comp-beta ----------------------------------------------------------------


def test_comp_beta_dry_run_says_who_and_changes_nothing(tmp_path: Path) -> None:
    db = tmp_path / "targum.db"
    store = Store(db)
    signed_up(store, "a@example.com")
    store.invite("b@example.com")
    result = CliRunner().invoke(
        app, ["comp-beta", "--until", UNTIL, "--dry-run", "--store", str(db)]
    )
    assert result.exit_code == 0, result.output
    assert "a@example.com" in result.output and "b@example.com" in result.output
    assert "1 account(s) and 1 invitation(s) would be comped" in result.output
    assert Store(db).person_by_email("a@example.com").plan_until == ""  # type: ignore[union-attr]


def test_comp_beta_comps_every_account_once(tmp_path: Path) -> None:
    db = tmp_path / "targum.db"
    store = Store(db)
    signed_up(store, "a@example.com")
    signed_up(store, "c@example.com")
    store.invite("b@example.com")
    result = CliRunner().invoke(app, ["comp-beta", "--until", UNTIL, "--store", str(db)])
    assert result.exit_code == 0, result.output
    assert "2 account(s) and 1 invitation(s) comped to Plan until 2027-03-04" in result.output
    again = Store(db)
    for email in ("a@example.com", "c@example.com"):
        assert again.person_by_email(email).plan_until == UNTIL  # type: ignore[union-attr]
    # The invitation carries it to the account opened later, whichever way in.
    assert signed_up(again, "b@example.com").plan_until == UNTIL
    # Idempotent: a second run comps nobody.
    second = CliRunner().invoke(app, ["comp-beta", "--until", UNTIL, "--store", str(db)])
    assert second.exit_code == 0
    assert "0 account(s) and 0 invitation(s) comped" in second.output
    # A shorter comp never cuts a longer one.
    assert again.comp_everyone("2027-01-01") == ([], [])
    assert again.person_by_email("a@example.com").plan_until == UNTIL  # type: ignore[union-attr]


def test_comp_beta_refuses_a_day_that_is_not_one(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app, ["comp-beta", "--until", "March", "--store", str(tmp_path / "t.db")]
    )
    assert result.exit_code != 0


def test_an_account_made_after_the_comp_is_free(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    signed_up(store, "a@example.com")
    store.comp_everyone(UNTIL)
    assert signed_up(store, "new@example.com").plan_until == ""


# -- what a comp gives -----------------------------------------------------------------


def test_on_a_comped_reader_has_plan_and_everyone_else_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    beta = signed_up(store, "beta@example.com")
    store.comp_everyone(UNTIL)
    beta = store.person_by_email("beta@example.com")  # type: ignore[assignment]
    stranger = signed_up(store, "new@example.com")
    library = a_library(tmp_path, store)
    assert plans.paid(beta) and not plans.free(beta)
    assert library.allowance(paid_plan=plans.paid(beta)) == UPLOAD_SECONDS == 480 * 60
    assert plans.word_cap(beta) is None and plans.builds_by_itself(beta)
    assert not plans.paid(stranger)
    assert library.allowance(paid_plan=plans.paid(stranger)) == 60 * 60
    assert plans.word_cap(stranger) == 300 and not plans.builds_by_itself(stranger)
    said = plans.summary(beta)
    assert said["plan"] == "plan" and said["credits"] == 480 and said["words"] is None
    assert said["comp"] == UNTIL and said["compSaid"] == "March 4, 2027"
    assert "comp" not in plans.summary(stranger)


def test_off_a_comp_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TARGUM_PLANS", raising=False)
    store = Store(tmp_path / "targum.db")
    signed_up(store, "beta@example.com")
    store.comp_everyone(UNTIL)
    beta = store.person_by_email("beta@example.com")
    stranger = signed_up(store, "new@example.com")
    library = a_library(tmp_path, store)
    for who in (beta, stranger):
        assert library.allowance(paid_plan=plans.paid(who)) == UPLOAD_SECONDS
        assert plans.word_cap(who) is None and plans.builds_by_itself(who)
        assert plans.summary(who) == {"on": False}


def test_the_comp_ends_on_its_day() -> None:
    beta = Person(1, "beta@example.com", plan_until=UNTIL)
    assert plans.comped(beta, today=date(2027, 3, 3))
    assert not plans.comped(beta, today=date(2027, 3, 4))
    assert not plans.comped(Person(2, "x@example.com"), today=date(2026, 11, 15))
    assert not plans.comped(Person(3, "y@example.com", plan_until="soon"))


def test_the_comp_is_said_in_russian() -> None:
    assert plans.until_said(UNTIL, "ru") == "4 марта 2027"


# -- let in from the waitlist ----------------------------------------------------------


def test_let_in_from_the_waitlist_is_comped(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    waiting(store, "one@example.com", "few@example.com")
    opened = let_in(store, Postbox(), "https://targum.page", "one@example.com")
    assert opened is not None and opened.ok
    assert signed_up(store, "one@example.com").plan_until == plans.BETA_UNTIL
    # A few at a time is the same door.
    assert [row.email for row in open_the_door(store, Postbox(), "https://targum.page", 5)] == [
        "few@example.com"
    ]
    assert signed_up(store, "few@example.com").plan_until == plans.BETA_UNTIL
    # An invitation made by hand (`targum invite`) is not the waitlist, and comps nobody.
    store.invite("hand@example.com")
    assert signed_up(store, "hand@example.com").plan_until == ""


def test_let_in_after_the_comp_day_comps_nobody(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    store.invite("late@example.com")
    _comp(store, "late@example.com", today=date(2027, 3, 4))
    assert signed_up(store, "late@example.com").plan_until == ""


# -- the plans page --------------------------------------------------------------------


def test_the_plans_page_says_the_comp_and_keeps_start_greyed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    beta = Person(1, "beta@example.com", plan_until=UNTIL)
    page = plans_page(plans.summary(beta))
    assert "Free for beta readers until March 4, 2027" in page
    assert 'class="btn soon plan-start" disabled' in page and "Payments open soon" in page
    russian = plans_page(plans.summary(beta, language="ru"), language="ru")
    assert "до 4 марта 2027" in russian
    admin = plans_page(plans.summary(Person(2, "op@example.com", admin=True)))
    assert 'class="btn soon plan-start"' not in admin and "beta readers" not in admin
