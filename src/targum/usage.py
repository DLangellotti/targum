"""What a build actually cost, as opposed to what it was estimated at.

An estimate can refuse a build before it starts. It cannot tell anyone what a week of
reading cost, and it cannot be reconciled against a bill — which is the difference
between a spending limit and a guess with a limit written on it.

Every API response carries `usage`. Until now it was read past. This is where it
accumulates: providers add to a `Usage` as they go, the pipeline hands the total back
with the result, and the ledger settles the reservation it took up front against what
was really spent.

Prices live in the provider, because they are a property of the model rather than of
counting. A model nobody has priced counts tokens and costs nothing, which is honest:
an unknown price is not zero, but pretending to know it is worse.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Usage:
    """Tokens, by model, and what they came to."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    # Kept per model because one build can span two: translation on one, word meanings
    # on another, and a price that is an average of both is a price for neither.
    by_model: dict[str, tuple[int, int]] = field(default_factory=dict)

    def add(self, model: str, input_tokens: int, output_tokens: int) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        was_in, was_out = self.by_model.get(model, (0, 0))
        self.by_model[model] = (was_in + input_tokens, was_out + output_tokens)

    def __add__(self, other: Usage) -> Usage:
        total = Usage(
            calls=self.calls + other.calls,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            by_model=dict(self.by_model),
        )
        for model, (used_in, used_out) in other.by_model.items():
            was_in, was_out = total.by_model.get(model, (0, 0))
            total.by_model[model] = (was_in + used_in, was_out + used_out)
        return total

    def cost(self) -> float:
        """USD, from the prices the provider publishes for each model it used."""
        from .translate.anthropic_provider import PRICES

        total = 0.0
        for model, (used_in, used_out) in self.by_model.items():
            prices = PRICES.get(model)
            if prices is None:
                # Counted, not priced. Better than inventing a number for it.
                continue
            total += (used_in * prices[0] + used_out * prices[1]) / 1_000_000
        return total

    def state(self) -> dict[str, object]:
        return {
            "calls": self.calls,
            "input": self.input_tokens,
            "output": self.output_tokens,
            "cost": round(self.cost(), 4),
        }
