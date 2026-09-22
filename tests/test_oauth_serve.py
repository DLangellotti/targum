"""The connector's doors, driven the way a client drives them.

`test_oauth.py` covers the protocol and the rows. This runs a real server and walks the
whole flow — discover, register, approve, exchange, refresh — because the parts that
break in practice are the seams between those, not the pieces.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
from collections.abc import Callable
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import pytest

from targum import serve
from targum.accounts import Store

PUBLIC = "https://targum.page"
HOST = "targum.page"
CALLBACK = "https://claude.ai/api/mcp/auth_callback"


@pytest.fixture(scope="module")
def connected(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> tuple[int, str, Path]:
    """A hosted server with a reader signed in, as the deployment runs it."""
    tmp = tmp_path_factory.mktemp("connector")
    store_path = tmp / "targum.db"
    store = Store(store_path)
    token = store.start_sign_in("reader@example.com")
    signed_in = store.finish_sign_in(token)
    assert signed_in is not None
    port = free_port()
    threading.Thread(
        target=lambda: serve.start(
            out=tmp / "out",
            port=port,
            open_browser=False,
            store=store_path,
            require_account=True,
            public_address=PUBLIC,
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
    return port, signed_in[1], store_path


def get(
    port: int, path: str, session: str = "", host: str = HOST
) -> tuple[int, bytes, dict[str, str]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("GET", path, skip_host=True)
    conn.putheader("Host", host)
    if session:
        conn.putheader("Cookie", f"targum_session={session}")
    conn.endheaders()
    response = conn.getresponse()
    body = response.read()
    headers = {key.lower(): value for key, value in response.getheaders()}
    conn.close()
    return response.status, body, headers


def post(
    port: int,
    path: str,
    body: str,
    kind: str = "application/x-www-form-urlencoded",
    session: str = "",
    host: str = HOST,
) -> tuple[int, bytes, dict[str, str]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", path, skip_host=True)
    conn.putheader("Host", host)
    conn.putheader("Content-Type", kind)
    conn.putheader("Content-Length", str(len(body.encode())))
    if session:
        conn.putheader("Cookie", f"targum_session={session}")
    conn.endheaders()
    conn.send(body.encode())
    response = conn.getresponse()
    got = response.read()
    headers = {key.lower(): value for key, value in response.getheaders()}
    conn.close()
    return response.status, got, headers


def pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


def a_client(port: int, redirects: list[str] | None = None) -> str:
    status, body, _ = post(
        port,
        "/oauth/register",
        json.dumps({"client_name": "Claude", "redirect_uris": redirects or [CALLBACK]}),
        kind="application/json",
    )
    assert status == 201, body
    return str(json.loads(body)["client_id"])


def an_authorize(client_id: str, challenge: str, scope: str = "library record") -> str:
    return urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": CALLBACK,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": scope,
            "state": "s-123",
        }
    )


def a_code(port: int, session: str, client_id: str, challenge: str, scope: str) -> str:
    """Walk the approval page and come back with a code."""
    query = an_authorize(client_id, challenge, scope)
    status, _, _ = get(port, f"/oauth/authorize?{query}", session=session)
    assert status == 200
    status, _, headers = post(
        port,
        "/oauth/authorize",
        urlencode({"asked": query, "press": "approve"}),
        session=session,
    )
    assert status == 303, headers
    return parse_qs(urlparse(headers["location"]).query)["code"][0]


# --- discovery -------------------------------------------------------------------


def test_the_metadata_is_public_and_points_at_the_box(connected: tuple[int, str, Path]) -> None:
    port, _, _ = connected
    status, body, headers = get(port, "/.well-known/oauth-protected-resource")
    assert status == 200
    said = json.loads(body)
    assert said["resource"] == f"{PUBLIC}/mcp"
    assert said["authorization_servers"] == [PUBLIC]
    assert headers["access-control-allow-origin"] == "*", "read from the client's origin"

    status, body, _ = get(port, "/.well-known/oauth-authorization-server")
    assert status == 200
    said = json.loads(body)
    assert said["token_endpoint"] == f"{PUBLIC}/oauth/token"
    assert said["code_challenge_methods_supported"] == ["S256"]


def test_discovery_needs_no_account(connected: tuple[int, str, Path]) -> None:
    """The client reading these has no account and will never have one."""
    port, _, _ = connected
    for route in serve.OAUTH_METADATA:
        status, _, _ = get(port, route)
        assert status == 200, route


# --- registration ----------------------------------------------------------------


def test_a_client_registers_itself_and_gets_no_secret(connected: tuple[int, str, Path]) -> None:
    port, _, _ = connected
    status, body, _ = post(
        port,
        "/oauth/register",
        json.dumps({"client_name": "Claude", "redirect_uris": [CALLBACK]}),
        kind="application/json",
    )
    assert status == 201
    said = json.loads(body)
    assert said["client_id"] and "client_secret" not in said
    assert said["token_endpoint_auth_method"] == "none"


def test_a_registration_with_a_bad_redirect_is_refused(connected: tuple[int, str, Path]) -> None:
    port, _, _ = connected
    status, body, _ = post(
        port,
        "/oauth/register",
        json.dumps({"redirect_uris": ["http://evil.test/cb"]}),
        kind="application/json",
    )
    assert status == 400
    assert json.loads(body)["error"] == "invalid_redirect_uri"


# --- the approval page -----------------------------------------------------------


def test_the_page_says_what_is_being_asked_for(connected: tuple[int, str, Path]) -> None:
    port, session, _ = connected
    client_id = a_client(port)
    _, challenge = pkce()
    status, body, _ = get(
        port,
        f"/oauth/authorize?{an_authorize(client_id, challenge)}",
        session=session,
    )
    assert status == 200
    page = body.decode()
    assert "Claude" in page, "the client's claim about itself, shown as one"
    assert "Search the library" in page
    assert "Read your words" in page
    assert "Check your Hebrew" not in page, "not asked for, so not granted"


def test_the_spending_scope_says_what_it_costs(connected: tuple[int, str, Path]) -> None:
    """design.md §12: a standing grant that did not say so is a worse seam than a press."""
    port, session, _ = connected
    client_id = a_client(port)
    _, challenge = pkce()
    _, body, _ = get(
        port,
        f"/oauth/authorize?{an_authorize(client_id, challenge, 'library check')}",
        session=session,
    )
    page = body.decode()
    assert "Check your Hebrew" in page
    assert "hours" in page, "in hours, and never in money"
    assert str(serve.UPLOAD_HOURS) in page


def test_a_signed_out_reader_signs_in_and_is_brought_back(
    connected: tuple[int, str, Path],
) -> None:
    port, _, _ = connected
    client_id = a_client(port)
    _, challenge = pkce()
    query = an_authorize(client_id, challenge)
    status, body, headers = get(port, f"/oauth/authorize?{query}")
    assert status == 200
    assert b"Send a link" in body or b"Email" in body, "the sign-in door, not the holding page"
    assert serve.CONNECT_COOKIE in headers.get("set-cookie", ""), "so they come back here"


def test_a_request_we_cannot_read_is_a_page_and_never_a_redirect(
    connected: tuple[int, str, Path],
) -> None:
    """The address it wants to go back to is one nobody has checked."""
    port, session, _ = connected
    _, challenge = pkce()
    query = an_authorize("not-a-real-client-id-at-all", challenge)
    status, body, headers = get(port, f"/oauth/authorize?{query}", session=session)
    assert status == 400
    assert "location" not in headers
    assert b"couldn't finish" in body


def test_an_unregistered_redirect_never_receives_anything(
    connected: tuple[int, str, Path],
) -> None:
    port, session, _ = connected
    client_id = a_client(port)
    _, challenge = pkce()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "https://evil.test/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "library",
        }
    )
    status, _, headers = get(port, f"/oauth/authorize?{query}", session=session)
    assert status == 400 and "location" not in headers


def test_not_now_tells_the_client_so(connected: tuple[int, str, Path]) -> None:
    port, session, _ = connected
    client_id = a_client(port)
    _, challenge = pkce()
    query = an_authorize(client_id, challenge)
    status, _, headers = post(
        port,
        "/oauth/authorize",
        urlencode({"asked": query, "press": "refuse"}),
        session=session,
    )
    assert status == 303
    back = parse_qs(urlparse(headers["location"]).query)
    assert back["error"] == ["access_denied"]
    assert back["state"] == ["s-123"], "so the client knows which ask this answers"


def test_nobody_signed_in_cannot_approve(connected: tuple[int, str, Path]) -> None:
    port, _, _ = connected
    client_id = a_client(port)
    _, challenge = pkce()
    status, _, _ = post(
        port,
        "/oauth/authorize",
        urlencode({"asked": an_authorize(client_id, challenge), "press": "approve"}),
    )
    assert status == 401


def test_the_form_cannot_name_its_own_scopes(connected: tuple[int, str, Path]) -> None:
    """A press carries which request it answers; every field is read again from that."""
    port, session, store_path = connected
    client_id = a_client(port)
    verifier, challenge = pkce()
    code = a_code(port, session, client_id, challenge, "library")
    store = Store(store_path)
    granted = store.spend_grant(code)
    assert granted is not None and granted["scopes"] == "library"


# --- the token endpoint ----------------------------------------------------------


def test_a_code_becomes_a_working_token(connected: tuple[int, str, Path]) -> None:
    port, session, store_path = connected
    client_id = a_client(port)
    verifier, challenge = pkce()
    code = a_code(port, session, client_id, challenge, "library record")
    status, body, headers = post(
        port,
        "/oauth/token",
        urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "redirect_uri": CALLBACK,
                "code_verifier": verifier,
            }
        ),
    )
    assert status == 200, body
    said = json.loads(body)
    assert said["token_type"] == "Bearer" and said["scope"] == "library record"
    assert said["expires_in"] > 0 and said["refresh_token"]
    assert headers["cache-control"] == "no-store", "not a thing to leave in a proxy"

    who = Store(store_path).bearer(said["access_token"])
    assert who is not None and who[0].email == "reader@example.com"


def test_the_wrong_verifier_gets_nothing(connected: tuple[int, str, Path]) -> None:
    port, session, _ = connected
    client_id = a_client(port)
    _, challenge = pkce()
    code = a_code(port, session, client_id, challenge, "library")
    other, _ = pkce()
    status, body, _ = post(
        port,
        "/oauth/token",
        urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "redirect_uri": CALLBACK,
                "code_verifier": other,
            }
        ),
    )
    assert status == 400 and json.loads(body)["error"] == "invalid_grant"


def test_a_code_cannot_be_spent_twice(connected: tuple[int, str, Path]) -> None:
    port, session, _ = connected
    client_id = a_client(port)
    verifier, challenge = pkce()
    code = a_code(port, session, client_id, challenge, "library")
    form = urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "redirect_uri": CALLBACK,
            "code_verifier": verifier,
        }
    )
    assert post(port, "/oauth/token", form)[0] == 200
    assert post(port, "/oauth/token", form)[0] == 400, "a replay is a replay"


def test_another_client_cannot_spend_a_code(connected: tuple[int, str, Path]) -> None:
    port, session, _ = connected
    mine = a_client(port)
    theirs = a_client(port)
    verifier, challenge = pkce()
    code = a_code(port, session, mine, challenge, "library")
    status, body, _ = post(
        port,
        "/oauth/token",
        urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": theirs,
                "redirect_uri": CALLBACK,
                "code_verifier": verifier,
            }
        ),
    )
    assert status == 400 and json.loads(body)["error"] == "invalid_grant"


def test_an_unknown_grant_type_is_refused(connected: tuple[int, str, Path]) -> None:
    port, _, _ = connected
    status, body, _ = post(port, "/oauth/token", urlencode({"grant_type": "password"}))
    assert status == 400 and json.loads(body)["error"] == "unsupported_grant_type"


# --- refresh and revoke ----------------------------------------------------------


def test_a_refresh_token_rotates_and_the_old_one_dies(connected: tuple[int, str, Path]) -> None:
    port, session, store_path = connected
    client_id = a_client(port)
    verifier, challenge = pkce()
    code = a_code(port, session, client_id, challenge, "library record")
    _, body, _ = post(
        port,
        "/oauth/token",
        urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "redirect_uri": CALLBACK,
                "code_verifier": verifier,
            }
        ),
    )
    first = json.loads(body)
    refreshing = urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": first["refresh_token"],
            "client_id": client_id,
        }
    )
    status, body, _ = post(port, "/oauth/token", refreshing)
    assert status == 200
    second = json.loads(body)
    assert second["access_token"] != first["access_token"]
    assert second["scope"] == "library record", "a refresh never widens what was granted"
    assert Store(store_path).bearer(second["access_token"]) is not None
    assert post(port, "/oauth/token", refreshing)[0] == 400, "presented twice means it leaked"


def test_revoking_says_nothing_about_what_it_was(connected: tuple[int, str, Path]) -> None:
    port, session, store_path = connected
    client_id = a_client(port)
    verifier, challenge = pkce()
    code = a_code(port, session, client_id, challenge, "library")
    _, body, _ = post(
        port,
        "/oauth/token",
        urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "redirect_uri": CALLBACK,
                "code_verifier": verifier,
            }
        ),
    )
    token = json.loads(body)["access_token"]
    assert post(port, "/oauth/revoke", urlencode({"token": token}))[0] == 200
    assert Store(store_path).bearer(token) is None
    # The same answer for a token that never existed, or the endpoint is a way to ask.
    assert post(port, "/oauth/revoke", urlencode({"token": "never-was-one"}))[0] == 200


# --- the rails around it ---------------------------------------------------------


def test_another_origin_cannot_drive_any_of_it(connected: tuple[int, str, Path]) -> None:
    port, session, _ = connected
    status, _, _ = post(port, "/oauth/token", urlencode({"grant_type": "x"}), host="evil.test")
    assert status == 404, "the host allowlist stands in front of everything that posts"
