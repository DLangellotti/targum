"""Ways to sign in: Google linked, unlinked and linked again (targum-internal#502).

design.md §12, "Sign in with Google goes live, and signup opens to anyone" (2026-11-14).
The first Continue with Google links Google; Account's Unlink turns Google off for the
account, with Undo for a few seconds; after that only Account's Link turns it back on,
and only when Google proves the account's own address. Nothing here talks to Google:
`google.exchange` is replaced with an answer carrying the address under test.
"""

from __future__ import annotations

import base64
import json
import sqlite3
import threading
import time
from collections.abc import Callable
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from targum import accounts, google, serve
from targum.accounts import GoogleOff, Store, removable
from targum.render import builder

PUBLIC = "https://targum.page"


# -- the store -----------------------------------------------------------------------------


def test_the_first_google_sign_in_links_google(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    got = store.sign_in_verified("dina@example.com", via="google")
    assert got is not None
    held = store.ways_in(got[0].id)
    assert held == {"linked": True, "used": held["used"]} and held["used"]


def test_a_mailed_link_alone_links_nothing(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    got = store.finish_sign_in(store.start_sign_in("dina@example.com"))
    assert got is not None
    assert store.ways_in(got[0].id) == {"linked": False, "used": None}


def test_after_unlink_google_signs_nobody_in_and_the_link_still_does(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    got = store.sign_in_verified("dina@example.com", via="google")
    assert got is not None
    person = got[0]
    assert store.unlink_google(person.id)
    assert not store.ways_in(person.id)["linked"]
    with pytest.raises(GoogleOff):
        store.sign_in_verified("dina@example.com", via="google")
    # The email link is always a way in.
    assert store.finish_sign_in(store.start_sign_in("dina@example.com")) is not None


def test_undo_puts_back_exactly_what_was(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    got = store.sign_in_verified("dina@example.com", via="google")
    assert got is not None
    before = store.ways_in(got[0].id)
    store.unlink_google(got[0].id)
    assert store.relink_google(got[0].id)
    assert store.ways_in(got[0].id) == before


def test_undo_never_links_an_account_that_never_used_google(tmp_path: Path) -> None:
    store = Store(tmp_path / "targum.db")
    got = store.finish_sign_in(store.start_sign_in("dina@example.com"))
    assert got is not None
    assert not store.relink_google(got[0].id)
    assert not store.unlink_google(got[0].id), "nothing to unlink"
    assert not store.ways_in(got[0].id)["linked"]


def test_the_last_way_in_cannot_be_removed() -> None:
    """Today email is always on, so the rule refuses nobody; it holds for any way in
    added later (design.md §12, 2026-11-14)."""
    assert removable({"email", "google"}, "google")
    assert not removable({"email", "google"}, "email"), "email is always a way in"
    assert not removable({"google"}, "google"), "the last way in stays"
    assert not removable({"email", "passkey"}, "google"), "not a way it has"
    assert removable({"google", "passkey"}, "google")
    assert not removable({"passkey"}, "passkey")


def test_an_older_database_opens_with_google_never_linked(tmp_path: Path) -> None:
    path = tmp_path / "targum.db"
    store = Store(path)
    got = store.finish_sign_in(store.start_sign_in("dina@example.com"))
    assert got is not None
    store.close()
    old = sqlite3.connect(path)
    for column in ("google", "google_used"):
        old.execute(f"ALTER TABLE person DROP COLUMN {column}")
    old.execute("PRAGMA user_version = 67")
    old.commit()
    old.close()
    opened = Store(path)
    assert opened.db.execute("PRAGMA user_version").fetchone()[0] == accounts.SCHEMA_VERSION
    assert accounts.SCHEMA_VERSION >= 68
    assert opened.ways_in(got[0].id)["linked"] is False
    assert opened.sign_in_verified("dina@example.com", via="google") is not None
    assert opened.ways_in(got[0].id)["linked"] is True


# -- the server ----------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(google.CLIENT_ID_ENV, "targum.apps.googleusercontent.com")
    monkeypatch.setenv(google.CLIENT_SECRET_ENV, "a-secret")


def _box(tmp_path: Path, free_port: Callable[[], int]) -> tuple[int, Store]:
    class Mailer:
        def send(self, to: str, link: str, language: str = "en") -> None:
            pass

    store_path = tmp_path / "box.db"
    store = Store(store_path)
    port = free_port()
    threading.Thread(
        target=lambda: serve.start(
            out=tmp_path / "out",
            port=port,
            open_browser=False,
            store=store_path,
            mailer=Mailer(),
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
    return port, store


def _exchange(
    port: int,
    method: str,
    path: str,
    session: str = "",
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], str]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest(method, path, skip_host=True)
    conn.putheader("Host", "targum.page")
    if session:
        conn.putheader("Cookie", f"{serve.SESSION_COOKIE}={session}")
    for name, value in (headers or {}).items():
        conn.putheader(name, value)
    if method == "POST":
        conn.putheader("Content-Length", str(len(body)))
    conn.endheaders()
    if body:
        conn.send(body)
    response = conn.getresponse()
    said = response.read().decode("utf-8", errors="replace")
    answered = {name.lower(): value for name, value in response.getheaders()}
    conn.close()
    return response.status, answered, said


def _proving(monkeypatch: pytest.MonkeyPatch, address: str) -> None:
    """Google, as far as the server can tell, proving `address`."""
    payload = base64.urlsafe_b64encode(
        json.dumps({"email": address, "email_verified": True}).encode()
    ).decode()
    monkeypatch.setattr(google, "exchange", lambda *_: {"id_token": f"h.{payload.rstrip('=')}.s"})


def _through_google(
    port: int, monkeypatch: pytest.MonkeyPatch, address: str, start: str, session: str = ""
) -> tuple[int, dict[str, str], str]:
    status, headers, _ = _exchange(port, "GET", start, session)
    assert status in (302, 303), status
    assert headers["location"].startswith(google.AUTHORIZE)
    state = parse_qs(urlparse(headers["location"]).query)["state"][0]
    _proving(monkeypatch, address)
    return _exchange(port, "GET", f"/account/google/back?state={state}&code=x", session)


def _session(headers: dict[str, str]) -> str:
    cookie = headers.get("set-cookie", "")
    assert f"{serve.SESSION_COOKIE}=" in cookie, headers
    return cookie.split(f"{serve.SESSION_COOKIE}=", 1)[1].split(";", 1)[0]


def _me(port: int, session: str) -> dict[str, object]:
    status, _, said = _exchange(port, "GET", "/account/me", session)
    assert status == 200, said
    return json.loads(said)


def _google_way(me: dict[str, object]) -> dict[str, object]:
    ways = me["ways"]
    assert isinstance(ways, list)
    return next(way for way in ways if way["kind"] == "google")


JSON = {"Content-Type": "application/json", "Sec-Fetch-Site": "same-origin"}


def _press(
    port: int, route: str, session: str, headers: dict[str, str] | None = None
) -> tuple[int, dict[str, object]]:
    status, _, said = _exchange(port, "POST", route, session, b"{}", headers or JSON)
    return status, json.loads(said) if said.startswith("{") else {}


def _signed_in(port: int, store: Store, monkeypatch: pytest.MonkeyPatch, address: str) -> str:
    store.invite(address)
    status, headers, _ = _through_google(port, monkeypatch, address, "/account/google")
    assert status in (302, 303), status
    return _session(headers)


def test_a_first_continue_with_google_shows_linked_on_account(
    tmp_path: Path, free_port: Callable[[], int], client: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store = _box(tmp_path, free_port)
    session = _signed_in(port, store, monkeypatch, "dina@example.com")
    me = _me(port, session)
    assert me["ways"] == [
        {"kind": "email", "address": "dina@example.com"},
        {"kind": "google", "linked": True, "used": _google_way(me)["used"]},
    ]
    assert _google_way(me)["used"], "the day it was last used"


def test_unlink_then_undo(
    tmp_path: Path, free_port: Callable[[], int], client: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store = _box(tmp_path, free_port)
    session = _signed_in(port, store, monkeypatch, "dina@example.com")
    status, said = _press(port, "/account/google/unlink", session)
    assert status == 200 and _google_way(said)["linked"] is False
    assert _google_way(_me(port, session))["linked"] is False
    status, said = _press(port, "/account/google/link-again", session)
    assert status == 200 and _google_way(said)["linked"] is True
    # Undo is the one press after one Unlink, not a way to link Google without Google.
    status, said = _press(port, "/account/google/link-again", session)
    assert status == 409 and "too late to undo" in str(said["error"])


def test_undo_after_its_few_seconds_is_refused(
    tmp_path: Path, free_port: Callable[[], int], client: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store = _box(tmp_path, free_port)
    session = _signed_in(port, store, monkeypatch, "dina@example.com")
    assert _press(port, "/account/google/unlink", session)[0] == 200
    monkeypatch.setattr(serve, "UNDO_UNLINK_SECONDS", -1)
    status, said = _press(port, "/account/google/link-again", session)
    assert status == 409 and _google_way(said)["linked"] is False


def test_after_unlink_continue_with_google_is_refused(
    tmp_path: Path, free_port: Callable[[], int], client: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store = _box(tmp_path, free_port)
    session = _signed_in(port, store, monkeypatch, "dina@example.com")
    assert _press(port, "/account/google/unlink", session)[0] == 200
    status, headers, page = _through_google(
        port, monkeypatch, "dina@example.com", "/account/google"
    )
    assert status == 200
    assert "Google sign-in is off for this account." in page
    assert "link Google again from Your account." in page
    assert serve.SESSION_COOKIE not in headers.get("set-cookie", ""), "nobody signed in"
    assert 'action="/account/sign-in"' in page, "the email form beside it"


def test_link_from_account_with_its_own_address(
    tmp_path: Path, free_port: Callable[[], int], client: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store = _box(tmp_path, free_port)
    session = _signed_in(port, store, monkeypatch, "dina@example.com")
    assert _press(port, "/account/google/unlink", session)[0] == 200
    status, headers, _ = _through_google(
        port, monkeypatch, "dina@example.com", "/account/google?link=1", session
    )
    assert status in (302, 303) and headers["location"] == "/you#ways"
    assert _google_way(_me(port, session))["linked"] is True
    # And the door opens for Google again.
    status, headers, _ = _through_google(port, monkeypatch, "dina@example.com", "/account/google")
    assert status in (302, 303) and _session(headers)


def test_link_with_another_address_is_refused_and_signs_nobody_in(
    tmp_path: Path, free_port: Callable[[], int], client: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store = _box(tmp_path, free_port)
    session = _signed_in(port, store, monkeypatch, "dina@example.com")
    assert _press(port, "/account/google/unlink", session)[0] == 200
    store.invite("other@example.com")
    status, headers, _ = _through_google(
        port, monkeypatch, "other@example.com", "/account/google?link=1", session
    )
    assert status in (302, 303) and headers["location"] == "/you#ways"
    assert serve.SESSION_COOKIE not in headers.get("set-cookie", ""), "nobody signed in"
    assert (
        store.db.execute("SELECT 1 FROM person WHERE email = 'other@example.com'").fetchone()
        is None
    ), "no second account"
    me = _me(port, session)
    assert _google_way(me)["linked"] is False
    assert me["waysSaid"] == (
        "That Google account is for other@example.com. Choose the one for dina@example.com."
    )
    assert "waysSaid" not in _me(port, session), "said once"


def test_link_needs_somebody_signed_in(
    tmp_path: Path, free_port: Callable[[], int], client: None
) -> None:
    port, _ = _box(tmp_path, free_port)
    status, headers, _ = _exchange(port, "GET", "/account/google?link=1")
    assert status in (302, 303)
    assert headers["location"].startswith("/account/signin")


def test_unlink_is_refused_from_another_site_and_signed_out(
    tmp_path: Path, free_port: Callable[[], int], client: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store = _box(tmp_path, free_port)
    session = _signed_in(port, store, monkeypatch, "dina@example.com")
    elsewhere = {"Content-Type": "application/json", "Sec-Fetch-Site": "cross-site"}
    assert _press(port, "/account/google/unlink", session, elsewhere)[0] == 403
    as_a_form = {"Content-Type": "text/plain", "Sec-Fetch-Site": "same-origin"}
    assert _press(port, "/account/google/unlink", session, as_a_form)[0] == 403
    assert _press(port, "/account/google/unlink", "")[0] == 401
    assert _google_way(_me(port, session))["linked"] is True


def test_without_a_client_account_lists_only_the_email_link(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(google.CLIENT_ID_ENV, raising=False)
    monkeypatch.delenv(google.CLIENT_SECRET_ENV, raising=False)
    port, store = _box(tmp_path, free_port)
    got = store.sign_in_verified("dina@example.com")
    assert got is not None
    assert _me(port, got[1])["ways"] == [{"kind": "email", "address": "dina@example.com"}]
    assert _press(port, "/account/google/unlink", got[1])[0] == 404


# -- the pages -----------------------------------------------------------------------------


def test_account_draws_googles_row_only_with_a_client(
    monkeypatch: pytest.MonkeyPatch, client: None
) -> None:
    page = builder.you_page("")
    assert 'id="ways"' in page and "Ways to sign in" in page
    assert "Email link" in page and "Always on" in page
    assert 'id="way-google"' in page
    monkeypatch.delenv(google.CLIENT_ID_ENV)
    page = builder.you_page("")
    assert 'id="ways"' in page and "Email link" in page
    assert 'id="way-google"' not in page


def test_the_invitations_page_offers_google(
    tmp_path: Path, free_port: Callable[[], int], client: None
) -> None:
    port, _ = _box(tmp_path, free_port)
    status, _, page = _exchange(port, "GET", "/account/signin?invited=1")
    assert status == 200
    assert 'href="/account/google"' in page and "Continue with Google" in page


SWITCHES = ("TARGUM_FRONT_DOOR", "TARGUM_OPEN_SIGNUP", "TARGUM_PLANS")


def _front(monkeypatch: pytest.MonkeyPatch, **switches: str) -> str:
    for name in SWITCHES:
        monkeypatch.delenv(name, raising=False)
    for name, value in switches.items():
        monkeypatch.setenv(name, value)
    return builder.front_page("en", PUBLIC, "")


def test_the_front_door_draws_google_only_while_signup_is_open(
    monkeypatch: pytest.MonkeyPatch, client: None
) -> None:
    shut = _front(monkeypatch, TARGUM_FRONT_DOOR="1")
    assert "join-google" not in shut and "/account/google" not in shut
    opened = _front(monkeypatch, TARGUM_FRONT_DOOR="1", TARGUM_OPEN_SIGNUP="1", TARGUM_PLANS="1")
    press = 'class="btn join-google" href="/account/google"'
    assert opened.count(press) == 1, "under the ending's form"
    # Not under a tried link's form: the link rides /signup, and Google's state carries none.
    tried = builder.front_page(
        "en", PUBLIC, "", tried={"door": "page", "site": "x", "link": "https://x.org/a"}
    )
    assert tried.count(press) == 1, "the ending's, and not the tried link's"
    monkeypatch.delenv(google.CLIENT_SECRET_ENV)
    unconfigured = builder.front_page("en", PUBLIC, "")
    assert "join-google" not in unconfigured, "no client, no door"
