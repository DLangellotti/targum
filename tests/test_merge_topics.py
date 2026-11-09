"""scripts/merge_topics.py and tag_topics.py's incremental run (targum-internal#606).

Synthetic lemmas only: the lexicon is private and never enters the repository.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

from targum import topics

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
HEADER = [
    "id",
    "lemma",
    "glossed_as",
    "pos",
    "gloss",
    "count",
    "register",
    "sonnet-5-5",
    "sonnet-5-5_confidence",
    "opus-5-5",
    "opus-5-5_confidence",
    "agreed",
    "decision",
    "who",
    "at",
    "why",
]


def _script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # A dataclass looks its module up by name while it is defined.
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


def _row(i: int, lemma: str, a: str, b: str, agreed: str, low: bool = False) -> dict[str, str]:
    return {
        "id": str(i),
        "lemma": lemma,
        "glossed_as": lemma,
        "pos": "NOUN",
        "gloss": "x",
        "count": "1",
        "register": "modern",
        "sonnet-5-5": a,
        "sonnet-5-5_confidence": "low" if low else "high",
        "opus-5-5": b,
        "opus-5-5_confidence": "high",
        "agreed": agreed,
        "decision": "",
        "who": "",
        "at": "",
        "why": "",
    }


def test_decisions_rule_and_gap_each_settle_their_rows() -> None:
    merge = _script("merge_topics")
    full = [
        _row(0, "w-agreed", "food", "food", "food"),
        _row(1, "w-split", "school", "general", ""),
        _row(2, "w-low", "law", "law", "law", low=True),
        _row(5000, "w-rare-split", "money", "work", ""),
        _row(5001, "w-rare-shared", "money,work", "work", "work"),
    ]
    base = {"w-agreed": ["food"], "w-low": ["law"], "w-rare-shared": ["work"]}
    decisions = [
        {"id": 1, "lemma": "w-split", "topics": ["general"], "confidence": "high", "note": "n"},
        {"id": 2, "lemma": "w-low", "topics": ["security"], "confidence": "low", "note": ""},
        {"id": 3, "lemma": "w-wrong-id", "topics": ["food"], "confidence": "high"},
    ]
    gap = [
        _row(0, "g-agreed", "family", "family", "family"),
        _row(1, "g-split", "health", "science", ""),
        _row(2, "g-low", "travel", "travel", "travel", low=True),
        _row(3, "g-unanswered", "food", "", ""),
    ]
    got = merge.merge(base, full, decisions, gap, at="2026-11-09")
    assert got.lemmas == {
        "w-agreed": ["food"],
        "w-split": ["general"],
        "w-low": ["security"],
        "w-rare-split": ["general"],
        "w-rare-shared": ["work"],
        "g-agreed": ["family"],
        "g-split": ["general"],
        "g-low": ["travel"],
    }
    by = {row["lemma"]: row for row in got.full}
    assert (by["w-split"]["who"], by["w-split"]["decision"]) == ("ling-he", "general")
    assert by["w-low"]["why"] == "unsure"
    assert (by["w-rare-split"]["who"], by["w-rare-split"]["decision"]) == ("rule", "general")
    assert by["w-rare-shared"]["decision"] == "", "the models settled it; nothing to decide"
    assert got.counts["decision_mismatch"] == 1
    assert got.counts["gap_unanswered"] == 1
    assert [(one["lemma"], one["kind"]) for one in got.for_review] == [
        ("g-split", "disagreement"),
        ("g-low", "low-confidence"),
    ]


def test_a_decision_in_review_tsv_outranks_the_file_and_the_rule() -> None:
    merge = _script("merge_topics")
    full = [_row(1, "w-split", "school", "general", ""), _row(5000, "w-rare", "a", "b", "")]
    full[0].update(decision="school", who="ling-he", at="2026-11-10", why="study")
    full[1].update(decision="culture", who="ling-he", at="2026-11-10", why="")
    gap = [_row(0, "g-split", "health", "science", "")]
    gap[0].update(decision="health", who="ling-he", at="2026-11-10", why="")
    decisions = [{"id": 1, "lemma": "w-split", "topics": ["general"], "confidence": "high"}]
    got = merge.merge({}, full, decisions, gap, at="2026-11-11")
    assert got.lemmas == {"w-split": ["school"], "w-rare": ["culture"], "g-split": ["health"]}
    assert got.full[0]["at"] == "2026-11-10"
    assert got.counts["decided_kept"] == 1
    assert got.for_review == []


def test_a_rule_decision_is_the_rules_to_redo() -> None:
    merge = _script("merge_topics")
    gap = [_row(0, "g-split", "health", "science", "")]
    first = merge.merge({}, [], [], gap, at="2026-11-09")
    again = merge.merge({}, [], [], first.gap, at="2026-11-12")
    assert again.gap[0]["who"] == "rule" and again.gap[0]["at"] == "2026-11-12"
    assert again.lemmas == {"g-split": ["general"]}


def test_the_lexicon_is_written_only_past_95_on_what_can_be_measured() -> None:
    merge = _script("merge_topics")
    assert merge.passes({"news": None, "conversation": 0.95, "literature": 0.99})
    assert not merge.passes({"news": None, "conversation": 0.949, "literature": 0.99})
    assert not merge.passes({"news": None, "conversation": None, "literature": None})


def test_review_tsv_is_backed_up_and_round_trips(tmp_path: Path) -> None:
    merge = _script("merge_topics")
    file = tmp_path / "review.tsv"
    file.write_text("\t".join(HEADER) + "\n", encoding="utf-8")
    row = _row(0, "w-a", "food", "food", "food")
    row.update(decision="food", who="ling-he", at="2026-11-09", why="a\tb")
    merge.write_review(file, HEADER, [row])
    assert list(tmp_path.glob("review.tsv.bak-*"))
    header, rows = merge.read_review(file)
    assert header == HEADER and rows[0]["who"] == "ling-he" and rows[0]["why"] == "a\tb"


def test_a_gap_file_is_read_commonest_first_across_its_registers(tmp_path: Path) -> None:
    tag = _script("tag_topics")
    file = tmp_path / "gap.json"
    file.write_text(
        json.dumps(
            {
                "missing": {
                    "conversation": [{"lemma": "c1"}, {"lemma": "both"}, {"lemma": "c3"}],
                    "literature": [{"lemma": "both"}, {"lemma": "l2"}],
                }
            }
        ),
        encoding="utf-8",
    )
    assert tag.read_only(file) == ["c1", "both", "l2", "c3"]
    file.write_text(json.dumps(["b", "a", "b"]), encoding="utf-8")
    assert tag.read_only(file) == ["b", "a"]


def test_a_rerun_keeps_the_decisions_review_tsv_holds(tmp_path: Path) -> None:
    tag = _script("tag_topics")
    file = tmp_path / "review.tsv"
    row = _row(4, "w-a", "food", "law", "")
    row.update(decision="law", who="ling-he", at="2026-11-09", why="w")
    lines = ["\t".join(HEADER), "\t".join(row[name] for name in HEADER)]
    lines.append("\t".join(_row(5, "w-b", "x", "x", "x")[name] for name in HEADER))
    file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert tag._decided(file) == {("4", "w-a"): ("law", "ling-he", "2026-11-09", "w")}


def test_the_listed_lemmas_come_only_from_the_tables(tmp_path: Path) -> None:
    from targum.tables.store import Contribution, Store

    tag = _script("tag_topics")
    store = Store(tmp_path / "tables.db")
    store.write(
        Contribution("words", "conversation", "unit-a", "src", "CC0", "tool", "words/1"),
        {("w-noun", "NOUN"): 9, ("w-verb", "VERB"): 7, ("w-verb", "NOUN"): 1},
    )
    store.write(
        Contribution("words", "conversation", "unit-b", "src", "CC0", "tool", "words/1"),
        {("w-bare", "NOUN"): 3},
    )
    glosses = {"w-noun": ("a thing", ""), topics.glossed_as("w-verb", "VERB"): ("to do", "")}
    lemmas, missing = tag.listed(store, ["w-verb", "w-absent", "w-noun", "w-bare"], glosses.get)
    assert [(one.lemma, one.pos, one.count) for one in lemmas] == [
        ("w-verb", "VERB", 8),
        ("w-noun", "NOUN", 9),
    ]
    assert missing == ["w-bare"], "no gloss: listed apart; never counted: never asked"
