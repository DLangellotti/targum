"""The arrival's doors on a hosted box: the invitation, the sign-in page, the mailed link,
Google, and the room each one brings the reader back to (targum-internal#462).

Each test pins a state the arrival QA of 2026-10-18 found short of design.md §14 and
fixed: Google's door answering 404 on a hosted box, a refusal or a second press dropping
the room the reader had asked for, and a Russian invitation opening English pages from
the sign-in onwards.
"""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import pytest

from targum import google, letters, serve
from targum.accounts import Store

PUBLIC = "https://targum.page"


def _box(
    tmp_path: Path, free_port: Callable[[], int], links: list[tuple[str, str]]
) -> tuple[int, Store]:
    """A hosted server whose mailer writes down each link and the language it was in."""

    class Mailer:
        def send(self, to: str, link: str, language: str = "en") -> None:
            links.append((link, language))

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
    port: int, method: str, path: str, body: bytes = b"", kind: str = "", cookie: str = ""
) -> tuple[int, dict[str, str], str]:
    """One request with no redirect followed, as the door answers it."""
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest(method, path, skip_host=True)
    conn.putheader("Host", "targum.page")
    if cookie:
        conn.putheader("Cookie", cookie)
    if body:
        conn.putheader("Content-Type", kind)
        conn.putheader("Content-Length", str(len(body)))
    conn.endheaders()
    if body:
        conn.send(body)
    response = conn.getresponse()
    said = response.read().decode("utf-8", errors="replace")
    headers = {name.lower(): value for name, value in response.getheaders()}
    # Every cookie set, not only the last one named.
    cookies = response.headers.get_all("Set-Cookie") or []
    if cookies:
        headers["set-cookie"] = "\n".join(cookies)
    conn.close()
    return response.status, headers, said


def _ask_for_a_link(port: int, payload: dict[str, object]) -> int:
    body = json.dumps(payload).encode()
    status, _, _ = _exchange(port, "POST", "/account/sign-in", body, "application/json")
    return status


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(google.CLIENT_ID_ENV, "targum.apps.googleusercontent.com")
    monkeypatch.setenv(google.CLIENT_SECRET_ENV, "a-secret")


def test_the_address_the_form_posts_to_is_the_door_when_typed(
    tmp_path: Path, free_port: Callable[[], int]
) -> None:
    """`/account/sign-in` reads like the door, and opened in the bar it met the stale-key
    page: English only, a brown button and "the Terminal window", on a hosted box with no
    Terminal (errors QA, targum-internal#468). It goes to the door, room and all."""
    port, _ = _box(tmp_path, free_port, [])
    status, headers, page = _exchange(port, "GET", "/account/sign-in?next=%2Fprogress")
    assert status == 303, status
    assert headers["location"] == "/account/signin?next=%2Fprogress"
    assert "Terminal" not in page


# -- Google ------------------------------------------------------------------------------


def test_googles_door_opens_for_somebody_signed_out_on_a_hosted_box(
    tmp_path: Path, free_port: Callable[[], int], client: None
) -> None:
    """Both halves were missing from `OPEN_TO_STRANGERS`, so the box turned "Continue
    with Google" away at the account check — 404, the moment a client was configured."""
    port, _ = _box(tmp_path, free_port, [])
    status, headers, _ = _exchange(port, "GET", "/account/google?next=%2Fprogress")
    assert status in (302, 303), status
    assert headers["location"].startswith(google.AUTHORIZE)
    status, _, page = _exchange(port, "GET", "/account/google/back?state=nobody&code=x")
    assert status == 200 and "That sign-in took too long." in page


def test_without_a_client_googles_door_is_still_not_there(
    tmp_path: Path, free_port: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(google.CLIENT_ID_ENV, raising=False)
    monkeypatch.delenv(google.CLIENT_SECRET_ENV, raising=False)
    port, _ = _box(tmp_path, free_port, [])
    assert _exchange(port, "GET", "/account/google")[0] == 404
    assert _exchange(port, "GET", "/account/google/back?state=x")[0] == 404


def test_a_cancelled_google_sign_in_keeps_the_room(
    tmp_path: Path, free_port: Callable[[], int], client: None
) -> None:
    """Cancel on Google's own screen, and both ways on from the door still go back to the
    page the reader was turned away from: the form, and Google's button."""
    port, _ = _box(tmp_path, free_port, [])
    _, headers, _ = _exchange(port, "GET", "/account/google?next=%2Fprogress")
    state = parse_qs(urlparse(headers["location"]).query)["state"][0]
    status, _, page = _exchange(
        port,
        "GET",
        f"/account/google/back?state={state}&error=access_denied",
        cookie=_bound(headers),
    )
    assert status == 200 and "No harm done." in page
    assert 'data-next="/progress"' in page, "the form carries the room"
    assert 'href="/account/google?next=/progress"' in page, "and so does Google's button"


def test_a_google_sign_in_that_did_not_finish_tries_again_into_the_room(
    tmp_path: Path, free_port: Callable[[], int], client: None
) -> None:
    port, _ = _box(tmp_path, free_port, [])
    _, headers, _ = _exchange(port, "GET", "/account/google?next=%2Fprogress")
    state = parse_qs(urlparse(headers["location"]).query)["state"][0]
    status, _, page = _exchange(
        port, "GET", f"/account/google/back?state={state}", cookie=_bound(headers)
    )
    assert status == 200 and "That sign-in didn" in page
    assert 'href="/account/google?next=/progress">Sign in again' in page


def _bound(headers: dict[str, str]) -> str:
    """The cookie `/account/google` binds its sign-in to the browser with, as sent back."""
    return headers["set-cookie"].split(";")[0]


def _proved(monkeypatch: pytest.MonkeyPatch, address: str) -> None:
    """Google, answering any code with `address` proved."""
    import base64

    payload = base64.urlsafe_b64encode(
        json.dumps({"email": address, "email_verified": True}).encode()
    ).decode()
    monkeypatch.setattr(google, "exchange", lambda *_: {"id_token": f"h.{payload.rstrip('=')}.s"})


def test_a_google_callback_from_another_browser_signs_nobody_in(
    tmp_path: Path, free_port: Callable[[], int], client: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """targum-internal#729, login CSRF: somebody starts a Google sign-in as themselves,
    stops at the callback address and sends it on. Opened in a browser that did not start
    it, it signs nobody in, and the state is spent, so it works in no browser after."""
    port, store = _box(tmp_path, free_port, [])
    store.invite("mallory@example.com")
    _proved(monkeypatch, "mallory@example.com")
    _, started, _ = _exchange(port, "GET", "/account/google")
    state = parse_qs(urlparse(started["location"]).query)["state"][0]
    bound = _bound(started)
    told = started["set-cookie"]
    assert bound.startswith(f"{serve.GOOGLE_STATE_COOKIE}=") and state not in told
    for part in ("HttpOnly", "SameSite=Lax", "Secure", "Path=/account/google", "Max-Age=600"):
        assert part in told, told
    callback = f"/account/google/back?state={state}&code=x"

    # A fresh browser, with no cookie of ours, and one holding another sign-in's.
    spent: list[str] = []
    monkeypatch.setattr(google, "exchange", lambda *_: spent.append("code") or {})
    status, headers, page = _exchange(port, "GET", callback)
    assert status == 200 and "That sign-in didn" in page
    assert serve.SESSION_COOKIE not in headers.get("set-cookie", ""), "nobody signed in"
    assert not spent, "the code is never spent"
    # And it is spent: the browser that started it cannot finish it now either.
    _proved(monkeypatch, "mallory@example.com")
    status, headers, _ = _exchange(port, "GET", callback, cookie=bound)
    assert status == 200 and serve.SESSION_COOKIE not in headers.get("set-cookie", "")

    _, again, _ = _exchange(port, "GET", "/account/google")
    other = parse_qs(urlparse(again["location"]).query)["state"][0]
    status, headers, _ = _exchange(
        port, "GET", f"/account/google/back?state={other}&code=x", cookie=bound
    )
    assert status == 200 and serve.SESSION_COOKIE not in headers.get("set-cookie", ""), (
        "another sign-in's cookie is not this one's"
    )


def test_a_google_sign_in_finishes_in_the_browser_that_started_it(
    tmp_path: Path, free_port: Callable[[], int], client: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store = _box(tmp_path, free_port, [])
    store.invite("dina@example.com")
    _proved(monkeypatch, "dina@example.com")
    _, started, _ = _exchange(port, "GET", "/account/google")
    state = parse_qs(urlparse(started["location"]).query)["state"][0]
    status, headers, _ = _exchange(
        port, "GET", f"/account/google/back?state={state}&code=x", cookie=_bound(started)
    )
    assert status in (302, 303), status
    assert serve.SESSION_COOKIE in headers["set-cookie"]
    assert f"{serve.GOOGLE_STATE_COOKIE}=;" in headers["set-cookie"], "cleared once read"


def test_a_google_signup_keeps_the_tag_of_the_link_it_came_by(
    tmp_path: Path, free_port: Callable[[], int], client: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """targum-internal#676: Continue with Google under the join form carries the form's
    `from`, and the account Google opens keeps it as the emailed signup does, narrowed
    the same way. An account that was already there keeps what brought it first."""
    port, store = _box(tmp_path, free_port, [])

    def through_google(address: str, start: str) -> None:
        store.invite(address)
        _proved(monkeypatch, address)
        _, started, _ = _exchange(port, "GET", start)
        state = parse_qs(urlparse(started["location"]).query)["state"][0]
        status, headers, _ = _exchange(
            port, "GET", f"/account/google/back?state={state}&code=x", cookie=_bound(started)
        )
        assert status in (302, 303) and serve.SESSION_COOKIE in headers["set-cookie"]

    def came(address: str) -> str:
        row = store.db.execute(
            "SELECT came_from FROM person WHERE email = ?", (address,)
        ).fetchone()
        return str(row["came_from"])

    through_google("dina@example.com", "/account/google?from=meta.after-duolingo")
    assert came("dina@example.com") == "meta.after-duolingo"
    through_google("page@example.com", "/account/google?from=https%3A//targum.page/aliyah")
    assert came("page@example.com") == "/aliyah"
    through_google("odd@example.com", "/account/google?from=%3Cscript%3E")
    assert came("odd@example.com") == ""
    through_google("dina@example.com", "/account/google?from=other")
    assert came("dina@example.com") == "meta.after-duolingo"


def test_a_refused_google_sign_in_keeps_the_tag_on_sign_in_again(
    tmp_path: Path, free_port: Callable[[], int], client: None
) -> None:
    """A sign-in left too long or not finished offers Sign in again; the press it links
    to carries the tag the first one did (targum-internal#676)."""
    port, _ = _box(tmp_path, free_port, [])
    _, started, _ = _exchange(port, "GET", "/account/google?from=meta.after-duolingo&next=%2Fadd")
    state = parse_qs(urlparse(started["location"]).query)["state"][0]
    status, _, page = _exchange(port, "GET", f"/account/google/back?state={state}&code=x")
    assert status == 200 and "That sign-in didn" in page
    assert 'href="/account/google?next=/add&amp;from=meta.after-duolingo"' in page


# -- the mailed link ---------------------------------------------------------------------


def test_a_second_press_on_a_spent_link_keeps_the_room(
    tmp_path: Path, free_port: Callable[[], int]
) -> None:
    """The page a spent link opens kept the room; the press on a page left open, posted
    after the link had gone, dropped it, so the new link it asked for landed on home."""
    links: list[tuple[str, str]] = []
    port, store = _box(tmp_path, free_port, links)
    store.invite("reader@example.com")
    assert _ask_for_a_link(port, {"email": "reader@example.com", "next": "/progress"}) == 200
    token = parse_qs(urlparse(links[0][0]).query)["t"][0]
    form = urlencode({"t": token, "next": "/progress"}).encode()
    kind = "application/x-www-form-urlencoded"
    status, headers, _ = _exchange(port, "POST", "/account/enter", form, kind)
    assert status == 303 and headers["location"] == "/progress"
    status, _, page = _exchange(port, "POST", "/account/enter", form, kind)
    assert status == 200 and "That link no longer works" in page
    assert 'data-next="/progress"' in page


# -- a Russian invitation stays Russian --------------------------------------------------


def test_a_russian_invitation_opens_the_sign_in_page_in_russian() -> None:
    """The invitation is written in the language they joined in; its button now opens the
    sign-in page in it too, rather than in whatever the browser asks for."""
    russian = letters.invitation(PUBLIC, "ru", connector=False)
    assert f"{PUBLIC}/account/signin?invited=1&lang=ru" in russian.text
    english = letters.invitation(PUBLIC, "en", connector=False)
    assert f"{PUBLIC}/account/signin?invited=1\n" in english.text + "\n"
    assert "lang=" not in english.text
    # A language with no interface of its own gets the page the browser asks for.
    assert "lang=" not in letters.invitation(PUBLIC, "fr", connector=False).text


def test_a_link_asked_for_in_russian_opens_its_page_in_russian(
    tmp_path: Path, free_port: Callable[[], int]
) -> None:
    """Asked from the Russian sign-in page, the mail was Russian and the page its link
    opened was the browser's English, and so was everything after it. The link carries
    the language; the page it opens speaks it, posts it with the press, and hands it to
    this browser for the arrival."""
    links: list[tuple[str, str]] = []
    port, store = _box(tmp_path, free_port, links)
    store.invite("chitatel@example.com")
    assert _ask_for_a_link(port, {"email": "chitatel@example.com", "into": "ru"}) == 200
    link, language = links[0]
    assert language == "ru"
    assert parse_qs(urlparse(link).query)["lang"] == ["ru"]

    asked = urlparse(link)
    status, _, page = _exchange(port, "GET", f"{asked.path}?{asked.query}")
    assert status == 200
    assert '<html lang="ru">' in page
    assert 'action="/account/enter?lang=ru"' in page
    assert 'data-asked="ru"' in page, "for signin.js to keep it in this browser"


def test_an_english_link_carries_no_language(tmp_path: Path, free_port: Callable[[], int]) -> None:
    links: list[tuple[str, str]] = []
    port, store = _box(tmp_path, free_port, links)
    store.invite("reader@example.com")
    assert _ask_for_a_link(port, {"email": "reader@example.com"}) == 200
    assert "lang=" not in links[0][0]
    asked = urlparse(links[0][0])
    _, _, page = _exchange(port, "GET", f"{asked.path}?{asked.query}")
    assert 'action="/account/enter" class="enter">' in page


# -- the invitation's link leads with signing in (targum-internal#723) -------------------


def test_every_invitation_link_says_it_came_from_the_invitation() -> None:
    """design.md §12, "The invitation's link leads with signing in" (2026-11-14): the
    letter's button, in English and Russian, with and without the connector's paragraph,
    carries `?invited=1`, and it is the only sign-in link the letter has."""
    import re

    for language in ("en", "ru"):
        for connector in (True, False):
            mail = letters.invitation(PUBLIC, language, connector=connector)
            for body in (mail.text, mail.html):
                links = re.findall(r"/account/signin[^\s\"'<]*", body)
                assert links, (language, connector)
                assert all("invited=1" in one for one in links), (language, connector, links)


def test_the_state_cookie_is_secure_only_over_https() -> None:
    """A laptop's own serve is plain http on loopback, where a Secure cookie is never
    sent back, and Google sign-in there would refuse every return."""
    assert "Secure" not in serve.google_state_cookie("s", "http://127.0.0.1:8765")
    assert "; Secure" in serve.google_state_cookie("s", "https://targum.page")
    cleared = serve.google_state_cookie("", "https://targum.page")
    assert f"{serve.GOOGLE_STATE_COOKIE}=;" in cleared and "Max-Age=0" in cleared
