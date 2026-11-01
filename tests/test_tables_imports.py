"""What learners bring is pooled into the language tables as counts, behind a floor of
ten readers, without their text, without them, and never once they have said no (David,
2026-11-01; design.md §12, "What learners bring is counted in the tables, never kept").

Every token here is synthetic: placeholder lemmas, no sentence of any text.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from targum import tables
from targum.accounts import Store as AccountStore
from targum.cli import app
from targum.tables import imports, registers
from targum.tables.store import Contribution, Store
from targum.tables.words import PHRASES, ROOTS, WORDS

#: A string that stands for a reader's sentence: it is in the annotation and must be in
#: no row the tables hold.
SENTENCE = "zz-a-reader-s-own-sentence-zz"


def _token(lemma: str, pos: str = "NOUN", root: str | None = None) -> dict[str, Any]:
    token: dict[str, Any] = {"start": 0, "end": 1, "surface": SENTENCE, "lemma": lemma}
    token["pos"] = pos
    if root is not None:
        token["root"] = root
        token["binyan"] = "b1"
    return token


def _annotation(document_hash: str, lemmas: list[str]) -> dict[str, Any]:
    run = [_token(one) for one in lemmas] + [_token("v1", "VERB", root="r1")]
    return {
        "schema_version": 1,
        "document_hash": document_hash,
        "language": "he",
        "annotator": "dicta/test/1",
        "text": SENTENCE,
        "tokens": {"s0": run},
    }


def _brought(
    library: Path,
    person: int,
    name: str,
    lemmas: list[str],
    *,
    source: str = "",
    doc: str = "",
    ingester: str = "url/6",
) -> Path:
    folder = library / f"p{person}" / name
    folder.mkdir(parents=True, exist_ok=True)
    document_hash = doc or f"{person:04d}{name}".encode().hex().ljust(64, "0")[:64]
    document = {
        "content_hash": document_hash,
        "source": source or f"https://x.test/{name}",
        "ingester": ingester,
    }
    (folder / "document.json").write_text(json.dumps(document), encoding="utf-8")
    (folder / "annotation.json").write_text(
        json.dumps(_annotation(document_hash, lemmas)), encoding="utf-8"
    )
    return folder


@pytest.fixture
def book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    file = tmp_path / "corpus.db"
    monkeypatch.setenv("TARGUM_LEDGER", str(file))
    return file


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "library"
    root.mkdir()
    return root


def _person(accounts: AccountStore, email: str) -> Any:
    accounts.start_sign_in(email)
    person = accounts.person_by_email(email)
    assert person is not None
    return person


def _pooled(store: Store, table: str = WORDS) -> dict[str, int]:
    return dict(store.top(table, registers.IMPORTS, limit=1000, weighed=False))


def _every_cell(file: Path) -> str:
    """Every value of every row of every table in the file, as one string."""
    with sqlite3.connect(file) as db:
        names = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        cells = []
        for name in names:
            for row in db.execute(f"SELECT * FROM {name}"):  # noqa: S608
                cells.extend(str(value) for value in row)
    return "\n".join(cells)


def test_a_word_counts_only_once_ten_readers_have_brought_it(book: Path, library: Path) -> None:
    for person in range(1, 10):
        _brought(library, person, "a", ["common", f"rare{person}"])
    store = Store(book)
    imports.pool(library, store, set(range(1, 30)))
    assert _pooled(store) == {}, "nine readers are not enough"

    _brought(library, 10, "a", ["common"])
    imports.pool(library, store, set(range(1, 30)))
    pooled = _pooled(store)
    assert pooled == {"common": 10, "v1": 10}
    # One reader's word stays out, however often they used it.
    assert not any(key.startswith("rare") for key in pooled)
    # The phrase and the root ride the same floor: every phrase here but one has a rare
    # word in it, and that one ("common v1") only reader 10 wrote.
    assert _pooled(store, PHRASES) == {}
    assert _pooled(store, ROOTS) == {"r1": 10}


def test_one_reader_with_many_texts_is_one_reader(book: Path, library: Path) -> None:
    for name in "abcdefghijkl":
        _brought(library, 1, name, ["mine"])
    store = Store(book)
    result = imports.pool(library, store, {1})
    assert result.readers == 1 and result.texts == 12
    assert _pooled(store) == {}


def test_an_opted_out_reader_never_counts(book: Path, library: Path) -> None:
    for person in range(1, 11):
        _brought(library, person, "a", ["common"])
    store = Store(book)
    imports.pool(library, store, set(range(1, 11)))
    assert _pooled(store)["common"] == 10
    assert _pooled(store, PHRASES) == {"common v1": 10}

    # Reader 4 turns counting off: tonight's pool is made without them, and ten is now nine.
    result = imports.pool(library, store, set(range(1, 11)) - {4})
    assert result.left_out == 1 and result.readers == 9
    assert _pooled(store) == {}


def test_last_nights_pool_is_deleted_not_superseded(book: Path, library: Path) -> None:
    for person in range(1, 12):
        _brought(library, person, "a", ["common", "other"])
    store = Store(book)
    imports.pool(library, store, set(range(1, 12)))
    imports.pool(library, store, set(range(1, 12)) - {3})
    with sqlite3.connect(book) as db:
        held = db.execute(
            "SELECT tbl, unit, superseded_at FROM contribution WHERE register = ?",
            (registers.IMPORTS,),
        ).fetchall()
        tallies = db.execute(
            "SELECT COUNT(*) FROM tally WHERE contribution_id IN"
            " (SELECT id FROM contribution WHERE register = ?)",
            (registers.IMPORTS,),
        ).fetchone()[0]
    # One contribution a table, the pool's own unit, and no history beside it: the
    # difference between two nights would be one reader's material.
    assert sorted((tbl, unit) for tbl, unit, _ in held if unit == imports.UNIT) == sorted(
        (table, imports.UNIT) for table in imports.TABLES
    )
    assert all(at is None and unit.startswith(imports.UNIT) for _, unit, at in held)
    assert _pooled(store)["common"] == 10
    assert tallies == len(_pooled(store)) + len(_pooled(store, PHRASES)) + 1


def test_nothing_in_the_file_leads_back_to_a_reader_or_their_text(
    book: Path, library: Path
) -> None:
    folders = [_brought(library, person, "a", ["common"]) for person in range(31, 42)]
    _brought(library, 31, "b", ["onlyone"])
    store = Store(book)
    imports.pool(library, store, set(range(31, 42)))
    assert _pooled(store)["common"] == 11

    every = _every_cell(book)
    assert SENTENCE not in every, "no text"
    assert "onlyone" not in every, "no lemma under the floor"
    for folder in folders:
        document_hash = json.loads((folder / "document.json").read_text())["content_hash"]
        assert document_hash not in every, "no document"
        assert document_hash[:16] not in every
    for person in range(31, 42):
        assert f"p{person}" not in every, "no home"
    with sqlite3.connect(book) as db:
        units = {row[0] for row in db.execute("SELECT unit FROM contribution")}
        sources = {row[0] for row in db.execute("SELECT source FROM contribution")}
    assert all(unit.startswith(imports.UNIT) for unit in units)
    assert sources == {imports.SOURCE}


def test_the_file_keeps_no_copy_of_a_deleted_pool(book: Path, library: Path) -> None:
    """SQLite leaves a deleted row on its page until the page is reused; the pool asks for
    the pages to be overwritten, so an opted-out reader's lemma is not in the bytes."""
    for person in range(1, 11):
        _brought(library, person, "a", ["common", "zzlemmazz"])
    store = Store(book)
    imports.pool(library, store, set(range(1, 11)))
    assert "zzlemmazz" in _pooled(store)
    imports.pool(library, store, set(range(1, 11)) - {1})
    assert "zzlemmazz" not in _pooled(store)
    with sqlite3.connect(book) as db:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    raw = b"".join(path.read_bytes() for path in book.parent.glob("corpus.db*"))
    assert b"zzlemmazz" not in raw


def test_a_text_two_readers_brought_is_counted_once(book: Path, library: Path) -> None:
    shared = "ab" * 32
    for person in range(1, 11):
        _brought(library, person, "a", ["common", "common"], doc=shared)
    store = Store(book)
    imports.pool(library, store, set(range(1, 11)))
    assert _pooled(store)["common"] == 2, "counted once, with ten readers behind it"


def test_what_a_model_wrote_is_not_what_a_reader_brought(book: Path, library: Path) -> None:
    for person in range(1, 11):
        _brought(library, person, "s", ["scene"], source="dialogue:scene-01")
        _brought(library, person, "c", ["speech"], source="chat:7")
        rewritten = _brought(library, person, "r", ["rewrite"])
        (rewritten / "rewrite.json").write_text(json.dumps({"from": "a", "level": "a2"}))
    store = Store(book)
    result = imports.pool(library, store, set(range(1, 11)))
    assert result.model_written == 30 and result.texts == 0
    assert _pooled(store) == {}


def test_the_laptop_home_and_a_home_with_no_account_are_never_read(
    book: Path, library: Path
) -> None:
    for person in range(1, 11):
        _brought(library, person, "a", ["common"])
    local = library / "local" / "x"
    local.mkdir(parents=True)
    store = Store(book)
    result = imports.pool(library, store, set(range(1, 10)))
    assert result.left_out == 1 and _pooled(store) == {}


def test_the_public_fold_still_writes_nothing_for_a_home(book: Path, library: Path) -> None:
    """The old guard stands: a reader's text is never a unit of its own in any register."""
    folder = _brought(library, 1, "a", ["common"])
    assert tables.public_text(folder, library) is None
    assert tables.sweep(library, Store(book)).private == 1
    with pytest.raises(ValueError):
        Store(book).write(
            Contribution(WORDS, registers.IMPORTS, "x" * 64, "s", "l", "t", "r"), {("a", ""): 1}
        )


def test_the_pool_never_travels(book: Path, library: Path, tmp_path: Path) -> None:
    for person in range(1, 11):
        _brought(library, person, "a", ["common"])
    store = Store(book)
    imports.pool(library, store, set(range(1, 11)))
    assert list(store.export("laptop")) == [], "the pool is not pushed"

    line = {
        "contribution": {
            "id": "f" * 64,
            "tbl": WORDS,
            "register": registers.IMPORTS,
            "unit": imports.UNIT,
            "source": "s",
            "licence": "l",
            "tool": "t",
            "origin": "laptop",
            "written_at": "2026-11-01T00:00:00+00:00",
            "superseded_at": None,
        },
        "tally": [["planted", "NOUN", 99]],
    }
    box = Store(tmp_path / "box.db")
    assert box.import_rows([json.dumps(line)]).refused == 1


def test_the_switch_off_deletes_the_pool(
    book: Path, library: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    accounts = AccountStore(tmp_path / "targum.db")
    for person in range(1, 11):
        _person(accounts, f"reader{person}@x.test")
    ids = sorted(accounts.counted_readers())
    for person in ids:
        _brought(library, person, "a", ["common"])

    monkeypatch.setenv(imports.ENV, "1")
    command = ["tables", "sweep", "--library", str(library), "--store", str(accounts.path)]
    done = CliRunner().invoke(app, command)
    assert done.exit_code == 0, done.output
    assert _pooled(Store(book))["common"] == 10

    # Without the account database nobody's material is read, and the pool stands as it
    # was until a night that can say whose counts.
    done = CliRunner().invoke(app, ["tables", "sweep", "--library", str(library)])
    assert "Pooled nothing" in done.output

    monkeypatch.delenv(imports.ENV)
    done = CliRunner().invoke(app, command)
    assert done.exit_code == 0, done.output
    assert _pooled(Store(book)) == {}
    with sqlite3.connect(book) as db:
        assert not db.execute(
            "SELECT 1 FROM contribution WHERE register = ?", (registers.IMPORTS,)
        ).fetchone()


def test_who_may_be_counted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    accounts = AccountStore(tmp_path / "targum.db")
    reader = _person(accounts, "reader@x.test")
    quiet = _person(accounts, "quiet@x.test")
    operator = _person(accounts, "o.wner+beta@gmail.com")
    accounts.make_test_account("tester@x.test")
    accounts.make_admin("admin@x.test")
    admin = _person(accounts, "admin@x.test")
    tester = _person(accounts, "tester@x.test")
    assert {admin.id, tester.id}.isdisjoint(accounts.counted_readers())

    assert accounts.counts_material(reader.id), "on by default"
    accounts.set_counts_material(quiet, False)
    assert not accounts.counts_material(quiet.id)

    assert accounts.counted_readers(["owner@gmail.com"]) == {reader.id}
    accounts.set_counts_material(quiet, True)
    assert quiet.id in accounts.counted_readers()
    assert operator.id not in accounts.counted_readers(["owner@gmail.com"])


@pytest.mark.parametrize(
    ("source", "ingester", "expected"),
    [
        ("https://www.ynet.co.il/news/article/abc", "url/6", "news"),
        ("https://www.instagram.com/reel/AbC123/", "subtitles/1", "social"),
        ("https://www.tiktok.com/@someone/video/7300000000000000000", "audio/2", "social"),
        ("https://x.com/someone/status/1800000000000000000", "post/1", "social"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "subtitles/1", "video"),
        ("https://podcasts.apple.com/il/podcast/x/id123", "url/6", "podcasts"),
        ("https://media.example.org/episode-12.mp3", "audio/2", "podcasts"),
        ("/var/lib/targum/targums/p3/uploads/menu.jpg", "picture/2", "everyday"),
        ("/var/lib/targum/targums/p3/uploads/form.pdf", "pdf/1", "everyday"),
        ("https://he.wikipedia.org/wiki/x", "url/6", "imports"),
        ("/var/lib/targum/targums/p3/uploads/book.epub", "epub/4", "imports"),
        ("", "", "imports"),
    ],
)
def test_a_brought_text_is_sorted_by_its_source(source: str, ingester: str, expected: str) -> None:
    """From what is already written beside the text, and nothing else (David, 2026-11-01).
    A host is news only when it is a news publisher's; anything unclear is imports."""
    assert imports.sort(source, ingester, news={"ynet.co.il"}) == expected
    if expected == "news":
        assert imports.sort(source, ingester) == "imports", "news only from the list"


def test_the_floor_is_counted_in_each_register(book: Path, library: Path) -> None:
    """Five readers' videos and five readers' posts hold a word: ten readers in all, but
    five in each register, so it is written in neither."""
    for person in range(1, 6):
        _brought(library, person, "v", ["shared"], source="https://youtu.be/dQw4w9WgXcQ")
    for person in range(6, 11):
        _brought(library, person, "s", ["shared"], source="https://www.instagram.com/p/AbC/")
    store = Store(book)
    result = imports.pool(library, store, set(range(1, 11)))
    assert result.by_register == {"video": 5, "social": 5}
    for register in ("video", "social", "imports"):
        assert "shared" not in dict(
            store.top(WORDS, registers.pooled(register), limit=100, weighed=False)
        )

    for person in range(11, 16):
        _brought(library, person, "v", ["shared"], source="https://youtu.be/dQw4w9WgXcQ")
    imports.pool(library, store, set(range(1, 16)))
    video = dict(store.top(WORDS, registers.pooled("video"), limit=100, weighed=False))
    assert video["shared"] == 10
    assert "shared" not in _pooled(store), "and only in video"


def test_news_hosts_come_from_the_publishers_and_the_finds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    listed = tmp_path / "sources.json"
    listed.write_text(
        json.dumps(
            {
                "publishers": [
                    {"key": "a", "homepage": "https://www.ynet.co.il/", "kind": "news"},
                    {"key": "b", "homepage": "https://pod.example.org/", "kind": "podcast"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("TARGUM_SOURCES", str(listed))
    accounts = AccountStore(tmp_path / "targum.db")
    accounts.db.execute(
        "INSERT INTO find (language, source, url, host, found, expires, medium)"
        " VALUES ('he', 'news', 'https://www.maariv.co.il/a', 'www.maariv.co.il', 1, 2, 'text')"
    )
    # A live search's web find is not news for being found.
    accounts.db.execute(
        "INSERT INTO find (language, source, url, host, found, expires, medium)"
        " VALUES ('he', 'web', 'https://blog.example.org/a', 'blog.example.org', 1, 2, 'text')"
    )
    accounts.db.commit()
    assert imports.news_hosts(accounts) == {"ynet.co.il", "maariv.co.il"}
