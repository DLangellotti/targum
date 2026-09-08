"""The half of the package that CI cannot see, checked wherever it exists.

Eight modules are gitignored and ship in the wheel — the weekly's writer and voice, the
dialogue writer, the recording cutter and aligner. CI has a public checkout, so `ruff`,
`mypy` and `pytest` there never see them; a `git worktree` of a tracked branch does not
carry ignored files either, and worktrees are where most work happens here. The main
checkout is the only place they exist (targum-internal#230).

That matters because they depend on the public half. A rename in `recording/`,
`weekly/index.py` or `models.py` breaks one of them while every check stays green, and
the failure surfaces at the next weekly build, by hand.

So: where a private module is present, it must import against the tree it is sitting in.
Where it is absent — CI, and every worktree — these skip, which is the same bargain
`needs_dicta_model` makes about a model on disk.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

#: What ships in the wheel and is not in the repository. Named here rather than
#: discovered, so that a private module quietly disappearing is a failing test rather
#: than one less thing checked.
PRIVATE = (
    "targum.dialogue.write",
    "targum.recording.attach",
    "targum.recording.cut",
    "targum.weekly.facts",
    "targum.weekly.prompts",
    "targum.weekly.sources",
    "targum.weekly.voice",
    "targum.weekly.write",
)


def path_of(module: str) -> Path:
    import targum

    root = Path(targum.__file__).parent
    return root.joinpath(*module.split(".")[1:]).with_suffix(".py")


@pytest.mark.parametrize("module", PRIVATE)
def test_a_private_module_imports_against_this_tree(module: str) -> None:
    """The check nothing else makes. An import is most of it: these fail on a renamed
    symbol at import time, which is the way the public half usually breaks them."""
    if not path_of(module).is_file():
        pytest.skip(f"{module} is not in this checkout, which is the ordinary state")
    importlib.import_module(module)


def test_the_private_half_is_all_or_nothing() -> None:
    """A checkout with some of them is a checkout somebody has half copied, and the
    weekly will fail on whichever one is missing rather than say so here."""
    present = [module for module in PRIVATE if path_of(module).is_file()]
    assert not present or len(present) == len(PRIVATE), (
        f"{len(present)} of {len(PRIVATE)} private modules are here: "
        f"missing {sorted(set(PRIVATE) - set(present))}"
    )
