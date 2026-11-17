"""The waitlist once the door is open (targum-internal#477, C).

With `signup_is_open()` a stranger opens an account without waiting, so the waitlist's
three doors change what they do. `POST /waitlist`, from a cached page or an old popup, is
the open door's own form and mails the sign-in link. An old mail's `/waitlist/confirm`
lands on the sign-in page, headed "targum is open now", with the address filled in, and
confirms nobody onto a list. `/waitlist/stop` keeps working, because a way out always
must. The back office keeps the list as it stands, and Let in stays for anyone still on
it: a saved link becomes a gift build only through that press, never through the open
door.

Shut, or asked for without plans, every one of them is as it was, byte for byte.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from test_signup_door import ASKED, OPEN, SHUT, WAITING, _ask, _box, _sign_up, _switched

from targum.accounts import Store
from targum.backoffice import survey
from targum.render.builder import back_office_page


def _state(store: Store, email: str) -> str | None:
    row = store.db.execute("SELECT state FROM waiting WHERE email = ?", (email,)).fetchone()
    return None if row is None else str(row["state"])


def _confirm(port: int, token: str, method: str = "GET") -> tuple[int, str]:
    if method == "GET":
        return _ask(port, "GET", f"/waitlist/confirm?t={token}")
    return _sign_up(port, "/waitlist/confirm", t=token)


# -- POST /waitlist -----------------------------------------------------------


def test_with_the_door_open_joining_mails_the_sign_in_link(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    links: list[tuple[str, str]] = []
    port, store = _box(tmp_path, free_port, links)
    _switched(monkeypatch, OPEN)
    status, page = _sign_up(port, "/waitlist", email="new@example.com")
    assert status == 200
    assert "<h1>Check your email</h1>" in page
    assert "Thanks. We've sent a link to new@example.com." in page
    assert WAITING.search(page) is None
    assert [to for to, _ in links] == ["new@example.com"]
    assert "/account/enter?t=" in links[-1][1]
    assert "/waitlist/confirm" not in links[-1][1]
    # Nobody waits: no row, so nothing for Let in to find later.
    assert _state(store, "new@example.com") is None


def test_with_the_door_open_a_tried_link_waits_in_upload_and_is_not_saved(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The open door builds nothing: a link posted with the address rides in the mailed
    link to Upload, for their own press, and is never kept on a waitlist row, where Let
    in would build it on targum's budget."""
    links: list[tuple[str, str]] = []
    port, store = _box(tmp_path, free_port, links)
    _switched(monkeypatch, OPEN)
    tried = "https://www.youtube.com/watch?v=abc"
    assert _sign_up(port, "/waitlist", email="new@example.com", link=tried)[0] == 200
    mailed = parse_qs(urlparse(links[-1][1]).query)
    assert mailed["next"] == ["/add?source=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3Dabc"]
    assert store.db.execute("SELECT COUNT(*) FROM waiting").fetchone()[0] == 0


def test_with_the_door_open_joining_keeps_the_open_door_s_gates(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    links: list[tuple[str, str]] = []
    port, _ = _box(tmp_path, free_port, links)
    _switched(monkeypatch, OPEN)
    status, page = _sign_up(port, "/waitlist", email="someone@mailinator.com")
    assert status == 403 and "throwaway" in page
    assert links == []


@pytest.mark.parametrize("switches", [SHUT, ASKED], ids=["shut", "asked-without-plans"])
def test_short_of_the_open_door_joining_is_as_it_was(
    tmp_path: Path,
    free_port: Callable[[], int],
    monkeypatch: pytest.MonkeyPatch,
    switches: dict[str, str],
) -> None:
    links: list[tuple[str, str]] = []
    port, store = _box(tmp_path, free_port, links)
    _switched(monkeypatch, SHUT)
    shut = _sign_up(port, "/waitlist", email="first@example.com")
    _switched(monkeypatch, switches)
    either = _sign_up(port, "/waitlist", email="second@example.com")
    # The page names no address, so two joins under the same door are the same bytes.
    assert either == shut
    assert shut[0] == 200 and "Open it to confirm your place on the list." in shut[1]
    assert _state(store, "second@example.com") == "pending"
    assert "/waitlist/confirm?t=" in links[-1][1]


# -- /waitlist/confirm --------------------------------------------------------


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_with_the_door_open_an_old_confirm_link_opens_the_sign_in(
    tmp_path: Path,
    free_port: Callable[[], int],
    monkeypatch: pytest.MonkeyPatch,
    method: str,
) -> None:
    links: list[tuple[str, str]] = []
    port, store = _box(tmp_path, free_port, links)
    token = store.join_waitlist("dina@example.com")
    assert token
    _switched(monkeypatch, OPEN)
    status, page = _confirm(port, token, method)
    assert status == 200
    assert "<h1>targum is open now</h1>" in page
    assert 'value="dina@example.com"' in page
    assert re.search(r'<form method="post" action="/account/sign-in"', page)
    assert "Send a link" in page
    assert "If you're new, the same link sets up your account." in page
    assert WAITING.search(page) is None
    # Nothing confirmed, nothing spent, nobody mailed.
    assert _state(store, "dina@example.com") == "pending"
    assert store.peek_waiting(token) == "dina@example.com"
    assert links == []


def test_with_the_door_open_the_confirm_page_is_in_the_language_they_joined_in(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    links: list[tuple[str, str]] = []
    port, store = _box(tmp_path, free_port, links)
    token = store.join_waitlist("masha@example.com", "ru")
    assert token
    _switched(monkeypatch, OPEN)
    status, page = _confirm(port, token)
    assert status == 200
    assert "<h1>targum уже открыт</h1>" in page
    assert '<html lang="ru"' in page


def test_with_the_door_open_a_spent_confirm_link_names_nobody(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    links: list[tuple[str, str]] = []
    port, store = _box(tmp_path, free_port, links)
    token = store.join_waitlist("dina@example.com")
    assert token and store.confirm_waiting(token)
    _switched(monkeypatch, OPEN)
    spent = _confirm(port, token)
    made_up = _confirm(port, "not-a-token")
    assert spent == made_up
    assert spent[0] == 200 and "<h1>targum is open now</h1>" in spent[1]
    assert "dina@example.com" not in spent[1]


def test_with_the_door_open_the_filled_in_address_is_escaped(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Read off the raw bytes: `_ask` unescapes the body, so through it an address drawn
    unescaped and one drawn escaped would look the same (qa-claude on targum#1270)."""
    links: list[tuple[str, str]] = []
    port, store = _box(tmp_path, free_port, links)
    token = store.join_waitlist('o"ne<b>il&co@example.com')
    assert token
    _switched(monkeypatch, OPEN)
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("GET", f"/waitlist/confirm?t={token}", skip_host=True)
    conn.putheader("Host", "targum.page")
    conn.endheaders()
    response = conn.getresponse()
    raw = response.read().decode("utf-8")
    conn.close()
    assert response.status == 200
    assert 'value="o&#34;ne&lt;b&gt;il&amp;co@example.com"' in raw
    assert "<b>il" not in raw


def test_with_the_door_open_a_stopped_token_and_a_made_up_one_are_one_page(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A row stopped while pending keeps its confirm token, so its language would say
    the token was real; only a token that finds a waiting address is answered in the
    row's language (qa-claude on targum#1270)."""
    links: list[tuple[str, str]] = []
    port, store = _box(tmp_path, free_port, links)
    token = store.join_waitlist("masha@example.com", "ru")
    assert token
    stop = str(store.db.execute("SELECT stop FROM waiting").fetchone()[0])
    store.leave_waitlist(stop)
    _switched(monkeypatch, OPEN)
    stopped = _confirm(port, token)
    assert stopped == _confirm(port, "not-a-token") == _confirm(port, stop)
    assert '<html lang="en"' in stopped[1] and "targum is open now" in stopped[1]
    # Nothing the visitor did not press is carried into the form.
    assert "data-asked=" not in stopped[1]


@pytest.mark.parametrize("switches", [SHUT, ASKED], ids=["shut", "asked-without-plans"])
def test_short_of_the_open_door_confirming_is_as_it_was(
    tmp_path: Path,
    free_port: Callable[[], int],
    monkeypatch: pytest.MonkeyPatch,
    switches: dict[str, str],
) -> None:
    links: list[tuple[str, str]] = []
    port, store = _box(tmp_path, free_port, links)
    token = store.join_waitlist("dina@example.com")
    assert token
    _switched(monkeypatch, SHUT)
    shut = _confirm(port, token)
    _switched(monkeypatch, switches)
    assert _confirm(port, token) == shut
    assert "<h1>Confirm your place</h1>" in shut[1]
    status, page = _confirm(port, token, "POST")
    assert status == 200 and "<h1>You’re on the list</h1>" in page
    assert _state(store, "dina@example.com") == "on"


def test_with_the_door_open_leaving_still_works(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    links: list[tuple[str, str]] = []
    port, store = _box(tmp_path, free_port, links)
    token = store.join_waitlist("dina@example.com")
    assert token and store.confirm_waiting(token)
    stop = str(store.db.execute("SELECT stop FROM waiting").fetchone()[0])
    _switched(monkeypatch, OPEN)
    status, page = _ask(port, "GET", f"/waitlist/stop?t={stop}")
    assert status == 200 and "Yes, take me off" in page
    status, page = _sign_up(port, "/waitlist/stop", t=stop)
    assert status == 200 and "<h1>You’re off the list</h1>" in page
    assert _state(store, "dina@example.com") == "off"


# -- the back office ----------------------------------------------------------


def _waiting_list(tmp_path: Path) -> Store:
    store = Store(tmp_path / "targum.db")
    first = store.join_waitlist("first@example.com")
    assert first and store.confirm_waiting(first)
    store.join_waitlist("second@example.com")
    return store


def test_with_the_door_open_the_back_office_keeps_the_list_and_let_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _waiting_list(tmp_path)
    _switched(monkeypatch, OPEN)
    page = back_office_page(survey(store.db), 30, section="waitlist")
    assert "Signup is open, so nobody new joins this list." in page
    # The history as it stands, and Let in for anyone still waiting.
    assert "first@example.com" in page and "second@example.com" in page
    assert 'action="/back-office/let-in"' in page
    assert 'action="/back-office/open-the-door"' in page


@pytest.mark.parametrize("switches", [SHUT, ASKED], ids=["shut", "asked-without-plans"])
def test_short_of_the_open_door_the_back_office_is_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, switches: dict[str, str]
) -> None:
    store = _waiting_list(tmp_path)
    found = survey(store.db)
    _switched(monkeypatch, SHUT)
    shut = back_office_page(found, 30, section="waitlist")
    _switched(monkeypatch, switches)
    assert back_office_page(found, 30, section="waitlist") == shut
    assert "Signup is open" not in shut
