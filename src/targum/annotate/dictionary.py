"""What the dictionary says about a Hebrew word, bought once per form and kept.

The annotator that reads Hebrew is a tagger, and a tagger answers about an occurrence.
Three of the facts a card shows are not about the occurrence at all — the dictionary
form a word is filed under, its root, and its binyan belong to the word itself, are the
same in every sentence it ever appears in, and are exactly the facts a permissively
licensed tagger is worst at. Measured against the IAHLT treebanks, `dictabert-joint`
gets the part of speech right 97% of the time and the dictionary form of a **verb** right
56% of the time, because it answers with the participle a learner met rather than the
form a dictionary lists: `זורם` where the entry is `זרם`, `מיועד` where it is `יועד`.
The binyan follows the lemma down — a participle does not spell its pattern the way a
past tense does — and the root follows the binyan, which is why the biggest gap in the
library is on the words a reader most needs the root of.

So this asks once, per distinct form, and keeps the answer. It is the same bargain
`gloss.py` already strikes and it is cached the same way: keyed on the form and the
provider, never on the text, so the second book in Hebrew is nearly free. A shelf of
half a million words has about thirty thousand distinct forms, and the arithmetic that
makes glosses affordable makes this affordable twice over — the answer is shorter.

**It never overrules a fact that was looked up.** The Tanakh is hand-tagged and
`scripture.py` reads the binyan and the root off that tagging; this is for the modern
and revival registers, where there is no such tagging to read. Where the two disagree
the hand tagging wins, because it is not a guess.

**It is not trusted because it is a model.** `annotate/score.py` scores what comes back
against the treebanks the same way it scores the tagger, and a field is adopted only
where it beats the rule it replaces. Measured on 400 treebank verbs, the first draft of
the prompt below returned the binyan for 93.7% of them and had it right 91.2% of the
time, against 8.9% coverage from the spelling rules; and its roots were right where the
rule-derived reference was wrong, which is how the nifal bug in `hebrew.py` was found.
The two instructions the measurement added — ktiv male, and the past tense behind a
participle that reads as an adjective — are the two mistakes it made systematically.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Collection
from typing import Any, NamedTuple, Protocol

from pydantic import BaseModel

from ..cache import Cache
from ..errors import ProviderError
from .canonical import bare
from .hebrew import BINYANIM

#: Forms per request. Smaller than a gloss batch because each answer carries five fields
#: rather than one, and a batch that overruns `max_tokens` loses every entry after the
#: cut rather than the last one.
BATCH_SIZE = 30

#: Tokens per form, in and out, for the estimate shown before anything is spent.
#: Measured over 650 Hebrew forms: 48 in and 74 out per form, batched thirty at a time.
#: Quoted a little high on purpose — a cap that refuses a build is better fed high than
#: low, which is the lesson `gloss.py` records from quoting half a bill.
TOKENS_PER_FORM_IN = 50
TOKENS_PER_FORM_OUT = 80

#: Sonnet, not the build's Opus default. The task is a dictionary lookup rather than a
#: judgement, it is scored before it is believed, and the model is part of the cache key
#: — so a server and a build that disagreed about it would buy the whole library twice,
#: which is the mistake `serve._gloss_word` records having made.
DICTIONARY_MODEL = "claude-sonnet-5"

#: The question, versioned, because the question is half of what produced the answer.
#: The model is in the cache key already; the prompt was not, so sharpening it returned
#: the old answers from disk and reported no change. Same lesson as the annotator's
#: name, and the same rule: move this whenever an instruction below changes what a
#: correct answer looks like, and never to force a re-buy of an unchanged one.
PROMPT_VERSION = 3

#: What a binyan may be called, so a model that answers "hitpael" or "HITPAEL" or a name
#: nobody uses cannot put a word on the card that the reader has never seen.
_BINYAN_NAMES = {name: name for name in BINYANIM.values()}
_BINYAN_NAMES.update({tag.lower(): name for tag, name in BINYANIM.items()})
_BINYAN_NAMES.update(
    {
        "paal": "פעל",
        "qal": "פעל",
        "nifal": "נפעל",
        "niphal": "נפעל",
        "piel": "פיעל",
        "pual": "פועל",
        "hifil": "הפעיל",
        "hiphil": "הפעיל",
        "hufal": "הופעל",
        "hophal": "הופעל",
        "hitpael": "התפעל",
        "hithpael": "התפעל",
    }
)

Progress = Callable[[int], None]


class _Entry(BaseModel):
    form: str
    dictionary_form: str = ""
    part_of_speech: str = ""
    root: str = ""
    binyan: str = ""
    certain: bool = True


class _Batch(BaseModel):
    entries: list[_Entry]


class Entry(NamedTuple):
    """Everything the dictionary says about one form.

    Every field may be empty, and an empty field means "not answered" rather than "no".
    A root nobody could give is a gap the Pealim link fills; a root invented to fill the
    column is a lie told with confidence, which is the bargain `hebrew.py` opens by
    striking and this one keeps.
    """

    #: The form a dictionary would file this word under. For a verb the third-person
    #: masculine singular past, which is what every Hebrew dictionary and the Pealim link
    #: expect, and what the treebanks record.
    dictionary_form: str = ""
    part: str = ""
    #: The three or four letters, unpointed, written without separators. The reader puts
    #: the maqafs in.
    root: str = ""
    #: The binyan under its Hebrew name, as `BINYANIM` spells it.
    binyan: str = ""
    #: Whether the model said it was sure. An uncertain answer is kept — it is evidence —
    #: and is not used to overrule anything.
    certain: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "dictionary_form": self.dictionary_form,
            "part_of_speech": self.part,
            "root": self.root,
            "binyan": self.binyan,
            "certain": self.certain,
        }

    @property
    def empty(self) -> bool:
        return not (self.dictionary_form or self.root or self.binyan or self.part)


def provider_name(model: str = DICTIONARY_MODEL, version: int = PROMPT_VERSION) -> str:
    return f"anthropic/{model}/dictionary-{version}"


class DictionaryProvider(Protocol):
    @property
    def name(self) -> str: ...

    def look_up(
        self, forms: list[str], on_progress: Progress | None = None
    ) -> dict[str, Entry]: ...


SYSTEM = """You are compiling a Hebrew dictionary index for a reading tool.

For each Hebrew form you are given, return the facts a dictionary would carry about it.
The form arrives unpointed, as it was written, and is a form some annotator produced —
it may already be the dictionary form, or it may be a participle, a plural, or a
misreading that is not a Hebrew word at all.

- Return the form exactly as it was given, in `form`.
- `dictionary_form`: the entry a Hebrew dictionary files this word under, unpointed.
  For a verb that is the third-person masculine singular past — זרם for זורם, יועד for
  מיועד, רצה for רוצה. For a noun it is the singular; for an adjective the masculine
  singular. Where the form given is already the dictionary form, repeat it.
- Write it in ktiv male, the spelling used without vowel points: ביקש not בקש, ביצע not
  בצע, איפשר not אפשר, חידש not חדש, ליווה not לווה. A piel or pual verb writes the yod.
- A passive participle that has come to be used as an adjective — בדוק, ידוע, טמון,
  מעורב — is still a form of its verb, and its dictionary form is that verb's past
  tense: בדק, ידע, טמן, עורב. Give the adjective itself only where no verb stands
  behind it.
- A passive participle belongs to the *passive* verb, not the active one it was built
  from. מעורב is עורב and not עירב; מסולק is סולק and not סילק; מחולק is חולק, משוער is
  שוער, מבוסס is בוסס, מאושר is אושר. The same holds for הופעל: מוצג is הוצג.
- `part_of_speech`: one of noun, verb, adjective, adverb, preposition, pronoun,
  conjunction, particle, name, other. A participle used as an adjective is a verb.
- `root`: for a verb, and for a noun or adjective transparently built on a verbal root,
  the three or four root letters with nothing between them. Write the last letter in its
  final form. Leave it empty where the root is genuinely disputed or the word has none —
  a loanword, a name, a particle. Do not invent a root to fill the field.
- `binyan`: for a verb only, one of פעל, נפעל, פיעל, פועל, הפעיל, הופעל, התפעל. Leave it
  empty for anything that is not a verb, and for the rare stems outside those seven.
  Read the pattern off the dictionary form you gave, not off the form you were handed:
  התחיל is הפעיל and not התפעל, and איפשר is פיעל and not הפעיל.
- A פועל verb built on a root whose first letter is י is written with וּ in that place
  and looks exactly like הופעל. It is not: יוצר, יוצג, יועד, יושם, יובש and יוחד are
  פועל, the passives of ייצר, ייצג, ייעד, יישם, ייבש and ייחד. Ask what the active verb
  is — if it is פיעל, the passive is פועל.
- `certain`: false where the unpointed spelling is genuinely ambiguous and you are
  choosing between real readings, true otherwise.
- If the form is not a Hebrew word — a wordpiece, a fragment, a foreign string — return
  it with every field empty rather than guessing."""


def entries_for(forms: list[str]) -> str:
    return "\n".join(f"form: {form}" for form in forms)


def clean_binyan(said: str) -> str:
    """A binyan the reader already has a name for, or nothing."""
    return _BINYAN_NAMES.get((said or "").strip().lower(), "")


def clean_root(said: str, form: str = "") -> str:
    """Three or four Hebrew letters, or nothing.

    Separators are taken out because a model asked for a root writes it the way a
    grammar book does — ז־ר־ם, ז.ר.ם, ז ר ם — and the reader puts the maqafs in itself.
    Anything that is not letters, or is the wrong length, is dropped rather than shown.
    """
    letters = "".join(ch for ch in (said or "") if "א" <= ch <= "ת")
    if len(letters) not in (3, 4):
        return ""
    return letters


def clean_form(said: str, form: str = "") -> str:
    """The dictionary form, or nothing where the answer is not one word of Hebrew."""
    said = (said or "").strip()
    if not said or " " in said or not bare(said):
        return ""
    return said


class AnthropicDictionary:
    """The dictionary from the same provider that does translation and glosses."""

    def __init__(self, model: str | None = None, *, batch_size: int = BATCH_SIZE) -> None:
        from ..translate.anthropic_provider import AnthropicProvider

        self._provider = AnthropicProvider(model or DICTIONARY_MODEL)
        self.model = self._provider.model
        self.batch_size = batch_size

    @property
    def name(self) -> str:
        return provider_name(self.model)

    @property
    def spent(self) -> Any:
        return self._provider.spent

    def available(self) -> tuple[bool, str]:
        return self._provider.available()

    def look_up(self, forms: list[str], on_progress: Progress | None = None) -> dict[str, Entry]:
        import anthropic

        from ..translate.anthropic_provider import output_config

        out: dict[str, Entry] = {}
        for start in range(0, len(forms), self.batch_size):
            batch = forms[start : start + self.batch_size]
            try:
                response = self._provider.client().messages.parse(
                    model=self.model,
                    max_tokens=8000,
                    system=SYSTEM,
                    messages=[{"role": "user", "content": entries_for(batch)}],
                    output_format=_Batch,
                    **output_config(self.model, "low"),
                )
            except anthropic.APIStatusError as exc:
                raise ProviderError(
                    f"Anthropic API error {exc.status_code} while reading the dictionary.",
                    exc.message,
                ) from exc
            self._provider.spent.add(
                self.model or "",
                int(getattr(response.usage, "input_tokens", 0) or 0),
                int(getattr(response.usage, "output_tokens", 0) or 0),
            )
            parsed: Any = response.parsed_output
            if isinstance(parsed, _Batch):
                wanted = set(batch)
                for said in parsed.entries:
                    if said.form not in wanted:
                        continue
                    out[said.form] = Entry(
                        dictionary_form=clean_form(said.dictionary_form),
                        part=said.part_of_speech.strip().lower(),
                        root=clean_root(said.root),
                        binyan=clean_binyan(said.binyan),
                        certain=bool(said.certain),
                    )
            if on_progress:
                on_progress(len(batch))
        return out


def key(cache: Cache, form: str, provider: str) -> str:
    """One place the cache key is spelled, so pricing and paying cannot disagree."""
    return cache.key("dictionary", form=form, language="he", provider=provider)


def cached(form: str, provider: str, cache: Cache | None = None) -> Entry | None:
    """What is already held for a form, or None. Never spends."""
    cache = cache or Cache()
    stored = cache.get("dictionary", key(cache, form, provider))
    if not isinstance(stored, dict):
        return None
    return Entry(
        dictionary_form=str(stored.get("dictionary_form", "")),
        part=str(stored.get("part_of_speech", "")),
        root=str(stored.get("root", "")),
        binyan=str(stored.get("binyan", "")),
        certain=bool(stored.get("certain", True)),
    )


def unpaid(forms: Collection[str], provider: str, cache: Cache | None = None) -> list[str]:
    """The forms nobody has looked up yet, so a price is quoted net of the cache."""
    cache = cache or Cache()
    return [form for form in forms if cache.get("dictionary", key(cache, form, provider)) is None]


def estimate(form_count: int, model: str = DICTIONARY_MODEL) -> float:
    from ..translate.anthropic_provider import DEFAULT_MODEL, PRICES

    in_price, out_price = PRICES.get(model, PRICES[DEFAULT_MODEL])
    return (
        form_count * TOKENS_PER_FORM_IN * in_price + form_count * TOKENS_PER_FORM_OUT * out_price
    ) / 1_000_000


def held(cache: Cache | None = None, provider: str = "") -> dict[str, Entry]:
    """Every form this provider has already answered, read off the cache directory.

    A build does not know which forms a text will produce until it has been annotated,
    and annotating is what needs the answers — so the whole of what has been bought is
    handed in rather than a list looked up form by form. It is a few tens of thousands
    of small files at worst, and reading them is local.

    The cache stores what was asked as well as what came back, so a form that was asked
    about and declined is skipped here rather than counted as an answer.
    """
    cache = cache or Cache()
    provider = provider or provider_name()
    out: dict[str, Entry] = {}
    root = cache.root / "dictionary"
    if not root.is_dir():
        return out
    for path in root.glob("*/*.json"):
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(stored, dict):
            continue
        form = str(stored.get("form", ""))
        if not form or stored.get("provider") != provider:
            continue
        entry = Entry(
            dictionary_form=str(stored.get("dictionary_form", "")),
            part=str(stored.get("part_of_speech", "")),
            root=str(stored.get("root", "")),
            binyan=str(stored.get("binyan", "")),
            certain=bool(stored.get("certain", True)),
        )
        if not entry.empty:
            out[form] = entry
    return out


def for_language(language: str, cache: Cache | None = None) -> dict[str, Any]:
    """The `Annotator` keyword arguments for a language, from what has been bought.

    Every place that makes an `Annotator` calls this, and that is the point: a rebuild
    that read the dictionary while a repair did not would give one paragraph a different
    annotator name from the file it belongs to, and the whole document would be read
    again on the next build to resolve a difference nobody asked for.

    Cache only. Nothing here reaches the network or spends; `targum dictionary` does the
    buying, once, and this picks up whatever is there.
    """
    if language.split("-")[0].lower() != "he":
        return {}
    provider = provider_name()
    found = held(cache=cache, provider=provider)
    return {"dictionary": found, "dictionary_name": provider} if found else {}


def build(
    forms: Collection[str],
    provider: DictionaryProvider,
    *,
    cache: Cache | None = None,
    buy: bool = True,
    on_progress: Progress | None = None,
) -> tuple[dict[str, Entry], int]:
    """Every form's entry, from the cache and then from the provider.

    Returns what is held and how many forms are still unbought — so a caller that passed
    `buy=False` learns the price of finishing without paying it, exactly as
    `gloss.build_glossary` does.
    """
    cache = cache or Cache()
    held: dict[str, Entry] = {}
    missing: list[str] = []
    for form in dict.fromkeys(forms):
        found = cached(form, provider.name, cache)
        if found is None:
            missing.append(form)
        elif not found.empty:
            held[form] = found
    if not buy or not missing:
        return held, len(missing)

    bought = provider.look_up(missing, on_progress)
    for form in missing:
        entry = bought.get(form, Entry())
        # A form the provider declined is written too, and written empty. Otherwise it is
        # asked again on every build, and a word that is not a word never stops costing.
        cache.put(
            "dictionary",
            key(cache, form, provider.name),
            # The form and the provider are written into the value as well as hashed
            # into the key, because `held` reads the directory rather than asking about
            # a form it does not yet know it wants.
            entry.as_dict() | {"form": form, "provider": provider.name},
        )
        if not entry.empty:
            held[form] = entry
    return held, 0
