"""The `/parasha` page and the routes under it.

The corpus is built for real here — one portion, out of a book with a handful of verses
— because the thing under test is the whole path from a URL to a reader on the page, and
a stubbed corpus would not exercise the two gates that keep the reader folder shut.
"""

from __future__ import annotations

import json
import re
import shutil
import threading
from collections.abc import Iterator
from datetime import datetime
from html import unescape
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from test_parasha_cut import a_book

from targum.accounts import Store
from targum.mail import ConsoleMailer
from targum.parasha import build as corpus_build
from targum.parasha import calendar as cal
from targum.parasha.models import Index
from targum.serve import Handler, Library
from targum.vocalize import has_taamim

FIXTURES = Path(__file__).parent / "fixtures" / "parasha"


@pytest.fixture
def built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Index:
    """A corpus with one week's reading really built into a reader."""
    monkeypatch.setenv("TARGUM_PARASHA_DIR", str(tmp_path / "parasha"))
    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "1")
    # The corpus here is one week — Deuteronomy 29–31, Nitzavim-Vayeilech, read on
    # 2026-09-05 — and the routes ask the clock which week it is. Pin the clock inside
    # that week, or these tests pass for seven days and 404 on the eighth, which is what
    # happened on 2026-09-06.
    a_wednesday = datetime(2026, 9, 2, 12, tzinfo=ZoneInfo(cal.FLIP_ZONE))
    monkeypatch.setattr(cal, "now_in_flip_zone", lambda moment=None: a_wednesday)
    (tmp_path / "parasha" / "calendar").mkdir(parents=True)
    for one in FIXTURES.glob("*.json"):
        shutil.copy(one, tmp_path / "parasha" / "calendar" / one.name)
    library = tmp_path / "library"
    a_book(library / "דברים-he", "Deuteronomy", "דברים", {29: 29, 30: 20, 31: 30})
    # And the two haftarot the Deuteronomy readings in the fixture name: Isaiah for
    # Nitzavim-Vayeilech, Habakkuk for the Shavuot Shabbat that displaces a portion.
    a_book(library / "ישעיהו-he", "Isaiah", "ישעיהו", {61: 11, 62: 12, 63: 19})
    a_book(library / "חבקוק-he", "Habakkuk", "חבקוק", {3: 19})
    return corpus_build.build(
        years=[2026],
        # Named, because only 2026 is cached here and the corpus span is nineteen
        # years by default — unnamed, this test would go to Hebcal for eighteen more.
        corpus_years=[2026],
        schedules=[cal.Schedule.diaspora],
        library=library,
    )


@pytest.fixture
def serving(tmp_path: Path, built: Index) -> Iterator[int]:
    out = tmp_path / "targum-out"
    out.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    server.RequestHandlerClass = type(
        "TestHandler",
        (Handler,),
        {
            "library": Library(out),
            "token": "test-key",
            "welcome": "<html>start</html>",
            "shelf": "<html>library</html>",
            "store": Store(tmp_path / "words.db"),
            "mailer": ConsoleMailer(),
            "address": f"http://127.0.0.1:{port}",
        },
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        server.shutdown()
        server.server_close()


def get(port: int, path: str) -> tuple[int, str]:
    conn = HTTPConnection("127.0.0.1", port)
    conn.request("GET", path)
    answer = conn.getresponse()
    body = answer.read().decode("utf-8", "replace")
    conn.close()
    return answer.status, body


def robots_tag(port: int, path: str) -> str | None:
    """What a crawler is told about this page, which is not the same as what it is given."""
    conn = HTTPConnection("127.0.0.1", port)
    conn.request("GET", path)
    answer = conn.getresponse()
    answer.read()
    conn.close()
    return answer.getheader("X-Robots-Tag")


def raw(port: int, path: str) -> int:
    """A request whose path is sent exactly as written, so a dot-dot survives to the
    server instead of being tidied away by the client."""
    import socket

    with socket.create_connection(("127.0.0.1", port)) as sock:
        sock.sendall(
            f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n".encode()
        )
        data = b""
        while chunk := sock.recv(4096):
            data += chunk
    return int(data.split(b" ")[1])


# -- what the corpus build produces ------------------------------------------


def test_the_build_is_free_and_idempotent(built: Index, tmp_path: Path) -> None:
    """Nothing is fetched and nothing is spent, so a rerun is safe to put on a cron."""
    first = (
        tmp_path / "parasha" / "read" / "nitzavim-vayeilech" / "reader" / "sec-0001.html"
    ).read_text(encoding="utf-8")
    again = corpus_build.build(
        corpus_years=[2026],
        years=[2026],
        schedules=[cal.Schedule.diaspora],
        library=tmp_path / "library",
    )
    assert again.portions.keys() == built.portions.keys()
    after = (
        tmp_path / "parasha" / "read" / "nitzavim-vayeilech" / "reader" / "sec-0001.html"
    ).read_text(encoding="utf-8")
    assert after == first


def test_a_festival_shabbat_is_built_as_what_is_actually_read(built: Index) -> None:
    festival = [p for p in built.portions.values() if p.kind is cal.ReadingKind.festival]
    assert festival, "a festival falling on Shabbat displaces the portion"
    assert all(not p.listed(set()) for p in festival), "a festival is not on the shelf"


def test_the_reader_carries_both_forms_of_the_text(built: Index, tmp_path: Path) -> None:
    """The whole point of the two chips: one build, both readings of the same verse.

    Read off a section rather than `index.html`, which is the contents page: a portion is
    built in seven, one per aliyah.
    """
    page = (
        tmp_path / "parasha" / "read" / "nitzavim-vayeilech" / "reader" / "sec-0001.html"
    ).read_text(encoding="utf-8")
    assert 'data-form="pointed"' in page
    assert 'data-form="unaccented"' in page
    assert "data-taamim-toggle" in page


def test_a_book_that_is_not_on_the_shelf_takes_its_readings_and_leaves_the_rest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A build against an empty library is an empty corpus, not a crash — and the book
    is named once rather than once per reading, which would be forty identical lines."""
    monkeypatch.setenv("TARGUM_PARASHA_DIR", str(tmp_path / "parasha"))
    (tmp_path / "parasha" / "calendar").mkdir(parents=True)
    for one in FIXTURES.glob("*.json"):
        shutil.copy(one, tmp_path / "parasha" / "calendar" / one.name)
    said: list[str] = []
    index = corpus_build.build(
        corpus_years=[2026],
        years=[2026],
        schedules=[cal.Schedule.diaspora],
        library=tmp_path / "nothing-here",
        notify=said.append,
    )
    assert index.portions == {}
    assert index.weeks == [], "a week pointing at a portion nobody built points nowhere"
    named = [line for line in said if "is not built" in line]
    assert named, "the missing book is named"
    assert len(named) == len(set(named)), "said once per book, not once per reading"


def test_only_a_folder_with_a_built_reader_counts_as_readable(built: Index, tmp_path: Path) -> None:
    """The gate both routes and the sitemap ask: an index entry is not a built reader,
    and sending somebody to one that is not there is worse than not listing it."""
    reader = tmp_path / "parasha" / "read" / "nitzavim-vayeilech" / "reader" / "index.html"
    assert "nitzavim-vayeilech" in corpus_build.readable(built)
    reader.unlink()
    assert "nitzavim-vayeilech" not in corpus_build.readable(built)


def test_the_unaccented_form_keeps_the_vowels_and_drops_the_accents() -> None:
    """What the second chip actually promises."""
    from targum.vocalize import strip_taamim

    accented = "אַתֶּ֨ם נִצָּבִ֤ים הַיּוֹם֙"
    plain = strip_taamim(accented)
    assert has_taamim(accented)
    assert not has_taamim(plain)
    assert "אַ" in plain, "the vowels stay where they were"


# -- the routes --------------------------------------------------------------


def test_this_weeks_portion_is_served(serving: int) -> None:
    """A page of the desk (design.md §12, "A series is one page of the desk, for
    everyone", 2026-10-09): the app's bar, the series' head and this Shabbat's card."""
    status, body = get(serving, "/parasha")
    assert status == 200
    assert 'class="site-head"' in body, "the app's bar, not the front door's"
    assert "The weekly portion" in body and "This Shabbat" in body
    assert "/parasha/read/" in body, "each aliyah opens its reader"
    assert "sec-0001.html" in body, "the press opens on the first aliyah, not the contents"


def test_any_portion_has_an_address_of_its_own(serving: int) -> None:
    """What makes the corpus a shelf rather than a page that changes: a link to a
    portion keeps working after the week it was this week's."""
    status, body = get(serving, "/parasha/nitzavim-vayeilech")
    assert status == 200
    assert "nitzavim-vayeilech" in body


def test_a_portion_nobody_built_is_not_found(serving: int) -> None:
    assert get(serving, "/parasha/no-such-portion")[0] == 404


def test_the_reader_files_are_served(serving: int) -> None:
    """Both the contents page and the sections it lists."""
    status, body = get(serving, "/parasha/read/nitzavim-vayeilech/reader/index.html")
    assert status == 200
    assert "targum" in body
    status, body = get(serving, "/parasha/read/nitzavim-vayeilech/reader/sec-0001.html")
    assert status == 200
    assert "\u05e8\u05d0\u05e9\u05d5\u05df" in body, "the first section is the first aliyah"


def test_a_reader_folder_nobody_built_is_not_found(serving: int) -> None:
    assert get(serving, "/parasha/read/made-up/reader/index.html")[0] == 404


@pytest.mark.parametrize(
    "path",
    [
        "/parasha/read/../../etc/passwd",
        "/parasha/read/nitzavim-vayeilech/reader/../../../../etc/passwd",
        "/parasha/read/nitzavim-vayeilech/reader/%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    ],
)
def test_a_name_cannot_climb_out_of_the_corpus(serving: int, path: str) -> None:
    """The second gate: the file has to resolve inside the folder it was asked for."""
    assert raw(serving, path) == 404


def test_a_page_of_the_desk_has_no_frame_and_no_teamim_switch(serving: int) -> None:
    """The landing framed the whole reader beside a te'amim switch; the reader has its own
    switch, and a row opens it (design.md §12, 2026-10-09)."""
    status, body = get(serving, "/parasha?taamim=off")
    assert status == 200
    assert "<iframe" not in body.split('<footer class="site-footer">')[0].split("talk-frame")[0]
    assert "data-taamim" not in body


def test_the_page_says_which_schedule_and_only_names_both_when_they_differ(
    serving: int,
) -> None:
    status, body = get(serving, "/parasha?schedule=israel")
    assert status == 200
    # This corpus has only the diaspora built, so asking for Israel must fall back
    # rather than 404: the page still serves a reading.
    assert "/parasha/read/" in body
    assert "This Shabbat" in body


def test_a_schedule_this_box_never_built_falls_back_rather_than_404ing(serving: int) -> None:
    """This corpus was built for the diaspora only. A query string asking for the other
    schedule must not empty the page: the reading that is there is the one to show."""
    status, body = get(serving, "/parasha?schedule=israel")
    assert status == 200
    assert "/parasha/read/" in body, "the reader it does have is still on the page"


def test_a_portions_catalogue_id_leads_to_its_own_page(serving: int) -> None:
    """A portion is a catalogue entry so the library lists it, and two URLs for one text
    is a duplicate a search engine has to choose between. This is which one wins."""
    conn = HTTPConnection("127.0.0.1", serving)
    conn.request("GET", "/library/parasha-nitzavim-vayeilech")
    answer = conn.getresponse()
    answer.read()
    where = answer.headers.get("Location")
    conn.close()
    assert answer.status == 301
    assert where == "/parasha/nitzavim-vayeilech"


def test_a_catalogue_id_naming_a_portion_nobody_built_is_not_redirected(serving: int) -> None:
    """An entry naming a portion that is not built is an entry pointing at a 404, and
    sending a reader there is worse than not listing it."""
    assert get(serving, "/library/parasha-no-such-portion")[0] == 404


def _location(port: int, path: str) -> tuple[int, str | None]:
    conn = HTTPConnection("127.0.0.1", port)
    conn.request("GET", path)
    answer = conn.getresponse()
    answer.read()
    conn.close()
    return answer.status, answer.headers.get("Location")


def test_a_signed_in_reader_opening_a_portions_id_goes_straight_into_its_reader(
    serving: int,
) -> None:
    """targum-internal#410: the portion's reader is built once for the box, so a reader
    who is signed in is sent to it — nothing to build, nothing to spend — and a stranger
    still lands on the public page. A 302, because the answer depends on who asks and a
    browser keeps a 301."""
    status, where = _location(serving, "/library/parasha-nitzavim-vayeilech?k=test-key")
    assert status == 302
    assert where == "/parasha/read/nitzavim-vayeilech/reader/index.html?k=test-key"
    assert _location(serving, "/library/parasha-nitzavim-vayeilech") == (
        301,
        "/parasha/nitzavim-vayeilech",
    ), "signed out, the public page is still the answer"


def test_the_door_onto_a_portion_is_its_reader(serving: int) -> None:
    """`/open/<id>` is every link to a text, from Learn, the reader and the palette; a
    portion's is its reader rather than the library's offer to build it."""
    status, where = _location(serving, "/open/parasha-nitzavim-vayeilech?k=test-key")
    assert status == 302
    assert where == "/parasha/read/nitzavim-vayeilech/reader/index.html?k=test-key"


def test_a_signed_in_reader_opens_a_portion_with_the_shelves_shut(
    serving: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The portion is in the Library now, so its reader answers a reader who is signed in
    whether or not the shelves are open to strangers — and still nobody else."""
    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "")
    reader = "/parasha/read/nitzavim-vayeilech/reader/index.html"
    assert get(serving, reader + "?k=test-key")[0] == 200
    assert get(serving, reader)[0] != 200
    status, where = _location(serving, "/library/parasha-nitzavim-vayeilech?k=test-key")
    assert (status, where) == (302, reader + "?k=test-key")


def test_the_weekly_shelf_is_the_cycle_with_this_weeks_named(serving: int) -> None:
    """targum-internal#411: `/portions` is what the Library's shelf draws — each built
    portion with its reader, and which is read this Shabbat on each calendar this box
    has built."""
    status, body = get(serving, "/portions?k=test-key")
    assert status == 200
    answer = json.loads(body)
    assert answer["week"] == {"diaspora": "nitzavim-vayeilech"}
    assert answer["shabbat"] == "2026-09-05"
    by_slug = {one["slug"]: one for one in answer["portions"]}
    this_week = by_slug["nitzavim-vayeilech"]
    assert this_week["href"] == "/parasha/read/nitzavim-vayeilech/reader/index.html"
    assert this_week["id"] == "parasha-nitzavim-vayeilech"
    assert get(serving, this_week["href"])[0] == 200, "every card opens something"
    assert all(one["href"].startswith("/parasha/read/") for one in answer["portions"])


def test_the_weekly_shelf_lists_only_what_is_built(built: Index, tmp_path: Path) -> None:
    """A card with no reader behind it opens a 404; it is left off instead."""
    shelf = corpus_build.shelf(built)
    listed = [one["slug"] for one in shelf["portions"] if one["listed"]]
    assert listed == [
        one.slug for one in built.listed() if one.folder in corpus_build._built(built)
    ]
    portion = built.portions["nitzavim-vayeilech"]
    shutil.rmtree(tmp_path / "parasha" / "read" / portion.folder)
    gone = corpus_build.shelf(built)
    assert "nitzavim-vayeilech" not in {one["slug"] for one in gone["portions"]}
    assert gone["week"] == {} and gone["shabbat"] == ""


def test_the_sitemap_names_the_portions_by_their_own_addresses(
    serving: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Their catalogue ids redirect here, so listing both would be asking a crawler to
    pick between two addresses for one text."""
    monkeypatch.setenv("TARGUM_INDEX_PARASHA", "1")
    status, body = get(serving, "/sitemap.xml")
    assert status == 200
    assert "/parasha</loc>" in body
    assert "/parasha/nitzavim-vayeilech</loc>" in body
    assert "/library/parasha-" not in body, "the id that redirects is left out"


def test_the_sitemap_names_a_portion_in_both_its_languages(
    serving: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """targum-internal#188: a portion's page says its range, its date and its headings in
    Russian at `?lang=ru`, and canonicals there, so the sitemap lists both addresses with
    the alternate set beside each. `/parasha` is not one of them: it canonicals to the
    portion it means this week."""
    monkeypatch.setenv("TARGUM_INDEX_PARASHA", "1")
    body = get(serving, "/sitemap.xml")[1]
    assert "/parasha/nitzavim-vayeilech?lang=ru</loc>" in body
    assert re.search(r'hreflang="ru" href="[^"]*/parasha/nitzavim-vayeilech\?lang=ru"', body)
    assert "/parasha?lang=ru</loc>" not in body


def test_the_sitemap_is_silent_about_the_parasha_until_it_is_invited(serving: int) -> None:
    """Off by default. A sitemap naming pages whose every response says noindex would be
    the site contradicting itself."""
    status, body = get(serving, "/sitemap.xml")
    assert status == 200
    assert "/parasha</loc>" not in body
    assert "/parasha/nitzavim-vayeilech</loc>" not in body
    assert "/library</loc>" in body, "the rest of the sitemap is unaffected"


def test_every_parasha_page_says_noindex_until_the_deployment_says_otherwise(
    serving: int,
) -> None:
    """A portion's page is the same page every year, so whatever ranks for its name ranks
    for a long time. The shelf, one portion, and a file of a built reader all say it."""
    assert robots_tag(serving, "/parasha") == "noindex"
    assert robots_tag(serving, "/parasha/nitzavim-vayeilech") == "noindex"
    assert robots_tag(serving, "/parasha/read/nitzavim-vayeilech/index.html") == "noindex"


def test_the_noindex_lifts_when_the_deployment_invites_crawlers(
    serving: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_INDEX_PARASHA", "1")
    assert robots_tag(serving, "/parasha") is None
    assert robots_tag(serving, "/parasha/nitzavim-vayeilech") is None


def test_robots_lets_a_crawler_into_the_parasha(serving: int) -> None:
    """Deliberately still allowed while the pages say noindex: a crawler barred in
    robots.txt never fetches the page, so it never reads the noindex, and an address it
    learned elsewhere can be indexed bare. The header is the instruction."""
    status, body = get(serving, "/robots.txt")
    assert status == 200
    assert "Allow: /parasha" in body


def test_the_shelf_is_listed_on_the_page(serving: int) -> None:
    status, body = get(serving, "/parasha")
    assert status == 200
    assert "Every portion" in body


def test_the_reader_is_framed_by_its_own_page_and_nothing_else(serving: int) -> None:
    """`frames="out"` on the reader and `frames="in"` on the page: the same pair the
    weekly uses, and what keeps the built reader off other people's sites."""
    conn = HTTPConnection("127.0.0.1", serving)
    conn.request("GET", "/parasha/read/nitzavim-vayeilech/reader/index.html")
    answer = conn.getresponse()
    answer.read()
    policy = answer.headers.get("Content-Security-Policy") or ""
    conn.close()
    assert "frame-ancestors" in policy


def test_a_named_portion_does_not_argue_about_schedules(serving: int) -> None:
    """The bug this guards: the schedule block compared *this week's* two readings while
    the page was showing a portion somebody had asked for by name, so a page about
    Bereshit announced that Israel and the diaspora disagree — and then printed the same
    portion's name in both chips.
    """
    body = get(serving, "/parasha/bereshit")[1]
    assert "reading different portions" not in body
    assert 'class="schedules"' not in body


def test_a_corpus_with_one_schedule_offers_no_choice_between_two(serving: int) -> None:
    """This corpus was built for the diaspora only. Drawing a switch whose other
    position is not there would be offering a page that does not exist — so the choice
    stays off, and `test_both_portions_are_named_only_where_the_schedules_really_differ`
    covers the page that has both.
    """
    body = get(serving, "/parasha")[1]
    assert 'class="seg series-schedule"' not in body
    assert "This Shabbat" in body, "the page itself is fine without it"


def test_both_portions_are_named_only_where_the_schedules_really_differ() -> None:
    """Rendered directly, so the week under test is a choice rather than today."""
    from datetime import date as _date

    from targum.parasha.models import Portion as P
    from targum.render.builder import parasha_page

    nasso = P(slug="nasso", name="Nasso", hebrew="נָשֹׂא", numbers=[35], summary="Numbers 4:21-7:89")
    behaalotcha = P(
        slug="behaalotcha",
        name="Beha'alotcha",
        hebrew="בְּהַעֲלֹתְךָ",
        numbers=[36],
        summary="Numbers 8:1-12:16",
    )
    apart = parasha_page(
        nasso,
        schedule=cal.Schedule.diaspora,
        diaspora=nasso,
        israel=behaalotcha,
        shabbat=_date(2026, 5, 30),
    )
    assert "reading different portions" in apart
    assert "בְּהַעֲלֹתְךָ" in apart, "the other schedule's portion is named"

    together = parasha_page(
        nasso,
        schedule=cal.Schedule.diaspora,
        diaspora=nasso,
        israel=nasso,
        shabbat=_date(2026, 7, 4),
    )
    assert "reading different portions" not in together


def test_the_series_tile_is_the_scroll_carried_in_the_page(serving: int) -> None:
    """The photograph stays as the series' tile, carried in the page once, never
    fetched, and never under type (§12, 2026-09-01 and 2026-10-09)."""
    body = get(serving, "/parasha")[1]
    assert body.count("data:image/jpeg;base64,") == 1, "inlined once, for every tile"
    assert 'class="series-tile has-pic is-large" aria-hidden="true"></span>' in body


def test_a_stranger_is_asked_to_sign_in_not_to_join(serving: int) -> None:
    """David, 2026-10-09: no marketing landing. A stranger gets the same page with a
    sign-in prompt where Subscribe stands, and reading needs no account."""
    body = get(serving, "/parasha")[1]
    assert 'action="/waitlist"' not in body
    assert 'class="btn filled series-sign-in" href="/account/signin"' in body
    assert 'id="series-subscribe"' not in body


def test_a_named_portion_gets_its_own_card(serving: int) -> None:
    """Fifty-four pages are told apart by what they show: the portion's own name heads
    its card, and only this week's page calls itself this Shabbat's."""
    week = get(serving, "/parasha")[1]
    named = get(serving, "/parasha/nitzavim-vayeilech")[1]
    assert 'id="series-now-title"' in named and "Nitzavim-Vayeilech" in named
    assert "This Shabbat ·" in week
    page = named.split('<footer class="site-footer">')[0]
    assert "this shabbat ·" not in unescape(page).casefold()


def test_a_named_portion_does_not_title_itself_this_weeks(serving: int) -> None:
    """The same correction as the headline, in the tag that carries more of the weight.

    A search engine reads the title first, and fifty-four of them claiming to be this
    week's parasha is fifty-four pages it cannot tell apart — on a page whose whole
    argument is that every parasha name is a query. The chapter range is what somebody
    searching the name wants confirmed, and it differs for all fifty-four.
    """
    week = get(serving, "/parasha")[1]
    named = get(serving, "/parasha/nitzavim-vayeilech")[1]

    def title(body: str) -> str:
        # Unescaped, because Jinja writes the apostrophe as &#39; and a test that compares
        # the raw markup is testing the escaper rather than the words.
        return unescape(body[body.index("<title>") + 7 : body.index("</title>")])

    assert title(week) == "Nitzavim-Vayeilech — this week's parasha — targum"
    assert "this week" not in title(named).casefold(), "a portion browsed to is not a week"
    assert "Nitzavim-Vayeilech" in title(named), "and it still says which portion it is"


def test_the_kicker_of_a_named_portion_says_where_it_is(serving: int) -> None:
    """A named portion is not about a week: its card says which book it is in."""
    named = get(serving, "/parasha/nitzavim-vayeilech")[1]
    kicker = named.split('<p class="series-kicker">')[1].split("</p>")[0]
    assert "This Shabbat" not in kicker
    assert "Deuteronomy" in kicker


def test_the_opening_words_describe_the_page(serving: int) -> None:
    """What a search result leads with: the words somebody who knows the portion
    recognises, rather than the chapter numbers alone."""
    import re

    body = get(serving, "/parasha/nitzavim-vayeilech")[1]
    found = re.search(r'name="description" content="([^"]*)"', body)
    assert found is not None
    assert "Nitzavim-Vayeilech" in found.group(1)
    assert "Deuteronomy 29:9" in found.group(1), "and where the reading starts"
    # The opening words themselves: pointed Hebrew out of the reading's first verse.
    assert any("\u0591" <= c <= "\u05c7" for c in found.group(1)), "opening words present"


# -- the portion before and the one after --------------------------------------


def _cycle() -> list[object]:
    from targum.parasha.models import Portion as P

    return [
        P(slug="bereshit", name="Bereshit", hebrew="בְּרֵאשִׁית", numbers=[1], summary="x"),
        P(slug="noach", name="Noach", hebrew="נֹחַ", numbers=[2], summary="x"),
        P(slug="vzot-haberachah", name="Vzot", hebrew="וְזֹאת הַבְּרָכָה", numbers=[54], summary="x"),
    ]


def _nav(page: str) -> str:
    """The portions nav alone. Its closing tag is found from its own opening one — the
    ladder above it is also a nav, and its close comes first in the document."""
    at = page.index('<nav class="portions')
    return page[at : page.index("</nav>", at)]


def test_a_portion_page_leads_to_the_portions_before_and_after_it() -> None:
    from targum.render.builder import parasha_page

    listed = _cycle()
    nav = _nav(parasha_page(listed[1], schedule=cal.Schedule.diaspora, listed=listed))
    assert 'class="prev" href="/parasha/bereshit"' in nav
    assert "בְּרֵאשִׁית" in nav, "named in Hebrew, the way the shelf names it"
    assert 'class="next" href="/parasha/vzot-haberachah"' in nav
    assert 'class="all" href="/parasha#sources"' in nav, "signed out, the list on this page"

    wrapped = _nav(parasha_page(listed[2], schedule=cal.Schedule.diaspora, listed=listed))
    assert 'class="next" href="/parasha/bereshit"' in wrapped, "after וזאת הברכה, בראשית"
    assert 'class="prev" href="/parasha/noach"' in wrapped


def test_a_festival_page_has_no_place_in_the_cycle_but_still_the_whole_list() -> None:
    from targum.parasha.models import Portion as P
    from targum.render.builder import parasha_page

    festival = P(
        slug="pesach", name="Pesach", hebrew="פסח", kind=cal.ReadingKind.festival, summary="x"
    )
    nav = _nav(parasha_page(festival, schedule=cal.Schedule.diaspora, listed=_cycle()))
    assert 'class="prev"' not in nav
    assert 'class="next"' not in nav
    assert 'class="all" href="/parasha#sources"' in nav


def test_a_signed_in_reader_is_sent_to_the_portion_on_their_own_shelf() -> None:
    from targum.parasha.models import Portion as P
    from targum.render.builder import parasha_page

    listed = _cycle()
    page = parasha_page(listed[1], schedule=cal.Schedule.diaspora, listed=listed, signed_in=True)
    assert 'class="all" href="/library#parasha-noach"' in page
    # A doubled week is not on the shelf beside its halves; its first half is.
    doubled = P(slug="bereshit-noach", name="x", hebrew="x", numbers=[1, 2], summary="x")
    page = parasha_page(doubled, schedule=cal.Schedule.diaspora, listed=listed, signed_in=True)
    assert 'class="all" href="/library#parasha-bereshit"' in page


def test_a_signed_in_reader_gets_the_switch_not_the_prompt() -> None:
    """One page for everyone (design.md §12, 2026-10-09): signed in, Subscribe in the
    state the account is in; signed out, the sign-in prompt in its place."""
    from targum.render.builder import parasha_page

    listed = _cycle()
    stranger = parasha_page(listed[1], schedule=cal.Schedule.diaspora, listed=listed)
    assert 'class="btn filled series-sign-in"' in stranger
    assert 'id="series-subscribe"' not in stranger
    reader = parasha_page(listed[1], schedule=cal.Schedule.diaspora, listed=listed, signed_in=True)
    assert 'id="series-subscribe"' in reader and 'class="btn filled series-sign-in"' not in reader
    assert 'aria-pressed="false"' in reader and "btn filled series-switch" in reader
    on = parasha_page(
        listed[1], schedule=cal.Schedule.diaspora, listed=listed, signed_in=True, subscribed=True
    )
    assert 'aria-pressed="true"' in on and "btn tonal is-on series-switch" in on
    assert 'action="/waitlist"' not in reader + stranger


def test_the_served_page_carries_the_way_round_the_year(serving: int, built: Index) -> None:
    listed = [one for one in built.listed()]
    assert listed, "the fixture builds at least one portion"
    status, body = get(serving, f"/parasha/{listed[0].slug}")
    assert status == 200
    nav = _nav(body)
    assert 'class="all" href="/parasha#sources"' in nav
    if len(listed) > 1:
        assert 'class="prev"' in nav
        assert 'class="next"' in nav


# -- the haftarah ------------------------------------------------------------


def test_the_haftarah_is_built_beside_the_portion(built: Index, tmp_path: Path) -> None:
    """Every portion in the corpus that has a haftarah carries its reference, resolved
    to a reader of its own under the corpus root."""
    portion = built.portions["nitzavim-vayeilech"]
    assert portion.haftarah == "isaiah-61-10-63-9"
    record = built.haftarot[portion.haftarah]
    assert record.summary == "Isaiah 61:10-63:9"
    assert record.books == ["Isaiah"]
    assert record.hebrew == "ישעיהו"
    assert record.verses == 23
    assert record.folder == "haftarah-isaiah-61-10-63-9"
    # One section, so the renderer wrote `index.html` alone and that is what opens.
    assert record.opens == "index.html"
    reader = tmp_path / "parasha" / "read" / record.folder / "reader" / record.opens
    assert reader.is_file()
    assert not (reader.parent / "sec-0001.html").exists()
    assert record.folder in corpus_build.readable(built), "a built haftarah is readable"

    week = built.week("2026-09-05", cal.Schedule.diaspora)
    assert week is not None
    assert week.haftarah == "isaiah-61-10-63-9"
    assert week.haftarah_reason == ""


def test_a_festival_shabbat_carries_the_festivals_haftarah(built: Index) -> None:
    """Shavuot's second day on Shabbat displaces Bamidbar or Nasso, and its haftarah
    displaces theirs: the week and the built festival both say Habakkuk."""
    week = built.week("2026-05-23", cal.Schedule.diaspora)
    assert week is not None
    assert week.slug == "shavuot-ii-on-shabbat"
    assert week.haftarah == "habakkuk-3-1-19"
    festival = built.portions[week.slug]
    assert festival.kind is cal.ReadingKind.festival
    assert festival.haftarah == "habakkuk-3-1-19"
    assert built.haftarot["habakkuk-3-1-19"].folder == "haftarah-habakkuk-3-1-19"


def test_the_variant_rite_is_recorded_on_the_week_and_the_portion(built: Index) -> None:
    week = built.week("2026-05-23", cal.Schedule.diaspora)
    assert week is not None
    assert week.haftarah_sephardic == "Habakkuk 2:20-3:19"
    assert built.portions[week.slug].haftarah_sephardic == "Habakkuk 2:20-3:19"


def test_a_haftarah_whose_book_is_not_on_the_shelf_keeps_its_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reference is written down whether or not the text is built: the page can at
    least say what is read. The missing book is named once, the way a missing book of
    the Torah is."""
    monkeypatch.setenv("TARGUM_PARASHA_DIR", str(tmp_path / "parasha"))
    (tmp_path / "parasha" / "calendar").mkdir(parents=True)
    for one in FIXTURES.glob("*.json"):
        shutil.copy(one, tmp_path / "parasha" / "calendar" / one.name)
    library = tmp_path / "library"
    a_book(library / "דברים-he", "Deuteronomy", "דברים", {29: 29, 30: 20, 31: 30})
    said: list[str] = []
    index = corpus_build.build(
        corpus_years=[2026],
        years=[2026],
        schedules=[cal.Schedule.diaspora],
        library=library,
        notify=said.append,
    )
    record = index.haftarot["isaiah-61-10-63-9"]
    assert record.summary == "Isaiah 61:10-63:9"
    assert record.folder == "", "no reader was built, and the record says so"
    assert record.folder not in corpus_build.readable(index)
    assert index.portions["nitzavim-vayeilech"].haftarah == "isaiah-61-10-63-9"
    named = [line for line in said if "Isaiah is not built" in line]
    assert len(named) == 1

    from targum.render.builder import parasha_page

    page = parasha_page(
        index.portions["nitzavim-vayeilech"],
        schedule=cal.Schedule.diaspora,
        haftarah=record,
        haftarah_readable=False,
    )
    assert "Isaiah 61:10-63:9" in page, "the reference is said"
    assert 'id="haftarah"' not in page, "and no frame is drawn on nothing"


def test_this_weeks_page_carries_the_haftarah(serving: int) -> None:
    status, body = get(serving, "/parasha")
    assert status == 200
    assert "The haftarah" in body
    assert "Isaiah 61:10-63:9" in body
    assert "/parasha/read/haftarah-isaiah-61-10-63-9/reader/index.html" in body
    assert "Read this week in place of" not in body, "an ordinary Shabbat gives no reason"


def test_the_haftarahs_reader_is_served_under_the_corpus(serving: int) -> None:
    status, body = get(serving, "/parasha/read/haftarah-isaiah-61-10-63-9/reader/index.html")
    assert status == 200
    assert "הפטרה" in unescape(body)
    assert 'data-form="pointed"' in body
    assert 'data-form="unaccented"' in body, "the chanting marks come off the haftarah too"


def test_a_named_portion_shows_the_haftarah_it_ordinarily_has(serving: int) -> None:
    status, body = get(serving, "/parasha/nitzavim-vayeilech")
    assert status == 200
    assert "Isaiah 61:10-63:9" in body


def test_the_festival_page_shows_the_festivals_haftarah_and_not_the_variant(
    serving: int,
) -> None:
    status, body = get(serving, "/parasha/shavuot-ii-on-shabbat")
    assert status == 200
    assert "Habakkuk 3:1-19" in body
    assert "/parasha/read/haftarah-habakkuk-3-1-19/reader/index.html" in body
    assert "2:20" not in body, "the Sephardic reading is recorded and not shown"
    assert "Sephardic" not in body and "Ashkenazi" not in body, "no rite chooser"


def test_the_corpus_records_which_annotation_it_was_cut_from(tmp_path: Path, built: Index) -> None:
    """The corpus keeps no artifact beside its readers, so this one string in the index
    is all that can say whether a portion is behind the book it came from. Read back the
    way `targum preflight` reads it: level with the shelf as built, behind it once the
    shelf's annotation moves on and the corpus has not been cut again
    (targum-internal#227)."""
    from targum.annotate.versions import survey_corpus

    assert built.portions["nitzavim-vayeilech"].annotator == "test/1"
    assert built.haftarot["isaiah-61-10-63-9"].annotator == "test/1"
    library = tmp_path / "library"
    corpus = tmp_path / "parasha"

    level = survey_corpus(corpus, library)
    assert (level.current, level.behind, level.unknown) == (level.total, [], 0)

    for book in ("דברים-he", "ישעיהו-he", "חבקוק-he"):
        path = library / book / "annotation.json"
        moved = json.loads(path.read_text(encoding="utf-8"))
        moved["annotator"] = "test/2"
        path.write_text(json.dumps(moved, ensure_ascii=False), encoding="utf-8")
    behind = survey_corpus(corpus, library)
    assert behind.current == 0 and len(behind.behind) == behind.total
    assert behind.moved() == {"test/1 -> test/2": behind.total}


# -- this week's reading, part by part (targum-internal#203) -------------------------


def _parts(page: str) -> list[dict[str, str]]:
    import re

    found = []
    rows = page.split('<ol class="rows series-parts">')[1].split("</ol>")[0]
    for href, inner in re.findall(r'<a class="series-row-title" href="([^"]*)">(.*?)</a>', rows):
        name = unescape(re.sub(r"<[^>]+>", "", inner.split('<span class="series-en">')[0]))
        found.append({"href": href, "name": name.strip()})
    return found


def test_this_weeks_page_lists_each_part_of_the_reading(serving: int, tmp_path: Path) -> None:
    """Seven aliyot and the haftarah, each a row that opens its reader, with no share of
    it said where nobody is signed in."""
    from targum.parasha.cut import ALIYOT, HAFTARAH

    status, body = get(serving, "/parasha")
    assert status == 200
    parts = _parts(body)
    reader = tmp_path / "parasha" / "read" / "nitzavim-vayeilech" / "reader"
    sections = len(list(reader.glob("sec-*.html")))
    assert [p["name"] for p in parts] == [*ALIYOT[:sections], HAFTARAH]
    for n, part in enumerate(parts[:sections], start=1):
        assert part["href"] == f"/parasha/read/nitzavim-vayeilech/reader/sec-{n:04d}.html"
    assert parts[-1]["href"] == "/parasha/read/haftarah-isaiah-61-10-63-9/reader/index.html"
    rows = body.split('<ol class="rows series-parts">')[1].split("</ol>")[0]
    assert "% known" not in rows and "series-mark" not in rows, "nothing marked for a stranger"


def test_a_portion_asked_for_by_name_is_not_a_week(serving: int) -> None:
    status, body = get(serving, "/parasha/nitzavim-vayeilech")
    assert status == 200
    assert "This Shabbat ·" not in body, "a portion by name has no week to be read in"


def test_the_week_holds_until_the_turn(serving: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """A reader mid-practice on Saturday night keeps the week they are in until the turn."""
    saturday_night = datetime(2026, 9, 6, 1, 59, tzinfo=ZoneInfo(cal.FLIP_ZONE))
    monkeypatch.setattr(cal, "now_in_flip_zone", lambda moment=None: saturday_night)
    status, body = get(serving, "/parasha")
    assert status == 200
    assert "This Shabbat · 5 September" in body
    assert "nitzavim-vayeilech/reader/sec-0001.html" in body


def test_a_festival_week_lists_what_is_actually_read(
    serving: int, built: Index, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On a Shabbat a festival displaces the portion, the parts are the festival reading's
    and the haftarah is the festival's (`ReadingKind.festival`)."""
    week = built.week("2026-05-23", cal.Schedule.diaspora)
    assert week is not None and week.slug == "shavuot-ii-on-shabbat"
    midweek = datetime(2026, 5, 20, 12, tzinfo=ZoneInfo(cal.FLIP_ZONE))
    monkeypatch.setattr(cal, "now_in_flip_zone", lambda moment=None: midweek)
    status, body = get(serving, "/parasha")
    assert status == 200
    parts = _parts(body)
    assert parts, "the festival reading is listed"
    folder = built.portions["shavuot-ii-on-shabbat"].folder
    assert all(f"/parasha/read/{folder}/" in p["href"] for p in parts[:-1])
    # The fixture's festival reading is too short to split, so it is one part, read whole.
    assert len(parts) == 2 and parts[0]["href"].endswith("/reader/index.html")
    assert parts[-1]["href"] == "/parasha/read/haftarah-habakkuk-3-1-19/reader/index.html"


def test_the_facts_line_counts_in_the_readers_language() -> None:
    """targum-internal#348: the counts go through `tn`, because Russian has three plural
    forms, and the books are the language's own."""
    import re
    from datetime import date

    from targum.parasha.models import Portion as P
    from targum.render.builder import parasha_page

    def facts(html: str) -> str:
        found = re.search(r'<p class="series-facts">(.*?)</p>', html, re.S)
        assert found, "no facts on the card"
        return " ".join(re.sub(r"<[^>]+>", " ", found.group(1)).split())

    portion = P(
        slug="x",
        name="Nasso",
        hebrew="נָשֹׂא",
        numbers=[35],
        summary="Numbers 4:21-7:89",
        verses=176,
        aliyot=7,
    )
    when = date(2026, 5, 30)
    english = facts(parasha_page(portion, schedule=cal.Schedule.diaspora, shabbat=when))
    assert english == "Numbers 4:21-7:89 · 176 verses in 7 aliyot"
    russian = facts(
        parasha_page(portion, schedule=cal.Schedule.diaspora, shabbat=when, language="ru")
    )
    assert "176 стихов" in russian and "verses" not in russian
    for count, form in ((21, "21 стих,"), (11, "11 стихов"), (22, "22 стиха")):
        one = P(slug="y", name="N", hebrew="נ", numbers=[35], summary="s", verses=count, aliyot=1)
        said = facts(parasha_page(one, schedule=cal.Schedule.diaspora, shabbat=when, language="ru"))
        assert form in said, (count, said)


def test_the_credits_are_whole_sentences_with_their_links_inside_them() -> None:
    """targum-internal#348: one key each, with the links riding in blanks as `Markup`,
    folded at the foot as "Every portion, and credits" since 2026-10-09."""
    import re
    from datetime import date

    from targum.parasha.models import Portion as P
    from targum.render.builder import parasha_page

    portion = P(slug="x", name="N", hebrew="נ", numbers=[35], summary="s", verses=1, aliyot=1)
    when = date(2026, 5, 30)

    for language, expected in (("en", "The scroll at the top was"), ("ru", "Свиток наверху")):
        html = parasha_page(
            portion, schedule=cal.Schedule.diaspora, shabbat=when, language=language
        )
        credits = " ".join(re.findall(r'<p class="series-credit">(.*?)</p>', html, re.S))
        assert expected in credits, language
        assert "&lt;a" not in html, "a link was escaped into the sentence"
        assert 'href="https://archive.org/details/PockettorahAudioFiles"' in credits
        assert "</a>, " in credits, "and the sentence closes onto them without a gap"
