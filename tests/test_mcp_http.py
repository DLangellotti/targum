"""The connector over HTTP, driven the way a host drives it.

The flow a client actually walks — 401, discover, connect, initialize, list, call — and
the two things that must stay true underneath it: a scope decides what is listed, and a
session cookie is not a way in.
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
from urllib.parse import parse_qs, urlencode, urlparse

import pytest

from targum import mcp_http, oauth, serve
from targum.accounts import Store

PUBLIC = "https://targum.page"
HOST = "targum.page"
CALLBACK = "https://claude.ai/api/mcp/auth_callback"


@pytest.fixture(scope="module")
def box(tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]) -> tuple[int, str]:
    tmp = tmp_path_factory.mktemp("mcp")
    store_path = tmp / "targum.db"
    store = Store(store_path)
    signed_in = store.finish_sign_in(store.start_sign_in("reader@example.com"))
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
    return port, signed_in[1]


def send(
    port: int,
    method: str,
    path: str,
    body: str = "",
    kind: str = "application/json",
    token: str = "",
    session: str = "",
    host: str = HOST,
) -> tuple[int, bytes, dict[str, str]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=10)
    conn.putrequest(method, path, skip_host=True)
    conn.putheader("Host", host)
    if body:
        conn.putheader("Content-Type", kind)
        conn.putheader("Content-Length", str(len(body.encode())))
    if token:
        conn.putheader("Authorization", f"Bearer {token}")
    if session:
        conn.putheader("Cookie", f"targum_session={session}")
    conn.endheaders()
    if body:
        conn.send(body.encode())
    response = conn.getresponse()
    got = response.read()
    headers = {key.lower(): value for key, value in response.getheaders()}
    conn.close()
    return response.status, got, headers


def rpc(port: int, token: str, method: str, params: dict | None = None, at: int = 1) -> dict:
    payload = {"jsonrpc": "2.0", "id": at, "method": method}
    if params is not None:
        payload["params"] = params
    status, body, _ = send(port, "POST", "/mcp", json.dumps(payload), token=token)
    assert status == 200, (status, body)
    return dict(json.loads(body))


def a_token(port: int, scope: str) -> str:
    """Walk the whole flow and come out with an access token carrying `scope`."""
    _, registered, _ = send(
        port,
        "POST",
        "/oauth/register",
        json.dumps({"client_name": "Claude", "redirect_uris": [CALLBACK]}),
    )
    client_id = json.loads(registered)["client_id"]
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": CALLBACK,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": scope,
        }
    )
    _, _, headers = send(
        port,
        "POST",
        "/oauth/authorize",
        urlencode({"asked": query, "press": "approve"}),
        kind="application/x-www-form-urlencoded",
        session=SESSION[0],
    )
    code = parse_qs(urlparse(headers["location"]).query)["code"][0]
    _, body, _ = send(
        port,
        "POST",
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
        kind="application/x-www-form-urlencoded",
    )
    return str(json.loads(body)["access_token"])


#: The signed-in session, filled by the first test that needs one. A list so `a_token`
#: can reach it without every test unpacking a fixture it does not otherwise use.
SESSION: list[str] = []


@pytest.fixture(autouse=True)
def _session(box: tuple[int, str]) -> None:
    if not SESSION:
        SESSION.append(box[1])


# --- the way in ------------------------------------------------------------------


def test_no_token_is_a_401_that_says_where_to_go(box: tuple[int, str]) -> None:
    """The 401 is the first link of the chain that makes "paste one URL" work."""
    port, _ = box
    status, _, headers = send(port, "POST", "/mcp", '{"jsonrpc":"2.0","id":1,"method":"ping"}')
    assert status == 401
    said = headers["www-authenticate"]
    assert said.startswith("Bearer")
    assert f"{PUBLIC}/.well-known/oauth-protected-resource" in said


def test_a_session_cookie_is_not_a_way_in(box: tuple[int, str]) -> None:
    """A browser can be made to POST cross-site; a client carries a token on purpose."""
    port, session = box
    status, _, _ = send(
        port, "POST", "/mcp", '{"jsonrpc":"2.0","id":1,"method":"ping"}', session=session
    )
    assert status == 401


def test_a_made_up_token_is_a_401(box: tuple[int, str]) -> None:
    port, _ = box
    status, _, _ = send(
        port, "POST", "/mcp", '{"jsonrpc":"2.0","id":1,"method":"ping"}', token="not-a-token"
    )
    assert status == 401


def test_a_revoked_token_stops_working(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library")
    assert rpc(port, token, "ping")["result"] == {}
    send(
        port,
        "POST",
        "/oauth/revoke",
        urlencode({"token": token}),
        kind="application/x-www-form-urlencoded",
    )
    status, _, _ = send(
        port, "POST", "/mcp", '{"jsonrpc":"2.0","id":1,"method":"ping"}', token=token
    )
    assert status == 401


def test_get_says_there_is_no_stream(box: tuple[int, str]) -> None:
    port, _ = box
    status, _, headers = send(port, "GET", "/mcp")
    assert status == 405 and headers["allow"] == "POST"


# --- the protocol ----------------------------------------------------------------


def test_initialize_negotiates_and_says_what_this_is(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library")
    said = rpc(port, token, "initialize", {"protocolVersion": oauth.LATEST_PROTOCOL})["result"]
    assert said["protocolVersion"] == oauth.LATEST_PROTOCOL
    assert said["serverInfo"]["name"] == "targum"
    assert "tools" in said["capabilities"] and "prompts" in said["capabilities"]
    assert "you cannot press it for them" in said["instructions"]


def test_a_version_we_do_not_know_is_answered_with_one_we_do(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library")
    said = rpc(port, token, "initialize", {"protocolVersion": "1999-01-01"})["result"]
    assert said["protocolVersion"] in oauth.PROTOCOL_VERSIONS


def test_a_notification_is_answered_with_nothing(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library")
    status, body, _ = send(
        port,
        "POST",
        "/mcp",
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        token=token,
    )
    assert status == 202 and body == b""


def test_an_unknown_method_is_a_jsonrpc_error_and_not_a_500(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library")
    said = rpc(port, token, "resources/list")
    assert said["error"]["code"] == mcp_http.METHOD_NOT_FOUND


def test_nonsense_is_a_parse_error(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library")
    status, body, _ = send(port, "POST", "/mcp", "{not json", token=token)
    assert status == 400
    assert json.loads(body)["error"]["code"] == mcp_http.PARSE_ERROR


def test_a_batch_is_answered_as_one(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library")
    status, body, _ = send(
        port,
        "POST",
        "/mcp",
        json.dumps(
            [
                {"jsonrpc": "2.0", "id": 1, "method": "ping"},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "ping"},
            ]
        ),
        token=token,
    )
    assert status == 200
    said = json.loads(body)
    assert [one["id"] for one in said] == [1, 2], "the notification drops out"


# --- tools, and what a scope decides ---------------------------------------------


def test_the_library_scope_lists_the_library_and_not_the_record(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library")
    names = {one["name"] for one in rpc(port, token, "tools/list")["result"]["tools"]}
    assert "search_library" in names and "describe_source" in names
    assert "my_vocabulary" not in names, "that is the record, and was not granted"
    assert "quote_build" not in names, "that is `check`, and was not granted"


def test_the_record_scope_adds_the_reader_s_own(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library record")
    names = {one["name"] for one in rpc(port, token, "tools/list")["result"]["tools"]}
    assert {"my_vocabulary", "my_progress", "search_my_shelf", "my_hours"} <= names
    assert "quote_build" not in names


def test_the_check_scope_adds_pricing(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library record check")
    names = {one["name"] for one in rpc(port, token, "tools/list")["result"]["tools"]}
    assert "quote_build" in names


def test_the_conversation_tool_is_never_listed(box: tuple[int, str]) -> None:
    """It needs a conversation on the page, and over a connector there is none."""
    port, _ = box
    token = a_token(port, "library record check")
    names = {one["name"] for one in rpc(port, token, "tools/list")["result"]["tools"]}
    assert "quote_conversation" not in names


def test_a_tool_outside_the_scope_cannot_be_called_anyway(box: tuple[int, str]) -> None:
    """A client that remembers a name from before a scope was revoked still gets nothing."""
    port, _ = box
    token = a_token(port, "library")
    said = rpc(port, token, "tools/call", {"name": "my_vocabulary", "arguments": {}})
    assert said["error"]["code"] == mcp_http.INVALID_PARAMS


def test_a_tool_answers_for_the_person_the_token_names(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library record")
    said = rpc(port, token, "tools/call", {"name": "my_progress", "arguments": {}})["result"]
    assert said["isError"] is False
    ladder = json.loads(said["content"][0]["text"])
    assert ladder["ladder"]["note"] == "A guide, not a placement."


def test_a_schema_comes_over_as_the_registry_wrote_it(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library")
    tools = rpc(port, token, "tools/list")["result"]["tools"]
    search = next(one for one in tools if one["name"] == "search_library")
    assert "inputSchema" in search, "MCP's spelling, not the Anthropic API's"
    assert "register" in search["inputSchema"]["properties"]
    assert search["inputSchema"]["additionalProperties"] is False


def test_a_tool_that_fails_is_a_result_and_not_a_request_error(box: tuple[int, str]) -> None:
    """The model is meant to read it and try something else."""
    port, _ = box
    token = a_token(port, "library")
    said = rpc(
        port, token, "tools/call", {"name": "open_library_text", "arguments": {"id": "nope"}}
    )
    assert "error" not in said
    assert said["result"]["isError"] is True
    assert "error" in json.loads(said["result"]["content"][0]["text"])


def test_the_library_really_answers(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library")
    said = rpc(
        port,
        token,
        "tools/call",
        {"name": "search_library", "arguments": {"register": "biblical", "limit": 3}},
    )["result"]
    found = json.loads(said["content"][0]["text"])
    assert found["count"] >= 1
    assert all(row["register"] == "biblical" for row in found["texts"])


# --- prompts ---------------------------------------------------------------------


def test_the_prompts_are_offered_by_name(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library record")
    names = {one["name"] for one in rpc(port, token, "prompts/list")["result"]["prompts"]}
    assert {"what-next", "drill", "read-with-me"} <= names


def test_a_prompt_comes_back_as_a_message(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library record")
    said = rpc(port, token, "prompts/get", {"name": "drill"})["result"]
    text = said["messages"][0]["content"]["text"]
    assert "my_vocabulary" in text
    assert "never keep score" in text, "the page it came from promises as much"


def test_a_prompt_nobody_wrote_is_refused(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library record")
    said = rpc(port, token, "prompts/get", {"name": "invented"})
    assert said["error"]["code"] == mcp_http.INVALID_PARAMS


def test_a_prompt_listing_does_not_leak_what_it_says(box: tuple[int, str]) -> None:
    """`prompts/list` is a menu; `prompts/get` is the thing itself."""
    assert all("says" not in one for one in mcp_http.prompt_shapes())


# --- the rails -------------------------------------------------------------------


def test_another_origin_cannot_reach_it(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library")
    status, _, _ = send(
        port,
        "POST",
        "/mcp",
        '{"jsonrpc":"2.0","id":1,"method":"ping"}',
        token=token,
        host="evil.test",
    )
    assert status == 404


def test_nothing_that_spends_is_listed_while_nothing_spends(box: tuple[int, str]) -> None:
    """Until `record_turn` lands, `check` grants pricing and nothing that costs money."""
    port, _ = box
    token = a_token(port, "library record check")
    tools = rpc(port, token, "tools/list")["result"]["tools"]
    from targum.chat import tools as registry

    by_name = {one.name: one for one in registry.REGISTRY}
    assert not [one for one in tools if by_name[one["name"]].spends]
