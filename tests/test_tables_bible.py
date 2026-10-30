"""The bible register's backfill (targum-internal#578): `count_tanakh.py --counts` writes
both keyings as contributions from the per-book cache and leaves `tanakh.json` alone.

Every word here is synthetic: placeholder lemmas, no verse of any text.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from targum.annotate import oshb, scripture
from targum.tables import bible
from targum.tables.store import Store

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "count_tanakh.py"


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("count_tanakh", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _word(headword: str, code: str) -> oshb.Word:
    return oshb.Word(headword, (headword,), ("1",), (code,))


def test_the_aramaic_verses_are_the_ones_the_card_names() -> None:
    for ref in ("Gen.31.47", "Jer.10.11", "Dan.2.4", "Dan.5.31", "Dan.7.28", "Ezra.4.8"):
        assert bible.is_aramaic(ref), ref
    for ref in ("Ezra.6.18", "Ezra.7.12", "Ezra.7.26"):
        assert bible.is_aramaic(ref), ref
    for ref in ("Gen.31.46", "Jer.10.10", "Dan.2.3", "Dan.8.1", "Ezra.4.7", "Ezra.6.19"):
        assert not bible.is_aramaic(ref), ref
    assert not bible.is_aramaic("Ezra.7.11") and not bible.is_aramaic("Ezra.7.27")
    assert not bible.is_aramaic("1Chr.2.4") and not bible.is_aramaic("not a ref")


def test_the_tagging_code_gives_a_universal_pos() -> None:
    assert bible.upos("Ncfsa") == "NOUN"
    assert bible.upos("Npm") == "PROPN"
    assert bible.upos("Vqp3ms") == "VERB"
    assert bible.upos("Td") == "DET"
    assert bible.upos("To") == "PART"
    assert bible.upos("R") == "ADP"
    assert bible.upos("") == ""


def test_the_aramaic_share_never_takes_more_than_the_book_held() -> None:
    split = bible.split_lemmas({"w1": 5, "w2": 2, "w3": 1}, {"w1": 2, "w2": 9, "w4": 3})
    assert split == {("w1", ""): 3, ("w1", "arc"): 2, ("w2", "arc"): 2, ("w3", ""): 1}
    assert sum(split.values()) == 8, "the two always add up to the book"
    assert bible.split_lemmas({"w1": 1}, None) == {("w1", ""): 1}


def test_a_lexeme_is_counted_by_its_headword_and_aramaic_by_its_variant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scripture, "headword_of", lambda word: word.text)
    monkeypatch.setattr(scripture, "is_section", lambda word: word.text == "§")
    verses = [
        ("Dan.1.1", (_word("w1", "Ncmsa"), _word("§", "x"), _word("w2", "Vqp3ms"))),
        ("Dan.2.4", (_word("w1", "Ncmsa"), _word("w3", "Npm"))),
    ]
    assert bible.count_lexemes(verses) == {
        ("w1", "NOUN"): 1,
        ("w2", "VERB"): 1,
        ("w1", "arc"): 1,
        ("w3", "arc"): 1,
    }


def test_only_the_two_keyings_are_written(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        bible.write(Store(tmp_path / "corpus.db"), "phrases", "Gen", "t", bible.Counter())


@pytest.fixture
def tanakh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A synthetic Tanakh: every book one verse of two words, a cache for each, an
    Aramaic read already cached, and a table file with the name the cache was read by."""
    cache = tmp_path / "cache"
    cache.mkdir()
    for code in oshb.BOOKS.values():
        (cache / f"{code}.json").write_text(json.dumps({"w1": 2, "w2": 1}), encoding="utf-8")
    (cache / "aramaic.json").write_text(json.dumps({"Dan": {"w2": 1}}), encoding="utf-8")
    table = tmp_path / "tanakh.json"
    table.write_text(
        json.dumps({"counted": {"dicta": {"by": "dicta/test/1"}}, "bands": {"w1": 1}}) + "\n",
        encoding="utf-8",
    )

    def verses(code: str) -> list[tuple[str, tuple[oshb.Word, ...]]]:
        ref = "Dan.2.4" if code == "Dan" else f"{code}.1.1"
        return [(ref, (_word("w1", "Ncmsa"), _word("w2", "Vqp3ms")))]

    monkeypatch.setattr(oshb, "verses", verses)
    monkeypatch.setattr(scripture, "headword_of", lambda word: word.text)
    return {"cache": cache, "table": table, "ledger": tmp_path / "corpus.db"}


def test_counts_writes_both_keyings_and_leaves_the_table_alone(tanakh: dict[str, Any]) -> None:
    before = tanakh["table"].read_bytes()
    said: list[str] = []
    assert _script().counts(tanakh["cache"], tanakh["table"], tanakh["ledger"], said.append) == 0
    assert tanakh["table"].read_bytes() == before, "tanakh.json is never written"

    store = Store(tanakh["ledger"])
    books = len(oshb.BOOKS)
    assert store.total(bible.WORDS, "bible") == 3 * books
    assert store.total(bible.LEXEMES, "bible") == 2 * books
    assert store.registers(bible.WORDS) == {"bible": books}
    with sqlite3.connect(tanakh["ledger"]) as db:
        provenance = set(db.execute("SELECT source, licence FROM contribution"))
        aramaic = db.execute(
            "SELECT c.tbl, t.key, t.n FROM tally t JOIN contribution c"
            " ON c.id = t.contribution_id WHERE t.variant = 'arc' ORDER BY c.tbl, t.key"
        ).fetchall()
        tools = {row[0] for row in db.execute("SELECT tool FROM contribution WHERE tbl = 'words'")}
    assert provenance == {(bible.SOURCE, bible.LICENCE)}
    assert aramaic == [("lexemes", "w1", 1), ("lexemes", "w2", 1), ("words", "w2", 1)]
    assert tools == {"dicta/test/1"}, "filed under the name the cache was read by"

    # Run again, nothing new: every contribution is a content hash.
    assert _script().counts(tanakh["cache"], tanakh["table"], tanakh["ledger"], said.append) == 0
    assert store.total(bible.WORDS, "bible") == 3 * books


def test_counts_stops_when_a_book_is_missing_from_the_cache(tanakh: dict[str, Any]) -> None:
    (tanakh["cache"] / "Ruth.json").unlink()
    said: list[str] = []
    assert _script().counts(tanakh["cache"], tanakh["table"], tanakh["ledger"], said.append) == 1
    assert "Ruth" in said[0]
    assert not tanakh["ledger"].exists(), "nothing written, and no model run"
