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

**And a French object pronoun says what it stands for** (prompt 3, 2026-09-28,
targum-internal#264, with #263's imperfect). The tense list takes `Imp`, so the imparfait
is no longer written as the past and a finite past is the passé simple; a French clitic
takes its `Role`; and where the words that name what it stands for are in the same segment
or the one before, a sixth column copies them. One bump for all three, because a bump
re-reads every text these languages have.

**A reading from an earlier prompt still serves** (`EARLIER`). Until a text is read again
— `targum rebuild --words --reread fr`, which spends — a lemmatizer that is not buying a
segment takes its prompt-2 reading rather than dropping its words, and says so in its name
(`/with-2`), so the page knows its tenses are not yet apart and a rebuild after the
re-read picks the new reading up.
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
PROMPT_VERSION = 3

#: The earlier versions whose cached readings still serve a segment nobody is buying now,
#: newest first. Prompt 2's facts are prompt 3's less the imparfait and the clitic's role,
#: so a card drawn from one says less and nothing wrong. Prompt 1 had no grammar at all.
EARLIER = (2,)

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
#: Prompt 3 is 1,291 tokens by the counting endpoint (2026-09-28), and its eval came back
#: at 20.7 tokens a word in French and 21.4 in Italian: a role and a sixth column ride on
#: a pronoun or two a sentence, so the per-word figures stand. Russian and Yiddish were not
#: read again. Quoted a little high on purpose, as `dictionary.py` does: a cap fed high
#: refuses less than it should, fed low it lets through more.
TOKENS_PER_BATCH = 1300
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
    "Tense": frozenset({"Past", "Pres", "Fut", "Imp"}),
    "Person": frozenset({"1", "2", "3"}),
    "VerbForm": frozenset({"Inf", "Fin", "Part", "Conv"}),
    "Mood": frozenset({"Ind", "Imp", "Cnd", "Sub"}),
    # Not Universal Dependencies, which says this with the relation rather than a feature:
    # what a French clitic is to its verb (prompt 3, targum-internal#264). `En` and `Y`
    # are named for the pronoun, because "of it, some" and "there, to it" are theirs alone.
    "Role": frozenset({"Obj", "Iobj", "En", "Y", "Refl"}),
}

#: The features a language's card may show, where that is narrower than `FEATURES`. French
#: and Italian keep no case, animacy or aspect: their nouns have none, and the model's
#: case for a French pronoun agreed with the treebank 39% of the time on 2026-09-14 — a
#: card must not say what is measured to be a guess. Yiddish has case and no aspect. A
#: clitic's role is asked of French alone.
KEPT: dict[str, frozenset[str]] = {
    "fr": frozenset(FEATURES) - {"Case", "Animacy", "Aspect"},
    "it": frozenset(FEATURES) - {"Case", "Animacy", "Aspect", "Role"},
    "ru": frozenset(FEATURES) - {"Role"},
    "yi": frozenset(FEATURES) - {"Animacy", "Aspect", "Role"},
}

#: The card names what a pronoun stands for only once the words it copies are measured to
#: be right nine times in ten (targum-internal#264, criterion 2). The measure is a hand-
#: written set of 150 sentences that waits for a person, so until it is written this is
#: `None` and the card gives the role alone. The words are read and kept all the same:
#: they cost next to nothing in the same pass, and asked later they would cost a re-read.
ANTECEDENT_PRECISION: float | None = None
ANTECEDENT_FLOOR = 0.9


def antecedents_shown() -> bool:
    """Whether the page carries what a pronoun stands for (`ANTECEDENT_PRECISION`)."""
    return ANTECEDENT_PRECISION is not None and ANTECEDENT_PRECISION >= ANTECEDENT_FLOOR


#: The Universal POS tags, which is what a token's `pos` holds for every other lemmatizer.
UPOS = frozenset(
    "ADJ ADP ADV AUX CCONJ DET INTJ NOUN NUM PART PRON PROPN PUNCT SCONJ SYM VERB X".split()
)
_SKIPPED = frozenset({"PUNCT", "SYM"})
_NUMBER = re.compile(r"^[#(\[]?(\d+)(?:[.:)\]][\d.]*)?$")
#: The sixth column: the segment that names what a pronoun stands for, and the words.
_NAMED = re.compile(r"^(\d+)\s*:\s*(\S.*)$")

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
(Past Pres Fut Imp), Person (1 2 3), VerbForm (Inf Fin Part Conv), Mood (Ind Imp Cnd Sub), \
Role (Obj Iobj En Y Refl). For example Case=Acc|Gender=Fem|Number=Sing, or \
Gender=Masc|Number=Sing|Aspect=Perf|Tense=Past|VerbForm=Fin|Mood=Ind. Write _ when none apply.
- In French and Italian, Tense=Imp is the imperfect (il mangeait, mangiava) and Tense=Past \
on a finite verb is the simple past (il mangea, mangiò). A past participle is Tense=Past \
with VerbForm=Part.
- In French, a pronoun that is the object of a verb (le, la, l', les, lui, leur, en, y, and \
se, me, te, nous, vous where they are not the subject) has a Role: Obj, the direct object \
(je le vois); Iobj, the indirect object (je lui parle); En for en (j'en veux, il en parle); \
Y for y (j'y vais, il y pense); Refl where it stands for the subject (il se lave, je me \
souviens). Se and s' always have Role=Refl. Le, la, l', les before a verb, or after an \
imperative with a hyphen, are the pronoun, PRON and never DET: in ils la donnent, il \
l'oppose, prends-le, the pronoun is PRON with Role=Obj. Only before a noun or an adjective \
are they the article, DET with no Role; a subject pronoun has no Role either.
- For a French pronoun with the Role Obj, Iobj, En or Y, where the person or thing it \
stands for is named in the same segment or the one before it, add a sixth column: the \
number of the segment that names it, a colon, and the words that name it copied exactly as \
written, with their article (3:le livre). Leave the sixth column off where it stands for \
nothing named there, or for a whole clause.
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
    """Whether a language's words are read by this lemmatizer.

    Russian only where this machine cannot read it itself (`annotate/russian.py`, since
    2026-09-27): with the `russian` extra installed its words are read here for nothing,
    and without it they are read by the model exactly as before."""
    code = (language or "").split("-")[0].lower()
    if code == "ru":
        from . import russian

        return not russian.available()
    return code in LANGUAGES


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


def _named(field: str, number: int, texts: Sequence[str], before: str) -> tuple[int, str] | None:
    """The sixth column as a token keeps it: how many segments back, and the words as the
    text writes them. Only the segment itself or the one before, and only words that are
    there — in this segment, before the pronoun — so a phrase the model made up, or
    placed in a segment it never saw, is dropped rather than shown."""
    said = _NAMED.match(field.strip())
    if said is None:
        return None
    back = number - (int(said.group(1)) - 1)
    if back not in (0, 1) or number - back < 0:
        return None
    within = before if back == 0 else texts[number - 1]
    words = said.group(2).strip().translate(_APOSTROPHES)
    plain = within.translate(_APOSTROPHES)
    at = plain.rfind(words)
    if at < 0 and len(plain.casefold()) == len(plain):
        at = plain.casefold().rfind(words.casefold())
    if at < 0 or not _has_letters(words):
        return None
    return back, within[at : at + len(words)]


def parse(answer: str, texts: Sequence[str], language: str = "") -> list[list[Token] | None]:
    """Tokens per segment from the model's lines, placed by searching each segment's text.

    Offsets are found, never trusted: each word is looked for in its own segment from where
    the last one ended, so a word the model spelled differently from the text is dropped
    rather than put on a card over the wrong letters. The one difference forgiven is the
    apostrophe: ’ and ' place the same word, and the surface is always the text's own.
    A segment the answer never mentioned is `None`, which is different from a segment that
    was read and held no word.
    """
    lines: list[list[tuple[str, str, str, str, str]]] = [[] for _ in texts]
    mentioned = [False for _ in texts]
    for line in answer.splitlines():
        fields = [field.strip() for field in line.split("\t")]
        # The segment's number leads the line. Asked for alone, it sometimes arrives as
        # the word's place too — `3.1`, `3.2` — which lost whole batches until it was
        # read for what it leads with (measured on the French dev set, 2026-09-13).
        # Four columns is an answer that left the features off, which still has words in
        # it worth keeping; six is a French pronoun that says what it stands for.
        numbered = _NUMBER.match(fields[0]) if len(fields) in (4, 5, 6) else None
        if numbered is None:
            continue
        number = int(numbered.group(1)) - 1
        if not 0 <= number < len(texts):
            continue
        mentioned[number] = True
        surface, lemma, pos = fields[1], fields[2], fields[3].upper()
        grammar = fields[4] if len(fields) >= 5 else ""
        named = fields[5] if len(fields) == 6 else ""
        if surface and pos not in _SKIPPED:
            tag = pos if pos in UPOS else "X"
            kept = features(grammar, tag, language)
            lines[number].append((surface, lemma or surface, tag, kept, named))

    out: list[list[Token] | None] = []
    for text, words, said in zip(texts, lines, mentioned, strict=True):
        if not said:
            out.append(None)
            continue
        tokens: list[Token] = []
        cursor = 0
        plain = text.translate(_APOSTROPHES)
        folded = plain.casefold()
        for surface, lemma, pos, feats, named in words:
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
            # Only a pronoun that has a role other than the reflexive stands for something.
            refers = "Role=" in feats and "Role=Refl" not in feats and named
            tokens.append(
                Token(
                    start=at,
                    end=end,
                    surface=text[at:end],
                    lemma=lemma if pos == "PROPN" else lemma.lower(),
                    band=0,
                    pos=pos,
                    feats=feats,
                    stands_for=_named(named, len(out), texts, text[:at]) if refers else None,
                )
            )
            cursor = end
        out.append(tokens)
    return out


def _stored(tokens: list[Token]) -> list[list[Any]]:
    """A row a token, with a seventh column only on a pronoun that stands for something."""
    return [
        [t.start, t.end, t.surface, t.lemma, t.pos, t.feats or ""]
        + ([list(t.stands_for)] if t.stands_for else [])
        for t in tokens
    ]


def _restored(rows: Any, text: str) -> list[Token] | None:
    if not isinstance(rows, list):
        return None
    tokens: list[Token] = []
    for row in rows:
        if not isinstance(row, list) or len(row) not in (6, 7):
            return None
        start, end, surface, lemma, pos, feats = row[:6]
        if not (isinstance(start, int) and isinstance(end, int) and text[start:end] == surface):
            return None
        named = row[6] if len(row) == 7 else None
        stands_for = (
            (named[0], named[1])
            if isinstance(named, list)
            and len(named) == 2
            and named[0] in (0, 1)
            and isinstance(named[1], str)
            else None
        )
        tokens.append(
            Token(
                start=start,
                end=end,
                surface=surface,
                lemma=str(lemma),
                band=0,
                pos=str(pos),
                feats=str(feats) or None,
                stands_for=stands_for,
            )
        )
    return tokens


def _in_reach(tokens: list[Token], before: str | None) -> list[Token]:
    """The tokens, less any that stands for words the segment before this one does not
    have. A reading is cached by the sentence and shared by every text that has it, and
    a text is read in batches of the segments nobody has paid for, so "the one before" is
    settled against the document here rather than trusted from when it was read."""
    return [
        token
        if not token.stands_for
        or token.stands_for[0] == 0
        or (before is not None and token.stands_for[1] in before)
        else token.model_copy(update={"stands_for": None})
        for token in tokens
    ]


def tenses_apart(annotator: str) -> bool:
    """Whether an annotation's tenses were all read by a question that tells the
    imparfait from the passé simple (prompt 3 on). Where it was not — prompt 2, or a
    prompt-3 text that still holds prompt-2 readings — a finite past is either, and the
    card says "past" rather than guess."""
    found = re.search(r"model-lemma/[^/+]+/(\d+)(/with-[\d,]+)?", annotator or "")
    return found is not None and int(found.group(1)) >= 3 and not found.group(2)


def merged(older: str, newer: str) -> str:
    """The name of an annotation holding `older`'s words beside a chapter read as `newer`.

    A book bought a chapter at a time keeps its earlier chapters' words when the next is
    merged in, so where those were read before the tenses came apart, the whole is not
    apart either, and says so the way a lemmatizer that fell back does."""
    found = re.search(r"model-lemma/[^/+]+/\d+", newer)
    if found is None or tenses_apart(older) or not tenses_apart(newer):
        return newer
    return f"{newer[: found.end()]}/with-{EARLIER[0]}{newer[found.end() :]}"


class ModelLemmatizer:
    """Tokens, dictionary forms, parts of speech and grammar, read by the model and cached."""

    #: A word not in the text's language comes back tagged X, which is what lets the annotator
    #: leave English out of an Italian text (`annotate.base.foreign_runs`).
    marks_foreign = True

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
        #: The earlier prompts the last `lemmas` call took a reading from (`EARLIER`).
        self.earlier: set[int] = set()

    @property
    def name(self) -> str:
        """The provider's name, and after a call that served a segment an earlier prompt's
        reading, which prompts it took: that is a different annotation, and the page and
        the next rebuild both need to know it."""
        base = provider_name(self.model)
        if not self.earlier:
            return base
        return f"{base}/with-{','.join(str(v) for v in sorted(self.earlier, reverse=True))}"

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
        self.earlier = set()
        for segment in segments:
            if not _has_letters(segment.text):
                out[segment.id] = []
                continue
            held = self._held(segment.text, code, provider_name(self.model))
            if held is not None:
                out[segment.id] = held
            elif self.buy and (self.allowed is None or segment.id in self.allowed):
                owed.append(segment)
            else:
                # Not being bought now: an earlier question's reading rather than no words.
                for version in EARLIER:
                    held = self._held(segment.text, code, provider_name(self.model, version))
                    if held is not None:
                        out[segment.id] = held
                        self.earlier.add(version)
                        break
        if owed:
            usable, why = self.available()
            if not usable:
                raise TargumError("Cannot read the words without a key.", why)
            for segment, tokens in zip(owed, self._read(owed, code), strict=True):
                if tokens is not None:
                    out[segment.id] = tokens
        before: str | None = None
        for segment in segments:
            if segment.id in out:
                out[segment.id] = _in_reach(out[segment.id], before)
            before = segment.text
        return out

    def _held(self, text: str, code: str, provider: str) -> list[Token] | None:
        stored = self.cache.get("lemma", key(self.cache, text, code, provider))
        return _restored(stored.get("tokens"), text) if isinstance(stored, dict) else None

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
                    provider = provider_name(self.model)
                    self.cache.put(
                        "lemma",
                        key(self.cache, segment.text, code, provider),
                        {"text": segment.text, "provider": provider, "tokens": _stored(tokens)},
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
