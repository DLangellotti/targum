"""Translation through the Anthropic API.

Output is requested segment by segment and keyed by segment ID, so alignment holds by
construction rather than by counting lines. Any ID that does not come back is retried
on its own; the batch around it is not paid for twice.
"""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel

from ..errors import ProviderError
from ..models import Segment, Style
from .base import Progress, batches, context_window
from .prompts import language_name, system_prompt

DEFAULT_MODEL = "claude-opus-5"

# USD per million tokens, input and output. Used only for the estimate shown before a run.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

MAX_ATTEMPTS = 3


class _Blocked(Exception):
    """A batch the safety filter refused, which a smaller batch often survives."""


class _Line(BaseModel):
    id: str
    text: str


class _Batch(BaseModel):
    segments: list[_Line]


class AnthropicProvider:
    name = "anthropic"
    needs_key = True
    default_model = DEFAULT_MODEL

    def __init__(
        self,
        model: str | None = None,
        *,
        batch_size: int = 20,
        effort: str = "medium",
    ) -> None:
        self.model = model or DEFAULT_MODEL
        self.batch_size = max(1, batch_size)
        self.effort = effort
        self._client: Any = None

    # -- setup ------------------------------------------------------------------

    def client(self) -> Any:
        if self._client is None:
            import anthropic

            try:
                self._client = anthropic.Anthropic()
            except Exception as exc:
                raise ProviderError(
                    "Could not start the Anthropic client.",
                    "export ANTHROPIC_API_KEY=...",
                ) from exc
        return self._client

    def available(self) -> tuple[bool, str]:
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            return True, self.model
        return False, "set ANTHROPIC_API_KEY"

    # -- cost -------------------------------------------------------------------

    def estimate(self, segments: list[Segment], source: str, target: str, style: Style) -> float:
        """Rough USD for a run. Excludes thinking tokens, so it reads low on hard texts."""
        body = "\n".join(segment.text for segment in segments)
        try:
            counted = self.client().messages.count_tokens(
                model=self.model,
                system=system_prompt(source, target, style),
                messages=[{"role": "user", "content": body}],
            )
            input_tokens = float(counted.input_tokens)
        except Exception:
            # Offline, or no key yet. Characters per token runs low on Hebrew and Russian.
            input_tokens = len(body) / 2.5
        # Context repeats across batches, and the system prompt rides on every call.
        input_tokens *= 1.0 + (len(list(batches(segments, self.batch_size))) * 0.15)
        output_tokens = input_tokens * 1.3
        in_price, out_price = PRICES.get(self.model, PRICES[DEFAULT_MODEL])
        return (input_tokens * in_price + output_tokens * out_price) / 1_000_000

    # -- translation ------------------------------------------------------------

    def translate(
        self,
        segments: list[Segment],
        source_language: str,
        target_language: str,
        style: Style,
        on_progress: Progress | None = None,
    ) -> dict[str, str]:
        system = system_prompt(source_language, target_language, style)
        out: dict[str, str] = {}

        for batch in batches(segments, self.batch_size):
            got = self._translate_batch(batch, segments, system, target_language)
            missing = [segment for segment in batch if segment.id not in got]
            for attempt in range(MAX_ATTEMPTS - 1):
                if not missing:
                    break
                # Retry the misses alone, not the batch that mostly worked.
                got |= self._translate_batch(
                    missing, segments, system, target_language, split=attempt > 0
                )
                missing = [segment for segment in missing if segment.id not in got]
            if missing:
                raise ProviderError(
                    f"{len(missing)} of {len(batch)} segments came back empty after "
                    f"{MAX_ATTEMPTS} attempts.",
                    f"First one: {missing[0].id}",
                )
            out |= got
            if on_progress:
                on_progress(len(batch))
        return out

    def _translate_batch(
        self,
        batch: list[Segment],
        all_segments: list[Segment],
        system: str,
        target_language: str,
        *,
        split: bool = False,
    ) -> dict[str, str]:
        if split and len(batch) > 1:
            # A batch that keeps dropping segments is usually one bad segment. Halve it.
            middle = len(batch) // 2
            return self._translate_batch(
                batch[:middle], all_segments, system, target_language
            ) | self._translate_batch(batch[middle:], all_segments, system, target_language)

        before, after = context_window(all_segments, batch)
        try:
            response = self._call(system, self._user_message(batch, before, after, target_language))
        except _Blocked as blocked:
            # The filter reads a whole batch at once, so it occasionally objects to a
            # combination no single sentence would trigger. Halve and try again.
            if len(batch) > 1:
                middle = len(batch) // 2
                return self._translate_batch(
                    batch[:middle], all_segments, system, target_language
                ) | self._translate_batch(batch[middle:], all_segments, system, target_language)
            raise ProviderError(
                f"The safety filter blocked segment {batch[0].id} on its own.",
                f"Text: {batch[0].text[:60]}",
            ) from blocked
        return {
            line.id: line.text.strip()
            for line in response.segments
            if line.text.strip() and any(line.id == segment.id for segment in batch)
        }

    @staticmethod
    def _user_message(batch: list[Segment], before: str, after: str, target_language: str) -> str:
        parts = []
        if before:
            parts.append(f"Context before (do not translate):\n{before}")
        parts.append(
            "Segments to translate into "
            f"{language_name(target_language)}:\n"
            + "\n".join(f"[{segment.id}] {segment.text}" for segment in batch)
        )
        if after:
            parts.append(f"Context after (do not translate):\n{after}")
        return "\n\n".join(parts)

    def _call(self, system: str, message: str) -> _Batch:
        import anthropic

        try:
            response = self.client().messages.parse(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": message}],
                output_config={"effort": self.effort},
                output_format=_Batch,
            )
        except anthropic.AuthenticationError as exc:
            raise ProviderError(
                "The Anthropic API rejected the key.", "Check ANTHROPIC_API_KEY"
            ) from exc
        except anthropic.NotFoundError as exc:
            raise ProviderError(f"No such model: {self.model}", str(exc)) from exc
        except anthropic.RateLimitError as exc:
            raise ProviderError(
                "Rate limited by the Anthropic API.", "Wait and rerun; finished work is cached."
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("Could not reach the Anthropic API.", str(exc)) from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code == 400 and "content filtering" in (exc.message or ""):
                raise _Blocked(exc.message) from exc
            raise ProviderError(f"Anthropic API error {exc.status_code}.", exc.message) from exc

        if response.stop_reason == "refusal":
            raise ProviderError(
                "The model declined to translate a passage.",
                "Rerun with a smaller --batch-size to isolate it.",
            )
        parsed: Any = response.parsed_output
        if not isinstance(parsed, _Batch):
            raise ProviderError("The model returned no structured output for a batch.")
        return parsed
