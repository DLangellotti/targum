"""An outside corpus counted into the language tables (targum-internal#580, #581): counts
with provenance, never a sentence, resumable a chunk at a time.

Every line here is synthetic: placeholder words, no sentence of any text. The annotator
is a stand-in that files each word under itself, so no model runs.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from targum.cli import app
from targum.models import Token
from targum.tables import corpus
from targum.tables.store import Store
from targum.tables.words import PHRASES, WORDS


class Stand:
    """Files every word under its capital as a noun, so a lemma is never the text read;
    counts the chunks it was handed."""

    name = "stand-in/1"

    def __init__(self) -> None:
        self.read = 0

    def annotate(self, document: Any) -> Any:
        self.read += 1
        tokens = {}
        for segment in document.segments:
            run = []
            at = 0
            for word in segment.text.split():
                run.append(
                    Token(
                        start=at,
                        end=at + len(word),
                        surface=word,
                        lemma=word.upper(),
                        band=0,
                        pos="NOUN",
                    )
                )
                at += len(word) + 1
            tokens[segment.id] = run
        return SimpleNamespace(tokens=tokens)


LINES = ["w1 w2 w3", "w1 w2", "w1 w2 w4", "w5", "w1 w2 w3", "w6 w7"]
OPTS = {"register": "conversation", "source": "test-corpus", "licence": "test licence"}


def test_a_corpus_is_counted_with_its_provenance_and_no_sentence(tmp_path: Path) -> None:
    store = Store(tmp_path / "corpus.db")
    result = corpus.count_corpus(LINES, store, annotator=Stand(), size=3, **OPTS)
    assert (result.counted, result.held, result.sentences) == (2, 0, 6)
    assert result.tokens == 14 == store.total(WORDS, "conversation")
    assert len(result.lemmas) == 7
    with sqlite3.connect(store.file) as db:
        rows = set(db.execute("SELECT tbl, register, source, licence, tool FROM contribution"))
        keys = {row[0] for row in db.execute("SELECT key FROM tally")}
        dump = "\n".join(db.iterdump())
    assert {row[1:] for row in rows} == {
        ("conversation", "test-corpus", "test licence", "stand-in/1")
    }
    assert {row[0] for row in rows} == {"words", "phrases", "roots"}
    assert "W1" in keys
    for line in LINES:
        assert line not in dump, "no sentence is stored"


def test_phrases_under_the_floor_are_not_written(tmp_path: Path) -> None:
    store = Store(tmp_path / "corpus.db")
    corpus.count_corpus(LINES, store, annotator=Stand(), size=10, **OPTS)
    # "W1 W2" runs four times in the one chunk; "W2 W3" twice, under the floor of three.
    assert store.top(PHRASES, "conversation") == [("W1 W2", 4)]


def test_a_stopped_run_resumes_without_reading_a_chunk_twice(tmp_path: Path) -> None:
    store = Store(tmp_path / "corpus.db")
    asked = iter(["", "the disk is full"])
    first = Stand()
    stopped = corpus.count_corpus(
        LINES, store, annotator=first, size=2, stop=lambda: next(asked), **OPTS
    )
    assert stopped.stopped == "the disk is full" and first.read == 1
    again = Stand()
    resumed = corpus.count_corpus(LINES, store, annotator=again, size=2, **OPTS)
    assert (resumed.held, resumed.counted, again.read) == (1, 2, 2)
    assert resumed.tokens == 14 == store.total(WORDS, "conversation")
    done = corpus.count_corpus(LINES, store, annotator=Stand(), size=2, **OPTS)
    assert (done.held, done.counted) == (3, 0), "run twice, nothing is counted twice"


def test_a_sample_ends_on_a_whole_chunk_and_grows_later(tmp_path: Path) -> None:
    store = Store(tmp_path / "corpus.db")
    small = corpus.count_corpus(LINES, store, annotator=Stand(), size=2, tokens=4, **OPTS)
    assert small.counted == 1 and small.tokens == 5 and "sample" in small.stopped
    grown = corpus.count_corpus(LINES, store, annotator=Stand(), size=2, tokens=100, **OPTS)
    assert (grown.held, grown.counted, grown.tokens) == (1, 2, 14)


def test_only_a_backfill_register_and_named_provenance_are_taken(tmp_path: Path) -> None:
    store = Store(tmp_path / "corpus.db")
    with pytest.raises(ValueError):
        corpus.count_corpus(LINES, store, annotator=Stand(), **{**OPTS, "register": "news"})
    with pytest.raises(ValueError):
        corpus.count_corpus(LINES, store, annotator=Stand(), **{**OPTS, "licence": ""})


def test_a_long_line_is_cut_at_spaces() -> None:
    long = " ".join(["w1234"] * 300)
    pieces = list(corpus.lines_of([long, "", "  w1   w2 "]))
    assert all(len(piece) <= corpus.LINE_CHARS for piece in pieces)
    assert " ".join(pieces[:-1]) == long and pieces[-1] == "w1 w2"


def test_the_command_counts_a_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = tmp_path / "corpus.db"
    monkeypatch.setenv("TARGUM_LEDGER", str(ledger))
    monkeypatch.setattr(corpus, "default_annotator", Stand)
    sample = tmp_path / "sample.txt"
    sample.write_text("\n".join(LINES) + "\n", encoding="utf-8")
    args = ["tables", "count-corpus", str(sample), "--register", "literature"]
    args += ["--source", "test-corpus", "--licence", "test licence", "--min-free-gb", "0"]
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "14 words" in result.output
    assert Store(ledger).total(WORDS, "literature") == 14
    refused = CliRunner().invoke(app, [*args[:3], "--register", "news", *args[5:]])
    assert refused.exit_code != 0
