"""A refund Paddle approved (Terms of sale clause 9, approved by David 2026-11-19): a
top-up's unused credits go back, never below nothing, and a Plan payment refunded in full
ends the Plan at once. Once per adjustment, whatever Paddle sends twice. Fixtures are
shaped as Paddle's documentation draws an adjustment; nothing talks to Paddle."""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

import pytest
from test_billing_webhook import box, deliver, fixture, signed, signed_up  # noqa: F401

from targum import billing
from targum.accounts import Store

TOP_UP = "adjustment_updated_refund_top_up"
PLAN = "adjustment_updated_refund_plan"


@pytest.fixture(autouse=True)
def paddle(monkeypatch: pytest.MonkeyPatch) -> None:
    from test_billing_webhook import SECRET

    monkeypatch.setenv(billing.WEBHOOK_SECRET_ENV, SECRET)
    monkeypatch.setenv(billing.PRICE_MONTH_ENV, "pri_month")
    monkeypatch.setenv(billing.PRICE_TOP_UP_ENV, "pri_top_up")


def bought(store: Store, who: int) -> None:
    """180 credits bought: the top-up fixture's three units."""
    outcome = billing.handle(store, fixture("transaction_completed_top_up", who, store))
    assert outcome.kind == "top-up" and outcome.detail == "180"


def left_of(seconds: float) -> Any:
    return lambda _who: seconds


def refund(**changes: Any) -> dict[str, Any]:
    event = fixture(TOP_UP)
    event["data"].update(changes)
    return event


def credits(store: Store, who: int) -> list[int]:
    return [one["credits"] for one in store.top_ups(who)]


def test_a_full_refund_takes_back_a_top_ups_unused_credits(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    bought(store, me.id)
    outcome = billing.handle(store, refund(), top_up_left=left_of(180 * 60))
    assert (outcome.kind, outcome.person, outcome.detail) == (
        "refund",
        me.id,
        "180 of 180 credits taken back",
    )
    assert credits(store, me.id) == [180, -180]


def test_only_what_is_still_unused_goes_back_never_below_nothing(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    bought(store, me.id)
    # 50 credits of the top-up left unused: 50 go back, not 180.
    assert billing.handle(store, refund(), top_up_left=left_of(50 * 60)).detail == (
        "50 of 180 credits taken back"
    )
    assert credits(store, me.id) == [180, -50]
    # All used: the refund is still recorded, and takes back nothing.
    other = signed_up(store, "b@example.com")
    store.grant_credits(other.id, 60, "txn_other")
    event = refund(id="adj_01other", transaction_id="txn_other")
    assert billing.handle(store, event, top_up_left=left_of(0)).detail == (
        "0 of 60 credits taken back"
    )
    assert credits(store, other.id) == [60, 0]
    # The ledger never reads below nothing, whatever a later month spends.
    assert store.grant_seconds(other.id, int(time.time() * 1000) + 10**10, 480 * 60, 3600) >= 0


def test_a_partial_refund_takes_back_its_share(tmp_path: Path) -> None:
    """$3 of the $9 three units cost: a third of the 180 credits."""
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    bought(store, me.id)
    event = refund(type="partial", totals={"subtotal": "300", "tax": "0", "total": "300"})
    assert billing.handle(store, event, top_up_left=left_of(180 * 60)).detail == (
        "60 of 60 credits taken back"
    )
    assert credits(store, me.id) == [180, -60]


def test_a_partial_refund_in_another_currency_is_the_operators(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    bought(store, me.id)
    event = refund(type="partial", currency_code="EUR")
    outcome = billing.handle(store, event, top_up_left=left_of(180 * 60))
    assert outcome.kind == "review"
    assert credits(store, me.id) == [180], "nothing guessed"


def test_the_same_refund_twice_takes_back_once(tmp_path: Path) -> None:
    """Paddle sends `created` and then `updated` for one adjustment, and either may come
    twice: one take-back, keyed on the adjustment."""
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    bought(store, me.id)
    assert billing.handle(store, refund(), top_up_left=left_of(180 * 60)).kind == "refund"
    again = refund()
    again["event_type"] = "adjustment.created"
    assert billing.handle(store, again, top_up_left=left_of(180 * 60)).kind == "ignored"
    assert credits(store, me.id) == [180, -180]


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "pending_approval"},
        {"status": "rejected"},
        {"action": "credit"},
        {"action": "chargeback"},
    ],
)
def test_anything_but_an_approved_refund_changes_nothing(
    tmp_path: Path, changes: dict[str, str]
) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    bought(store, me.id)
    assert billing.handle(store, refund(**changes), top_up_left=left_of(180 * 60)).kind == "ignored"
    assert credits(store, me.id) == [180]


def test_a_refund_of_a_transaction_nobody_here_made_changes_nothing(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    outcome = billing.handle(
        store, refund(transaction_id="txn_unknown"), top_up_left=left_of(180 * 60)
    )
    assert outcome.kind == "unknown-account" and outcome.detail == "txn_unknown"
    assert store.db.execute("SELECT COUNT(*) FROM credit_grant").fetchone()[0] == 0


def on_plan(store: Store, who: int) -> None:
    outcome = billing.handle(store, fixture("subscription_created", who, store))
    assert outcome.kind == "plan"


def test_a_plan_payment_refunded_in_full_ends_the_plan_at_once(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    on_plan(store, me.id)
    cancelled: list[str] = []
    outcome = billing.handle(store, fixture(PLAN), cancel_now=cancelled.append)
    assert (outcome.kind, outcome.person, outcome.detail) == ("refund", me.id, "plan ended")
    held = store.person_by_id(me.id).billing  # type: ignore[union-attr]
    assert held is not None and held.status == "canceled"
    assert store.plan_ended("sub_01hv8x29kz0t586xy6zn1a62ny")
    assert cancelled == ["sub_01hv8x29kz0t586xy6zn1a62ny"], "and Paddle is asked to stop it"
    # The paid period ends where the refund did, so the Plan counts only until then.
    ends = store.db.execute("SELECT MAX(ends) FROM plan_period WHERE person = ?", (me.id,))
    assert ends.fetchone()[0] <= billing._millis("2026-11-20T09:00:00.000000Z")  # noqa: SLF001
    # The same refund again: nothing more happens, and Paddle is not asked twice.
    assert billing.handle(store, fixture(PLAN), cancel_now=cancelled.append).kind == "ignored"
    assert cancelled == ["sub_01hv8x29kz0t586xy6zn1a62ny"]
    # A later `active` for the ended subscription cannot bring it back.
    assert billing.handle(store, fixture("subscription_created", me.id, store)).kind == "ignored"


def test_a_plan_ends_here_even_when_paddle_cannot_be_reached(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    on_plan(store, me.id)

    def down(_subscription: str) -> None:
        raise billing.PaddleError("unreachable")

    outcome = billing.handle(store, fixture(PLAN), cancel_now=down)
    assert outcome.kind == "refund" and "failed" in outcome.detail
    assert store.plan_ended("sub_01hv8x29kz0t586xy6zn1a62ny")


def test_a_partial_refund_of_a_plan_payment_is_the_operators(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    on_plan(store, me.id)
    event = fixture(PLAN)
    event["data"]["type"] = "partial"
    cancelled: list[str] = []
    assert billing.handle(store, event, cancel_now=cancelled.append).kind == "review"
    assert store.person_by_id(me.id).billing.status == "active"  # type: ignore[union-attr]
    assert cancelled == []


def test_a_plan_refund_for_nobody_here_changes_nothing(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    outcome = billing.handle(store, fixture(PLAN), cancel_now=lambda _s: None)
    assert outcome.kind == "unknown-account"


def test_cancelling_at_once_asks_paddle_for_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[tuple[str, str, Any]] = []
    monkeypatch.setattr(billing, "_call", lambda m, p, b=None: asked.append((m, p, b)) or {})
    billing.cancel("sub_1", at_once=True)
    billing.cancel("sub_2")
    assert asked[0][2] == {"effective_from": "immediately"}
    assert asked[1][2] == {"effective_from": "next_billing_period"}


def test_the_route_verifies_and_takes_a_refund_once(box: tuple[int, Path, int]) -> None:  # noqa: F811
    """Signed as Paddle signs, through the live route: a refund of the top-up the box's
    reader bought is taken back once, and an unsigned one is refused."""
    port, store_path, who = box
    store = Store(store_path)
    if not store.granted_by("txn_01hv8wptq8987qeep44cyrewp9"):
        body, signature = signed(fixture("transaction_completed_top_up", who, store))
        deliver(port, body, signature)
    event = copy.deepcopy(fixture(TOP_UP))
    body = json.dumps(event).encode()
    assert deliver(port, body, None)[0] == 401
    body, signature = signed(event)
    status, answer = deliver(port, body, signature)
    assert (status, answer) == (200, {"handled": "refund"})
    again = copy.deepcopy(event)
    again["event_id"] = "evt_01hvgf2s840000000000000099"
    body, signature = signed(again)
    assert deliver(port, body, signature) == (200, {"handled": "ignored"})
    taken = [one for one in Store(store_path).top_ups(who) if one["credits"] <= 0]
    assert len(taken) == 1
