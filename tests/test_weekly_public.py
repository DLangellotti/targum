"""The weekly, as a stranger meets it.

Its routes are variable paths, so they cannot be named in the exact-match
`OPEN_TO_STRANGERS` and have to return before `_needs_account` is ever consulted. That
is easy to get subtly wrong and impossible to see from a unit test, so these run against
a real server started the way the deployment starts it.
"""

from __future__ import annotations

import re
import shutil
import threading
import time
from collections.abc import Callable
from http.client import HTTPConnection
from pathlib import Path

import pytest

from targum import serve
from targum.accounts import Store

PUBLIC = "https://targum.page"
HOST = "targum.page"
FIXTURES = Path(__file__).parent / "fixtures"
WEEK = "2026-w36"

#: The module-scoped server's session and database, so the handful of tests that need to
#: reach past the routes can, without every other test unpacking something it never uses.
SESSION: list[str] = []
STORE: list[Path] = []


@pytest.fixture(scope="module")
def weekly_server(
    tmp_path_factory: pytest.TempPathFactory, free_port: Callable[[], int]
) -> tuple[int, Path]:
    tmp = tmp_path_factory.mktemp("weekly-hosted")
    out = tmp / "out"
    out.mkdir()
    shutil.copytree(FIXTURES / "weekly", out / "weekly")
    store_path = tmp / "targum.db"
    store = Store(store_path)
    signed = store.finish_sign_in(store.start_sign_in("reader@example.com"))
    assert signed is not None
    SESSION.append(signed[1])
    STORE.append(store_path)
    port = free_port()

    threading.Thread(
        target=lambda: serve.start(
            out=out,
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
    return port, out / "weekly"


@pytest.fixture
def open_shelves(
    weekly_server: tuple[int, Path], monkeypatch: pytest.MonkeyPatch
) -> tuple[int, Path]:
    """The server's own weekly, named for this test too.

    The suite's isolation fixture points every test at an empty directory, so this puts
    it back to the one the server was started over — a request and the assertion about
    it have to be looking at the same issues.
    """
    from targum.weekly import index

    port, weekly_dir = weekly_server
    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "1")
    monkeypatch.setenv("TARGUM_WEEKLY_DIR", str(weekly_dir))
    monkeypatch.setattr(index, "_cached", None)
    return port, weekly_dir


def post(
    port: int, path: str, form: str = "", session: str = "", json_body: str = ""
) -> tuple[int, bytes]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("POST", path, skip_host=True)
    conn.putheader("Host", HOST)
    body = (json_body or form).encode()
    kind = "application/json" if json_body else "application/x-www-form-urlencoded"
    conn.putheader("Content-Type", kind)
    conn.putheader("Content-Length", str(len(body)))
    if session:
        conn.putheader("Cookie", f"targum_session={session}")
    conn.endheaders()
    conn.send(body)
    response = conn.getresponse()
    read = response.read()
    conn.close()
    return response.status, read


def _headers(port: int, path: str) -> dict[str, str]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("GET", path, skip_host=True)
    conn.putheader("Host", HOST)
    conn.endheaders()
    response = conn.getresponse()
    response.read()
    found = {name.lower(): value for name, value in response.getheaders()}
    conn.close()
    return found


def ask(port: int, path: str) -> tuple[int, bytes, str]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    conn.putrequest("GET", path, skip_host=True)
    conn.putheader("Host", HOST)
    conn.endheaders()
    response = conn.getresponse()
    body = response.read()
    location = response.getheader("Location") or ""
    conn.close()
    return response.status, body, location


# -- reaching it at all --------------------------------------------------------------


def test_a_stranger_can_read_an_issue(open_shelves: tuple[int, Path]) -> None:
    """Signed out, with no account and no invitation. This is the first thing targum
    has that somebody can read rather than read about."""
    port, _ = open_shelves
    status, body, _ = ask(port, f"/weekly/{WEEK}/bet")
    assert status == 200
    page = body.decode()
    assert "השבוע בעברית" in page
    assert "ועדה ציבורית" in page, "the Hebrew is given whole"


def test_the_bare_address_lands_on_the_newest_issue(open_shelves: tuple[int, Path]) -> None:
    port, _ = open_shelves
    status, _, where = ask(port, "/weekly")
    assert status == 303
    assert where == f"/weekly/{WEEK}/bet"


def test_an_issue_without_a_level_is_sent_to_the_middle_one(
    open_shelves: tuple[int, Path],
) -> None:
    """The one most readers can read, with the other two a click either side."""
    port, _ = open_shelves
    status, _, where = ask(port, f"/weekly/{WEEK}")
    assert status == 303
    assert where == f"/weekly/{WEEK}/bet"


@pytest.mark.parametrize("level", ["aleph", "bet", "gimel"])
def test_every_level_answers(open_shelves: tuple[int, Path], level: str) -> None:
    port, _ = open_shelves
    assert ask(port, f"/weekly/{WEEK}/{level}")[0] == 200


@pytest.mark.parametrize(
    "path",
    [f"/weekly/{WEEK}/dalet", "/weekly/1999-w01/bet", f"/weekly/{WEEK}/bet/extra"],
)
def test_nonsense_is_a_flat_404(open_shelves: tuple[int, Path], path: str) -> None:
    port, _ = open_shelves
    assert ask(port, path)[0] == 404


def test_a_draft_is_not_reachable_and_is_not_announced(open_shelves: tuple[int, Path]) -> None:
    """On disk and not published is, from out here, the same as not existing. Saying
    "not yet" would be telling a stranger what is coming."""
    port, _ = open_shelves
    status, body, _ = ask(port, "/weekly/2026-w37/bet")
    assert status == 404
    assert b"2026-w37" not in ask(port, "/sitemap.xml")[1]


def test_the_weekly_is_shut_with_the_shelves(
    weekly_server: tuple[int, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """One switch, not two. Two is a state nobody tests.

    Shut, the route falls through to the door rather than to an error — which answers
    200, like every other closed page here. What matters is that the issue is not in it.
    """
    port, _ = weekly_server
    monkeypatch.delenv("TARGUM_PUBLIC_SHELVES", raising=False)
    _, body, _ = ask(port, f"/weekly/{WEEK}/bet")
    page = body.decode()
    assert "ועדה ציבורית" not in page, "the Hebrew is not served with the shelves shut"
    assert "Compiled by a model" not in page
    assert "sign in" in page.lower() or "invitation" in page.lower()


# -- the catalogue id still works ----------------------------------------------------


def test_the_catalogue_id_is_moved_rather_than_broken(open_shelves: tuple[int, Path]) -> None:
    """An edition is a catalogue entry, so `/library/<id>` answers — but two URLs for
    one page is a duplicate a search engine has to guess between, and a link somebody
    already wrote down should not die."""
    port, _ = open_shelves
    status, _, where = ask(port, f"/library/weekly-{WEEK}-gimel")
    assert status == 301
    assert where == f"/weekly/{WEEK}/gimel"


def test_a_draft_id_is_not_redirected_to_nothing(open_shelves: tuple[int, Path]) -> None:
    port, _ = open_shelves
    assert ask(port, "/library/weekly-2026-w37-bet")[0] == 404


# -- what a crawler is told -----------------------------------------------------------


def test_the_weekly_is_in_robots_and_the_sitemap_when_indexed(
    open_shelves: tuple[int, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_INDEX_WEEKLY", "1")
    port, _ = open_shelves
    assert b"Allow: /weekly" in ask(port, "/robots.txt")[1]

    found = re.findall(r"<loc>(.*?)</loc>", ask(port, "/sitemap.xml")[1].decode())
    paths = {url.removeprefix(PUBLIC) for url in found}
    for level in ("aleph", "bet", "gimel"):
        assert f"/weekly/{WEEK}/{level}" in paths
    assert f"/library/weekly-{WEEK}-bet" not in paths, "the redirecting address, not the page"


# -- what the page says ---------------------------------------------------------------


def test_the_page_says_how_it_was_made_before_anything_it_made(
    open_shelves: tuple[int, Path],
) -> None:
    """Not a badge and not a footnote — a line of type, above the article."""
    page = ask(open_shelves[0], f"/weekly/{WEEK}/bet")[1].decode()
    assert "Compiled by a model" in page
    assert "curated by the targum team" in page


def test_the_page_names_its_sources(open_shelves: tuple[int, Path]) -> None:
    """How a licence obligation gets discharged by code rather than by memory."""
    page = ask(open_shelves[0], f"/weekly/{WEEK}/bet")[1].decode()
    assert "kan, globes" in page
    assert "State of Israel, free use" in page


def test_the_page_embeds_the_reader_rather_than_linking_to_it(
    open_shelves: tuple[int, Path],
) -> None:
    """A link away is a decision somebody has to make before they have been shown
    anything, and a stranger makes that decision by leaving. The first thing under the
    headline is the product running.

    The page carries a level switcher of its own, above the frame. For a while it did
    not — two controls doing one thing, with only one of them able to know which level
    is showing, is a way to be wrong on screen — but on a phone the reader's own switch
    went behind ⋯, and the page can know: the frame is the same origin and `weekly.js`
    reads where it has gone on every load (see the browser test below).
    """
    page = ask(open_shelves[0], f"/weekly/{WEEK}/bet")[1].decode()
    assert "<iframe" in page
    assert f"/weekly/read/weekly-{WEEK}-bet-he/reader/index.html" in page
    assert "Learn to read the news in Hebrew" in page
    for level in ("aleph", "bet", "gimel"):
        assert f'href="/weekly/{WEEK}/{level}" data-level="{level}"' in page, level
    assert 'data-level="bet"\n       data-what=' in page or 'data-level="bet"' in page
    assert re.search(r'data-level="bet"[^>]*class="here" aria-current="page"', page)
    assert not re.search(r'data-level="aleph"[^>]*aria-current', page)


def test_the_page_keeps_step_with_the_level_the_frame_is_showing(
    open_shelves: tuple[int, Path],
) -> None:
    """Switch level inside the framed reader and the page's own switcher, the sentence
    under it and the address all follow — the answer to the objection that two controls
    for one thing will disagree."""
    playwright_api = pytest.importorskip("playwright.sync_api")
    port = open_shelves[0]
    with playwright_api.sync_playwright() as driver:
        try:
            browser = driver.chromium.launch()
        except Exception as why:  # pragma: no cover - the browser itself is not installed
            pytest.skip(f"no Chromium ({why})")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(f"http://127.0.0.1:{port}/weekly/{WEEK}/bet")
        page.wait_for_selector(".ladder a.here")
        # The fixture's readers are stubs with no bar, so the frame is sent where the
        # bar's own level link would send it: the same navigation, the same `load`.
        page.evaluate(
            "(to) => { document.querySelector('.embed iframe').src = to; }",
            f"/weekly/read/weekly-{WEEK}-aleph-he/reader/index.html",
        )
        page.wait_for_function(
            "() => document.querySelector('.ladder a.here').getAttribute('data-level') === 'aleph'"
        )
        assert page.url.endswith(f"/weekly/{WEEK}/aleph")
        said = page.inner_text("#ladder-what")
        wanted = page.get_attribute('.ladder a[data-level="aleph"]', "data-what")
        assert said == wanted
        browser.close()


def test_the_page_is_canonical_to_itself(open_shelves: tuple[int, Path]) -> None:
    """The three levels are different Hebrew, not near-duplicates of one page."""
    page = ask(open_shelves[0], f"/weekly/{WEEK}/gimel")[1].decode()
    assert f'<link rel="canonical" href="{PUBLIC}/weekly/{WEEK}/gimel">' in page


def test_the_page_leaks_no_route_that_needs_an_account(open_shelves: tuple[int, Path]) -> None:
    """The same rule `test_public` holds every other public page to."""
    page = ask(open_shelves[0], f"/weekly/{WEEK}/bet")[1].decode()
    for private in ("/progress", "/readers", "/job/", "/glossary/"):
        assert private not in page, private
    # As an href, not as a substring: the public reader lives at
    # `/weekly/read/<edition>/reader/<file>`, which contains "/reader/" and needs no
    # account. What must never appear is a link to the private route itself.
    assert '"/reader/' not in page, "the private reader route"
    assert "/account/signin" in page, "the door is the one way in it may offer"


def test_the_page_carries_what_a_search_engine_needs(open_shelves: tuple[int, Path]) -> None:
    page = ask(open_shelves[0], f"/weekly/{WEEK}/bet")[1].decode()
    assert "<title>" in page
    description = re.search(r'<meta name="description" content="([^"]*)"', page)
    assert description is not None and len(description.group(1)) > 20
    assert 'property="og:title"' in page
    assert 'lang="he" dir="rtl"' in page


# -- being told when a new issue is out ------------------------------------------------


def _store() -> Store:
    return Store(STORE[0])


def test_a_stranger_can_ask_for_the_weekly(open_shelves: tuple[int, Path]) -> None:
    """No account, no invitation. Somebody who reads an issue signed out is not going to
    open an account to be told when the next one is out."""
    port, _ = open_shelves
    status, body = post(port, "/weekly/subscribe", "email=stranger@example.com")
    assert status == 200
    assert b"Check your email" in body

    store = _store()
    assert (
        store.db.execute(
            "SELECT COUNT(*) AS n FROM subscriber WHERE email = ?", ("stranger@example.com",)
        ).fetchone()["n"]
        == 1
    )
    assert not store.may_join("stranger@example.com"), "not an invitation"


def test_the_answer_is_the_same_whatever_the_address_is(open_shelves: tuple[int, Path]) -> None:
    """An endpoint that answered differently would be a way to ask whether somebody is a
    reader here — the same reason asking for a sign-in link says one thing."""
    port, _ = open_shelves
    already = post(port, "/weekly/subscribe", "email=known@example.com")[1]
    again = post(port, "/weekly/subscribe", "email=nobody-at-all@example.com")[1]
    assert b"Check your email" in already and b"Check your email" in again


def test_a_nonsense_address_is_refused_before_anything_is_sent(
    open_shelves: tuple[int, Path],
) -> None:
    port, _ = open_shelves
    status, body = post(port, "/weekly/subscribe", "email=not-an-address")
    assert status != 200 or b"does not look like" in body


def test_confirming_needs_a_press_and_not_a_fetch(open_shelves: tuple[int, Path]) -> None:
    """A mail client that fetches every link in a message must not answer for the
    person it was sent to. Same ruling as the sign-in door."""
    port, _ = open_shelves
    store = _store()
    token = store.subscribe("press@example.com")
    assert token is not None

    status, body, _ = ask(port, f"/weekly/confirm?t={token}")
    assert status == 200
    assert b"press@example.com" in body and b"<form" in body
    assert not store.following("press@example.com"), "fetching it did not spend it"

    assert post(port, "/weekly/confirm", f"t={token}")[0] == 200
    assert store.following("press@example.com")


def test_stopping_is_one_press_from_an_email(open_shelves: tuple[int, Path]) -> None:
    port, _ = open_shelves
    store = _store()
    store.follow("leaving@example.com")
    row = store.db.execute(
        "SELECT stop FROM subscriber WHERE email = ?", ("leaving@example.com",)
    ).fetchone()

    status, body, _ = ask(port, f"/weekly/stop?t={row['stop']}")
    assert status == 200 and b"<form" in body
    assert store.following("leaving@example.com"), "the page alone does not stop it"

    assert post(port, "/weekly/stop", f"t={row['stop']}")[0] == 200
    assert not store.following("leaving@example.com")


def test_the_doors_work_with_no_javascript(open_shelves: tuple[int, Path]) -> None:
    """Two of the three are followed out of an email client, where JavaScript is not a
    thing that exists."""
    port, _ = open_shelves
    store = _store()
    token = store.subscribe("plain@example.com")
    page = ask(port, f"/weekly/confirm?t={token}")[1].decode()
    assert '<form class="door" method="post"' in page
    assert 'name="t"' in page


def test_a_signed_in_reader_subscribes_with_one_press(open_shelves: tuple[int, Path]) -> None:
    """They proved they control the address by following a link to get in. Mailing them
    to ask would be asking them to confirm what they confirmed at the door."""
    port, _ = open_shelves
    status, body = post(port, "/weekly/follow", session=SESSION[0], json_body='{"on": true}')
    assert status == 200
    assert b'"following": true' in body.replace(b'"following":true', b'"following": true')
    assert _store().following("reader@example.com")


def test_the_signed_in_door_ignores_an_address_in_the_body(
    open_shelves: tuple[int, Path],
) -> None:
    """It reads the session's own address and nothing else. With nothing to supply there
    is no way to sign somebody else's inbox up, which is a shorter argument than any
    amount of checking one."""
    port, _ = open_shelves
    post(
        port,
        "/weekly/follow",
        session=SESSION[0],
        json_body='{"on": true, "email": "victim@example.com"}',
    )
    store = _store()
    assert store.following("reader@example.com")
    assert not store.following("victim@example.com")
    assert (
        store.db.execute(
            "SELECT COUNT(*) AS n FROM subscriber WHERE email = ?", ("victim@example.com",)
        ).fetchone()["n"]
        == 0
    )


def test_signed_out_cannot_use_the_signed_in_door(open_shelves: tuple[int, Path]) -> None:
    port, _ = open_shelves
    assert post(port, "/weekly/follow", json_body='{"on": true}')[0] in {401, 403}


# -- the ask -----------------------------------------------------------------------


def test_the_page_can_be_subscribed_to_without_javascript(
    open_shelves: tuple[int, Path],
) -> None:
    """Somebody arrives from a search result and may have JavaScript off, blocked, or
    still loading. The form is a real form either way."""
    page = ask(open_shelves[0], f"/weekly/{WEEK}/bet")[1].decode()
    assert '<form method="post" action="/weekly/subscribe">' in page
    assert 'name="email"' in page


def test_the_dialog_carries_the_same_form(open_shelves: tuple[int, Path]) -> None:
    """So that if it opens and its script then fails, the ask still works."""
    page = ask(open_shelves[0], f"/weekly/{WEEK}/bet")[1].decode()
    assert page.count('action="/weekly/subscribe"') == 2
    assert "<dialog" in page


def test_the_page_still_offers_only_the_one_door(open_shelves: tuple[int, Path]) -> None:
    """Adding a dialog must not have added a route that needs an account."""
    page = ask(open_shelves[0], f"/weekly/{WEEK}/bet")[1].decode()
    for private in ("/progress", "/readers", "/job/", "/glossary/"):
        assert private not in page, private
    assert '"/reader/' not in page, "the private reader route"


# -- the reader itself, for a stranger -------------------------------------------------


def _reader(port: int, folder: str, name: str = "index.html") -> tuple[int, bytes, str]:
    return ask(port, f"/weekly/read/{folder}/reader/{name}")


def test_a_stranger_gets_the_whole_reader(open_shelves: tuple[int, Path]) -> None:
    """Not a page about the product: the product. The built reader is self-contained —
    its meanings, its vowel points and its word list are all baked in — so handing it to
    somebody with no account gives away nothing that the prose page did not, and gives
    them the one thing they cannot be told about."""
    port, weekly_dir = open_shelves
    built = weekly_dir / "weekly-2026-w36-bet-he" / "reader"
    built.mkdir(parents=True, exist_ok=True)
    (built / "index.html").write_text("<!doctype html><p>contents", encoding="utf-8")
    (built / "sec-0002.html").write_text("<!doctype html><p>ישראל", encoding="utf-8")

    assert _reader(port, "weekly-2026-w36-bet-he")[0] == 200
    assert _reader(port, "weekly-2026-w36-bet-he", "sec-0002.html")[0] == 200


def test_only_a_published_edition_is_served(open_shelves: tuple[int, Path]) -> None:
    """A draft is on disk and is not published, which from out here is the same thing as
    not existing."""
    port, weekly_dir = open_shelves
    built = weekly_dir / "weekly-2026-w37-bet-he" / "reader"
    built.mkdir(parents=True, exist_ok=True)
    (built / "index.html").write_text("<!doctype html><p>draft", encoding="utf-8")

    assert _reader(port, "weekly-2026-w37-bet-he")[0] == 404


@pytest.mark.parametrize("folder", ["shared", "..", "../shared", "weekly-2026-w99-bet-he", "local"])
def test_the_reader_route_reaches_nothing_else(open_shelves: tuple[int, Path], folder: str) -> None:
    """It answers for editions of published issues and for nothing else. A person's own
    home and the shared one are served by a different branch entirely, and this one
    never learns their names."""
    port, _ = open_shelves
    assert _reader(port, folder)[0] != 200


def test_a_file_outside_the_edition_is_not_reachable(open_shelves: tuple[int, Path]) -> None:
    port, weekly_dir = open_shelves
    (weekly_dir / "secret.html").write_text("<!doctype html><p>no", encoding="utf-8")
    built = weekly_dir / "weekly-2026-w36-bet-he" / "reader"
    built.mkdir(parents=True, exist_ok=True)
    (built / "index.html").write_text("<!doctype html>", encoding="utf-8")

    for name in ("../../secret.html", "..%2F..%2Fsecret.html", "../document.json"):
        assert ask(port, f"/weekly/read/weekly-2026-w36-bet-he/reader/{name}")[0] != 200


def test_the_reader_is_shut_with_the_shelves(
    weekly_server: tuple[int, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """One switch for the whole public surface, the reader included."""
    port, weekly_dir = weekly_server
    built = weekly_dir / "weekly-2026-w36-bet-he" / "reader"
    built.mkdir(parents=True, exist_ok=True)
    (built / "index.html").write_text("<!doctype html><p>ONLY-IN-THE-READER", encoding="utf-8")
    monkeypatch.delenv("TARGUM_PUBLIC_SHELVES", raising=False)

    assert b"ONLY-IN-THE-READER" not in _reader(port, "weekly-2026-w36-bet-he")[1]


def test_the_issue_page_sends_a_reader_into_it(open_shelves: tuple[int, Path]) -> None:
    """The door on the public page goes into the reading, not to the sign-in form. What
    makes this worth an account is a thing a stranger can only be told about until they
    have done it once."""
    page = ask(open_shelves[0], f"/weekly/{WEEK}/bet")[1].decode()
    # One file. An issue is not a book: five short sections that add up to a
    # twenty-minute read, and splitting them gave a stranger a contents page and five
    # clicks before any Hebrew.
    assert "/weekly/read/weekly-2026-w36-bet-he/reader/index.html" in page
    assert "sec-0001.html" not in page, "the weekly is one targum, not chapters"


def test_the_two_policies_let_the_frame_work(open_shelves: tuple[int, Path]) -> None:
    """Both directions, and same-origin only.

    `default-src 'none'` refuses an iframe outright, and every other page here carries
    `frame-ancestors 'none'`, so the reader would refuse to be framed at all. The
    landing page may frame targum and the reader may be framed by targum; `'self'` is
    not `'*'`, so the clickjacking guard every other page gets is kept exactly.
    """
    port, weekly_dir = open_shelves
    built = weekly_dir / "weekly-2026-w36-bet-he" / "reader"
    built.mkdir(parents=True, exist_ok=True)
    (built / "index.html").write_text("<!doctype html><p>ישראל", encoding="utf-8")

    landing = _headers(port, f"/weekly/{WEEK}/bet")["content-security-policy"]
    assert "frame-src 'self'" in landing
    assert "frame-ancestors 'none'" in landing, "the landing page itself stays unframeable"

    framed = _headers(port, "/weekly/read/weekly-2026-w36-bet-he/reader/index.html")
    policy = framed["content-security-policy"]
    assert "frame-ancestors 'self'" in policy
    assert "frame-ancestors 'none'" not in policy


def test_an_ordinary_public_page_is_still_unframeable(open_shelves: tuple[int, Path]) -> None:
    """The relaxation is for the weekly's two pages and nothing else."""
    policy = _headers(open_shelves[0], "/library")["content-security-policy"]
    assert "frame-ancestors 'none'" in policy
    assert "frame-src" not in policy


# -- the sources, and the way into them -----------------------------------------------


def test_each_source_links_to_the_article(open_shelves: tuple[int, Path]) -> None:
    """A citation nobody can follow is not a citation, and the outlet that did the
    reporting should get the visit."""
    page = ask(open_shelves[0], f"/weekly/{WEEK}/bet")[1].decode()
    assert 'href="https://www.ynet.co.il/example"' in page
    assert 'href="https://www.gov.il/example"' in page


def test_an_outbound_link_hands_nothing_over(open_shelves: tuple[int, Path]) -> None:
    """These addresses arrive from somebody else's feed. The tab that opens gets no
    handle back on this one, and the link passes on no ranking."""
    page = ask(open_shelves[0], f"/weekly/{WEEK}/bet")[1].decode()
    for story in ("https://www.ynet.co.il/example", "https://www.gov.il/example"):
        before = page[: page.index(f'href="{story}"')]
        opening = before.rindex("<a ")
        assert 'rel="noopener noreferrer nofollow"' in page[opening : page.index(story) + 200]


def test_a_source_can_be_taken_as_your_own_targum(open_shelves: tuple[int, Path]) -> None:
    """Their account, their spend, their shelf — exactly as pasting the link into Add.
    Signed out it meets the door first, which is the point: somebody who wants a whole
    article is further along than somebody who wants a digest."""
    page = ask(open_shelves[0], f"/weekly/{WEEK}/bet")[1].decode()
    # Jinja's urlencode leaves slashes alone, which is legal in a query value and what
    # `URLSearchParams` decodes back to the address the reader clicked.
    assert "/add?source=https%3A//www.ynet.co.il/example" in page
    assert "Read the whole thing" in page


def test_a_link_that_is_not_a_link_never_reaches_the_page() -> None:
    """A `javascript:` address in a feed would be a script targum served to its own
    visitors. Refused at the edge where the value enters, once."""
    from targum.weekly.models import Part, Story

    facts = pytest.importorskip("targum.weekly.facts")
    for bad in ("javascript:alert(1)", "data:text/html,<script>", "file:///etc/passwd"):
        assert facts.canonical(bad) == ""

    # And a story built from one carries no link, so no template can render one.
    story = Story(section=Part.israel, headline="x", links=[facts.canonical("javascript:1")])
    assert story.links == [""], "nothing a template would render as an address"


# -- published is not the same as readable --------------------------------------------


def test_an_issue_with_no_reader_is_not_offered(
    weekly_server: tuple[int, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The index says an issue is published; the built reader is what makes it readable,
    and the two can disagree — a half-finished copy to the box, or a publish that ran
    before a build.

    The page is a frame around the reader, so a level with no reader on disk served a
    200 whose middle was a browser error. Not found is the honest answer.
    """
    from targum.weekly import index

    port, _ = weekly_server
    bare = Path(str(weekly_server[1])).parent / "bare-weekly"
    bare.mkdir(exist_ok=True)
    (bare / "index.json").write_text(
        (Path(__file__).parent / "fixtures" / "weekly" / "index.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "1")
    monkeypatch.setenv("TARGUM_WEEKLY_DIR", str(bare))
    monkeypatch.setattr(index, "_cached", None)

    assert ask(port, f"/weekly/{WEEK}/bet")[0] == 404
    assert ask(port, "/weekly")[0] == 404


def test_the_front_page_opens_a_level_that_is_there(open_shelves: tuple[int, Path]) -> None:
    """Where the usual level has no reader but another does, the issue still opens —
    at the one that exists, rather than at a page that cannot be read."""
    port, weekly_dir = open_shelves
    for level in ("aleph", "gimel"):
        built = weekly_dir / f"weekly-{WEEK}-{level}-he" / "reader"
        built.mkdir(parents=True, exist_ok=True)
        (built / "index.html").write_text("<!doctype html><p>ישראל", encoding="utf-8")

    # The usual level is the one taken away, so the fallback has to choose another.
    import shutil

    shutil.rmtree(weekly_dir / f"weekly-{WEEK}-bet-he" / "reader", ignore_errors=True)
    try:
        status, _, where = ask(port, "/weekly")
        assert status == 303
        assert where.endswith(f"/weekly/{WEEK}/aleph"), where
    finally:
        built = weekly_dir / f"weekly-{WEEK}-bet-he" / "reader"
        built.mkdir(parents=True, exist_ok=True)
        (built / "index.html").write_text("<!doctype html><p>ישראל", encoding="utf-8")


def test_nothing_offers_an_issue_whose_reader_never_arrived(
    weekly_server: tuple[int, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Published and readable are different facts, and every surface has to agree.

    Fixing the landing page alone left four other places offering it: the redirect from
    a week with no level, the 301 from a catalogue id, three dead URLs in the sitemap,
    and three rows on the shelf. A row that leads to a 404 is worse than a row that is
    not there yet, and a sitemap of dead links is worse than a small one.
    """
    from targum.weekly import index

    port, weekly_dir = weekly_server
    bare = weekly_dir.parent / "unbuilt-weekly"
    bare.mkdir(exist_ok=True)
    (bare / "index.json").write_text(
        (FIXTURES / "weekly" / "index.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "1")
    monkeypatch.setenv("TARGUM_WEEKLY_DIR", str(bare))
    monkeypatch.setattr(index, "_cached", None)

    for path in (
        "/weekly",
        f"/weekly/{WEEK}",
        f"/weekly/{WEEK}/bet",
        f"/library/weekly-{WEEK}-bet",
        f"/weekly/read/weekly-{WEEK}-bet-he/reader/index.html",
    ):
        assert ask(port, path)[0] == 404, path

    assert b"/weekly" not in ask(port, "/sitemap.xml")[1]
    assert f"weekly-{WEEK}".encode() not in ask(port, "/library")[1]


# -- a weekly with a past --------------------------------------------------------------
#
# Everything above was written against a single issue, which is the one week the weekly
# is not weekly. The archive, choosing between issues, and telling one from another in a
# mailout only exist from the second Monday.


def test_the_front_page_opens_the_newest_issue(open_shelves: tuple[int, Path]) -> None:
    """Newest by the Monday it belongs to, not by the order the index happens to hold —
    an issue drafted late and published out of order is an ordinary thing."""
    port, _ = open_shelves
    status, _, where = ask(port, "/weekly")
    assert status == 303
    assert f"/weekly/{WEEK}/" in where, where
    assert "2026-w35" not in where, "the older issue is not the front page"


def test_an_older_issue_is_still_readable(open_shelves: tuple[int, Path]) -> None:
    """The archive is not decoration. A reader who missed a week can still have it."""
    port, _ = open_shelves
    assert ask(port, "/weekly/2026-w35/bet")[0] == 200
    assert ask(port, "/weekly/read/weekly-2026-w35-bet-he/reader/index.html")[0] == 200


def test_the_page_offers_the_weeks_before_it(open_shelves: tuple[int, Path]) -> None:
    """And never itself: an archive listing the issue you are reading is a link that
    goes nowhere you are not."""
    page = ask(open_shelves[0], f"/weekly/{WEEK}/bet")[1].decode()
    archive = page.split('class="archive"', 1)[1]
    assert "/weekly/2026-w35/" in archive
    # The level switcher above the frame does link this issue — at every level, this
    # one included — so the rule is asked of the archive alone.
    assert f'href="/weekly/{WEEK}/' not in archive


def test_the_sitemap_carries_every_issue_once_indexing_is_invited(
    open_shelves: tuple[int, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_INDEX_WEEKLY", "1")
    found = re.findall(r"<loc>(.*?)</loc>", ask(open_shelves[0], "/sitemap.xml")[1].decode())
    paths = {url.removeprefix(PUBLIC) for url in found}
    for week in (WEEK, "2026-w35"):
        for level in ("aleph", "bet", "gimel"):
            assert f"/weekly/{week}/{level}" in paths, f"{week}/{level}"


def test_until_then_the_weekly_is_reachable_and_unindexed(open_shelves: tuple[int, Path]) -> None:
    """Public and indexed are different facts, and the default is the careful one.

    Anyone with the address reads the issue; no search engine is invited to surface it.
    The instruction is the noindex header on the page itself rather than robots.txt,
    because a crawler barred by robots never fetches the page and never sees the header —
    and a URL learned elsewhere can be indexed bare.
    """
    port, _ = open_shelves
    body = ask(port, "/sitemap.xml")[1].decode()
    assert "/weekly" not in body, "the sitemap does not name what noindex disavows"
    for path in (f"/weekly/{WEEK}/bet", f"/weekly/read/weekly-{WEEK}-bet-he/reader/index.html"):
        assert _headers(port, path).get("x-robots-tag") == "noindex", path
    # The pages themselves still answer: unindexed, not unreachable.
    assert ask(port, f"/weekly/{WEEK}/bet")[0] == 200
    # And the rest of the site is untouched — the library is indexed as before.
    assert _headers(port, "/library").get("x-robots-tag") is None


def test_the_library_holds_every_issue(open_shelves: tuple[int, Path]) -> None:
    """Six rows from two issues, so a reader can find the one they missed by looking
    rather than by knowing its address."""
    page = ask(open_shelves[0], "/library")[1].decode()
    rows = {row for row in re.findall(r"weekly-2026-w3[0-9]-[a-z]+", page)}
    assert len(rows) == 6, sorted(rows)


LOCKED = """
() => ({
  locked: document.body.classList.contains('locked'),
  embed: (() => {
    const r = document.getElementById('embed').getBoundingClientRect();
    return { top: Math.round(r.top), height: Math.round(r.height), width: Math.round(r.width) };
  })(),
  handle: document.getElementById('embed-handle').textContent,
  scrollY: Math.round(window.scrollY),
})
"""


@pytest.mark.parametrize("phone", [True, False], ids=["a phone", "a desktop"])
def test_the_framed_reader_takes_the_screen_and_gives_it_back(
    open_shelves: tuple[int, Path], phone: bool
) -> None:
    """A reader in a slot on a page that scrolls is cramped and fights the page for the
    scroll. So the frame takes the whole window when reading starts in it — a press
    inside, and on a phone scrolling it to the top — and gives it back from the row above
    it or on Escape. Out once, scrolling does not pull you back; a press inside does."""
    playwright_api = pytest.importorskip("playwright.sync_api")
    port = open_shelves[0]
    size = {"width": 390, "height": 844} if phone else {"width": 1280, "height": 800}
    with playwright_api.sync_playwright() as driver:
        try:
            browser = driver.chromium.launch()
        except Exception as why:  # pragma: no cover - the browser itself is not installed
            pytest.skip(f"no Chromium ({why})")
        page = browser.new_page(viewport=size, has_touch=phone, is_mobile=phone)
        page.goto(f"http://127.0.0.1:{port}/weekly/{WEEK}/bet")
        page.wait_for_selector("#embed-handle")
        assert not page.evaluate(LOCKED)["locked"], "at rest, a slot on the page"

        # Scrolling the frame to the top of the window.
        page.evaluate("() => window.scrollTo(0, document.getElementById('embed').offsetTop)")
        page.wait_for_timeout(200)
        seen = page.evaluate(LOCKED)
        if phone:
            assert seen["locked"], "on a phone, scrolling it to the top is starting to read"
            assert seen["embed"] == {"top": 0, "height": 844, "width": 390}, seen
            assert seen["handle"] == "Back to the page"
            page.click("#embed-handle")
            seen = page.evaluate(LOCKED)
            assert not seen["locked"] and seen["handle"] == "Full screen"
            slot = page.evaluate("() => document.getElementById('embed').offsetTop")
            assert abs(seen["scrollY"] - slot) < 4, "the page is back where it was"
            page.evaluate("() => window.scrollBy(0, 30)")
            page.wait_for_timeout(200)
            assert not page.evaluate(LOCKED)["locked"], "out once, scrolling does not pull you back"
        else:
            assert not seen["locked"], "a desktop is not scroll-jacked"

        # A press inside the reader.
        page.frame_locator(".embed iframe").locator("body").dispatch_event("pointerdown")
        page.wait_for_function("() => document.body.classList.contains('locked')")
        seen = page.evaluate(LOCKED)
        assert seen["embed"]["top"] == 0 and seen["embed"]["height"] == size["height"]
        page.keyboard.press("Escape")
        assert not page.evaluate(LOCKED)["locked"], "Escape gives the page back"
        browser.close()
