"""targum as an authorization server, for exactly one resource: its own `/mcp`.

A reader adds targum to Claude or ChatGPT by pressing Connect (targum-internal#80). That
needs a token that names a person, and the two connector directories both want it minted
the standard way — so this is OAuth 2.1: authorization code with PKCE, dynamic client
registration, and the two metadata documents a client reads before it knows any of that.

**Why not an API key.** A key pasted into somebody else's client is a bearer credential
with no scopes, no expiry and no way to take it back one client at a time. `serve.py`
already reasons this way about the start-up key and concludes that hosted has none at
all. The same argument ends here in a different place only because the directories
require a flow, not because a key would have been safe.

**This module knows the protocol and nothing else.** The rows are `accounts.Store`'s and
the routes are `serve.Handler`'s; what is here is the part that is neither — what a valid
request looks like, what the metadata says, and how a verifier is checked against a
challenge. It holds no state and touches no database.

**Three scopes, and only one of them spends** (design.md §12, "A scope is a press that
lasts"). `library` is the catalogue and what is at a link. `record` is the reader's own
words, read. `chat` is the one that writes and the one that costs credits, and it is
listed on the approval page with what it costs beside it, because a standing grant that
did not say so would be a worse seam than the press it replaces.

`chat` was called `check` until 2026-09-23, when §12 ("A cost is credits, and a credit is
a minute") renamed it: "checking your Hebrew" was this module's scope name leaking into
the reader's copy, and what a reader does in Claude or ChatGPT is have a conversation.
The old name is still honoured wherever a stored grant is read — see `RENAMED`.

**Everything a client sends is a claim.** Its name, its redirect list, its scope request:
all of it is written down and none of it is trusted. What the reader approved is stored
on the grant and read back from there, never from the token request that follows.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlparse

#: What a connector may be allowed to do. Ordered as the approval page lists them, which
#: is least to most: the library is public knowledge, the record is the reader's own, and
#: `chat` is the one that writes to it and spends their credits doing so.
SCOPES: tuple[tuple[str, str], ...] = (
    ("library", "Search the library and look up what is at a link"),
    ("record", "Read your words, your mistakes and your progress"),
    (
        "chat",
        "Read what you write in the language you're learning, keep the lines we correct, "
        "get texts and playlists ready for you to confirm, and add a language you practise",
    ),
)

#: Scopes that have been renamed, old name to new. **A grant is stored as the words the
#: reader approved**, so a rename that stopped here would quietly strip every connector
#: already authorised — `granted()` compares strings, and `granted("library check",
#: "chat")` is False. Read through `current()` instead of migrating the rows: a token is
#: short-lived and a refresh mints the new spelling, so the table converges on its own,
#: and a `REPLACE(scopes, 'check', 'chat')` over live rows is a substring edit on a column
#: whose values are space-joined words. This map is the whole cost of the rename.
RENAMED: dict[str, str] = {"check": "chat"}

#: The scope a client gets if it asks for nothing. The smallest one: a client that did
#: not say what it wanted has not been agreed to for anything else.
DEFAULT_SCOPE = "library"

#: The only scope that reaches a tool with `spends` set. Named once here so the rule is
#: greppable from either side of it.
SPENDING_SCOPE = "chat"

#: The MCP revisions this server will speak. The newest is what an `initialize` that asks
#: for something unknown is answered with, per the spec's version negotiation.
PROTOCOL_VERSIONS: tuple[str, ...] = ("2025-06-18", "2025-03-26")
LATEST_PROTOCOL = PROTOCOL_VERSIONS[0]

#: Where the connector lives on the box. One path, because there is one resource.
RESOURCE_PATH = "/mcp"

#: PKCE, and only S256. A client that sends `plain` is refused rather than downgraded:
#: `plain` makes the challenge equal to the verifier, which protects against nothing, and
#: every client either of these directories will send supports S256.
CHALLENGE_METHODS = ("S256",)

#: A client may register this many redirects, and each must be an exact URL. Enough for a
#: desktop client that offers a loopback port and a web one that offers a callback.
MOST_REDIRECTS = 16

#: What a client's registration may say its name is. Shown to the reader as the client's
#: claim about itself, so it is trimmed and length-capped and otherwise left alone — a
#: name that lies is a name that lies, and shortening it would not make it true.
MOST_NAME = 200

#: A registered client id and an authorization code are both `token_urlsafe`, so this is
#: what either looks like coming back.
_OPAQUE = re.compile(r"^[A-Za-z0-9_-]{16,512}$")


class OAuthError(Exception):
    """A request that fails in the way RFC 6749 §5.2 says to fail.

    Carries the error code the client reads, which is not the same thing as a sentence a
    reader reads: these reach a machine. What a *person* is shown when something goes
    wrong on the approval page is `serve`'s business and is written in the voice §6 asks
    for.
    """

    def __init__(self, code: str, description: str = "", status: int = 400) -> None:
        super().__init__(description or code)
        self.code = code
        self.description = description
        self.status = status

    def as_json(self) -> dict[str, str]:
        out = {"error": self.code}
        if self.description:
            out["error_description"] = self.description
        return out


@dataclass(frozen=True)
class Asked:
    """A validated authorization request, ready for the reader to approve or refuse."""

    client_id: str
    redirect: str
    scopes: tuple[str, ...]
    challenge: str
    state: str
    resource: str

    @property
    def scope_string(self) -> str:
        return " ".join(self.scopes)

    @property
    def spends(self) -> bool:
        """Whether what is being asked for includes the one scope that costs credits."""
        return SPENDING_SCOPE in self.scopes


def known_scopes(asked: str | None) -> tuple[str, ...]:
    """The scopes in a request that this server actually has, in the order it lists them.

    An unknown scope is dropped rather than refused. RFC 6749 allows either, and dropping
    is the kinder half: a client that asks for `profile` out of habit should get a working
    connector limited to what targum offers, not an error page the reader cannot act on.
    What the reader is shown, and what is stored, is what survives this.

    A renamed scope is honoured rather than dropped, which is not the same kindness. A
    client that registered before 2026-09-23 has `check` written into its own stored
    configuration and will keep asking for it; dropping it would leave the reader with a
    silent fall back to `library` alone and an approval page that no longer offers the
    scope they had.
    """
    wanted = {RENAMED.get(word, word) for word in (asked or "").replace(",", " ").split() if word}
    kept = tuple(name for name, _ in SCOPES if name in wanted)
    return kept or (DEFAULT_SCOPE,)


def describe_scopes(scopes: tuple[str, ...]) -> list[dict[str, str]]:
    """The scopes as the approval page draws them: the name, and what it lets a client do."""
    said = dict(SCOPES)
    return [{"name": name, "says": said[name]} for name in scopes if name in said]


def current(scopes: str | None) -> tuple[str, ...]:
    """A stored scope string as the names this server uses today.

    A grant holds the words the reader approved, and those outlive a rename: the
    connector David authorised on 2026-09-22 holds `check`, which no longer names
    anything. Mapping on the way out keeps every live grant working and keeps exactly one
    spelling in the code above this line. An unknown scope is dropped, as `known_scopes`
    drops one arriving from a client — a name this server has never had grants nothing.
    """
    known = {name for name, _ in SCOPES}
    said = []
    for word in (scopes or "").split():
        name = RENAMED.get(word, word)
        if name in known and name not in said:
            said.append(name)
    return tuple(said)


def granted(scopes: str | None, wanted: str) -> bool:
    """Whether a token's scope string carries one scope.

    Takes the string straight off the token row, through `current()` so a grant made
    under an older spelling still carries what the reader agreed to. Nothing here reads a
    scope out of a request, and this signature is the place that is easiest to get wrong
    later.
    """
    return wanted in current(scopes)


def verify_challenge(verifier: str, challenge: str) -> bool:
    """Whether a PKCE verifier matches the S256 challenge stored with the grant.

    Compared in constant time, because it is a secret being checked against a stored
    value, which is the shape of comparison that leaks when it is done with `==`.
    """
    if not verifier or not challenge:
        return False
    if not 43 <= len(verifier) <= 128:
        return False
    digested = hashlib.sha256(verifier.encode("ascii", "ignore")).digest()
    made = base64.urlsafe_b64encode(digested).rstrip(b"=").decode("ascii")
    return secrets.compare_digest(made, challenge)


def check_redirect(given: str, registered: list[str]) -> str:
    """The redirect to use, or refuse.

    **Exact match, always.** Prefix matching is how redirect allowlists are got round, and
    a client that registered `https://claude.ai/api/mcp/auth_callback` has no reason to
    arrive with anything else. A request naming no redirect gets the registered one only
    when there is exactly one, because choosing on the client's behalf between two is
    guessing where it wanted to go.
    """
    if not registered:
        raise OAuthError("invalid_client", "That client registered no redirect.")
    if not given:
        if len(registered) == 1:
            return registered[0]
        raise OAuthError("invalid_request", "Name which redirect to come back to.")
    for one in registered:
        if secrets.compare_digest(given, one):
            return given
    raise OAuthError("invalid_request", "That redirect is not one this client registered.")


def origin_of(redirect: str) -> str:
    """The scheme and host a redirect goes to, for the page's `form-action`.

    An origin and never the whole URL: a policy naming a path would be a policy that
    breaks the moment a client adds a query, and `form-action` matches on origin anyway.
    Empty for anything that is not an absolute http(s) URL, which `check_redirect` has
    already refused by the time this is asked — so a caller that somehow reaches here
    with one widens the policy by nothing rather than by a value it did not check.
    """
    parsed = urlparse(redirect)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def check_registration(payload: dict[str, Any]) -> tuple[str, list[str]]:
    """What a dynamic registration is allowed to say (RFC 7591).

    Written by strangers, so the only thing checked is the only thing that has to be
    right: the redirects are absolute `https` URLs, or loopback `http`, which is what a
    desktop client that listens on a port of its own needs and what the spec carves out
    for exactly that.
    """
    redirects = payload.get("redirect_uris")
    if not isinstance(redirects, list) or not redirects:
        raise OAuthError("invalid_redirect_uri", "Give at least one redirect_uris entry.")
    if len(redirects) > MOST_REDIRECTS:
        raise OAuthError("invalid_redirect_uri", "That is more redirects than we keep.")
    kept: list[str] = []
    for one in redirects:
        if not isinstance(one, str) or not one:
            raise OAuthError("invalid_redirect_uri", "A redirect has to be a URL.")
        parsed = urlparse(one)
        if parsed.fragment:
            raise OAuthError("invalid_redirect_uri", "A redirect may not carry a fragment.")
        loopback = parsed.hostname in ("127.0.0.1", "::1", "localhost")
        if parsed.scheme == "https" or (parsed.scheme == "http" and loopback):
            kept.append(one)
            continue
        raise OAuthError("invalid_redirect_uri", "A redirect has to be https, or http on loopback.")
    name = payload.get("client_name")
    return (name if isinstance(name, str) else "")[:MOST_NAME], kept


def read_request(query: dict[str, list[str]]) -> Asked:
    """Read an `/oauth/authorize` query, or say what is wrong with it.

    Only the shape is checked here — that a client id looks like one, that the response
    type is `code`, that PKCE is present and S256. Whether the client exists and whether
    the redirect is one of its own needs the database, and is `serve`'s to do with what
    `check_redirect` returns.
    """

    def one(name: str) -> str:
        return (query.get(name) or [""])[0].strip()

    if one("response_type") != "code":
        raise OAuthError("unsupported_response_type", "This server issues codes.")
    client_id = one("client_id")
    if not _OPAQUE.match(client_id):
        raise OAuthError("invalid_client", "That is not a client id.")
    method = one("code_challenge_method")
    if method not in CHALLENGE_METHODS:
        raise OAuthError("invalid_request", "This server takes S256 challenges.")
    challenge = one("code_challenge")
    if not 43 <= len(challenge) <= 128:
        raise OAuthError("invalid_request", "That is not an S256 challenge.")
    return Asked(
        client_id=client_id,
        redirect=one("redirect_uri"),
        scopes=known_scopes(one("scope")),
        challenge=challenge,
        state=one("state")[:512],
        # RFC 8707. Recorded and answered with, so a token minted for targum says it is
        # for targum; a client that names somebody else's resource is not refused here,
        # because the only resource this server has is its own and the mismatch shows up
        # as a token that does not work where they meant to use it.
        resource=one("resource")[:512],
    )


def back_to(redirect: str, **fields: str) -> str:
    """The client's redirect with the answer on it, dropping anything empty.

    A query rather than a fragment: the code has to reach the client's server, and a
    fragment never leaves the browser.
    """
    said = {key: value for key, value in fields.items() if value}
    joiner = "&" if urlparse(redirect).query else "?"
    return f"{redirect}{joiner}{urlencode(said)}"


def protocol_version(asked: str | None) -> str:
    """Which MCP revision to answer an `initialize` with.

    The spec says to reply with a version we support, which may not be the one asked for;
    the client then decides whether it can live with that. An unknown version is answered
    with the newest rather than refused, because a client from next year asking for next
    year's revision is more likely to cope than to have meant nothing.
    """
    return asked if asked in PROTOCOL_VERSIONS else LATEST_PROTOCOL


def protected_resource(address: str) -> dict[str, Any]:
    """RFC 9728, the document a client reads off the 401 to find out who issues tokens."""
    return {
        "resource": f"{address}{RESOURCE_PATH}",
        "authorization_servers": [address],
        "scopes_supported": [name for name, _ in SCOPES],
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{address}/connect",
    }


def authorization_server(address: str) -> dict[str, Any]:
    """RFC 8414, what this server does and where each door is.

    `code` and S256 only, and both grant types said out loud: a client reads this to
    decide whether it can talk to us at all, and leaving `refresh_token` out would make
    every connector re-ask the reader every hour.
    """
    return {
        "issuer": address,
        "authorization_endpoint": f"{address}/oauth/authorize",
        "token_endpoint": f"{address}/oauth/token",
        "registration_endpoint": f"{address}/oauth/register",
        "revocation_endpoint": f"{address}/oauth/revoke",
        "scopes_supported": [name for name, _ in SCOPES],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": list(CHALLENGE_METHODS),
        "token_endpoint_auth_methods_supported": ["none"],
        "service_documentation": f"{address}/connect",
    }


def challenge_header(address: str) -> str:
    """What a 401 from `/mcp` says, so a client knows where to go and come back from.

    The `resource_metadata` parameter is how a client finds the document above without
    being told out of band, and it is the whole reason a connector can be added by
    pasting one URL.
    """
    return (
        f'Bearer realm="targum", resource_metadata="{address}/.well-known/oauth-protected-resource"'
    )


def bearer_from(header: str | None) -> str:
    """The token out of an Authorization header, or empty.

    Case-insensitive on the scheme, because the RFC says so and clients differ.
    """
    if not header:
        return ""
    parts = header.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return ""
    return parts[1].strip()


def token_reply(access: str, refresh: str, scopes: str, seconds: int) -> dict[str, Any]:
    """The body of a successful `/oauth/token`."""
    out: dict[str, Any] = {
        "access_token": access,
        "token_type": "Bearer",
        "expires_in": seconds,
        "scope": scopes,
    }
    if refresh:
        out["refresh_token"] = refresh
    return out


def registration_reply(client_id: str, name: str, redirects: list[str], made: int) -> str:
    """The body of a successful `/oauth/register`, as JSON.

    No client secret: every client this server will meet is public — a desktop app or a
    browser — and a secret shipped inside one is not a secret. `token_endpoint_auth_method`
    says `none` for the same reason, and PKCE is what stands in its place.
    """
    return json.dumps(
        {
            "client_id": client_id,
            "client_id_issued_at": made // 1000,
            "client_name": name,
            "redirect_uris": redirects,
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }
    )


__all__ = [
    "CHALLENGE_METHODS",
    "DEFAULT_SCOPE",
    "LATEST_PROTOCOL",
    "MOST_REDIRECTS",
    "PROTOCOL_VERSIONS",
    "RENAMED",
    "RESOURCE_PATH",
    "SCOPES",
    "SPENDING_SCOPE",
    "Asked",
    "OAuthError",
    "authorization_server",
    "back_to",
    "bearer_from",
    "challenge_header",
    "check_redirect",
    "check_registration",
    "current",
    "describe_scopes",
    "granted",
    "known_scopes",
    "origin_of",
    "protected_resource",
    "protocol_version",
    "read_request",
    "registration_reply",
    "token_reply",
    "verify_challenge",
]
