"""targum as an authorization server: the flow, and the ways it is meant to refuse.

The connector is the first surface where a client targum does not control holds a
credential, so most of what is asserted here is a refusal — a replayed code, a rotated
refresh token used twice, a redirect that is nearly right.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from pathlib import Path

import pytest

from targum import oauth
from targum.accounts import Person, Store


def a_store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


def a_person(store: Store, email: str = "reader@example.com") -> Person:
    person, _ = store.finish_sign_in(store.start_sign_in(email))  # type: ignore[misc]
    return person


def a_verifier() -> tuple[str, str]:
    """A PKCE pair, made the way a client makes one."""
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    return verifier, challenge


def _query(**over: str) -> dict[str, list[str]]:
    said = {
        "response_type": "code",
        "client_id": secrets.token_urlsafe(32),
        "code_challenge_method": "S256",
        "code_challenge": a_verifier()[1],
        "redirect_uri": "https://claude.ai/api/mcp/auth_callback",
        "scope": "library record",
        "state": "abc",
    }
    said.update(over)
    return {key: [value] for key, value in said.items()}


# --- scopes ----------------------------------------------------------------------


def test_an_unknown_scope_is_dropped_and_not_refused() -> None:
    assert oauth.known_scopes("library profile record") == ("library", "record")


def test_asking_for_nothing_gets_the_smallest_scope() -> None:
    assert oauth.known_scopes("") == ("library",)
    assert oauth.known_scopes(None) == ("library",)
    assert oauth.known_scopes("profile email") == ("library",), "none of ours is none"


def test_scopes_come_back_in_the_order_the_page_lists_them() -> None:
    assert oauth.known_scopes("chat library") == ("library", "chat")


def test_only_one_scope_spends() -> None:
    spending = [name for name, _ in oauth.SCOPES if name == oauth.SPENDING_SCOPE]
    assert spending == ["chat"], "design.md §12: one tool spends, and this is its scope"
    assert not oauth.read_request(_query(scope="library record")).spends
    assert oauth.read_request(_query(scope="library chat")).spends


def test_granted_reads_a_scope_string_and_not_a_substring() -> None:
    assert oauth.granted("library chat", "chat")
    assert not oauth.granted("library", "chat")
    assert not oauth.granted("libraryx", "library"), "a prefix is not a scope"
    assert not oauth.granted(None, "library")


def test_a_grant_made_under_the_old_scope_name_still_carries_it() -> None:
    """design.md §12, 2026-09-23: `check` became `chat`.

    A grant stores the words the reader approved, and those outlive a rename. Every
    connector authorised before today holds `check`, and `granted()` compares strings —
    so without the map the rename would silently strip the spending scope from a live
    connector, and its owner would see one fewer scope on their account page than they
    agreed to.
    """
    assert oauth.granted("library record check", "chat"), "a live grant lost its scope"
    assert oauth.current("library record check") == ("library", "record", "chat")
    # And a client that still asks by the old name is answered, not quietly downgraded:
    # the name is written into its own stored configuration and it will keep sending it.
    assert oauth.known_scopes("library check") == ("library", "chat")
    assert oauth.read_request(_query(scope="library check")).spends
    # The old name is gone from everything the reader is shown or the server offers.
    assert "check" not in dict(oauth.SCOPES)
    assert oauth.current("check check") == ("chat",), "said twice is held once"
    assert oauth.current("profile") == (), "a name this server never had grants nothing"


# --- PKCE ------------------------------------------------------------------------


def test_a_verifier_matches_its_own_challenge() -> None:
    verifier, challenge = a_verifier()
    assert oauth.verify_challenge(verifier, challenge)


def test_a_wrong_verifier_does_not() -> None:
    _, challenge = a_verifier()
    other, _ = a_verifier()
    assert not oauth.verify_challenge(other, challenge)
    assert not oauth.verify_challenge("", challenge)
    assert not oauth.verify_challenge("short", challenge)


def test_plain_is_not_offered_at_all() -> None:
    assert oauth.CHALLENGE_METHODS == ("S256",)
    with pytest.raises(oauth.OAuthError) as raised:
        oauth.read_request(_query(code_challenge_method="plain"))
    assert raised.value.code == "invalid_request"


# --- the authorize request -------------------------------------------------------


def test_a_well_formed_request_reads() -> None:
    asked = oauth.read_request(_query())
    assert asked.scopes == ("library", "record")
    assert asked.state == "abc"
    assert asked.scope_string == "library record"


def test_only_the_code_response_type() -> None:
    with pytest.raises(oauth.OAuthError) as raised:
        oauth.read_request(_query(response_type="token"))
    assert raised.value.code == "unsupported_response_type"


def test_a_request_without_pkce_is_refused() -> None:
    query = _query()
    del query["code_challenge"]
    with pytest.raises(oauth.OAuthError):
        oauth.read_request(query)


def test_a_client_id_that_is_not_one_is_refused() -> None:
    with pytest.raises(oauth.OAuthError) as raised:
        oauth.read_request(_query(client_id="../../etc/passwd"))
    assert raised.value.code == "invalid_client"


# --- redirects -------------------------------------------------------------------


def test_a_redirect_matches_exactly_or_not_at_all() -> None:
    registered = ["https://claude.ai/api/mcp/auth_callback"]
    assert oauth.check_redirect(registered[0], registered) == registered[0]
    for nearly in (
        "https://claude.ai/api/mcp/auth_callback/x",
        "https://claude.ai/api/mcp/auth_callbackX",
        "https://claude.ai.evil.test/api/mcp/auth_callback",
        "https://claude.ai/api/mcp/auth_callback?x=1",
    ):
        with pytest.raises(oauth.OAuthError):
            oauth.check_redirect(nearly, registered)


def test_one_registered_redirect_may_be_left_out_and_two_may_not() -> None:
    one = ["https://a.test/cb"]
    assert oauth.check_redirect("", one) == one[0]
    with pytest.raises(oauth.OAuthError):
        oauth.check_redirect("", [*one, "https://b.test/cb"])
    with pytest.raises(oauth.OAuthError):
        oauth.check_redirect("", [])


def test_registration_takes_https_and_loopback_and_nothing_else() -> None:
    name, kept = oauth.check_registration(
        {"client_name": "Claude", "redirect_uris": ["https://a.test/cb", "http://127.0.0.1:9/cb"]}
    )
    assert name == "Claude" and len(kept) == 2
    for bad in ("http://evil.test/cb", "javascript:alert(1)", "https://a.test/cb#frag"):
        with pytest.raises(oauth.OAuthError):
            oauth.check_registration({"redirect_uris": [bad]})
    with pytest.raises(oauth.OAuthError):
        oauth.check_registration({"redirect_uris": []})


def test_a_registration_name_is_a_claim_and_is_capped() -> None:
    name, _ = oauth.check_registration(
        {"client_name": "x" * 5000, "redirect_uris": ["https://a.test/cb"]}
    )
    assert len(name) == oauth.MOST_NAME


def test_the_answer_goes_back_on_the_query_and_never_the_fragment() -> None:
    back = oauth.back_to("https://a.test/cb", code="abc", state="s", error="")
    assert back == "https://a.test/cb?code=abc&state=s", "empties dropped"
    assert "#" not in back
    assert oauth.back_to("https://a.test/cb?x=1", code="abc").startswith(
        "https://a.test/cb?x=1&code=abc"
    )


# --- the store's half ------------------------------------------------------------


def test_a_code_is_spent_once(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    client = store.register_client("Claude", ["https://a.test/cb"])
    _, challenge = a_verifier()
    code = store.start_grant(
        person.id,
        client,
        scopes="library record",
        redirect="https://a.test/cb",
        challenge=challenge,
    )
    first = store.spend_grant(code)
    assert first is not None and first["person"] == person.id
    assert first["scopes"] == "library record"
    assert store.spend_grant(code) is None, "a replayed code is refused"


def test_a_stale_code_is_refused(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    client = store.register_client("Claude", ["https://a.test/cb"])
    code = store.start_grant(
        person.id, client, scopes="library", redirect="https://a.test/cb", challenge="c"
    )
    assert store.spend_grant(code, minutes=0) is None


def test_a_token_names_a_person_and_carries_its_scopes(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    client = store.register_client("Claude", ["https://a.test/cb"])
    token = store.mint_token(person.id, client, scopes="library record")
    got = store.bearer(token)
    assert got is not None
    who, scopes = got
    assert who.id == person.id and who.email == person.email
    assert oauth.granted(scopes, "record") and not oauth.granted(scopes, "chat")


def test_a_token_is_stored_as_a_digest_and_never_in_the_clear(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    client = store.register_client("Claude", ["https://a.test/cb"])
    token = store.mint_token(person.id, client, scopes="library")
    rows = store.db.execute("SELECT hash FROM oauth_token").fetchall()
    assert rows and all(row["hash"] != token for row in rows)
    assert all(row["hash"] == hashlib.sha256(token.encode()).hexdigest() for row in rows)


def test_an_expired_token_stops_working(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    client = store.register_client("Claude", ["https://a.test/cb"])
    token = store.mint_token(person.id, client, scopes="library", minutes=-1)
    assert store.bearer(token) is None


def test_nothing_and_nonsense_are_nobody(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    assert store.bearer(None) is None
    assert store.bearer("") is None
    assert store.bearer("not-a-token") is None


def test_a_refresh_token_rotates_and_the_old_one_dies(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    client = store.register_client("Claude", ["https://a.test/cb"])
    refresh = store.mint_token(person.id, client, kind="refresh", scopes="library record")
    spent = store.rotate_refresh(refresh)
    assert spent is not None and spent["scopes"] == "library record"
    assert store.rotate_refresh(refresh) is None, "presented twice means it leaked"


def test_a_refresh_token_is_not_an_access_token(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    client = store.register_client("Claude", ["https://a.test/cb"])
    refresh = store.mint_token(person.id, client, kind="refresh", scopes="library")
    assert store.bearer(refresh) is None, "the wrong kind at the wrong door"


def test_revoking_stops_a_token(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    client = store.register_client("Claude", ["https://a.test/cb"])
    token = store.mint_token(person.id, client, scopes="library")
    assert store.revoke_token(token) is True
    assert store.bearer(token) is None
    assert store.revoke_token(token) is False, "already gone"


def test_disconnecting_takes_both_kinds(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    client = store.register_client("Claude", ["https://a.test/cb"])
    access = store.mint_token(person.id, client, scopes="library")
    refresh = store.mint_token(person.id, client, kind="refresh", scopes="library")
    assert store.disconnect(person.id, client) == 2
    assert store.bearer(access) is None
    assert store.rotate_refresh(refresh) is None, "or it reconnects itself within the hour"


def test_disconnecting_one_client_leaves_another(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    claude = store.register_client("Claude", ["https://a.test/cb"])
    other = store.register_client("ChatGPT", ["https://b.test/cb"])
    kept = store.mint_token(person.id, other, scopes="library")
    store.mint_token(person.id, claude, scopes="library")
    store.disconnect(person.id, claude)
    assert store.bearer(kept) is not None


def test_one_connection_a_client_however_many_tokens(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    client = store.register_client("Claude", ["https://a.test/cb"])
    store.mint_token(person.id, client, scopes="library record")
    store.mint_token(person.id, client, kind="refresh", scopes="library record")
    connections = store.connections(person.id)
    assert len(connections) == 1
    assert connections[0]["name"] == "Claude"
    assert connections[0]["scopes"] == "library record"
    assert store.connections(None) == []


def test_a_connection_is_in_the_export_and_the_token_is_not(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    client = store.register_client("Claude", ["https://a.test/cb"])
    token = store.mint_token(person.id, client, scopes="library record")
    out = store.everything(person)
    assert out["connections"][0]["name"] == "Claude"
    assert token not in json.dumps(out), "a credential is not data"


def test_leaving_takes_every_connector_with_it(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    client = store.register_client("Claude", ["https://a.test/cb"])
    access = store.mint_token(person.id, client, scopes="library record")
    refresh = store.mint_token(person.id, client, kind="refresh", scopes="library")
    store.forget(person)
    assert store.bearer(access) is None
    assert store.rotate_refresh(refresh) is None
    assert store.connections(person.id) == []


def test_an_account_on_its_way_out_is_nobody(tmp_path: Path) -> None:
    """`forget` deletes the rows; this is the belt to that braces, for a row that survives."""
    store = a_store(tmp_path)
    person = a_person(store)
    client = store.register_client("Claude", ["https://a.test/cb"])
    token = store.mint_token(person.id, client, scopes="library")
    with store.write() as db:
        db.execute("UPDATE person SET leaving = 1 WHERE id = ?", (person.id,))
    assert store.bearer(token) is None


def test_the_sweep_drops_what_nothing_can_use(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    client = store.register_client("Claude", ["https://a.test/cb"])
    live = store.mint_token(person.id, client, scopes="library")
    store.mint_token(person.id, client, scopes="library", minutes=-100 * 24 * 60)
    assert store.sweep_tokens(days=1) >= 1
    assert store.bearer(live) is not None, "the live one stays"


# --- the documents a client reads ------------------------------------------------


def test_the_metadata_points_at_this_box() -> None:
    meta = oauth.protected_resource("https://targum.page")
    assert meta["resource"] == "https://targum.page/mcp"
    assert meta["authorization_servers"] == ["https://targum.page"]
    assert set(meta["scopes_supported"]) == {name for name, _ in oauth.SCOPES}

    server = oauth.authorization_server("https://targum.page")
    assert server["issuer"] == "https://targum.page"
    assert server["code_challenge_methods_supported"] == ["S256"]
    assert "refresh_token" in server["grant_types_supported"], "or every hour re-asks"
    assert server["response_types_supported"] == ["code"]


def test_the_challenge_header_says_where_the_metadata_is() -> None:
    said = oauth.challenge_header("https://targum.page")
    assert "Bearer" in said
    assert "https://targum.page/.well-known/oauth-protected-resource" in said


def test_a_bearer_header_is_read_however_it_is_cased() -> None:
    assert oauth.bearer_from("Bearer abc") == "abc"
    assert oauth.bearer_from("bearer abc") == "abc"
    assert oauth.bearer_from("BEARER  abc ") == "abc"
    assert oauth.bearer_from("Basic abc") == ""
    assert oauth.bearer_from(None) == ""
    assert oauth.bearer_from("abc") == ""


def test_a_version_we_do_not_know_is_answered_with_the_newest() -> None:
    assert oauth.protocol_version("2025-06-18") == "2025-06-18"
    assert oauth.protocol_version("2099-01-01") == oauth.LATEST_PROTOCOL
    assert oauth.protocol_version(None) == oauth.LATEST_PROTOCOL


def test_a_registration_reply_offers_no_secret() -> None:
    said = json.loads(oauth.registration_reply("id", "Claude", ["https://a.test/cb"], 1000))
    assert "client_secret" not in said, "every client here is public; PKCE stands in"
    assert said["token_endpoint_auth_method"] == "none"
    assert said["client_id_issued_at"] == 1


# --- what a reader wrote for their own connector (note 17) -----------------------


def test_a_prompt_is_saved_under_a_name_a_host_can_draw(tmp_path: Path) -> None:
    """A host draws these as things to pick by name, and several as slash commands."""
    store = a_store(tmp_path)
    person = a_person(store)
    written = store.write_prompt(person.id, "Drill My Verbs", "Work on my verbs.")
    assert written is not None and written["name"] == "drill-my-verbs"
    assert store.prompts(person.id)[0]["says"] == "Work on my verbs."


def test_saving_the_same_name_replaces_it(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    store.write_prompt(person.id, "mine", "first")
    store.write_prompt(person.id, "mine", "second")
    kept = store.prompts(person.id)
    assert len(kept) == 1 and kept[0]["says"] == "second"


def test_a_prompt_with_no_name_or_nothing_to_say_is_refused(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    assert store.write_prompt(person.id, "", "something") is None
    assert store.write_prompt(person.id, "named", "   ") is None
    assert store.write_prompt(person.id, "!!!", "something") is None, "no name survives that"


def test_there_is_a_ceiling_on_how_many(tmp_path: Path) -> None:
    from targum.accounts import MOST_PROMPTS

    store = a_store(tmp_path)
    person = a_person(store)
    for n in range(MOST_PROMPTS):
        assert store.write_prompt(person.id, f"p{n}", "x") is not None
    assert store.write_prompt(person.id, "one-too-many", "x") is None
    assert store.write_prompt(person.id, "p0", "replacing is not adding") is not None


def test_removing_one_is_a_tombstone(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    store.write_prompt(person.id, "mine", "x")
    assert store.drop_prompt(person.id, "mine") is True
    assert store.prompts(person.id) == []
    assert store.drop_prompt(person.id, "mine") is False, "already gone"
    assert store.write_prompt(person.id, "mine", "back") is not None, "and can come back"


def test_prompts_are_exported_and_go_with_the_account(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    store.write_prompt(person.id, "mine", "my own words")
    assert store.everything(person)["prompts"][0]["says"] == "my own words"
    store.forget(person)
    assert store.prompts(person.id) == []


def test_one_reader_s_prompts_are_their_own(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    mine = a_person(store, "mine@example.com")
    theirs = a_person(store, "theirs@example.com")
    store.write_prompt(mine.id, "mine", "x")
    assert store.prompts(theirs.id) == []
    assert store.drop_prompt(theirs.id, "mine") is False, "not theirs to remove"
    assert len(store.prompts(mine.id)) == 1


# --- what a leaked refresh token costs -------------------------------------------


def test_reusing_a_rotated_refresh_token_takes_the_whole_family(tmp_path: Path) -> None:
    """By the time one is presented twice, one of the two holding it is not the reader,
    and nothing here can say which. So both of them lose it."""
    store = a_store(tmp_path)
    person = a_person(store)
    client = store.register_client("Claude", ["https://a.test/cb"])
    first = store.mint_token(person.id, client, kind="refresh", scopes="library record")
    spent = store.rotate_refresh(first)
    assert spent is not None
    # What the rotation minted — the thief's, or the reader's; there is no telling.
    access = store.mint_token(person.id, client, scopes="library record")
    second = store.mint_token(person.id, client, kind="refresh", scopes="library record")
    assert store.bearer(access) is not None

    assert store.rotate_refresh(first) is None, "the reuse is refused"
    assert store.bearer(access) is None, "and what came of it stops working"
    assert store.rotate_refresh(second) is None
    assert store.connections(person.id) == []


def test_a_reuse_does_not_reach_another_client(tmp_path: Path) -> None:
    store = a_store(tmp_path)
    person = a_person(store)
    claude = store.register_client("Claude", ["https://a.test/cb"])
    other = store.register_client("ChatGPT", ["https://b.test/cb"])
    kept = store.mint_token(person.id, other, scopes="library")
    leaked = store.mint_token(person.id, claude, kind="refresh", scopes="library")
    store.rotate_refresh(leaked)
    store.rotate_refresh(leaked)
    assert store.bearer(kept) is not None, "one connector's trouble is not another's"


def test_registering_has_a_ceiling(tmp_path: Path) -> None:
    """Open by definition, so the limit is on the act: there is no asker to key it on."""
    store = a_store(tmp_path)
    assert store.registering_too_often(limit=2) is False
    assert store.registering_too_often(limit=2) is False
    assert store.registering_too_often(limit=2) is True


def test_the_sweep_is_called_at_start_up(tmp_path: Path) -> None:
    """A sweep nothing calls is a sweep that never happens, which is what `Store.purge`
    was until somebody noticed."""
    from targum.serve import Library

    store = a_store(tmp_path)
    person = a_person(store)
    client = store.register_client("Claude", ["https://a.test/cb"])
    store.mint_token(person.id, client, scopes="library", minutes=-100 * 24 * 60)
    live = store.mint_token(person.id, client, scopes="library")
    Library(tmp_path / "out", store=store)
    assert store.bearer(live) is not None
    rows = store.db.execute("SELECT COUNT(*) AS n FROM oauth_token").fetchone()
    assert int(rows["n"]) == 1, "the dead one was swept on the way up"


def test_every_scope_is_said_in_the_reader_s_own_language() -> None:
    """The approval page is where a reader agrees, so it must be readable to them.

    `SCOPES` is written in this module as English and the page drew it raw, so a Russian
    reader met the whole page in Russian except the three lines saying what they were
    agreeing to (2026-09-23). The page goes through the catalogue now, and this holds the
    English in both places to the same words — a scope whose two copies drift is a page
    that promises one thing and stores another.
    """
    from targum import strings

    english, russian = strings.catalogue("en"), strings.catalogue("ru")
    for name, says in oauth.SCOPES:
        key = f"connect.scope.{name}"
        assert english.get(key) == says, f"{key} and oauth.SCOPES disagree"
        assert russian.get(key), f"{key} is not said in Russian"
        assert russian[key] != says, f"{key} is still English on the Russian page"
