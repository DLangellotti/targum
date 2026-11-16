"""Manage, on Your account (targum-internal#59 phase 2, item 9): the renewal day, and a
link into Paddle's customer portal that our server makes as the reader presses it. The
portal's link is never kept. Paddle's API is mocked: the suite is offline by force."""

from __future__ import annotations

import io
import json
import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest

from targum import billing, plans, serve
from targum.accounts import Person, Store

HOST = "targum.page"
PORTAL = "https://sandbox-customer-portal.paddle.com/cpl_01test?action=overview&token=pga_x"
VIEW = (
    "https://sandbox-customer-portal.paddle.com/cpl_01test?action=view_subscription"
    "&subscription_id=sub_paying&token=pga_y"
)


def configure(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        billing.API_KEY_ENV: "pdl_sdbx_apikey_01test",
        billing.WEBHOOK_SECRET_ENV: "pdl_ntfset_01test",
        billing.PRICE_MONTH_ENV: "pri_month",
        billing.PRICE_QUARTER_ENV: "pri_quarter",
        billing.PRICE_TOP_UP_ENV: "pri_top_up",
        billing.CHECKOUT_URL_ENV: "https://sandbox-pay.paddle.io/hsc_01test",
    }.items():
        monkeypatch.setenv(name, value)


class Paddle:
    def __init__(self) -> None:
        self.asked: list[Any] = []
        self.answer: Any = {
            "data": {
                "id": "cpls_01",
                "customer_id": "ctm_paying",
                "urls": {
                    "general": {"overview": PORTAL},
                    "subscriptions": [
                        {
                            "id": "sub_paying",
                            "cancel_subscription": VIEW.replace("view_", "cancel_"),
                            "update_subscription_payment_method": VIEW,
                            "view_subscription": VIEW,
                        }
                    ],
                },
            }
        }

    def __call__(self, request: Any, timeout: float = 0) -> Any:
        self.asked.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        return io.BytesIO(json.dumps(self.answer).encode())


@pytest.fixture
def paddle(monkeypatch: pytest.MonkeyPatch) -> Iterator[Paddle]:
    mock = Paddle()
    monkeypatch.setattr(billing.urllib.request, "urlopen", mock)
    yield mock


def paying(store: Store, email: str, **said: Any) -> Person:
    assert store.finish_sign_in(store.start_sign_in(email)) is not None
    me = store.person_by_email(email)
    assert me is not None
    store.set_billing(
        me.id,
        cadence=str(said.get("cadence", "month")),
        status=str(said.get("status", "active")),
        period_end=str(said.get("period_end", "2026-12-16T10:00:00.000Z")),
        cancel_at_end=bool(said.get("cancel_at_end", False)),
        customer="ctm_paying",
        subscription="sub_paying",
    )
    again = store.person_by_id(me.id)
    assert again is not None
    return again


# -- the portal call ------------------------------------------------------------------


def test_the_portal_opens_on_the_subscription(
    monkeypatch: pytest.MonkeyPatch, paddle: Paddle
) -> None:
    configure(monkeypatch)
    assert billing.portal("ctm_paying", "sub_paying") == VIEW
    request = paddle.asked[0]
    assert request.full_url == "https://sandbox-api.paddle.com/customers/ctm_paying/portal-sessions"
    assert json.loads(request.data) == {"subscription_ids": ["sub_paying"]}


def test_without_a_subscription_the_portal_opens_on_its_overview(
    monkeypatch: pytest.MonkeyPatch, paddle: Paddle
) -> None:
    configure(monkeypatch)
    assert billing.portal("ctm_paying") == PORTAL
    assert json.loads(paddle.asked[0].data) == {}


@pytest.mark.parametrize(
    "link", ["http://customer-portal.paddle.com/x", "https://example.com/x", "", "javascript:1"]
)
def test_a_link_that_is_not_paddles_is_refused(
    monkeypatch: pytest.MonkeyPatch, paddle: Paddle, link: str
) -> None:
    configure(monkeypatch)
    paddle.answer = {"data": {"urls": {"general": {"overview": link}, "subscriptions": []}}}
    with pytest.raises(billing.PaddleError):
        billing.portal("ctm_paying")


def test_no_customer_is_no_portal(monkeypatch: pytest.MonkeyPatch, paddle: Paddle) -> None:
    configure(monkeypatch)
    with pytest.raises(billing.PaddleError):
        billing.portal("")
    assert paddle.asked == []


# -- what Your account is told -----------------------------------------------------------


def test_the_summary_says_when_a_paddle_plan_renews(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    me = paying(store, "a@example.com", cadence="quarter")
    said = plans.summary(me, manage=True)
    assert said["plan"] == "plan" and said["credits"] == 480
    assert said["billed"] == {
        "cadence": "quarter",
        "ending": False,
        "manage": True,
        "renews": "2026-12-16",
        "renewsSaid": "December 16, 2026",
    }
    assert plans.summary(me, manage=False)["billed"]["manage"] is False
    assert "$" not in json.dumps(said), "no money on Your account"


def test_the_summary_says_a_cancel_and_a_grace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    ending = paying(store, "a@example.com", cancel_at_end=True)
    assert plans.summary(ending)["billed"]["ending"] is True
    late = paying(store, "b@example.com", status="past_due")
    assert late.billing is not None and late.billing.past_due_since is not None
    grace = datetime.fromtimestamp(late.billing.past_due_since / 1000, UTC) + timedelta(
        days=plans.GRACE_DAYS
    )
    assert plans.summary(late, language="ru")["billed"]["graceSaid"] == plans.until_said(
        grace.date().isoformat(), "ru"
    )


def test_a_plan_that_no_longer_holds_says_nothing_of_paddle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    store = Store(tmp_path / "targum.db")
    gone = paying(store, "a@example.com", status="canceled")
    assert "billed" not in plans.summary(gone) and plans.summary(gone)["plan"] == "free"


# -- the route ------------------------------------------------------------------------


@pytest.fixture(scope="module")
def box(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> tuple[int, dict[str, str]]:
    tmp = tmp_path_factory.mktemp("manage")
    store_path = tmp / "targum.db"
    store = Store(store_path)
    sessions = {}
    for name in ("paying", "never"):
        made = store.finish_sign_in(store.start_sign_in(f"{name}@example.com"))
        assert made is not None
        sessions[name] = made[1]
    me = store.person_by_email("paying@example.com")
    assert me is not None
    store.set_billing(
        me.id,
        cadence="month",
        status="active",
        period_end="2026-12-16T10:00:00Z",
        cancel_at_end=False,
        customer="ctm_paying",
        subscription="sub_paying",
    )
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
    return port, sessions


def fetch(port: int, path: str, session: str) -> tuple[int, dict[str, str], str]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest("GET", path, skip_host=True)
    conn.putheader("Host", HOST)
    conn.putheader("Cookie", f"targum_session={session}")
    conn.endheaders()
    response = conn.getresponse()
    body = response.read().decode("utf-8", "replace")
    headers = dict(response.getheaders())
    conn.close()
    return response.status, headers, body


def test_unconfigured_manage_is_not_there(
    box: tuple[int, dict[str, str]], monkeypatch: pytest.MonkeyPatch, paddle: Paddle
) -> None:
    port, sessions = box
    for name in (billing.API_KEY_ENV, billing.CHECKOUT_URL_ENV):
        monkeypatch.delenv(name, raising=False)
    assert fetch(port, serve.PLANS_MANAGE, sessions["paying"])[0] == 404
    assert paddle.asked == []


def test_manage_sends_a_paying_reader_to_paddles_portal(
    box: tuple[int, dict[str, str]], monkeypatch: pytest.MonkeyPatch, paddle: Paddle
) -> None:
    port, sessions = box
    configure(monkeypatch)
    status, headers, _ = fetch(port, serve.PLANS_MANAGE, sessions["paying"])
    assert (status, headers["Location"]) == (303, VIEW)
    assert headers["Cache-Control"] == "no-store"


def test_manage_sends_a_reader_who_never_paid_to_plans(
    box: tuple[int, dict[str, str]], monkeypatch: pytest.MonkeyPatch, paddle: Paddle
) -> None:
    port, sessions = box
    configure(monkeypatch)
    status, headers, _ = fetch(port, serve.PLANS_MANAGE, sessions["never"])
    assert (status, headers["Location"]) == (303, "/plans")
    assert paddle.asked == []


def test_a_paddle_that_does_not_answer_goes_back_to_your_account(
    box: tuple[int, dict[str, str]], monkeypatch: pytest.MonkeyPatch, paddle: Paddle
) -> None:
    port, sessions = box
    configure(monkeypatch)
    paddle.answer = OSError("down")
    status, headers, _ = fetch(port, serve.PLANS_MANAGE, sessions["paying"])
    assert (status, headers["Location"]) == (303, "/account?manage=failed")


def test_your_account_is_told_the_renewal_and_keeps_form_action_self(
    box: tuple[int, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, sessions = box
    configure(monkeypatch)
    monkeypatch.setenv("TARGUM_PLANS", "1")
    status, _, body = fetch(port, "/account/me", sessions["paying"])
    billed = json.loads(body)["plan"]["billed"]
    assert billed["renewsSaid"] == "December 16, 2026" and billed["manage"] is True
    _, headers, _ = fetch(port, "/account", sessions["paying"])
    assert "paddle" not in headers.get("Content-Security-Policy", "")
