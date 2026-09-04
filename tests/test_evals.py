"""The score ledger: that a number, once taken, survives the next one."""

from __future__ import annotations

import json
from pathlib import Path

from targum import evals


def row(**over: object) -> evals.Row:
    base: dict[str, object] = {
        "at": "2026-09-04",
        "stage": "lemma",
        "system": "dicta/joint",
        "version": "1",
        "metric": "lemma",
        "score": 0.842,
        "n": 200,
        "corpus": "iahltwiki",
    }
    base.update(over)
    return evals.Row(**base)  # type: ignore[arg-type]


def test_a_ledger_that_is_not_there_reads_as_empty(tmp_path: Path) -> None:
    assert evals.read(tmp_path / "nothing.jsonl") == []


def test_a_row_survives_the_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    assert evals.append([row()], path) == 1
    assert evals.read(path) == [row()]


def test_appending_keeps_what_was_there(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    evals.append([row(score=0.80)], path)
    evals.append([row(score=0.84, version="2")], path)
    scores = [entry.score for entry in evals.read(path)]
    assert scores == [0.80, 0.84], "an append that loses the earlier number is not a ledger"


def test_the_same_version_twice_is_recorded_twice(tmp_path: Path) -> None:
    """#163's fourth criterion: a second run of one version appends an identical score.

    Nothing here may collapse them, because two rows agreeing is the only evidence that
    the harness is deterministic, and a file that de-duplicates has thrown it away.
    """
    path = tmp_path / "ledger.jsonl"
    evals.append([row()], path)
    evals.append([row()], path)
    kept = evals.read(path)
    assert len(kept) == 2
    assert kept[0] == kept[1]


def test_movement_is_measured_against_a_different_version(tmp_path: Path) -> None:
    rows = [
        row(version="1", score=0.80),
        row(version="1", score=0.80),
        row(version="2", score=0.84),
    ]
    pair = evals.moved(rows, rows[0].key())
    assert pair is not None
    older, newer = pair
    assert (older.version, newer.version) == ("1", "2")
    assert round(newer.score - older.score, 4) == 0.04


def test_one_version_has_not_moved_yet(tmp_path: Path) -> None:
    assert evals.moved([row()], row().key()) is None


def test_a_rerun_of_one_version_reports_no_movement() -> None:
    """Two rows of the same version are the determinism check, not a trend. Reading
    them as a trend would report nothing moved and hide the move before them."""
    rows = [
        row(version="1", score=0.80),
        row(version="2", score=0.84),
        row(version="2", score=0.84),
    ]
    pair = evals.moved(rows, rows[0].key())
    assert pair is not None
    assert (pair[0].version, pair[1].version) == ("1", "2")


def test_a_new_system_still_moves_the_same_measurement() -> None:
    """The reason the system is not part of the key. In this codebase an annotator's name
    *is* its version — the name is the cache key — so keying on it would file every
    change under a heading of its own and nothing would ever be seen to move. Stanza to
    DICTA on one corpus is the trend the harness exists to show."""
    rows = [
        row(system="stanza", version="1.14.0", score=0.71),
        row(system="dicta-il/dictabert-joint", version="joint", score=0.842),
    ]
    pair = evals.moved(rows, rows[0].key())
    assert pair is not None
    assert pair[0].system == "stanza" and pair[1].system.startswith("dicta")
    assert round(pair[1].score - pair[0].score, 4) == 0.132


def test_latest_takes_the_last_row_not_the_latest_date() -> None:
    rows = [row(at="2026-09-04", score=0.80), row(at="2026-09-04", score=0.84)]
    assert evals.latest(rows)[rows[0].key()].score == 0.84


def test_a_scorecard_becomes_rows() -> None:
    payload = {
        "gold": {"corpus": "iahltwiki"},
        "cards": [
            {
                "annotator": "dicta-il/dictabert-joint",
                "corpus": "iahltwiki",
                "paired": 4321,
                "rates": {"lemma": 0.842, "pos": 0.974, "binyan_accuracy": None},
            }
        ],
    }
    rows = evals.rows_from_scorecard(payload, at="2026-09-04")
    assert {entry.metric for entry in rows} == {"lemma", "pos"}, "a null rate is not a score"
    assert all(entry.n == 4321 and entry.stage == "lemma" for entry in rows)


def test_a_metric_with_nothing_to_measure_is_left_out() -> None:
    """A base of zero is not a score of zero. Writing it down as one would read, on the
    next run, as a stage that collapsed rather than one that never ran."""
    payload = {"cards": [{"annotator": "x", "corpus": "c", "paired": 0, "rates": {"root": None}}]}
    assert evals.rows_from_scorecard(payload) == []


def test_the_table_says_what_moved(tmp_path: Path) -> None:
    rows = [row(version="1", score=0.80), row(version="2", score=0.84)]
    drawn = evals.table(rows)
    assert "lemma" in drawn and "+0.0400" in drawn


def test_an_empty_ledger_says_so() -> None:
    assert "No scores" in evals.table([])


def test_rows_are_written_one_per_line_and_stay_readable(tmp_path: Path) -> None:
    """The file is read by `git log -p` as much as by this module."""
    path = tmp_path / "ledger.jsonl"
    evals.append([row(), row(version="2")], path)
    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["stage"] == "lemma"
