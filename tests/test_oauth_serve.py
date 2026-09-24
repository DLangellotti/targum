"""The connector's doors, driven the way a client drives them.

`test_oauth.py` covers the protocol and the rows. This runs a real server and walks the
whole flow — discover, register, approve, exchange, refresh — because the parts that
break in practice are the seams between those, not the pieces.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
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
    # Armed, the way `targum.env` arms it on the box: the connector ships dark
    # and these tests are about what it does once somebody has turned it on.
    os.environ["TARGUM_CONNECTOR"] = "1"
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
    assert "add a language you practise" not in page, "not asked for, so not granted"


def test_the_spending_scope_says_chatting_is_included(connected: tuple[int, str, Path]) -> None:
    """design.md §12, 2026-09-24: a message rounds to no credits, so the page says that
    chatting is included, and names no allowance that reads as being spent."""
    port, session, _ = connected
    client_id = a_client(port)
    _, challenge = pkce()
    _, body, _ = get(
        port,
        f"/oauth/authorize?{an_authorize(client_id, challenge, 'library check')}",
        session=session,
    )
    page = body.decode()
    assert "add a language you practise" in page
    assert "Chatting is included." in page
    said = page.split("<main", 1)[1]  # the page inlines `reader.css`, which says plenty
    assert "credits" not in said and "hours" not in said, "no allowance on this page"
    assert '<b class="host">claude.ai</b>' in page, "where Connect sends the reader, in bold"


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
    assert b"We don't know that client" not in body, "the client's detail stays in the log"
    assert b"Your app sent a request we couldn't check." in body


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


# --- the doors a reader meets ----------------------------------------------------


def test_connect_is_public_and_says_how(connected: tuple[int, str, Path]) -> None:
    """The reader it is written for has not got in yet (note 2)."""
    port, _, _ = connected
    status, body, _ = get(port, "/connect")
    assert status == 200
    page = body.decode()
    assert f"{PUBLIC}/mcp" in page, "the one thing they have to copy exactly"
    assert "In Claude" in page and "In ChatGPT" in page
    assert "claude mcp add" in page


def test_connect_names_mcp_once_and_leads_with_what_they_get(
    connected: tuple[int, str, Path],
) -> None:
    """§6: on a public page the copy sells, and our words are not the reader's."""
    port, _, _ = connected
    _, body, _ = get(port, "/connect")
    page = body.decode()
    where = page.index("targum in Claude and ChatGPT")
    assert "MCP" not in page[:where], "the headline is what they get, not what it is"
    assert page.count("MCP-server") == 0
    assert "connector" not in page.split("<main")[0], "not a word a stranger decodes"


def test_connect_promises_no_tick_and_tells_a_stranger_they_need_an_account(
    connected: tuple[int, str, Path],
) -> None:
    """design.md §12, 2026-09-24: the grant is one press, so nothing on /connect says
    "tick" or "choose what it can see"; and connecting needs an account, which a stranger
    has not got, so the hero says so and a signed-in reader is not told it."""
    port, session, _ = connected
    stranger = get(port, "/connect")[1].decode()
    said = stranger.split("<main", 1)[1]
    assert "Tick what you want" not in said and "choose what it can see" not in said
    assert "Open Customize, then Connectors." in said, "where Claude keeps them now"
    assert 'class="need-account"' in said and 'href="#join"' in said
    assert 'id="join"' in said
    reader = get(port, "/connect", session=session)[1].decode()
    assert 'class="need-account"' not in reader


def test_connect_guesses_nothing_about_which_app(connected: tuple[int, str, Path]) -> None:
    """A reader in the wrong block can see that they are; a page that chose cannot."""
    port, _, _ = connected
    _, body, _ = get(port, "/connect")
    page = body.decode()
    for host in ("In Claude", "In ChatGPT", "In Claude Code"):
        assert host in page, f"{host} is offered whoever is reading"


def test_a_connection_is_listed_on_the_account_and_can_be_taken_back(
    connected: tuple[int, str, Path],
) -> None:
    """design.md §12: a grant that lasts is visible somewhere the reader can end it."""
    port, session, _ = connected
    client_id = a_client(port)
    verifier, challenge = pkce()
    code = a_code(port, session, client_id, challenge, "library record")
    post(
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
        session=session,
    )
    status, body, _ = get(port, "/account/me", session=session)
    assert status == 200
    mine = [one for one in json.loads(body)["connections"] if one["client"] == client_id]
    assert mine and mine[0]["name"] == "Claude"
    assert mine[0]["scopes"] == "library record"

    status, body, _ = post(
        port,
        "/account/disconnect",
        json.dumps({"client": client_id}),
        kind="application/json",
        session=session,
    )
    assert status == 200 and json.loads(body)["disconnected"] >= 1
    _, body, _ = get(port, "/account/me", session=session)
    assert not [one for one in json.loads(body)["connections"] if one["client"] == client_id]


def test_nobody_can_disconnect_for_somebody_else(connected: tuple[int, str, Path]) -> None:
    port, _, _ = connected
    status, _, _ = post(
        port, "/account/disconnect", json.dumps({"client": "whatever"}), kind="application/json"
    )
    assert status == 401


def test_a_token_is_never_in_the_account_answer(connected: tuple[int, str, Path]) -> None:
    port, session, _ = connected
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
    _, body, _ = get(port, "/account/me", session=session)
    assert token not in body.decode(), "a credential is not data"


# --- the switch (targum-internal#80) ---------------------------------------------


def test_every_door_is_shut_while_the_connector_is_off(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> None:
    """It ships dark, the way the front door does: the day it opens is one line in
    targum.env rather than a release."""
    tmp = tmp_path_factory.mktemp("shut")
    store_path = tmp / "targum.db"
    Store(store_path)
    port = free_port()
    was = os.environ.pop("TARGUM_CONNECTOR", None)
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
    try:
        for _ in range(60):
            try:
                probe = HTTPConnection("127.0.0.1", port, timeout=1)
                probe.request("GET", "/health")
                probe.getresponse().read()
                probe.close()
                break
            except OSError:
                time.sleep(0.1)
        for route in [*serve.OAUTH_METADATA, "/connect", "/oauth/authorize", "/mcp"]:
            assert get(port, route)[0] == 404, route
        for route in serve.OAUTH_POSTS:
            assert post(port, route, "")[0] == 404, route
        assert post(port, "/mcp", '{"jsonrpc":"2.0","id":1,"method":"ping"}')[0] == 404
        assert b"/connect" not in get(port, "/sitemap.xml")[1]
    finally:
        if was is not None:
            os.environ["TARGUM_CONNECTOR"] = was


def test_the_approval_page_lets_the_press_reach_the_client(
    connected: tuple[int, str, Path],
) -> None:
    """`form-action` is enforced on the redirect, not only on the action URL. With
    `'self'` alone the POST leaves and Chrome silently refuses to follow the 303 to the
    client's callback — the reader presses Connect and the page sits there, with nothing
    in the network log and nothing a page script can see.

    Found on the box on 2026-09-23 and invisible to every test before this one: the
    suite drives this flow over `HTTPConnection`, where no policy exists.
    """
    port, session, _ = connected
    client_id = a_client(port)
    _, challenge = pkce()
    status, _, headers = get(
        port, f"/oauth/authorize?{an_authorize(client_id, challenge)}", session=session
    )
    assert status == 200
    policy = headers["content-security-policy"]
    said = next(one.strip() for one in policy.split(";") if one.strip().startswith("form-action"))
    assert said == "form-action 'self' https://claude.ai", said


def test_only_that_one_redirect_is_named(connected: tuple[int, str, Path]) -> None:
    """The origin comes from what `check_redirect` matched against the registration,
    never from the request — so the policy widens by exactly what the reader was shown."""
    port, session, _ = connected
    client_id = a_client(port, ["https://example.test/cb"])
    _, challenge = pkce()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": "https://example.test/cb",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "library",
        }
    )
    _, _, headers = get(port, f"/oauth/authorize?{query}", session=session)
    policy = headers["content-security-policy"]
    assert "form-action 'self' https://example.test" in policy
    assert "claude.ai" not in policy


def test_every_other_page_keeps_the_narrow_policy(connected: tuple[int, str, Path]) -> None:
    port, _, _ = connected
    _, _, headers = get(port, "/connect")
    policy = headers["content-security-policy"]
    assert "form-action 'self';" in policy or policy.rstrip().endswith("form-action 'self'")
