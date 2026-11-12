"""/after-duolingo-hebrew, the page for course graduates (targum-internal#676, step 3).

What is tested here is what makes it safe to point an ad at: it answers while the front
door does and not before, its one ask says it was pressed here (`from=after-duolingo-hebrew`),
its box answers on the page itself and spends nothing, and it loads nothing from any
other origin (design.md §12, 2026-10-30).
"""

from __future__ import annotations

import io
import json
import re
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest

from targum.accounts import Store
from targum.catalogue import Entry, Kind, Register
from targum.mail import ConsoleMailer
from targum.render.builder import AFTER_DUOLINGO_FIRSTS, after_duolingo_page, asset_files
from targum.serve import Handler, Library, joined_from

ADDRESS = "https://targum.page"

#: The three rows as the catalogue holds them, so the page is drawn the same on a CI
#: checkout, which has no catalogue, as on the box.
ROWS = {
    "kan-small-cola": Entry(
        id="kan-small-cola",
        title="למה קולה קטן עולה יותר מקולה גדול?",
        author="כאן",
        language="he",
        source="video:NEoaePzDhGc",
        blurb="Dana finds that her friend's big bottle of cola cost less than her small one.",
        words=363,
        english="Why does a small cola cost more than a big one?",
        kind=Kind.talk,
        register=Register.modern,
    ),
    "yatziv-shoelace-seller": Entry(
        id="yatziv-shoelace-seller",
        title="מוֹכֵר הַשְּׂרוֹכִים",
        author="יצחק יציב",
        language="he",
        source="https://benyehuda.org/download/29709.txt",
        blurb="Shlomo is nine, sells shoelaces office to office.",
        words=359,
        english="The Shoelace Seller",
        kind=Kind.story,
        register=Register.modern,
    ),
}


@pytest.fixture
def shelf(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two of the three rows on this machine's catalogue, and the third missing, as a
    checkout without it would have it."""
    monkeypatch.setattr("targum.catalogue.by_id", lambda entry_id: ROWS.get(entry_id))
    monkeypatch.setattr("targum.levelmap.text_level", lambda entry, index=None: "A1")


@pytest.fixture
def served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[int, Store]]:
    out = tmp_path / "targum-out"
    out.mkdir()
    store = Store(tmp_path / "words.db")
    library = Library(out)
    library.store = store
    library.mailer = ConsoleMailer(io.StringIO())
    library.hosted = True
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    server.RequestHandlerClass = type(
        "TestHandler",
        (Handler,),
        {
            "library": library,
            "token": "test-key",
            "require_account": True,
            "welcome": "<html>start</html>",
            "store": store,
            "mailer": library.mailer,
            "address": f"http://127.0.0.1:{port}",
        },
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield port, store
    finally:
        server.shutdown()
        server.server_close()


def ask(port: int, method: str, path: str, form: dict[str, str] | None = None) -> tuple[int, str]:
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        if form is None:
            connection.request(method, path)
        else:
            connection.request(
                method,
                path,
                urlencode(form),
                {"Content-Type": "application/x-www-form-urlencoded"},
            )
        response = connection.getresponse()
        return response.status, response.read().decode("utf-8", "replace")
    finally:
        connection.close()


# -- the page itself ------------------------------------------------------------------


def test_the_page_loads_nothing_from_another_origin(shelf: None) -> None:
    """Every address it loads is its own. The only other-origin addresses are links a
    visitor chooses to press, in the foot, and nothing is a script, a stylesheet, a font
    or a picture from somebody else (design.md §12, 2026-10-30)."""
    page = after_duolingo_page(ADDRESS)
    loaded = re.findall(r'<(?:script|img|iframe|source|video|audio)\b[^>]*\bsrc="([^"]+)"', page)
    loaded += re.findall(
        r'<link\b[^>]*rel="(?:stylesheet|preload|modulepreload|icon)"[^>]*href="([^"]+)"', page
    )
    assert all(not re.match(r"(?:https?:)?//", address) for address in loaded), loaded
    assert not re.search(r"url\(\s*['\"]?(?:https?:)?//", page), "a stylesheet fetches something"
    assert not re.search(r"@import", page)
    outbound = set(re.findall(r'href="(https?://[^"]+)', page))
    assert outbound <= {
        "https://github.com/DLangellotti/targum",
        "https://x.com/targum_app",
        "https://www.instagram.com/targum.page/",
        "https://www.linkedin.com/company/targum-page/",
        f"{ADDRESS}/after-duolingo-hebrew",
        # The clip's credit: its source and its licence, as CC BY asks.
        "https://www.youtube.com/watch?v=NEoaePzDhGc",
        "https://creativecommons.org/licenses/by/3.0/",
    }, outbound
    assert "<script src" not in page


def test_the_page_names_duolingo_and_says_it_is_not_theirs(shelf: None) -> None:
    page = after_duolingo_page(ADDRESS)
    assert "<h1>You finished Duolingo Hebrew. Now learn from real Hebrew.</h1>" in page
    assert "targum isn’t affiliated with Duolingo." in page
    assert "<title>After Duolingo Hebrew: what to read next — targum</title>" in page
    assert f'<link rel="canonical" href="{ADDRESS}/after-duolingo-hebrew">' in page


def test_every_ask_says_it_was_pressed_here(shelf: None) -> None:
    """The waitlist's form (or Sign up's, with the door open) carries from=after-duolingo-hebrew,
    and so do the bar's Sign in and the links out to the first texts."""
    page = after_duolingo_page(ADDRESS)
    said = re.findall(r'<input type="hidden" name="from" value="([^"]*)">', page)
    assert said and set(said) == {"after-duolingo-hebrew"}, said
    assert 'action="/waitlist?lang=en"' in page
    assert 'href="/account/signin?lang=en&amp;from=after-duolingo-hebrew"' in page
    assert joined_from("after-duolingo-hebrew") == "/after-duolingo-hebrew"


def test_the_first_texts_are_the_library_s_own_rows(shelf: None) -> None:
    """Drawn off the catalogue, each linking to its page in the library, and a row this
    machine does not hold is left out rather than drawn from memory."""
    page = after_duolingo_page(ADDRESS)
    assert len(AFTER_DUOLINGO_FIRSTS) == 3
    rows = page.split('<ul class="texts lib-rows">', 1)[1].split("</ul>", 1)[0]
    links = re.findall(r'<a href="([^"]+)">', rows)
    assert links == [
        "/library/kan-small-cola?from=after-duolingo-hebrew",
        "/library/yatziv-shoelace-seller?from=after-duolingo-hebrew",
    ]
    assert rows.count('<li class="lib-row">') == 2
    assert "Why does a small cola cost more than a big one?" in rows
    assert '<span class="byline">A1 · Video · 3 minutes</span>' in rows
    assert '<span class="byline">A1 · Story · 3 minutes</span>' in rows


def test_with_the_library_shut_the_first_texts_are_named_without_links(shelf: None) -> None:
    """A link to a library page a stranger cannot open ends at a refusal (qa-claude on
    targum#1187), so with the shelves shut the texts are named and not linked."""
    page = after_duolingo_page(ADDRESS, linked=False)
    drawn = page.split("<main", 1)[1].split('id="questions"', 1)[0]
    assert "/library/" not in drawn
    assert page.count('<div class="lib-name">') == 2
    assert "The Shoelace Seller" in page
    assert "Read it in the library" not in page


def test_the_top_is_the_front_page_s_word_card_and_reader(shelf: None) -> None:
    """Drawn as the front page's top (design's spec, 2026-11-12): the word card beside the
    hero, open on the word the reader's third line has open, and four real lines of the
    story under both, its foot opening the story in the library. Drawn whole in the
    markup, so with no script nothing is a press that does nothing."""
    page = after_duolingo_page(ADDRESS)
    top = page.split('<div class="col top">', 1)[1].split('<section class="part"', 1)[0]
    assert '<aside class="card" id="card"' in top
    assert '<p class="card-word" lang="he" dir="rtl">בית</p>' in top
    assert "house" in top.split("</aside>", 1)[0]
    assert '<article class="reader still" id="story"' in top
    assert top.count('<div class="pair') == 4
    assert '<span class="w open" data-id="l3w4">לְבֵית</span>' in top
    assert "“Why don’t you go to school?”" in top
    assert (
        '<a href="/library/yatziv-shoelace-seller?from=after-duolingo-hebrew">'
        "Read it in the library</a>" in top
    )
    assert "<button" not in top.rsplit("</form>", 1)[1], "a still page draws no dead press"
    # The one line that says the words answer a tap waits for the script that makes it so.
    assert '<span class="tap-hint" hidden>Tap any word.</span>' in top


def test_every_word_in_the_reader_has_targum_s_card(shelf: None) -> None:
    """Each word the reader draws is one targum read, and its card rides in the page for
    `landing.js` (David, 2026-11-12: tapping any word opens it in the word card). The card
    keeps no list, so it offers no Learning, Known or Ask."""
    page = after_duolingo_page(ADDRESS)
    lines = page.split('id="storyLines"', 1)[1].split("</article>", 1)[0]
    drawn = re.findall(r'<span class="w(?: open)?" data-id="([^"]+)">', lines)
    held = re.search(r'<script type="application/json" id="landingWords">(.*?)</script>', page)
    assert held
    words = json.loads(held.group(1))["words"]
    assert len(drawn) == 22 and set(drawn) == set(words)
    assert words["l3w4"]["head"] == "בית" and words["l3w4"]["sense"] == "house"
    assert "ל</span> to + <span" in words["l3w4"]["facts"][0][1]
    assert words["l4w2"]["inf"] == "לשלוח" and words["l4w2"]["sense"] == "to send"
    assert "data-set" not in page.split('<aside class="card"', 1)[1].split("</aside>", 1)[0]
    # The front page's own script, inline (§12: nothing from another origin).
    assert "<script src" not in page
    assert 'var film = document.getElementById("film");' in page


def test_why_real_hebrew_feels_harder_is_shown(shelf: None) -> None:
    """Each reason carries the front page's How card picture rather than prose alone."""
    page = after_duolingo_page(ADDRESS)
    why = page.split('id="why"', 1)[1].split("</section>", 1)[0]
    assert why.count('<li class="how-card">') == 4
    assert why.count('<div class="how-vis') == 4
    assert "מדוע אינך הולך לבית־הספר?" in why
    assert "מַדּוּעַ אֵינְךָ הוֹלֵךְ לְבֵית־הַסֵּפֶר?" in why


def test_people_talk_fast_plays_a_real_clip_from_our_own_origin(shelf: None) -> None:
    """ "People talk fast" plays a few seconds of the cola video (David, 2026-11-12): from
    targum's own origin by a hash address, small, muted, credited as CC BY asks, every
    word carrying the clock targum's aligner gave it."""
    page = after_duolingo_page(ADDRESS)
    card = page.split("<h3>People talk fast.</h3>", 1)[1].split("</li>", 1)[0]
    film = re.search(
        r'<video id="clipFilm" src="(/assets/kan-small-cola\.[0-9a-f]{16}\.mp4)"', card
    )
    assert film, card
    assert " muted " in card and " controls " in card
    assert film.group(1) in asset_files()
    body, kind, name = asset_files()[film.group(1)]
    assert kind == "video/mp4" and name == "films/kan-small-cola.mp4"
    assert len(body) < 300_000, "a clip rides beside the page, so it stays a few seconds and small"
    timed = re.findall(r'<span class="w" data-at="([\d.]+) ([\d.]+)">', card)
    assert len(timed) == 12
    assert all(float(a) < float(b) <= 5 for a, b in timed)
    assert "CC BY 3.0" in card and "Kan" in card
    assert "Hold on, something here doesn’t add up." in card


def test_the_bar_s_faq_is_this_page_s_questions(shelf: None) -> None:
    page = after_duolingo_page(ADDRESS)
    assert '<a href="#questions">FAQ</a>' in page
    assert 'id="questions"' in page


def test_the_box_is_the_front_door_s_box_and_names_its_page(shelf: None) -> None:
    page = after_duolingo_page(ADDRESS)
    form = re.search(r'<form class="try-form" method="post" action="([^"]+)">', page)
    assert form and form.group(1) == "/try?lang=en#try"
    assert '<input type="hidden" name="on" value="after-duolingo-hebrew">' in page


def test_try_this_one_offers_a_first_text_s_own_link(shelf: None) -> None:
    """Under the box, one of the first texts' own links to try (David, 2026-11-12): the
    cola video's YouTube address, posted to the same box from a form of its own, so it
    works with JavaScript off."""
    page = after_duolingo_page(ADDRESS)
    chip = page.split('<form class="try-this" id="tryThis"', 1)[1].split("</form>", 1)[0]
    assert 'action="/try?lang=en#try"' in chip
    assert '<input type="hidden" name="on" value="after-duolingo-hebrew">' in chip
    assert (
        '<input type="hidden" name="link" value="https://www.youtube.com/watch?v=NEoaePzDhGc">'
        in chip
    )
    assert "Try this one" in chip
    assert "youtube.com/watch?v=NEoaePzDhGc" in chip


def test_without_the_row_nothing_is_offered_to_try(monkeypatch: pytest.MonkeyPatch) -> None:
    """A catalogue without the cola row offers no link it cannot back."""
    monkeypatch.setattr("targum.catalogue.by_id", lambda entry_id: None)
    assert 'id="tryThis"' not in after_duolingo_page(ADDRESS)


def test_a_signed_in_reader_is_not_asked_to_join(shelf: None) -> None:
    page = after_duolingo_page(ADDRESS, signed_in=True)
    assert '<input type="hidden" name="from"' not in page


# -- served ---------------------------------------------------------------------------


def test_the_page_answers_while_the_front_door_does(
    served: tuple[int, Store], shelf: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, _ = served
    monkeypatch.delenv("TARGUM_FRONT_DOOR", raising=False)
    status, _ = ask(port, "GET", "/after-duolingo-hebrew")
    assert status == 404
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    status, page = ask(port, "GET", "/after-duolingo-hebrew")
    assert status == 200
    assert "Why real Hebrew feels harder" in page


def test_joining_here_is_counted_as_here(
    served: tuple[int, Store], shelf: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store = served
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    ask(
        port,
        "POST",
        "/waitlist?lang=en",
        {"email": "noa@example.com", "from": "after-duolingo-hebrew"},
    )
    row = store.db.execute(
        "SELECT page FROM waiting WHERE email = ?", ("noa@example.com",)
    ).fetchone()
    assert row["page"] == "/after-duolingo-hebrew"


def test_a_try_here_answers_here_and_builds_nothing(
    served: tuple[int, Store], shelf: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, store = served
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")

    def describe(url: str) -> dict[str, Any]:
        return {"webpage_url": url, "title": "סביח", "duration": 540, "subtitles": {"he": [{}]}}

    monkeypatch.setattr("targum.video.ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.setattr("targum.video.youtube.describe", describe)
    status, page = ask(
        port,
        "POST",
        "/try?lang=en",
        {"link": "https://www.youtube.com/watch?v=abcdefghijk", "on": "after-duolingo-hebrew"},
    )
    assert status == 200
    assert "You finished Duolingo Hebrew." in page
    assert "That’s a YouTube video" in page
    # The waitlist under the answer carries the link and says where it was pressed.
    assert '<input type="hidden" name="from" value="after-duolingo-hebrew">' in page
    assert (
        '<input type="hidden" name="link" value="https://www.youtube.com/watch?v=abcdefghijk">'
        in page
    )
    # Described, never built: no job was written for it.
    assert store.db.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 0


def test_try_this_one_is_the_box_s_real_answer_and_builds_nothing(
    served: tuple[int, Store], shelf: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One press on "Try this one" is the box's own answer to that link, described and
    never built: no job is written (`Library.describe` never spends)."""
    port, store = served
    monkeypatch.setenv("TARGUM_FRONT_DOOR", "1")
    asked: list[str] = []

    def describe(url: str) -> dict[str, Any]:
        asked.append(url)
        return {
            "webpage_url": url,
            "title": "כאן מסבירים | למה קולה קטן עולה יותר מקולה גדול?",
            "duration": 181,
            "subtitles": {"iw": [{}]},
        }

    monkeypatch.setattr("targum.video.ytdlp_available", lambda: (True, "yt-dlp"))
    monkeypatch.setattr("targum.video.youtube.describe", describe)
    page = after_duolingo_page(ADDRESS)
    chip = page.split('id="tryThis"', 1)[1].split("</form>", 1)[0]
    form = dict(re.findall(r'<input type="hidden" name="(\w+)" value="([^"]+)">', chip))
    status, answer = ask(port, "POST", "/try?lang=en", form)
    assert status == 200
    assert asked == ["https://www.youtube.com/watch?v=NEoaePzDhGc"]
    assert "That’s a YouTube video" in answer
    assert "למה קולה קטן עולה יותר מקולה גדול?" in answer
    # The answer stands in the box, so the chip has done its work and goes.
    assert 'id="tryThis"' not in answer
    assert store.db.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 0


def test_the_clip_is_answered_in_ranges(served: tuple[int, Store]) -> None:
    """Safari opens a video with a two-byte probe and plays nothing unless it is a real
    206, so the clip is answered in ranges, as a reader's part is."""
    port, _ = served
    film = next(
        address for address, (_, _, name) in asset_files().items() if name.startswith("films/")
    )
    connection = HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", film, headers={"Range": "bytes=0-1"})
        response = connection.getresponse()
        assert response.status == 206
        assert response.getheader("Accept-Ranges") == "bytes"
        assert response.getheader("Content-Type") == "video/mp4"
        assert len(response.read()) == 2
    finally:
        connection.close()
