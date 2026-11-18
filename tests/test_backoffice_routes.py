"""The back office's six pages and a page for each reader (design.md §12, 2026-11-17),
asked of the running server: who gets in, what each answer may be kept as, and that a
reader's address never rides in an address the proxy writes down."""

from __future__ import annotations

import re
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlencode

import pytest
import test_serve
from test_serve import Postbox, sign_in

from targum import backoffice, serve
from targum.accounts import Store

served = test_serve.served
postbox = test_serve.postbox

ROOT = Path(__file__).resolve().parent.parent

#: Every page: the six under the bar, then one reader's (its id filled in by the test).
PAGES = [
    "/back-office",
    "/back-office/",
    "/back-office/readers",
    "/back-office/waitlist",
    "/back-office/traffic",
    "/back-office/shelf",
    "/back-office/operations",
    "/back-office/readers/{id}",
]
#: Addresses under the door that name no page, or no reader.
NOWHERE = [
    "/back-office/nonsense",
    "/back-office/promote",
    "/back-office/readers/abc",
    "/back-office/readers/99999",
    "/back-office/readers/{id}/more",
    "/back-office/readers/+{id}",
    "/back-office/readers/%C2%B2",
    "/back-office/overview",
    "/back-office/reader",
]
#: Every form the pages post, with a body that would do something for an admin.
POSTS = {
    "/back-office/promote": {"id": "nothing", "action": "decline"},
    "/back-office/take-down": {"id": "nothing"},
    "/back-office/open-the-door": {"count": "1"},
    "/back-office/let-in": {"email": "waiting@example.com"},
    "/back-office/resend": {"email": "waiting@example.com"},
    "/back-office/turn-off": {"email": "waiting@example.com"},
    "/back-office/turn-on": {"email": "waiting@example.com"},
    "/back-office/balance": {"service": "anthropic", "said": "$1"},
    "/back-office/told": {"id": "1", "state": "fixed"},
    "/back-office/fault": {"message": "TypeError: boom"},
}

#: What a reader wrote, kept or brought, which no page here may show.
SECRETS = ("סודיביותר", "a-secret-phrase", "a-secret-note", "Secret Upload Title")


def ask(
    port: int,
    method: str,
    path: str,
    cookie: str = "",
    fields: dict[str, str] | None = None,
    navigate: bool = False,
    sent: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], str]:
    """A request, and its status, headers and body. `sent` adds headers of its own."""
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if cookie:
            headers["Cookie"] = cookie
        if navigate:
            headers |= {"Accept": "text/html", "Sec-Fetch-Mode": "navigate"}
        headers |= sent or {}
        body = urlencode(fields).encode("utf-8") if fields is not None else None
        connection.request(method, path, body, headers)
        response = connection.getresponse()
        raw = response.read()
        return (
            response.status,
            {key.lower(): value for key, value in response.getheaders()},
            raw.decode("utf-8", "replace"),
        )
    finally:
        connection.close()


@pytest.fixture
def world(
    served: tuple[int, str, Path], postbox: Postbox, tmp_path: Path
) -> tuple[int, Store, str, str, int]:
    """A running server with a reader who has kept, written and brought things, somebody
    confirmed on the waitlist, and an admin. The port, the store, the reader's session,
    the admin's, and the reader's id."""
    port, _, _ = served
    store = Store(tmp_path / "words.db")
    reader = sign_in(port, postbox, "reader@example.com")
    person = store.person_by_email("reader@example.com")
    assert person is not None
    store.db.execute(
        "INSERT INTO word (person, language, lemma, note, at) VALUES (?, 'he', ?, ?, 1)",
        (person.id, SECRETS[0], SECRETS[2]),
    )
    store.db.execute(
        "INSERT INTO phrase (person, id, text, note, at) VALUES (?, 'p1', ?, ?, 1)",
        (person.id, SECRETS[1], SECRETS[2]),
    )
    store.db.execute(
        "INSERT INTO doc (person, hash, title, opened, updated) VALUES (?, 'h1', ?, 1, 1)",
        (person.id, SECRETS[3]),
    )
    store.db.commit()
    token = store.join_waitlist("waiting@example.com", "en")
    assert token is not None and store.confirm_waiting(token)
    store.make_admin("ops@example.com")
    admin = sign_in(port, postbox, "ops@example.com")
    return port, store, reader, admin, person.id


def test_signed_out_every_page_is_the_holding_page(world) -> None:  # type: ignore[no-untyped-def]
    port, _, _, _, who = world
    for path in [*PAGES, *NOWHERE, f"/back-office?who={who}"]:
        for navigate in (False, True):
            status, headers, body = ask(port, "GET", path.format(id=who), navigate=navigate)
            assert status == 200, (path, status)
            assert headers["cache-control"] == "no-store", path
            assert "<h1>back office" not in body and "reader@example.com" not in body, path
            assert "location" not in headers, "not even where the page went"


def test_a_reader_who_is_not_an_admin_is_told_there_is_nothing_here(world) -> None:  # type: ignore[no-untyped-def]
    port, _, reader, _, who = world
    for path in [*PAGES, *NOWHERE, f"/back-office?who={who}"]:
        for navigate in (False, True):
            status, headers, body = ask(port, "GET", path.format(id=who), reader, navigate=navigate)
            assert status == 404, (path, status)
            assert headers["cache-control"] == "no-store", path
            assert "<h1>back office" not in body and "ops@example.com" not in body, path
            assert "location" not in headers


def test_an_admin_opens_each_page_and_it_is_kept_nowhere(world) -> None:  # type: ignore[no-untyped-def]
    port, _, _, admin, who = world
    for path in PAGES:
        status, headers, body = ask(port, "GET", path.format(id=who), admin, navigate=True)
        assert status == 200, (path, status)
        assert headers["cache-control"] == "no-store", path
        assert headers["referrer-policy"] == "no-referrer", path
        assert '<nav class="bo-tabs"' in body and body.count('aria-current="page"') >= 1, path
        assert 'name="robots" content="noindex' in body
        # Nothing a reader wrote, kept or brought: not the lemma, the phrase, a note or the
        # title of what they opened.
        for secret in SECRETS:
            assert secret not in body, (path, secret)
    for path in NOWHERE:
        status, headers, _ = ask(port, "GET", path.format(id=who), admin)
        assert status == 404, (path, status)
        assert headers["cache-control"] == "no-store", path


def test_each_page_is_its_own(world) -> None:  # type: ignore[no-untyped-def]
    port, _, _, admin, who = world
    one = {
        "/back-office": '<h2 id="follow">Follow up',
        "/back-office/readers": "<h2>Readers",
        "/back-office/waitlist": "<h2>The waitlist",
        "/back-office/traffic": '<h2 id="visitors">',
        "/back-office/shelf": "<h2>Proposed for the shelf",
        "/back-office/operations": '<h2 id="services">',
        f"/back-office/readers/{who}": "credits this month &middot;",
    }
    for path in one:
        body = ask(port, "GET", path, admin)[2]
        for other, other_head in one.items():
            assert (other_head in body) == (other == path), (path, other)
    reader = ask(port, "GET", f"/back-office/readers/{who}", admin)[2]
    assert "reader@example.com" in reader and 'href="/back-office/readers">Back' in reader
    assert 'href="/back-office/readers" aria-current="page"' in reader


def test_the_old_reader_address_goes_on_to_the_readers_page(world) -> None:  # type: ignore[no-untyped-def]
    port, _, _, admin, who = world
    status, headers, _ = ask(port, "GET", f"/back-office?who={who}", admin)
    assert (status, headers["location"]) == (302, f"/back-office/readers/{who}")
    assert headers["cache-control"] == "no-store"
    for odd in ("abc", "²", "0", "1" * 30):
        status, headers, _ = ask(port, "GET", f"/back-office?{urlencode({'who': odd})}", admin)
        assert (status, headers["location"]) == (302, "/back-office/readers"), odd


def test_every_press_is_the_admins_alone(world) -> None:  # type: ignore[no-untyped-def]
    port, store, reader, admin, _ = world
    store.fault(None, "TypeError: boom", "", "/texts")
    store.tell(None, "please fix")
    for path, fields in POSTS.items():
        for cookie in ("", reader):
            status, headers, _ = ask(port, "POST", path, cookie, fields)
            assert status == 404, (path, bool(cookie), status)
            assert "location" not in headers
    # Nothing moved for either of them.
    assert store.waiting_state("waiting@example.com") == "on"
    assert store.balances() == {}
    assert store.told()[0]["state"] == "open"
    assert store.faults()[0]["fixed"] == 0
    # And the admin is sent back to the page each form is on.
    pages = {
        "/back-office/promote": "/back-office/shelf",
        "/back-office/take-down": "/back-office/shelf",
        "/back-office/open-the-door": "/back-office/waitlist",
        "/back-office/let-in": "/back-office/waitlist",
        "/back-office/turn-off": "/back-office/waitlist",
        "/back-office/turn-on": "/back-office/waitlist",
        "/back-office/resend": "/back-office",
        "/back-office/balance": "/back-office/operations",
        "/back-office/told": "/back-office",
        "/back-office/fault": "/back-office/operations",
    }
    for path, fields in POSTS.items():
        status, headers, _ = ask(port, "POST", path, admin, fields)
        assert status in (303, 400), (path, status)
        if status == 303:
            assert re.split(r"[?#]", headers["location"])[0] == pages[path], path
            assert headers["cache-control"] == "no-store"


def test_a_press_never_puts_an_address_in_the_address(world) -> None:  # type: ignore[no-untyped-def]
    """What a press said rides back as `?said=`, which the proxy logs (targum.log). It
    says what happened, never to whom."""
    port, store, _, admin, _ = world
    for path in ("/back-office/turn-off", "/back-office/turn-on", "/back-office/let-in"):
        status, headers, _ = ask(port, "POST", path, admin, {"email": "waiting@example.com"})
        assert status == 303
        where = headers["location"]
        assert where.startswith("/back-office/waitlist?said="), where
        assert "waiting" not in where and "%40" not in where and "@" not in where, where
    status, headers, _ = ask(port, "POST", "/back-office/resend", admin, {"email": "x@example.com"})
    assert "%40" not in headers["location"] and "example" not in headers["location"]
    assert store.waiting_state("waiting@example.com") == "on"


def test_a_said_is_cut_of_any_address_before_it_rides() -> None:
    cut = serve.EMAIL_IN_TEXT.sub
    assert cut("the address", "Could not write: 550 <a.b+c@example.co.il> refused") == (
        "Could not write: 550 <the address> refused"
    )
    assert cut("the address", "Let 3 in.") == "Let 3 in."


def test_the_searches_are_named_so_the_log_can_drop_them(world) -> None:  # type: ignore[no-untyped-def]
    """`?q=` put a reader's address in targum.log on every search. The names are `bq`
    and `bwq` now, and both are found by the page they search."""
    port, _, _, admin, _ = world
    readers = ask(port, "GET", "/back-office/readers?bq=reader%40example", admin)[2]
    assert 'name="bq" value="reader@example"' in readers and "reader@example.com" in readers
    assert "ops@example.com" not in readers[readers.index("<h2>Readers") :]
    # The old name searches nothing.
    old = ask(port, "GET", "/back-office/readers?q=reader%40example", admin)[2]
    assert 'name="bq" value=""' in old
    waitlist = ask(port, "GET", "/back-office/waitlist?bwq=waiting", admin)[2]
    assert 'name="bwq" value="waiting"' in waitlist and "waiting@example.com" in waitlist
    template = (ROOT / "src" / "targum" / "render" / "templates" / "backoffice.html.j2").read_text()
    for name in re.findall(r'name="([a-z]+)"', template):
        assert name not in ("q", "wq"), name


def test_the_log_filter_deletes_them() -> None:
    """`deploy.sh` does not ship the Caddyfile, so David applies this once; the file is
    still where it is written down, and both names' logs drop all three."""
    caddyfile = (ROOT / "deploy" / "Caddyfile").read_text()
    filters = re.findall(r"request>uri query \{(.*?)\}", caddyfile, re.S)
    assert len(filters) == 2, "targum.page's log and the back office's"
    for kept in filters:
        deleted = set(re.findall(r"delete (\w+)", kept))
        assert {"t", "k", backoffice.ACCOUNT_SEARCH, backoffice.WAITING_SEARCH, "said"} <= deleted
        assert {"q", "wq"} <= deleted, "the old names, for a bookmark that still has them"


def test_one_route_said_in_two_places() -> None:
    assert serve.BACK_OFFICE_ROUTE == backoffice.ROUTE
    assert backoffice.page_route("overview") == "/back-office"
    assert backoffice.page_route("shelf") == "/back-office/shelf"


#: How a press from somewhere else announces itself: another site, a sibling name under
#: the same domain (the same site, so SameSite=Lax sends the cookie), and an old browser
#: that names only its `Origin`.
ELSEWHERE = [
    {"Sec-Fetch-Site": "cross-site"},
    {"Sec-Fetch-Site": "same-site", "Origin": "https://x.targum.page"},
    {"Origin": "https://evil.example"},
    # An old browser's sandboxed frame says `null` and sends no `Sec-Fetch-Site`
    # (qa on targum#1308).
    {"Origin": "null"},
]


def test_a_press_from_anywhere_but_our_own_page_is_refused(world) -> None:  # type: ignore[no-untyped-def]
    """qa on targum#1308: SameSite=Lax sends the admin's cookie with a form posted from
    any name under the same domain. Every press is refused 403 unless it comes from the
    same origin, before the body is read, and changes nothing."""
    port, store, _, admin, _ = world
    store.fault(None, "TypeError: boom", "", "/texts")
    store.tell(None, "please fix")
    for path, fields in POSTS.items():
        for headers in ELSEWHERE:
            status, answer, _ = ask(port, "POST", path, admin, fields, sent=headers)
            assert status == 403, (path, headers, status)
            assert "location" not in answer
    assert store.waiting_state("waiting@example.com") == "on"
    assert store.balances() == {}
    assert store.told()[0]["state"] == "open"
    assert store.faults()[0]["fixed"] == 0
    # Our own page's post goes through: the browser says same-origin, and under
    # no-referrer its `Origin` is `null`; and so does one with neither header (curl).
    for headers in ({"Sec-Fetch-Site": "same-origin", "Origin": "null"}, {}):
        status, answer, _ = ask(
            port, "POST", "/back-office/balance", admin, POSTS["/back-office/balance"], sent=headers
        )
        assert status == 303 and answer["location"] == "/back-office/operations#services"


def test_what_went_wrong_goes_to_incidents_and_not_into_the_address() -> None:
    """qa on targum#1308: an error's own words, a mail server's or the shelf's, never ride
    in `said`; the page says it did not go through and Incidents says why."""
    text = (ROOT / "src" / "targum" / "serve.py").read_text(encoding="utf-8")
    presses = text[text.index("    def _open_the_door(") : text.index("    def do_GET(")]
    assert "str(error)" not in presses and "row.failed}" not in presses
    assert "error.message" not in presses and "error.hint" not in presses
    trouble = text[text.index("def _back_office_trouble(") : text.index("def _behind_the_door(")]
    assert "incidents_module.record(" in trouble
