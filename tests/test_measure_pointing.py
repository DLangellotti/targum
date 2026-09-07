"""`scripts/measure_pointing.py` scores a pointing the way the reader would see it.

The script is loaded by path because `scripts/` is not a package. No model is loaded:
these are the scoring function on hand-written pairs, so that the numbers the script
appends to the ledger mean what its docstring says they mean (targum-internal#148).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture(scope="module")
def script() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "measure_pointing.py"
    spec = importlib.util.spec_from_file_location("measure_pointing", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before it runs: a dataclass resolves its own module through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


#: One corpus line as the file writes it: a mater in angle brackets, a qamats qatan on
#: the het, a shin with its dot, a dagesh in the bet.
RAW = "דִּ<י>בֵּר עַל כׇּל שָׁלוֹם"


def test_the_bare_text_is_the_plene_spelling_with_nothing_on_it(script: ModuleType) -> None:
    (line,) = script.parse_dicta(f" ** !! ** $0001$ header ** !! **\n\n{RAW}\n")
    assert line.bare == "דיבר על כל שלום"
    assert line.gold == "דִּיבֵּר עַל כׇּל שָׁלוֹם", "only the brackets go; the mater stays bare"


def test_the_reference_pointing_scores_one_everywhere(script: ModuleType) -> None:
    (line,) = script.parse_dicta(RAW)
    tally = script.Tally()
    script.score(line, line.gold, tally)
    rates = tally.rates()
    assert rates["skeleton_kept"] == (1.0, 1)
    assert rates["letter_vowel"] == (1.0, 12)
    assert rates["letter_dagesh"] == (1.0, 12)
    assert rates["shin_dot"] == (1.0, 1)
    assert rates["qamats_qatan_recall"] == (1.0, 1)
    assert rates["qamats_qatan_precision"] == (1.0, 1)
    assert rates["word_exact"] == (1.0, 4)
    assert tally.stress_emitted == 0


def test_mark_order_does_not_matter(script: ModuleType) -> None:
    """The reference writes dagesh before the vowel; a model may write the vowel first."""
    (line,) = script.parse_dicta(RAW)
    reversed_marks = "".join(
        base + "".join(chr(mark) for mark in sorted(marks, reverse=True))
        for base, marks in script.units(line.gold)
    )
    assert reversed_marks != line.gold, "the pair must actually differ in order"
    tally = script.Tally()
    script.score(line, reversed_marks, tally)
    assert tally.rates()["word_exact"] == (1.0, 4)


def test_one_wrong_vowel_costs_a_letter_and_a_word(script: ModuleType) -> None:
    (line,) = script.parse_dicta(RAW)
    tally = script.Tally()
    # Segol where the reference has tsere, and nothing else touched.
    script.score(line, line.gold.replace("בֵּ", "בֶּ"), tally, keep=3)
    rates = tally.rates()
    assert rates["letter_vowel"] == (11 / 12, 12)
    assert rates["letter_dagesh"] == (1.0, 12)
    assert rates["word_exact"] == (3 / 4, 4)
    assert tally.misses == [("דִּיבֵּר", "דִּיבֶּר")]


def test_a_qamats_where_the_reference_has_a_qatan_is_right_only_folded(
    script: ModuleType,
) -> None:
    """Nakdimon never emits U+05C7. Strictly that is a wrong vowel; folded it is not, and
    both numbers are kept so the difference is visible rather than argued about."""
    (line,) = script.parse_dicta(RAW)
    tally = script.Tally()
    script.score(line, line.gold.replace("ׇ", "ָ"), tally)
    rates = tally.rates()
    assert rates["letter_vowel"] == (11 / 12, 12)
    assert rates["letter_vowel_folded"] == (1.0, 12)
    assert rates["qamats_qatan_recall"] == (0.0, 1)
    assert rates["qamats_qatan_precision"] == (None, 0), "nothing emitted is not a score"


def test_a_dropped_mater_fails_the_skeleton_and_scores_nothing_else(
    script: ModuleType,
) -> None:
    """The gate in the issue: a model that deletes a letter is out, and a line whose
    letters changed cannot be aligned, so it adds nothing to the letter counts."""
    (line,) = script.parse_dicta(RAW)
    tally = script.Tally()
    script.score(line, line.gold.replace("דִּי", "דִּ"), tally, keep=1)
    rates = tally.rates()
    assert rates["skeleton_kept"] == (0.0, 1)
    assert tally.failed == 1
    assert tally.broken == [("דיבר על כל שלום", "דבר על כל שלום")]
    assert rates["letter_vowel"] == (None, 0)
    assert rates["word_exact"] == (None, 0)


def test_no_output_at_all_fails_the_line(script: ModuleType) -> None:
    (line,) = script.parse_dicta(RAW)
    tally = script.Tally()
    script.score(line, None, tally)
    assert tally.failed == 1 and tally.skeleton_kept == 0


def test_a_cheap_run_is_spread_across_the_file(script: ModuleType) -> None:
    lines = [script.Line(str(i), str(i)) for i in range(10)]
    assert [line.bare for line in script.spread(lines, 4)] == ["0", "2", "5", "7"]
    assert script.spread(lines, 0) == lines


def test_a_ben_yehuda_work_is_its_pointed_paragraphs_in_lines(script: ModuleType) -> None:
    """The title goes, the credit block goes, a bare paragraph breaks the run rather
    than joining it, and short runs are kept only when they hold a few words."""
    verse = "כָּאן עַל פְּנֵי הָאֲדָמָה לֹא בָּעָבִים מֵעַל"
    work = "\n".join(
        [
            "כָּאן עַל פְּנֵי הָאֲדָמָה",
            "",
            "בתוך: מכתבים ופנקסים",
            *([verse] * 3),
            "לא מנוקד",
            verse,
            "",
            "את הטקסט[ים] לעיל הפיקו מתנדבי פרויקט בן־יהודה באינטרנט.",
            verse,
        ]
    )
    lines = script.parse_ben_yehuda(work)
    assert len(lines) == 2
    assert script.hebrew_words(lines[0].gold) >= script.CHUNK_WORDS
    assert lines[0].gold.startswith(verse) and "בתוך" not in lines[0].gold
    assert lines[1].gold == verse, "the tail after the bare paragraph stands alone"
    assert lines[1].bare == "כאן על פני האדמה לא בעבים מעל"


def test_meteg_in_an_edition_is_not_held_against_a_model(script: ModuleType) -> None:
    (line,) = script.parse_dicta(RAW)
    tally = script.Tally()
    script.score(line._replace(gold=line.gold.replace("כׇּל", "כׇּֽל")), line.gold, tally)
    assert tally.rates()["word_exact"] == (1.0, 4)


def test_a_shin_the_reference_leaves_bare_is_not_scored(script: ModuleType) -> None:
    """Editions of the Ben-Yehuda period dot only the sin. A model that dots the shin
    there is not wrong, and the shin does not count towards the dot metric."""
    (line,) = script.parse_dicta(RAW)
    undotted = line._replace(gold=line.gold.replace("שָׁ", "שָ"))
    tally = script.Tally()
    script.score(undotted, line.gold, tally)
    assert tally.rates()["shin_dot"] == (None, 0)
    assert tally.rates()["word_exact"] == (1.0, 4)
