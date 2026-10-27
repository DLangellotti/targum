"""`targum corpus export` (targum-internal#162, slice 3): criteria 3 and 4, and the two
promises around them — no private row in either export, and no account id anywhere."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from targum import corpus_export, ledger
from targum.cli import app
from targum.models import Annotation, Token, Translation, Vocalization


def _pointed(document_hash: str, **change: Any) -> dict[str, Any]:
    value = Vocalization(
        document_hash=document_hash,
        language="he",
        vocalizer="dicta/menaked/1",
        model="dictabert-large-char-menaked",
        segments={"s0": "שָׁלוֹם.", "s1": "אִמָּא בָּאָה."},
        machine=["s1"],
        rejected=[],
    ).model_dump(mode="json")
    return {**value, **change}


def _annotated(document_hash: str) -> dict[str, Any]:
    return Annotation(
        document_hash=document_hash,
        language="he",
        annotator="grammar/2",
        method="test",
        method_note="two segments",
        tokens={
            "s0": [Token(start=0, end=5, surface="שלום", lemma="שלום", band=1, pos="NOUN")],
            "s1": [
                Token(start=0, end=3, surface="אמא", lemma="אמא", band=1, pos="NOUN"),
                Token(start=4, end=8, surface="באה", lemma="בוא", band=2, pos="VERB"),
            ],
        },
    ).model_dump(mode="json")


def _translated(document_hash: str, **change: Any) -> dict[str, Any]:
    value = Translation(
        name="English (Claude)",
        document_hash=document_hash,
        source_language="he",
        target_language="en",
        provider="claude",
        model="claude-test",
        segments={"s1": "Mother came.", "s0": "Hello."},
        coarse=["s1"],
        confidence={"s1": 0.5},
    ).model_dump(mode="json")
    return {**value, **change}


H = {name: name * 64 for name in "abcdef"}


@pytest.fixture
def book(tmp_path: Path) -> ledger.Ledger:
    """A ledger with one text of every kind the rule tells apart."""
    book = ledger.Ledger(tmp_path / "corpus.db")
    texts = {
        "a": ("gutenberg:1", "Public Domain", frozenset()),
        "b": ("https://x.example/b", "CC BY-NC 4.0", frozenset()),
        "c": ("upload.pdf", "Public Domain", frozenset({"p3"})),
        "d": ("https://x.example/d", "", frozenset()),
        "e": ("https://x.example/e", "CC BY-ND 4.0", frozenset()),
    }
    for name, (source, licence, homes) in texts.items():
        book.record_text(ledger.Text(H[name], source, licence, homes, "markdown/1", 4))
    for name in "abcdef":
        book.record("vocalize", f"v-{name}", _pointed(H[name]))
    for name in "ac":
        book.record("tokens", f"{H[name]}:grammar/2", _annotated(H[name]))
    # History: only the current value goes out.
    book.record("vocalize", "v-a", _pointed(H["a"], machine=[]))
    # Renderings: targum's own under the text's licence, a published one under its own.
    for name, licence in (("a", "Public Domain"), ("b", "CC BY-NC 4.0"), ("c", "Public Domain")):
        book.record(
            "translations",
            f"{H[name]}:claude.natural.en",
            _translated(H[name]),
            licence=licence,
            sources={"s0": "שלום.", "s1": "אמא באה."},
        )
    book.record(
        "translations",
        f"{H['a']}:aligned.jps.en",
        _translated(H["a"], kind="aligned", provider="JPS 1917", name="JPS"),
        licence="CC BY-NC 4.0",
    )
    return book


def _lines(folder: Path, table: str) -> list[dict[str, Any]]:
    text = (folder / f"{table}.jsonl").read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines()]


def _everything(folder: Path) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(folder.iterdir()))


def test_the_commercial_export_holds_only_what_may_be_sold(
    book: ledger.Ledger, tmp_path: Path
) -> None:
    sheet = corpus_export.export(book.file, tmp_path / "out", "exportable")
    out = tmp_path / "out"
    assert [row["document_hash"] for row in _lines(out, "texts")] == [H["a"]]
    assert [row["document_hash"] for row in _lines(out, "vocalizations")] == [H["a"]]
    assert [row["document_hash"] for row in _lines(out, "annotations")] == [H["a"]]
    assert len(_lines(out, "tokens")) == 3
    assert [row["segment_id"] for row in _lines(out, "pointings")] == ["s0", "s1"]
    assert _lines(out, "vocalizations")[0]["cache_key"] == "v-a", "the current value"
    assert sheet["rows"] == {
        "texts": 1,
        "vocalizations": 1,
        "pointings": 2,
        "annotations": 1,
        "tokens": 3,
        "translations": 1,
        "pairs": 2,
    }
    pairs = _lines(out, "pairs")
    assert [(row["segment_id"], row["source"], row["target"]) for row in pairs] == [
        ("s1", "אמא באה.", "Mother came."),
        ("s0", "שלום.", "Hello."),
    ]
    assert pairs[0]["coarse"] == 1 and pairs[0]["confidence"] == 0.5


def test_the_research_export_also_admits_noncommercial(book: ledger.Ledger, tmp_path: Path) -> None:
    corpus_export.export(book.file, tmp_path / "out", "research")
    hashes = [row["document_hash"] for row in _lines(tmp_path / "out", "texts")]
    assert hashes == [H["a"], H["b"]]


@pytest.mark.parametrize("kind", corpus_export.KINDS)
def test_row_counts_are_the_count_of_rows_with_the_bit(
    book: ledger.Ledger, tmp_path: Path, kind: str
) -> None:
    """Criterion 3: each table's count is `SELECT COUNT(*) … WHERE <bit>` of its rows."""
    sheet = corpus_export.export(book.file, tmp_path / "out", kind)
    with sqlite3.connect(book.file) as db:
        for table in ("texts", "vocalizations", "annotations", "translations"):
            expected = db.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {kind} AND superseded_at IS NULL"  # noqa: S608
            ).fetchone()[0]
            assert sheet["rows"][table] == expected, table
            assert len(_lines(tmp_path / "out", table)) == expected, table


@pytest.mark.parametrize("kind", corpus_export.KINDS)
def test_no_licence_no_private_and_no_nd_text_leaves_even_with_a_wrong_bit(
    book: ledger.Ledger, tmp_path: Path, kind: str
) -> None:
    """Criterion 4 and the private bucket. The bits are forced wrong on every row of the
    three texts that must stay, and still nothing of theirs goes out."""
    with sqlite3.connect(book.file) as db:
        for name in "cde":
            for table in ("texts", "vocalizations", "annotations", "translations"):
                db.execute(
                    f"UPDATE {table} SET exportable = 1, research = 1"  # noqa: S608
                    " WHERE document_hash = ?",
                    (H[name],),
                )
    corpus_export.export(book.file, tmp_path / "out", kind)
    gone = _everything(tmp_path / "out")
    for name in "cdef":
        assert H[name] not in gone, name


@pytest.mark.parametrize("kind", corpus_export.KINDS)
def test_no_account_id_is_written(book: ledger.Ledger, tmp_path: Path, kind: str) -> None:
    corpus_export.export(book.file, tmp_path / "out", kind)
    written = _everything(tmp_path / "out")
    assert "p3" not in written
    assert "text_homes" not in written and '"private"' not in written
    for row in _lines(tmp_path / "out", "texts"):
        assert set(row) == {
            "document_hash",
            "source",
            "licence",
            "reader_publishable",
            "ingester",
            "schema_version",
            "written_at",
        }


def test_the_datasheet_lists_every_source_licence_and_tool(
    book: ledger.Ledger, tmp_path: Path
) -> None:
    sheet = corpus_export.export(book.file, tmp_path / "out", "research")
    assert sheet["sources"] == [
        {"source": "gutenberg:1", "licence": "Public Domain"},
        {"source": "https://x.example/b", "licence": "CC BY-NC 4.0"},
    ]
    assert sheet["licences"] == {"CC BY-NC 4.0": 1, "Public Domain": 1}
    assert {(one["table"], one["tool"], one["rows"]) for one in sheet["tools"]} == {
        ("vocalizations", "dicta/menaked/1", 2),
        ("annotations", "grammar/2", 1),
        ("translations", "claude", 2),
        ("translations", "JPS 1917", 1),
    }
    assert sheet["translation_licences"] == {"CC BY-NC 4.0": 2, "Public Domain": 1}
    assert sheet["ledger_schema"] == ledger.LEDGER_SCHEMA
    on_disk = json.loads((tmp_path / "out" / "datasheet.json").read_text(encoding="utf-8"))
    assert on_disk == sheet
    page = (tmp_path / "out" / "DATASHEET.md").read_text(encoding="utf-8")
    assert "https://x.example/b — CC BY-NC 4.0" in page


def test_an_export_never_writes_over_another(book: ledger.Ledger, tmp_path: Path) -> None:
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "texts.jsonl").write_text("kept\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not empty"):
        corpus_export.export(book.file, tmp_path / "out", "exportable")
    assert (tmp_path / "out" / "texts.jsonl").read_text(encoding="utf-8") == "kept\n"
    with pytest.raises(ValueError, match="no export"):
        corpus_export.export(book.file, tmp_path / "other", "everything")


class TestTheCommand:
    def test_it_wants_exactly_one_export(
        self, monkeypatch: pytest.MonkeyPatch, book: ledger.Ledger, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(ledger.ENV, str(book.file))
        for flags in ([], ["--exportable", "--research"]):
            result = CliRunner().invoke(app, ["corpus", "export", str(tmp_path / "o"), *flags])
            assert result.exit_code != 0 and "Choose one export" in result.output

    def test_it_refuses_with_the_ledger_off(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.delenv(ledger.ENV, raising=False)
        result = CliRunner().invoke(app, ["corpus", "export", str(tmp_path / "o"), "--exportable"])
        assert result.exit_code != 0 and "ledger is off" in result.output

    def test_it_writes_the_export(
        self, monkeypatch: pytest.MonkeyPatch, book: ledger.Ledger, tmp_path: Path
    ) -> None:
        monkeypatch.setenv(ledger.ENV, str(book.file))
        result = CliRunner().invoke(app, ["corpus", "export", str(tmp_path / "o"), "--exportable"])
        assert result.exit_code == 0, result.output
        assert "1 texts" in result.output
        assert (tmp_path / "o" / "datasheet.json").is_file()


def test_a_source_that_is_a_path_through_a_home_never_leaves(
    book: ledger.Ledger, tmp_path: Path
) -> None:
    """A public text whose source is a path into a reader's home would carry their
    account id out in the `source` column; it is not exported at all."""
    leaky = "9" * 64
    book.record_text(ledger.Text(leaky, "/var/lib/targum/out/p3/notes.md", "Public Domain"))
    corpus_export.export(book.file, tmp_path / "out", "exportable")
    written = _everything(tmp_path / "out")
    assert leaky not in written and "p3" not in written


def test_a_published_rendering_leaves_only_under_its_own_licence(
    book: ledger.Ledger, tmp_path: Path
) -> None:
    """Slice 4: the JPS rendering beside a public-domain text is CC BY-NC here, so it is
    in the research export and not the commercial one, whatever its text allows."""
    corpus_export.export(book.file, tmp_path / "commercial", "exportable")
    corpus_export.export(book.file, tmp_path / "research", "research")
    commercial = [row["cache_key"] for row in _lines(tmp_path / "commercial", "translations")]
    research = [row["cache_key"] for row in _lines(tmp_path / "research", "translations")]
    assert commercial == [f"{H['a']}:claude.natural.en"]
    assert research == [
        f"{H['a']}:claude.natural.en",
        f"{H['b']}:claude.natural.en",
        f"{H['a']}:aligned.jps.en",
    ]


def test_a_rendering_whose_own_licence_was_stamped_wrong_still_stays(
    book: ledger.Ledger, tmp_path: Path
) -> None:
    with sqlite3.connect(book.file) as db:
        db.execute("UPDATE translations SET exportable = 1, own_exportable = 1")
    corpus_export.export(book.file, tmp_path / "out", "exportable")
    keys = [row["cache_key"] for row in _lines(tmp_path / "out", "translations")]
    assert keys == [f"{H['a']}:claude.natural.en"], "the licence is asked again"
