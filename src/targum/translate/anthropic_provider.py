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
from ..usage import Usage
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

# Cost model, measured Aug 23 2026 against the Hebrew fixtures with the token-counting
# endpoint. Redo these if the prompt, the batch size or the context span changes.

# The system prompt and the structured-output scaffolding ride on every request and do
# not grow with the document. This is a fixed cost per batch, not a share of the text:
# treating it as a percentage made the estimate grow with the square of the length.
TOKENS_PER_BATCH = 428

# Each batch also re-sends the sentences on either side of it as context, so that share
# of the body is paid for twice. Two segments each way; see context_window().
CONTEXT_SEGMENTS_PER_BATCH = 4

# Hebrew runs 57% of the English word count for the same content but nearly the same
# token count, so a translation comes back at about the size that went in. Thinking is
# billed inside output_tokens and measures at 15% or less, so it needs no separate term.
OUTPUT_RATIO = 1.0

# Characters per token, for when the counting endpoint cannot be reached. Only Hebrew
# and English are measured. The default is a Latin-script guess and reads low on any
# script that is not one: Hebrew is 1.45, not the 2.5 an English-shaped guess gives.
CHARS_PER_TOKEN = {"he": 1.45, "en": 2.73}
DEFAULT_CHARS_PER_TOKEN = 2.5


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
        # What this provider has actually spent, as opposed to what it estimated.
        # Accumulated across every call a run makes, read once at the end.
        self.spent = Usage()

    # -- setup ------------------------------------------------------------------

    def client(self) -> Any:
        if self._client is None:
            import anthropic

            try:
                self._client = anthropic.Anthropic()
            except Exception as exc:
                raise ProviderError(
                    "No Anthropic API key found.",
                    "Get one at console.anthropic.com, then: export ANTHROPIC_API_KEY=...",
                ) from exc
        return self._client

    def available(self) -> tuple[bool, str]:
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            return True, self.model
        return False, "set ANTHROPIC_API_KEY (a key comes from console.anthropic.com)"

    # -- cost -------------------------------------------------------------------

    def estimate(self, segments: list[Segment], source: str, target: str, style: Style) -> float:
        """Rough USD for a run, before a cent of it is spent.

        Shaped the way the requests actually are: the body once, the sentences either
        side of each batch a second time as context, and a fixed overhead on every call.
        The overhead is counted per batch, so a longer text pays more of it, but the
        estimate stays linear in the length rather than growing with its square.
        """
        if not segments:
            return 0.0
        body = "\n".join(segment.text for segment in segments)
        try:
            counted = self.client().messages.count_tokens(
                model=self.model,
                messages=[{"role": "user", "content": body}],
            )
            body_tokens = float(counted.input_tokens)
        except Exception:
            # Offline, or no key yet.
            language = source.split("-")[0].lower()
            body_tokens = len(body) / CHARS_PER_TOKEN.get(language, DEFAULT_CHARS_PER_TOKEN)
        batch_count = len(list(batches(segments, self.batch_size)))
        context_share = CONTEXT_SEGMENTS_PER_BATCH / self.batch_size
        input_tokens = body_tokens * (1.0 + context_share) + TOKENS_PER_BATCH * batch_count
        output_tokens = body_tokens * OUTPUT_RATIO
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

    def _record(self, response: Any) -> None:
        """Add one response's tokens to the running total, if it reported any."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self.spent.add(
            self.model,
            int(getattr(usage, "input_tokens", 0) or 0),
            int(getattr(usage, "output_tokens", 0) or 0),
        )

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
                "The Anthropic API rejected the key.",
                "Check ANTHROPIC_API_KEY, or get a new one at console.anthropic.com",
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

        # Recorded before anything can go wrong with the answer: a batch that comes
        # back refused or unparseable was still charged for.
        self._record(response)

        if response.stop_reason == "refusal":
            raise ProviderError(
                "The model declined to translate a passage.",
                "Rerun to try it again on its own; finished work is cached.",
            )
        parsed: Any = response.parsed_output
        if not isinstance(parsed, _Batch):
            raise ProviderError("The model returned no structured output for a batch.")
        return parsed
