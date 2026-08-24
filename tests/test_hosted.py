"""What has to be true before this runs on a box that is not a laptop.

Everything here failed, or would have, against the loopback-only server: these are the
things that only break once there is a domain in front of it.
"""

from __future__ import annotations

import json
import re
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest

from targum import serve
from targum.accounts import Store

PUBLIC = "https://targum.page"

# Where the module-scoped server keeps its database. A list rather than a return value so
# the handful of tests that need to reach past the API can, without every other test
# having to unpack something it does not use.
STORE: list[Path] = []


@pytest.fixture(scope="module")
def hosted(tmp_path_factory: pytest.TempPathFactory) -> tuple[int, str]:
    """A server started the way the deployment starts it, with somebody signed in."""
    tmp = tmp_path_factory.mktemp("hosted")
    store_path = tmp / "targum.db"
    STORE.append(store_path)
    store = Store(store_path)
    token = store.start_sign_in("reader@example.com")
    signed_in = store.finish_sign_in(token)
    assert signed_in is not None
    port = 8491

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
            # Read the response and close it. Firing a request and walking away leaves
            # the server writing into a socket that has been collected, which surfaces
            # as an "Exception occurred during processing of request" in about one run
            # in three — noise from the probe, mistaken for a fault in the product.
            probe = HTTPConnection("127.0.0.1", port, timeout=1)
            probe.request("GET", "/health")
            probe.getresponse().read()
            probe.close()
            break
        except OSError:
            time.sleep(0.1)
    return port, signed_in[1]


def ask(port: int, path: str, host: str, session: str = "") -> tuple[int, bytes]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("GET", path, skip_host=True)
    conn.putheader("Host", host)
    if session:
        conn.putheader("Cookie", f"targum_session={session}")
    conn.endheaders()
    response = conn.getresponse()
    body = response.read()
    conn.close()
    return response.status, body


# -- the allowlist ----------------------------------------------------------


def test_the_allowlist_follows_the_public_address() -> None:
    assert serve.hosts_for("") == frozenset(serve.SAFE_HOSTS)
    for address in (PUBLIC, "https://www.targum.page"):
        allowed = serve.hosts_for(address)
        assert "targum.page" in allowed
        # A registrar's www redirect is not always in place on the first day.
        assert "www.targum.page" in allowed
        assert "127.0.0.1" in allowed, "the proxy and the laptop both still connect over loopback"


def test_the_allowlist_admits_nothing_else() -> None:
    allowed = serve.hosts_for(PUBLIC)
    for other in ("evil.com", "targum.page.evil.com", "targumpage", ""):
        assert other not in allowed


def test_www_is_not_prefixed_onto_an_address() -> None:
    """`www.127.0.0.1` is not a thing anybody can reach, so it should not be admitted."""
    assert serve.hosts_for("http://127.0.0.1:8420") == frozenset(serve.SAFE_HOSTS)


@pytest.mark.parametrize("path", ["/", "/library", "/words"])
def test_a_signed_in_reader_is_served_at_the_public_domain(
    hosted: tuple[int, str], path: str
) -> None:
    """The one that was broken.

    A reader who has signed in correctly, arriving at the domain they were sent, got 403
    on every page — and the body told them to open a Terminal, which a hosted reader does
    not have. Loopback worked, so nothing local ever showed it.
    """
    port, session = hosted
    status, body = ask(port, path, "targum.page", session)
    assert status == 200, f"{path} refused a signed-in reader at the public domain"
    assert b"earlier session" not in body


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_loopback_still_works(hosted: tuple[int, str], host: str) -> None:
    port, session = hosted
    assert ask(port, "/library", host, session)[0] == 200


def test_a_stranger_host_is_still_refused(hosted: tuple[int, str]) -> None:
    """The property the allowlist exists for, kept while widening it."""
    port, session = hosted
    status, _ = ask(port, "/library", "evil.example.com", session)
    assert status == 403


# -- the start-up key ---------------------------------------------------------


def test_hosted_mints_no_start_up_key(hosted: tuple[int, str]) -> None:
    """It proves you can read a terminal. Hosted there is no terminal and no such person."""
    port, session = hosted
    _, body = ask(port, "/", "targum.page", session)
    assert b'TARGUM_KEY = ""' in body, "the page should be handed no key at all"


def test_no_page_hands_a_reader_a_key_in_a_url(hosted: tuple[int, str]) -> None:
    """A key in the address is a bearer token in browser history and in a Referer."""
    port, session = hosted
    for path in ("/", "/library", "/words"):
        page = ask(port, path, "targum.page", session)[1].decode("utf-8", "replace")
        for hit in re.finditer(r"\?k=", page):
            around = page[max(0, hit.start() - 40) : hit.start()]
            assert "key ?" in around or "key\n" in around or "(key" in around, (
                f"{path} emits a literal ?k= rather than a conditional: ...{around[-40:]}"
            )


def test_an_empty_key_authorises_nobody() -> None:
    """The trap in taking the key away.

    Hosted the key is the empty string, and `compare_digest("", "")` is True — so a
    comparison that guards only the value would authorise every anonymous request
    instead of none. `_authorised` has to test the token itself first.
    """
    source = Path("src/targum/serve.py").read_text()
    assert "if self.token and secrets.compare_digest(given, self.token):" in source


@pytest.mark.parametrize("query", ["", "?k=", "?k=guessed", "?k=%20"])
def test_no_key_gets_a_stranger_through_the_door(hosted: tuple[int, str], query: str) -> None:
    port, _ = hosted
    status, body = ask(port, "/words" + query, "targum.page")
    assert status == 200
    assert b"Coming soon" in body, "a stranger should meet the holding page, whatever they guess"


def test_run_locally_the_key_is_still_there(tmp_path: Path) -> None:
    """The mechanism is right for the case it was built for and stays.

    One person, one machine, nobody else able to reach it, and reading the terminal is
    the same as being the person sitting at it.
    """
    announced: list[str] = []
    port = 8492
    threading.Thread(
        target=lambda: serve.start(
            out=tmp_path / "out",
            port=port,
            open_browser=False,
            store=tmp_path / "local.db",
            announce=announced.append,
        ),
        daemon=True,
    ).start()
    for _ in range(60):
        if announced:
            break
        time.sleep(0.1)
    assert announced and "?k=" in announced[0]
    key = announced[0].split("k=")[1]
    assert ask(port, "/", "127.0.0.1")[0] == 403, "no key, no entry, on a single-user machine"
    assert ask(port, f"/?k={key}", "127.0.0.1")[0] == 200


# -- health -----------------------------------------------------------------


def test_health_needs_no_key_and_no_account(hosted: tuple[int, str]) -> None:
    """A monitor has neither, and asks from off the box."""
    port, _ = hosted
    status, body = ask(port, "/health", "targum.page")
    assert status == 200
    assert json.loads(body)["ok"] is True


def test_health_reports_the_store_rather_than_only_the_process() -> None:
    """A process running against a database it cannot read is the failure worth catching.

    An endpoint that only proves a socket is open would call that healthy.
    """
    assert "self.store.anyone()" in Path("src/targum/serve.py").read_text()


# -- the public surface -------------------------------------------------------


def test_robots_and_sitemap_follow_whether_the_shelves_are_open(
    hosted: tuple[int, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shut, a crawler is turned away from the whole site; open, it is given the map."""
    port, _ = hosted

    assert b"Disallow: /\n" in ask(port, "/robots.txt", "targum.page")[1]
    assert ask(port, "/sitemap.xml", "targum.page")[0] == 404

    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "1")
    status, robots = ask(port, "/robots.txt", "targum.page")
    assert status == 200
    assert b"Sitemap: https://targum.page/sitemap.xml" in robots
    assert b"Disallow: /account/" in robots

    status, sitemap = ask(port, "/sitemap.xml", "targum.page")
    assert status == 200
    assert b"<urlset" in sitemap


def test_the_sitemap_lists_every_text_and_nothing_private(
    hosted: tuple[int, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Generated from the catalogue, never kept by hand — a hand-written sitemap is
    wrong the first time somebody adds an entry and forgets, and being wrong here is
    invisible until the traffic does not arrive."""
    from targum.catalogue import CATALOGUE

    port, _ = hosted
    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "1")
    found = re.findall(r"<loc>(.*?)</loc>", ask(port, "/sitemap.xml", "targum.page")[1].decode())
    paths = {url.removeprefix("https://targum.page") for url in found}
    for entry in CATALOGUE:
        assert f"/{entry.shelf.value}/{entry.id}" in paths, entry.id
    for private in ("/words", "/readers", "/health", "/account/signin"):
        assert private not in paths, f"{private} should not be advertised"


def test_a_text_only_answers_on_its_own_shelf(
    hosted: tuple[int, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise every text would exist at two addresses, which splits whatever ranking
    it earns and puts a novel at a Beit Midrash URL."""
    port, _ = hosted
    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "1")
    assert ask(port, "/library/il-declaration", "targum.page")[0] == 200
    assert ask(port, "/beit-midrash/il-declaration", "targum.page")[0] == 404
    assert ask(port, "/library/no-such-text", "targum.page")[0] == 404


def test_the_front_door_is_still_shut(hosted: tuple[int, str]) -> None:
    """The shelves opening up must not have opened anything else."""
    port, _ = hosted
    for route in ("/", "/words"):
        status, body = ask(port, route, "targum.page")
        assert status == 200 and b"Coming soon" in body, route


# -- which shelf somebody reads in --------------------------------------------


def test_the_shelf_choice_outlives_a_sign_out(tmp_path: Path) -> None:
    """The whole reason it is on the account rather than in the browser.

    `sync.js` deletes every `targum:*` key but the theme on sign-out — deliberately,
    after a bug that left a previous reader's words behind — so a local preference would
    be forgotten every time somebody signed out on their own machine, and a new device
    would show them the shelf they asked not to see.
    """
    store = Store(tmp_path / "shelf.db")
    signed_in = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert signed_in is not None
    person, session = signed_in
    assert person.shelf == "", "undecided is not the same as choosing the Library"

    store.choose_shelf(person, "beit-midrash")
    store.sign_out(session)

    again = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert again is not None
    assert again[0].shelf == "beit-midrash"
    # And on a device that has never held any browser storage at all.
    assert store.whoever(again[1]).shelf == "beit-midrash"  # type: ignore[union-attr]


def test_only_a_shelf_that_exists_can_be_chosen(tmp_path: Path) -> None:
    """It arrives from a request, so it is checked rather than trusted."""
    store = Store(tmp_path / "shelf.db")
    signed_in = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert signed_in is not None
    person = signed_in[0]
    for junk in ("../etc", "Library", "beit midrash", "'; DROP TABLE person; --"):
        with pytest.raises(ValueError):
            store.choose_shelf(person, junk)
    for good in ("library", "beit-midrash", ""):
        store.choose_shelf(person, good)


def test_the_account_tells_the_page_which_shelf(hosted: tuple[int, str]) -> None:
    """The page is baked once and shared, so this is the only way a per-person choice
    can reach it."""
    port, session = hosted
    status, body = ask(port, "/account/me", "targum.page", session)
    assert status == 200
    assert "shelf" in json.loads(body)


# -- who may open an account --------------------------------------------------


def post(port: int, path: str, payload: dict[str, object], host: str = "targum.page"):
    body = json.dumps(payload).encode()
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", path, skip_host=True)
    conn.putheader("Host", host)
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", str(len(body)))
    conn.endheaders()
    conn.send(body)
    response = conn.getresponse()
    out = json.loads(response.read())
    conn.close()
    return response.status, out


def test_an_empty_list_means_nobody_rather_than_everybody(tmp_path: Path) -> None:
    """The safe way round, and the whole point.

    A box standing on a public address with a funded API key must not, by default, let
    whoever finds it open an account and start spending — the per-account rail is $3.00
    a *day*, which is a rate limit rather than a plan limit.
    """
    store = Store(tmp_path / "invite.db")
    assert store.invitations() == []
    assert not store.may_join("stranger@example.com")


def test_only_an_invited_address_gets_a_link(tmp_path: Path) -> None:
    sent: list[str] = []

    class Mailer:
        def send(self, to: str, link: str) -> None:
            sent.append(to)

    store_path = tmp_path / "invite.db"
    store = Store(store_path)
    port = 8494
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

    status, body = post(port, "/account/sign-in", {"email": "wife@example.com"})
    assert status == 403 and "not open" in body["error"]
    assert sent == [], "an uninvited address must not be mailed"

    # Messy on the way in, tidied on the way through — the same rule addresses already
    # follow everywhere else, so an invitation typed with a capital still matches.
    store.invite("  Wife@Example.com ")
    assert store.invitations() == ["wife@example.com"]

    assert post(port, "/account/sign-in", {"email": "wife@example.com"})[0] == 200
    assert sent == ["wife@example.com"]
    assert post(port, "/account/sign-in", {"email": "stranger@example.com"})[0] == 403
    assert sent == ["wife@example.com"], "and still nobody else"


def test_locally_there_is_no_guest_list(tmp_path: Path) -> None:
    """One person, one machine, nobody else able to reach it. Making them ask themselves
    for permission would be absurd."""
    store = Store(tmp_path / "local.db")
    assert store.invitations() == []
    # The gate lives in the hosted branch of `_sign_in`, so this is the assertion that
    # the switch is the thing deciding rather than the list being empty.
    assert "self.require_account and not self.store.may_join" in Path(
        "src/targum/serve.py"
    ).read_text(encoding="utf-8")


def test_uninviting_does_not_lock_out_somebody_already_reading(tmp_path: Path) -> None:
    """This decides who may *join*. Someone who has been reading for a month should not
    lose their own words to an edit of a guest list."""
    store = Store(tmp_path / "invite.db")
    store.invite("reader@example.com")
    signed_in = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert signed_in is not None

    assert store.uninvite("reader@example.com") is True
    assert store.invitations() == []
    assert store.whoever(signed_in[1]) is not None, "their session should still work"


def test_removing_an_address_that_was_never_there_says_so(tmp_path: Path) -> None:
    assert Store(tmp_path / "invite.db").uninvite("nobody@example.com") is False


def test_an_invitation_survives_a_restart(tmp_path: Path) -> None:
    """It is a table rather than an environment variable so the list outlives a redeploy
    and gets backed up with everything else."""
    path = tmp_path / "invite.db"
    Store(path).invite("reader@example.com")
    assert Store(path).may_join("reader@example.com")


# -- taking everything away ---------------------------------------------------


def test_the_export_holds_every_language_and_no_filter(hosted: tuple[int, str]) -> None:
    """The two Export buttons on the words page hand back what you are *looking at* —
    one language, filtered by the status filter. That is right for a spreadsheet and
    quietly wrong for leaving: a reader with Hebrew and Russian would get a subset with
    no sign anything was missing. This one is everything.
    """
    port, session = hosted
    store = Store(STORE[0])
    person = store.whoever(session)
    assert person is not None
    store.push(
        person,
        {
            "words": [
                {"language": "he", "lemma": "ספר", "status": 2, "at": 1, "seen": 1},
                {"language": "ru", "lemma": "книга", "status": 1, "at": 2, "seen": 2},
            ]
        },
    )

    status, body = ask(port, "/account/export", "targum.page", session)
    assert status == 200
    data = json.loads(body)
    assert {word["language"] for word in data["words"]} == {"he", "ru"}
    assert data["account"]["email"] == "reader@example.com"
    for expected in ("words", "phrases", "docs", "builds", "account"):
        assert expected in data, expected


def test_the_export_arrives_as_a_file(hosted: tuple[int, str]) -> None:
    """A wall of JSON in a browser tab is not a thing anybody can keep."""
    port, session = hosted
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("GET", "/account/export", skip_host=True)
    conn.putheader("Host", "targum.page")
    conn.putheader("Cookie", f"targum_session={session}")
    conn.endheaders()
    response = conn.getresponse()
    response.read()
    assert "attachment" in (response.getheader("Content-Disposition") or "")
    conn.close()


def test_the_export_carries_no_credentials(hosted: tuple[int, str]) -> None:
    """Sessions and sign-in links are keys, not data.

    Writing them into a file somebody downloads, mails to themselves and leaves in a
    downloads folder would be handing out live access to their own account.
    """
    port, session = hosted
    body = ask(port, "/account/export", "targum.page", session)[1].decode()
    assert session not in body
    assert "session" not in body and "link" not in json.loads(body)


def test_nobody_else_gets_your_data(hosted: tuple[int, str]) -> None:
    port, _ = hosted
    status, body = ask(port, "/account/export", "targum.page")
    assert status == 401, "and as data, not as a page somebody has to read"
    assert json.loads(body)["error"]
