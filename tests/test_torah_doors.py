"""Every way into the Torah opens the portion that reads it, at the verse
(targum-internal#446).

The five books are read as the 54 portions and nothing else (David, 2026-10-12): the map,
the Library, a reference typed into Add, the connector and an old address of a book's
reader all land on `/torah/<ref>`, which answers with the portion's reader open at the
verse. These are the pieces each of those leans on.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

import pytest

from targum import catalogue as catalogue_module
from targum.accounts import Store
from targum.catalogue import Entry
from targum.chat import tools
from targum.mail import ConsoleMailer
from targum.parasha import build as corpus
from targum.parasha import calendar as cal
from targum.parasha.models import Index, Portion
from targum.render import builder
from targum.serve import Handler, Library

STARTS = json.loads(Path(corpus.__file__).with_name("starts.json").read_text(encoding="utf-8"))

#: Lech-Lecha's first two aliyot as its reader's contents draw them, and the rest of it
#: as one, so a verse anywhere in the portion has a file to land in.
LECH_LECHA = [("12:1", "12:13", "sec-0001.html"), ("12:14", "17:27", "sec-0002.html")]


def cycle() -> Index:
    """The 54, each read on its own and begun where `starts.json` says."""
    index = Index()
    for number, row in enumerate(STARTS, start=1):
        index.portions[row["slug"]] = Portion(
            slug=row["slug"],
            name=row["name"],
            hebrew=row["hebrew"],
            kind=cal.ReadingKind.parasha,
            numbers=[number],
            summary=row["summary"],
            books=[row["book"]],
            opening_ref=f"{row['book']} {row['chapter']}:{row['verse']}",
            folder=row["slug"],
            aliyot=7,
        )
    return index


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TARGUM_PARASHA_DIR", str(tmp_path / "parasha"))
    here = tmp_path / "parasha"
    index = cycle()
    for portion in index.portions.values():
        reader = here / "read" / portion.folder / "reader"
        reader.mkdir(parents=True)
        (reader / "index.html").write_text("<html></html>", encoding="utf-8")
    sections = [
        {"number": n, "file": page, "from": first, "to": last}
        for n, (first, last, page) in enumerate(LECH_LECHA, start=1)
    ]
    (here / "read" / "lech-lecha" / "reader" / "contents.json").write_text(
        json.dumps({"sections": sections}), encoding="utf-8"
    )
    russian = here / "read" / "lech-lecha" / "reader-ru"
    russian.mkdir()
    (russian / "index.html").write_text("<html></html>", encoding="utf-8")
    (here / "index.json").write_text(index.model_dump_json(), encoding="utf-8")
    return here


# -- where a verse is read ------------------------------------------------------------


def test_every_portion_begins_where_it_begins_and_the_verse_before_is_the_last_ones(
    root: Path,
) -> None:
    """Both edges of all 54: the first verse opens its own portion, and the verse before
    it opens the portion read the week before."""
    checked = 0
    for before, row in zip([None, *STARTS], STARTS, strict=False):
        place = corpus.locate(row["book"], row["chapter"], row["verse"])
        assert place is not None and place.slug == row["slug"], row["slug"]
        checked += 1
        if before is None or before["book"] != row["book"]:
            continue
        chapter, verse = row["chapter"], row["verse"] - 1
        if verse == 0:
            # The chapter before, from its first verse where the earlier portion holds it
            # (no table here says how long a chapter is).
            chapter, verse = chapter - 1, 1
            if (chapter, verse) < (before["chapter"], before["verse"]):
                continue
        earlier = corpus.locate(row["book"], chapter, verse)
        assert earlier is not None and earlier.slug == before["slug"], row["slug"]
        checked += 1
    assert checked > 54 + 40, "every start, and the verse before nearly every one"


def test_a_verse_lands_in_the_aliyah_that_holds_it(root: Path) -> None:
    first = corpus.locate("Genesis", 12, 13)
    second = corpus.locate("Genesis", 12, 14)
    assert (
        first is not None and first.href() == "/parasha/read/lech-lecha/reader/sec-0001.html#12:13"
    )
    assert second is not None and second.page == "sec-0002.html" and second.anchor == "12:14"


def test_a_reader_in_russian_lands_in_the_russian_reader(root: Path) -> None:
    place = corpus.locate("Genesis", 12, 1)
    assert place is not None
    assert place.href("ru") == "/parasha/read/lech-lecha-ru/reader/sec-0001.html#12:1"
    other = corpus.locate("Genesis", 6, 9)
    assert other is not None and other.href("ru").startswith("/parasha/read/noach/"), (
        "a portion with no Russian reader keeps its own"
    )


def test_a_reader_with_no_contents_opens_at_its_index_which_sends_the_verse_on(root: Path) -> None:
    place = corpus.locate("Genesis", 6, 9)
    assert place is not None and place.href() == "/parasha/read/noach/reader/index.html#6:9"


def test_nothing_past_a_portions_last_verse_or_in_an_unbuilt_one(root: Path) -> None:
    assert corpus.locate("Genesis", 17, 28) is None, "past Lech-Lecha's contents"
    assert corpus.locate("Genesis", 0, 1) is None
    assert corpus.locate("Isaiah", 1, 1) is None
    (root / "read" / "noach" / "reader" / "index.html").unlink()
    assert corpus.locate("Genesis", 6, 9) is None, "an address that would 404 is no answer"


def test_the_hebrew_name_of_a_book_is_the_same_book(root: Path) -> None:
    place = corpus.locate("בראשית", 12, 1)
    assert place is not None and place.slug == "lech-lecha"


# -- the map and the Library ----------------------------------------------------------


def test_the_map_opens_a_torah_chapter_in_its_portion(root: Path) -> None:
    year = builder.tanakh_year()
    lech = next(one for one in year if one["slug"] == "lech-lecha")
    assert lech["href"] == "/torah/Genesis.12.1", "the strip opens the reader, not the page"


def test_a_torah_chapter_square_opens_its_portion(root: Path) -> None:
    torah = next(part for part in builder.tanakh_map() if part["part"] == "torah")
    genesis_book = torah["books"][0]["halves"][0]["chapters"]
    assert genesis_book[11]["href"] == "/torah/Genesis.12.1"
    assert genesis_book[11]["portion"] == "Lech-Lecha"


def genesis(entry_id: str = "genesis", source: str = "sefaria:Genesis") -> Entry:
    return Entry(
        id=entry_id,
        title="בראשית",
        author="",
        language="he",
        source=source,
        blurb="",
        words=1,
        english="Genesis",
    )


def test_the_library_lists_no_torah_book_where_the_portions_are_built(root: Path) -> None:
    assert builder.read_as_portions(genesis())
    assert not builder.read_as_portions(genesis("rashi", "sefaria:he:Rashi on Genesis"))
    assert not builder.read_as_portions(genesis("chapter", "sefaria:Genesis 12")), (
        "a chapter somebody built is theirs"
    )


def test_without_the_portions_the_book_stays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TARGUM_PARASHA_DIR", str(tmp_path / "nothing"))
    assert not builder.read_as_portions(genesis()), "the Torah is never missing altogether"


# -- the doors on the server ----------------------------------------------------------


@pytest.fixture
def serving(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[int, Path]]:
    monkeypatch.setattr(catalogue_module, "CATALOGUE", [genesis()])
    out = tmp_path / "targum-out"
    out.mkdir()
    library = Library(out)
    # The shared shelf's Genesis, as every box has it, and a chapter of it somebody built.
    for name, source in (("בראשית-he", "sefaria:Genesis"), ("בראשית-12", "sefaria:Genesis 12")):
        book = library.shared / name
        (book / "reader").mkdir(parents=True)
        (book / "document.json").write_text(json.dumps({"source": source}), encoding="utf-8")
        (book / "reader" / "sec-0012.html").write_text("<html>book</html>", encoding="utf-8")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    server.RequestHandlerClass = type(
        "TestHandler",
        (Handler,),
        {
            "library": library,
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
        yield port, library.shared
    finally:
        server.shutdown()
        server.server_close()


def get(port: int, path: str) -> tuple[int, str, str]:
    conn = HTTPConnection("127.0.0.1", port)
    conn.request("GET", path)
    answer = conn.getresponse()
    body = answer.read().decode("utf-8")
    conn.close()
    return answer.status, answer.getheader("Location") or "", body


def post(port: int, path: str, payload: dict[str, object]) -> dict[str, object]:
    conn = HTTPConnection("127.0.0.1", port)
    conn.request(
        "POST",
        path + "?k=test-key",
        body=json.dumps(payload),
        headers={"Content-Type": "application/json", "X-Targum-Key": "test-key"},
    )
    answer = conn.getresponse()
    body = answer.read().decode("utf-8")
    conn.close()
    found = json.loads(body)
    assert isinstance(found, dict)
    return found


@pytest.mark.parametrize(
    ("asked", "lands"),
    [
        ("Genesis.12.14", "/parasha/read/lech-lecha/reader/sec-0002.html?k=test-key#12:14"),
        (quote("בראשית יב א"), "/parasha/read/lech-lecha/reader/sec-0001.html?k=test-key#12:1"),
        (quote("Lech Lecha"), "/parasha/read/lech-lecha/reader/sec-0001.html?k=test-key#12:1"),
        ("Genesis.6.9", "/parasha/read/noach/reader/index.html?k=test-key#6:9"),
    ],
)
def test_a_reference_opens_its_portion_at_the_verse(
    serving: tuple[int, Path], asked: str, lands: str
) -> None:
    status, where, _ = get(serving[0], f"/torah/{asked}?k=test-key")
    assert (status, where) == (302, lands)


def test_a_russian_reader_is_sent_to_the_russian_reader(serving: tuple[int, Path]) -> None:
    status, where, _ = get(serving[0], "/torah/Genesis.12.1?k=test-key&lang=ru")
    assert status == 302 and where.startswith("/parasha/read/lech-lecha-ru/reader/sec-0001.html")


def test_a_reference_to_no_verse_is_a_page_that_is_not_there(serving: tuple[int, Path]) -> None:
    for asked in ("Genesis.51.1", "Isaiah.1.1", quote("hello there")):
        assert get(serving[0], f"/torah/{asked}?k=test-key")[0] == 404, asked


def test_an_old_address_of_the_book_forwards_with_its_verse(serving: tuple[int, Path]) -> None:
    status, _, body = get(
        serving[0], "/reader/" + quote("בראשית-he") + "/reader/sec-0012.html?k=test-key"
    )
    assert status == 200
    assert "location.replace(" in body and "/torah/Genesis." in body, "the verse is read off #"
    assert 'href="/torah/Genesis.12.1"' in body, "and without a script, the chapter"
    assert "book" not in body.split("<body>")[1], "the book itself is not served"


def test_a_chapter_somebody_built_is_still_theirs_to_read(serving: tuple[int, Path]) -> None:
    status, _, body = get(
        serving[0], "/reader/" + quote("בראשית-12") + "/reader/sec-0012.html?k=test-key"
    )
    assert (status, body) == (200, "<html>book</html>")


def test_the_books_catalogue_door_opens_the_portions(
    serving: tuple[int, Path], tmp_path: Path
) -> None:
    shutil_target = serving[1] / "בראשית-he"
    for page in shutil_target.joinpath("reader").iterdir():
        page.unlink()
    shutil_target.joinpath("reader").rmdir()
    status, where, _ = get(serving[0], "/open/genesis?k=test-key")
    assert status == 302 and where.startswith("/torah/Genesis"), "never an offer to build it"


@pytest.mark.parametrize(
    ("typed", "opens"),
    [
        ("Genesis 12:14", "/torah/Genesis.12.14"),
        ("בראשית", "/torah/Genesis.1.1"),
        ("https://www.sefaria.org/Genesis.12.1?lang=bi", "/torah/Genesis.12.1"),
    ],
)
def test_add_says_a_reference_is_already_here_and_where(
    serving: tuple[int, Path], typed: str, opens: str
) -> None:
    found = post(serving[0], "/already", {"text": typed})
    assert found["opens"] == opens


def test_add_says_nothing_of_text_that_only_starts_like_one(serving: tuple[int, Path]) -> None:
    assert "opens" not in post(serving[0], "/already", {"text": "בראשית ברא אלהים"})


# -- the connector --------------------------------------------------------------------


def portion_entry(slug: str, summary: str) -> Entry:
    return Entry(
        id=f"parasha-{slug}",
        title=slug,
        author="",
        language="he",
        source=f"sefaria:{summary}",
        blurb=f"{summary}. A portion.",
        words=1,
        english=slug.title(),
    )


def connector(tmp_path: Path) -> tools.Ctx:
    ctx = tools.Ctx(
        person=None,
        home=tmp_path,
        library=Library(tmp_path / "out"),
        store=Store(tmp_path / "words.db"),
        chat_id="c",
        level=tools.level_module.EMPTY,
    )
    ctx.press_at = "https://targum.test"
    return ctx


def test_find_text_puts_the_portion_of_a_verse_first(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        catalogue_module,
        "CATALOGUE",
        [genesis(), portion_entry("lech-lecha", "Genesis 12:1-17:27")],
    )
    found = tools.find_text(connector(tmp_path), {"query": "Genesis 12:14", "where": "library"})
    first = found["texts"][0]
    assert first["id"] == "parasha-lech-lecha" and first["verse"] == "Genesis 12:14"
    assert first["reader"] == "https://targum.test/torah/Genesis.12.14"
    assert [row["id"] for row in found["texts"]].count("parasha-lech-lecha") == 1


def test_a_portion_and_a_torah_book_open_without_a_build(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        catalogue_module,
        "CATALOGUE",
        [genesis(), portion_entry("lech-lecha", "Genesis 12:1-17:27")],
    )
    ctx = connector(tmp_path)
    portion = tools.open_library_text(ctx, {"id": "parasha-lech-lecha"})
    assert portion["on_shelf"] is True
    assert portion["reader"] == "https://targum.test/parasha/read/lech-lecha/reader/index.html"
    book = tools.open_library_text(ctx, {"id": "genesis"})
    assert book["on_shelf"] is True and book["reader"] == "https://targum.test/torah/Genesis"
