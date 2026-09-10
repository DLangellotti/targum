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
    # Transcription is bought by the minute, not the token, so it counts on its own
    # axis. Seconds rather than minutes: what a provider reports is a file's length,
    # and rounding here would round sixty times per audiobook.
    seconds_by_model: dict[str, float] = field(default_factory=dict)
    # And a web search the API ran for the chat is bought per search. Counted here so a
    # turn that searched three times settles for what it cost, not for its tokens alone.
    searches: int = 0
    # What the chat's prompt cache did (targum-internal#239): tokens read back from it,
    # which cost a tenth of the input price, and tokens written into it, which cost a
    # quarter more. Both were read past until 2026-09-10, so the receipt could not say
    # whether caching the prompt saved anything. Per model, like the tokens.
    cache_by_model: dict[str, tuple[int, int]] = field(default_factory=dict)

    #: What a cached token costs against a fresh one: read, and written.
    CACHE_READ = 0.1
    CACHE_WRITE = 1.25

    def add(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_read: int = 0,
        cache_write: int = 0,
    ) -> None:
        self.calls += 1
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        was_in, was_out = self.by_model.get(model, (0, 0))
        self.by_model[model] = (was_in + input_tokens, was_out + output_tokens)
        if cache_read or cache_write:
            read, wrote = self.cache_by_model.get(model, (0, 0))
            self.cache_by_model[model] = (read + cache_read, wrote + cache_write)

    @property
    def cache_read_tokens(self) -> int:
        return sum(read for read, _ in self.cache_by_model.values())

    @property
    def cache_write_tokens(self) -> int:
        return sum(wrote for _, wrote in self.cache_by_model.values())

    def add_seconds(self, model: str, seconds: float) -> None:
        self.calls += 1
        self.seconds_by_model[model] = self.seconds_by_model.get(model, 0.0) + seconds

    def add_search(self) -> None:
        self.searches += 1

    def __add__(self, other: Usage) -> Usage:
        total = Usage(
            calls=self.calls + other.calls,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            by_model=dict(self.by_model),
            seconds_by_model=dict(self.seconds_by_model),
            searches=self.searches + other.searches,
        )
        for model, (used_in, used_out) in other.by_model.items():
            was_in, was_out = total.by_model.get(model, (0, 0))
            total.by_model[model] = (was_in + used_in, was_out + used_out)
        for model, seconds in other.seconds_by_model.items():
            total.seconds_by_model[model] = total.seconds_by_model.get(model, 0.0) + seconds
        total.cache_by_model = dict(self.cache_by_model)
        for model, (read, wrote) in other.cache_by_model.items():
            was_read, was_wrote = total.cache_by_model.get(model, (0, 0))
            total.cache_by_model[model] = (was_read + read, was_wrote + wrote)
        return total

    def cost(self) -> float:
        """USD, from the prices the provider publishes for each model it used."""
        from .transcribe import PRICES as MINUTES
        from .translate.anthropic_provider import PRICES, SEARCH_PRICE

        total = 0.0
        for model, (used_in, used_out) in self.by_model.items():
            prices = PRICES.get(model)
            if prices is None:
                # Counted, not priced. Better than inventing a number for it.
                continue
            total += (used_in * prices[0] + used_out * prices[1]) / 1_000_000
        for model, (read, wrote) in self.cache_by_model.items():
            prices = PRICES.get(model)
            if prices is None:
                continue
            total += (
                read * prices[0] * self.CACHE_READ + wrote * prices[0] * self.CACHE_WRITE
            ) / 1_000_000
        for model, seconds in self.seconds_by_model.items():
            rate = MINUTES.get(model)
            if rate is None:
                # Counted, not priced, for the reason above.
                continue
            total += seconds / 60 * rate
        total += self.searches * SEARCH_PRICE
        return total

    def state(self) -> dict[str, object]:
        state: dict[str, object] = {
            "calls": self.calls,
            "input": self.input_tokens,
            "output": self.output_tokens,
            "cost": round(self.cost(), 4),
        }
        if self.seconds_by_model:
            state["seconds"] = round(sum(self.seconds_by_model.values()), 1)
        if self.searches:
            state["searches"] = self.searches
        if self.cache_by_model:
            state["cache_read"] = self.cache_read_tokens
            state["cache_write"] = self.cache_write_tokens
        return state
