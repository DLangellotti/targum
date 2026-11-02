"""The corrections ledger (targum-internal#585, language tables spec §4): before, after,
why and stage for every fix, in the `correction` table with a kind, a tool and a run.

Every string here is synthetic: placeholder words and lines, no sentence of any text.
"""

from __future__ import annotations

import inspect
import json
import logging
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from targum.accounts import SCHEMA_VERSION, Store
from targum.cli import app
from targum.tables import fixes
from targum.tables.store import Store as TablesStore

POINTED = "בָּדָק"
BARE = "בדק"
OTHER = "בָּדַק"


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "targum.db")


def fix(store: Store | Path, **over: Any) -> int | None:
    fields: dict[str, Any] = {
        "stage": "editor",
        "before": POINTED,
        "after": OTHER,
        "why": "placeholder reason",
        "kind": "nikkud",
        "tool": "model-a",
        "unit": "s-01 t1",
    }
    fields.update(over)
    return fixes.record(store, **fields)


# -- the schema -------------------------------------------------------------------------


def test_an_older_database_gains_the_three_columns(tmp_path: Path) -> None:
    file = tmp_path / "old.db"
    with sqlite3.connect(file) as db:
        db.execute(
            "CREATE TABLE correction (id INTEGER PRIMARY KEY AUTOINCREMENT, at INTEGER NOT NULL,"
            " stage TEXT NOT NULL, language TEXT NOT NULL DEFAULT '', target TEXT NOT NULL"
            " DEFAULT '', term TEXT NOT NULL DEFAULT '', text TEXT NOT NULL DEFAULT '',"
            " span TEXT NOT NULL DEFAULT '', before TEXT NOT NULL DEFAULT '', after TEXT NOT"
            " NULL DEFAULT '', who TEXT NOT NULL, licence TEXT NOT NULL DEFAULT '', context"
            " TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '')"
        )
        db.execute("INSERT INTO correction (at, stage, who) VALUES (1, 'gloss', 'author')")
    opened = Store(file)
    columns = {row[1] for row in opened.db.execute("PRAGMA table_info(correction)")}
    assert {"kind", "tool", "run", "judge", "state"} <= columns
    assert opened.db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 58
    row = opened.corrections()[0]
    assert (row["kind"], row["tool"], row["run"]) == ("", "", ""), "nobody said, before"


def test_the_public_api_keeps_its_names() -> None:
    """The private half calls this by keyword. A rename here breaks the weekly's writer
    and the dialogue writer in a checkout CI never sees, so it fails here first."""
    names = list(inspect.signature(fixes.record).parameters)
    assert names[:9] == [
        "store",
        "stage",
        "before",
        "after",
        "why",
        "kind",
        "tool",
        "unit",
        "who",
    ]
    assert fixes.KINDS == (
        "nikkud",
        "gender",
        "wording",
        "stress",
        "lifted",
        "gloss",
        "segmentation",
        "other",
    )


# -- record -----------------------------------------------------------------------------


def test_a_fix_is_kept_with_its_provenance(store: Store) -> None:
    written = fix(store, run="batch-1", context="placeholder line")
    assert written
    row = store.corrections()[0]
    assert row["stage"] == "editor" and row["who"] == "model", "a pass is a model's"
    assert (row["before"], row["after"], row["span"]) == (POINTED, OTHER, "s-01 t1")
    assert (row["kind"], row["tool"], row["run"]) == ("nikkud", "model-a", "batch-1")
    assert row["reason"] == "placeholder reason" and row["licence"] == "targum"
    assert row["term"] == BARE, "the term is read off before, points taken off"
    assert row["language"] == "he" and row["state"] == ""


def test_the_same_fix_is_never_a_second_row(store: Store) -> None:
    assert fix(store)
    assert fix(store, why="said differently", tool="model-b") == 0, "one fix, one row"
    assert fix(store, unit="s-02 t4"), "another place is another fix"
    assert fix(store, stage="director"), "another stage is another fix"
    assert fix(store, after="בָּדוּק", kind="wording"), "another after is another fix"
    assert len(store.corrections()) == 4


def test_two_editors_reaching_one_fix_stay_two_judges(store: Store) -> None:
    assert fix(store, who="editor", judge="j1", after="x")
    assert fix(store, who="editor", judge="j2", after="x")
    assert fix(store, who="author", after="x"), "the author has no judge and is a third"
    found = store.agreed()
    assert found and found[0]["judges"] == 3


def test_a_failed_write_is_logged_and_never_raised(
    tmp_path: Path, store: Store, caplog: pytest.LogCaptureFixture
) -> None:
    folder = tmp_path / "a-folder"
    folder.mkdir()
    with caplog.at_level(logging.WARNING, logger="targum.tables.fixes"):
        assert fix(folder) is None, "a directory is no database"
        assert fix(store, who="somebody") is None, "a role, never a person"
        assert fix(store, after=POINTED) is None, "nothing was fixed"
        assert fix(store, stage="") is None
    assert len([r for r in caplog.records if r.name == "targum.tables.fixes"]) == 4
    assert store.corrections() == []


def test_a_kind_off_the_list_is_kept_as_other(
    store: Store, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="targum.tables.fixes"):
        assert fix(store, kind="vibes")
    assert store.corrections()[0]["kind"] == "other"
    assert "vibes" in caplog.text


def test_a_store_may_be_named_by_its_path(tmp_path: Path) -> None:
    assert fix(tmp_path / "by-path.db")
    assert Store(tmp_path / "by-path.db").corrections()[0]["kind"] == "nikkud"


def test_points_moved_is_nikkud_and_letters_changed_is_wording() -> None:
    assert fixes.kind_of(POINTED, OTHER) == "nikkud"
    assert fixes.kind_of(POINTED, "בָּדוּק") == "wording"


# -- the recurrence report and the gold set ---------------------------------------------


def _ledger(store: Store) -> None:
    for unit in ("s-01 t1", "s-02 t1", "s-03 t1"):
        fix(store, unit=unit)  # one mistake, three places
    fix(store, before="אאא", after="בבב", kind="wording", tool="model-b", unit="s-01 t2")
    fix(store, before="גגג", after="דדד", kind="gender", tool="model-a", unit="s-04 t0")
    fix(store, before="הָהָה", after="", kind="other", who="author", unit="s-05 t0")
    fix(store, before="וָוָו", after="וַוַו", who="author", unit="s-06 t0")


def test_the_recurrence_counts_fixes_places_and_what_comes_back(store: Store) -> None:
    _ledger(store)
    proposed = store.propose_correction(
        stage="reader",
        who="reader",
        term="זזז",
        before="זזז",
        after="חחח",
        span="s-07 t0",
        kind="wording",
    )
    store.settle_correction(proposed, accept=False)
    by_kind = {row["kind"]: row for row in fixes.recurrence(store)}
    assert by_kind["nikkud"]["fixes"] == 4 and by_kind["nikkud"]["units"] == 4
    assert by_kind["nikkud"]["recurring"] == 1, "one pair, made in three places"
    assert by_kind["wording"]["fixes"] == 1, "the refused proposal is not a fix"
    pairs = {
        (row["kind"], row["tool"]): row["fixes"]
        for row in fixes.recurrence(store, ["kind", "tool"])
    }
    assert pairs[("nikkud", "model-a")] == 4 and pairs[("wording", "model-b")] == 1
    top = fixes.recurring(store)
    assert [(one["before"], one["units"]) for one in top] == [(POINTED, 3)]
    with pytest.raises(ValueError, match="nonsense"):
        fixes.recurrence(store, ["nonsense"])


def test_gold_is_the_authors_hand_and_what_a_person_accepted(store: Store) -> None:
    _ledger(store)
    proposed = store.propose_correction(
        stage="reader", who="reader", term="זזז", before="זזז", after="חחח", span="s-07 t0"
    )
    store.settle_correction(proposed, accept=True)
    waiting = store.propose_correction(
        stage="reader", who="reader", term="ככך", before="ככך", after="ללל", span="s-08 t0"
    )
    assert waiting
    found = fixes.gold(store)
    assert [(row["before"], row["after"]) for row in found] == [
        ("וָוָו", "וַוַו"),
        ("זזז", "חחח"),
    ], "no model's fix, no deletion, no unsettled proposal, one line per accepted fix"
    assert "judge" not in found[0] and "id" not in found[0]
    assert fixes.gold(store, stage="nothing") == []


# -- the command ------------------------------------------------------------------------


def test_the_command_reports_by_kind_and_tool_and_exports_gold(
    store: Store, tmp_path: Path
) -> None:
    _ledger(store)
    runner = CliRunner()
    done = runner.invoke(
        app,
        [
            "tables",
            "fixes",
            "--by",
            "kind",
            "--by",
            "tool",
            "--recurring",
            "5",
            "--store",
            str(store.path),
        ],
    )
    assert done.exit_code == 0, done.output
    lines = done.output.splitlines()
    assert "4 fixes" in lines[0] and "nikkud  model-a" in lines[0]
    assert any("3x" in line and POINTED in line for line in lines)
    out = tmp_path / "gold.jsonl"
    done = runner.invoke(
        app, ["tables", "fixes", "--gold", "--out", str(out), "--store", str(store.path)]
    )
    assert done.exit_code == 0, done.output
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [row["who"] for row in rows] == ["author"]
    wrong = runner.invoke(app, ["tables", "fixes", "--by", "nonsense", "--store", str(store.path)])
    assert wrong.exit_code != 0


# -- carried to the box (targum-internal#587) -------------------------------------------


def test_the_laptops_fixes_reach_the_box_once_and_a_readers_never(
    tmp_path: Path, store: Store
) -> None:
    _ledger(store)
    store.correct("reader", who="reader", before="x", after="y", span="local")
    lines = list(fixes.export(store))
    assert len(lines) == 7 and all(fixes.is_fix_line(line) for line in lines)
    assert not any('"who": "reader"' in line for line in lines)
    box = Store(tmp_path / "box.db")
    first = fixes.take(box, [*lines, '{"correction": {"stage": "", "who": "model"}}'])
    assert (first.added, first.unchanged, first.refused) == (7, 0, 1)
    again = fixes.take(box, lines)
    assert (again.added, again.unchanged) == (0, 7), "a push run twice changes nothing"
    here = {row["before"]: row for row in store.corrections()}
    there = {row["before"]: row for row in box.corrections()}
    assert there["אאא"]["at"] == here["אאא"]["at"] and there["אאא"]["tool"] == "model-b"


def test_the_cli_carries_fixes_beside_the_tables_and_push_names_the_box_store(
    tmp_path: Path, store: Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ledger(store)
    (tmp_path / "laptop").mkdir()
    (tmp_path / "box").mkdir()
    laptop = TablesStore(tmp_path / "laptop" / "corpus.db")
    runner = CliRunner()
    out = tmp_path / "rows.jsonl"
    env = {"TARGUM_LEDGER": str(laptop.file)}
    done = runner.invoke(
        app, ["tables", "export", "--out", str(out), "--store", str(store.path)], env=env
    )
    assert done.exit_code == 0, done.output
    box_ledger = tmp_path / "box" / "corpus.db"
    left = runner.invoke(app, ["tables", "import", str(out), "--ledger", str(box_ledger)])
    assert left.exit_code == 1 and "pass --store" in left.output
    box = tmp_path / "box" / "targum.db"
    took = runner.invoke(
        app, ["tables", "import", str(out), "--ledger", str(box_ledger), "--store", str(box)]
    )
    assert took.exit_code == 0, took.output
    assert "Kept 7 fixes" in " ".join(took.output.split())
    assert len(Store(box).corrections()) == 7

    seen: dict[str, Any] = {}

    def run(command: list[str], *, stdin: Any, check: bool) -> subprocess.CompletedProcess[str]:
        seen["remote"] = command[-1]
        seen["lines"] = stdin.read().splitlines()
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(subprocess, "run", run)
    pushed = runner.invoke(
        app, ["tables", "push", "--host", "h", "--store", str(store.path)], env=env
    )
    assert pushed.exit_code == 0, pushed.output
    assert seen["remote"].endswith(
        "--ledger /var/lib/targum/corpus.db --store /var/lib/targum/targum.db -"
    )
    assert len(seen["lines"]) == 7
