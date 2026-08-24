"""Glosses: the dictionary form of a word and what it means here.

Generated once per lemma and cached across every text you process, because a text has
far fewer distinct lemmas than tokens and the second book in a language costs a
fraction of the first. The cache is keyed on the lemma and the language pair, not on
the document, so it is shared.

In-context definitions beat a wall of unranked senses, and coverage does not depend on
a dump existing for the language. The provider stays behind the same interface as
translation, so Wiktionary through Wiktextract can slot in beside it later.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel

from ..cache import Cache
from ..errors import ProviderError
from ..models import Annotation, Glossary
from ..translate.prompts import language_name

BATCH_SIZE = 40
# Glosses are short, so a batch is cheap. Rough tokens per lemma, in and out, for the
# estimate shown before anything is spent.
TOKENS_PER_LEMMA_IN = 12
TOKENS_PER_LEMMA_OUT = 24

Progress = Callable[[int], None]


class _Entry(BaseModel):
    lemma: str
    gloss: str
    part_of_speech: str = ""


class _Batch(BaseModel):
    entries: list[_Entry]


class GlossProvider(Protocol):
    @property
    def name(self) -> str: ...

    def gloss(
        self,
        lemmas: list[str],
        source_language: str,
        target_language: str,
        on_progress: Progress | None = None,
    ) -> dict[str, tuple[str, str]]: ...


SYSTEM = """You are writing a learner's glossary for {source} read by a {target} speaker.

For each {source} dictionary form you are given, return one short {target} gloss.

- The dictionary form is given as it would appear in a dictionary. Gloss that form.
- Two to six words. The most common sense first, and only add a second sense when the
  word is genuinely ambiguous, separated by a semicolon.
- No transliteration, no grammatical explanation, no example sentences.
- Give the part of speech as one of: noun, verb, adjective, adverb, preposition,
  pronoun, conjunction, particle, other.
- If a form is not a word of {source}, return it with an empty gloss rather than
  guessing."""


class AnthropicGlosses:
    """Glosses from the same provider that does translation."""

    def __init__(self, model: str | None = None, *, batch_size: int = BATCH_SIZE) -> None:
        from ..translate.anthropic_provider import DEFAULT_MODEL, AnthropicProvider

        self._provider = AnthropicProvider(model or DEFAULT_MODEL)
        self.model = self._provider.model
        self.batch_size = batch_size

    @property
    def name(self) -> str:
        return f"anthropic/{self.model}"

    def available(self) -> tuple[bool, str]:
        return self._provider.available()

    def gloss(
        self,
        lemmas: list[str],
        source_language: str,
        target_language: str,
        on_progress: Progress | None = None,
    ) -> dict[str, tuple[str, str]]:
        import anthropic

        system = SYSTEM.format(
            source=language_name(source_language), target=language_name(target_language)
        )
        out: dict[str, tuple[str, str]] = {}
        for start in range(0, len(lemmas), self.batch_size):
            batch = lemmas[start : start + self.batch_size]
            try:
                response = self._provider.client().messages.parse(
                    model=self.model,
                    max_tokens=8000,
                    system=system,
                    messages=[{"role": "user", "content": "\n".join(batch)}],
                    output_config={"effort": "low"},
                    output_format=_Batch,
                )
            except anthropic.APIStatusError as exc:
                raise ProviderError(
                    f"Anthropic API error {exc.status_code} while glossing.", exc.message
                ) from exc
            # Word meanings are a real share of a build — measured, about half of it
            # before glossing became on-demand — so they are counted like everything
            # else rather than treated as incidental.
            self._provider.spent.add(
                self.model or "",
                int(getattr(response.usage, "input_tokens", 0) or 0),
                int(getattr(response.usage, "output_tokens", 0) or 0),
            )
            parsed: Any = response.parsed_output
            if isinstance(parsed, _Batch):
                wanted = set(batch)
                for entry in parsed.entries:
                    if entry.lemma in wanted and entry.gloss.strip():
                        out[entry.lemma] = (entry.gloss.strip(), entry.part_of_speech.strip())
            if on_progress:
                on_progress(len(batch))
        return out


def unique_lemmas(annotation: Annotation, *, min_band: int = 1) -> list[str]:
    """Every distinct lemma worth glossing, rarest-first so a cut list keeps the useful end."""
    best: dict[str, int] = {}
    for tokens in annotation.tokens.values():
        for token in tokens:
            # An unrated word is still a word worth looking up.
            if token.band >= min_band or (token.band == 0 and min_band <= 1):
                best[token.lemma] = max(best.get(token.lemma, 0), token.band)
    return [lemma for lemma, _ in sorted(best.items(), key=lambda item: (-item[1], item[0]))]


def estimate(lemma_count: int, model: str) -> float:
    from ..translate.anthropic_provider import DEFAULT_MODEL, PRICES

    in_price, out_price = PRICES.get(model, PRICES[DEFAULT_MODEL])
    return (
        lemma_count * TOKENS_PER_LEMMA_IN * in_price
        + lemma_count * TOKENS_PER_LEMMA_OUT * out_price
    ) / 1_000_000


def gloss_one(
    lemma: str,
    source_language: str,
    target_language: str,
    provider: GlossProvider,
    *,
    cache: Cache | None = None,
) -> str:
    """One word, looked up because someone asked for it.

    The whole-text pass is the expensive half of a build and most of what it buys is
    never read: you look up the handful of words you actually stumble on. This is that
    handful, one at a time, through the same cache — so a word looked up while reading
    one article is free in the next.
    """
    cache = cache or Cache()
    key = cache.key(
        "gloss",
        lemma=lemma,
        source=source_language,
        target=target_language,
        provider=provider.name,
    )
    stored = cache.get("gloss", key)
    if isinstance(stored, dict) and stored.get("gloss"):
        return str(stored["gloss"])

    fresh = provider.gloss([lemma], source_language, target_language, None)
    found = fresh.get(lemma)
    if not found:
        return ""
    cache.put("gloss", key, {"gloss": found[0], "part_of_speech": found[1]})
    return found[0]


def build_glossary(
    annotation: Annotation,
    target_language: str,
    provider: GlossProvider,
    *,
    min_band: int = 1,
    cache: Cache | None = None,
    on_progress: Progress | None = None,
    on_batch: Callable[[Glossary], None] | None = None,
) -> tuple[Glossary, int]:
    """Returns the glossary and how many lemmas had to be paid for.

    `on_batch` is handed the glossary so far after every batch that is paid for. The
    reader opens before any of this has run and polls for the file, so writing it once
    at the end meant every word showed a blank card for as long as the whole run took.
    """
    cache = cache or Cache()
    wanted = unique_lemmas(annotation, min_band=min_band)

    entries: dict[str, str] = {}
    parts: dict[str, str] = {}
    missing: list[str] = []
    for lemma in wanted:
        key = cache.key(
            "gloss",
            lemma=lemma,
            source=annotation.language,
            target=target_language,
            provider=provider.name,
        )
        stored = cache.get("gloss", key)
        if isinstance(stored, dict) and stored.get("gloss"):
            entries[lemma] = str(stored["gloss"])
            parts[lemma] = str(stored.get("part_of_speech", ""))
        else:
            missing.append(lemma)

    def assembled() -> Glossary:
        return Glossary(
            source_language=annotation.language,
            target_language=target_language,
            provider=provider.name,
            entries=dict(entries),
            parts_of_speech=dict(parts),
        )

    # Handed over a batch at a time rather than all at once, so a partial glossary can
    # be published while the rest is still being looked up. The provider batches
    # internally too; asking for one batch at a time makes each call one request.
    size = max(1, int(getattr(provider, "batch_size", 0)) or len(missing) or 1)
    for start in range(0, len(missing), size):
        chunk = missing[start : start + size]
        fresh = provider.gloss(chunk, annotation.language, target_language, on_progress)
        for lemma, (gloss, part) in fresh.items():
            entries[lemma] = gloss
            parts[lemma] = part
            cache.put(
                "gloss",
                cache.key(
                    "gloss",
                    lemma=lemma,
                    source=annotation.language,
                    target=target_language,
                    provider=provider.name,
                ),
                {"gloss": gloss, "part_of_speech": part},
            )
        if on_batch:
            on_batch(assembled())

    return assembled(), len(missing)
