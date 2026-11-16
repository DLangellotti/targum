"""French chat evals (targum-internal#644): the case set, the rubric that reads a reply,
and the stage hook that counts French's chat evals once a run holds its floors. Nothing
here calls a model."""

from __future__ import annotations

from pathlib import Path

import pytest

from targum import evals, stages
from targum.chat import rubric


def reply(recast: str, why: str = "", rest: str = "Super !") -> str:
    lines = [f"> {recast}", "= (gloss)"]
    if why:
        lines.append(f"~ {why}")
    lines += [rest, "= Great!"]
    return "\n".join(lines)


def case(kind: str, sent: str, **more: object) -> rubric.Case:
    return rubric.Case(id="t", sent=sent, kind=kind, **more)  # type: ignore[arg-type]


def test_the_french_set_is_whole_and_every_error_names_what_it_fixes() -> None:
    cases = rubric.load()
    kinds = {kind: [one for one in cases if one.kind == kind] for kind in rubric.KINDS}
    assert (len(kinds["correct"]), len(kinds["register"]), len(kinds["error"])) == (15, 5, 20)
    assert len({one.id for one in cases}) == len(cases)
    for one in kinds["error"]:
        assert one.error and rubric.says(one.sent, one.error), one
        assert not any(rubric.says(one.sent, fix) for fix in one.fix), one
    for one in cases:
        if one.keep:
            assert rubric.says(one.sent, one.keep), one


def test_words_are_found_whole() -> None:
    assert rubric.says("La voiture est vert.", "est vert")
    assert not rubric.says("La voiture est verte.", "est vert")
    assert rubric.says("Je suis allé à Paris.", "à paris")
    assert not rubric.says("Je suis allé à Paris.", "a paris")
    assert rubric.says("J’ai froid.", "j'ai froid")
    assert rubric.normal("Tu veux venir ?") == rubric.normal("tu veux venir ?")


def test_a_correct_line_said_back_with_no_why_passes() -> None:
    one = rubric.score(case("correct", "J'ai mangé une pomme."), reply("J'ai mangé une pomme."))
    assert one.kept and not one.why_shown and not one.gender_changed


def test_a_correct_line_given_a_why_is_the_failure_counted() -> None:
    sent = "Je suis contente de te voir."
    said = reply("Je suis content de te voir.", "Content agrees with the speaker.")
    one = rubric.score(case("correct", sent, keep="contente"), said)
    assert one.why_shown and not one.kept and one.gender_changed


def test_an_error_is_fixed_only_where_the_error_is_gone_and_a_fix_is_said() -> None:
    wrong = case("error", "J'ai allé à la plage.", fix=("je suis allé", "je suis allée"),
                 error="j'ai allé")  # fmt: skip
    fixed = rubric.score(wrong, reply("Je suis allé à la plage.", "Aller takes être."))
    assert fixed.fixed and fixed.why_shown
    carried = rubric.score(wrong, reply("J'ai allé à la plage."))
    assert not carried.fixed and not carried.why_shown
    elsewhere = rubric.score(wrong, reply("Je suis parti à la plage.", "Aller takes être."))
    assert not elsewhere.fixed, "the error is gone, but none of the fixes is said"
    calque = case("error", "Ça fait sens.", error="fait sens")
    assert rubric.score(calque, reply("Ça a du sens.", "Faire sens is a calque.")).fixed


def test_a_why_that_belongs_to_no_recast_is_not_shown() -> None:
    stray = "> Je sais pas.\n= I don't know.\nD'accord.\n~ Ne is dropped.\n= OK."
    one = rubric.score(case("register", "Je sais pas."), stray)
    assert not one.why_shown


def test_a_run_is_summarised_as_the_ledger_records_it() -> None:
    verdicts = [
        rubric.score(case("correct", "Il fait beau."), reply("Il fait beau.")),
        rubric.score(case("correct", "Je suis allée.", keep="allée"), reply("Je suis allé.", "x")),
        rubric.score(case("register", "Je sais pas."), reply("Je ne sais pas.", "Ne.")),
        rubric.score(
            case("error", "Je aime.", fix=("j'aime",), error="je aime"), reply("J'aime.", "x")
        ),
        rubric.score(case("error", "Il est tres.", fix=("très",), error="tres"), reply("x")),
    ]
    summary = rubric.summarise(verdicts)
    assert summary.scores == {
        "why_shown_on_correct_lines": 1,
        "why_shown_on_register_lines": 1,
        "reader_gender_changed": 1,
        "recast_kept_share": 0.5,
        "fixed_share": 0.5,
        "why_shown_on_errors_share": 0.5,
    }
    assert summary.over["reader_gender_changed"] == 1 and summary.over["fixed_share"] == 2


def test_the_runner_is_named_and_writes_what_the_floors_name() -> None:
    assert evals.script_for("chat/fr-cases") == "eval_chat_fr.py"
    assert evals.script_for("chat") == "eval_why.py"
    named = {f.metric for f in evals.floors(stages.FLOORS) if f.corpus == "fr-cases"}
    verdicts = [rubric.score(one, reply(one.sent)) for one in rubric.load()]
    assert named == set(rubric.summarise(verdicts).scores)


def _row(metric: str, score: float, system: str = "chat-contract") -> evals.Row:
    return evals.Row(
        at="2026-11-17", stage="chat", corpus="fr-cases", metric=metric, score=score, n=20,
        system=system, version="claude-opus-5", note="",
    )  # fmt: skip


def _passing() -> list[evals.Row]:
    return [
        _row(floor.metric, floor.at_least if floor.at_least is not None else 0.0)
        for floor in evals.floors(stages.FLOORS)
        if floor.corpus == "fr-cases"
    ]


def test_french_has_no_chat_evals_until_a_run_is_recorded() -> None:
    limits = evals.floors(stages.FLOORS)
    assert not stages._chat_evals_hold("fr", limits, [])
    assert not stages.facts("fr", rows=[]).chat_evals
    assert "no chat evals in the language" in stages.shortfall(
        stages.facts("fr", rows=[]), stages.Stage.beta
    )


def test_french_has_chat_evals_once_a_run_holds_every_floor() -> None:
    limits = evals.floors(stages.FLOORS)
    rows = _passing()
    assert stages._chat_evals_hold("fr", limits, rows)
    assert stages.facts("fr", rows=rows).chat_evals
    assert "no chat evals in the language" not in stages.shortfall(
        stages.facts("fr", rows=rows), stages.Stage.beta
    )


@pytest.mark.parametrize("metric", ["why_shown_on_correct_lines", "fixed_share"])
def test_one_floor_crossed_or_unmeasured_takes_them_away(metric: str) -> None:
    limits = evals.floors(stages.FLOORS)
    crossed = [
        _row(row.metric, 3.0 if metric.startswith("why") else 0.1) if row.metric == metric else row
        for row in _passing()
    ]
    assert not stages._chat_evals_hold("fr", limits, crossed)
    missing = [row for row in _passing() if row.metric != metric]
    assert not stages._chat_evals_hold("fr", limits, missing)
    # Another system's row is a comparison, not this set's run.
    other = [_row(row.metric, row.score, "other-model") for row in _passing()]
    assert not stages._chat_evals_hold("fr", limits, other)


def test_hebrew_keeps_its_chat_evals_and_a_language_with_no_set_has_none() -> None:
    limits = evals.floors(stages.FLOORS)
    assert stages._chat_evals_hold("he", limits, [])
    assert not stages._chat_evals_hold("ru", limits, _passing())


def test_the_committed_ledger_has_no_french_run_yet() -> None:
    """The run spends and has no approved cap: it waits for David. Until then French
    shows the gap rather than a pass nobody measured."""
    rows = evals.read(stages.LEDGER)
    assert not [row for row in rows if row.corpus == "fr-cases"]
    assert not stages.facts("fr").chat_evals


def test_the_case_file_is_in_the_repository() -> None:
    assert rubric.FRENCH_CASES == Path(stages.FLOORS).parent / "chat-fr-cases.jsonl"
