"""The correction store's editor door (targum-internal#354): a paid editor's pass kept
as rows, `who = "editor"` and `licence = "targum"`, counted as a judge of its own."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from targum.accounts import Store
from targum.annotate import gloss as gloss_module
from targum.cache import Cache
from targum.cli import app
from targum.editor_pass import read_editor_pass
from targum.errors import TargumError


def test_an_editor_and_a_reader_are_two_judges(tmp_path: Path) -> None:
    """Acceptance 2: an editor agreeing with a reader is corroboration."""
    store = Store(tmp_path / "words.db")
    reader = store.judge_for(7)
    store.correct("gloss", who="reader", judge=reader, term="עם", language="he", after="with")
    assert store.agreed() == [], "one reader alone is not a gold row"
    store.editor_pass("gloss", [{"term": "עם", "language": "he", "after": "with"}])
    (row,) = store.agreed()
    assert row["judges"] == 2 and set(row["roles"].split(",")) == {"reader", "editor"}


def test_an_editors_pass_is_rows_under_targums_licence(tmp_path: Path) -> None:
    """Acceptance 1, and it can be run twice without inventing a second editor."""
    store = Store(tmp_path / "words.db")
    judge = store.editor_judge("Dana")
    rows = [
        {"span": "market-01 t3", "term": "שלום", "before": "שָלוֹם", "after": "שָׁלוֹם"},
        {"span": "market-01 t4", "term": "תודה", "before": "תודא", "after": "תודה", "reason": "x"},
    ]
    written, skipped = store.editor_pass("scene", rows, judge=judge)
    assert len(written) == 2 and skipped == 0
    kept = store.corrections("scene")
    assert {r["who"] for r in kept} == {"editor"} and {r["licence"] for r in kept} == {"targum"}
    assert {r["judge"] for r in kept} == {judge}
    again, skipped = store.editor_pass("scene", rows, judge=judge)
    assert again == [] and skipped == 2
    assert len(store.corrections("scene")) == 2


def test_two_editors_are_two_judges_and_one_editor_twice_is_one(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    dana, dana_again, avi = (store.editor_judge(n) for n in ("Dana", " dana ", "Avi"))
    assert dana == dana_again != avi
    assert len(dana) == 16 and dana != store.judge_for(1)
    for why in ("first pass", "second pass"):
        store.correct("gloss", who="editor", judge=dana, term="אור", after="light", reason=why)
    assert store.agreed() == [], "one editor twice is one judge"
    store.editor_pass("gloss", [{"term": "אור", "after": "light"}], judge=avi)
    (row,) = store.agreed()
    assert row["judges"] == 2 and row["roles"] == "editor" and row["seen"] == 3
    with pytest.raises(ValueError):
        store.editor_judge("  ")


def test_an_editor_can_settle_a_readers_proposal(tmp_path: Path) -> None:
    store = Store(tmp_path / "words.db")
    offered = store.propose_correction(stage="gloss", who="reader", term="עם", after="with")
    decided = store.settle_correction(
        offered, accept=True, by="editor", judge=store.editor_judge("Dana")
    )
    row = {r["id"]: r for r in store.corrections()}[decided]
    assert row["who"] == "editor" and row["licence"] == "targum" and row["judge"]
    assert set(store.agreed()[0]["roles"].split(",")) == {"reader", "editor"}


# -- the file an editor hands back ------------------------------------------------------


def test_a_csv_pass_reads_with_the_editors_own_column_names(tmp_path: Path) -> None:
    path = tmp_path / "pass.csv"
    path.write_text(
        "line,before,after,note\n"
        "market-01 t3,שָלוֹם,שָׁלוֹם,shin dot\n"
        ",,,\n"
        "market-01 t5,ילד,ילדה,the speaker is a girl\n",
        encoding="utf-8",
    )
    rows = read_editor_pass(path, "scene")
    assert [r["span"] for r in rows] == ["market-01 t3", "market-01 t5"], "blank lines skipped"
    assert rows[0]["term"] == "שלום", "the term is before without its points"
    assert rows[0]["reason"] == "shin dot" and rows[0]["language"] == "he"


def test_a_jsonl_pass_reads_too(tmp_path: Path) -> None:
    path = tmp_path / "pass.jsonl"
    path.write_text(
        json.dumps({"line": "a t1", "term": "עם", "before": "people", "after": "with"}) + "\n\n",
        encoding="utf-8",
    )
    (row,) = read_editor_pass(path, "gloss")
    assert row["term"] == "עם" and row["after"] == "with" and row["span"] == "a t1"


def test_a_bad_row_refuses_the_whole_file_and_names_the_line(tmp_path: Path) -> None:
    path = tmp_path / "pass.csv"
    path.write_text("line,before,after,term\na,people,with,עם\nb,people,with,\n", encoding="utf-8")
    with pytest.raises(TargumError, match="line 3: a gloss row must name its term"):
        read_editor_pass(path, "gloss")
    other = tmp_path / "pass.txt"
    other.write_text("x", encoding="utf-8")
    with pytest.raises(TargumError, match="neither .csv nor .jsonl"):
        read_editor_pass(other, "scene")


# -- the commands -----------------------------------------------------------------------


def test_the_editor_pass_command_says_first_and_writes_on_write(tmp_path: Path) -> None:
    db = tmp_path / "words.db"
    path = tmp_path / "pass.csv"
    path.write_text("line,before,after,note\nm t1,ילד,ילדה,girl\n", encoding="utf-8")
    runner = CliRunner()
    base = ["editor-pass", str(path), "--stage", "scene", "--editor", "Dana", "--store", str(db)]

    looked = runner.invoke(app, base)
    assert looked.exit_code == 0, looked.output
    assert "1 to write" in looked.output and "Nothing was written" in looked.output
    assert Store(db).corrections() == []

    wrote = runner.invoke(app, [*base, "--write"])
    assert wrote.exit_code == 0, wrote.output
    assert "Kept 1" in wrote.output
    (row,) = Store(db).corrections()
    assert row["who"] == "editor" and row["licence"] == "targum" and row["judge"]

    again = runner.invoke(app, [*base, "--write"])
    assert "Kept 0" in again.output and "1 already there" in again.output
    assert len(Store(db).corrections()) == 1


def test_correct_takes_an_editors_hand(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gloss_module, "Cache", lambda root=None: Cache(tmp_path / "cache"))
    db = tmp_path / "words.db"
    runner = CliRunner()
    said = runner.invoke(
        app,
        ["correct", "עם", "--meaning", "with", "--who", "editor", "--editor", "Dana"]
        + ["--store", str(db)],
    )
    assert said.exit_code == 0, said.output
    (row,) = Store(db).corrections()
    assert row["who"] == "editor" and row["licence"] == "targum"
    assert row["judge"] == Store(db).editor_judge("Dana")

    for wrong in (["--who", "reader"], ["--editor", "Dana"]):
        refused = runner.invoke(
            app, ["correct", "עם", "--meaning", "x", *wrong, "--store", str(db)]
        )
        assert refused.exit_code != 0
    assert len(Store(db).corrections()) == 1, "a refused hand writes nothing"


def test_settle_takes_an_editors_hand(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gloss_module, "_home", lambda: tmp_path / "glosses", raising=False)
    monkeypatch.setenv("TARGUM_CACHE", str(tmp_path / "cache"))
    db = tmp_path / "words.db"
    offered = Store(db).propose_correction(stage="gloss", who="reader", term="אור", after="x")
    runner = CliRunner()
    said = runner.invoke(
        app, ["settle", str(offered), "--reject", "--by", "editor", "--store", str(db)]
    )
    assert said.exit_code == 0, said.output
    decided = Store(db).corrections()[0]
    assert decided["who"] == "editor" and decided["state"] == "rejected"
