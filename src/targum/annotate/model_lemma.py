"""Dictionary forms for a language no clean tagger reads, asked of the model and kept.

A word card needs a dictionary form and a part of speech for every word, and for Hebrew
DICTA gives both under CC BY 4.0. For French, Russian, Italian and Yiddish nothing does:
every Stanza model for them is trained on a NonCommercial or ShareAlike treebank, which
`LICENSING.md` keeps out of a paid offering (see `segment/stanza_segmenter.AUDITED`), and
Yiddish has no Stanza model at all. So the facts are asked of the model — the move
`dictionary.py` already makes for the Hebrew facts a permissive tagger is worst at — and
the same discipline comes with it:

- **Measured before it is believed.** `scripts/eval_lemma.py` scores what comes back
  against the Universal Dependencies dev sets for each language, which are fine to
  *score against* whatever their licence because nothing is trained on them and nothing
  derived from them ships; the scores sit in `evals/ledger.jsonl` and the floors file
  fails CI on a worse one.
- **Kept, once per sentence.** Cached by the language, the model, the prompt's version and
  the sentence's own text, so a sentence two texts share is read once, and a rebuild reads
  nothing again.
- **Never bought without a press.** Unlike Stanza this costs money, and targum's rule is
  that nothing is spent before a reader has seen the price and pressed. Every lemmatizer
  made here reads from the cache alone unless it is made with `buy=True`, which only
  `Build.annotate` and `Build.annotate_chapter` do — both inside a build that was quoted
  and claimed. Pricing a card, measuring a shelf, repairing a paragraph: cache only.
- **By the chapter.** A book is bought a chapter at a time, so `allowed` limits what one
  build may buy to the chapters it is buying; the rest of the book is read when those
  chapters are.

The name is part of the annotator's name, so a new prompt version reads every text in these
languages again — bought again, unlike every other annotator change. Move it only when
what a correct answer looks like has changed.

**The grammar comes with the word** (prompt 2, 2026-09-14, targum-internal#258). A Russian
learner's two hardest facts about a word are its case and its aspect, and a card that
names neither leaves the grammar line empty. Asked in the same pass rather than a second
one, because the words are already being read and a second pass would bill every word
twice: a fifth column of Universal Dependencies features, from a fixed list
(`FEATURES`), scored against the same dev sets as the dictionary forms.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Sequence
from typing import Any

from ..cache import Cache
from ..errors import ProviderError, TargumError
from ..models import Segment, Token
from ..usage import Usage

#: The languages read this way. Hebrew is DICTA's; Aramaic has no treebank to measure a
#: model against, so it stays text and translation until one exists.
LANGUAGES = frozenset({"fr", "ru", "it", "yi"})

#: Haiku: tagging a sentence is a narrow task, the answer is long (a line a word), and the
#: output is most of the bill. Scored against the treebanks like any other choice here; a
#: bigger model is a PROMPT_VERSION-sized decision, because the model is in the cache key.
MODEL = "claude-haiku-4-5"

#: The question's version. See the module docstring for what moving it costs.
PROMPT_VERSION = 2

#: How much text goes in one request. Small enough that a batch cut off at `max_tokens`
#: loses little, and is split and asked again rather than dropped.
BATCH_CHARS = 2400
BATCH_SEGMENTS = 30

#: For the price quoted before anything is spent. The system prompt rides on every batch;
#: each word comes back as a line of number, word, lemma, tag and features. Prompt 1 was
#: measured with the counting endpoint on 2026-09-13, over sixty dev-set sentences a
#: language: 435 tokens of prompt, and a word back at 10.9 tokens in French and Italian,
#: 12.2 in Russian and 15.8 in Yiddish, whose script tokenizes densely. Prompt 2 is 873
#: tokens by the counting endpoint (2026-09-14), and its per-word figures are the eval's
#: own usage over 120 dev sentences a language (`scripts/eval_lemma.py` prints them).
#: Quoted a little high on purpose, as `dictionary.py` does: a cap fed high refuses less
#: than it should, fed low it lets through more.
TOKENS_PER_BATCH = 900
TOKENS_PER_WORD_OUT = {"fr": 22, "it": 22, "ru": 30, "yi": 26}

#: The features a card can say something with, and the values each may take. Anything
#: else the model writes is dropped rather than shipped: a card must never say a word is
#: in a case the list does not have. Order is the order they are written in, after the
#: part of speech, which is the pipe format `hebrew.kept_feats` gives the card already.
#: `Loc` is the Russian prepositional, which is what Universal Dependencies calls it.
FEATURES: dict[str, frozenset[str]] = {
    "Case": frozenset({"Nom", "Gen", "Dat", "Acc", "Ins", "Loc", "Par", "Voc"}),
    "Gender": frozenset({"Masc", "Fem", "Neut"}),
    "Number": frozenset({"Sing", "Plur"}),
    "Animacy": frozenset({"Anim", "Inan"}),
    "Aspect": frozenset({"Perf", "Imp"}),
    "Tense": frozenset({"Past", "Pres", "Fut"}),
    "Person": frozenset({"1", "2", "3"}),
    "VerbForm": frozenset({"Inf", "Fin", "Part", "Conv"}),
    "Mood": frozenset({"Ind", "Imp", "Cnd", "Sub"}),
}

#: The features a language's card may show, where that is narrower than `FEATURES`. French
#: and Italian keep no case, animacy or aspect: their nouns have none, and the model's
#: case for a French pronoun agreed with the treebank 39% of the time on 2026-09-14 — a
#: card must not say what is measured to be a guess. Yiddish has case and no aspect.
KEPT: dict[str, frozenset[str]] = {
    "fr": frozenset(FEATURES) - {"Case", "Animacy", "Aspect"},
    "it": frozenset(FEATURES) - {"Case", "Animacy", "Aspect"},
    "yi": frozenset(FEATURES) - {"Animacy", "Aspect"},
}

#: The Universal POS tags, which is what a token's `pos` holds for every other lemmatizer.
UPOS = frozenset(
    "ADJ ADP ADV AUX CCONJ DET INTJ NOUN NUM PART PRON PROPN PUNCT SCONJ SYM VERB X".split()
)
_SKIPPED = frozenset({"PUNCT", "SYM"})
_NUMBER = re.compile(r"^[#(\[]?(\d+)(?:[.:)\]][\d.]*)?$")

#: The apostrophes a text is written with, read as one when a word is placed. French and
#: Italian usually arrive with the curly one (`l’école`, `dell’anno`) and the model often
#: answers with the straight one, which dropped the article without a trace
#: (targum-internal#262). Each is a single code point, so offsets survive the swap.
_APOSTROPHES = str.maketrans({"\u2019": "'", "\u02bc": "'"})

SYSTEM = """You tag {language} text for a reading tool that shows a learner the dictionary \
form and the grammar of every word.

You are given numbered segments. For every word of every segment, in order, write one line:

<segment number><TAB><word exactly as written><TAB><dictionary form><TAB><part of speech>\
<TAB><features>

The first column is the segment's number alone, the same on every line of that segment: \
3, never 3.1 or 3.2.

- The word is copied character for character from the segment: same letters, same accents, \
same capitals. Never correct, normalise or translate it.
- Skip punctuation and symbols. Numbers written in digits are words, tagged NUM.
- An elided word is split at its apostrophe, and the apostrophe stays on the first part: \
l'homme is l' and homme, qu'il is qu' and il, dell'anno is dell' and anno.
- A pronoun joined to a verb by a hyphen is its own word: dit-il is dit and il. A compound \
written with a hyphen or an apostrophe inside it (aujourd'hui, grand-mère, всё-таки) is one \
word.
- The dictionary form is the headword a {language} dictionary lists: the infinitive of a \
verb, the singular of a noun (nominative singular in Russian), the masculine singular of an \
adjective, the base form of a pronoun or article. Lowercase, except a proper name. For a \
contraction of a preposition and an article (du, au, della, nel) give the preposition.
- In Russian keep ё where the dictionary form has it, and add no stress marks.
- In Yiddish write the dictionary form in the spelling the text uses; a verb's is its \
infinitive.
- The part of speech is one Universal Dependencies tag: ADJ ADP ADV AUX CCONJ DET INTJ NOUN \
NUM PART PRON PROPN SCONJ VERB X.
- The features are the word's grammar as it is used in this sentence, in Universal \
Dependencies form, joined with |, and only these: Case (Nom Gen Dat Acc Ins Loc Par Voc), \
Gender (Masc Fem Neut), Number (Sing Plur), Animacy (Anim Inan), Aspect (Perf Imp), Tense \
(Past Pres Fut), Person (1 2 3), VerbForm (Inf Fin Part Conv), Mood (Ind Imp Cnd Sub). For \
example Case=Acc|Gender=Fem|Number=Sing, or Gender=Masc|Number=Sing|Aspect=Perf|Tense=Past|\
VerbForm=Fin|Mood=Ind. Write _ when none apply.
- In Russian, Loc is the prepositional case. Every noun, pronoun, adjective, determiner, \
declined numeral and participle has its Case, and every verb form, participles and \
converbs included, has its Aspect. A participle (описанный, идущий, заданных) is tagged \
VERB with VerbForm=Part, never ADJ, and its dictionary form is the verb's infinitive; it has \
Case, Gender, Number, Aspect and Tense. A noun has its Animacy.
- Case is read from the sentence, not from the ending alone: where nominative and \
accusative look the same, the subject is Nom and the direct object is Acc, whichever comes \
first; a noun after a preposition is in the case that preposition takes here (в школе Loc, \
в школу Acc, по мере Dat). Words of a name in apposition take the case of the phrase.
- Write nothing else: no heading, no explanation, no blank lines."""


def reads(language: str) -> bool:
    """Whether a language's words are read by this lemmatizer."""
    return (language or "").split("-")[0].lower() in LANGUAGES


def provider_name(model: str = MODEL, version: int = PROMPT_VERSION) -> str:
    return f"model-lemma/{model}/{version}"


def key(cache: Cache, text: str, language: str, provider: str) -> str:
    """One place the cache key is spelled, so pricing and paying cannot disagree."""
    return cache.key("lemma", text=text, language=language, provider=provider)


def _code(language: str) -> str:
    return (language or "").split("-")[0].lower()


def _has_letters(text: str) -> bool:
    return any(char.isalpha() for char in text)


def _place(text: str, surface: str, cursor: int) -> int:
    """Where `surface` is next written in `text` as a word of its own, or -1.

    A find that starts or ends inside a run of letters is another word's middle: the model's
    `de` for `d’` was placed inside *solde* ninety letters on, and every word between was
    lost with it (targum-internal#262). Such a place is passed over, not taken.
    """
    at = text.find(surface, cursor)
    while at >= 0:
        end = at + len(surface)
        inside = (at > 0 and text[at - 1].isalpha() and surface[0].isalpha()) or (
            end < len(text) and text[end].isalpha() and surface[-1].isalpha()
        )
        if not inside:
            return at
        at = text.find(surface, at + 1)
    return -1


def unpaid(
    segments: Sequence[Segment], language: str, provider: str, cache: Cache | None = None
) -> list[Segment]:
    """The segments nobody has paid to read yet, so a price is quoted net of the cache."""
    cache = cache or Cache()
    code = _code(language)
    return [
        segment
        for segment in segments
        if _has_letters(segment.text)
        and cache.get("lemma", key(cache, segment.text, code, provider)) is None
    ]


def estimate(segments: Sequence[Segment], language: str, model: str = MODEL) -> float:
    """What reading these segments will cost, before a cent is spent."""
    from ..translate.anthropic_provider import (
        CHARS_PER_TOKEN,
        DEFAULT_CHARS_PER_TOKEN,
        DEFAULT_MODEL,
        PRICES,
    )

    if not segments:
        return 0.0
    in_price, out_price = PRICES.get(model, PRICES[DEFAULT_MODEL])
    per_token = CHARS_PER_TOKEN.get(_code(language), DEFAULT_CHARS_PER_TOKEN)
    chars = sum(len(segment.text) for segment in segments)
    words = sum(len(segment.text.split()) for segment in segments)
    batches = max(1, -(-chars // BATCH_CHARS))
    tokens_in = chars / per_token + batches * TOKENS_PER_BATCH
    tokens_out = words * TOKENS_PER_WORD_OUT.get(_code(language), 17)
    return (tokens_in * in_price + tokens_out * out_price) / 1_000_000


def features(raw: str, pos: str, language: str = "") -> str:
    """The card's grammar string: the part of speech, then the features `FEATURES` allows
    and the language keeps (`KEPT`).

    Written in the order `FEATURES` lists, whatever order the model used, so the same
    grammar is the same string — which is what the reader's table of distinct strings
    counts on.
    """
    kept = KEPT.get(_code(language), frozenset(FEATURES))
    said: dict[str, str] = {}
    for part in (raw or "").split("|"):
        name, _, value = part.strip().partition("=")
        if name in kept and value in FEATURES.get(name, ()):
            said.setdefault(name, value)
    return "|".join([f"UPOS={pos}", *(f"{name}={said[name]}" for name in FEATURES if name in said)])


def parse(answer: str, texts: Sequence[str], language: str = "") -> list[list[Token] | None]:
    """Tokens per segment from the model's lines, placed by searching each segment's text.

    Offsets are found, never trusted: each word is looked for in its own segment from where
    the last one ended, so a word the model spelled differently from the text is dropped
    rather than put on a card over the wrong letters. The one difference forgiven is the
    apostrophe: ’ and ' place the same word, and the surface is always the text's own.
    A segment the answer never mentioned is `None`, which is different from a segment that
    was read and held no word.
    """
    lines: list[list[tuple[str, str, str, str]]] = [[] for _ in texts]
    mentioned = [False for _ in texts]
    for line in answer.splitlines():
        fields = [field.strip() for field in line.split("\t")]
        # The segment's number leads the line. Asked for alone, it sometimes arrives as
        # the word's place too — `3.1`, `3.2` — which lost whole batches until it was
        # read for what it leads with (measured on the French dev set, 2026-09-13).
        # Four columns is an answer that left the features off, which still has words in
        # it worth keeping.
        numbered = _NUMBER.match(fields[0]) if len(fields) in (4, 5) else None
        if numbered is None:
            continue
        number = int(numbered.group(1)) - 1
        if not 0 <= number < len(texts):
            continue
        mentioned[number] = True
        surface, lemma, pos = fields[1], fields[2], fields[3].upper()
        grammar = fields[4] if len(fields) == 5 else ""
        if surface and pos not in _SKIPPED:
            tag = pos if pos in UPOS else "X"
            lines[number].append((surface, lemma or surface, tag, features(grammar, tag, language)))

    out: list[list[Token] | None] = []
    for text, words, said in zip(texts, lines, mentioned, strict=True):
        if not said:
            out.append(None)
            continue
        tokens: list[Token] = []
        cursor = 0
        plain = text.translate(_APOSTROPHES)
        folded = plain.casefold()
        for surface, lemma, pos, feats in words:
            surface = surface.translate(_APOSTROPHES)
            at = _place(plain, surface, cursor)
            if at < 0 and len(folded) == len(text):
                at = _place(folded, surface.casefold(), cursor)
            if at < 0:
                continue
            end = at + len(surface)
            # An elided word the model wrote without its apostrophe (`l` for `l’`) takes
            # the apostrophe the text gives it, as the prompt asks.
            if end < len(plain) and plain[end] == "'" and surface[-1].isalpha():
                end += 1
            if not _has_letters(text[at:end]) and pos != "NUM":
                continue
            tokens.append(
                Token(
                    start=at,
                    end=end,
                    surface=text[at:end],
                    lemma=lemma if pos == "PROPN" else lemma.lower(),
                    band=0,
                    pos=pos,
                    feats=feats,
                )
            )
            cursor = end
        out.append(tokens)
    return out


def _stored(tokens: list[Token]) -> list[list[Any]]:
    return [[t.start, t.end, t.surface, t.lemma, t.pos, t.feats or ""] for t in tokens]


def _restored(rows: Any, text: str) -> list[Token] | None:
    if not isinstance(rows, list):
        return None
    tokens: list[Token] = []
    for row in rows:
        if not isinstance(row, list) or len(row) != 6:
            return None
        start, end, surface, lemma, pos, feats = row
        if not (isinstance(start, int) and isinstance(end, int) and text[start:end] == surface):
            return None
        tokens.append(
            Token(
                start=start,
                end=end,
                surface=surface,
                lemma=str(lemma),
                band=0,
                pos=str(pos),
                feats=str(feats) or None,
            )
        )
    return tokens


class ModelLemmatizer:
    """Tokens, dictionary forms, parts of speech and grammar, read by the model and cached."""

    def __init__(
        self,
        model: str = MODEL,
        *,
        buy: bool = False,
        allowed: Collection[str] | None = None,
        cache: Cache | None = None,
    ) -> None:
        self.model = model
        self.buy = buy
        #: The segment ids a build may pay to read. `None` is all of them.
        self.allowed: set[str] | None = set(allowed) if allowed is not None else None
        self.cache = cache or Cache()
        self.spent = Usage()
        self._provider: Any = None

    @property
    def name(self) -> str:
        return provider_name(self.model)

    def provider(self) -> Any:
        if self._provider is None:
            from ..translate.anthropic_provider import AnthropicProvider

            self._provider = AnthropicProvider(self.model)
        return self._provider

    def available(self) -> tuple[bool, str]:
        usable, why = self.provider().available()
        return bool(usable), str(why)

    def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
        code = _code(language)
        if code not in LANGUAGES:
            raise TargumError(
                f"The model does not read '{code}' words here.",
                "Hebrew is read by DICTA; see annotate/model_lemma.LANGUAGES.",
            )
        out: dict[str, list[Token]] = {}
        owed: list[Segment] = []
        for segment in segments:
            if not _has_letters(segment.text):
                out[segment.id] = []
                continue
            stored = self.cache.get("lemma", key(self.cache, segment.text, code, self.name))
            held = (
                _restored(stored.get("tokens"), segment.text) if isinstance(stored, dict) else None
            )
            if held is not None:
                out[segment.id] = held
            elif self.buy and (self.allowed is None or segment.id in self.allowed):
                owed.append(segment)
        if owed:
            usable, why = self.available()
            if not usable:
                raise TargumError("Cannot read the words without a key.", why)
            for segment, tokens in zip(owed, self._read(owed, code), strict=True):
                if tokens is not None:
                    out[segment.id] = tokens
        return out

    def _read(self, segments: list[Segment], code: str) -> list[list[Token] | None]:
        """Every segment's tokens, in batches, splitting any batch the answer overran.

        Each batch is kept the moment it comes back, not once the last one has. A book is
        about an hour of batches one after another, and keeping them all at the end
        threw away every paid answer when one call failed — a 400 when the credit ran out
        at 11:41 on 2026-09-14 lost about $3. Kept as it arrives, a run that dies is
        rerun for the batches that never answered and nothing else.
        """
        results: list[list[Token] | None] = []
        batch: list[Segment] = []
        size = 0

        def ask() -> None:
            found = self._ask(batch, code)
            for segment, tokens in zip(batch, found, strict=True):
                if tokens is not None:
                    self.cache.put(
                        "lemma",
                        key(self.cache, segment.text, code, self.name),
                        {"text": segment.text, "provider": self.name, "tokens": _stored(tokens)},
                    )
            results.extend(found)

        for segment in segments:
            if batch and (size + len(segment.text) > BATCH_CHARS or len(batch) >= BATCH_SEGMENTS):
                ask()
                batch, size = [], 0
            batch.append(segment)
            size += len(segment.text)
        if batch:
            ask()
        return results

    def _ask(
        self, batch: list[Segment], code: str, *, again: bool = True
    ) -> list[list[Token] | None]:
        if not batch:
            return []

        import anthropic

        from ..translate.anthropic_provider import output_config
        from ..translate.prompts import language_name

        texts = [segment.text for segment in batch]
        words = sum(len(text.split()) for text in texts)
        body = "\n\n".join(f"{n}. {text}" for n, text in enumerate(texts, start=1))
        try:
            response = (
                self.provider()
                .client()
                .messages.create(
                    model=self.model,
                    max_tokens=min(16000, 400 + words * 40),
                    system=SYSTEM.format(language=language_name(code)),
                    messages=[{"role": "user", "content": body}],
                    **output_config(self.model, "low"),
                )
            )
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                f"Anthropic API error {exc.status_code} while reading the words.", exc.message
            ) from exc
        usage = getattr(response, "usage", None)
        self.spent.add(
            self.model,
            int(getattr(usage, "input_tokens", 0) or 0),
            int(getattr(usage, "output_tokens", 0) or 0),
        )
        answer = "".join(str(getattr(block, "text", "")) for block in response.content)
        found = parse(answer, texts, code)
        if getattr(response, "stop_reason", "") == "max_tokens" and len(batch) > 1:
            # Cut off: keep what arrived whole and ask again for the rest, in halves. The
            # last segment the answer reached may be cut too, so it is asked again.
            reached = max((n for n, tokens in enumerate(found) if tokens is not None), default=-1)
            kept = found[:reached] if reached > 0 else []
            rest = batch[len(kept) :]
            middle = max(1, len(rest) // 2)
            return kept + self._ask(rest[:middle], code) + self._ask(rest[middle:], code)
        skipped = [n for n, tokens in enumerate(found) if tokens is None]
        if skipped and again and len(batch) > 1:
            # A segment the answer never reached is asked once more, on its own batch,
            # rather than left without words or asked for ever.
            retried = self._ask([batch[n] for n in skipped], code, again=False)
            for n, tokens in zip(skipped, retried, strict=True):
                found[n] = tokens
        return found
