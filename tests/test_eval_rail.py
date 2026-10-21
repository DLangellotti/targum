"""The scoring behind `scripts/eval_rail.py` (targum-internal#324), on a tiny set and
with nothing asked of Jev: the checks are `record_turn`'s own, a gate may only add a
block, and precision and recall count a block as the positive class."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE.parent / "scripts" / "eval_rail.py"


def load_script() -> Any:
    spec = importlib.util.spec_from_file_location("eval_rail", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before it runs: a dataclass looks its own module up by name.
    sys.modules["eval_rail"] = module
    spec.loader.exec_module(module)
    return module


def case(id: str, spend: bool, wrote: str = "אני הלך לים") -> dict[str, Any]:
    return {"id": id, "kind": "t", "args": {"wrote": wrote, "language": "he"}, "spend": spend}


def said(refuse: float) -> dict[str, Any]:
    """A Choice answer putting `refuse` on the option that blocks, for every wording."""
    return {
        wording: {"choice": "", "probabilities": {"refuse": refuse, "other": 1 - refuse}}
        for wording in ("charge", "typed")
    }


@pytest.fixture(autouse=True)
def no_jev(monkeypatch: pytest.MonkeyPatch) -> None:
    from targum import jev

    def refuse(*_: Any, **__: Any) -> Any:
        raise AssertionError("scoring asked Jev, which costs money")

    monkeypatch.setattr(jev, "ask", refuse)


def test_the_checks_are_record_turns_own_and_stop_before_the_claim(tmp_path: Path) -> None:
    script = load_script()
    assert script.checks({"wrote": "אני הלך לים אתמול", "language": "he"}, tmp_path) is None
    assert script.checks({"wrote": "   ", "language": "he"}, tmp_path)
    assert script.checks({"wrote": "what does this mean", "language": "he"}, tmp_path)
    assert script.checks({"wrote": "שלום", "language": "yi"}, tmp_path)
    assert script.checks({"wrote": " ".join(["מילה"] * 61), "language": "he"}, tmp_path)
    sixty = {"wrote": " ".join(["מילה"] * 60), "language": "he"}
    assert script.checks(sixty, tmp_path, rail=False) is None, "the word limit's own edge"
    assert script.checks(sixty, tmp_path), "and the rail's repeats, in front of the claim"


def test_precision_and_recall_count_a_block_as_the_positive() -> None:
    script = load_script()
    cases = [case("a", True), case("b", True), case("c", False), case("d", False)]
    found = script.score(cases, {"a": True, "b": False, "c": True, "d": False})
    assert (found.caught, found.false_blocks, found.missed, found.passed) == (1, 1, 1, 1)
    assert found.precision == 0.5 and found.recall == 0.5
    nothing = script.score(cases, dict.fromkeys("abcd", False))
    assert nothing.precision == 1.0, "no block is never a wrong block"
    assert nothing.recall == 0.0


def test_the_gate_can_only_say_no() -> None:
    script = load_script()
    cases = [case("stopped", False), case("let", False), case("own", True), case("quiet", False)]
    by_checks = {"stopped": True, "let": False, "own": False, "quiet": False}
    answers = {"stopped": said(0.0), "let": said(0.9), "own": said(0.2)}
    both = script.gated(cases, by_checks, answers, "charge", 0.5)
    assert both["stopped"], "Jev saying yes does not undo a check's no"
    assert both["let"], "Jev's no is added"
    assert not both["own"], "under the threshold is not a block"
    assert not both["quiet"], "no answer leaves it to the checks"
    assert not script.gated(cases, by_checks, answers, "charge", 0.95)["let"]


def test_an_answer_is_read_by_the_weight_on_refusing() -> None:
    script = load_script()
    assert script.refused(None) == 0.0
    assert script.refused({"probabilities": {"refuse": 0.3, "charge": 0.7}}) == 0.3
    assert script.refused({"choice": "refuse"}) == 1.0
    assert script.refused({"choice": "charge"}) == 0.0


def test_every_wording_offers_the_option_that_blocks_in_the_language_named() -> None:
    script = load_script()
    asked = script.questions({"wrote": "je suis", "language": "fr-CA"})
    assert set(asked) == set(script.WORDINGS)
    for question in asked.values():
        assert question["type"] == "choice"
        assert script.NO in question["criteria"]
        assert "French" in question["instructions"]
    assert script.state({"wrote": "x"}) == {"wrote": "x", "language": "he"}


def test_the_report_names_what_the_gate_added_and_what_it_refused() -> None:
    script = load_script()
    cases = [case("own", True), case("paste", False), case("empty", False, "")]
    by_checks = {"own": False, "paste": False, "empty": True}
    answers = {"own": said(0.6), "paste": said(0.8), "empty": said(0.1)}
    out = script.report(cases, by_checks, answers, (0.5,))
    assert "| checks alone | 1 | 1 | 0 | 1.00 | 0.50 |" in out
    assert "catches the checks miss (1): paste" in out
    assert "false blocks (1): own" in out


def test_the_labelled_set_is_whole() -> None:
    kept = json.loads((HERE / "fixtures" / "rail" / "record_turn.json").read_text("utf-8"))
    assert "labelled by Claude" in kept["about"]
    cases = kept["cases"]
    assert 60 <= len(cases) <= 100
    assert len({one["id"] for one in cases}) == len(cases)
    for one in cases:
        assert isinstance(one["spend"], bool) and one["why"] and "wrote" in one["args"]
    assert {one["spend"] for one in cases} == {True, False}


def test_the_table_says_what_the_rail_adds_to_the_checks() -> None:
    script = load_script()
    cases = [case("own", True), case("paste", False), case("markup", False)]
    before = {"own": False, "paste": False, "markup": False}
    after = {"own": False, "paste": False, "markup": True}
    table = script.report(cases, after, {}, (0.5,), before)
    assert "| checks alone | 0 | 2 | 0 | 1.00 | 0.00 |" in table
    assert "| checks + deterministic rail | 1 | 1 | 0 | 1.00 | 0.50 |" in table
    assert "The rail catches (1): markup" in table
    assert "The rail's false blocks (0)" in table
