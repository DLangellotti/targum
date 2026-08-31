"""What a run of words means, in a sentence whose translation is already on the page.

A phrase selected inside a sentence has no translation of its own. Translation is one
segment in and one segment out, and the alignment pairs sentences, never words — so
until now the reader's chip could only string together the glosses of the words it
touched: "and a council · military · new" for ועדה צבאית חדשה. Honest, and no use.

This asks the model one question with the sentence and its translation in hand: which
piece of the translation is this run? Usually it is a contiguous piece, and that piece
comes back word for word, so the reader is shown the parallel text and not a second
translation of it. Where word order or idiom will not allow a quote, a short rendering
of the run as it is used here comes back instead, and the answer says which it is.

Bought when a reader selects, never in advance, and cached on the sentence, the
translation and the run — so the same selection in the same text is free for everyone
after the first. Nothing here touches SCHEMA_VERSION.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from pydantic import BaseModel

from ..cache import Cache
from ..errors import ProviderError
from ..translate.prompts import language_name
from .gloss import GLOSS_MODEL, gloss_provider_name

#: The same model meanings are bought on. It is part of the cache key for the same reason
#: the gloss model is: every place that asks must agree, or the same question is paid for
#: twice.
PHRASE_MODEL = GLOSS_MODEL

#: A sentence is what this is for; a paragraph is what a page could send. Enforced by the
#: server, and the reader only ever sends one segment, so the two do not disagree.
MAX_SENTENCE = 600
MAX_TRANSLATION = 900

# What a model wraps a quotation in, which the translation itself does not contain at
# the edges of a phrase.
_QUOTES = "\"'“”‘’«»"


class _Answer(BaseModel):
    meaning: str
    quoted: bool = False


class PhraseProvider(Protocol):
    @property
    def name(self) -> str: ...

    def explain(
        self,
        phrase: str,
        sentence: str,
        translation: str,
        source_language: str,
        target_language: str,
    ) -> tuple[str, bool]: ...


SYSTEM = """You are helping a {target} speaker read {source} with the translation beside the text.

You are given a {source} sentence, its {target} translation, and a run of words from the
sentence. Say what the run means.

- If a contiguous piece of the translation is the translation of exactly that run,
  return that piece word for word, exactly as it appears in the translation, and set
  quoted to true.
- Otherwise — the run is spread across the translation, or the idiom does not carry —
  return a short {target} rendering of the run as it is used in this sentence, and set
  quoted to false.
- The meaning only. No notes, no transliteration, no grammar."""


def tidy(text: str) -> str:
    return " ".join(text.split())


def entry_for(phrase: str, sentence: str, translation: str) -> str:
    return f"sentence: {tidy(sentence)}\ntranslation: {tidy(translation)}\nrun: {tidy(phrase)}"


def quoted_piece(meaning: str, translation: str) -> str | None:
    """The piece of the translation the answer is, as the translation spells it.

    None when the answer is not in the translation at all — a model asked for a quote
    sometimes paraphrases and still says it quoted. Whitespace, case and the quotation
    marks a model likes to add are forgiven; the words are not.
    """
    wanted = tidy(meaning).strip(_QUOTES).strip()
    if not wanted:
        return None
    text = tidy(translation)
    at = text.casefold().find(wanted.casefold())
    if at < 0:
        return None
    return text[at : at + len(wanted)]


class AnthropicPhrases:
    """Phrases from the same provider that does translation and glossing."""

    def __init__(self, model: str | None = None) -> None:
        from ..translate.anthropic_provider import AnthropicProvider

        self._provider = AnthropicProvider(model or PHRASE_MODEL)
        self.model = self._provider.model

    @property
    def name(self) -> str:
        return gloss_provider_name(self.model)

    def available(self) -> tuple[bool, str]:
        return self._provider.available()

    def explain(
        self,
        phrase: str,
        sentence: str,
        translation: str,
        source_language: str,
        target_language: str,
    ) -> tuple[str, bool]:
        import anthropic

        from ..translate.anthropic_provider import output_config

        system = SYSTEM.format(
            source=language_name(source_language), target=language_name(target_language)
        )
        try:
            response = self._provider.client().messages.parse(
                model=self.model,
                max_tokens=400,
                system=system,
                messages=[{"role": "user", "content": entry_for(phrase, sentence, translation)}],
                output_format=_Answer,
                **output_config(self.model, "low"),
            )
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                f"Anthropic API error {exc.status_code} while translating a phrase.",
                exc.message,
            ) from exc
        # Counted like everything else that is bought, small as each one is.
        self._provider.spent.add(
            self.model or "",
            int(getattr(response.usage, "input_tokens", 0) or 0),
            int(getattr(response.usage, "output_tokens", 0) or 0),
        )
        parsed: Any = response.parsed_output
        if not isinstance(parsed, _Answer):
            return "", False
        return parsed.meaning.strip(), bool(parsed.quoted)


def phrase_key(
    cache: Cache,
    phrase: str,
    sentence: str,
    translation: str,
    source: str,
    target: str,
    provider: str,
) -> str:
    """One place the key is spelled. The translation is part of it: a sentence translated
    again is a different question, and the old answer might quote words that are no
    longer on the page."""
    return cache.key(
        "phrase",
        phrase=tidy(phrase),
        sentence=tidy(sentence),
        translation=tidy(translation),
        source=source,
        target=target,
        provider=provider,
    )


def cached_phrase(
    phrase: str,
    sentence: str,
    translation: str,
    source: str,
    target: str,
    provider: str,
    cache: Cache | None = None,
) -> tuple[str, bool] | None:
    """The answer already held, or None. Never spends."""
    cache = cache or Cache()
    stored = cache.get(
        "phrase", phrase_key(cache, phrase, sentence, translation, source, target, provider)
    )
    if isinstance(stored, dict) and stored.get("meaning"):
        return str(stored["meaning"]), bool(stored.get("quoted"))
    return None


def phrase_one(
    phrase: str,
    sentence: str,
    translation: str,
    source: str,
    target: str,
    provider: PhraseProvider,
    *,
    cache: Cache | None = None,
) -> tuple[str, bool]:
    """One run of words, looked up because someone selected it.

    Returns the meaning and whether it is a quotation from the translation. `quoted` is
    only ever true when the words really are in the translation, whatever the model
    claimed, and then the meaning is the translation's own spelling of them. An empty
    answer is returned empty and not remembered, so the next reader asks again.
    """
    cache = cache or Cache()
    held = cached_phrase(phrase, sentence, translation, source, target, provider.name, cache)
    if held is not None:
        return held

    meaning, quoted = provider.explain(phrase, sentence, translation, source, target)
    meaning = tidy(meaning)
    if not meaning:
        return "", False
    piece = quoted_piece(meaning, translation) if quoted else None
    if piece is not None:
        meaning, quoted = piece, True
    else:
        quoted = False
    cache.put(
        "phrase",
        phrase_key(cache, phrase, sentence, translation, source, target, provider.name),
        {"meaning": meaning, "quoted": quoted},
    )
    return meaning, quoted


# Kept importable for a caller that wants to reject before it asks, the way the server does.
def within_limits(phrase: str, sentence: str, translation: str) -> bool:
    """A phrase-in-context service, not a translator: the run has to be in the sentence,
    and both texts have to be the size of a sentence."""
    return bool(
        phrase
        and sentence
        and translation
        and len(sentence) <= MAX_SENTENCE
        and len(translation) <= MAX_TRANSLATION
        and re.search(re.escape(tidy(phrase)), tidy(sentence)) is not None
    )
