"""The free half of `scripts/eval_hebrew_stress.py` (targum-internal#325): the gold read
off an accent written before a holam male, the binyan and mishkal rule, and the pausal
share. Words are built by hand, so nothing here needs OSHB on disk or a key."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eval_hebrew_stress.py"


@pytest.fixture(scope="module")
def module() -> Any:
    spec = importlib.util.spec_from_file_location("eval_hebrew_stress", SCRIPT)
    assert spec and spec.loader
    loaded = importlib.util.module_from_spec(spec)
    # Registered before it runs: a dataclass looks its own module up by name.
    sys.modules["eval_hebrew_stress"] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def item(module: Any, word: str, gold: int, accent: str = "", code: str = "", suffix: str = ""):
    parts = module.syllables(word)
    assert parts is not None, word
    return module.Item("Gen.1.1", word, word, tuple(parts), gold, accent, code, suffix)


def test_an_accent_before_a_holam_male_stresses_the_holam(module: Any) -> None:
    """The codex writes the accent of הָמוֹן on the mem; the stress is the holam's."""
    assert module.gold_syllable("הָמ֖וֹן") == 1
    assert module.gold_syllable("גָּד֥וֹל") == 1


def test_an_accent_on_its_own_vowel_reads_as_before(module: Any) -> None:
    assert module.gold_syllable("בָּאָ֑רֶץ") == 1
    assert module.gold_syllable("דָּבָ֑ר") == 1
    assert module.gold_syllable("וַיֹּ֥אמֶר") == 1


@pytest.mark.parametrize(
    ("word", "code", "suffix", "reason"),
    [
        ("מֶלֶךְ", "Ncmsa", "", "segolate"),
        ("נַעַר", "Ncmsa", "", "segolate with a guttural"),
        ("הַמַּיִם", "Ncmpa", "", "-ַיִם, -ַיִת"),
        ("מִזְבֵּחַ", "Ncmsa", "", "furtive patah"),
        ("דְּבָרֶךָ", "Ncmsc", "Sp2ms", "-ךָ after a vowel"),
        ("פָּנֶיהָ", "Ncbpc", "Sp3fs", "-הָ suffix"),
        ("שָׁמַרְתִּי", "Vqp1cs", "", "perfect 1cs/2ms"),
    ],
)
def test_the_rule_keeps_the_stress_back_where_the_grammar_does(
    module: Any, word: str, code: str, suffix: str, reason: str
) -> None:
    got = item(module, word, 0, code=code, suffix=suffix)
    assert module.mil_el(got) == reason
    assert module.by_rule(got) == len(got.syllables) - 2


@pytest.mark.parametrize(
    ("word", "code", "suffix"),
    [
        ("דָּבָר", "Ncmsa", ""),
        ("אַרְצְךָ", "Ncbsc", "Sp2ms"),  # -ְךָ after a shva is stressed on the suffix
        ("דִּבֶּר", "Vpp3ms", ""),  # the piel's doubled letter is not a segolate's
        ("אֲשֶׁר", "Tr", ""),  # a hataf before the segol
        ("לָהֶם", "R", "Sp3mp"),  # the plural suffix takes the stress
        ("וְשָׁמַרְתִּי", "Vqq1cs", ""),  # the sequential perfect moves it forward
    ],
)
def test_the_rule_leaves_the_last_syllable_elsewhere(
    module: Any, word: str, code: str, suffix: str
) -> None:
    got = item(module, word, 0, code=code, suffix=suffix)
    assert module.mil_el(got) is None
    assert module.by_rule(got) == len(got.syllables) - 1


def test_the_vowels_only_rule_reads_no_tagging(module: Any) -> None:
    """The perfect ending needs the tagging; the segolate does not."""
    perfect = item(module, "שָׁמַרְתִּי", 1, code="Vqp1cs")
    assert module.mil_el(perfect, morphology=False) is None
    assert module.mil_el(item(module, "מֶלֶךְ", 0), morphology=False) == "segolate"


def test_measure_counts_the_pausal_words_and_scores_without_them(module: Any) -> None:
    words = [
        item(module, "מֶלֶךְ", 0, accent="etnachta", code="Ncmsa"),  # rule right, default wrong
        item(module, "דָּבָר", 1, accent="zakef-katan", code="Ncmsa"),  # both right
        item(module, "דָּבָר", 1, accent="tipcha", code="Ncmsa"),  # both right
        item(module, "מֶלֶךְ", 1, accent="munach", code="Ncmsa"),  # the rule misses it
    ]
    got = module.measure(words)
    assert got["pausal_share"] == (0.25, 4)
    assert got["pausal_share_with_kings"] == (0.5, 4)
    assert got["default_accuracy"] == (0.75, 4)
    assert got["default_accuracy_nonpausal"] == (1.0, 3)
    assert got["default_accuracy_nonpausal_kings"] == (1.0, 2)
    assert got["rule_accuracy"] == (0.75, 4)
    assert got["rule_accuracy_nonpausal"] == (0.6667, 3)
    assert set(got) == set(module.FREE), "every free number names its system in FREE"
