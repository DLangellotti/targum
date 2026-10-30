"""The language tables count public texts only, never twice, and never leave
(targum-internal#577).

Every token here is synthetic: placeholder lemmas, no sentence of any text.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from targum import ledger, tables
from targum.cli import app
from targum.tables import registers, weights
from targum.tables.store import Store
from targum.tables.words import PHRASES, ROOTS, TABLES, WORDS, count

H = {name: name * 64 for name in "abcdef"}


def _token(
    lemma: str, pos: str, entity: str | None = None, root: str | None = None
) -> dict[str, Any]:
    token: dict[str, Any] = {"start": 0, "end": 1, "surface": lemma, "lemma": lemma, "band": 1}
    token["pos"] = pos
    if entity is not None:
        token["entity"] = entity
    if root is not None:
        token["root"] = root
        token["binyan"] = "b1"
    return token


#: Two segments: "w1 of w2 w3" and "name and w1". Lemmas only, no text; the verb's root
#: is a placeholder too.
TOKENS = {
    "s0": [
        _token("w1", "NOUN"),
        _token("f1", "ADP"),
        _token("w2", "NOUN"),
        _token("w3", "VERB", root="r3"),
    ],
    "s1": [
        _token("n1", "PROPN", "B-PER"),
        _token("f2", "CCONJ"),
        _token("w1", "NOUN"),
    ],
}
WORD_COUNT = 7


def _annotation(document_hash: str, annotator: str = "dicta/test/1") -> dict[str, Any]:
    return {
        "schema_version": 1,
        "document_hash": document_hash,
        "language": "he",
        "annotator": annotator,
        "method": "test",
        "method_note": "synthetic",
        "band_count": 6,
        "tokens": TOKENS,
    }


def _built(folder: Path, document_hash: str, annotator: str = "dicta/test/1") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    document = {"content_hash": document_hash, "source": f"test:{document_hash[:4]}"}
    (folder / "document.json").write_text(json.dumps(document), encoding="utf-8")
    (folder / "annotation.json").write_text(
        json.dumps(_annotation(document_hash, annotator)), encoding="utf-8"
    )
    return folder


@pytest.fixture
def book(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The corpus ledger, switched on, in a file of its own."""
    file = tmp_path / "corpus.db"
    monkeypatch.setenv("TARGUM_LEDGER", str(file))
    return file


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "library"
    root.mkdir()
    return root


def _rows(file: Path, table: str) -> int:
    if not file.is_file():
        return 0
    with sqlite3.connect(file) as db:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone():
            return 0
        return int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608


def test_a_home_writes_nothing_and_the_shelf_writes_rows(book: Path, library: Path) -> None:
    private = _built(library / "p1" / "x", H["a"])
    shelf = _built(library / "shared" / "y", H["b"])

    assert tables.public_text(private, library) is None
    text = tables.public_text(shelf, library)
    assert text is not None

    store = Store(book)
    assert tables.fold(text, _annotation(H["b"]), store) == len(TABLES)
    assert store.total(WORDS) == WORD_COUNT
    with sqlite3.connect(book) as db:
        units = {row[0] for row in db.execute("SELECT unit FROM contribution")}
    assert units == {H["b"]}


def test_a_private_text_writes_no_root_rows(book: Path, library: Path) -> None:
    store = Store(book)
    _built(library / "p1" / "x", H["a"])
    _built(library / "local" / "x", H["c"])
    assert tables.sweep(library, store).private == 2
    assert store.total(ROOTS) == 0
    assert _rows(book, "tally") == 0

    # The same annotation on the shelf counts its verb's root, under the root's own rule.
    text = tables.public_text(_built(library / "shared" / "y", H["b"]), library)
    assert text is not None
    assert tables.fold(text, _annotation(H["b"]), store) == len(TABLES)
    assert store.top(ROOTS, registers.UNFILED) == [("r3", 1)]
    with sqlite3.connect(book) as db:
        units = {row[0] for row in db.execute("SELECT unit FROM contribution WHERE tbl = 'roots'")}
    assert units == {H["b"]}


def test_every_home_fails_closed(library: Path, tmp_path: Path) -> None:
    for home in ("p1", "p22", "local"):
        assert tables.public_text(_built(library / home / "x", H["a"]), library) is None
    # The top folder decides, whatever lies beneath it.
    assert tables.public_text(_built(library / "p3" / "local" / "x", H["a"]), library) is None
    # A library that is itself a home is that home.
    assert tables.public_text(_built(library / "p4" / "y", H["a"]), library / "p4") is None
    # With no root known, nothing is counted at all, home or not.
    assert tables.public_text(_built(tmp_path / "loose" / "z", H["a"])) is None
    # Nor a folder outside the root it is asked under.
    assert tables.public_text(_built(tmp_path / "elsewhere" / "z", H["a"]), library) is None


def test_the_ledger_saying_private_is_enough(book: Path, library: Path) -> None:
    shelf = _built(library / "shared" / "y", H["c"])
    ledger.Ledger(book).record_text(
        ledger.Text(H["c"], "upload.pdf", "Public Domain", frozenset({"p9"}), "pdf/1", 1)
    )
    assert tables.public_text(shelf, library) is None


def test_sweep_skips_every_home_and_counts_a_text_once_it_is_public(
    book: Path, library: Path
) -> None:
    for home in ("p1", "p22", "local"):
        _built(library / home / "x", H["a"])
    _built(library / "p3" / "local" / "x", H["a"])
    _built(library / "shared" / "y", H["b"])
    _built(library / "shared" / "z", H["c"])
    book_ = ledger.Ledger(book)
    book_.record_text(ledger.Text(H["c"], "test:c", "Public Domain", frozenset({"p1"}), "t", 1))
    store = Store(book)

    first = tables.sweep(library, store)
    assert first.folded == 1
    assert first.private == 5
    with sqlite3.connect(book) as db:
        units = {row[0] for row in db.execute("SELECT unit FROM contribution")}
    assert units == {H["b"]}

    # The private text is later built on the shelf, and the next sweep counts it then.
    book_.hold(ledger.Text(H["c"], "test:c", "Public Domain", frozenset(), "t", 1), None)
    second = tables.sweep(library, store)
    assert second.folded == 1
    assert second.unchanged == 1
    assert store.total(WORDS) == 2 * WORD_COUNT

    # And a sweep with nothing new writes nothing.
    rows = _rows(book, "tally")
    third = tables.sweep(library, store)
    assert third.folded == 0
    assert _rows(book, "tally") == rows


def test_a_new_annotator_name_supersedes_rather_than_doubles(book: Path, library: Path) -> None:
    store = Store(book)
    text = tables.public_text(_built(library / "shared" / "y", H["b"]), library)
    assert text is not None

    assert tables.fold(text, _annotation(H["b"], "dicta/test/1"), store) == len(TABLES)
    assert tables.fold(text, _annotation(H["b"], "dicta/test/1"), store) == 0
    assert _rows(book, "contribution") == len(TABLES)
    assert tables.fold(text, _annotation(H["b"], "dicta/test/2"), store) == len(TABLES)

    assert store.total(WORDS) == WORD_COUNT
    with sqlite3.connect(book) as db:
        held = db.execute(
            "SELECT tool, superseded_at IS NULL FROM contribution WHERE tbl = 'words'"
            " ORDER BY written_at, tool"
        ).fetchall()
    # The old count stays, to compare the two annotators by; only the new one is current.
    assert sorted(held) == [("dicta/test/1", 0), ("dicta/test/2", 1)]

    # Renamed back, the first is current again, and still nothing doubles.
    assert tables.fold(text, _annotation(H["b"], "dicta/test/1"), store) == len(TABLES)
    assert store.total(WORDS) == WORD_COUNT
    assert _rows(book, "contribution") == 2 * len(TABLES)


def test_the_sweep_sees_a_rename_on_disk(book: Path, library: Path) -> None:
    store = Store(book)
    _built(library / "shared" / "y", H["b"], "dicta/test/1")
    assert tables.sweep(library, store).folded == 1
    _built(library / "shared" / "y", H["b"], "dicta/test/2")
    assert tables.sweep(library, store).folded == 1
    assert store.total(WORDS) == WORD_COUNT


def test_corpus_export_writes_no_tally_rows(book: Path, library: Path, tmp_path: Path) -> None:
    book_ = ledger.Ledger(book)
    book_.record_text(ledger.Text(H["b"], "test:b", "Public Domain", frozenset(), "t", 1))
    book_.record("tokens", H["b"], _annotation(H["b"]))
    _built(library / "shared" / "y", H["b"])
    assert tables.sweep(library, Store(book)).folded == 1
    assert _rows(book, "tally") > 0
    with sqlite3.connect(book) as db:
        ids = [row[0] for row in db.execute("SELECT id FROM contribution")]

    for kind in ("--exportable", "--research"):
        out = tmp_path / f"export{kind}"
        result = CliRunner().invoke(app, ["corpus", "export", str(out), kind])
        assert result.exit_code == 0, result.output
        names = {path.name for path in out.iterdir()}
        assert "tokens.jsonl" in names  # the export ran, and carried the text it could
        assert not any("tally" in name or "contribution" in name for name in names)
        written = "".join(path.read_text(encoding="utf-8") for path in out.iterdir())
        assert not any(one in written for one in ids)
        assert "tally" not in written


def test_fold_takes_only_a_public_text(book: Path, library: Path) -> None:
    forged = tables.PublicText(library / "p1" / "x", H["a"], "upload.pdf", "", "news")
    with pytest.raises(TypeError):
        tables.fold(forged, _annotation(H["a"]), Store(book))
    text = tables.public_text(_built(library / "shared" / "y", H["b"]), library)
    assert text is not None
    # Another document's annotation is not filed under this one.
    with pytest.raises(ValueError):
        tables.fold(text, _annotation(H["a"]), Store(book))
    assert _rows(book, "tally") == 0


def test_the_ledger_off_writes_nothing(library: Path, tmp_path: Path) -> None:
    text = tables.public_text(_built(library / "shared" / "y", H["b"]), library)
    assert text is not None
    assert tables.fold(text, _annotation(H["b"])) == 0
    assert not list(tmp_path.rglob("*.db"))


def test_names_become_one_key_and_glue_is_not_a_phrase() -> None:
    counted = count(TOKENS)
    words = counted[WORDS]
    assert words[(weights.NAME, "PROPN")] == 1
    assert ("n1", "PROPN") not in words
    assert words[("w1", "NOUN")] == 2
    phrases = {key for key, _variant in counted[PHRASES]}
    assert "w1 f1 w2" in phrases
    assert f"{weights.NAME} f2 w1" in phrases
    # A name beside a function word is all glue: a name is not vocabulary either.
    assert f"{weights.NAME} f2" not in phrases
    # Never across two segments.
    assert "w3 " + weights.NAME not in phrases


def test_top_weighs_out_function_words_and_keeps_them_raw(book: Path, library: Path) -> None:
    store = Store(book)
    _built(library / "shared" / "y", H["b"])
    tables.sweep(library, store)
    register = registers.UNFILED
    weighed = dict(store.top(WORDS, register))
    raw = dict(store.top(WORDS, register, weighed=False))
    assert "f1" not in weighed and weights.NAME not in weighed
    assert raw["f1"] == 1 and raw[weights.NAME] == 1
    assert weighed["w1"] == 2


def _entry(**fields: Any) -> SimpleNamespace:
    base: dict[str, Any] = {"tags": frozenset(), "kind": "prose", "register": ""}
    return SimpleNamespace(**{**base, **fields})


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (_entry(tags=frozenset({"journalism"}), kind="article"), registers.NEWS),
        (_entry(kind="article", register="modern"), registers.NEWS),
        (_entry(tags=frozenset({"tanakh"}), register="biblical"), registers.BIBLE),
        (_entry(kind="story", register="revival"), registers.LITERATURE),
        (_entry(kind="talk", register="modern"), registers.CONVERSATION),
        (_entry(kind="essay", register="medieval"), "medieval"),
        (None, registers.UNFILED),
    ],
)
def test_registers_come_from_the_catalogue(
    monkeypatch: pytest.MonkeyPatch, entry: SimpleNamespace | None, expected: str
) -> None:
    from targum import catalogue

    monkeypatch.setattr(catalogue, "matching", lambda _source: entry)
    assert registers.register_of("test:x") == expected


def test_scenes_feed_no_yardstick_by_default() -> None:
    assert registers.register_of("dialogue:scene-01-x") == registers.SCENES
    assert registers.SCENES not in registers.YARDSTICKS
    assert registers.register_of("weekly:2026-10-26") not in registers.YARDSTICKS
