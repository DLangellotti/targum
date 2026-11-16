"""Paddle's webhook (targum-internal#59 phase 2; design.md §12, "Payments are Paddle's, by
a hosted checkout", 2026-11-15).

Every event here is a fixture shaped as Paddle's documentation draws it, signed the way
Paddle signs (`Paddle-Signature: ts=…;h1=…`, an HMAC-SHA256 of `ts:body`). Nothing talks
to Paddle: the suite is offline by force."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from targum import billing, plans, serve
from targum.accounts import Person, Store

HOST = "targum.page"
SECRET = "pdl_ntfset_01testsecret_abcdefghijklmnopqrstuvwxyz"
EVENTS = Path(__file__).parent / "fixtures" / "paddle"


@pytest.fixture(autouse=True)
def paddle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(billing.WEBHOOK_SECRET_ENV, SECRET)
    monkeypatch.setenv(billing.PRICE_MONTH_ENV, "pri_month")
    monkeypatch.setenv(billing.PRICE_QUARTER_ENV, "pri_quarter")
    monkeypatch.setenv(billing.PRICE_TOP_UP_ENV, "pri_top_up")


def fixture(name: str, account: int | None = None, store: Store | None = None) -> dict[str, Any]:
    """A fixture event, its `custom_data` naming `account` with the tag our checkout
    writes where `store` holds that account, as `/plans/start` would have made it."""
    raw = (EVENTS / f"{name}.json").read_text()
    if account is not None:
        raw = raw.replace('"ACCOUNT"', f'"{account}"')
    event: dict[str, Any] = json.loads(raw)
    custom = event["data"].get("custom_data")
    if isinstance(custom, dict) and account is not None and store is not None:
        made = store.db.execute("SELECT made FROM person WHERE id = ?", (account,)).fetchone()
        if made is not None:
            custom[billing.TAG_KEY] = billing.account_tag(account, int(made[0]))
    return event


def signed_up(store: Store, email: str) -> Person:
    assert store.finish_sign_in(store.start_sign_in(email)) is not None
    me = store.person_by_email(email)
    assert me is not None
    return me


def reloaded(store: Store, me: Person) -> Person:
    again = store.person_by_id(me.id)
    assert again is not None
    return again


# -- the signature --------------------------------------------------------------------


def test_a_signature_paddle_made_is_believed() -> None:
    body = b'{"event_id":"evt_1"}'
    at = int(time.time())
    assert billing.verify(billing.sign(body, SECRET, at), body, SECRET) == ""


def test_a_rotated_secret_is_believed_on_any_h1() -> None:
    body = b'{"event_id":"evt_1"}'
    at = int(time.time())
    old = billing.sign(body, "pdl_ntfset_old", at).split(";")[1]
    header = f"{billing.sign(body, SECRET, at)};{old}"
    assert billing.verify(header, body, SECRET) == ""
    assert billing.verify(header, body, "pdl_ntfset_old") == ""


@pytest.mark.parametrize(
    ("header", "why"),
    [
        (None, "unsigned"),
        ("", "unsigned"),
        ("h1=abc", "unsigned"),
        ("ts=nope;h1=abc", "unsigned"),
        ("ts=NOW", "unsigned"),
    ],
)
def test_a_missing_or_broken_signature_is_refused(header: str | None, why: str) -> None:
    body = b"{}"
    said = header.replace("NOW", str(int(time.time()))) if header else header
    assert billing.verify(said, body, SECRET) == why


@pytest.mark.parametrize("header", ["ts=\u00b2;h1=abc", "ts=\u0661\u0662;h1=abc"])
def test_a_timestamp_that_is_not_ascii_digits_is_unsigned(header: str) -> None:
    """qa-claude on #1280: "²".isdigit() is true and int("²") raises."""
    assert billing.verify(header, b"{}", SECRET) == "unsigned"


def test_a_signature_that_is_not_ascii_is_forged() -> None:
    header = f"ts={int(time.time())};h1=\u00e9\u00e9\u00e9"
    assert billing.verify(header, b"{}", SECRET) == "forged"


def test_a_body_changed_after_signing_is_forged() -> None:
    at = int(time.time())
    header = billing.sign(b'{"a":1}', SECRET, at)
    assert billing.verify(header, b'{"a": 1}', SECRET) == "forged"
    assert billing.verify(header, b'{"a":1}', "pdl_ntfset_another") == "forged"


def test_a_signature_older_or_newer_than_the_tolerance_is_stale() -> None:
    body = b"{}"
    now = 2_000_000_000
    fresh = billing.sign(body, SECRET, now - billing.TOLERANCE_SECONDS)
    assert billing.verify(fresh, body, SECRET, at=now) == ""
    old = billing.sign(body, SECRET, now - billing.TOLERANCE_SECONDS - 1)
    assert billing.verify(old, body, SECRET, at=now) == "stale"
    ahead = billing.sign(body, SECRET, now + billing.TOLERANCE_SECONDS + 1)
    assert billing.verify(ahead, body, SECRET, at=now) == "stale"


def test_no_secret_believes_nothing() -> None:
    body = b"{}"
    assert billing.verify(billing.sign(body, "", int(time.time())), body, "") == "unconfigured"


# -- what each event does --------------------------------------------------------------


def test_subscription_created_puts_the_reader_on_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    assert plans.free(me)
    outcome = billing.handle(store, fixture("subscription_created", me.id, store))
    assert outcome.kind == "plan" and outcome.person == me.id
    me = reloaded(store, me)
    assert me.billing is not None
    assert me.billing.status == "active" and me.billing.cadence == "month"
    assert me.billing.period_end == "2026-12-16T10:00:00.000Z"
    assert me.billing.customer.startswith("ctm_") and me.billing.subscription.startswith("sub_")
    assert plans.paid(me) and not plans.free(me)


def test_a_quarter_is_read_from_its_price(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    billing.handle(store, fixture("subscription_created_quarter", me.id, store))
    assert reloaded(store, me).billing.cadence == "quarter"  # type: ignore[union-attr]


def test_a_subscription_to_a_price_that_is_not_plans_is_not_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """qa-claude on #1280: only PADDLE_PRICE_MONTH or PADDLE_PRICE_QUARTER is Plan, so a
    subscription to any other price in the catalogue changes nothing."""
    monkeypatch.setenv(billing.PRICE_QUARTER_ENV, "pri_renamed")
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    outcome = billing.handle(store, fixture("subscription_created_quarter", me.id, store))
    assert outcome.kind == "ignored" and outcome.detail == "not Plan's price"
    assert reloaded(store, me).billing is None


def test_a_paid_period_is_kept(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    billing.handle(store, fixture("subscription_created", me.id, store))
    row = store.db.execute("SELECT subscription, starts, ends FROM plan_period").fetchone()
    assert row[0].startswith("sub_") and row[2] - row[1] == 30 * 86_400_000


def test_custom_data_without_our_tag_names_nobody(tmp_path: Path) -> None:
    """qa-claude on #1280: an id in `custom_data` is only believed with the tag our
    checkout writes, so a checkout made elsewhere cannot subscribe another reader."""
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    forged = fixture("subscription_created", me.id)
    assert billing.handle(store, forged).kind == "unknown-account"
    forged["data"]["custom_data"][billing.TAG_KEY] = "0" * 32
    assert billing.handle(store, forged).kind == "unknown-account"
    assert reloaded(store, me).billing is None


def test_a_tag_made_for_an_earlier_account_with_the_same_id_names_nobody(
    tmp_path: Path,
) -> None:
    """qa-claude on #1279: an id given again must not inherit a payment. The tag is made
    over the id and the moment the account was made, so it names only that account."""
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    event = fixture("transaction_completed_top_up", me.id, store)
    store.db.execute("UPDATE person SET made = made + 1 WHERE id = ?", (me.id,))
    assert billing.handle(store, event).kind == "unknown-account"


def test_a_tag_under_the_previous_secret_is_believed_while_it_rotates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    event = fixture("transaction_completed_top_up", me.id, store)
    monkeypatch.setenv(billing.WEBHOOK_SECRET_ENV, "pdl_ntfset_new")
    assert billing.handle(store, event).kind == "unknown-account"
    monkeypatch.setenv(billing.WEBHOOK_SECRET_PREVIOUS_ENV, SECRET)
    assert billing.handle(store, event).kind == "top-up"


def test_a_cancel_at_once_trims_the_paid_period(tmp_path: Path) -> None:
    """qa-claude on #1279: a plan cancelled at once (or refunded and cancelled) counts
    as Plan only until Paddle's `canceled_at`."""
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    billing.handle(store, fixture("subscription_created", me.id, store))
    at_once = fixture("subscription_canceled", me.id, store)
    at_once["data"]["canceled_at"] = "2026-11-16T11:00:00.000Z"
    billing.handle(store, at_once)
    row = store.db.execute("SELECT starts, ends FROM plan_period").fetchone()
    assert row[1] - row[0] == 3_600_000


def test_the_held_subscription_wins_over_custom_data(tmp_path: Path) -> None:
    """What the store already holds comes first: a subscription keeps its account
    whatever a later event's `custom_data` names."""
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    other = signed_up(store, "b@example.com")
    billing.handle(store, fixture("subscription_created", me.id, store))
    moved = fixture("subscription_updated_cancel", other.id, store)
    assert billing.handle(store, moved).person == me.id
    assert reloaded(store, other).billing is None


def test_an_old_subscriptions_cancel_does_not_end_a_new_one(tmp_path: Path) -> None:
    """qa-claude on #1280: two subscriptions (a Start pressed twice, a plan after a
    lapsed one). The older one's `canceled` arriving later changes nothing."""
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    billing.handle(store, fixture("subscription_created", me.id, store))
    second = fixture("subscription_created_quarter", me.id, store)
    second["data"]["id"] = "sub_second"
    second["event_id"] = "evt_second"
    second["occurred_at"] = "2026-11-17T10:00:00.000Z"
    assert billing.handle(store, second).kind == "plan"
    old_cancel = fixture("subscription_canceled", me.id, store)
    assert billing.handle(store, old_cancel).kind == "ignored"
    held = reloaded(store, me).billing
    assert held is not None and held.subscription == "sub_second" and held.status == "active"


def test_cancelling_runs_to_the_period_end_and_then_ends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    billing.handle(store, fixture("subscription_created", me.id, store))
    billing.handle(store, fixture("subscription_updated_cancel", me.id, store))
    me = reloaded(store, me)
    assert me.billing is not None and me.billing.cancel_at_end and plans.paid(me)
    billing.handle(store, fixture("subscription_canceled", me.id, store))
    me = reloaded(store, me)
    assert me.billing is not None and me.billing.status == "canceled"
    assert not plans.paid(me) and plans.free(me)


def test_an_event_delivered_late_does_not_undo_a_newer_one(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    billing.handle(store, fixture("subscription_canceled", me.id, store))
    late = billing.handle(store, fixture("subscription_created", me.id, store))
    assert late.kind == "ignored" and late.detail == "stale"
    assert reloaded(store, me).billing.status == "canceled"  # type: ignore[union-attr]


def test_an_event_without_custom_data_finds_the_reader_by_subscription(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    billing.handle(store, fixture("subscription_created", me.id, store))
    unnamed = fixture("subscription_past_due")
    unnamed["data"]["custom_data"] = None
    assert billing.handle(store, unnamed).person == me.id


def test_an_event_for_nobody_here_changes_nothing(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    signed_up(store, "a@example.com")
    outcome = billing.handle(store, fixture("subscription_created", 999))
    assert outcome.kind == "unknown-account"
    assert store.db.execute("SELECT COUNT(*) FROM plan").fetchone()[0] == 0


def test_past_due_is_plan_for_the_grace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    billing.handle(store, fixture("subscription_created", me.id, store))
    billing.handle(store, fixture("subscription_past_due", me.id, store))
    me = reloaded(store, me)
    assert me.billing is not None and me.billing.status == "past_due"
    assert me.billing.past_due_since is not None and plans.paid(me)


def test_a_failed_renewal_starts_the_grace(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    billing.handle(store, fixture("subscription_created", me.id, store))
    outcome = billing.handle(store, fixture("transaction_payment_failed_renewal"))
    assert outcome.kind == "grace" and outcome.person == me.id
    me = reloaded(store, me)
    assert me.billing is not None and me.billing.status == "past_due"
    assert me.billing.cadence == "month" and me.billing.subscription.startswith("sub_")
    # Said twice, the clock does not restart.
    again = billing.handle(store, fixture("transaction_payment_failed_renewal"))
    assert again.kind == "ignored"


def test_a_card_refused_at_the_checkout_changes_nothing(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    billing.handle(store, fixture("subscription_created", me.id, store))
    outcome = billing.handle(store, fixture("transaction_payment_failed_checkout", me.id, store))
    assert outcome.kind == "ignored"
    assert reloaded(store, me).billing.status == "active"  # type: ignore[union-attr]


def test_a_top_up_paid_for_grants_its_credits_once(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    outcome = billing.handle(store, fixture("transaction_completed_top_up", me.id, store))
    assert outcome.kind == "top-up" and outcome.detail == "180"
    assert [one["credits"] for one in store.top_ups(me.id)] == [180]
    assert (
        billing.handle(store, fixture("transaction_completed_top_up", me.id, store)).kind
        == "ignored"
    )
    assert [one["credits"] for one in store.top_ups(me.id)] == [180]


def test_a_plans_own_payment_grants_nothing(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    assert (
        billing.handle(store, fixture("transaction_completed_plan", me.id, store)).kind == "ignored"
    )
    assert store.top_ups(me.id) == []


def test_another_event_is_ignored(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    event = fixture("subscription_created", 1)
    event["event_type"] = "customer.updated"
    assert billing.handle(store, event).kind == "ignored"


def test_no_money_and_no_card_is_kept(tmp_path: Path) -> None:
    """Paddle is the merchant of record: the store keeps Paddle's ids, the status, the
    cadence and the dates, and nothing the event says of money or of the card."""
    store = Store(tmp_path / "targum.db")
    me = signed_up(store, "a@example.com")
    for name in ("subscription_created", "transaction_completed_top_up"):
        billing.handle(store, fixture(name, me.id, store))
    kept = json.dumps(
        [
            [dict(row) for row in store.db.execute(f"SELECT * FROM {table}")]  # noqa: S608
            for table in ("plan", "credit_grant", "billing_event")
        ]
    )
    for said in ("1600", "900", "4242", "visa", "USD", "add_01", "inv_01"):
        assert said not in kept, said


# -- the route ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def box(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> tuple[int, Path, int]:
    tmp = tmp_path_factory.mktemp("billing")
    store_path = tmp / "targum.db"
    store = Store(store_path)
    me = signed_up(store, "paying@example.com")
    port = free_port()
    threading.Thread(
        target=lambda: serve.start(
            out=tmp / "out",
            port=port,
            open_browser=False,
            store=store_path,
            require_account=True,
            public_address=f"https://{HOST}",
        ),
        daemon=True,
    ).start()
    for _ in range(60):
        try:
            probe = HTTPConnection("127.0.0.1", port, timeout=1)
            probe.request("GET", "/health")
            probe.getresponse().read()
            probe.close()
            break
        except OSError:
            time.sleep(0.1)
    return port, store_path, me.id


def deliver(port: int, body: bytes, signature: str | None) -> tuple[int, Any]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest("POST", serve.BILLING_HOOK, skip_host=True)
    conn.putheader("Host", HOST)
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", str(len(body)))
    if signature is not None:
        conn.putheader("Paddle-Signature", signature)
    conn.endheaders()
    conn.send(body)
    response = conn.getresponse()
    got = response.read()
    conn.close()
    try:
        return response.status, json.loads(got)
    except json.JSONDecodeError:
        return response.status, got.decode("utf-8", "replace")


def signed(event: dict[str, Any]) -> tuple[bytes, str]:
    body = json.dumps(event).encode()
    return body, billing.sign(body, SECRET, int(time.time()))


def test_without_a_secret_the_route_is_not_there(
    box: tuple[int, Path, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store_path, who = box
    monkeypatch.delenv(billing.WEBHOOK_SECRET_ENV)
    body, signature = signed(fixture("subscription_created", who, Store(store_path)))
    assert deliver(port, body, signature)[0] == 404


def test_the_route_takes_a_signed_event_once(box: tuple[int, Path, int]) -> None:
    port, store_path, who = box
    body, signature = signed(fixture("transaction_completed_top_up", who, Store(store_path)))
    status, answer = deliver(port, body, signature)
    assert (status, answer) == (200, {"handled": "top-up"})
    # Paddle sends it again, freshly signed: seen, and nothing more is granted.
    body, signature = signed(fixture("transaction_completed_top_up", who, Store(store_path)))
    assert deliver(port, body, signature) == (200, {"seen": True})
    assert [one["credits"] for one in Store(store_path).top_ups(who)] == [180]


def test_the_route_refuses_what_paddle_did_not_sign(box: tuple[int, Path, int]) -> None:
    port, store_path, who = box
    event = fixture("subscription_created", who, Store(store_path))
    event["event_id"] = "evt_forged"
    body, _ = signed(event)
    assert deliver(port, body, None)[0] == 401
    assert deliver(port, body, billing.sign(body, "pdl_ntfset_wrong", int(time.time())))[0] == 401
    stale = billing.sign(body, SECRET, int(time.time()) - 3600)
    assert deliver(port, body, stale) == (401, {"error": "stale"})
    assert Store(store_path).billing(who) is None
    # Refused, so not marked seen: Paddle's real delivery of it is still handled.
    assert deliver(port, body, billing.sign(body, SECRET, int(time.time())))[0] == 200


def test_the_route_answers_401_for_a_header_it_cannot_read(box: tuple[int, Path, int]) -> None:
    port, _, _ = box
    body = b'{"event_id": "evt_odd"}'
    assert deliver(port, body, "ts=\u00b2;h1=abc")[0] == 401


def test_the_route_refuses_a_body_that_is_too_large_and_closes(box: tuple[int, Path, int]) -> None:
    port, _, _ = box
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest("POST", serve.BILLING_HOOK, skip_host=True)
    conn.putheader("Host", HOST)
    conn.putheader("Content-Length", str(billing.MOST_BODY_BYTES + 1))
    conn.endheaders()
    conn.send(b"x" * (billing.MOST_BODY_BYTES + 1))
    response = conn.getresponse()
    response.read()
    assert response.status == 413
    # The server closed its end rather than reading on into the body it refused.
    assert conn.sock is None or conn.sock.recv(1) == b""
    conn.close()


def test_the_route_refuses_a_body_that_is_not_an_event(box: tuple[int, Path, int]) -> None:
    port, _, _ = box
    for body in (b"not json", b"[]", b'{"event_type": "subscription.created"}'):
        assert deliver(port, body, billing.sign(body, SECRET, int(time.time())))[0] == 400


def test_an_event_whose_handling_fails_is_handled_on_the_retry(
    box: tuple[int, Path, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store_path, who = box
    event = fixture("subscription_created_quarter", who, Store(store_path))
    event["event_id"] = "evt_fails_once"
    real = billing.handle
    calls: list[str] = []

    def once(store: Store, said: dict[str, Any]) -> billing.Outcome:
        calls.append(str(said["event_id"]))
        if len(calls) == 1:
            raise RuntimeError("the disk was full")
        return real(store, said)

    monkeypatch.setattr(billing, "handle", once)
    body, signature = signed(event)
    assert deliver(port, body, signature) == (500, {"error": "not handled"})
    body, signature = signed(event)
    assert deliver(port, body, signature) == (200, {"handled": "plan"})
    assert len(calls) == 2
