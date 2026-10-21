"""The portion page in Russian, and the reader it frames (QA, 2026-10-05).

`/parasha/bereshit?lang=ru` framed the English reader — Listen, Chanted, "0 of 99
known" and the English column — and said "GENESIS" and «читают Shabbat» around it. The
reader's words are written into it when it is built, so a portion with a Russian
rendering is built twice: `reader/` as before, and `reader-ru/` with the Russian first,
served at `/parasha/read/<folder>-ru/reader/…`.

The corpus here is the one `test_parasha_page` builds, with a Russian rendering beside
the English in the book, so the whole path — build, page, frame, reader — is real.
"""

from __future__ import annotations

import re
import shutil
import threading
from collections.abc import Iterator
from datetime import datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from test_parasha_cut import a_book
from test_parasha_page import FIXTURES, get, raw

from targum.accounts import Store
from targum.mail import ConsoleMailer
from targum.models import Document, Translation
from targum.parasha import build as corpus_build
from targum.parasha import calendar as cal
from targum.parasha.models import Index
from targum.serve import Handler, Library

SLUG = "nitzavim-vayeilech"


def russian_beside(book: Path, name: str) -> None:
    """A Russian rendering of a fixture book, verse for verse, as `published:ru` makes."""
    document = Document.model_validate_json((book / "document.json").read_text("utf-8"))
    segments = {block.id: f"Русский стих {block.ref}" for block in document.blocks if block.ref}
    Translation(
        name="Второзаконие",
        document_hash=document.content_hash,
        source_language="he",
        target_language="ru",
        provider="aligned",
        segments=segments,
    ).write(book / "translations" / f"aligned.{name.lower()}.ru.json")


@pytest.fixture
def built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Index:
    """One week's reading, built from a Deuteronomy carrying English and Russian, and its
    haftarah from an Isaiah carrying English alone."""
    monkeypatch.setenv("TARGUM_PARASHA_DIR", str(tmp_path / "parasha"))
    monkeypatch.setenv("TARGUM_PUBLIC_SHELVES", "1")
    a_wednesday = datetime(2026, 9, 2, 12, tzinfo=ZoneInfo(cal.FLIP_ZONE))
    monkeypatch.setattr(cal, "now_in_flip_zone", lambda moment=None: a_wednesday)
    (tmp_path / "parasha" / "calendar").mkdir(parents=True)
    for one in FIXTURES.glob("*.json"):
        shutil.copy(one, tmp_path / "parasha" / "calendar" / one.name)
    library = tmp_path / "library"
    a_book(library / "דברים-he", "Deuteronomy", "דברים", {29: 29, 30: 20, 31: 30})
    russian_beside(library / "דברים-he", "Deuteronomy")
    a_book(library / "ישעיהו-he", "Isaiah", "ישעיהו", {61: 11, 62: 12, 63: 19})
    a_book(library / "חבקוק-he", "Habakkuk", "חבקוק", {3: 19})
    return corpus_build.build(
        years=[2026], corpus_years=[2026], schedules=[cal.Schedule.diaspora], library=library
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


# -- the build --------------------------------------------------------------------------


def test_a_reading_with_a_russian_rendering_is_built_again_in_russian(built: Index) -> None:
    reader = cal.root() / "read" / SLUG / "reader-ru"
    assert (reader / "index.html").is_file() and (reader / "sec-0001.html").is_file()
    page = (reader / "sec-0001.html").read_text("utf-8")
    assert '<html lang="ru"' in page, "the reader's own words are Russian"
    assert "Русский стих Deuteronomy 29:9" in page, "and the column it opens on"
    english = (cal.root() / "read" / SLUG / "reader" / "sec-0001.html").read_text("utf-8")
    assert '<html lang="en"' in english, "the first build is the one it always was"
    assert corpus_build.served_as(SLUG, "ru") == f"{SLUG}-ru"
    assert corpus_build.served_as(SLUG, "en") == SLUG


def test_the_russian_build_keeps_no_second_copy_of_the_recordings(built: Index) -> None:
    assert not (cal.root() / "read" / SLUG / "reader-ru" / "audio").exists()


def test_a_reading_with_no_russian_has_no_russian_reader(built: Index) -> None:
    """The haftarah's book carries English alone: its page frames the reader it has."""
    haftarot = [one.folder for one in built.haftarot.values() if one.folder]
    assert haftarot
    for folder in haftarot:
        assert not corpus_build.built_in(folder, "ru")
        assert corpus_build.served_as(folder, "ru") == folder


def test_a_served_name_is_read_back_to_its_folder_and_language(built: Index) -> None:
    folders = corpus_build.readable()
    assert corpus_build.read_as(f"{SLUG}-ru", folders) == (SLUG, "ru")
    assert corpus_build.read_as(SLUG, folders) == (SLUG, "en")
    assert corpus_build.read_as("made-up-ru", folders) == ("made-up-ru", "en")


# -- the page ---------------------------------------------------------------------------


def frame(body: str, name: str = "reading") -> str:
    """Where the page opens a reading: its press for the portion, the haftarah's row for
    the haftarah (no frame since 2026-10-09; design.md §12)."""
    if name == "haftarah":
        found = re.search(r'href="(/parasha/read/haftarah-[^"]+)"', body)
    else:
        found = re.search(
            r'<p class="series-go[^"]*">\s*<a class="btn filled" href="([^"]+)"', body
        )
        found = found or re.search(
            r'<div class="series-go series-go-row">\s*<a class="btn filled" href="([^"]+)"', body
        )
    assert found, f"no {name} press"
    return found.group(1)


def test_the_russian_page_frames_the_russian_reader(serving: int) -> None:
    status, body = get(serving, f"/parasha/{SLUG}?lang=ru")
    assert status == 200
    assert frame(body) == f"/parasha/read/{SLUG}-ru/reader/sec-0001.html"
    status, english = get(serving, f"/parasha/{SLUG}")
    assert frame(english) == f"/parasha/read/{SLUG}/reader/sec-0001.html"


def test_this_weeks_russian_page_names_its_parts_in_the_russian_reader(serving: int) -> None:
    body = get(serving, "/parasha?lang=ru")[1]
    assert frame(body) == f"/parasha/read/{SLUG}-ru/reader/sec-0001.html"
    rows = body.split('<ol class="rows series-parts">')[1].split("</ol>")[0]
    parts = re.findall(r'<a class="series-row-title" href="([^"]+)"', rows)
    aliyot = [href for href in parts if "haftarah-" not in href]
    assert aliyot and all(f"/parasha/read/{SLUG}-ru/reader/" in href for href in aliyot)
    # The haftarah has no Russian, so its row opens the one it has.
    assert "-ru/" not in frame(body, "haftarah")


def test_the_russian_reader_is_served_and_its_recordings_come_from_the_first_build(
    serving: int,
) -> None:
    status, body = get(serving, f"/parasha/read/{SLUG}-ru/reader/sec-0001.html")
    assert status == 200 and '<html lang="ru"' in body
    audio = cal.root() / "read" / SLUG / "reader" / "audio"
    audio.mkdir(exist_ok=True)
    (audio / "chanted-0001.mp3").write_bytes(b"ID3 not really a recording")
    assert get(serving, f"/parasha/read/{SLUG}-ru/reader/audio/chanted-0001.mp3")[0] in (200, 206)
    assert get(serving, f"/parasha/read/{SLUG}-xx/reader/index.html")[0] == 404
    assert raw(serving, f"/parasha/read/{SLUG}-ru/reader/../../../../etc/passwd") == 404


def test_the_russian_reader_reads_on_into_the_next_portions_russian_reader(serving: int) -> None:
    """targum-internal#446: past the last aliyah, the next portion in the book — in the
    reader built in Russian, named in Russian, and never the English one."""
    status, body = get(serving, f"/parasha/read/{SLUG}-ru/reader/sec-0007.html")
    assert status == 200
    onward = re.search(r'<a class="next beyond" href="([^"]+)" data-page="([^"]+)"', body)
    assert onward is not None
    assert onward.group(1) == "/parasha/read/vzot-haberachah-ru/reader/sec-0001.html"
    assert onward.group(2) == "/parasha/vzot-haberachah?lang=ru"
    # The reader it names is there, in Russian.
    there = get(serving, "/parasha/read/vzot-haberachah-ru/reader/index.html")
    assert there[0] == 200 and '<html lang="ru"' in there[1]
    back = get(serving, f"/parasha/read/{SLUG}-ru/reader/sec-0001.html")[1]
    assert 'class="prev beyond" href="/parasha/read/vzot-haberachah-ru/reader/' in back
    english = get(serving, f"/parasha/read/{SLUG}/reader/sec-0007.html")[1]
    assert 'href="/parasha/read/vzot-haberachah/reader/sec-0001.html"' in english


def test_the_librarys_portions_say_their_verses_in_the_readers_names_of_the_books(
    serving: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Library QA, 2026-10-20: under the Russian interface this week's card on the
    Library's Weekly portion shelf said «Бытие 12:1…» and every other card "Genesis …"."""
    import json

    english = json.loads(get(serving, "/portions?k=test-key")[1])["portions"]
    said = [one["summary"] for one in english if one.get("summary")]
    assert said and any("Deuteronomy" in one for one in said)
    monkeypatch.setattr(Handler, "_ui_language", lambda self: "ru")
    russian = json.loads(get(serving, "/portions?k=test-key")[1])["portions"]
    said = [one["summary"] for one in russian if one.get("summary")]
    assert said and not [one for one in said if "Deuteronomy" in one]
    assert any("Дварим" in one for one in said)
