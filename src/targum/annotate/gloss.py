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

from collections.abc import Callable, Collection, Mapping
from typing import Any, NamedTuple, Protocol

from pydantic import BaseModel

from ..cache import Cache
from ..errors import ProviderError, TargumError
from ..models import Annotation, Glossary
from ..translate.prompts import language_name

BATCH_SIZE = 40
# Glosses are short, so a batch is cheap. Tokens per lemma, in and out, for the estimate
# shown before anything is spent. Measured Aug 27 2026 over 30,000 Hebrew lemmas: 22 in
# on every model, 35 out on Sonnet and 50 on Opus. The earlier guess of 12 and 24
# quoted half the bill; 40 out is the middle, and a cap that refuses a build is better
# fed a little high than a little low.
TOKENS_PER_LEMMA_IN = 22
TOKENS_PER_LEMMA_OUT = 40

Progress = Callable[[int], None]


class _Entry(BaseModel):
    lemma: str
    gloss: str
    part_of_speech: str = ""
    citation: str = ""
    plural: str = ""


class Sense(NamedTuple):
    """Everything a gloss can say about a dictionary form.

    `citation` and `plural` arrived 2026-08-31 and are empty on everything glossed
    before then. Deliberately: the provider name did not move, so nothing already paid
    for is bought again — the fields fill in lemma by lemma as words are looked up,
    the way contextual senses do.
    """

    gloss: str
    part: str = ""
    #: Verbs: the form a learner keeps — the infinitive, with the preposition the verb
    #: takes where it takes one. לְהִשְׁתַּמֵּשׁ בְּ־, not השתמש.
    citation: str = ""
    #: Nouns: the plural, only where it lies about the gender or changes the stem.
    #: מִלִּים beside מילה; nothing beside ספר.
    plural: str = ""
    #: Whether a sentence decided which sense came first. A gloss bought bare is a guess
    #: at which sense a reader will need — עם came back "people; nation", and the
    #: preposition never — so it stands only until a reader meets the word in a
    #: sentence, which buys it once more, grounded, and that one stands for good.
    #: Absent on everything glossed before 2026-09-02, which is the point: the
    #: catalogue's lemmas were bought without a sentence, and re-buying them all would
    #: only guess a different sentence.
    grounded: bool = False


class _Batch(BaseModel):
    entries: list[_Entry]


#: What meanings are bought on. Cheaper than the prose and good enough for a dictionary
#: line, and the cache is keyed on it: every reader, the quote, the build and a rebuild
#: filling a card from what is held must agree, or the same word is paid for twice.
GLOSS_MODEL = "claude-sonnet-5"


def gloss_provider_name(model: str = GLOSS_MODEL) -> str:
    return f"anthropic/{model}"


class GlossProvider(Protocol):
    @property
    def name(self) -> str: ...

    def gloss(
        self,
        lemmas: list[str],
        source_language: str,
        target_language: str,
        on_progress: Progress | None = None,
        contexts: Mapping[str, str] | None = None,
    ) -> Mapping[str, Any]: ...


SYSTEM = """You are writing a learner's glossary for {source} read by a {target} speaker.

For each {source} dictionary form you are given, return one short {target} gloss.

- Each entry is a dictionary form after `form:`, sometimes followed by the sentence the
  reader met it in after `in:`. Gloss the form, and return it exactly as it was given.
- Two to six words. The most common sense first — or, where a sentence is given, the
  sense the form has there — and a second sense only when the word is genuinely
  ambiguous, separated by a semicolon. The gloss is kept for every text, not this one.
- No transliteration, no grammatical explanation, no example sentences.
- Give the part of speech as one of: noun, verb, adjective, adverb, preposition,
  pronoun, conjunction, particle, other.
- For a verb, give citation: the form a learner would keep, in {source} — the
  infinitive, with the preposition the verb takes where it takes one. Otherwise leave
  citation empty.
- For a noun whose plural is irregular — the ending does not match the gender, or the
  stem changes — give plural: that plural form, in {source}. For a regular plural
  leave it empty.
- For a grammatical word with no {target} equivalent, the gloss is a short note on
  what it does instead of a translation.
- If a form is not a word of {source}, return it with an empty gloss rather than
  guessing."""


def entries_for(lemmas: list[str], contexts: Mapping[str, str] | None = None) -> str:
    """One entry per form, with the sentence it was met in where there is one.

    A gloss with no sentence behind it is a guess at which sense the reader needs — עם
    is "with" and "people", and a learner shown the wrong one is worse off than one
    shown neither. The sentence is what lets the model put the live sense first.
    """
    entries = []
    for lemma in lemmas:
        sentence = " ".join(((contexts or {}).get(lemma) or "").split())
        entries.append(f"form: {lemma}" + (f"\nin: {sentence}" if sentence else ""))
    return "\n\n".join(entries)


class AnthropicGlosses:
    """Glosses from the same provider that does translation."""

    def __init__(self, model: str | None = None, *, batch_size: int = BATCH_SIZE) -> None:
        from ..translate.anthropic_provider import DEFAULT_MODEL, AnthropicProvider

        self._provider = AnthropicProvider(model or DEFAULT_MODEL)
        self.model = self._provider.model
        self.batch_size = batch_size

    @property
    def name(self) -> str:
        return gloss_provider_name(self.model)

    def available(self) -> tuple[bool, str]:
        return self._provider.available()

    def gloss(
        self,
        lemmas: list[str],
        source_language: str,
        target_language: str,
        on_progress: Progress | None = None,
        contexts: Mapping[str, str] | None = None,
    ) -> dict[str, Sense]:
        import anthropic

        from ..translate.anthropic_provider import output_config

        system = SYSTEM.format(
            source=language_name(source_language), target=language_name(target_language)
        )
        out: dict[str, Sense] = {}
        for start in range(0, len(lemmas), self.batch_size):
            batch = lemmas[start : start + self.batch_size]
            try:
                response = self._provider.client().messages.parse(
                    model=self.model,
                    max_tokens=8000,
                    system=system,
                    messages=[{"role": "user", "content": entries_for(batch, contexts)}],
                    output_format=_Batch,
                    **output_config(self.model, "low"),
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
                        out[entry.lemma] = Sense(
                            entry.gloss.strip(),
                            entry.part_of_speech.strip(),
                            entry.citation.strip(),
                            entry.plural.strip(),
                        )
            if on_progress:
                on_progress(len(batch))
        return out


def unique_lemmas(
    annotation: Annotation, *, min_band: int = 1, only: Collection[str] | None = None
) -> list[str]:
    """Every distinct lemma worth glossing, rarest-first so a cut list keeps the useful end.

    `only` narrows it to a set of segments — the chapters a build is actually buying.
    Meanings are the expensive half of a build, and looking them up for a whole novel
    when one chapter of it was bought is how a long book came to cost more than the cap
    allowed and could never be opened at all.

    "Lemma" here is the form a meaning is filed under, which is the lemma except where
    two words share a spelling and the token says which — see `Token.glossed_as`. אֵלֶּה
    and אָלָה are one lemma and two entries, because they are two words.
    """
    best: dict[str, int] = {}
    for segment_id, tokens in annotation.tokens.items():
        if only is not None and segment_id not in only:
            continue
        for token in tokens:
            # An unrated word is still a word worth looking up.
            if token.band >= min_band or (token.band == 0 and min_band <= 1):
                form = token.glossed_as
                best[form] = max(best.get(form, 0), token.band)
    return [lemma for lemma, _ in sorted(best.items(), key=lambda item: (-item[1], item[0]))]


def gloss_key(cache: Cache, lemma: str, source: str, target: str, provider: str) -> str:
    """One place the cache key is spelled, so pricing and paying cannot disagree."""
    return cache.key("gloss", lemma=lemma, source=source, target=target, provider=provider)


def unpaid(
    lemmas: Collection[str],
    source_language: str,
    target_language: str,
    provider: str,
    cache: Cache | None = None,
) -> list[str]:
    """The lemmas nobody has looked up yet.

    Glosses are cached per lemma across every text, so most of a second Hebrew book is
    already bought. An estimate that counts them anyway quotes a price for work that is
    about to be free, which is the difference between a book opening and a book being
    refused.
    """
    cache = cache or Cache()
    missing: list[str] = []
    for lemma in lemmas:
        stored = cache.get(
            "gloss", gloss_key(cache, lemma, source_language, target_language, provider)
        )
        if not (isinstance(stored, dict) and stored.get("gloss")):
            missing.append(lemma)
    return missing


def estimate(lemma_count: int, model: str) -> float:
    from ..translate.anthropic_provider import DEFAULT_MODEL, PRICES

    in_price, out_price = PRICES.get(model, PRICES[DEFAULT_MODEL])
    return (
        lemma_count * TOKENS_PER_LEMMA_IN * in_price
        + lemma_count * TOKENS_PER_LEMMA_OUT * out_price
    ) / 1_000_000


def cached_gloss(
    lemma: str,
    source_language: str,
    target_language: str,
    provider: str,
    cache: Cache | None = None,
) -> Sense | None:
    """The sense already held for a word, or None. Never spends."""
    cache = cache or Cache()
    stored = cache.get("gloss", gloss_key(cache, lemma, source_language, target_language, provider))
    if isinstance(stored, dict) and stored.get("gloss"):
        return _sense_of(stored)
    return None


def _sense_of(stored: dict[str, Any]) -> Sense:
    return Sense(
        str(stored["gloss"]),
        str(stored.get("part_of_speech", "")),
        str(stored.get("citation", "")),
        str(stored.get("plural", "")),
        bool(stored.get("grounded", False)),
    )


def _record(sense: Sense, *, grounded: bool) -> dict[str, Any]:
    """What is written to the cache for one sense — one place, so a sense bought by the
    build and one bought at a tap are read back by the same code."""
    return {
        "gloss": sense.gloss,
        "part_of_speech": sense.part,
        "citation": sense.citation,
        "plural": sense.plural,
        "grounded": grounded,
    }


class _Held:
    """A provider that only ever answers from the cache, for filling without buying."""

    def __init__(self, model: str = GLOSS_MODEL) -> None:
        self.name = gloss_provider_name(model)

    def gloss(self, *args: Any, **kwargs: Any) -> dict[str, Sense]:
        raise TargumError("Nothing is bought here.")


def fill_from_cache(
    annotation: Annotation,
    glossaries: dict[str, Glossary],
    targets: Collection[str],
    cache: Cache | None = None,
    provider: GlossProvider | None = None,
) -> dict[str, Glossary]:
    """Every glossary this text can have for free: what it has, plus whatever the cache
    holds for its words in each language somebody reads. Returns only the ones that
    changed, so a rebuild writes nothing where nothing changed.

    A lemma the glossary already has is taken from the cache too where the two differ:
    the cache is the later word, because a reader met the word in a sentence and the
    sense was bought again with that sentence in hand, and the file should catch up.

    `provider`, given, buys what the cache lacks as well. Free is the default because a
    rebuild is; but a word can come to be filed under a key nobody has bought yet — the
    pointed headwords of `oshb/2` reached the box with 92 of 200 rows of Judges empty —
    and a shelf full of "look it up" buttons on everyday words is not a state a rebuild
    should leave a reader in. Bought bare, the way a build buys them, so the first tap
    grounds each one.
    """
    cache = cache or Cache()
    grown: dict[str, Glossary] = {}
    for target in sorted(set(targets) | set(glossaries)):
        if provider is None:
            held, _ = build_glossary(annotation, target, _Held(), cache=cache, buy=False)
        else:
            held, _ = build_glossary(annotation, target, provider, cache=cache)
        have = glossaries.get(target)
        entries = dict(have.entries) if have else {}
        parts = dict(have.parts_of_speech) if have else {}
        citations = dict(have.citations) if have else {}
        plurals = dict(have.plurals) if have else {}
        new = {lemma: gloss for lemma, gloss in held.entries.items() if entries.get(lemma) != gloss}
        if not new:
            continue
        entries |= new
        parts |= {lemma: held.parts_of_speech.get(lemma, "") for lemma in new}
        citations |= {lemma: held.citations[lemma] for lemma in new if lemma in held.citations}
        plurals |= {lemma: held.plurals[lemma] for lemma in new if lemma in held.plurals}
        grown[target] = Glossary(
            source_language=annotation.language,
            target_language=target,
            provider=have.provider if have else held.provider,
            entries=entries,
            parts_of_speech=parts,
            citations=citations,
            plurals=plurals,
        )
    return grown


def gloss_one(
    lemma: str,
    source_language: str,
    target_language: str,
    provider: GlossProvider,
    *,
    cache: Cache | None = None,
    context: str = "",
) -> Sense | None:
    """One word, looked up because someone asked for it.

    The whole-text pass is the expensive half of a build and most of what it buys is
    never read: you look up the handful of words you actually stumble on. This is that
    handful, one at a time, through the same cache — so a word looked up while reading
    one article is free in the next.

    `context` is the sentence it was tapped in. The answer is still filed under the
    lemma alone — the cache is what makes the second book cheap, and a key that carried
    the sentence would make every word cost again in every text — so the sentence
    decides which sense comes first, and the other common sense rides after it for
    whoever meets the word elsewhere.

    A sense held without a sentence behind it is bought once more the first time a
    sentence arrives, and never after: the catalogue's lemmas were all bought bare, and
    this is how each one gets its sentence — the sentence a reader was actually in,
    at the moment they asked, for the price of one lookup. Re-buying all of them at
    once would cost the same per word and guess the sentence.
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
    held = _sense_of(stored) if isinstance(stored, dict) and stored.get("gloss") else None
    if held is not None and (held.grounded or not context):
        return held

    try:
        if context:
            fresh = provider.gloss(
                [lemma], source_language, target_language, None, contexts={lemma: context}
            )
        else:
            fresh = provider.gloss([lemma], source_language, target_language, None)
    except TargumError:
        # A word that already has a meaning does not lose it because grounding it
        # failed just now; the next sentence will try again. A word with nothing is
        # a failure the reader has to be told about.
        if held is not None:
            return held
        raise
    found = fresh.get(lemma)
    if not found:
        return held
    sense = Sense(*found)._replace(grounded=bool(context))
    cache.put("gloss", key, _record(sense, grounded=sense.grounded))
    return sense


def build_glossary(
    annotation: Annotation,
    target_language: str,
    provider: GlossProvider,
    *,
    min_band: int = 1,
    only: Collection[str] | None = None,
    cache: Cache | None = None,
    on_progress: Progress | None = None,
    on_batch: Callable[[Glossary], None] | None = None,
    buy: bool = True,
) -> tuple[Glossary, int]:
    """Returns the glossary and how many lemmas had to be paid for.

    `buy=False` hands over what the cache already holds and buys nothing: the count
    that comes back is then what it *would* have cost, in lemmas.

    `on_batch` is handed the glossary so far after every batch that is paid for. The
    reader opens before any of this has run and polls for the file, so writing it once
    at the end meant every word showed a blank card for as long as the whole run took.
    """
    cache = cache or Cache()
    wanted = unique_lemmas(annotation, min_band=min_band, only=only)

    entries: dict[str, str] = {}
    parts: dict[str, str] = {}
    citations: dict[str, str] = {}
    plurals: dict[str, str] = {}

    def keep(lemma: str, sense: Sense) -> None:
        entries[lemma] = sense.gloss
        parts[lemma] = sense.part
        # Only where there is something to say: most words have neither, and a
        # glossary of thirty thousand lemmas must not carry that many empty strings.
        if sense.citation:
            citations[lemma] = sense.citation
        if sense.plural:
            plurals[lemma] = sense.plural

    missing: list[str] = []
    for lemma in wanted:
        key = gloss_key(cache, lemma, annotation.language, target_language, provider.name)
        stored = cache.get("gloss", key)
        if isinstance(stored, dict) and stored.get("gloss"):
            keep(lemma, _sense_of(stored))
        else:
            missing.append(lemma)

    def assembled() -> Glossary:
        return Glossary(
            source_language=annotation.language,
            target_language=target_language,
            provider=provider.name,
            entries=dict(entries),
            parts_of_speech=dict(parts),
            citations=dict(citations),
            plurals=dict(plurals),
        )

    # Handed over a batch at a time rather than all at once, so a partial glossary can
    # be published while the rest is still being looked up. The provider batches
    # internally too; asking for one batch at a time makes each call one request.
    if not buy:
        return assembled(), len(missing)

    size = max(1, int(getattr(provider, "batch_size", 0)) or len(missing) or 1)
    for start in range(0, len(missing), size):
        chunk = missing[start : start + size]
        fresh = provider.gloss(chunk, annotation.language, target_language, on_progress)
        for lemma, found in fresh.items():
            # `Sense(*found)` reads a bare (gloss, part) pair as readily as a full
            # sense, so a provider that says less still fits.
            sense = Sense(*found)
            keep(lemma, sense)
            # Bought bare — the whole text at once, no sentence per word — so it
            # says so, and the first reader to meet the word in a sentence grounds it.
            cache.put(
                "gloss",
                gloss_key(cache, lemma, annotation.language, target_language, provider.name),
                _record(sense, grounded=False),
            )
        if on_batch:
            on_batch(assembled())

    return assembled(), len(missing)
