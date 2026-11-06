"""A source is private unless its kind is listed public (David, 2026-11-06;
targum-internal#653).

`novel:` stands for a kind somebody added and forgot to list, and `novel/1` for the
ingester that read it. Every writer of the corpus ledger and the tables, every export
and the shelf must leave such a text out; the back office must name its kind; and every
kind the audit found must be listed, so no row that exists today changes.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from targum import corpus_export, kinds, ledger, promote, tables
from targum.accounts import SCHEMA
from targum.backoffice import survey
from targum.ingest import fetch
from targum.models import Segment
from targum.render.builder import back_office_page
from targum.tables import imports
from targum.tables.store import Store

#: What the audit of 2026-11-06 found: every scheme in the laptop's library (1,037 built
#: texts), its tables (972 contributions) and the catalogue (1,695 rows), and every
#: scheme the code writes into a `document.json`. The PR carries the table.
AUDITED_KINDS = {
    "catalogue": "code: Build.PUBLIC_SOURCES, a catalogue row by id",
    "dialogue": "library 202, catalogue 381, tables 300",
    "globalstorybooks": "library 34, catalogue 164",
    "gutenberg": "library 3, catalogue 2",
    "http": "code: a link",
    "https": "library 144 (url, url-text), catalogue 369, tables 6",
    "published": "code: fetch/published.py",
    "sefaria": "library 289 (sefaria, parasha), catalogue 224, tables 309",
    "siddur": "library 1, catalogue 3",
    "storyweaver": "library 100, catalogue 100",
    "video": "library 42 (video, audio), catalogue 376",
    "weekly": "library 26, tables 63",
    "wikisource": "library 69, catalogue 76, tables 6",
}

#: The ingesters that read a file with no scheme, by family: the library's 127 such texts
#: and every file ingester the code has.
AUDITED_INGESTERS = {
    "audio": "library 27 (the curated videos' sound)",
    "epub": "code: ingest/epub.py",
    "markdown": "library 91",
    "pdf": "code: ingest/pdf.py",
    "picture": "library 4",
    "subtitles": "code: ingest/subtitles.py",
    "text": "library 2",
    "transcript": "library 3",
}

UNLISTED = "novel:1"
UNLISTED_INGESTER = "novel/1"
H = "ab" * 32


def _write(folder: Path, source: str, ingester: str, document_hash: str = H) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    document = {
        "schema_version": 4,
        "source": source,
        "language": "he",
        "blocks": [],
        "content_hash": document_hash,
        "ingester": ingester,
    }
    (folder / "document.json").write_text(json.dumps(document), encoding="utf-8")
    annotation = {
        "schema_version": 1,
        "document_hash": document_hash,
        "language": "he",
        "annotator": "dicta/test/1",
        "tokens": {"s0": [{"start": 0, "end": 1, "surface": "x", "lemma": "l1", "pos": "NOUN"}]},
    }
    (folder / "annotation.json").write_text(json.dumps(annotation), encoding="utf-8")
    return folder


def _rows(file: Path) -> dict[str, int]:
    with sqlite3.connect(file) as db:
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return {
            name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]  # noqa: S608
            for name in names
            if name != "meta"
        }


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "library"
    (root / "shared").mkdir(parents=True)
    return root


@pytest.fixture
def book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    file = tmp_path / "corpus.db"
    monkeypatch.setenv(ledger.ENV, str(file))
    return file


# --- The list ---------------------------------------------------------------------------


def test_every_audited_kind_is_listed_and_nothing_else() -> None:
    assert kinds.PUBLIC_KINDS - {"test"} == set(AUDITED_KINDS)
    assert set(AUDITED_INGESTERS) == kinds.PUBLIC_INGESTERS
    assert not kinds.PRIVATE & (kinds.PUBLIC_KINDS | kinds.PUBLIC_INGESTERS)


def test_the_suite_s_fixture_kind_is_not_in_the_module() -> None:
    """`conftest.py` lists `test` for the fixture catalogue; no deployment does."""
    text = Path(kinds.__file__).read_text(encoding="utf-8")
    assert '"test"' not in text


def test_every_fetcher_is_declared_one_way_or_the_other() -> None:
    for name in fetch.FETCHERS:
        assert name in kinds.PUBLIC_KINDS or name in kinds.PRIVATE, name
    assert fetch.private_source is kinds.private_source and fetch.PRIVATE is kinds.PRIVATE


def test_every_file_ingester_is_listed() -> None:
    from targum.ingest import _BY_SUFFIX
    from targum.ingest.audio import AudioIngester
    from targum.ingest.picture import PictureIngester
    from targum.ingest.transcript import NAME

    names = {one.name for one in _BY_SUFFIX.values()}
    names |= {AudioIngester.name, PictureIngester.name, NAME}
    for name in names:
        assert kinds.family(name) in kinds.PUBLIC_INGESTERS, name


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        ("sefaria:Psalms", "sefaria"),
        ("HTTPS://he.wikinews.org/x", "https"),
        ("/srv/p3/uploads/ab12/notes:1.txt", ""),
        ("targum-out/curated-build/a:b/audio/source.mp4", ""),
        ("targum-out/curated-build/האריה/audio/source.mp4", ""),
        ("ספר:1", ""),
        ("", ""),
        ("novel:1", "novel"),
    ],
)
def test_the_kind_is_the_scheme_and_a_path_has_none(source: str, kind: str) -> None:
    assert kinds.kind_of(source) == kind


@pytest.mark.parametrize(
    ("source", "ingester", "private"),
    [
        ("sefaria:Leviticus 19:1-20:27", "parasha/1", False),
        ("https://he.globalvoices.org/x", "url/6", False),
        ("video:ih_5Q8eht5U", "audio/2", False),
        ("/srv/p3/uploads/ab12", "picture/2", False),
        ("/srv/p3/uploads/ab12", "", True),
        ("/srv/p3/uploads/ab12", UNLISTED_INGESTER, True),
        (UNLISTED, "markdown/5", True),
        (UNLISTED, "", True),
        ("", "", True),
    ],
)
def test_private_unless_listed(source: str, ingester: str, private: bool) -> None:
    assert kinds.private_source(source, ingester) is private


def test_private_wins_over_public(monkeypatch: pytest.MonkeyPatch) -> None:
    """How targum#1121's `course` drops in: by kind, and by the ingester that read it."""
    monkeypatch.setattr(kinds, "PRIVATE", frozenset({"course"}))
    monkeypatch.setattr(kinds, "PUBLIC_KINDS", kinds.PUBLIC_KINDS | {"course"})
    assert kinds.private_source("course:it:b:1")
    assert kinds.private_source("https://x.test/a", "course/1")
    assert kinds.private_source("/srv/a.md", "course/1")


# --- Withheld everywhere ----------------------------------------------------------------


def test_the_tables_never_count_it(library: Path) -> None:
    listed = _write(library / "shared" / "a", "sefaria:Ruth", "sefaria/6", "cd" * 32)
    unlisted = _write(library / "shared" / "b", UNLISTED, UNLISTED_INGESTER)
    as_file = _write(library / "shared" / "c", "/srv/c.nov", UNLISTED_INGESTER, "ef" * 32)
    assert tables.public_text(listed, library) is not None
    assert tables.public_text(unlisted, library) is None
    assert tables.public_text(as_file, library) is None


def test_the_ledger_never_writes_a_row_of_it(book: Path, library: Path) -> None:
    folder = _write(library / "shared" / "b", UNLISTED, UNLISTED_INGESTER)
    (folder / "translations").mkdir()
    (folder / "translations" / "en.json").write_text(
        json.dumps({"document_hash": H, "segments": {"s0": "x"}}), encoding="utf-8"
    )
    book_ = ledger.Ledger(book)
    text = ledger.Text(H, UNLISTED, "Public Domain", frozenset(), UNLISTED_INGESTER, 4)
    assert book_.record_text(text) is False
    assert book_.hold(text, None) is False
    assert book_.hold(text, "p3") is False
    ledger.mirror_text(folder, library)
    assert ledger.backfill_texts(book_, library) == (0, 0)
    assert ledger.record_translations(book_, folder, root=library) == (0, 0)
    ledger.withhold(H)
    book_.record(
        "vocalize",
        "k" * 64,
        {
            "document_hash": H,
            "language": "he",
            "vocalizer": "v/1",
            "model": None,
            "segments": {"s0": "x"},
            "machine": [],
            "rejected": [],
        },
    )
    # A listed text, so the ledger is plainly on: its row is the only one.
    book_.record_text(ledger.Text("cd" * 32, "gutenberg:1", "Public Domain", frozenset(), "g/3", 4))
    rows = _rows(book)
    assert rows.pop("texts") == 1 and set(rows.values()) == {0}


class _Named:
    model = None
    name = "fake/1"

    def available(self) -> tuple[bool, str]:
        return True, ""

    def vocalize(self, segments: list[Segment], language: str) -> dict[str, str]:
        return {segment.id: segment.text for segment in segments}


def test_a_build_of_it_leaves_nothing_in_the_ledger(
    book: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_segmenter: object,
) -> None:
    from targum.pipeline import Build

    source = tmp_path / "text.md"
    source.write_text("# כותרת\n\nאבא בא. אמא באה.\n", encoding="utf-8")
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(ledger, "_licence_of", lambda _folder, _source: "Public Domain")
    (tmp_path / "out" / "shared").mkdir(parents=True)

    def build(name: str) -> None:
        Build(
            str(source),
            provider_name="null",
            out=tmp_path / "out" / "shared" / name,
            segmenter=fake_segmenter,  # type: ignore[arg-type]
            target_language="en",
            vocalizer=_Named(),  # type: ignore[arg-type]
        ).run()

    # Markdown is listed, so the build is recorded, and the ledger is truly on.
    build("text-he")
    listed = _rows(book)
    assert listed["texts"] == 1 and listed["vocalizations"] == 1
    # The same file, read by an ingester nobody listed: nothing more is written.
    book.unlink()
    monkeypatch.setattr(kinds, "PUBLIC_INGESTERS", kinds.PUBLIC_INGESTERS - {"markdown"})
    monkeypatch.setenv("TARGUM_CACHE_DIR", str(tmp_path / "cache-2"))
    build("again-he")
    assert not book.exists() or set(_rows(book).values()) <= {0}


def test_the_pool_never_counts_it(book: Path, library: Path) -> None:
    _write(library / "p1" / "a", "https://x.test/a", "url/6", "cd" * 32)
    _write(library / "p1" / "b", UNLISTED, UNLISTED_INGESTER)
    _write(library / "p2" / "c", "/srv/p2/uploads/c", UNLISTED_INGESTER, "ef" * 32)
    result = imports.pool(library, Store(book), {1, 2}, floor=1)
    assert result.texts == 1 and result.withheld == 2


def test_the_corpus_export_never_carries_it(book: Path, tmp_path: Path) -> None:
    """Asked again at export, so a row written before the list, or by hand, is refused."""
    book_ = ledger.Ledger(book)
    book_.record_text(ledger.Text(H, "gutenberg:1", "Public Domain", frozenset(), "gutenberg/3", 4))
    sheet = corpus_export.export(book, tmp_path / "before", "exportable")
    assert sheet["rows"]["texts"] == 1
    with sqlite3.connect(book) as db:
        db.execute("UPDATE texts SET source = ?", (UNLISTED,))
    sheet = corpus_export.export(book, tmp_path / "after", "exportable")
    assert sheet["rows"]["texts"] == 0


def test_the_shelf_never_proposes_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    joined: list[Any] = []
    monkeypatch.setattr(promote, "join_find", lambda *args, **kwargs: joined.append(args))
    job = SimpleNamespace(
        kind="build", reader="b-he", home=tmp_path, source=UNLISTED, options={"via": "find"}
    )
    assert promote.candidate(object(), object(), job) is None  # type: ignore[arg-type]
    assert joined == []
    job.source = "https://x.test/a"
    promote.candidate(object(), object(), job)  # type: ignore[arg-type]
    assert len(joined) == 1, "a listed kind still reaches the shelf's own rules"


# --- The back office names the kind -----------------------------------------------------


def test_the_back_office_names_each_withheld_kind(library: Path) -> None:
    _write(library / "shared" / "a", "sefaria:Ruth", "sefaria/6", "cd" * 32)
    _write(library / "shared" / "b", UNLISTED, UNLISTED_INGESTER)
    _write(library / "p4" / "c", "novel:2", UNLISTED_INGESTER, "ef" * 32)
    _write(library / "p4" / "d", str(library / "p4" / "uploads" / "d"), "novel/1", "aa" * 32)
    found = kinds.withheld_kinds(library)
    assert found == Counter({"novel:": 2, "a file read by novel": 1})

    db = sqlite3.connect(":memory:")
    db.executescript(SCHEMA)
    page = back_office_page(survey(db, today=date(2026, 11, 6)), 30, withheld=found)
    assert "Withheld: unknown kind" in page and "novel:" in page
    assert "a file read by novel" in page
    assert str(library) not in page, "a source is never named, only its kind"
    quiet = back_office_page(survey(db, today=date(2026, 11, 6)), 30)
    assert "Nothing is withheld." in quiet


def test_the_server_counts_at_most_every_ten_minutes(
    library: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from targum import serve

    monkeypatch.setattr(serve, "_withheld_seen", {})
    _write(library / "shared" / "b", UNLISTED, UNLISTED_INGESTER)
    assert serve.withheld_survey(library, now=0.0) == {"novel:": 1}
    _write(library / "shared" / "c", "novel:3", UNLISTED_INGESTER, "ef" * 32)
    assert serve.withheld_survey(library, now=1.0) == {"novel:": 1}
    assert serve.withheld_survey(library, now=serve.WITHHELD_FOR + 1) == {"novel:": 2}


# --- Today's data -----------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("TARGUM_AUDIT_LIBRARY"),
    reason="set TARGUM_AUDIT_LIBRARY to a library to audit (the laptop's targum-out)",
)
def test_nothing_built_today_is_withheld(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run by hand against a real library: every text built so far is of a listed kind,
    so no ledger row, table count or pool entry that exists today changes."""
    monkeypatch.setattr(kinds, "PUBLIC_KINDS", kinds.PUBLIC_KINDS - {"test"})
    root = Path(os.environ["TARGUM_AUDIT_LIBRARY"])
    assert kinds.withheld_kinds(root) == Counter()
