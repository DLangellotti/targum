"""Signing in with Google, without a Google script on the page (targum-internal#304).

The mailed link is one round trip through a mail client between wanting to read Hebrew
and reading it, and it is where an invitation quietly dies: the mail lands in spam, or on
the phone when they are at the laptop, and the turn we told them had come does not arrive.

**Google is not a second kind of account.** `person`, `invited` and `waiting` are all
keyed on an email address, so this is a faster way to prove the same address — not a
different identity. Somebody who signs in with a link one day and with Google the next
lands in the same account with the same words, and `tests/test_google.py` holds that.

**No Google script, and that constraint shapes the whole module.** Google Identity
Services is a hosted widget, and the front door's own rule forbids it: "No script,
stylesheet, font or image comes off the network ... the first page anybody sees should
not be a page that phones somebody else first." So this is plain OAuth 2.0 authorization
code with PKCE. What the page carries is an anchor to `accounts.google.com`, which is an
outbound link the reader chooses to click and the one exception §11 already carves out.
Nothing is embedded, nothing is fetched, and a reader who never presses it is never seen
by Google at all.

**Scope is `openid email` and nothing else.** Not `profile`, though it would fill in the
greeting: the FAQ promises "Your email and nothing else. We won't pass it on", and a name
can be asked for in its own box by somebody who wants to give one. The token response is
read for an address and discarded — no ID token kept, no refresh token asked for, nothing
about the Google account stored anywhere.

**Everything here is inert without credentials.** `configured()` is false when the
environment names no client, the page draws no button, and both routes answer 404. That
is the state on a machine somebody runs themselves, and the state on the box until David
puts a client id in `targum.env`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

#: Google's own endpoints. Hard-coded rather than discovered: fetching the discovery
#: document would be one more network call that can fail, on a path a person is waiting
#: on, to learn two URLs that have not changed in a decade.
AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"

#: What is asked for, and the whole of it. `openid` because the address rides in the id
#: token; `email` for the address and whether Google has verified it.
SCOPE = "openid email"

#: How long a started sign-in stays startable. Long enough to read a consent screen and
#: choose an account, short enough that a `state` left in a bookmark is dead.
BEGUN_MINUTES = 10

CLIENT_ID_ENV = "TARGUM_GOOGLE_CLIENT_ID"
CLIENT_SECRET_ENV = "TARGUM_GOOGLE_CLIENT_SECRET"


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def configured() -> bool:
    """Whether this install can offer Google at all.

    Both halves or neither: a client id without its secret cannot finish the exchange,
    and offering a door that fails at the last step is worse than not offering it.
    """
    return bool(_env(CLIENT_ID_ENV) and _env(CLIENT_SECRET_ENV))


@dataclass(frozen=True)
class Begun:
    """One sign-in started: where to send them, and what to remember while they are gone."""

    where: str
    state: str
    verifier: str
    made: float


def _nonce() -> str:
    return secrets.token_urlsafe(32)


def _challenge(verifier: str) -> str:
    """S256: the verifier's SHA-256, base64url, unpadded, as RFC 7636 says."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def begin(redirect_to: str) -> Begun:
    """Start a sign-in: the address to send the reader to, and the secrets to keep.

    PKCE even though this is a confidential client with a secret. It costs one hash and
    it closes the window where an authorization code intercepted on the way back can be
    spent by anybody else.
    """
    verifier = _nonce()
    state = _nonce()
    query = {
        "client_id": _env(CLIENT_ID_ENV),
        "redirect_uri": redirect_to,
        "response_type": "code",
        "scope": SCOPE,
        "state": state,
        "code_challenge": _challenge(verifier),
        "code_challenge_method": "S256",
        # A reader with two Google accounts is asked which; without this Google picks
        # the one it saw last, which is how somebody signs in as the wrong person and
        # finds an empty shelf.
        "prompt": "select_account",
    }
    return Begun(
        where=f"{AUTHORIZE}?{urllib.parse.urlencode(query)}",
        state=state,
        verifier=verifier,
        made=time.time(),
    )


def stale(begun: Begun, at: float | None = None) -> bool:
    """Whether a started sign-in has been sitting too long to finish."""
    return (at or time.time()) - begun.made > BEGUN_MINUTES * 60


class Refused(Exception):
    """Google would not, or did not, prove an address."""


def _claims(id_token: str) -> dict[str, object]:
    """The payload of an id token, read without verifying its signature.

    **That is safe here and nowhere else.** This token came back over TLS, on a direct
    connection to Google's own token endpoint, in answer to a request carrying this
    install's client secret and PKCE verifier — not from the browser, where an unverified
    token would be whatever the browser felt like sending. Google's own documentation
    says a token received this way may be used without validation.
    """
    parts = id_token.split(".")
    if len(parts) != 3:
        raise Refused("That sign-in did not come back with an identity.")
    padded = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        loaded = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, json.JSONDecodeError) as error:
        raise Refused("That sign-in did not come back with an identity.") from error
    if not isinstance(loaded, dict):
        raise Refused("That sign-in did not come back with an identity.")
    return loaded


def address_from(answer: dict[str, object]) -> str:
    """The verified address in a token response, or a refusal saying why not.

    An unverified address is refused outright. Google will hand one over for an account
    whose address it has not confirmed, and accepting it would let somebody sign in as an
    address they do not hold — which, on an invite-only install, is the whole gate.
    """
    id_token = answer.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        raise Refused("That sign-in did not come back with an identity.")
    claims = _claims(id_token)
    email = str(claims.get("email") or "").strip().lower()
    if not email:
        raise Refused("That Google account has no email address on it.")
    if claims.get("email_verified") not in (True, "true"):
        raise Refused("Google has not verified that address.")
    return email


def exchange(
    code: str, verifier: str, redirect_to: str, timeout: float = 10.0
) -> dict[str, object]:
    """Trade an authorization code for tokens, server side.

    The one network call in this module, and the reason the client secret never reaches a
    browser. Kept separate from `address_from` so the reading of an answer can be tested
    without a network at all.
    """
    body = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": _env(CLIENT_ID_ENV),
            "client_secret": _env(CLIENT_SECRET_ENV),
            "redirect_uri": redirect_to,
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        }
    ).encode("ascii")
    request = urllib.request.Request(  # noqa: S310 - TOKEN is a literal https URL
        TOKEN,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310
            loaded = json.loads(answer.read().decode("utf-8"))
    except Exception as error:  # noqa: BLE001 - any failure here is one refusal
        raise Refused("We couldn't finish that sign-in with Google.") from error
    if not isinstance(loaded, dict):
        raise Refused("We couldn't finish that sign-in with Google.")
    return loaded
