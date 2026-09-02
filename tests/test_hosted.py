"""What has to be true before this runs on a box that is not a laptop.

Everything here failed, or would have, against the loopback-only server: these are the
things that only break once there is a domain in front of it.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
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
def hosted(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> tuple[int, str]:
    """A server started the way the deployment starts it, with somebody signed in."""
    tmp = tmp_path_factory.mktemp("hosted")
    store_path = tmp / "targum.db"
    STORE.append(store_path)
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


@pytest.mark.parametrize("path", ["/", "/library", "/progress"])
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
    for path in ("/", "/library", "/progress"):
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
    status, body = ask(port, "/progress" + query, "targum.page")
    assert status == 200
    assert b"Coming soon" in body, "a stranger should meet the holding page, whatever they guess"


def test_run_locally_the_key_is_still_there(tmp_path: Path, free_port: Callable[[], int]) -> None:
    """The mechanism is right for the case it was built for and stays.

    One person, one machine, nobody else able to reach it, and reading the terminal is
    the same as being the person sitting at it.
    """
    announced: list[str] = []
    port = free_port()
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
        assert f"/library/{entry.id}" in paths, entry.id
    for private in ("/progress", "/readers", "/health", "/account/signin"):
        assert private not in paths, f"{private} should not be advertised"
    # Shut for the alpha, so a crawler is told about none of them.
    for shut in ("/privacy", "/terms", "/retention", "/deletion"):
        assert shut not in paths, shut


def test_the_legal_documents_are_shut_for_the_alpha(hosted: tuple[int, str]) -> None:
    """Shut all the way down, as the catalogue is: 404 rather than the holding page.

    The holding page would be the worse answer. It says "Coming soon" with a way in, so
    a privacy notice that answered with it would look present and be absent, which is
    the failure that is hardest to notice from outside.
    """
    port, _ = hosted
    for route in ("/privacy", "/terms", "/retention", "/deletion"):
        status, body = ask(port, route, "targum.page")
        assert status == 404, route
        assert b"Coming soon" not in body, f"{route} answered with the holding page"


def test_the_legal_documents_answer_once_the_switch_is_thrown(
    hosted: tuple[int, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """What beta turns on, asserted now so that throwing the switch is all it takes.

    Hosted is the shape that matters: an account is required for everything, so a route
    left out of `OPEN_TO_STRANGERS` would answer with the holding page rather than the
    document. They open whether or not the shelves are, being no part of the shop
    window.
    """
    port, _ = hosted
    monkeypatch.setenv("TARGUM_PUBLIC_LEGAL", "1")
    for route in ("/privacy", "/terms", "/retention", "/deletion"):
        status, body = ask(port, route, "targum.page")
        assert status == 200, route
        assert b"Coming soon" not in body, f"{route} fell through to the holding page"
        assert b"hello@targum.page" in body, f"{route} gives nobody to write to"


def test_the_sitemap_and_robots_name_the_documents_once_they_are_open(
    hosted: tuple[int, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both lists are built from `LEGAL_ROUTES` behind the same switch, so neither can
    advertise a document that answers 404."""
    port, _ = hosted
    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "1")
    monkeypatch.setenv("TARGUM_PUBLIC_LEGAL", "1")
    robots = ask(port, "/robots.txt", "targum.page")[1].decode()
    sitemap = ask(port, "/sitemap.xml", "targum.page")[1].decode()
    for route in ("/privacy", "/terms", "/retention", "/deletion"):
        assert f"Allow: {route}" in robots, route
        assert f"<loc>https://targum.page{route}</loc>" in sitemap, route


def test_every_text_answers_at_one_address(
    hosted: tuple[int, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """There were two shelves and so two URL shapes, and a text at two addresses splits
    whatever ranking it earns. One list, one address, whatever the text is."""
    port, _ = hosted
    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "1")
    assert ask(port, "/library/il-declaration", "targum.page")[0] == 200
    assert ask(port, "/library/ruth", "targum.page")[0] == 200, "Tanakh included"
    # The Beit Midrash shelf is gone, so its addresses are simply unknown routes now.
    # What matters is that no second copy of the text is served from one.
    from targum.catalogue import by_id

    ruth = by_id("ruth")
    assert ruth is not None
    assert ruth.title.encode() not in ask(port, "/beit-midrash/ruth", "targum.page")[1]
    assert ask(port, "/library/no-such-text", "targum.page")[0] == 404


def test_the_front_door_is_still_shut(hosted: tuple[int, str]) -> None:
    """The shelves opening up must not have opened anything else."""
    port, _ = hosted
    for route in ("/", "/progress"):
        status, body = ask(port, route, "targum.page")
        assert status == 200 and b"Coming soon" in body, route


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


def test_only_an_invited_address_gets_a_link(tmp_path: Path, free_port: Callable[[], int]) -> None:
    sent: list[str] = []

    class Mailer:
        def send(self, to: str, link: str) -> None:
            sent.append(to)

    store_path = tmp_path / "invite.db"
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


def test_the_export_holds_every_kind_the_account_syncs(hosted: tuple[int, str]) -> None:
    """Asked of `KINDS`, not of a list written here.

    The acceptance criterion on targum-internal #17 is that adding a new thing the
    account keeps must not need adding to the export separately. `Store.everything`
    already loops `KINDS`, so it is true — but the test above checked a hand-written
    tuple that omitted `days` and `meanings`, which meant either could have been dropped
    from the export and nothing would have failed. Progress is days; losing them
    silently is the exact shape that issue is about.

    Derived here, so a kind added tomorrow is covered tomorrow.
    """
    from targum.accounts import KINDS

    port, session = hosted
    status, body = ask(port, "/account/export", "targum.page", session)
    assert status == 200
    data = json.loads(body)

    missing = [name for name in KINDS if name not in data]
    assert not missing, f"the export drops what the account syncs: {missing}"
    assert "days" in data, "reading days are progress, and progress is the point of this"


def test_the_export_carries_what_they_said_about_themselves() -> None:
    """A name typed on the profile page and the languages chosen there are as much
    theirs as their words are, and neither is a kind the account syncs — so `KINDS`
    could not carry them and the export had to say so itself (targum-internal#17)."""
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        store = Store(Path(raw) / "db")
        person, _ = store.finish_sign_in(store.start_sign_in("reader@example.com"))  # type: ignore[misc]
        store.rename(person, "Ruth")
        store.choose(person, "learning", ["he", "yi"])
        taken = store.everything(person)
        assert taken["account"]["name"] == "Ruth"
        assert "picture" in taken["account"]
        assert {(row["kind"], row["language"]) for row in taken["languages"]} == {
            ("learning", "he"),
            ("learning", "yi"),
        }


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


# -- how much of a text you already know --------------------------------------


def test_the_shelf_says_how_much_of_each_text_you_know(hosted: tuple[int, str]) -> None:
    """The number the reader has always computed and thrown away.

    `reader.js` works it out for the section in front of you and says so — its own comment
    records why: *the reason to know it is choosing what to read next.* It was never
    persisted, so the choosing happened somewhere it could not be seen.
    """
    import json as json_module

    from targum.coverage import against, lemmas

    port, session = hosted
    store = Store(STORE[0])
    person = store.whoever(session)
    assert person is not None

    # A targum with real annotation on this reader's shelf.
    home = Path(str(STORE[0])).parent / "out" / f"p{person.id}"
    folder = home / "measured"
    (folder / "reader").mkdir(parents=True, exist_ok=True)
    (folder / "reader" / "index.html").write_text("<html></html>", encoding="utf-8")
    (folder / "document.json").write_text(
        json_module.dumps({"title": "Measured", "language": "he", "content_hash": "h"}),
        encoding="utf-8",
    )
    (folder / "annotation.json").write_text(
        json_module.dumps(
            {"tokens": {"s1": [{"lemma": w} for w in ("אחד", "שתיים", "שלוש", "ארבע")]}}
        ),
        encoding="utf-8",
    )
    store.push(
        person,
        {"words": [{"language": "he", "lemma": "אחד", "status": 9, "at": 1, "seen": 1}]},
    )

    status, body = ask(port, "/readers", "targum.page", session)
    assert status == 200
    mine = [r for r in json.loads(body)["readers"] if r["name"] == "measured"]
    assert mine, "the targum should be on the shelf"
    assert mine[0]["known"] == 0.25, "one of its four words is known"
    assert mine[0]["fresh"] == 3, "and three have never been marked"

    # Counted straight, the same answer.
    assert against(folder, {"אחד": 9}).known == 0.25  # type: ignore[union-attr]
    assert len(lemmas(folder)) == 4


def test_a_targum_with_no_annotation_says_nothing_rather_than_zero(tmp_path: Path) -> None:
    """ "0% known" and "not measured" are very different claims to make about a book, and
    a targum built without `--words` is a normal state rather than a fault."""
    from targum.coverage import against

    assert against(tmp_path, {"anything": 9}) is None


def test_the_shelf_never_carries_a_server_path(hosted: tuple[int, str]) -> None:
    """The folder is resolved on the server. Where a file sits on disk is not something a
    browser has any business being told."""
    port, session = hosted
    for reader in json.loads(ask(port, "/readers", "targum.page", session)[1])["readers"]:
        assert "folder" not in reader
        assert not any(str(value).startswith("/") for value in reader.values())


# -- who somebody is -------------------------------------------------------------


def test_a_name_is_tidied_and_kept(tmp_path: Path) -> None:
    """An account was an address and nothing else. A corner pill cannot show an address,
    and a page that greets you by one is not greeting you."""
    store = Store(tmp_path / "words.db")
    store.start_sign_in("someone@example.com")
    person = store.person_by_email("someone@example.com")
    assert person is not None

    assert store.rename(person, "  David   Langellotti  ") == "David Langellotti"
    assert store.profile(person)["name"] == "David Langellotti"
    assert store.profile(person)["initials"] == "DL"

    # Empty is allowed and means going back to having none.
    assert store.rename(person, "") == ""
    assert store.profile(person)["initials"] == "SO", "the address, as it was before"


def test_initials_come_from_whatever_there_is() -> None:
    from targum.accounts import initials

    assert initials("David Langellotti", "x@y.com") == "DL"
    assert initials("", "djlangellotti@gmail.com") == "DJ"
    assert initials("", "david.langellotti@x.com") == "DL", "a dot is a name boundary"
    assert initials("דוד לנגלוטי", "x@y.com") == "דל", "no case to raise, and none needed"
    assert initials("", "") == "?"


def test_a_meaning_already_held_is_free_to_ask_for(hosted: tuple[int, str]) -> None:
    """A card opening asks whether the meaning is already in the cache before it offers
    a button. That question must never buy anything — and must not need a key to ask."""
    from targum.annotate.gloss import gloss_key, gloss_provider_name
    from targum.cache import Cache

    port, session = hosted
    cache = Cache()
    cache.put(
        "gloss",
        gloss_key(cache, "ארץ", "he", "en", gloss_provider_name()),
        {"gloss": "land", "part_of_speech": "noun"},
    )

    def ask(lemma: str) -> tuple[int, dict[str, object]]:
        body = json.dumps({"lemma": lemma, "source": "he", "target": "en", "free": True}).encode()
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        conn.putrequest("POST", "/gloss", skip_host=True)
        conn.putheader("Host", "targum.page")
        conn.putheader("Cookie", f"targum_session={session}")
        conn.putheader("Content-Type", "application/json")
        conn.putheader("Content-Length", str(len(body)))
        conn.endheaders()
        conn.send(body)
        response = conn.getresponse()
        out = json.loads(response.read())
        conn.close()
        return response.status, out

    assert ask("ארץ") == (
        200,
        {"lemma": "ארץ", "meaning": "land", "citation": "", "plural": "", "cached": True},
    )
    status, answer = ask("שלום")
    assert status == 200 and answer["meaning"] is None and answer["cached"] is False


def test_a_phrase_already_answered_is_free_to_ask_for(
    hosted: tuple[int, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Selecting a few words asks what they mean against the sentence's translation.
    An answer already held comes back without a key; one that is not is refused
    politely when nothing can be bought; and the endpoint is for phrases in the
    sentence in front of the reader, not a translator with an open door."""
    from targum.annotate.gloss import gloss_provider_name
    from targum.annotate.phrase import PHRASE_MODEL, phrase_key
    from targum.cache import Cache

    port, session = hosted
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    sentence = 'השבוע: השב"כ מאשר איום על בנו של ראש הממשלה, ובאיסטנבול נפתחת ועדה צבאית חדשה.'
    translation = (
        "This week: the Shin Bet confirms a threat against the prime minister's son, "
        "and in Istanbul a new military committee opens."
    )
    cache = Cache()
    cache.put(
        "phrase",
        phrase_key(
            cache,
            "ועדה צבאית חדשה",
            sentence,
            translation,
            "he",
            "en",
            gloss_provider_name(PHRASE_MODEL),
        ),
        {"meaning": "a new military committee", "quoted": True},
    )
    base: dict[str, object] = {
        "phrase": "ועדה צבאית חדשה",
        "sentence": sentence,
        "translation": translation,
        "source": "he",
        "target": "en",
    }

    def ask(**changes: object) -> tuple[int, dict[str, object]]:
        return _signed_post(port, "/phrase", {**base, **changes}, session)

    assert ask() == (
        200,
        {
            "meaning": "a new military committee",
            "quoted": True,
            "kind": "",
            "citation": "",
            "cached": True,
        },
    )
    status, answer = ask(phrase="ראש הממשלה")
    assert status == 402 and answer["error"], "not held and nothing can be bought"
    assert ask(phrase="שלום")[0] == 400, "not in the sentence"
    assert ask(phrase="א", sentence="א" * 601)[0] == 400, "a paragraph, not a sentence"
    assert ask(translation="")[0] == 400
    assert ask(source="")[0] == 400


def test_no_page_stops_for_want_of_a_key() -> None:
    """Hosted there is no key: the session cookie is what identifies the reader. Three
    scripts asked for the key and returned when it was missing — the next-chapter
    prefetch, Prepare all, and the chapter page's own Translate — so on the live site
    the second chapter of every upload was never bought, and nothing said why."""
    from targum.render.builder import ASSETS

    for name in ("reader.js", "contents.js"):
        script = (ASSETS / name).read_text(encoding="utf-8")
        # `if (!key) return path;` inside `keyed()` is the right shape: the key is
        # optional there. Stopping the whole script on it is the wrong one.
        assert not re.search(r"if \(!key\) return;", script), f"{name} stops without a key"
        assert "!link || !key" not in script, name
        assert "!key || !press" not in script, name


# -- the shared home ------------------------------------------------------------


def _signed_post(port: int, path: str, payload: dict[str, object], session: str):
    body = json.dumps(payload).encode()
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", path, skip_host=True)
    conn.putheader("Host", "targum.page")
    conn.putheader("Cookie", f"targum_session={session}")
    conn.putheader("Content-Type", "application/json")
    conn.putheader("Content-Length", str(len(body)))
    conn.endheaders()
    conn.send(body)
    response = conn.getresponse()
    out = json.loads(response.read())
    conn.close()
    return response.status, out


def _targum(folder: Path, title: str) -> None:
    (folder / "reader").mkdir(parents=True, exist_ok=True)
    (folder / "reader" / "index.html").write_text(f"<html>{title}</html>", encoding="utf-8")
    (folder / "document.json").write_text(
        json.dumps({"title": title, "language": "he", "content_hash": title}), encoding="utf-8"
    )


def test_a_shared_targum_is_readable_by_anyone_signed_in(hosted: tuple[int, str]) -> None:
    """What a reader with nothing on their shelf is handed first. Built once by
    `targum seed` into a home nobody owns, and read from there by everybody."""
    port, session = hosted
    out = Path(str(STORE[0])).parent / "out"
    _targum(out / "shared" / "ruth", "ruth")

    status, body = ask(port, "/reader/ruth/reader/index.html", "targum.page", session)
    assert status == 200 and b"ruth" in body

    status, body = ask(port, "/readers", "targum.page", session)
    assert status == 200
    shared = json.loads(body)["shared"]
    assert [r["name"] for r in shared] == ["ruth"]
    assert shared[0]["shared"] is True
    assert "ruth" not in [r["name"] for r in json.loads(body)["readers"]], "not on your shelf"


def test_a_shared_targum_cannot_be_bought_or_trashed(hosted: tuple[int, str]) -> None:
    """Everything that changes a targum goes through `within(home, name)`, and the shared
    home is not this reader's home."""
    port, session = hosted
    out = Path(str(STORE[0])).parent / "out"
    _targum(out / "shared" / "ruth", "ruth")
    assert _signed_post(port, "/trash", {"name": "ruth"}, session)[0] == 404
    assert _signed_post(port, "/restore", {"name": "ruth"}, session)[0] == 404
    assert _signed_post(port, "/chapter", {"name": "ruth", "number": 2}, session)[0] == 404
    assert (out / "shared" / "ruth" / "reader" / "index.html").is_file()


def test_one_account_still_cannot_read_anothers_reader(hosted: tuple[int, str]) -> None:
    """The guard the shared home was added beside, not instead of."""
    port, session = hosted
    out = Path(str(STORE[0])).parent / "out"
    _targum(out / "p999" / "secret", "secret")
    for path in (
        "/reader/secret/reader/index.html",
        "/reader/../p999/secret/reader/index.html",
        "/reader/%2E%2E/p999/secret/reader/index.html",
        "/reader/../shared/../p999/secret/reader/index.html",
    ):
        status, body = ask(port, path, "targum.page", session)
        assert status == 404, path
        assert b"secret" not in body, path


def test_your_builds_are_listed_for_you_alone(hosted: tuple[int, str]) -> None:
    port, session = hosted
    status, body = ask(port, "/jobs", "targum.page")
    assert status == 401, "data routes answer as data"
    status, body = ask(port, "/jobs", "targum.page", session)
    assert status == 200
    assert json.loads(body) == {"jobs": []}


def test_watching_a_build_that_is_not_yours_is_not_found(hosted: tuple[int, str]) -> None:
    port, session = hosted
    assert _signed_post(port, "/jobs/watch", {"id": "nope"}, session)[0] == 404


def test_a_finished_text_is_kept_on_the_account_and_in_the_export() -> None:
    """targum-internal#112: persisted per person, synced, and in what they take away."""
    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        store = Store(Path(raw) / "db")
        person, _ = store.finish_sign_in(store.start_sign_in("reader@example.com"))  # type: ignore[misc]
        store.push(
            person,
            {
                "docs": [
                    {
                        "hash": "h",
                        "title": "One",
                        "language": "he",
                        "updated": 5,
                        "opened": 4,
                        "done": 9,
                        "seen": 5,
                    }
                ]
            },
        )
        rows = store.db.execute("SELECT done FROM doc WHERE hash = 'h'").fetchall()
        assert [row["done"] for row in rows] == [9]
        taken = json.dumps(store.everything(person))
        assert '"done": 9' in taken
