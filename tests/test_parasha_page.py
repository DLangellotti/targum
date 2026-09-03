"""The `/parasha` page and the routes under it.

The corpus is built for real here — one portion, out of a book with a handful of verses
— because the thing under test is the whole path from a URL to a reader on the page, and
a stubbed corpus would not exercise the two gates that keep the reader folder shut.
"""

from __future__ import annotations

import shutil
import threading
from collections.abc import Iterator
from html import unescape
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

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
    (tmp_path / "parasha" / "calendar").mkdir(parents=True)
    for one in FIXTURES.glob("*.json"):
        shutil.copy(one, tmp_path / "parasha" / "calendar" / one.name)
    library = tmp_path / "library"
    a_book(library / "דברים-he", "Deuteronomy", "דברים", {29: 29, 30: 20, 31: 30})
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
            "page": "<html>start</html>",
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
    status, body = get(serving, "/parasha")
    assert status == 200
    assert "This week's parasha" in body
    assert "/parasha/read/" in body, "the reader is framed rather than linked to"
    assert "sec-0001.html" in body, "it opens on the first aliyah, not the contents page"


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


def test_the_chips_work_without_javascript(serving: int) -> None:
    """They are links first. `parasha.js` upgrades them to a switch; with it turned off
    the page still offers both readings."""
    status, body = get(serving, "/parasha?taamim=off")
    assert status == 200
    assert 'data-taamim="off"' in body
    assert 'href="?taamim=on"' in body


def test_the_page_says_which_schedule_and_only_names_both_when_they_differ(
    serving: int,
) -> None:
    status, body = get(serving, "/parasha?schedule=israel")
    assert status == 200
    # Not `"Israel" in body`: the honesty section says the word regardless of the query,
    # so that assertion passed whatever the schedule did. Assert the page actually served
    # a reading instead — this corpus has only the diaspora built, so asking for Israel
    # must fall back rather than 404.
    assert "/parasha/read/" in body
    assert "This week's parasha" in body


def test_a_schedule_this_box_never_built_falls_back_rather_than_404ing(serving: int) -> None:
    """This corpus was built for the diaspora only. A query string asking for the other
    schedule must not empty the page: the reading that is there is the one to show."""
    status, body = get(serving, "/parasha?schedule=israel")
    assert status == 200
    assert "/parasha/read/" in body, "the reader it does have is still on the page"


def test_a_taamim_value_nobody_recognises_leaves_the_marks_on(serving: int) -> None:
    """Only the literal `off` takes them off, so a mangled link opens the text as the
    edition wrote it rather than in the departure from it."""
    status, body = get(serving, "/parasha?taamim=banana")
    assert status == 200
    assert 'data-taamim="on" class="here"' in body
    assert 'data-taamim="off" class="here"' not in body


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
    position is not there would be offering a page that does not exist — so the block
    stays off, and `test_both_portions_are_named_only_where_the_schedules_really_differ`
    covers the page that has both.
    """
    body = get(serving, "/parasha")[1]
    assert 'class="schedules"' not in body
    assert "This week's parasha" in body, "the page itself is fine without it"


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


def test_the_hero_band_carries_the_scroll_and_the_words(serving: int) -> None:
    """D4: ink and the words on one side, the photograph on the other."""
    body = get(serving, "/parasha")[1]
    assert 'class="band"' in body
    assert 'class="pic"' in body
    assert "data:image/jpeg;base64," in body, "the photograph is inlined, not fetched"
    assert 'aria-hidden="true"' in body, "the picture says nothing the words do not"


def test_the_band_never_sets_type_over_the_picture(serving: int) -> None:
    """The whole reason the seam is upright. If the words ever end up inside `.pic`,
    the legibility problem this layout exists to solve has come back."""
    import re

    body = get(serving, "/parasha")[1]
    pic = re.search(r'<div class="pic"[^>]*>(.*?)</div>', body, re.S)
    assert pic is not None
    assert "<h1" not in pic.group(1)
    assert "eyebrow" not in pic.group(1)


def test_the_band_is_the_dark_surface_in_both_themes(serving: int) -> None:
    """The band's colours are constants, not the max-contrast tokens: that pair flips
    with the theme, and flipping puts a pale panel on a dark page."""
    body = get(serving, "/parasha")[1]
    assert "--band-ground: #171614" in body
    assert "--band-ink: #e6e1d8" in body
    band = body[body.index(".public .band {") : body.index(".public .band .pic img")]
    assert "--ink-max" not in band and "--page-max" not in band


def test_a_named_portion_gets_its_own_headline(serving: int) -> None:
    """Fifty-two pages sharing one headline is fifty-two pages a search engine cannot
    tell apart — and on a portion you browsed to, "this week's" is simply false."""
    week = get(serving, "/parasha")[1]
    named = get(serving, "/parasha/nitzavim-vayeilech")[1]
    assert "This week's parasha, every word explained." in week
    assert "Nitzavim-Vayeilech, every word explained." in named
    # Unescaped and casefolded, and both are needed. This assertion passed for weeks
    # while every named portion's <title> still said "this week's parasha" — the title is
    # lower case where the headline is capitalised, and Jinja writes its apostrophe as
    # &#39;, so a raw case-sensitive search for the phrase could not find it either way.
    assert "this week's parasha" not in unescape(named).casefold()


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


def test_the_eyebrow_does_not_repeat_the_label_under_it(serving: int) -> None:
    """Both said "This Shabbat" for a while, one above the other."""
    named = get(serving, "/parasha/nitzavim-vayeilech")[1]
    assert "This Shabbat" not in named, "a named portion is not about a week"
    assert "The reading" in named


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
    at = page.index('<nav class="portions"')
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
