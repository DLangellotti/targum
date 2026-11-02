"""Which reading a spelling takes, per register (targum-internal#583).

Every word here is synthetic: two- and three-letter strings of Hebrew letters with
vowels put on them for the test, never a sentence of any text.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from targum import tables
from targum.cli import app
from targum.tables import imports, registers, spellings
from targum.tables.store import Store
from targum.tables.words import TABLES

#: One spelling, two readings: "אבג" pointed two ways, filed under two lemmas.
SPELLING = "אבג"
ONE = "אָבַג"
TWO = "אֶבֶג"
#: A second word, so a segment is more than one token.
OTHER, OTHER_POINTED = "דה", "דֶּה"

H = {name: name * 64 for name in "abcdefgh"}


def _segment(readings: list[str]) -> tuple[str, str, list[dict[str, Any]]]:
    """A segment of `SPELLING` once per reading, then `OTHER`: (text, pointed, tokens)."""
    words = [SPELLING] * len(readings) + [OTHER]
    pointed = [*readings, OTHER_POINTED]
    tokens = []
    at = 0
    for word, reading in zip(words, pointed, strict=True):
        lemma = "l-one" if reading == ONE else "l-two" if reading == TWO else "l-other"
        tokens.append(
            {"start": at, "end": at + len(word), "surface": word, "lemma": lemma, "pos": "NOUN"}
        )
        at += len(word) + 1
    return " ".join(words), " ".join(pointed), tokens


def _built(
    folder: Path,
    document_hash: str,
    readings: list[str],
    *,
    vocalizer: str | None = "dicta/menaked/1",
    annotator: str = "dicta/test/1",
    source: str = "",
) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    text, pointed, tokens = _segment(readings)
    document = {"content_hash": document_hash, "source": source or f"test:{document_hash[:4]}"}
    annotation = {
        "document_hash": document_hash,
        "language": "he",
        "annotator": annotator,
        "tokens": {"s0": tokens},
    }
    segments = {
        "document_hash": document_hash,
        "segments": [{"id": "s0", "text": text}],
    }
    (folder / "document.json").write_text(json.dumps(document), encoding="utf-8")
    (folder / "annotation.json").write_text(json.dumps(annotation), encoding="utf-8")
    (folder / "segments.json").write_text(json.dumps(segments), encoding="utf-8")
    if vocalizer is not None:
        vocalization = {
            "document_hash": document_hash,
            "language": "he",
            "vocalizer": vocalizer,
            "segments": {"s0": pointed},
        }
        (folder / "vocalization.json").write_text(json.dumps(vocalization), encoding="utf-8")
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


@pytest.fixture
def by_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """A source naming its register: `test:news-…` is news, `test:bible-…` bible."""

    def register_of(source: str) -> str:
        return source.split(":", 1)[1].split("-", 1)[0]

    monkeypatch.setattr(tables, "register_of", register_of)


def _share(found: spellings.Readings) -> dict[str, float]:
    return {one.pointed: round(one.share, 4) for one in found.choices}


@pytest.mark.usefixtures("by_source")
def test_two_readings_in_two_registers_give_their_shares(book: Path, library: Path) -> None:
    store = Store(book)
    _built(library / "shared" / "a", H["a"], [ONE, ONE, ONE, TWO], source="test:news-a")
    _built(library / "shared" / "b", H["b"], [TWO, TWO, TWO, ONE], source="test:bible-b")
    assert tables.sweep(library, store).folded == 2

    news = tables.readings(SPELLING, "news", store)
    assert news.total == 4 and news.unaligned == 0
    assert _share(news) == {ONE: 0.75, TWO: 0.25}
    assert [one.glossed_as for one in news.choices] == ["l-one", "l-two"]
    assert _share(tables.readings(SPELLING, "bible", store)) == {ONE: 0.25, TWO: 0.75}
    # Every register at once; and the spelling may be asked with its vowels on.
    assert _share(tables.readings(ONE, None, store)) == {ONE: 0.5, TWO: 0.5}
    assert tables.readings("זזז", "news", store).total == 0


def test_the_sweep_backfills_readings_where_a_vocalization_sits_beside(
    book: Path, library: Path
) -> None:
    store = Store(book)
    _built(library / "shared" / "a", H["a"], [ONE])
    _built(library / "shared" / "b", H["b"], [TWO], vocalizer=None)
    assert tables.sweep(library, store).folded == 2
    with sqlite3.connect(book) as db:
        held = db.execute("SELECT unit FROM contribution WHERE tbl = ?", (spellings.READINGS,))
        units = {row[0] for row in held}
    assert units == {H["a"]}

    # A second sweep finds every table current and reads nothing again.
    again = tables.sweep(library, store)
    assert again.folded == 0 and again.unchanged == 2

    # A vocalization that lands later is backfilled by the next sweep.
    _built(library / "shared" / "b", H["b"], [TWO])
    assert tables.sweep(library, store).folded == 1
    assert _share(tables.readings(SPELLING, registers.UNFILED, store)) == {ONE: 0.5, TWO: 0.5}


def test_a_new_vocalizer_supersedes_rather_than_doubles(book: Path, library: Path) -> None:
    store = Store(book)
    _built(library / "shared" / "a", H["a"], [ONE, TWO])
    tables.sweep(library, store)
    _built(library / "shared" / "a", H["a"], [TWO, TWO], vocalizer="dicta/menaked/2")
    assert tables.sweep(library, store).folded == 1
    found = tables.readings(SPELLING, registers.UNFILED, store)
    assert found.total == 2 and _share(found) == {TWO: 1.0}


def test_a_token_that_cannot_be_aligned_is_counted_and_never_guessed() -> None:
    text, pointed, tokens = _segment([ONE, ONE])
    # The segment the vocalization left out: every word in it is unaligned.
    counted = spellings.count({"s0": tokens}, {"s0": text}, {})
    assert counted == {
        (SPELLING, spellings.variant(spellings.UNALIGNED, "l-one")): 2,
        (OTHER, spellings.variant(spellings.UNALIGNED, "l-other")): 1,
    }
    # A pointed word that spells another word is not this spelling's reading.
    wrong = pointed.replace(ONE, "אָבַד", 1)
    counted = spellings.count({"s0": tokens}, {"s0": text}, {"s0": wrong})
    assert counted[(SPELLING, spellings.variant(spellings.UNALIGNED, "l-one"))] == 1
    assert counted[(SPELLING, spellings.variant(ONE, "l-one"))] == 1
    # A word the vocalizer left bare carries no reading.
    bare = pointed.replace(ONE, SPELLING, 1)
    counted = spellings.count({"s0": tokens}, {"s0": text}, {"s0": bare})
    assert counted[(SPELLING, spellings.variant(spellings.UNALIGNED, "l-one"))] == 1
    # Offsets out of reach are unaligned, not an error.
    stray = [{**tokens[0], "start": 40, "end": 43}]
    counted = spellings.count({"s0": stray}, {"s0": text}, {"s0": pointed})
    assert set(counted) == {(SPELLING, spellings.variant(spellings.UNALIGNED, "l-one"))}

    # And the share is of the aligned occurrences alone.
    found = spellings.shares(
        SPELLING,
        None,
        {spellings.variant(ONE, "l-one"): 3, spellings.variant(spellings.UNALIGNED, "l-one"): 5},
    )
    assert found.total == 3 and found.unaligned == 5 and _share(found) == {ONE: 1.0}


def test_a_scene_line_in_ktiv_menukad_still_aligns() -> None:
    # Full spelling in the text, a mater left out of the pointed line (#568).
    text = "חיבור"
    tokens = [{"start": 0, "end": 5, "surface": text, "lemma": "l", "pos": "NOUN"}]
    counted = spellings.count({"s0": tokens}, {"s0": text}, {"s0": "חִבּוּר"}, "scene/1")
    assert counted == {(text, spellings.variant("חִבּוּר", "l")): 1}
    # Not for any other vocalizer, whose lines keep every letter.
    counted = spellings.count({"s0": tokens}, {"s0": text}, {"s0": "חִבּוּר"}, "dicta/menaked/1")
    assert counted == {(text, spellings.variant(spellings.UNALIGNED, "l")): 1}


def test_names_and_non_words_are_not_counted_and_a_verb_is_filed_as_one() -> None:
    text, pointed, tokens = _segment([ONE])
    tokens[0] = {**tokens[0], "pos": "VERB"}
    tokens[1] = {**tokens[1], "pos": "PROPN", "entity": "B-PER"}
    counted = spellings.count({"s0": tokens}, {"s0": text}, {"s0": pointed})
    assert counted == {(SPELLING, spellings.variant(ONE, "l-one (verb)")): 1}
    latin = [{"start": 0, "end": 3, "surface": "abc", "lemma": "abc", "pos": "X"}]
    assert spellings.count({"s0": latin}, {"s0": "abc"}, {"s0": "abc"}) == {}


def test_chanting_marks_do_not_split_a_reading() -> None:
    text, _pointed, tokens = _segment([ONE])
    accented = f"{ONE}֑ {OTHER_POINTED}"
    counted = spellings.count({"s0": tokens}, {"s0": text}, {"s0": accented})
    assert counted[(SPELLING, spellings.variant(ONE, "l-one"))] == 1


def test_a_home_writes_no_readings(book: Path, library: Path) -> None:
    store = Store(book)
    _built(library / "p1" / "a", H["a"], [ONE])
    _built(library / "local" / "a", H["b"], [ONE])
    assert tables.sweep(library, store).private == 2
    assert tables.readings(SPELLING, store=store).total == 0
    # Nothing was written at all: the ledger file was never even made.
    assert not book.exists()


def test_what_readers_bring_counts_readings_behind_the_floor(book: Path, library: Path) -> None:
    store = Store(book)
    for person in range(1, 11):
        readings = [ONE] if person != 1 else [ONE, TWO]
        _built(
            library / f"p{person}" / "a",
            f"{person:064d}",
            readings,
            source=f"https://x.test/{person}",
        )
    imports.pool(library, store, set(range(1, 11)))
    pooled = tables.readings(SPELLING, registers.IMPORTS, store)
    # Ten readers gave ONE; only one gave TWO, so it was never written down.
    assert pooled.total == 11 - 1 and _share(pooled) == {ONE: 1.0}
    with sqlite3.connect(book) as db:
        cells = "\n".join(str(v) for row in db.execute("SELECT * FROM tally") for v in row)
        units = {row[0] for row in db.execute("SELECT unit FROM contribution")}
    assert TWO not in cells
    assert all(unit.startswith(imports.UNIT) for unit in units)
    # The pool is never in the public answer.
    assert tables.readings(SPELLING, None, store).total == 0

    # Nine readers are not enough.
    imports.pool(library, store, set(range(2, 11)))
    assert tables.readings(SPELLING, registers.IMPORTS, store).total == 0


def test_the_fold_writes_readings_only_when_given_them(book: Path, library: Path) -> None:
    folder = _built(library / "shared" / "a", H["a"], [ONE])
    text = tables.public_text(folder, library)
    assert text is not None
    annotation = json.loads((folder / "annotation.json").read_text(encoding="utf-8"))
    store = Store(book)
    assert tables.fold(text, annotation, store) == len(TABLES)
    near = spellings.beside(folder, H["a"])
    assert near is not None
    assert tables.fold(text, annotation, store, beside=near) == 1
    assert tables.fold(text, annotation, store, beside=near) == 0
    # A vocalization of another document is not this one's.
    assert spellings.beside(folder, H["b"]) is None


def test_the_command_prints_each_share(book: Path, library: Path) -> None:
    _built(library / "shared" / "a", H["a"], [ONE, ONE, ONE, TWO])
    tables.sweep(library, Store(book))
    result = CliRunner().invoke(app, ["tables", "readings", SPELLING])
    assert result.exit_code == 0, result.output
    assert "75.00%" in result.output and ONE in result.output
    result = CliRunner().invoke(app, ["tables", "readings", "זזז", "--register", "news"])
    assert result.exit_code == 0 and "not counted" in result.output
