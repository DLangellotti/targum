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

import json
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
from targum.strings import catalogue, said_portion

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
    found = re.search(rf'<iframe\s+name="{name}"\s+src="([^"]+)"', body)
    assert found, f"no {name} frame"
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
    parts = re.findall(r'<a class="week-part" href="([^"]+)" target="reading"', body)
    assert parts and all(f"/parasha/read/{SLUG}-ru/reader/" in href for href in parts)
    # The haftarah has no Russian, so its frame is the one it has.
    haftarah = re.findall(r'<a class="week-part" href="([^"]+)" target="haftarah"', body)
    assert haftarah and "-ru/" not in haftarah[0]
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


def test_next_shabbat_from_the_russian_reader_answers_in_russian(serving: int) -> None:
    status, body = get(serving, f"/parasha/next/{SLUG}-ru")
    assert status == 200
    offered = json.loads(body)["next"]
    if offered is None:
        pytest.skip("the fixture's calendar has nothing after this reading")
    assert offered["page"].endswith("?lang=ru")
    assert re.search(r"[А-Яа-я]", offered["name"]), offered["name"]
    english = json.loads(get(serving, f"/parasha/next/{SLUG}")[1])["next"]
    assert not english["page"].endswith("?lang=ru") and "-ru/" not in english["href"]


def text_of(body: str) -> str:
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", body, flags=re.S)
    return re.sub(r"<[^>]+>", " ", body)


def test_the_named_portion_page_says_its_book_its_name_and_shabbat_in_russian(
    serving: int,
) -> None:
    body = get(serving, f"/parasha/{SLUG}?lang=ru")[1]
    assert '<p class="eyebrow">Второзаконие</p>' in body
    assert "Ницавим-Ваелех — каждое слово с разбором." in body
    assert "читают в субботу" in body
    words = text_of(body)
    for english in ("Shabbat", "Deuteronomy", "Nitzavim", "GENESIS", "Genesis"):
        assert english not in words, english
    assert "<title>Ницавим-Ваелех — " in body
    # Whose words stand beside the verse: the Russian Torah, since the frame is Russian.
    assert "Герштейна и Гордона" in body and "Мецуда, опубликованный" not in body


def test_the_english_page_is_what_it_was(serving: int) -> None:
    body = get(serving, f"/parasha/{SLUG}")[1]
    assert '<p class="eyebrow">Deuteronomy</p>' in body
    assert "is read on Shabbat" in body
    assert "Nitzavim-Vayeilech, every word explained." in body
    assert "the Metsudah linear translation" in body


def test_a_language_pressed_for_rides_on_the_links_that_stay_here(serving: int) -> None:
    body = get(serving, f"/parasha/{SLUG}?lang=ru")[1]
    assert 'href="?taamim=off&amp;lang=ru"' in body or 'href="?taamim=off&lang=ru"' in body
    assert 'href="/parasha?lang=ru#sources"' in body
    for href in re.findall(r'<a class="story" href="([^"]+)"', body):
        assert href.endswith("?lang=ru"), href
    # Inferred from the browser rather than pressed, nothing is carried.
    plain = get(serving, f"/parasha/{SLUG}")[1]
    assert "lang=ru" not in plain.partition("<main")[2].partition("</main>")[0]


def test_the_pdf_form_is_still_a_plain_link_without_a_script(serving: int) -> None:
    body = get(serving, f"/parasha/{SLUG}?lang=ru")[1]
    form = body.partition('<form class="sheet-choices"')[2].partition("</form>")[0]
    assert f'action="/parasha/{SLUG}.pdf" method="get"' in form
    assert '<button type="submit" class="btn tonal sheet">Скачать PDF</button>' in form


def test_the_sheet_pressed_in_the_russian_reader_is_the_portions(
    serving: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reader's print link names the portion as its folder does, `…-ru.pdf`."""
    from targum.parasha import sheet

    asked: list[tuple[str, str]] = []

    def make(slug: str, **kwargs: object) -> None:
        asked.append((slug, str(kwargs.get("language"))))
        return None

    monkeypatch.setattr(sheet, "make", make)
    assert get(serving, f"/parasha/{SLUG}-ru.pdf")[0] == 404
    assert asked == [(SLUG, "ru")]


# -- the strings ------------------------------------------------------------------------


def test_every_portion_has_a_russian_name(built: Index) -> None:
    russian = catalogue("ru")
    english = catalogue("en")
    for slug in built.portions:
        assert f"portion.name.{slug}" in english, slug
        assert re.search(r"[А-Яа-я]", russian.get(f"portion.name.{slug}", "")), slug


def test_a_portion_is_named_in_english_exactly_as_the_calendar_wrote_it() -> None:
    assert said_portion("bereshit", "Bereshit", "en") == "Bereshit"
    assert said_portion("bereshit", "Bereshit", "ru") == "Берешит"
    assert said_portion("made-up", "Made Up", "ru") == "Made Up"
