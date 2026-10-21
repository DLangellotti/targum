"""`scripts/eval_stress_tagger.py` (targum-internal#325): DICTA's morphology written in
OSHB's code shape, the small tagger's facts and back, and the alignment of DICTA's tokens
with a verse's words. Built by hand, so nothing here needs OSHB, DICTA or scikit-learn."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eval_stress_tagger.py"


@pytest.fixture(scope="module")
def module() -> Any:
    spec = importlib.util.spec_from_file_location("eval_stress_tagger", SCRIPT)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    sys.modules["eval_stress_tagger"] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def token(pos: str, feats: dict[str, str], prefixes: list[str] | None = None, **more: Any):
    return {"morph": {"pos": pos, "feats": feats, "prefixes": prefixes or [], **more}}


def test_a_past_first_person_is_common_whatever_gender_dicta_guessed(module: Any) -> None:
    said = token("VERB", {"Gender": "Fem", "Number": "Sing", "Person": "1", "Tense": "Past"})
    assert module.code_of(said) == ("Vxp1cs", "")


def test_the_rule_reads_dictas_perfect_second_person(module: Any) -> None:
    stress = module.stress
    word = "שָׁמַרְתָּ"
    parts = stress.syllables(word)
    said = token("VERB", {"Gender": "Masc", "Number": "Sing", "Person": "2", "Tense": "Past"})
    code, suffix = module.code_of(said)
    item = stress.Item("Gen.1.1", word, word, tuple(parts), 0, "", code, suffix)
    assert stress.mil_el(item) == "perfect 1cs/2ms"


def test_a_perfect_behind_a_vav_is_sequential_only_when_asked(module: Any) -> None:
    said = token(
        "VERB",
        {"Gender": "Masc", "Number": "Sing", "Person": "2", "Tense": "Past"},
        ["CCONJ"],
    )
    assert module.code_of(said)[0] == "Vxp2ms"
    assert module.code_of(said, sequential=True)[0] == "Vxq2ms"


def test_a_pronoun_suffix_is_written_as_oshbs(module: Any) -> None:
    said = token(
        "NOUN",
        {"Gender": "Fem", "Number": "Plur"},
        suffix="PRON",
        suffix_feats={"Gender": "Masc", "Number": "Plur", "Person": "2"},
    )
    assert module.code_of(said) == ("Nxfpa", "Sp2mp")


def test_facts_go_back_into_the_code_the_rule_reads(module: Any) -> None:
    facts = module.facts_of("Vqp2ms", "")
    assert facts == {"pos": "V", "tense": "p", "png": "2ms", "suffix": "-"}
    assert module.code_from(facts) == ("Vxp2ms", "")
    assert module.code_from(module.facts_of("Ncmsa", "Sd")) == ("N", "Sd")
    assert module.code_from(module.facts_of("Ncmpc", "Sp2mp")) == ("N", "Sp2mp")


def test_tokens_line_up_with_words_and_only_a_mismatch_is_untagged(module: Any) -> None:
    words = ["בראשית", "ברא", "אלהים"]
    tokens = [
        {"token": "בראשית", "morph": {"pos": "NOUN"}},
        {"token": ",", "morph": {"pos": "PUNCT"}},
        {"token": "בר", "morph": {"pos": "VERB"}},
        {"token": "אלהים", "morph": {"pos": "NOUN"}},
    ]
    aligned = module._aligned(words, tokens)
    assert [bool(t) for t in aligned] == [True, False, True]


def test_the_letters_dicta_reads_drop_the_points_and_the_maqaf(module: Any) -> None:
    assert module.bare("כָּל־") == "כל"
