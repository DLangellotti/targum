"""The sentence's shape, read off the tree `dictabert-joint` already returns (#150).

Against `fixtures/syntax/predict.json`, five sentences put through the model once, at the
pinned revision, and recorded exactly as `predict(..., output_style="json")` answered. No
test here loads the model; `measure_syntax.py` is loaded by path because `scripts/` is not
a package, and loading it imports no torch.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from targum.annotate import dicta, syntax

FIXTURE = Path(__file__).parent / "fixtures" / "syntax" / "predict.json"


@pytest.fixture(scope="module")
def recorded() -> dict[str, Any]:
    body: dict[str, Any] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return body


@pytest.fixture(scope="module")
def said(recorded: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {one["text"]: one for one in recorded["sentences"]}


@pytest.fixture(scope="module")
def script() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "measure_syntax.py"
    spec = importlib.util.spec_from_file_location("measure_syntax", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before it runs, because a dataclass looks its own module up by name.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_the_fixture_is_the_model_the_annotator_runs(recorded: dict[str, Any]) -> None:
    assert recorded["model"] == dicta.MODEL
    assert recorded["revision"] == dicta.REVISION


def test_a_relative_inside_a_complement_is_four_deep_and_four_clauses(
    said: dict[str, dict[str, Any]],
) -> None:
    # אמר → הלך (ccomp) → שהילד (nsubj) → שראה (acl:relcl) → אתמול: four arcs. And four
    # clauses: the root, the complement, the relative, and ואכל joined to הלך by conj.
    tree = syntax.tree(said["הוא אמר שהילד שראה אתמול הלך הביתה ואכל."])
    assert (tree.depth, tree.clauses, tree.words) == (4, 4, 8)


def test_a_flat_sentence_is_one_deep_and_one_clause(said: dict[str, dict[str, Any]]) -> None:
    tree = syntax.tree(said["לא, היא לא היתה מעודה ביפו."])
    assert (tree.depth, tree.clauses) == (1, 1)


def test_a_verb_joined_by_conj_is_a_second_clause(said: dict[str, dict[str, Any]]) -> None:
    tree = syntax.tree(said["את שמע העיר שמעה, אבל בה לא היתה."])
    assert tree.clauses == 2


def test_an_infinitive_completing_its_verb_is_not_a_clause(
    said: dict[str, dict[str, Any]],
) -> None:
    # Two clauses: זוכה and לבלום, joined by conj. עלול is an aux here, not a clause.
    text = (
        "עם זאת, כאמור, הממשלה אינה זוכה לתמיכה בסנאט והסנאט עלול לבלום כל חקיקה ממשלתית "
        "בבית התחתון."
    )
    tree = syntax.tree(said[text])
    assert (tree.depth, tree.clauses, tree.words) == (3, 2, 16)


def test_one_word_is_no_depth_and_one_clause(said: dict[str, dict[str, Any]]) -> None:
    tree = syntax.tree(said["שלום."])
    assert (tree.depth, tree.clauses, tree.words) == (0, 1, 1)
    assert tree.arcs == ((-1, "root"), (0, "punct"))


def test_the_pairs_are_the_models_own_in_its_order(said: dict[str, dict[str, Any]]) -> None:
    one = said["הוא אמר שהילד שראה אתמול הלך הביתה ואכל."]
    tree = syntax.tree(one)
    assert len(tree.arcs) == len(one["tokens"])
    assert tree.arcs[1] == (-1, "root")
    assert tree.arcs[3] == (2, "acl:relcl")


def test_on_tokens_lines_up_with_what_the_annotator_keeps(
    said: dict[str, dict[str, Any]],
) -> None:
    # The same words `dicta._tokens` makes a Token of, one pair each, with heads counted
    # in that list rather than in the model's.
    for one in said.values():
        pairs = syntax.tree(one).on_tokens()
        assert len(pairs) == len(dicta._tokens(one))
        assert sum(head == syntax.ROOT for head, _ in pairs) == 1
        assert all(-1 <= head < len(pairs) for head, _ in pairs)
    text = "לא, היא לא היתה מעודה ביפו."
    # The comma after לא is gone, so היתה, fifth to the model, is fourth here.
    assert syntax.tree(said[text]).on_tokens()[0] == (3, "advmod")


def test_a_malformed_tree_reads_shallow_rather_than_forever() -> None:
    def word(head: Any, rel: str = "dep") -> dict[str, Any]:
        return {"syntax": {"dep_head_idx": head, "dep_func": rel}, "morph": {"pos": "NOUN"}}

    looped = {"tokens": [word(1), word(0)]}
    assert syntax.tree(looped).depth == 1
    stray = {"tokens": [word(-1, "root"), word(7)]}
    assert syntax.tree(stray).depth == 0
    assert syntax.tree({"tokens": [word("x")]}).arcs == ((-1, "dep"),)
    assert syntax.tree({}) == syntax.Tree(depth=0, clauses=0, words=0, arcs=())


def test_a_subtype_counts_as_its_relation() -> None:
    assert syntax.base("acl:relcl") == "acl"
    assert syntax.base("nsubj") == "nsubj"


def test_loading_the_script_loads_no_model(script: ModuleType) -> None:
    for name in ("torch", "transformers"):
        assert not hasattr(script, name)


def test_spearman_is_one_on_the_same_order_and_minus_one_reversed(script: ModuleType) -> None:
    assert script.spearman([1, 2, 3, 4], [10, 20, 30, 45]) == pytest.approx(1.0)
    assert script.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert script.spearman([1, 1, 1], [1, 2, 3]) is None
    assert script.spearman([1, 2], [1, 2]) is None


def test_ties_share_their_ranks(script: ModuleType) -> None:
    assert script.ranks([5, 1, 5, 3]) == [3.5, 1.0, 3.5, 2.0]


def test_stored_bytes_are_the_two_numbers_added_to_a_row(script: ModuleType) -> None:
    pairs = [(1, "nsubj"), (-1, "root"), (1, "obj")]
    relations = {"nsubj": 0, "obj": 1, "root": 12}
    # ",1,0" + ",-1,12" + ",1,1"
    assert script.row_bytes(pairs, relations) == 4 + 6 + 4
    assert script.field_bytes([(-1, "root")]) == len(',"head":-1,"rel":"root"')
