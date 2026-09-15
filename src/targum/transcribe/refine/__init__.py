"""Turning a raw transcript into something a reader can read."""

from __future__ import annotations

from .base import Refiner
from .null import NullRefiner
from .punctuate import Punctuator
from .rules import RuleRefiner

__all__ = ["NullRefiner", "Punctuator", "Refiner", "RuleRefiner", "build"]


def build(name: str = "", *, punctuate: bool = True) -> Refiner:
    """The refiner to run, by name; the environment may promote the model-backed one.

    Rules are the default: local, and good enough to read once a sentence can be told
    from the next. That one thing is bought — a transcript heard without punctuation has
    it put back by the model (`punctuate.py`) — because a learner cannot read Hebrew
    that never stops. It is not a silent upgrade: every quote that prices a hearing
    prices the punctuation with it (`Punctuator.dollars_per_minute`), and the receipt
    counts its tokens. `punctuate=False` is a hearing nobody paid for — the test
    transcriber — which has nothing to put marks on.

    The model-backed refiner, which rewrites rather than punctuates, is opted into per box
    (`TARGUM_REFINER=anthropic`) until it has earned the default.
    """
    import os

    chosen = name or os.environ.get("TARGUM_REFINER", "")
    punctuator = Punctuator() if punctuate else None
    if punctuator is not None and not punctuator.available()[0]:
        punctuator = None
    if chosen in ("anthropic", "anthropic-refine/1"):
        from .anthropic import AnthropicRefiner

        candidate = AnthropicRefiner()
        if candidate.available()[0]:
            return candidate
        return RuleRefiner(punctuator)
    if chosen in ("", "rules") or chosen.startswith("rules/"):
        return RuleRefiner(punctuator)
    return NullRefiner()
