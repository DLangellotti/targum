"""The pay presses (targum-internal#59 phase 2; design.md §12, "Payments are Paddle's, by
a hosted checkout", 2026-11-15).

Start the plan and Top up are plain form posts that our server answers with a 303 to
Paddle's hosted checkout, after making a Paddle transaction for them. No page of ours
loads anything of Paddle's; the plans page names Paddle's checkout origin in its
`form-action` and nowhere else. Paddle's API is mocked: the suite is offline by force."""

from __future__ import annotations

import io
import json
import threading
import time
import urllib.error
from collections.abc import Callable, Iterator
from http.client import HTTPConnection
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest

from targum import billing, serve
from targum.accounts import Store
from targum.render.builder import plans_page

HOST = "targum.page"
CHECKOUT = "https://sandbox-pay.paddle.io/hsc_01testcheckout"
KEY = "pdl_sdbx_apikey_01test_abcdefghijklmnopqrstuvwxyz"


def configure(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        billing.API_KEY_ENV: KEY,
        billing.WEBHOOK_SECRET_ENV: "pdl_ntfset_01test",
        billing.ENVIRONMENT_ENV: "sandbox",
        billing.PRICE_MONTH_ENV: "pri_month",
        billing.PRICE_QUARTER_ENV: "pri_quarter",
        billing.PRICE_TOP_UP_ENV: "pri_top_up",
        billing.CHECKOUT_URL_ENV: CHECKOUT,
    }.items():
        monkeypatch.setenv(name, value)


def unconfigure(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        billing.API_KEY_ENV,
        billing.WEBHOOK_SECRET_ENV,
        billing.ENVIRONMENT_ENV,
        billing.PRICE_MONTH_ENV,
        billing.PRICE_QUARTER_ENV,
        billing.PRICE_TOP_UP_ENV,
        billing.CHECKOUT_URL_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


class Paddle:
    """Paddle's API as the mock answers it: every request kept, one answer each."""

    def __init__(self) -> None:
        self.asked: list[Any] = []
        self.answer: Any = {"data": {"id": "txn_01made", "status": "ready"}}

    def __call__(self, request: Any, timeout: float = 0) -> Any:
        self.asked.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        return io.BytesIO(json.dumps(self.answer).encode())

    def body(self, at: int = -1) -> dict[str, Any]:
        said: dict[str, Any] = json.loads(self.asked[at].data)
        return said


@pytest.fixture
def paddle(monkeypatch: pytest.MonkeyPatch) -> Iterator[Paddle]:
    mock = Paddle()
    monkeypatch.setattr(billing.urllib.request, "urlopen", mock)
    yield mock


# -- the settings ---------------------------------------------------------------------


def test_nothing_is_configured_until_every_setting_is_there(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unconfigure(monkeypatch)
    assert not billing.configured()
    configure(monkeypatch)
    assert billing.configured()
    for name in (
        billing.API_KEY_ENV,
        billing.WEBHOOK_SECRET_ENV,
        billing.PRICE_TOP_UP_ENV,
        billing.CHECKOUT_URL_ENV,
    ):
        configure(monkeypatch)
        monkeypatch.delenv(name)
        assert not billing.configured(), name


def test_a_key_for_the_other_environment_is_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch)
    assert billing.environment() == "sandbox" and billing.api_key() == KEY
    monkeypatch.setenv(billing.API_KEY_ENV, "pdl_live_apikey_01real")
    assert billing.api_key() == "" and not billing.configured()
    monkeypatch.setenv(billing.ENVIRONMENT_ENV, "live")
    assert billing.api_key() == "pdl_live_apikey_01real"
    monkeypatch.setenv(billing.ENVIRONMENT_ENV, "anything")
    assert billing.environment() == "sandbox", "sandbox unless it says live"


@pytest.mark.parametrize(
    "said",
    [
        "http://sandbox-pay.paddle.io/hsc_1",
        "https://pay.paddle.io.example.com/hsc_1",
        "https://example.com/hsc_1",
        "https://evilpaddle.io/hsc_1",
        "javascript:alert(1)",
    ],
)
def test_a_checkout_link_that_is_not_paddles_is_no_link(
    monkeypatch: pytest.MonkeyPatch, said: str
) -> None:
    configure(monkeypatch)
    monkeypatch.setenv(billing.CHECKOUT_URL_ENV, said)
    assert billing.checkout_url() == "" and not billing.configured()


def test_the_checkout_origin_is_paddles(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch)
    assert billing.checkout_origin() == "https://sandbox-pay.paddle.io"


# -- the call to Paddle ---------------------------------------------------------------


def test_a_checkout_makes_a_transaction_for_the_account(
    monkeypatch: pytest.MonkeyPatch, paddle: Paddle
) -> None:
    configure(monkeypatch)
    where = billing.checkout("pri_month", account=7, made=1000)
    assert where == f"{CHECKOUT}?transaction_id=txn_01made"
    request = paddle.asked[0]
    assert request.full_url == "https://sandbox-api.paddle.com/transactions"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == f"Bearer {KEY}"
    assert paddle.body() == {
        "items": [{"price_id": "pri_month", "quantity": 1}],
        "custom_data": {
            "targum_account": "7",
            "targum_tag": billing.account_tag(7, 1000, "pdl_ntfset_01test"),
        },
        "collection_mode": "automatic",
    }


def test_a_reader_who_paid_before_is_named_by_their_customer(
    monkeypatch: pytest.MonkeyPatch, paddle: Paddle
) -> None:
    configure(monkeypatch)
    billing.checkout("pri_top_up", account=7, made=1000, quantity=3, customer="ctm_1")
    assert paddle.body()["customer_id"] == "ctm_1"
    assert paddle.body()["items"] == [{"price_id": "pri_top_up", "quantity": 3}]


def test_live_calls_paddles_live_api(monkeypatch: pytest.MonkeyPatch, paddle: Paddle) -> None:
    configure(monkeypatch)
    monkeypatch.setenv(billing.ENVIRONMENT_ENV, "live")
    monkeypatch.setenv(billing.API_KEY_ENV, "pdl_live_apikey_01real")
    billing.checkout("pri_month", account=7, made=1000)
    assert paddle.asked[0].full_url == "https://api.paddle.com/transactions"


@pytest.mark.parametrize(
    "answer",
    [
        urllib.error.HTTPError("https://x", 400, "bad", {}, None),  # type: ignore[arg-type]
        urllib.error.URLError("down"),
        {"error": {"code": "forbidden"}},
        {"data": {"status": "ready"}},
    ],
)
def test_a_paddle_that_does_not_answer_is_an_error(
    monkeypatch: pytest.MonkeyPatch, paddle: Paddle, answer: Any
) -> None:
    configure(monkeypatch)
    paddle.answer = answer
    with pytest.raises(billing.PaddleError):
        billing.checkout("pri_month", account=7, made=1000)


# -- the plans page -------------------------------------------------------------------


def test_unconfigured_the_page_is_greyed_as_before() -> None:
    page = plans_page({"on": True, "plan": "free"})
    assert 'class="btn soon plan-start" disabled' in page and "Payments open soon" in page
    assert 'action="/plans/start"' not in page


def test_configured_start_is_a_form_to_our_own_server() -> None:
    page = plans_page({"on": True, "plan": "free"}, pay=True)
    assert '<form class="plan-pay" id="plan-start-form" method="post" action="/plans/start">' in (
        page
    )
    assert '<button type="submit" class="btn plan-start">Start the plan</button>' in page
    assert 'name="cadence" value="month"' in page and 'name="cadence" value="quarter"' in page
    assert "Payments open soon" not in page
    assert "paddle" not in page.lower(), "nothing of Paddle's on our page"


def test_a_comped_reader_keeps_start_greyed() -> None:
    page = plans_page({"on": True, "plan": "plan", "comp": "2027-03-04"}, pay=True)
    assert 'class="btn soon plan-start" disabled' in page


def test_a_failed_press_is_said() -> None:
    page = plans_page({"on": True, "plan": "free"}, pay=True, failed=True)
    assert "The checkout didn't open. Try again in a minute." in page


# -- the server -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def box(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> tuple[int, Path, dict[str, str]]:
    tmp = tmp_path_factory.mktemp("checkout")
    store_path = tmp / "targum.db"
    store = Store(store_path)
    sessions = {}
    for name in ("free", "paying", "comped"):
        made = store.finish_sign_in(store.start_sign_in(f"{name}@example.com"))
        assert made is not None
        sessions[name] = made[1]
    paying = store.person_by_email("paying@example.com")
    assert paying is not None
    store.set_billing(
        paying.id,
        cadence="month",
        status="active",
        period_end="2026-12-16T10:00:00Z",
        cancel_at_end=False,
        customer="ctm_paying",
        subscription="sub_paying",
    )
    store.comp("comped@example.com", "2099-01-01")
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
    return port, store_path, sessions


def press(
    port: int, path: str, form: dict[str, str], session: str = "", cross: bool = False
) -> tuple[int, dict[str, str], str]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    raw = urlencode(form).encode()
    conn.putrequest("POST", path, skip_host=True)
    conn.putheader("Host", HOST)
    conn.putheader("Content-Type", "application/x-www-form-urlencoded")
    conn.putheader("Content-Length", str(len(raw)))
    conn.putheader("Sec-Fetch-Site", "cross-site" if cross else "same-origin")
    if session:
        conn.putheader("Cookie", f"targum_session={session}")
    conn.endheaders()
    conn.send(raw)
    response = conn.getresponse()
    body = response.read().decode("utf-8", "replace")
    headers = dict(response.getheaders())
    conn.close()
    return response.status, headers, body


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


@pytest.fixture
def on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TARGUM_PLANS", "1")
    configure(monkeypatch)


def test_unconfigured_both_presses_are_not_there(
    box: tuple[int, Path, dict[str, str]], monkeypatch: pytest.MonkeyPatch, paddle: Paddle
) -> None:
    port, _, sessions = box
    monkeypatch.setenv("TARGUM_PLANS", "1")
    unconfigure(monkeypatch)
    assert press(port, serve.PLANS_START, {"cadence": "month"}, sessions["free"])[0] == 404
    assert press(port, serve.PLANS_TOP_UP, {"size": "60"}, sessions["paying"])[0] == 404
    configure(monkeypatch)
    monkeypatch.delenv("TARGUM_PLANS")
    assert press(port, serve.PLANS_START, {"cadence": "month"}, sessions["free"])[0] == 404
    assert paddle.asked == []


def test_unconfigured_the_plans_page_keeps_form_action_self(
    box: tuple[int, Path, dict[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, _, sessions = box
    monkeypatch.setenv("TARGUM_PLANS", "1")
    unconfigure(monkeypatch)
    status, headers, page = fetch(port, "/plans", sessions["free"])
    assert status == 200 and "form-action 'self';" in headers["Content-Security-Policy"]
    assert "Payments open soon" in page


@pytest.mark.usefixtures("on")
def test_configured_the_plans_page_names_paddles_checkout_and_only_it(
    box: tuple[int, Path, dict[str, str]],
) -> None:
    port, _, sessions = box
    status, headers, page = fetch(port, "/plans", sessions["free"])
    policy = headers["Content-Security-Policy"]
    assert status == 200 and "form-action 'self' https://sandbox-pay.paddle.io;" in policy
    for directive in ("script-src", "style-src", "img-src", "font-src", "connect-src"):
        clause = next(one for one in policy.split(";") if one.strip().startswith(directive))
        assert "paddle" not in clause, directive
    assert "frame-src" not in policy or "paddle" not in policy.split("frame-src")[1]
    assert 'action="/plans/start"' in page
    # Every other page keeps `form-action 'self'`.
    _, account, _ = fetch(port, "/account", sessions["free"])
    assert "paddle" not in account.get("Content-Security-Policy", "")


@pytest.mark.usefixtures("on")
def test_start_sends_a_free_reader_to_paddles_checkout(
    box: tuple[int, Path, dict[str, str]], paddle: Paddle
) -> None:
    port, store_path, sessions = box
    status, headers, _ = press(port, serve.PLANS_START, {"cadence": "quarter"}, sessions["free"])
    assert status == 303
    assert headers["Location"] == f"{CHECKOUT}?transaction_id=txn_01made"
    me = Store(store_path).person_by_email("free@example.com")
    assert me is not None
    assert paddle.body()["items"] == [{"price_id": "pri_quarter", "quantity": 1}]
    made = Store(store_path).db.execute("SELECT made FROM person WHERE id = ?", (me.id,))
    tag = billing.account_tag(me.id, int(made.fetchone()[0]))
    assert paddle.body()["custom_data"] == {"targum_account": str(me.id), "targum_tag": tag}
    assert "customer_id" not in paddle.body()


@pytest.mark.usefixtures("on")
def test_start_refuses_a_cadence_it_does_not_know_and_a_reader_already_paying(
    box: tuple[int, Path, dict[str, str]], paddle: Paddle
) -> None:
    port, _, sessions = box
    status, headers, _ = press(port, serve.PLANS_START, {"cadence": "year"}, sessions["free"])
    assert (status, headers["Location"]) == (303, "/plans")
    status, headers, _ = press(port, serve.PLANS_START, {"cadence": "month"}, sessions["paying"])
    assert (status, headers["Location"]) == (303, "/plans")
    assert paddle.asked == []


@pytest.mark.usefixtures("on")
def test_top_up_is_for_a_reader_on_plan(
    box: tuple[int, Path, dict[str, str]], paddle: Paddle
) -> None:
    port, _, sessions = box
    status, headers, _ = press(port, serve.PLANS_TOP_UP, {"size": "180"}, sessions["paying"])
    assert status == 303 and headers["Location"].startswith(CHECKOUT)
    assert paddle.body()["items"] == [{"price_id": "pri_top_up", "quantity": 3}]
    assert paddle.body()["customer_id"] == "ctm_paying"
    # No top-up on Free; a size that is not one of the three is no press.
    status, headers, _ = press(port, serve.PLANS_TOP_UP, {"size": "60"}, sessions["free"])
    assert (status, headers["Location"]) == (303, "/account")
    for size in ("120", "0", "", "lots"):
        status, headers, _ = press(port, serve.PLANS_TOP_UP, {"size": size}, sessions["paying"])
        assert (status, headers["Location"]) == (303, "/account"), size
    assert len(paddle.asked) == 1


@pytest.mark.usefixtures("on")
def test_a_comped_reader_may_top_up(box: tuple[int, Path, dict[str, str]], paddle: Paddle) -> None:
    port, _, sessions = box
    status, _, _ = press(port, serve.PLANS_TOP_UP, {"size": "60"}, sessions["comped"])
    assert status == 303 and paddle.body()["items"][0]["quantity"] == 1


@pytest.mark.usefixtures("on")
def test_a_press_from_another_site_or_nobody_is_refused(
    box: tuple[int, Path, dict[str, str]], paddle: Paddle
) -> None:
    port, _, sessions = box
    status, _, _ = press(port, serve.PLANS_START, {"cadence": "month"}, sessions["free"], True)
    assert status == 403
    status, _, _ = press(port, serve.PLANS_START, {"cadence": "month"})
    assert status in (303, 401, 403)
    assert paddle.asked == []


@pytest.mark.usefixtures("on")
def test_a_paddle_that_does_not_answer_goes_back_to_plans(
    box: tuple[int, Path, dict[str, str]], paddle: Paddle
) -> None:
    port, _, sessions = box
    paddle.answer = urllib.error.URLError("down")
    status, headers, _ = press(port, serve.PLANS_START, {"cadence": "month"}, sessions["free"])
    assert (status, headers["Location"]) == (303, "/plans?pay=failed")
    _, _, page = fetch(port, "/plans?pay=failed", sessions["free"])
    assert "The checkout didn't open." in page


def test_cancel_asks_paddle_to_end_at_the_period_paid_for(
    monkeypatch: pytest.MonkeyPatch, paddle: Paddle
) -> None:
    configure(monkeypatch)
    billing.cancel("sub_01x")
    request = paddle.asked[0]
    assert request.full_url == "https://sandbox-api.paddle.com/subscriptions/sub_01x/cancel"
    assert paddle.body() == {"effective_from": "next_billing_period"}
    with pytest.raises(billing.PaddleError):
        billing.cancel("")


@pytest.mark.usefixtures("on")
def test_closing_an_account_cancels_its_paddle_plan(
    box: tuple[int, Path, dict[str, str]], paddle: Paddle
) -> None:
    """qa-claude on #1279: an account deleted under a live subscription leaves the
    reader paying. Closing it asks Paddle to cancel; the purge waits for Paddle."""
    port, store_path, sessions = box
    store = Store(store_path)
    made = store.finish_sign_in(store.start_sign_in("leaving@example.com"))
    assert made is not None
    me = store.person_by_email("leaving@example.com")
    assert me is not None
    store.set_billing(
        me.id,
        cadence="month",
        status="active",
        period_end="2026-12-16T10:00:00Z",
        cancel_at_end=False,
        customer="ctm_leaving",
        subscription="sub_leaving",
    )
    status, _, _ = press(port, "/account/forget", {}, made[1])
    assert status < 400
    assert paddle.asked[-1].full_url.endswith("/subscriptions/sub_leaving/cancel")
    assert store.purge(days=0) == [], "the purge waits for Paddle's canceled"


def test_the_purge_sweep_asks_again_for_a_plan_that_has_not_ended(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, paddle: Paddle
) -> None:
    """qa-claude on #1279: a cancel that failed at closing, or a paused plan, would keep
    the account waiting for ever. Each sweep asks Paddle again."""
    configure(monkeypatch)
    store = Store(tmp_path / "targum.db")
    library = serve.Library(tmp_path / "out", max_cost=1.0, budget=1.0, store=store)
    made = store.finish_sign_in(store.start_sign_in("gone@example.com"))
    assert made is not None
    me = store.person_by_email("gone@example.com")
    assert me is not None
    store.set_billing(
        me.id,
        cadence="month",
        status="paused",
        period_end="",
        cancel_at_end=False,
        customer="ctm_gone",
        subscription="sub_gone",
    )
    store.db.execute("UPDATE person SET leaving = 1 WHERE id = ?", (me.id,))
    assert library.purge_departed() == []
    assert paddle.asked[-1].full_url.endswith("/subscriptions/sub_gone/cancel")
    # A Paddle that does not answer is written down, and the sweep goes on.
    paddle.answer = urllib.error.URLError("down")
    assert library.purge_departed() == []
    assert (tmp_path / "out" / "incidents.jsonl").read_text().count("billing-cancel") == 1
