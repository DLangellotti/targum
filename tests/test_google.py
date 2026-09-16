"""Signing in with Google (targum-internal#304).

Most of what matters here is what the module refuses. Google will hand over an address
it has not verified; this install is invite-only, so accepting one would be a way past
the guest list, which is the whole gate on a box with a funded key.

Nothing here talks to Google. `exchange` is the one network call and is kept apart from
`address_from` so that reading an answer can be tested without one.
"""

from __future__ import annotations

import base64
import json
import urllib.parse

import pytest

from targum import google
from targum.accounts import Store


def token_for(**claims: object) -> dict[str, object]:
    """A token response shaped like Google's, carrying these claims."""
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return {"id_token": f"header.{payload}.signature", "access_token": "ya29."}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(google.CLIENT_ID_ENV, "targum.apps.googleusercontent.com")
    monkeypatch.setenv(google.CLIENT_SECRET_ENV, "a-secret")


def test_an_install_with_no_client_offers_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """A door that fails at its last step is worse than a door that is not there."""
    monkeypatch.delenv(google.CLIENT_ID_ENV, raising=False)
    monkeypatch.delenv(google.CLIENT_SECRET_ENV, raising=False)
    assert not google.configured()
    monkeypatch.setenv(google.CLIENT_ID_ENV, "an-id")
    assert not google.configured(), "an id without its secret cannot finish the exchange"


def test_where_it_sends_them(client: None) -> None:
    begun = google.begin("https://targum.page/account/google/back")
    assert begun.where.startswith(google.AUTHORIZE + "?")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(begun.where).query)
    assert query["scope"] == ["openid email"], "no profile: the address and nothing else"
    assert query["response_type"] == ["code"]
    assert query["redirect_uri"] == ["https://targum.page/account/google/back"]
    assert query["state"] == [begun.state]
    assert query["code_challenge_method"] == ["S256"]
    assert query["prompt"] == ["select_account"]
    # The secret is never in anything a browser sees.
    assert "a-secret" not in begun.where


def test_the_challenge_is_the_verifier_hashed(client: None) -> None:
    """PKCE: what goes to the browser must not be what finishes the exchange."""
    begun = google.begin("https://targum.page/account/google/back")
    query = urllib.parse.parse_qs(urllib.parse.urlparse(begun.where).query)
    assert query["code_challenge"] != [begun.verifier]
    assert query["code_challenge"] == [google._challenge(begun.verifier)]
    assert begun.verifier not in begun.where


def test_two_sign_ins_share_nothing(client: None) -> None:
    one = google.begin("https://targum.page/account/google/back")
    two = google.begin("https://targum.page/account/google/back")
    assert one.state != two.state and one.verifier != two.verifier


def test_a_sign_in_left_too_long_is_stale(client: None) -> None:
    begun = google.begin("https://targum.page/account/google/back")
    assert not google.stale(begun, at=begun.made + 60)
    assert google.stale(begun, at=begun.made + google.BEGUN_MINUTES * 60 + 1)


def test_a_verified_address_is_taken() -> None:
    answer = token_for(email="Dina@Example.com", email_verified=True)
    assert google.address_from(answer) == "dina@example.com"


def test_an_unverified_address_is_refused() -> None:
    """Google hands one over for an account it has not confirmed. Taking it would let
    somebody sign in as an address they do not hold, which is the whole gate."""
    with pytest.raises(google.Refused):
        google.address_from(token_for(email="dina@example.com", email_verified=False))
    with pytest.raises(google.Refused):
        google.address_from(token_for(email="dina@example.com"))


def test_an_answer_with_no_identity_is_refused() -> None:
    with pytest.raises(google.Refused):
        google.address_from({"access_token": "ya29."})
    with pytest.raises(google.Refused):
        google.address_from({"id_token": "not-a-jwt"})
    with pytest.raises(google.Refused):
        google.address_from({"id_token": "a.!!!not-base64!!!.c"})
    with pytest.raises(google.Refused):
        google.address_from(token_for(email_verified=True))


def test_google_reaches_the_same_account_as_a_mailed_link(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The point of the whole thing: it is a second proof, not a second account."""
    store = Store(tmp_path / "targum.db")
    token = store.start_sign_in("dina@example.com")
    first = store.finish_sign_in(token)
    assert first is not None
    then = store.sign_in_verified("Dina@Example.com ")
    assert then is not None
    assert then[0].id == first[0].id, "same person"
    assert then[1] != first[1], "a session of its own"


def test_somebody_on_their_way_out_cannot_come_back_through_google(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The one refusal the mailed link also makes."""
    store = Store(tmp_path / "targum.db")
    token = store.start_sign_in("dina@example.com")
    got = store.finish_sign_in(token)
    assert got is not None
    store.forget(got[0])
    assert store.sign_in_verified("dina@example.com") is None


def test_an_empty_address_signs_nobody_in(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = Store(tmp_path / "targum.db")
    assert store.sign_in_verified("") is None
    assert store.sign_in_verified("   ") is None
