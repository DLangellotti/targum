"""Turning a raw transcript into something a reader can read."""

from __future__ import annotations

from .base import Refiner
from .null import NullRefiner
from .rules import RuleRefiner

__all__ = ["NullRefiner", "Refiner", "RuleRefiner", "build"]


def build(name: str = "") -> Refiner:
    """The refiner to run, by name; the environment may promote the model-backed one.

    Rules are the default: free, local, and good enough to read. The model-backed
    refiner is opted into per box (`TARGUM_REFINER=anthropic`) until it has earned the
    default — a stage that spends money is never a silent upgrade.
    """
    import os

    chosen = name or os.environ.get("TARGUM_REFINER", "")
    if chosen in ("anthropic", "anthropic-refine/1"):
        from .anthropic import AnthropicRefiner

        candidate = AnthropicRefiner()
        if candidate.available()[0]:
            return candidate
        return RuleRefiner()
    if chosen in ("", "rules", RuleRefiner.name):
        return RuleRefiner()
    return NullRefiner()
