"""A day of the Tanakh cycles, read aloud in Be'eri's reading of its books (2026-10-13).

The same plain reading a portion carries beside its chanting: the day's verses cut out of
each chapter's file, kept in `audio/` beside the pages and served as sound. What can go
wrong is the same addressing a portion has — a day that starts mid-chapter must not open
on the verse before it, and a chapter Be'eri never recorded must be silent rather than
handed another chapter's sound — and then the route, which until now served pages only.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from datetime import date
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_parasha_cut import a_book
from test_two_recordings import chapter_part, shelve, stand_in  # noqa: F401 - a fixture

from targum.accounts import Store
from targum.audio import PAD
from targum.daily.calendar import Day
from targum.daily.cycles import CYCLES, RECITED, parse_reference
from targum.ids import slug
from targum.mail import ConsoleMailer
from targum.recording import Recording

TODAY = date(2026, 10, 13)

#: Where each book sits on the test shelf, by the name a cycle calls it.
BOOKS = {"Psalms": "תהלים", "Isaiah": "ישעיהו", "Jeremiah": "ירמיהו"}


def a_day(cycle: str, reference: str) -> Day:
    return Day(
        day=TODAY,
        cycle=cycle,
        title=reference,
        hebrew="",
        hdate="1 Cheshvan 5787",
        reference=reference,
        span=parse_reference(reference),
    )


@pytest.fixture
def built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stand_in) -> Path:  # noqa: F811
    """Three days built: Psalms 1-2 with only Psalm 1 recorded, a seder of Isaiah that
    starts and ends inside a chapter, and a chapter of Jeremiah, which Be'eri did not
    record at all."""
    from targum.daily import build as daily_build
    from targum.daily import cut as daily_cut

    monkeypatch.setenv("TARGUM_PARASHA_DIR", str(tmp_path / "parasha"))
    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "1")
    monkeypatch.setenv("TARGUM_RECORDING_DIR", str(tmp_path / "recordings"))
    monkeypatch.setattr(
        daily_cut,
        "entry_for",
        lambda name: SimpleNamespace(english=name, title=BOOKS[name]) if name in BOOKS else None,
    )
    library = tmp_path / "library"
    a_book(library / f"{slug(BOOKS['Psalms'])}-he", "Psalms", BOOKS["Psalms"], {1: 6, 2: 12})
    a_book(library / f"{slug(BOOKS['Isaiah'])}-he", "Isaiah", BOOKS["Isaiah"], {1: 31, 2: 22})
    a_book(library / f"{slug(BOOKS['Jeremiah'])}-he", "Jeremiah", BOOKS["Jeremiah"], {1: 19})
    for book, chapters in (("Psalms", ((1, 6),)), ("Isaiah", ((1, 31), (2, 22)))):
        shelve(
            tmp_path / "recordings",
            Recording(
                source=f"sefaria:{book}",
                credit="Rabbi Dan Be'eri",
                licence="CC BY-SA 3.0",
                licence_url="https://creativecommons.org/licenses/by-sa/3.0/",
                parts=[chapter_part(book, c, n) for c, n in chapters],
            ),
        )
    days = [
        a_day("tehillim", "Psalms 1-2"),
        a_day("tanakh-yomi", "Isaiah 1:27-2:4"),
        a_day("nach-yomi", "Jeremiah 1"),
    ]
    monkeypatch.setattr(daily_build, "today", lambda: TODAY)
    monkeypatch.setattr(daily_build, "window", lambda first, last: days)
    daily_build.build(library=library, ahead=1, behind=0)
    return tmp_path / "parasha" / "daily" / "read"


def payload(page: str) -> dict:
    found = re.search(
        r'<script type="application/json" id="targum-data">(.*?)</script>', page, re.S
    )
    assert found, "the page carries its data"
    return json.loads(found.group(1))


def reader(built: Path, cycle: str) -> Path:
    return built / cycle / TODAY.isoformat() / "reader"


def test_the_tanakh_cycles_are_read_aloud_and_the_mishnah_is_not() -> None:
    assert {cycle.slug for cycle in CYCLES} - RECITED == {"mishna-yomi"}


def test_a_psalm_is_heard_from_beside_the_page(built: Path) -> None:
    home = reader(built, "tehillim")
    page = (home / "sec-0001.html").read_text(encoding="utf-8")
    speech = payload(page)["speech"]
    assert speech["audio"] == "audio/spoken-0001.mp3"
    assert speech["spans"], "it follows along verse by verse"
    assert (home / "audio" / "spoken-0001.mp3").is_file()
    assert "data:audio" not in page, "beside the page, not inside it"
    assert "Read by Rabbi Dan Be" in page


def test_a_chapter_with_no_recording_is_silent(built: Path) -> None:
    second = (reader(built, "tehillim") / "sec-0002.html").read_text(encoding="utf-8")
    assert not payload(second).get("speech", {}).get("audio")
    assert not (reader(built, "tehillim") / "audio" / "spoken-0002.mp3").exists()
    jeremiah = reader(built, "nach-yomi")
    assert not (jeremiah / "audio").exists(), "Be'eri did not record Jeremiah"


def test_a_seder_inside_two_chapters_hears_only_its_own_verses(built: Path, stand_in) -> None:  # noqa: F811
    first = (reader(built, "tanakh-yomi") / "sec-0001.html").read_text(encoding="utf-8")
    spans = payload(first)["speech"]["spans"]
    assert len(spans) == 5, "Isaiah 1:27-31, and nothing before it"
    # Verse 27 sits at [54, 55.5] in the chapter's file. The cut breathes a margin back
    # from it and stops short of verse 26, which ends at 53.5, so the day opens on its
    # own first verse after a breath and never on the end of the one before.
    assert min(span[0] for span in spans.values()) == pytest.approx(PAD)
    assert PAD < 0.5, "the margin fits in the quiet between verses 26 and 27"
    cuts = [round(seconds, 3) for pieces in stand_in for _, seconds in pieces]
    assert cuts, "the chapters were cut, not carried whole"
    assert all(seconds < 100 for seconds in cuts)


@pytest.fixture
def serving(tmp_path: Path, built: Path) -> Iterator[int]:
    from targum.serve import Handler, Library

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


def test_a_days_reading_is_served_as_sound(serving: int) -> None:
    base = f"/tehillim/read/{TODAY.isoformat()}/reader/audio"
    conn = HTTPConnection("127.0.0.1", serving)
    conn.request("GET", f"{base}/spoken-0001.mp3", headers={"Range": "bytes=0-2"})
    answer = conn.getresponse()
    assert answer.status == 206, "a player seeks by ranges"
    assert answer.getheader("Content-Type") == "audio/mpeg"
    assert answer.read() == b"ID3"
    conn.close()
    for wrong in (f"{base}/nothing.mp3", f"{base}/../sec-0001.mp3", f"{base}/x.wav"):
        conn = HTTPConnection("127.0.0.1", serving)
        conn.request("GET", wrong)
        assert conn.getresponse().status == 404, wrong
        conn.close()
