"""The plan paid for and the top-ups, as the store keeps them (targum-internal#59 phase 2,
design.md §12 2026-11-15, "Payments are Paddle's, by a hosted checkout").

One `plan` row per account as Paddle last said it, one `credit_grant` row per top-up, and
the month's allowance still read from the one ledger of job rows: what is left of the
top-ups is never stored. A comp still wins until its day. Nothing here talks to Paddle."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from targum import accounts, plans
from targum.accounts import Person, Store
from targum.serve import UPLOAD_SECONDS, Job, Library

HOUR = 3600.0


def signed_up(store: Store, email: str) -> Person:
    assert store.finish_sign_in(store.start_sign_in(email)) is not None
    me = store.person_by_email(email)
    assert me is not None
    return me


def a_library(tmp_path: Path, store: Store) -> Library:
    return Library(
        tmp_path / "out", max_cost=1000.0, budget=1000.0, store=store, account_budget=None
    )


def recording(library: Library, who: int, seconds: float, ident: str) -> Job:
    job = Job(
        id=ident,
        source=f"upload:{ident}.mp3",
        estimate=0.10,
        owner=who,
        home=library.out / "local",
        audio=True,
        seconds=seconds,
    )
    library.jobs[ident] = job
    library.remember(job)
    return job


def ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def subscribe(store: Store, who: int, status: str = "active", **said: object) -> Person:
    store.set_billing(
        who,
        cadence=str(said.get("cadence", "month")),
        status=status,
        period_end=str(said.get("period_end", "2026-12-16T00:00:00Z")),
        cancel_at_end=bool(said.get("cancel_at_end", False)),
        customer=str(said.get("customer", "ctm_1")),
        subscription=str(said.get("subscription", "sub_1")),
    )
    me = store.person_by_id(who)
    assert me is not None
    return me


# -- the schema --------------------------------------------------------------------


def test_the_tables_land_on_an_old_file_and_the_version_moves(tmp_path: Path) -> None:
    db = tmp_path / "targum.db"
    Store(db).close()
    raw = sqlite3.connect(db)
    for table in ("plan", "credit_grant", "billing_event"):
        raw.execute(f"DROP TABLE {table}")  # noqa: S608 - fixed names
    raw.execute("PRAGMA user_version = 73")
    raw.commit()
    raw.close()
    store = Store(db)
    names = {
        str(row[0]) for row in store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"plan", "credit_grant", "billing_event"} <= names
    assert store.db.execute("PRAGMA user_version").fetchone()[0] == accounts.SCHEMA_VERSION == 74
    # Opened again, nothing fails: the tables are IF NOT EXISTS.
    Store(db).close()


# -- the plan row --------------------------------------------------------------------


def test_an_account_with_no_plan_row_has_no_billing(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    assert me.billing is None and not plans.subscribed(me)


def test_the_plan_row_keeps_what_paddle_said_and_is_read_with_the_person(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    me = subscribe(store, me.id, cadence="quarter", cancel_at_end=True)
    assert me.billing is not None
    assert me.billing.cadence == "quarter" and me.billing.status == "active"
    assert me.billing.cancel_at_end and me.billing.customer == "ctm_1"
    assert store.person_by_subscription("sub_1") == me
    assert store.person_by_customer("ctm_1") == me
    assert store.person_by_subscription("sub_other") is None


def test_an_update_keeps_the_customer_and_cadence_it_was_not_told(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    subscribe(store, me.id, cadence="quarter")
    me = subscribe(store, me.id, "canceled", cadence="", customer="")
    assert me.billing is not None
    assert me.billing.cadence == "quarter" and me.billing.customer == "ctm_1"


def test_an_older_word_from_paddle_changes_nothing(tmp_path: Path) -> None:
    """Paddle does not promise order: a subscription.updated sent before the cancel and
    delivered after it must not bring the plan back."""
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    assert store.set_billing(
        me.id,
        cadence="month",
        status="canceled",
        period_end="",
        cancel_at_end=False,
        customer="ctm_1",
        subscription="sub_1",
        said_at=2_000,
    )
    assert not store.set_billing(
        me.id,
        cadence="month",
        status="active",
        period_end="",
        cancel_at_end=False,
        customer="ctm_1",
        subscription="sub_1",
        said_at=1_000,
    )
    me = store.person_by_id(me.id)  # type: ignore[assignment]
    assert me.billing is not None and me.billing.status == "canceled"


def test_a_status_paddle_does_not_have_is_refused(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    with pytest.raises(ValueError, match="plan status"):
        subscribe(store, me.id, "gold")
    with pytest.raises(ValueError, match="cadence"):
        subscribe(store, me.id, cadence="year")


def test_past_due_starts_the_grace_once_and_anything_else_ends_it(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    me = subscribe(store, me.id, "past_due")
    assert me.billing is not None and me.billing.past_due_since is not None
    first = me.billing.past_due_since
    store.db.execute("UPDATE plan SET past_due_since = past_due_since - 5000")
    me = subscribe(store, me.id, "past_due")
    assert me.billing is not None and me.billing.past_due_since == first - 5000
    me = subscribe(store, me.id, "active")
    assert me.billing is not None and me.billing.past_due_since is None


# -- who is on Plan ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "on_plan"),
    [("active", True), ("trialing", True), ("paused", False), ("canceled", False)],
)
def test_paddles_status_says_plan(tmp_path: Path, status: str, on_plan: bool) -> None:
    store = Store(tmp_path / "targum.db")
    me = subscribe(store, signed_up(store, "a@example.com").id, status)
    assert plans.subscribed(me) is on_plan
    assert plans.paid(me) is on_plan


def test_a_cancelled_plan_runs_to_its_period_end(tmp_path: Path) -> None:
    """Paddle keeps a cancelled subscription active, with a scheduled change, until the
    period ends, and only then says canceled: so cancel_at_end is still Plan."""
    store = Store(tmp_path / "targum.db")
    me = subscribe(store, signed_up(store, "a@example.com").id, cancel_at_end=True)
    assert plans.paid(me)


def test_a_failed_renewal_is_plan_for_the_grace_and_then_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    me = subscribe(store, signed_up(store, "a@example.com").id, "past_due")
    assert me.billing is not None and me.billing.past_due_since is not None
    began = datetime.fromtimestamp(me.billing.past_due_since / 1000, UTC)
    assert plans.subscribed(me, began + timedelta(days=plans.GRACE_DAYS) - timedelta(minutes=1))
    assert not plans.subscribed(me, began + timedelta(days=plans.GRACE_DAYS))
    assert plans.paid(me) and not plans.free(me)


def test_a_comp_still_wins_until_its_day(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    store.comp_everyone("2099-01-01")
    me = subscribe(store, me.id, "canceled")
    assert plans.comped(me) and plans.paid(me)


def test_a_paid_reader_spends_plans_month_at_the_real_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    me = subscribe(store, signed_up(store, "a@example.com").id)
    library = a_library(tmp_path, store)
    assert library.allowance(paid_plan=plans.paid(me), owner=me.id) == UPLOAD_SECONDS
    assert library.claim(recording(library, me.id, 7 * HOUR, "p1")) == ""
    over = library.claim(recording(library, me.id, 2 * HOUR, "p2"))
    assert over.act == "top-up"


def test_the_back_office_counts_a_paid_reader_at_plans_month(tmp_path: Path) -> None:
    from targum.backoffice import _admins

    store = Store(tmp_path / "targum.db")
    paying = signed_up(store, "paying@example.com")
    subscribe(store, paying.id)
    lapsed = signed_up(store, "lapsed@example.com")
    subscribe(store, lapsed.id, "canceled", subscription="sub_2", customer="ctm_2")
    late = signed_up(store, "late@example.com")
    subscribe(store, late.id, "past_due", subscription="sub_3", customer="ctm_3")
    on_plan = _admins(store.db)
    assert "paying@example.com" in on_plan and "late@example.com" in on_plan
    assert "lapsed@example.com" not in on_plan
    store.db.execute(
        "UPDATE plan SET past_due_since = ? WHERE person = ?",
        (ms(datetime.now(UTC) - timedelta(days=plans.GRACE_DAYS + 1)), late.id),
    )
    assert "late@example.com" not in _admins(store.db)


# -- top-ups ------------------------------------------------------------------------


def test_a_grant_is_made_once_per_transaction(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    assert store.grant_credits(me.id, 60, "txn_1")
    assert not store.grant_credits(me.id, 60, "txn_1")
    assert [one["credits"] for one in store.top_ups(me.id)] == [60]
    with pytest.raises(ValueError):
        store.grant_credits(me.id, 0, "txn_2")


def test_a_top_up_adds_to_the_month_on_either_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    library = a_library(tmp_path, store)
    paying = subscribe(store, signed_up(store, "a@example.com").id)
    free = signed_up(store, "b@example.com")
    store.grant_credits(paying.id, 180, "txn_a")
    store.grant_credits(free.id, 60, "txn_b")
    assert library.allowance(paid_plan=True, owner=paying.id) == (480 + 180) * 60
    # A top-up bought on Plan stays the reader's when the plan ends.
    assert library.allowance(paid_plan=False, owner=free.id) == (60 + 60) * 60
    # Nobody else's grant is anybody's.
    other = signed_up(store, "c@example.com")
    assert library.allowance(paid_plan=False, owner=other.id) == 60 * 60


def test_a_top_up_lets_the_real_gate_past_the_plans_month(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    me = subscribe(store, signed_up(store, "a@example.com").id)
    library = a_library(tmp_path, store)
    assert library.claim(recording(library, me.id, 8 * HOUR, "full")) == ""
    assert library.claim(recording(library, me.id, HOUR, "over")).act == "top-up"
    store.grant_credits(me.id, 60, "txn_1")
    assert library.claim(recording(library, me.id, HOUR, "topped")) == ""
    assert library.claim(recording(library, me.id, 60.0, "past")).act == "top-up"


def _job(store: Store, who: int, seconds: float, at: datetime, ident: str) -> None:
    store.db.execute(
        "INSERT INTO job (id, owner, home, source, length, made, claimed)"
        " VALUES (?, ?, '', 'upload:x', ?, ?, 0.1)",
        (ident, who, seconds, ms(at)),
    )


def _grant_at(store: Store, who: int, credits: int, at: datetime, txn: str) -> None:
    store.grant_credits(who, credits, txn)
    store.db.execute("UPDATE credit_grant SET at = ? WHERE txn = ?", (ms(at), txn))


def test_what_is_left_of_a_top_up_is_read_from_the_job_rows(tmp_path: Path) -> None:
    """September: 300 credits bought, 200 minutes spent past a month of 480 → 100 left
    to October. October: 30 minutes past the month → 70 left to November, with a fresh
    60 bought in November on top. Nothing stores the 70: it is read from the rows."""
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    base = 480 * 60.0
    sep = datetime(2026, 9, 3, tzinfo=UTC)
    _grant_at(store, me.id, 300, sep, "txn_sep")
    _job(store, me.id, base + 100 * 60, sep + timedelta(days=1), "s1")
    _job(store, me.id, 100 * 60, sep + timedelta(days=2), "s2")
    oct_first = datetime(2026, 10, 1, tzinfo=UTC)
    assert store.grant_seconds(me.id, ms(oct_first), base) == 100 * 60
    _job(store, me.id, base + 30 * 60, oct_first + timedelta(days=4), "o1")
    nov_first = datetime(2026, 11, 1, tzinfo=UTC)
    assert store.grant_seconds(me.id, ms(nov_first), base) == 70 * 60
    _grant_at(store, me.id, 60, nov_first + timedelta(days=2), "txn_nov")
    assert store.grant_seconds(me.id, ms(nov_first), base) == 130 * 60
    # A month spent inside its allowance takes nothing off.
    dec_first = datetime(2026, 12, 1, tzinfo=UTC)
    _job(store, me.id, 100 * 60, nov_first + timedelta(days=5), "n1")
    assert store.grant_seconds(me.id, ms(dec_first), base) == 130 * 60


def test_a_top_up_never_goes_below_nothing(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    sep = datetime(2026, 9, 3, tzinfo=UTC)
    _grant_at(store, me.id, 60, sep, "txn_1")
    _job(store, me.id, 1000 * 60, sep + timedelta(days=1), "big")
    assert store.grant_seconds(me.id, ms(datetime(2026, 10, 1, tzinfo=UTC)), 480 * 60.0) == 0
    assert store.grant_seconds(None, 0, 0.0) == 0


def test_plans_off_a_grant_still_adds_and_nothing_else_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TARGUM_PLANS", raising=False)
    store = Store(tmp_path / "targum.db")
    library = a_library(tmp_path, store)
    me = signed_up(store, "a@example.com")
    assert library.allowance(paid_plan=False, owner=me.id) == UPLOAD_SECONDS
    store.grant_credits(me.id, 60, "txn_1")
    assert library.allowance(paid_plan=False, owner=me.id) == UPLOAD_SECONDS + 3600


# -- the account's own copy, and leaving -------------------------------------------


def test_the_export_carries_the_plan_and_top_ups(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = subscribe(store, signed_up(store, "a@example.com").id)
    store.grant_credits(me.id, 60, "txn_1")
    out = store.everything(me)
    assert out["plan"]["status"] == "active" and out["plan"]["subscription"] == "sub_1"
    assert [one["credits"] for one in out["top_ups"]] == [60]


def test_a_purged_account_takes_its_plan_rows(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = subscribe(store, signed_up(store, "a@example.com").id)
    store.grant_credits(me.id, 60, "txn_1")
    store.db.execute("UPDATE person SET leaving = 1 WHERE id = ?", (me.id,))
    assert store.purge(days=0) == [me.id]
    assert store.db.execute("SELECT COUNT(*) FROM plan").fetchone()[0] == 0
    assert store.db.execute("SELECT COUNT(*) FROM credit_grant").fetchone()[0] == 0


# -- webhooks seen ------------------------------------------------------------------


def test_a_webhook_is_seen_once_and_can_be_forgotten(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    assert store.billing_seen("evt_1", "subscription.created")
    assert not store.billing_seen("evt_1", "subscription.created")
    store.billing_unseen("evt_1")
    assert store.billing_seen("evt_1", "subscription.created")
