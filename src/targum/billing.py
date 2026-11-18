"""Paying for Plan and for top-ups, through Paddle (targum-internal#59 phase 2; design.md
§12, "Payments are Paddle's, by a hosted checkout", 2026-11-15, and "/plans alone loads
Paddle's checkout script", 2026-11-17).

**The checkout is Paddle's overlay, on `/plans` alone** (David, 2026-11-17). A pay press
posts to our server, which makes the Paddle transaction (`transaction`) and sends the
reader back to `/plans` holding its id and a ticket only our server can make (`ticket`).
That one view of `/plans` loads Paddle.js (`PADDLE_JS`) and opens the overlay on the
transaction; no other page, and no other view of `/plans`, loads anything of Paddle's.

**Paddle is the merchant of record.** It sells, it keeps the card, it charges the tax and
it mails the receipt. targum keeps only what Paddle's webhooks say of an account's plan
(the `plan` row) and of a top-up paid for (`credit_grant`), and nothing of money.

**Everything here is inert without its keys.** Every setting is read from the environment
each time it is asked for, and `configured()` is false until all of them are there, so a
machine nobody has set up, and the box until David puts the keys in `box.env.op`, behaves
exactly as before: `/billing/webhook` answers 404 and every pay button stays greyed.

The webhook (`POST /billing/webhook`) is the only way a plan or a top-up reaches the
store. It is believed only when it carries Paddle's signature (`verify`): an HMAC-SHA256
of `ts:body` under the destination's secret, with `ts` no older than `TOLERANCE_SECONDS`.
Each event is handled once, by its id (`Store.billing_seen`).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .accounts import Person, Store

#: The settings, all from the environment and none with a default but the environment.
API_KEY_ENV = "PADDLE_API_KEY"
WEBHOOK_SECRET_ENV = "PADDLE_WEBHOOK_SECRET"
#: The secret before the last rotation, set only while one is under way: tags our
#: checkout wrote under it are still believed (`account_tag`), for checkouts started
#: before the rotation and paid after it. Paddle signs with both while it rotates.
WEBHOOK_SECRET_PREVIOUS_ENV = "PADDLE_WEBHOOK_SECRET_PREVIOUS"
ENVIRONMENT_ENV = "PADDLE_ENVIRONMENT"
#: Plan's Paddle price ids (`pri_...`). Only the month is offered (David, 2026-11-18);
#: the quarter is read where a deployment still names one, and the box does not.
PRICE_MONTH_ENV = "PADDLE_PRICE_MONTH"
PRICE_QUARTER_ENV = "PADDLE_PRICE_QUARTER"
#: One hour of top-up, 60 credits: a top-up of 180 is three of it. One price rather than
#: three, so the three sizes cannot disagree about what an hour costs.
PRICE_TOP_UP_ENV = "PADDLE_PRICE_TOP_UP"
#: The client-side token Paddle.js is initialised with (`test_…` in sandbox, `live_…` on
#: live). Paddle made it to be published: it can open a checkout and preview prices, and
#: nothing else, so it is safe in the page. Not a secret, though it is kept with the rest.
CLIENT_TOKEN_ENV = "PADDLE_CLIENT_TOKEN"

#: Paddle.js, where Paddle says it must be loaded from. Paddle publishes it at a major
#: version only, with no pinned build and no integrity hash, and asks that it always be
#: loaded from its CDN (developer.paddle.com/paddle-js/about/include-paddlejs), so the
#: address is pinned to v2 and the policy names the CDN's origin and nothing wider.
PADDLE_JS = "https://cdn.paddle.com/paddle/v2/paddle.js"

#: What the checkout's page may reach, by environment: Paddle.js from its CDN, the
#: overlay's frame, and the checkout service Paddle.js talks to. Named for the one view
#: of `/plans` that opens a checkout (`serve.Handler._policy`), and for no other page.
CHECKOUT_SOURCES = {
    "sandbox": {
        "script": "https://cdn.paddle.com",
        "frame": "https://sandbox-buy.paddle.com",
        "connect": "https://sandbox-checkout-service.paddle.com",
    },
    "live": {
        "script": "https://cdn.paddle.com",
        "frame": "https://buy.paddle.com",
        "connect": "https://checkout-service.paddle.com",
    },
}

#: The two places Paddle runs. Sandbox unless the deployment says live, so a key put in
#: by mistake charges nobody.
ENVIRONMENTS = ("sandbox", "live")
API_BASE = {"sandbox": "https://sandbox-api.paddle.com", "live": "https://api.paddle.com"}

#: Credits in one unit of the top-up price.
TOP_UP_UNIT = 60

#: How old a signature may be when it arrives. Paddle's own libraries allow five seconds;
#: a little more here, for the box's clock and the proxy, and still short enough that a
#: delivery somebody captured cannot be sent again later.
TOLERANCE_SECONDS = 30
#: The most of a webhook body read. Paddle's events are a few kilobytes.
MOST_BODY_BYTES = 256 * 1024

#: The key in `custom_data` that names the account a checkout was made for. Set by our
#: server when it makes the transaction, and copied by Paddle onto the subscription.
ACCOUNT_KEY = "targum_account"
#: And beside it the account's tag (`account_tag`), so a `custom_data` our server did not
#: write names nobody: Paddle's hosted checkout documents no way to pass it, but nothing
#: here should rest on that (qa-claude on #1280).
TAG_KEY = "targum_tag"


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def environment() -> str:
    """`sandbox` or `live`: sandbox unless the deployment says live."""
    said = _env(ENVIRONMENT_ENV).lower()
    return said if said in ENVIRONMENTS else "sandbox"


def webhook_secret() -> str:
    return _env(WEBHOOK_SECRET_ENV)


def api_key() -> str:
    """The API key, but only where it is for the environment the deployment names:
    Paddle's keys say which they are (`pdl_sdbx_...`, `pdl_live_...`), and a live key
    on a sandbox deployment, or the other way round, is treated as no key."""
    key = _env(API_KEY_ENV)
    if not key:
        return ""
    marked = {"sdbx": "sandbox", "live": "live"}
    for mark, place in marked.items():
        if f"_{mark}_" in key and place != environment():
            return ""
    return key


def prices() -> dict[str, str]:
    """The price ids by what they buy: `month`, `quarter` and `top-up`. The quarter is
    "" wherever the deployment names none, which is every deployment now."""
    return {
        "month": _env(PRICE_MONTH_ENV),
        "quarter": _env(PRICE_QUARTER_ENV),
        "top-up": _env(PRICE_TOP_UP_ENV),
    }


def client_token() -> str:
    """The client-side token, but only where it is for the environment the deployment
    names (`test_…` for sandbox, `live_…` for live): one for the other is no token."""
    token = _env(CLIENT_TOKEN_ENV)
    wanted = "test_" if environment() == "sandbox" else "live_"
    return token if token.startswith(wanted) else ""


#: The prices an install needs before it can take money: Plan's month and the top-up.
#: The quarter is not one of them: Plan is monthly only (David, 2026-11-18), the box names
#: no quarter, and `configured` asking for it kept every pay press off (builder-3's
#: go-live walk, 2026-11-18). A quarter a deployment still names is read by the webhook.
REQUIRED_PRICES = ("month", "top-up")


def configured() -> bool:
    """Whether this install can take money: the key, the webhook secret, the client token
    and the prices in `REQUIRED_PRICES`. Until then nothing is offered."""
    named = prices()
    return bool(
        api_key()
        and webhook_secret()
        and all(named[one] for one in REQUIRED_PRICES)
        and client_token()
    )


# -- the signature --------------------------------------------------------------------


def sign(body: bytes, secret: str, at: int) -> str:
    """The `Paddle-Signature` header Paddle would send for `body` at `at`: what the tests
    sign their fixtures with, and what `verify` checks against."""
    digest = hmac.new(secret.encode(), f"{at}:".encode() + body, hashlib.sha256).hexdigest()
    return f"ts={at};h1={digest}"


def verify(header: str | None, body: bytes, secret: str, at: float | None = None) -> str:
    """Why a webhook is not believed, or "" when it is.

    `header` is `Paddle-Signature`: `ts=<seconds>;h1=<hex>`, with more than one `h1`
    while Paddle rotates a secret, any of which may match. The body is the raw bytes as
    they arrived, since re-encoding JSON changes what was signed."""
    if not secret:
        return "unconfigured"
    if not header:
        return "unsigned"
    stamp = ""
    given: list[str] = []
    for part in header.split(";"):
        name, _, value = part.strip().partition("=")
        if name == "ts":
            stamp = value
        elif name == "h1" and value:
            given.append(value)
    # ASCII digits only: `"²".isdigit()` is true and `int("²")` raises, and a header is
    # whatever the sender wrote (qa-claude on #1280).
    if not (stamp.isascii() and stamp.isdigit()) or not given:
        return "unsigned"
    moment = time.time() if at is None else at
    if abs(moment - int(stamp)) > TOLERANCE_SECONDS:
        return "stale"
    wanted = hmac.new(secret.encode(), f"{stamp}:".encode() + body, hashlib.sha256).hexdigest()
    # Compared as bytes: `compare_digest` raises on a str that is not ASCII.
    said = [one.encode("utf-8", "replace") for one in given]
    if not any(hmac.compare_digest(wanted.encode(), one) for one in said):
        return "forged"
    return ""


# -- what an event says ------------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    """What handling one event did, for the log and the tests: `kind` is `plan`,
    `top-up`, `grace`, `ignored` or `unknown-account`."""

    kind: str
    person: int | None = None
    detail: str = ""


#: The subscription events that carry the subscription whole, and so set the plan row.
SUBSCRIPTION_EVENTS = (
    "subscription.created",
    "subscription.updated",
    "subscription.canceled",
    "subscription.past_due",
    "subscription.activated",
    "subscription.paused",
    "subscription.resumed",
    "subscription.trialing",
)


def _millis(said: Any) -> int | None:
    """Paddle's RFC 3339 moment (`2026-11-16T10:00:00.123456Z`) in milliseconds."""
    if not isinstance(said, str) or not said:
        return None
    try:
        moment = datetime.fromisoformat(said.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return int(moment.timestamp() * 1000)


def account_tag(account: int, made: int, secret: str | None = None) -> str:
    """What our checkout writes beside the account's id in `custom_data`: an HMAC of the
    id and the moment the account was made, under the webhook secret. Only our server
    can make it, and an account made later under the same id would not match it."""
    key = (webhook_secret() if secret is None else secret).encode()
    return hmac.new(key, f"{int(account)}:{int(made)}".encode(), hashlib.sha256).hexdigest()[:32]


def _account(store: Store, data: dict[str, Any]) -> Person | None:
    """The account `custom_data` names, where its tag is the one our checkout wrote."""
    custom = data.get("custom_data")
    if not isinstance(custom, dict):
        return None
    try:
        account = int(str(custom.get(ACCOUNT_KEY)))
    except ValueError:
        return None
    tag = str(custom.get(TAG_KEY) or "").encode("utf-8", "replace")
    row = store.db.execute("SELECT made FROM person WHERE id = ?", (account,)).fetchone()
    secrets = [one for one in (webhook_secret(), _env(WEBHOOK_SECRET_PREVIOUS_ENV)) if one]
    if row is None or not tag or not secrets:
        return None
    wanted = [account_tag(account, int(row[0]), one).encode() for one in secrets]
    if not any(hmac.compare_digest(one, tag) for one in wanted):
        return None
    return store.person_by_id(account)


def _whose(store: Store, data: dict[str, Any], subscription: str = "") -> Person | None:
    """The account an event is about: the one already holding this subscription, else
    the one our checkout named in `custom_data` with its tag, else the one with this
    Paddle customer. What the store already holds comes first, so `custom_data` never
    moves a subscription from the account that has it."""
    if subscription:
        person = store.person_by_subscription(subscription)
        if person is not None:
            return person
    person = _account(store, data)
    if person is not None:
        return person
    customer = str(data.get("customer_id") or "")
    return store.person_by_customer(customer) if customer else None


def _price_ids(data: dict[str, Any]) -> list[tuple[str, int]]:
    """Each item's price id and quantity."""
    out: list[tuple[str, int]] = []
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        price = item.get("price")
        price_id = str(price.get("id") if isinstance(price, dict) else item.get("price_id") or "")
        try:
            quantity = int(item.get("quantity") or 1)
        except (TypeError, ValueError):
            quantity = 1
        out.append((price_id, quantity))
    return out


def _cadence(data: dict[str, Any]) -> str:
    """`month` or `quarter`, by the price, where it is one of Plan's two; "" where no
    item is, and such a subscription is not Plan (qa-claude on #1280)."""
    by_price = {one: name for name, one in prices().items() if one and name in ("month", "quarter")}
    for price_id, _ in _price_ids(data):
        if price_id in by_price:
            return by_price[price_id]
    return ""


def _subscription(store: Store, kind: str, data: dict[str, Any], said_at: int | None) -> Outcome:
    from .accounts import PLAN_STATUSES

    subscription = str(data.get("id") or "")
    person = _whose(store, data, subscription)
    if person is None:
        return Outcome("unknown-account", detail=subscription)
    status = str(data.get("status") or "")
    if status not in PLAN_STATUSES:
        return Outcome("ignored", person.id, f"status {status!r}")
    cadence = _cadence(data)
    if not cadence:
        return Outcome("ignored", person.id, "not Plan's price")
    period = data.get("current_billing_period")
    ends = str(period.get("ends_at") or "") if isinstance(period, dict) else ""
    starts = str(period.get("starts_at") or "") if isinstance(period, dict) else ""
    scheduled = data.get("scheduled_change")
    cancelling = isinstance(scheduled, dict) and scheduled.get("action") == "cancel"
    applied = store.set_billing(
        person.id,
        cadence=cadence,
        status=status,
        period_end=ends,
        cancel_at_end=cancelling,
        customer=str(data.get("customer_id") or ""),
        subscription=subscription,
        said_at=said_at,
        period_start=starts,
        ended_at=str(data.get("canceled_at") or ""),
    )
    return Outcome("plan" if applied else "ignored", person.id, status if applied else "stale")


def _completed(store: Store, data: dict[str, Any]) -> Outcome:
    """A transaction paid. A subscription's payments are the subscription events' to
    say; one with no subscription and our top-up price on it is a top-up."""
    if data.get("subscription_id"):
        return Outcome("ignored", detail="a subscription's payment")
    top_up = prices()["top-up"]
    units = sum(
        quantity for price_id, quantity in _price_ids(data) if top_up and price_id == top_up
    )
    if units <= 0:
        return Outcome("ignored", detail="no top-up on it")
    person = _whose(store, data)
    if person is None:
        return Outcome("unknown-account", detail=str(data.get("id") or ""))
    granted = store.grant_credits(person.id, units * TOP_UP_UNIT, str(data.get("id") or ""))
    return Outcome("top-up" if granted else "ignored", person.id, f"{units * TOP_UP_UNIT}")


def _payment_failed(store: Store, data: dict[str, Any], said_at: int | None) -> Outcome:
    """A payment that failed. Only a renewal's starts the grace: a card refused at the
    checkout is the reader trying again on Paddle's page, and changes nothing here."""
    subscription = str(data.get("subscription_id") or "")
    if not subscription or data.get("origin") != "subscription_recurring":
        return Outcome("ignored", detail="not a renewal")
    person = _whose(store, data, subscription)
    if person is None or person.billing is None:
        return Outcome("unknown-account", detail=subscription)
    held = person.billing
    if held.status == "past_due":
        return Outcome("ignored", person.id, "already in grace")
    store.set_billing(
        person.id,
        cadence=held.cadence,
        status="past_due",
        period_end=held.period_end,
        cancel_at_end=held.cancel_at_end,
        customer=held.customer,
        subscription=held.subscription or subscription,
        said_at=said_at,
    )
    return Outcome("grace", person.id)


def handle(store: Store, event: dict[str, Any]) -> Outcome:
    """Apply one verified event to the store. Idempotency is the caller's
    (`Store.billing_seen`); this only says what the event means."""
    kind = str(event.get("event_type") or "")
    data = event.get("data")
    if not isinstance(data, dict):
        return Outcome("ignored", detail="no data")
    said_at = _millis(event.get("occurred_at"))
    if kind in SUBSCRIPTION_EVENTS:
        return _subscription(store, kind, data, said_at)
    if kind == "transaction.completed":
        return _completed(store, data)
    if kind == "transaction.payment_failed":
        return _payment_failed(store, data, said_at)
    return Outcome("ignored", detail=kind)


# -- talking to Paddle ------------------------------------------------------------------


class PaddleError(Exception):
    """Paddle did not answer as asked: unreachable, refused, or an answer without what
    the call needs. Said to the reader as "try again", never as Paddle's words."""


#: How long a call to Paddle may take. A reader is waiting on the press.
TIMEOUT_SECONDS = 15


def _call(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """One call to Paddle's API, with the key, as JSON, answering `data`."""
    key = api_key()
    if not key:
        raise PaddleError("no key")
    request = urllib.request.Request(
        API_BASE[environment()] + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - Paddle's own https address
            answer = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        raise PaddleError(f"{method} {path}: {error.code}") from error
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise PaddleError(f"{method} {path}: {error}") from error
    data = answer.get("data") if isinstance(answer, dict) else None
    if not isinstance(data, dict):
        raise PaddleError(f"{method} {path}: no data")
    return data


def transaction(
    price: str, *, account: int, made: int, quantity: int = 1, customer: str = ""
) -> str:
    """A Paddle transaction for `price` and this account, to open the checkout on: its id.

    The account rides in `custom_data` with its tag (`account_tag`, over the id and
    `made`, when the account was made), which Paddle copies onto the subscription, so
    the webhook knows whose it is and that our server said so. A reader who has paid
    before is named by their Paddle customer, so a second subscription or a top-up lands
    on the same one."""
    if not price or not client_token():
        raise PaddleError("not configured")
    body: dict[str, Any] = {
        "items": [{"price_id": price, "quantity": int(quantity)}],
        "custom_data": {
            ACCOUNT_KEY: str(int(account)),
            TAG_KEY: account_tag(int(account), int(made)),
        },
        "collection_mode": "automatic",
    }
    if customer:
        body["customer_id"] = customer
    answer = _call("POST", "/transactions", body)
    made_id = str(answer.get("id") or "")
    if not TRANSACTION_ID.fullmatch(made_id):
        raise PaddleError("no transaction")
    return made_id


#: A Paddle transaction id, as Paddle writes them: `txn_` and 26 lowercase base-32 letters.
TRANSACTION_ID = re.compile(r"txn_[a-z0-9]{26}")


#: How long a checkout ticket opens a checkout for (qa on #1304): long enough to read the
#: plans page and pay, short enough that a link copied out of a history or a log is dead.
TICKET_MINUTES = 30

#: What a ticket was made for: Start the plan, or a top-up.
TICKET_KINDS = ("start", "top-up")


def ticket(account: int, transaction_id: str, kind: str, at: float | None = None) -> str:
    """What our server gives the reader beside a transaction it made for them, so that
    `/plans` opens a checkout only on a transaction made for the account looking at it,
    for what it was made for, and only for `TICKET_MINUTES`: `<kind>.<seconds>.<mac>`,
    the kind and the moment it was made under the HMAC with the account and the id."""
    made = int(time.time() if at is None else at)
    return f"{kind}.{made}.{_ticket_mac(account, transaction_id, kind, made)}"


def _ticket_mac(account: int, transaction_id: str, kind: str, made: int) -> str:
    key = webhook_secret().encode()
    said = f"checkout:{int(account)}:{transaction_id}:{kind}:{made}".encode()
    return hmac.new(key, said, hashlib.sha256).hexdigest()[:32]


def ticket_kind(account: int, transaction_id: str, given: str, at: float | None = None) -> str:
    """What `given` was made for (`start` or `top-up`), where it is the ticket our server
    made for this account and transaction less than `TICKET_MINUTES` ago; "" otherwise."""
    if not webhook_secret() or not TRANSACTION_ID.fullmatch(transaction_id or ""):
        return ""
    kind, _, rest = (given or "").partition(".")
    stamp, _, mac = rest.partition(".")
    if kind not in TICKET_KINDS or not (stamp.isascii() and stamp.isdigit()):
        return ""
    made = int(stamp)
    now = time.time() if at is None else at
    if not (0 <= now - made <= TICKET_MINUTES * 60):
        return ""
    wanted = _ticket_mac(account, transaction_id, kind, made).encode()
    return kind if hmac.compare_digest(wanted, mac.encode("utf-8", "replace")) else ""


def ticket_holds(account: int, transaction_id: str, given: str) -> bool:
    """Whether `given` is a live ticket our server made for this account and transaction."""
    return bool(ticket_kind(account, transaction_id, given))


def cancel(subscription: str) -> None:
    """Ask Paddle to cancel a subscription at the end of the period already paid for:
    what closing an account does, so a reader who leaves is not charged again. Paddle
    says `canceled` by webhook when the period ends, and only then does the purge go
    ahead (`Store.live_billing`)."""
    if not subscription.startswith("sub_"):
        raise PaddleError("no subscription")
    _call(
        "POST",
        f"/subscriptions/{urllib.parse.quote(subscription)}/cancel",
        {"effective_from": "next_billing_period"},
    )


def portal(customer: str, subscription: str = "") -> str:
    """A link into Paddle's customer portal for this customer, made fresh for each press:
    its token is short-lived, so it is never kept. Opened on the subscription where there
    is one, which is where the card, the receipts and Cancel are."""
    if not customer.startswith("ctm_"):
        raise PaddleError("no customer")
    body = {"subscription_ids": [subscription]} if subscription.startswith("sub_") else {}
    made = _call("POST", f"/customers/{urllib.parse.quote(customer)}/portal-sessions", body)
    urls = made.get("urls")
    if not isinstance(urls, dict):
        raise PaddleError("no portal")
    for one in urls.get("subscriptions") or []:
        if isinstance(one, dict) and one.get("id") == subscription and one.get("view_subscription"):
            return _paddles(str(one["view_subscription"]))
    general = urls.get("general")
    overview = str(general.get("overview") or "") if isinstance(general, dict) else ""
    return _paddles(overview)


def _paddles(link: str) -> str:
    """A link Paddle handed back, where it is https on `paddle.com`, else an error: the
    server redirects the reader to it, so it is checked like the checkout's."""
    parsed = urllib.parse.urlsplit(link)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "paddle.com" or host.endswith(".paddle.com")):
        raise PaddleError("not a portal link")
    return link
