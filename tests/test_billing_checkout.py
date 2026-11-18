"""The pay presses (targum-internal#59 phase 2; design.md §12, "Payments are Paddle's, by
a hosted checkout", 2026-11-15).

Start the plan and Top up are plain form posts that our server answers with a 303 to
Paddle's hosted checkout, after making a Paddle transaction for them. No page of ours
loads anything of Paddle's; the plans page names Paddle's checkout origin in its
`form-action` and nowhere else. Paddle's API is mocked: the suite is offline by force.

Since 2026-11-17 (David) the checkout is Paddle's overlay, opened by Paddle.js on the one
view of `/plans` our server sends after a press: that view alone names Paddle's origins
in its policy, and every other page, `/plans` included, names none."""

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
TOKEN = "test_0123456789abcdef0123456789a"
TXN = "txn_01hv8wptq8987qeep44cyrewp9"
KEY = "pdl_sdbx_apikey_01test_abcdefghijklmnopqrstuvwxyz"


def configure(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in {
        billing.API_KEY_ENV: KEY,
        billing.WEBHOOK_SECRET_ENV: "pdl_ntfset_01test",
        billing.ENVIRONMENT_ENV: "sandbox",
        billing.PRICE_MONTH_ENV: "pri_month",
        billing.PRICE_QUARTER_ENV: "pri_quarter",
        billing.PRICE_TOP_UP_ENV: "pri_top_up",
        billing.CLIENT_TOKEN_ENV: TOKEN,
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
        billing.CLIENT_TOKEN_ENV,
    ):
        monkeypatch.delenv(name, raising=False)


class Paddle:
    """Paddle's API as the mock answers it: every request kept, one answer each."""

    def __init__(self) -> None:
        self.asked: list[Any] = []
        self.answer: Any = {"data": {"id": TXN, "status": "ready"}}

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
        billing.CLIENT_TOKEN_ENV,
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


def test_a_client_token_for_the_other_environment_is_no_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(monkeypatch)
    assert billing.client_token() == TOKEN
    monkeypatch.setenv(billing.CLIENT_TOKEN_ENV, "live_0123456789abcdef")
    assert billing.client_token() == "" and not billing.configured()
    monkeypatch.setenv(billing.ENVIRONMENT_ENV, "live")
    monkeypatch.setenv(billing.API_KEY_ENV, "pdl_live_apikey_01real")
    assert billing.client_token() == "live_0123456789abcdef"
    monkeypatch.setenv(billing.CLIENT_TOKEN_ENV, "pdl_sdbx_apikey_not_a_token")
    assert billing.client_token() == "", "an API key is never a client token"


def test_a_ticket_holds_only_for_its_account_transaction_and_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure(monkeypatch)
    now = 2_000_000_000.0
    ticket = billing.ticket(7, TXN, "start", at=now)
    assert billing.ticket_kind(7, TXN, ticket, at=now + 60) == "start"
    assert billing.ticket_kind(8, TXN, ticket, at=now) == "", "another account's"
    other = "txn_01hv8wptq8987qeep44cyrewq0"
    assert billing.ticket_kind(7, other, ticket, at=now) == "", "another transaction's"
    assert billing.ticket_kind(7, TXN, "", at=now) == "", "no ticket"
    assert billing.ticket_kind(7, "txn_short", billing.ticket(7, "txn_short", "start")) == ""
    assert billing.ticket_kind(7, TXN, ticket + "\u00e9", at=now) == ""
    # qa on #1304: a ticket dies after TICKET_MINUTES, and one from the future is no ticket.
    late = now + billing.TICKET_MINUTES * 60 + 1
    assert billing.ticket_kind(7, TXN, ticket, at=late) == "", "expired"
    assert billing.ticket_kind(7, TXN, ticket, at=now - 5) == "", "not made yet"
    # The kind and the time are under the MAC: changing either breaks it.
    kind, made, mac = ticket.split(".")
    assert billing.ticket_kind(7, TXN, f"top-up.{made}.{mac}", at=now) == ""
    assert billing.ticket_kind(7, TXN, f"{kind}.{int(made) + 600}.{mac}", at=now + 600) == ""
    top_up = billing.ticket(7, TXN, "top-up", at=now)
    assert billing.ticket_kind(7, TXN, top_up, at=now) == "top-up"
    monkeypatch.delenv(billing.WEBHOOK_SECRET_ENV)
    assert billing.ticket_kind(7, TXN, ticket, at=now) == "", "no secret, no ticket"


# -- the call to Paddle ---------------------------------------------------------------


def test_a_checkout_makes_a_transaction_for_the_account(
    monkeypatch: pytest.MonkeyPatch, paddle: Paddle
) -> None:
    configure(monkeypatch)
    made = billing.transaction("pri_month", account=7, made=1000)
    assert made == TXN
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
    billing.transaction("pri_top_up", account=7, made=1000, quantity=3, customer="ctm_1")
    assert paddle.body()["customer_id"] == "ctm_1"
    assert paddle.body()["items"] == [{"price_id": "pri_top_up", "quantity": 3}]


def test_live_calls_paddles_live_api(monkeypatch: pytest.MonkeyPatch, paddle: Paddle) -> None:
    configure(monkeypatch)
    monkeypatch.setenv(billing.ENVIRONMENT_ENV, "live")
    monkeypatch.setenv(billing.API_KEY_ENV, "pdl_live_apikey_01real")
    monkeypatch.setenv(billing.CLIENT_TOKEN_ENV, "live_0123456789abcdef")
    billing.transaction("pri_month", account=7, made=1000)
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
        billing.transaction("pri_month", account=7, made=1000)


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
    assert 'name="cadence" value="month"' in page and 'value="quarter"' not in page
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


PADDLE_ORIGINS = ("cdn.paddle.com", "buy.paddle.com", "checkout-service.paddle.com", "paddle.io")


def names_paddle(text: str) -> bool:
    return any(origin in text for origin in PADDLE_ORIGINS) or "paddle.js" in text.lower()


@pytest.mark.usefixtures("on")
def test_configured_the_plans_page_names_nothing_of_paddles_until_a_checkout(
    box: tuple[int, Path, dict[str, str]],
) -> None:
    """/plans as a reader opens it: Start the plan is a form to our own server, and the
    page and its policy carry nothing of Paddle's."""
    port, _, sessions = box
    status, headers, page = fetch(port, "/plans", sessions["free"])
    assert status == 200 and 'action="/plans/start"' in page
    assert not names_paddle(headers["Content-Security-Policy"]) and not names_paddle(page)
    assert "form-action 'self';" in headers["Content-Security-Policy"]


def fresh_checkout(port: int, sessions: dict[str, str]) -> str:
    status, headers, _ = press(port, serve.PLANS_START, {"cadence": "month"}, sessions["free"])
    assert status == 303
    return headers["Location"]


@pytest.mark.usefixtures("on")
def test_start_comes_back_to_plans_and_only_that_view_opens_paddles_checkout(
    box: tuple[int, Path, dict[str, str]], paddle: Paddle
) -> None:
    port, _, sessions = box
    where = fresh_checkout(port, sessions)
    assert where.startswith(f"/plans?checkout={TXN}&ticket="), "back to our own origin"
    status, headers, page = fetch(port, where, sessions["free"])
    policy = headers["Content-Security-Policy"]
    assert status == 200
    assert '<script src="https://cdn.paddle.com/paddle/v2/paddle.js"></script>' in page
    assert f'data-transaction="{TXN}"' in page and f'data-token="{TOKEN}"' in page
    assert 'data-environment="sandbox"' in page
    clauses = {one.strip().split(" ")[0]: one.strip() for one in policy.split(";")}
    assert "https://cdn.paddle.com" in clauses["script-src"]
    assert clauses["frame-src"].endswith("https://sandbox-buy.paddle.com")
    assert "https://sandbox-checkout-service.paddle.com" in clauses["connect-src"]
    # Nothing broader: no wildcard, no style, font, image or form origin of Paddle's,
    # and only the sandbox's frame and service while the deployment is sandbox.
    assert "*" not in policy and "unsafe-inline" not in policy
    for directive in ("style-src", "img-src", "font-src", "form-action", "default-src"):
        if directive in clauses:
            assert not names_paddle(clauses[directive]), directive
    assert "https://buy.paddle.com" not in policy
    assert " https://checkout-service.paddle.com" not in policy


@pytest.mark.usefixtures("on")
def test_a_checkout_link_opens_nothing_for_anyone_else(
    box: tuple[int, Path, dict[str, str]], paddle: Paddle
) -> None:
    """The ticket ties the transaction to the account it was made for: the same link
    signed in as somebody else, a forged ticket, another id or no ticket opens nothing."""
    port, _, sessions = box
    where = fresh_checkout(port, sessions)
    for session, link in (
        (sessions["paying"], where),
        (sessions["free"], where.rsplit("=", 1)[0] + "=" + "0" * 32),
        (sessions["free"], where.replace(TXN, "txn_01hv8wptq8987qeep44cyrewq0")),
        (sessions["free"], f"/plans?checkout={TXN}"),
    ):
        status, headers, page = fetch(port, link, session)
        assert status == 200
        policy = headers["Content-Security-Policy"]
        assert not names_paddle(policy) and not names_paddle(page), link


@pytest.mark.usefixtures("on")
def test_an_expired_ticket_or_a_start_after_subscribing_opens_nothing(
    box: tuple[int, Path, dict[str, str]], paddle: Paddle
) -> None:
    """qa on #1304: a copied Start link must not open an unpaid checkout once the reader
    has subscribed, nor any link after `TICKET_MINUTES`."""
    port, store_path, sessions = box
    store = Store(store_path)
    me = store.person_by_email("free@example.com")
    assert me is not None
    gone = time.time() - billing.TICKET_MINUTES * 60 - 5
    old = billing.ticket(me.id, TXN, "start", at=gone)
    _, headers, page = fetch(port, f"/plans?checkout={TXN}&ticket={old}", sessions["free"])
    assert not names_paddle(headers["Content-Security-Policy"]) and not names_paddle(page)
    # The paying reader's own fresh Start ticket opens nothing: their plan holds.
    paying = store.person_by_email("paying@example.com")
    assert paying is not None
    fresh = billing.ticket(paying.id, TXN, "start")
    _, _, page = fetch(port, f"/plans?checkout={TXN}&ticket={fresh}", sessions["paying"])
    assert not names_paddle(page), "a Start for an account already on a paid plan"
    # A top-up ticket for the same reader does open.
    top_up = billing.ticket(paying.id, TXN, "top-up")
    _, _, page = fetch(port, f"/plans?checkout={TXN}&ticket={top_up}", sessions["paying"])
    assert "cdn.paddle.com/paddle/v2/paddle.js" in page


@pytest.mark.usefixtures("on")
def test_no_other_page_gains_paddles_origins(
    box: tuple[int, Path, dict[str, str]], paddle: Paddle
) -> None:
    port, _, sessions = box
    fresh_checkout(port, sessions)
    for path in ("/account", "/", "/library", "/you/saved", "/connect"):
        _, headers, page = fetch(port, path, sessions["free"])
        assert not names_paddle(headers.get("Content-Security-Policy", "")), path
        assert "cdn.paddle.com" not in page, path


def test_a_reader_still_fetches_nothing_from_any_other_site() -> None:
    """CLAUDE.md: a reader fetches nothing from any other site. Paddle.js rides only the
    plans page's one view, which is no reader; no other template names it, and a page's
    policy names Paddle only when the plans page asks for it."""
    policy = serve.Handler._policy(b"<html><body>a reader</body></html>")
    assert not names_paddle(policy)
    assert "https://" not in policy.split("script-src")[1].split(";")[0]
    templates = Path(serve.__file__).parent / "render" / "templates"
    carrying = sorted(
        one.name
        for one in templates.glob("*.j2")
        if "cdn.paddle.com" in one.read_text(encoding="utf-8")
        or "checkout.script" in one.read_text(encoding="utf-8")
    )
    assert carrying == ["plans.html.j2"], carrying
    assets = Path(serve.__file__).parent / "render" / "assets"
    loading = sorted(
        one.name for one in assets.glob("*.js") if "cdn.paddle.com" in one.read_text("utf-8")
    )
    assert loading == [], "Paddle.js is named by the template alone, never by a script"


@pytest.mark.usefixtures("on")
def test_start_sends_a_free_reader_to_paddles_checkout(
    box: tuple[int, Path, dict[str, str]], paddle: Paddle
) -> None:
    port, store_path, sessions = box
    status, headers, _ = press(port, serve.PLANS_START, {"cadence": "month"}, sessions["free"])
    assert status == 303 and headers["Location"].startswith(f"/plans?checkout={TXN}&ticket=")
    me = Store(store_path).person_by_email("free@example.com")
    assert me is not None
    assert paddle.body()["items"] == [{"price_id": "pri_month", "quantity": 1}]
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
    assert status == 303 and headers["Location"].startswith(f"/plans?checkout={TXN}&ticket=")
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


@pytest.mark.usefixtures("on")
def test_a_quarter_is_not_offered(box: tuple[int, Path, dict[str, str]], paddle: Paddle) -> None:
    """Plan is monthly only (David, 2026-11-18): a pressed quarter goes back to /plans."""
    port, _, sessions = box
    status, headers, _ = press(port, serve.PLANS_START, {"cadence": "quarter"}, sessions["free"])
    assert status == 303 and headers["Location"] == "/plans"
