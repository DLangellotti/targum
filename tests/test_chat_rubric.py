"""French chat evals (targum-internal#644): the case set, the rubric that reads a reply,
and the stage hook that counts French's chat evals once a run holds its floors. Nothing
here calls a model."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from targum import evals, stages
from targum.chat import CHAT_MODEL, hebrew, rubric

RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "eval_chat_fr.py"

#: What a run of today's French contract is recorded under (`eval_chat_fr.SYSTEM`).
SYSTEM = f"chat-contract/fr{hebrew.FRENCH_CONTRACT_VERSION}"


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
    assert (len(kinds["correct"]), len(kinds["register"]), len(kinds["error"])) == (15, 5, 22)
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
    calque = case(
        "error", "Ça fait sens.", fix=("a du sens", "a un sens", "est logique", "se tient"),
        error="fait sens",
    )  # fmt: skip
    assert rubric.score(calque, reply("Ça a du sens.", "Faire sens is a calque.")).fixed
    assert not rubric.score(calque, reply("C'est bien.", "x")).fixed, "a fix must be said"


def test_the_set_s_one_unlisted_fix_is_gone() -> None:
    """qa on #1287: an error with no fixes listed counted any recast as fixed."""
    assert all(one.fix for one in rubric.load() if one.kind == "error")


def test_a_why_under_the_second_line_of_a_recast_is_shown() -> None:
    """The recast may run to two sentences, and a `~ ` under either is shown."""
    two = "> Je suis là.\n= I'm here.\n> Je suis allé à Paris.\n= I went.\n~ Aller takes être."
    one = rubric.score(case("correct", "Je suis là. Je suis allé à Paris."), two)
    assert one.why_shown and one.recast == "Je suis là. Je suis allé à Paris."
    assert one.kept


def test_a_register_line_silently_corrected_is_counted() -> None:
    """qa on #1287: *je ne sais pas* for *je sais pas* is a correction with no `~ `."""
    silent = rubric.score(case("register", "Je sais pas."), reply("Je ne sais pas."))
    assert not silent.why_shown and not silent.kept
    assert rubric.summarise([silent]).scores["register_lines_changed"] == 1
    kept = rubric.score(case("register", "Je sais pas."), reply("Je sais pas !"))
    assert kept.kept


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
        "register_lines_changed": 1,
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


def _row(
    metric: str,
    score: float,
    system: str = SYSTEM,
    version: str = CHAT_MODEL,
    gold: str | None = None,
) -> evals.Row:
    pin = gold if gold is not None else evals.fingerprint([stages.CHAT_EVAL_CASES["fr"]])
    return evals.Row(
        at="2026-11-17", stage="chat", corpus="fr-cases", metric=metric, score=score, n=20,
        system=system, version=version, note=evals.marked("ling-fr's learner lines", pin),
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


def test_the_first_run_is_history_and_holds_no_floor() -> None:
    """The first run (2026-11-17, David's go, $1.78) measured the French contract before
    it kept spoken French as written: two register lines were "corrected". It is kept as
    a measurement of that contract, recorded under its name, and breaches no floor of the
    contract that followed it."""
    rows = [
        row
        for row in evals.read(stages.LEDGER)
        if row.corpus == "fr-cases" and row.system == "chat-contract"
    ]
    assert rows
    scores = {row.metric: row.score for row in rows}
    assert scores["register_lines_changed"] == 2 and scores["why_shown_on_register_lines"] == 2
    floors = [f for f in evals.floors(stages.FLOORS) if f.corpus == "fr-cases"]
    assert floors and {f.system for f in floors} == {SYSTEM}
    assert not evals.breaches(rows, floors)


def test_the_fixed_contract_holds_and_french_has_its_chat_evals() -> None:
    """The fixed contract's first run (2026-11-17, David's go, $1.92) holds every floor,
    so French's stage no longer shows the chat-evals gap."""
    rows = [
        row
        for row in evals.read(stages.LEDGER)
        if row.corpus == "fr-cases" and row.system == SYSTEM
    ]
    assert rows
    floors = [f for f in evals.floors(stages.FLOORS) if f.corpus == "fr-cases"]
    assert not evals.breaches(rows, floors)
    assert stages.facts("fr").chat_evals


def test_the_contract_keeps_spoken_french_and_names_the_visiting_calque() -> None:
    # Read with its line breaks folded: the prompt wraps where the source does.
    contract = " ".join(hebrew.french_contract().split())
    assert "Spoken French is right French" in contract
    assert "je sais pas" in contract and 'no "~ " line' in contract
    assert "In your own lines, write the full negation" in contract
    assert "j'ai visité mon oncle" in contract
    # A spoken line's own mistake is still fixed, and a mixed line keeps its register.
    assert "si j'aurais su" in contract and "j'ai pas allé becomes je suis" in contract
    # The contract's examples are not the eval's lines: a case it spells out tests
    # nothing (qa on #1299).
    cases = " ".join(rubric.normal(one.sent) for one in rubric.load())
    for example in (
        "j'ai visité mon oncle",
        "si j'aurais su",
        "j'ai pas allé",
        "il faut que je vais",
    ):
        assert example not in cases, example


def test_the_case_file_is_in_the_repository() -> None:
    assert rubric.FRENCH_CASES == Path(stages.FLOORS).parent / "chat-fr-cases.jsonl"


def test_a_stale_run_does_not_keep_french_green() -> None:
    """qa on #1287: a run on cases since changed, or at a model since replaced, says
    nothing about the chat now, and does not count."""
    limits = evals.floors(stages.FLOORS)
    old_cases = [_row(row.metric, row.score, gold="0123456789ab") for row in _passing()]
    assert not stages._chat_evals_hold("fr", limits, old_cases)
    old_model = [_row(row.metric, row.score, version="claude-opus-4") for row in _passing()]
    assert not stages._chat_evals_hold("fr", limits, old_model)
    # A current run after a stale one counts; a stale breach after it does not undo it.
    stale_breach = [_row("fixed_share", 0.1, gold="0123456789ab")]
    assert stages._chat_evals_hold("fr", limits, old_cases + _passing() + stale_breach)


def _runner(monkeypatch: pytest.MonkeyPatch) -> Any:
    from targum.chat import hebrew

    monkeypatch.setattr(hebrew, "common_words", lambda *a, **k: ["le", "la", "être", "avoir"])
    spec = importlib.util.spec_from_file_location("eval_chat_fr_under_test", RUNNER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _no_model(monkeypatch: pytest.MonkeyPatch, replies: list[str] | None) -> list[int]:
    """Stand-ins for the client and the turns: `replies` is what the model would say, and
    None is a model that must not be called at all."""
    called: list[int] = []

    def turns(*args: object, **kwargs: object) -> list[str]:
        called.append(1)
        if replies is None:
            raise AssertionError("the model was called")
        return replies

    grading = types.ModuleType("eval_grading")
    grading.turns = turns  # type: ignore[attr-defined]
    client = types.ModuleType("anthropic")
    client.Anthropic = lambda: object()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "eval_grading", grading)
    monkeypatch.setitem(sys.modules, "anthropic", client)
    return called


def test_the_runner_prices_by_default_and_spends_only_when_told(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """qa on #1287: run bare, the runner calls nothing."""
    runner = _runner(monkeypatch)
    ledger = tmp_path / "ledger.jsonl"
    called = _no_model(monkeypatch, None)
    runner.main(["--ledger", str(ledger)])
    runner.main(["--dry-run", "--ledger", str(ledger)])
    assert not called and not ledger.exists()
    assert "Nothing was called. --spend runs it." in capsys.readouterr().out
    with pytest.raises(SystemExit):
        runner.main(["--spend", "--dry-run", "--ledger", str(ledger)])

    cases = rubric.load()
    called = _no_model(monkeypatch, [reply(one.sent) for one in cases])
    runner.main(["--spend", "--ledger", str(ledger)])
    assert called
    rows = evals.read(ledger)
    assert {row.metric for row in rows} == set(rubric.summarise([]).scores)
    assert all(row.corpus == "fr-cases" and row.version == CHAT_MODEL for row in rows)
    assert all(row.system == SYSTEM for row in rows)
    gold = evals.fingerprint([stages.CHAT_EVAL_CASES["fr"]])
    assert all(row.note.endswith(f"gold={gold}") for row in rows)


#: The French contract's text at each version, as the first 16 hex of a sha256, for each
#: language it glosses into (qa on #1299). A run is filed under the version it ran
#: (`chat-contract/fr<n>`), so the version has to change whenever the words do.
CONTRACT_PINS: dict[int, dict[str, str]] = {
    2: {"English": "ea6ae88e7029d052", "Russian": "92d84dec08d249fa"},
}


@pytest.mark.parametrize("gloss", ["English", "Russian"])
def test_the_french_contract_is_the_text_its_version_names(gloss: str) -> None:
    import hashlib

    version = hebrew.FRENCH_CONTRACT_VERSION
    said = hashlib.sha256(hebrew.french_contract(gloss).encode("utf-8")).hexdigest()[:16]
    assert version in CONTRACT_PINS, f"pin version {version}'s text here"
    assert said == CONTRACT_PINS[version][gloss], (
        f"The French contract's words changed and its version did not. Move "
        f"hebrew.FRENCH_CONTRACT_VERSION past {version} and pin the new text here "
        f"({gloss}: {said}): an eval run is filed under the version it ran."
    )
