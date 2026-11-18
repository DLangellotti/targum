"""`scripts/build_roots.py --split` (targum-internal#592): a request that ran out of
tokens is re-asked in parts, and the parts are merged back into the one answer the run
keys it under, with every part's tokens counted."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build_roots.py"


def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_roots", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_roots"] = module
    spec.loader.exec_module(module)
    return module


def piece(ids: range, output: int, stop: str = "end_turn") -> dict[str, object]:
    return {
        "type": "succeeded",
        "text": json.dumps({"rows": [{"id": i} for i in ids]}),
        "stop_reason": stop,
        "usage": {"input_tokens": 10, "output_tokens": output, "cache_creation": None},
    }


def test_a_request_is_cut_into_parts_numbered_as_the_run_numbers_them() -> None:
    build = script()
    chunk = list(range(7700, 7800))
    parts = build._parts(chunk, 25)
    assert [p[0] for p in parts] == [7700, 7725, 7750, 7775]
    assert sum(parts, []) == chunk
    assert build._parts(chunk, None) == [chunk] == build._parts(chunk, 200)


def test_the_parts_merge_into_one_answer_with_every_token_counted() -> None:
    build = script()
    whole = build.merged([piece(range(0, 2), 100), piece(range(2, 4), 50)])
    assert [row["id"] for row in json.loads(whole["text"])["rows"]] == [0, 1, 2, 3]
    assert whole["usage"] == {"input_tokens": 20, "output_tokens": 150}
    assert (whole["type"], whole["stop_reason"], whole["parts"]) == ("succeeded", "end_turn", 2)


def test_a_part_that_failed_or_ran_out_leaves_the_request_to_be_asked_again() -> None:
    build = script()
    failed = {"type": "errored", "usage": {}, "error": "overloaded"}
    some = build.merged([piece(range(0, 2), 100), failed])
    assert [row["id"] for row in json.loads(some["text"])["rows"]] == [0, 1]
    short = build.merged([piece(range(0, 2), 100, stop="max_tokens"), piece(range(2, 4), 9)])
    assert short["stop_reason"] == "max_tokens"
    nothing = build.merged([failed, failed])
    assert nothing["type"] == "errored" and "text" not in nothing


def test_the_lexicon_is_scored_against_wiktionary_under_the_weak_letter_rules() -> None:
    from targum.root_lexicon import score_against_wiktionary

    wiktionary = {
        "עלה": frozenset({"ע־ל־ה"}),
        "בית": frozenset({"ב־י־ת"}),
        "כתב": frozenset({"כ־ת־ב"}),
    }
    lexicon = {
        "עלה": {"root": "ע־ל־י"},
        "בית": {"root": None},
        "כתב": {"root": "כ־ת־ת"},
        "מחשב": {"root": "ח־ש־ב"},
    }
    found = score_against_wiktionary(lexicon, wiktionary)
    assert (found["both"], found["strict"], found["agreed"], found["ours_none"]) == (2, 0, 1, 1)
    assert found["rate"] == 0.5 and found["misses"] == [("כתב", "כ־ת־ת", "כ־ת־ב")]
