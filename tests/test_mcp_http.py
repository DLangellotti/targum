"""The connector over HTTP, driven the way a host drives it.

The flow a client actually walks — 401, discover, connect, initialize, list, call — and
the two things that must stay true underneath it: a scope decides what is listed, and a
session cookie is not a way in.
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
    assert {"what-next", "talk", "drill", "read-with-me"} <= names


def test_a_prompt_comes_back_as_a_message(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library record")
    said = rpc(port, token, "prompts/get", {"name": "drill"})["result"]
    text = said["messages"][0]["content"]["text"]
    assert "my_vocabulary" in text
    assert "never keep score" in text, "the page it came from promises as much"


def test_the_talk_prompt_sends_the_host_to_the_contract(box: tuple[int, str]) -> None:
    port, _ = box
    token = a_token(port, "library record")
    said = rpc(port, token, "prompts/get", {"name": "talk"})["result"]
    assert "how_to_talk" in said["messages"][0]["content"]["text"]


def test_the_host_is_told_how_to_talk_at_initialize() -> None:
    """A reader who asked for Hebrew was answered in English about Hebrew (2026-09-23)."""
    assert "how_to_talk" in mcp_http.INSTRUCTIONS
    assert "translation" in mcp_http.INSTRUCTIONS


def test_how_to_talk_hands_over_the_contract_and_the_ledger(box: tuple[int, str]) -> None:
    """One contract, both surfaces: the host is given what targum's own chat is given."""
    from targum.chat import hebrew

    port, _ = box
    said = rpc(
        port,
        a_token(port, "library record"),
        "tools/call",
        {"name": "how_to_talk", "arguments": {"language": "he"}},
    )["result"]
    assert said["isError"] is False
    contract = json.loads(said["content"][0]["text"])["contract"]
    assert hebrew.contract_for("he") in contract
    assert "Their ledger" in contract
    assert "folded" in contract, "the host is told why the translation waits to be asked"
    assert "record_turn" in contract


def test_how_to_talk_refuses_a_language_that_does_not_talk(box: tuple[int, str]) -> None:
    port, _ = box
    said = rpc(
        port,
        a_token(port, "library record"),
        "tools/call",
        {"name": "how_to_talk", "arguments": {"language": "yi"}},
    )["result"]
    assert "coming" in json.loads(said["content"][0]["text"])["error"]


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


def test_the_only_tool_that_spends_needs_the_scope_that_consented(
    box: tuple[int, str],
) -> None:
    """design.md §12: one scope may say otherwise, and it is the only thing that may."""
    from targum.chat import tools as registry

    by_name = {one.name: one for one in registry.REGISTRY}
    port, _ = box

    without = rpc(port, a_token(port, "library record"), "tools/list")["result"]["tools"]
    assert not [one for one in without if by_name[one["name"]].spends]

    granted = rpc(port, a_token(port, "library record check"), "tools/list")["result"]["tools"]
    spending = [one["name"] for one in granted if by_name[one["name"]].spends]
    assert spending == ["record_turn"]
    assert "Uses the reader's hours" in next(
        one["description"] for one in granted if one["name"] == "record_turn"
    ), "the model is told what it costs the person whose hours they are"


def test_a_connector_without_the_scope_cannot_call_it_either(box: tuple[int, str]) -> None:
    port, _ = box
    said = rpc(
        port,
        a_token(port, "library record"),
        "tools/call",
        {"name": "record_turn", "arguments": {"wrote": "x", "language": "he"}},
    )
    assert said["error"]["code"] == mcp_http.INVALID_PARAMS


# --- the press, for a quote made somewhere targum has no page ---------------------


def test_a_quote_comes_back_with_a_link_and_never_a_way_to_spend(box: tuple[int, str]) -> None:
    """design.md §12: a quote is information, and the press stays on a targum page."""
    port, _ = box
    token = a_token(port, "library record check")
    said = rpc(
        port,
        token,
        "tools/call",
        {"name": "quote_build", "arguments": {"catalogue_id": "ruth"}},
    )["result"]
    quoted = json.loads(said["content"][0]["text"])
    if "error" in quoted or "in_library" in quoted:
        pytest.skip(f"nothing quotable on this shelf: {quoted}")
    # The link is there whether or not the text could be made ready — the suite is
    # offline by force, so here it cannot be. That is the seam: a quote always comes
    # back pointing at a page of ours, and never at a way to spend.
    assert quoted["quote"]["open"].startswith(f"{PUBLIC}/build/")
    assert "press" not in quoted["note"].lower(), "the model is never told to press"
    # And no tool it holds could have: `quote_build` prices, `_build` claims.
    assert quoted["quote"]["stage"] != "working"


def test_the_press_page_needs_the_job_to_be_yours(box: tuple[int, str]) -> None:
    port, session = box
    status, _, _ = send(port, "GET", "/build/not-a-job-of-yours", session=session)
    assert status == 404


def test_the_press_page_needs_an_account(box: tuple[int, str]) -> None:
    """Signed out it is the holding page or the door, and never somebody's build."""
    port, _ = box
    status, body, _ = send(port, "GET", "/build/anything")
    assert status != 200 or b"sign in" in body.lower()


def _prose(page: str) -> str:
    """What the card actually reads as: no markup, no inlined CSS, no script.

    Asserting over the whole page catches the stylesheet — `[lang$="-Latn"]` holds a
    dollar sign, and `data-usually="420"` holds the number the prose must not say.
    """
    import re

    body = re.sub(r"<(style|script)\b.*?</\1>", " ", page, flags=re.S | re.I)
    return " ".join(re.sub(r"<[^>]+>", " ", body).split())


def _quoted(**over: object) -> dict[str, object]:
    """One `Job.state()`, carrying only the fields this page draws."""
    job: dict[str, object] = {
        "id": "abc123",
        "made": 1758600000000,
        "title": "מלמדים את הבעל לשתוף",
        "english": "",
        "stage": "ready",
        "done": 0,
        "total": 0,
        "message": "",
        "error": "",
        "blocked": "",
        "reader": "",
        "usually": 0.0,
        "audio": False,
        "seconds": 0.0,
        "known_line": "",
    }
    job.update(over)
    return job


def test_the_press_card_counts_in_credits_and_agrees_with_itself() -> None:
    """design.md §12, 2026-09-23: a cost is credits, and a credit is a minute.

    This card said "Uses 1 minutes of your hours" for a one-minute video — a plural
    error and a category error in six words, and the reason the vocabulary changed. It
    went through `t` with a `{minutes}` blank, where nothing could check the agreement;
    it goes through `tn` now, where the catalogue picks the form.
    """
    from targum.render import builder

    one = _prose(builder.press_page(_quoted(audio=True, seconds=62.0)))
    assert "Uses 1 credit" in one and "1 credits" not in one
    many = _prose(builder.press_page(_quoted(audio=True, seconds=2805.0)))
    assert "Uses 47 credits" in many
    # And a cost is never said in hours, in money, or in a mix of the two.
    for gone in ("of your hours", "minutes of your", "$"):
        assert gone not in one, f"the card still says {gone!r}"


def test_the_press_card_says_the_wait_in_minutes_not_seconds() -> None:
    """`usually` is seconds (`Job.state`) and was drawn as minutes, so a seven-minute
    build promised "Ready in about 420 minutes"."""
    from targum.render import builder

    said = _prose(builder.press_page(_quoted(usually=420.0)))
    assert "Ready in about 7 minutes" in said and "420" not in said
    # Under half a minute there is nothing worth quoting, so it says nothing.
    assert "Ready in about" not in _prose(builder.press_page(_quoted(usually=12.0)))


def test_a_build_already_running_is_watched_and_offers_the_way_out() -> None:
    """Coming back to the link mid-build used to dead-end.

    The watcher hung off the press form, which this state has not got, so the page never
    polled and never opened the reader: it sat on "We're making it" until somebody
    reloaded it by hand. The watch is its own element now, and this state carries the way
    to the shelf, which is where design.md §12 ("A build is on the shelf while it is
    building") says the reader was going anyway.
    """
    from targum.render import builder

    page = builder.press_page(
        _quoted(stage="working", message="Fetching the video…", usually=420.0)
    )
    assert 'id="press-watch"' in page, "nothing for the watcher to hang off"
    assert 'data-job="abc123"' in page and 'data-made="1758600000000"' in page
    assert 'data-usually="420"' in page
    assert 'id="press-doing"' in page and 'id="press-left"' in page
    assert "/texts" in page, "no way off the page while it builds"


def test_the_press_page_says_its_script_s_words_in_russian() -> None:
    """`press.js` narrates the build, and said it in English on a Russian page until this
    page was handed a `TargumStrings` (targum-internal#184)."""
    from targum.render import builder

    page = builder.press_page(_quoted(audio=True, seconds=62.0, usually=420.0), "ru")
    assert "TARGUM_STRINGS" in page
    assert "press.page.opening" in page, "the script's own words were never sent"
    assert "Займёт 1 кредит" in page


# --- a reader's own prompts, beside ours (note 17) --------------------------------


def a_prompt(port: int, session: str, name: str, says: str) -> None:
    status, body, _ = send(
        port,
        "POST",
        "/account/prompts",
        json.dumps({"name": name, "says": says}),
        session=session,
    )
    assert status == 200, body


def test_what_a_reader_writes_is_in_their_host(box: tuple[int, str]) -> None:
    port, session = box
    a_prompt(port, session, "my-verbs", "Drill the verbs I keep getting wrong.")
    token = a_token(port, "library record")
    listed = rpc(port, token, "prompts/list")["result"]["prompts"]
    names = [one["name"] for one in listed]
    assert "my-verbs" in names
    assert names.index("my-verbs") > names.index("drill"), "ours first, theirs beneath"

    got = rpc(port, token, "prompts/get", {"name": "my-verbs"})["result"]
    assert got["messages"][0]["content"]["text"] == "Drill the verbs I keep getting wrong."


def test_a_reader_cannot_shadow_one_of_ours(box: tuple[int, str]) -> None:
    """Somebody who writes their own `drill` gets ours, not a different thing under a
    name they recognise."""
    port, session = box
    a_prompt(port, session, "drill", "Something else entirely.")
    token = a_token(port, "library record")
    listed = rpc(port, token, "prompts/list")["result"]["prompts"]
    assert [one["name"] for one in listed].count("drill") == 1
    got = rpc(port, token, "prompts/get", {"name": "drill"})["result"]
    assert "my_vocabulary" in got["messages"][0]["content"]["text"], "ours"


def test_a_prompt_is_gone_from_the_host_when_it_is_removed(box: tuple[int, str]) -> None:
    port, session = box
    a_prompt(port, session, "for-now", "Temporary.")
    token = a_token(port, "library record")
    listed = rpc(port, token, "prompts/list")["result"]["prompts"]
    assert "for-now" in [one["name"] for one in listed]
    send(
        port,
        "POST",
        "/account/prompts",
        json.dumps({"name": "for-now", "gone": True}),
        session=session,
    )
    assert "for-now" not in [
        one["name"] for one in rpc(port, token, "prompts/list")["result"]["prompts"]
    ]


def test_a_stranger_cannot_write_one(box: tuple[int, str]) -> None:
    port, _ = box
    status, _, _ = send(port, "POST", "/account/prompts", json.dumps({"name": "x", "says": "y"}))
    assert status == 401


def test_a_prompt_with_nothing_in_it_says_so(box: tuple[int, str]) -> None:
    port, session = box
    status, body, _ = send(
        port, "POST", "/account/prompts", json.dumps({"name": "", "says": ""}), session=session
    )
    assert status == 400
    assert "name" in json.loads(body)["error"].lower()
