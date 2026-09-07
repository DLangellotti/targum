"""`scripts/measure_glue.py` counts what a space-fixer could have something to say about.

The script is loaded by path because `scripts/` is not a package. Nothing here loads a
model: the population and the bar are plain functions, and the model behind `--spacefix`
is imported only inside the function that runs it, which no test calls.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture(scope="module")
def script() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "measure_glue.py"
    spec = importlib.util.spec_from_file_location("measure_glue", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_loading_the_script_loads_no_model(script: ModuleType) -> None:
    for name in ("torch", "transformers", "huggingface_hub"):
        assert not hasattr(script, name)


def test_population_is_what_unglue_sees_as_one_token(script: ModuleType) -> None:
    """A maqaf compound is two words to the tokenizer already, and a surface with a
    space inside was never one token. Neither is glue, whatever the lexicon makes of
    the letters, and the first count had 270 of them."""
    found = script.population(
        [
            # Two names run together, unknown as one, known as either half: the shape
            # the issue is about.
            "סוקולובספר",
            # Already two words.
            "אִישׁ־אֱלֹהִ֖ים",
            "עֲבֹ֛ר אֶחָ֥ד",
            # A word the lexicon knows is left alone whatever it could be split into.
            "המלחמה",
            # Too short to hold two words.
            "שלום",
        ]
    )
    assert list(found) == ["סוקולובספר"]
    # Sokolov and ספר, and every other place two known halves meet: the seams are the
    # candidates, and choosing among them is the model's job, not this count's.
    assert 7 in found["סוקולובספר"]


@pytest.mark.parametrize(
    ("cuts", "expected"),
    [
        (None, ("no-context", None)),
        ([], ("no-proposal", None)),
        ([3, 6], ("many", [3, 6])),
        ([6], ("accept", 6)),
        ([4], ("off-seam", 4)),
    ],
)
def test_the_bar_accepts_one_proposal_at_a_seam_and_nothing_else(
    script: ModuleType, cuts: list[int] | None, expected: tuple[str, object]
) -> None:
    assert script.verdict(cuts, [6]) == expected
