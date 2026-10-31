"""Topics: which of sixteen topics a Hebrew lemma belongs to (targum-internal#609).

David approved the list on 2026-10-30, with the plan at
`~/targum-team/ling-he/keep/topic-tagging-2026-10-30.md`. A model tags a lemma from the
lemma, its pointed form, its part of speech and its cached English gloss, never from a
sentence, and two models do it independently so that where they disagree is where ling-he
looks. The lemmas come only from the language tables (`tables.Store.top`), which only
public texts reach (`tables.public_text`): never from `word` rows or the gloss cache,
because both hold private imports.

The result is a private lexicon, `~/.targum/topics.json`, keyed by DICTA lemma:

    {"version": "topics/1", "topics": [...codes...], "lemmas": {lemma: [codes]}}

It is never in the repository. This module is the open half: the list, the prompt, the
answer's shape, the price, and the share a reader's bar would show. The paid run is
`scripts/tag_topics.py`; `targum topics share` prints the shares for the synthetic
readers only.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .tables import Store

#: The closed list, in the order a page would draw it. Adding or splitting one is
#: `topics/2`.
TOPICS: dict[str, str] = {
    "everyday": "Everyday life",
    "family": "Family & home",
    "people": "People & feelings",
    "food": "Food & drink",
    "money": "Money & shopping",
    "travel": "Travel & transport",
    "work": "Work & business",
    "school": "School & study",
    "health": "Health & body",
    "culture": "Free time & culture",
    "nature": "Nature & weather",
    "politics": "Politics & government",
    "law": "Law & crime",
    "security": "Security & the army",
    "science": "Science & technology",
    "religion": "Religion & tradition",
}

#: No topic: abstract and all-purpose words. Exclusive, and it gets no bar.
GENERAL = "general"

#: The most topics one lemma carries.
MOST = 2

VERSION = "topics/1"
#: The prompt's own version, apart from the list's. Prompt 2 (2026-10-30, after pilot 1
#: scored 87% precision against ling-he's blind gold set): the commonest modern sense over
#: the gloss, ling-he's sharper Religion and Science definitions, people-nouns in People &
#: feelings, and the screen (`screen`) before anything is sent.
#: Prompt 3 (2026-10-31, after pilot 2's agreed errors were זמן and רגע tagged Everyday
#: life and פרסם and פורסם tagged Free time & culture): a rule and worked examples that keep
#: abstract time words and verbs of publishing, reporting and announcing `general`, beside
#: the clock-and-calendar nouns and the press's own nouns that do keep their topic. The
#: examples are new words, none from ling-he's first gold set, so it is not taught the test.
PROMPT_VERSION = "prompt/3"

#: The modern registers a topic's words are drawn from and weighed by, and the one
#: Religion & tradition adds for the words the modern registers do not hold.
MODERN = ("news", "conversation", "literature")
BIBLE = "bible"

#: The lexicon that ships, once it exists (targum-internal#607).
LEXICON = Path.home() / ".targum" / "topics.json"
#: Where a run keeps its raw answers and review files. Laptop-only.
RESEARCH = Path.home() / ".targum" / "research" / "topics"


# --- What a page may show ---------------------------------------------------------------

#: The topics a page may draw a bar for: those whose agreed tags passed ling-he's blind
#: gold set (pilot 3, 2026-10-31). David, 2026-10-31: ship the topics that pass now and
#: fix the rest. The other eleven are tagged and kept in the lexicon, but no bar shows
#: them until they pass (`passes_show`). The lexicon file carries the same list as
#: `shown`, with `SHOWN_RULE`; a page reads it through `load_shown`, so a lexicon whose
#: tags were re-scored can widen the list without a code change, and one without the
#: field falls back to this.
SHOWN: tuple[str, ...] = ("food", "security", "school", "family", "law")

#: A topic moves into `shown` only when its agreed tags reach this precision and recall
#: against at least this many gold rows (point estimates; the Wilson interval is reported
#: beside them).
SHOW_PRECISION = 0.90
SHOW_RECALL = 0.80
SHOW_GOLD = 15
SHOWN_RULE = (
    f"A bar is drawn only for a topic in `shown`. A topic joins `shown` only when its agreed"
    f" tags score precision >= {SHOW_PRECISION:.0%} and recall >= {SHOW_RECALL:.0%} on at"
    f" least {SHOW_GOLD} rows of ling-he's blind gold set (David, 2026-10-31)."
)


def passes_show(gold: int, precision: float | None, recall: float | None) -> bool:
    """Whether a topic's gold score lets it into `shown`."""
    return (
        gold >= SHOW_GOLD
        and precision is not None
        and recall is not None
        and precision >= SHOW_PRECISION
        and recall >= SHOW_RECALL
    )


def load_shown(file: Path | None = None) -> tuple[str, ...]:
    """The topics a page may draw for the lexicon at `file`: its `shown` list, in the
    order of `TOPICS`, or `SHOWN` where the file has none. Nothing at all where there is
    no lexicon, since there is nothing to draw."""
    file = file or LEXICON
    try:
        held = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    listed = held.get("shown") if isinstance(held, dict) else None
    if not isinstance(listed, list):
        return SHOWN
    return tuple(code for code in TOPICS if code in {str(one) for one in listed})


def wilson(hits: int, total: int, z: float = 1.96) -> tuple[float, float] | None:
    """The Wilson score interval for `hits` out of `total` (95% by default), or None for
    no trials. Better than the normal interval at the small counts a topic's gold has."""
    if total <= 0:
        return None
    p = hits / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def alternatives(note: str) -> tuple[str, ...]:
    """The other labels a gold note names as reasonable, in the order it names them.

    Read: every topic code (or `general`) on either side of an "or" ("feeling; or
    health", "or law (oath in court), religion", "or money/culture", "science or culture
    also defensible"), a code in brackets after a word that is not one ("submission
    (school) or serving (food)"), and "X would be defensible" or "could be X". A phrase
    stops at the first word that is not a code. ling-he confirms what this reads; the
    caller drops the row's own labels."""
    codes = {*TOPICS, GENERAL}
    found: list[str] = []

    def take(word: str) -> bool:
        word = word.strip(".;:'\"()").lower()
        if word not in codes:
            return False
        if word not in found:
            found.append(word)
        return True

    text = note.lower()
    for match in re.finditer(r"\bor\b", text):
        before = re.findall(r"[\w()]+", text[: match.start()])
        if before:
            take(before[-1])
        words = re.findall(r"\([^)]*\)|[^\s/,]+", text[match.end() :])
        for i, word in enumerate(words):
            if word in {"and", "also"}:
                continue
            if word.startswith("("):
                continue
            if take(word):
                continue
            # A word that is not a code, with its code in brackets after it.
            if i + 1 < len(words) and words[i + 1].startswith("("):
                take(words[i + 1])
            break
    for match in re.finditer(r"(\w+) would be defensible|could be (\w+)", text):
        take(match.group(1) or match.group(2))
    return tuple(found)


# --- Prices -----------------------------------------------------------------------------

#: USD per million tokens, (input, output), from the claude-api skill's model table
#: (cached 2026-10-06). The canonical page is
#: https://platform.claude.com/docs/en/about-claude/pricing.
PRICES: dict[str, tuple[float, float]] = {
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-opus-5-5": (4.0, 20.0),
}
MODELS = tuple(PRICES)
#: The Batches API halves every token.
BATCH_DISCOUNT = 0.5
#: A cache read costs a tenth of an input token and a five-minute cache write a quarter
#: more than one.
CACHE_READ = 0.1
CACHE_WRITE = 1.25


@dataclass
class Usage:
    """What one model's answers cost, in tokens and dollars."""

    input_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    output_tokens: int = 0
    #: Output tokens that were not the answer's text: the thinking, which is billed as
    #: output and never shown. Measured as output minus the counted text.
    thinking_tokens: int = 0
    requests: int = 0

    def add(self, other: Usage) -> None:
        for name, value in asdict(other).items():
            setattr(self, name, getattr(self, name) + value)


def cost(model: str, usage: Usage, *, batch: bool) -> float:
    """What `usage` costs on `model`, in dollars."""
    in_price, out_price = PRICES[model]
    factor = BATCH_DISCOUNT if batch else 1.0
    dollars = (
        usage.input_tokens * in_price
        + usage.cache_write_tokens * in_price * CACHE_WRITE
        + usage.cache_read_tokens * in_price * CACHE_READ
        + usage.output_tokens * out_price
    ) / 1_000_000
    return dollars * factor


def worst_case(model: str, input_tokens: int, max_tokens: int, *, batch: bool) -> float:
    """The most one request can cost: every input token uncached and written to the
    cache, and every output token up to `max_tokens` spent. A cap checked against this
    can never be passed."""
    in_price, out_price = PRICES[model]
    factor = BATCH_DISCOUNT if batch else 1.0
    return (input_tokens * in_price * CACHE_WRITE + max_tokens * out_price) / 1_000_000 * factor


# --- The lemmas -------------------------------------------------------------------------


@dataclass(frozen=True)
class Lemma:
    """One lemma as a model is shown it, and the count that ranked it."""

    lemma: str
    pos: str
    #: The form its meaning is filed under (`Token.glossed_as`): the lemma with its part
    #: of speech where the spelling is shared.
    glossed_as: str
    gloss: str
    #: The pointed citation form the gloss gave, where it gave one (verbs, mostly).
    pointed: str
    count: int
    register: str
    #: The commonest modern sense, in a few English words, where the gloss gives a rarer
    #: one first (`hints`), with the senses the gloss cache holds under the lemma's other
    #: keys. Empty for nearly every lemma, and then nothing about the request changes.
    hint: str = ""


def glossed_as(lemma: str, pos: str) -> str:
    """The key the gloss cache files a lemma under, from the lemma and its part of
    speech alone: `Token.glossed_as` without a scripture headword."""
    from .models import POS_MARKS, SPLIT_BY_POS, VERB_MARK

    if pos == "VERB":
        return lemma + VERB_MARK
    if lemma in SPLIT_BY_POS and pos in POS_MARKS:
        return lemma + POS_MARKS[pos]
    return lemma


def ranked(store: Store, registers: Sequence[str], limit: int) -> list[tuple[str, int]]:
    """The commonest content lemmas over `registers`, summed, from the tables alone.

    `Store.top` already leaves out function words, names and numbers
    (`tables.weights.weighed`), exactly as a yardstick does.
    """
    from .tables.words import WORDS

    totals: dict[str, int] = {}
    for register in registers:
        # Each register's own top, deep enough that the sum's top `limit` is whole.
        for key, n in store.top(WORDS, register, limit=limit * 4):
            totals[key] = totals.get(key, 0) + n
    return sorted(totals.items(), key=lambda item: (-item[1], item[0]))[:limit]


def universe(
    store: Store,
    *,
    modern: int,
    bible: int = 0,
    gloss: Any = None,
    registers: Sequence[str] = MODERN,
) -> tuple[list[Lemma], list[str]]:
    """The lemmas to tag, commonest first, and the ones passed over for want of a gloss.

    The `modern` commonest lemmas over `registers` (the modern yardstick registers unless
    a pilot says otherwise) that have a gloss, then the `bible` commonest bible lemmas
    with a gloss that are not already in. `gloss(glossed_as) -> (gloss, pointed) | None`
    reads the gloss cache; it is only ever asked about a lemma the tables gave, so
    nothing a reader imported can enter the list through it.
    """
    gloss = gloss or cached_gloss
    lemmas: list[Lemma] = []
    missing: list[str] = []
    seen: set[str] = set()
    for chosen, label, want in ((registers, "modern", modern), ((BIBLE,), BIBLE, bible)):
        if want <= 0:
            continue
        candidates = [(k, n) for k, n in ranked(store, chosen, want * 2 + 50) if k not in seen]
        took = _glossed(store, candidates, label, want, gloss, missing)
        lemmas += took
        seen.update(one.lemma for one in took)
    return lemmas, missing


def _glossed(
    store: Store,
    candidates: Sequence[tuple[str, int]],
    register: str,
    want: int,
    gloss: Any,
    missing: list[str],
) -> list[Lemma]:
    from .tables.words import WORDS

    variants = store.variants(WORDS, [key for key, _ in candidates])
    out: list[Lemma] = []
    for key, n in candidates:
        if len(out) >= want:
            break
        pos = _main_variant(variants.get(key, {}))
        filed = glossed_as(key, pos)
        # A verb glossed before 2026-09-08 is filed under the bare lemma.
        held = gloss(filed) or (gloss(key) if filed != key else None)
        if held is None:
            missing.append(key)
            continue
        out.append(Lemma(key, pos, filed, held[0], held[1], n, register))
    return out


def _main_variant(counts: Mapping[str, int]) -> str:
    from .tables.weights import weighed

    kept = {pos: n for pos, n in counts.items() if weighed("x", pos)}
    if not kept:
        return ""
    return sorted(kept.items(), key=lambda item: (-item[1], item[0]))[0][0]


# --- The screen -------------------------------------------------------------------------

#: A lemma is never tagged when, over every register, at least this share of its counts
#: carry a closed-class part of speech (`tables.weights.EXCLUDED`), a number's, or a
#: name's. `Store.top` weighs row by row, so אל, counted ADP 5,697 times and NOUN 247,
#: reaches the list on its NOUN rows; the screen asks the lemma as a whole. A name needs a
#: larger share than the rest, because DICTA tags אבא PROPN 64% of the time.
FUNCTION_SHARE = 0.5
NUMBER_SHARE = 0.5
NAME_SHARE = 0.75

#: One-letter clitics a lemmatiser leaves on a noun (הפועל, בעיר): the article and the
#: three prepositions written as a prefix. ו and the rest are left alone, because a real
#: word starts with them too often (ועדה, מספר).
CLITICS = frozenset("הבלכ")
_NOUNS = frozenset({"NOUN", "PROPN"})


def screened(
    lemma: str, variants: Mapping[str, int], bare: Mapping[str, int] | None = None
) -> str | None:
    """Why one lemma is left out before tagging, or None where it is tagged.

    `variants` is how often the lemma was counted under each part of speech over every
    register (`Store.variants`), and `bare` the same for the lemma without its first
    letter, where that letter is a clitic. The reasons: a one-letter lemma (a prefix the
    lemmatiser cut loose), a function word, a number, a name, and a noun whose first
    letter is a clitic on a noun the tables count at least as often (a lemmatisation
    error: הפועל beside פועל).
    """
    from .tables.weights import EXCLUDED

    if len(lemma) <= 1:
        return "one letter"
    total = sum(variants.values())
    if total:
        if sum(n for pos, n in variants.items() if pos in EXCLUDED) / total >= FUNCTION_SHARE:
            return "function word"
        if variants.get("NUM", 0) / total >= NUMBER_SHARE:
            return "number"
        if variants.get("PROPN", 0) / total >= NAME_SHARE:
            return "name"
    if lemma[0] in CLITICS and len(lemma) >= 4 and bare and total:
        main = max(variants.items(), key=lambda item: (item[1], item[0]))[0]
        bare_main = max(bare.items(), key=lambda item: (item[1], item[0]))[0]
        if main in _NOUNS and bare_main in _NOUNS and sum(bare.values()) >= total:
            return "clitic prefix"
    return None


def screen(store: Store, lemmas: Sequence[Lemma]) -> tuple[list[Lemma], list[dict[str, str]]]:
    """The lemmas worth tagging, in order, and the ones left out with the reason, from
    the tables' counts alone: nothing is sent for a function word, a number, a name or a
    lemmatisation error."""
    from .tables.words import WORDS

    variants = store.variants(WORDS, [one.lemma for one in lemmas])
    bares = store.variants(
        WORDS, [one.lemma[1:] for one in lemmas if one.lemma[:1] in CLITICS and len(one.lemma) >= 4]
    )
    kept: list[Lemma] = []
    dropped: list[dict[str, str]] = []
    for one in lemmas:
        why = screened(one.lemma, variants.get(one.lemma, {}), bares.get(one.lemma[1:]))
        if why is None:
            kept.append(one)
        else:
            dropped.append({"lemma": one.lemma, "pos": one.pos, "gloss": one.gloss, "why": why})
    return kept, dropped


def cached_gloss(filed: str) -> tuple[str, str] | None:
    """The English gloss and pointed citation the cache holds for a filed form, or None.
    Never spends."""
    from .annotate.gloss import GLOSS_MODEL, gloss_provider_name
    from .annotate.gloss import cached_gloss as held

    sense = held(filed, "he", "en", gloss_provider_name(GLOSS_MODEL))
    if sense is None:
        return None
    return sense.gloss, sense.citation


# --- The prompt and the answer ----------------------------------------------------------

_DEFINITIONS = {
    "everyday": "routine, time and dates, clothes, the phone and messages, errands, the"
    " ordinary objects and actions of a day that belong to no narrower topic",
    "family": "family members and relatives, relationships at home, marriage and children,"
    " the house and its rooms, furniture, chores, renting a flat",
    "people": "character, emotions and feelings, opinions, friendship, love, appearance,"
    " how people treat each other, and words for people as such (man, woman, guy, girl)",
    "food": "ingredients, dishes, cooking, eating and drinking, meals, restaurants, the market",
    "money": "prices, paying, the bank, bills, debts, shops and buying, saving",
    "travel": "the city and its streets, directions, buses, trains, cars, flights, hotels,"
    " named kinds of places one travels to",
    "work": "jobs and professions, the office, employers and employees, companies, trade,"
    " industry, the economy",
    "school": "school, university, teachers and students, learning, exams, reading and"
    " writing as study, language and grammar",
    "health": "the body and its parts, illness and injury, doctors, the clinic and"
    " hospital, medicine, fitness",
    "culture": "hobbies, sport, music, film, theatre, art, books as leisure, television, the"
    " press and media content, holidays as leisure",
    "nature": "animals, plants, landscape, the sea, the sky, climate and weather, the environment",
    "politics": "the state, the Knesset, government and ministries, elections, parties,"
    " diplomacy, public services, official forms and bureaucracy",
    "law": "courts, judges, lawyers, police, crime and punishment, rights, laws as legal"
    " instruments, contracts",
    "security": "the army, soldiers and reserve duty, war, weapons, attacks and terror,"
    " defence, security services",
    # ling-he's definitions (topic-gold-notes-2026-10-30), word for word.
    "science": "words for the sciences, research and engineering as fields, and for"
    " computing as a field or system (software, data, network, algorithm); everyday devices"
    " and their use (phone, screen, message, app) are Everyday life, and media content is"
    " Free time & culture",
    "religion": "words whose main modern sense is religious practice, belief or institution"
    " — God, prayer, Torah, commandments, the Temple and priesthood, synagogue, rabbis,"
    " holidays as observance, kashrut — not words that are religious only in a secondary or"
    " biblical sense",
}

#: Worked examples: (lemma, pointed, part of speech, gloss, answer). They teach the
#: main-sense rule, `general`, and when two topics are right.
EXAMPLES: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    ("שולחן", "שֻׁלְחָן", "NOUN", "table", ("family",)),
    ("לחם", "לֶחֶם", "NOUN", "bread", ("food",)),
    ("מסעדה", "מִסְעָדָה", "NOUN", "restaurant", ("food",)),
    ("אכל", "לֶאֱכֹל", "VERB", "to eat", ("food",)),
    ("טעים", "טָעִים", "ADJ", "tasty, delicious", ("food",)),
    ("אמא", "אִמָּא", "NOUN", "mom, mother", ("family",)),
    ("דירה", "דִּירָה", "NOUN", "apartment, flat", ("family",)),
    ("שכירות", "שְׂכִירוּת", "NOUN", "rent, renting", ("family", "money")),
    ("כעס", "לִכְעֹס", "VERB", "to be angry", ("people",)),
    ("חבר", "חָבֵר", "NOUN", "friend; member", ("people",)),
    ("עצוב", "עָצוּב", "ADJ", "sad", ("people",)),
    ("כסף", "כֶּסֶף", "NOUN", "money; silver", ("money",)),
    ("שילם", "לְשַׁלֵּם", "VERB", "to pay", ("money",)),
    ("בנק", "בַּנְק", "NOUN", "bank", ("money",)),
    ("אוטובוס", "אוֹטוֹבּוּס", "NOUN", "bus", ("travel",)),
    ("רחוב", "רְחוֹב", "NOUN", "street", ("travel",)),
    ("טיסה", "טִיסָה", "NOUN", "flight", ("travel",)),
    ("משרד", "מִשְׂרָד", "NOUN", "office; ministry", ("work", "politics")),
    ("משכורת", "מַשְׂכֹּרֶת", "NOUN", "salary", ("work", "money")),
    ("עבד", "לַעֲבֹד", "VERB", "to work", ("work",)),
    ("מורה", "מוֹרֶה", "NOUN", "teacher", ("school",)),
    ("מבחן", "מִבְחָן", "NOUN", "exam, test", ("school",)),
    ("רופא", "רוֹפֵא", "NOUN", "doctor, physician", ("health",)),
    ("ראש", "רֹאשׁ", "NOUN", "head; leader, chief", ("health",)),
    ("כאב", "כְּאֵב", "NOUN", "pain, ache", ("health",)),
    ("כדורגל", "כַּדּוּרֶגֶל", "NOUN", "football, soccer", ("culture",)),
    ("שיר", "שִׁיר", "NOUN", "song; poem", ("culture",)),
    ("גשם", "גֶּשֶׁם", "NOUN", "rain", ("nature",)),
    ("עץ", "עֵץ", "NOUN", "tree; wood", ("nature",)),
    ("בחירות", "בְּחִירוֹת", "NOUN", "elections", ("politics",)),
    ("ממשלה", "מֶמְשָׁלָה", "NOUN", "government", ("politics",)),
    ("משטרה", "מִשְׁטָרָה", "NOUN", "police", ("law",)),
    ("בית משפט", "בֵּית מִשְׁפָּט", "NOUN", "court of law", ("law",)),
    ("צבא", "צָבָא", "NOUN", "army", ("security",)),
    ("מילואים", "מִלּוּאִים", "NOUN", "reserve duty", ("security",)),
    ("מחשב", "מַחְשֵׁב", "NOUN", "computer", ("science",)),
    ("מחקר", "מֶחְקָר", "NOUN", "research", ("science",)),
    ("התפלל", "לְהִתְפַּלֵּל", "VERB", "to pray", ("religion",)),
    ("שבת", "שַׁבָּת", "NOUN", "Sabbath, Saturday", ("religion", "everyday")),
    ("כהן", "כֹּהֵן", "NOUN", "priest", ("religion",)),
    ("דבר", "דָּבָר", "NOUN", "thing; word, matter", (GENERAL,)),
    ("חשוב", "חָשׁוּב", "ADJ", "important", (GENERAL,)),
    ("היה", "לִהְיוֹת", "VERB", "to be", (GENERAL,)),
    ("גדול", "גָּדוֹל", "ADJ", "big, great", (GENERAL,)),
    ("בעיה", "בְּעָיָה", "NOUN", "problem", (GENERAL,)),
    ("אמר", "לוֹמַר", "VERB", "to say", (GENERAL,)),
    ("יום", "יוֹם", "NOUN", "day", ("everyday",)),
    ("שעה", "שָׁעָה", "NOUN", "hour", ("everyday",)),
    ("טלפון", "טֶלֶפוֹן", "NOUN", "telephone", ("everyday",)),
    # Prompt 3: time on the clock and the calendar is Everyday life; time as such is not.
    ("חודש", "חֹדֶשׁ", "NOUN", "month", ("everyday",)),
    ("תקופה", "תְּקוּפָה", "NOUN", "period, era", (GENERAL,)),
    ("פעם", "פַּעַם", "NOUN", "time, occasion; once", (GENERAL,)),
    ("עתיד", "עָתִיד", "NOUN", "future", (GENERAL,)),
    # Prompt 3: the press and what it makes is Free time & culture; publishing, reporting
    # and announcing are said of every topic, so they are `general`.
    ("ערוץ", "עָרוּץ", "NOUN", "channel (TV); channel, course", ("culture",)),
    ("הודיע", "לְהוֹדִיעַ", "VERB", "to announce, to inform", (GENERAL,)),
    ("ציטט", "לְצַטֵּט", "VERB", "to quote", (GENERAL,)),
    ("חשף", "לַחְשֹׂף", "VERB", "to reveal, to expose", (GENERAL,)),
)


def system_prompt() -> str:
    """The same on every request, so it is cached: the list, the rules, the examples."""
    topics = "\n".join(
        f"- `{code}` ({name}): {_DEFINITIONS[code]}." for code, name in TOPICS.items()
    )
    examples = "\n".join(
        f'- {lemma} ({pointed}, {pos}) "{gloss}" -> {", ".join(answer)}'
        for lemma, pointed, pos, gloss, answer in EXAMPLES
    )
    return f"""You tag Modern Hebrew dictionary words with topics, for a reading app's \
vocabulary map. A learner sees one bar per topic: the share of that topic's words they \
know. A bar is only useful if the words in it clearly belong there.

For each word you get an id, the unpointed lemma, a pointed form when there is one, the \
part of speech, and an English gloss. Tag the word's commonest sense in Modern Hebrew \
today. The gloss is a hint, not the sense: it may give a biblical or rarer sense, or one \
word of a spelling that is far commoner as another. פה is commonest "here", not "mouth"; \
אתר "website"; עמוד "page"; גר "lives". The part of speech can be wrong too.

The topics:
{topics}
- `{GENERAL}`: no topic. Abstract and all-purpose words, words used across many topics, \
and anything whose main sense belongs to no topic above.

Rules:
1. Tag the commonest modern sense, whatever the gloss gives first. A word is in a topic \
only when a teacher building that topic's word list would put it there. שולחן (table) is Family & \
home, not Food & drink.
2. Give one topic, or two when the word belongs squarely to both, or when the spelling \
has two senses in different topics and both are common in Modern Hebrew. Never more than two.
3. `{GENERAL}` stands alone: a word tagged `{GENERAL}` carries no other topic.
4. Prefer `{GENERAL}` to a stretch. A wrong `{GENERAL}` costs one word in no bar; a \
wrong topic puts a word in the wrong bar. Common verbs of motion, speech, thought and \
possession, adjectives of size, quality and time, and abstract nouns are usually \
`{GENERAL}`.
5. Religion & tradition only where the word's main modern sense is religious. A word \
religious only in a secondary sense, or only in the Bible, takes its modern topic or \
`{GENERAL}`.
6. Science & technology is the fields and computing as a system. A device and its \
everyday use is Everyday life; what the media publish is Free time & culture.
7. Words for people as such, by age or sex, are People & feelings; family members are \
Family & home.
8. Time: the units of the clock and the calendar (hour, day, week, month, morning) are \
Everyday life. Time as such (time, moment, period, occasion, the past, the future) and \
adverbs of time are `{GENERAL}`.
9. Media: the press and what it makes (newspaper, article, channel, series) is Free time \
& culture. Verbs of publishing, reporting, announcing, quoting and revealing are \
`{GENERAL}`, because the news says them about every topic.
10. Set `confidence` to `low` when the gloss is ambiguous, when the word could \
reasonably go either way, or when you are unsure of the Hebrew. Otherwise `high`.

Examples:
{examples}

Answer for every id you are given, once each, in the JSON shape required."""


def schema() -> dict[str, Any]:
    """The answer's shape, held to by structured outputs (`output_config.format`). The cap
    of two and `general`'s exclusiveness are checked after (`checked`)."""
    return {
        "type": "object",
        "properties": {
            "tags": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "topics": {
                            "type": "array",
                            "items": {"type": "string", "enum": [*TOPICS, GENERAL]},
                        },
                        "confidence": {"type": "string", "enum": ["high", "low"]},
                    },
                    "required": ["id", "topics", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["tags"],
        "additionalProperties": False,
    }


def user_message(lemmas: Sequence[Lemma], start: int) -> str:
    """One request's words, numbered from `start`. Nothing but the four fields."""
    lines = []
    for offset, one in enumerate(lemmas):
        pointed = f" ({one.pointed})" if one.pointed and one.pointed != one.lemma else ""
        gloss = f"{one.gloss} [{HINT_LABEL}: {one.hint}]" if one.hint else one.gloss
        lines.append(f"{start + offset}\t{one.lemma}{pointed}\t{one.pos or '?'}\t{gloss}")
    # Said only where a row carries a hint, so a request without one is prompt 3's own.
    note = (
        f" Where a gloss gives a rarer sense first, [{HINT_LABEL}: ...] after it names the"
        " sense to tag."
        if any(one.hint for one in lemmas)
        else ""
    )
    return (
        f"Tag these words. Columns: id, lemma (pointed form), part of speech, gloss.{note}\n\n"
        + "\n".join(lines)
    )


# --- Hints: the commonest modern sense, where the gloss gives a rarer one ---------------

#: What a hint is called inside a request's gloss column.
HINT_LABEL = "commonest modern sense"
HINT_VERSION = "hint/1"


def other_senses(lemma: str, pos: str, used: str, gloss: Any = None) -> list[str]:
    """The glosses the cache holds under the lemma's other keys (the bare lemma, the verb's
    key, a part-of-speech key) that differ from the one sent: גר glossed "stranger;
    convert" also holds "to live; reside" as a verb. Never spends."""
    from .models import POS_MARKS, VERB_MARK

    gloss = gloss or cached_gloss
    keys = [lemma, lemma + VERB_MARK, *(lemma + mark for mark in POS_MARKS.values())]
    out: list[str] = []
    for key in dict.fromkeys(keys):
        if key == glossed_as(lemma, pos):
            continue
        held = gloss(key)
        if held and held[0] != used and held[0] not in out:
            out.append(held[0])
    return out


def hint_system_prompt() -> str:
    """The hint pass's instructions: one short sense per word, and whether the gloss's
    first sense is it. It never sees a topic, so it cannot be taught the gold set."""
    return """You check English glosses of Modern Hebrew dictionary words for a reading \
app. Each gloss was written for the word's spelling, and sometimes gives a biblical, \
rarer or homograph sense first (עצב "to be sad; nerve" is commonest "sadness"; מטען \
"cargo; load" is commonest "phone charger"; גר "stranger; convert" is commonest "lives").

For each word you get an id, the unpointed lemma, a pointed form when there is one, the \
part of speech, and the gloss. Give:
- `sense`: the word's commonest sense in Modern Hebrew today, in one to four English \
words, as a learner would meet it in news and conversation.
- `first`: true when the gloss's first sense is that sense, or so close that a reader of \
the gloss would understand the word rightly; false when the gloss leads with a rarer, \
older or different sense.

Answer for every id you are given, once each, in the JSON shape required."""


def hint_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "senses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "sense": {"type": "string"},
                        "first": {"type": "boolean"},
                    },
                    "required": ["id", "sense", "first"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["senses"],
        "additionalProperties": False,
    }


def parse_hints(text: str, ids: Iterable[int]) -> dict[int, tuple[str, bool]]:
    """(sense, whether the gloss leads with it) for each id asked, answered once."""
    wanted = set(ids)
    try:
        rows = json.loads(text)["senses"]
    except (ValueError, KeyError, TypeError):
        return {}
    out: dict[int, tuple[str, bool]] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        number, sense, first = row.get("id"), row.get("sense"), row.get("first")
        if not isinstance(number, int) or number not in wanted or number in out:
            continue
        if not isinstance(sense, str) or not sense.strip() or not isinstance(first, bool):
            continue
        out[number] = (" ".join(sense.split())[:60], first)
    return out


def hinted(one: Lemma, sense: str, first: bool, others: Sequence[str]) -> Lemma:
    """The lemma as the tagger is shown it once the hint pass has read it: unchanged where
    the gloss leads with the commonest sense, otherwise carrying that sense and the cache's
    other senses as its hint."""
    if first:
        return one
    extra = [s for s in others if s != one.gloss]
    hint = "; ".join([sense, *(f"also {s}" for s in extra)])
    return Lemma(**{**asdict(one), "hint": hint})


@dataclass(frozen=True)
class Tag:
    topics: tuple[str, ...]
    confidence: str


def checked(topics: Iterable[str], confidence: str = "high") -> Tag | None:
    """One answer made to keep the rules, or None for one that cannot: an unknown code
    fails the row, more than two is cut to the first two, and `general` beside a topic
    is dropped in favour of the topic."""
    codes: list[str] = []
    for code in topics:
        if code != GENERAL and code not in TOPICS:
            return None
        if code not in codes:
            codes.append(code)
    if not codes:
        return None
    if GENERAL in codes and len(codes) > 1:
        codes = [code for code in codes if code != GENERAL]
    return Tag(tuple(codes[:MOST]), "low" if confidence == "low" else "high")


def parse(text: str, ids: Iterable[int]) -> dict[int, Tag]:
    """The tags in one answer, for the ids that were asked; an id answered twice keeps
    its first answer, and one answered badly is left out, to be asked again."""
    wanted = set(ids)
    try:
        held = json.loads(text)
        rows = held["tags"]
    except (ValueError, KeyError, TypeError):
        return {}
    tags: dict[int, Tag] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        number = row.get("id")
        if not isinstance(number, int) or number not in wanted or number in tags:
            continue
        topics = row.get("topics")
        if not isinstance(topics, list):
            continue
        tag = checked([str(code) for code in topics], str(row.get("confidence", "high")))
        if tag is not None:
            tags[number] = tag
    return tags


def agreed(first: Tag | None, second: Tag | None) -> tuple[str, ...] | None:
    """What two models' answers settle: the same answer, or the topics they share. None
    where they share nothing, which is a row for ling-he."""
    if first is None or second is None:
        return None
    if set(first.topics) == set(second.topics):
        return first.topics
    shared = tuple(code for code in first.topics if code in second.topics)
    return shared or None


# --- The lexicon and the share ----------------------------------------------------------


def load(file: Path | None = None) -> dict[str, tuple[str, ...]] | None:
    """The lexicon's lemmas and their topics, or None where there is no file."""
    file = file or LEXICON
    try:
        held = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    lemmas = held.get("lemmas") if isinstance(held, dict) else None
    if not isinstance(lemmas, dict):
        return None
    return {
        str(lemma): tuple(str(code) for code in codes)
        for lemma, codes in lemmas.items()
        if isinstance(codes, list)
    }


#: A bar is drawn only for a topic with this many lemmas in the yardstick's top 20k, and
#: only for a reader who knows this many content lemmas.
TOPIC_FLOOR = 60
READER_FLOOR = 100
#: The yardstick depth a bar counts inside.
DEPTH = 20_000


def weights(store: Store, registers: Sequence[str], depth: int = DEPTH) -> dict[str, float]:
    """Each lemma's weight over `registers`: log(1 + its blended rate per million), where
    the blend is the plain mean of the registers' own rates, so no register outweighs
    another by being bigger. Log-damped, so three words cannot decide a bar (David,
    2026-10-30: weighted, as the plan recommends)."""
    from .tables.words import WORDS

    rates: dict[str, float] = {}
    present = 0
    for register in registers:
        top = store.top(WORDS, register, limit=depth)
        total = sum(n for _, n in top)
        if not total:
            continue
        present += 1
        for key, n in top:
            rates[key] = rates.get(key, 0.0) + n * 1_000_000 / total
    if not present:
        return {}
    blended = sorted(rates.items(), key=lambda item: (-item[1], item[0]))[:depth]
    return {key: math.log1p(rate / present) for key, rate in blended}


@dataclass(frozen=True)
class Share:
    topic: str
    share: float
    known: int
    lemmas: int
    #: Whether a page draws the bar: the topic is in `shown` and has enough lemmas in the
    #: yardstick.
    drawn: bool
    #: Whether the topic is in `shown` at all; one that is not has failed the gold set.
    shown: bool = True


def shares(
    lexicon: Mapping[str, Sequence[str]],
    known: Iterable[str],
    modern: Mapping[str, float],
    bible: Mapping[str, float],
    shown: Iterable[str] = SHOWN,
) -> list[Share]:
    """Each topic's share of its weighed lemmas the reader knows. A word in two topics
    counts fully in both; `general` has none. Religion & tradition is weighed from the
    bible register where the modern ones do not hold the word. A topic is `drawn` only
    when it is in `shown` (`load_shown`) and above the topic floor."""
    knows = set(known)
    visible = set(shown)
    out: list[Share] = []
    for topic in TOPICS:
        total = mine = 0.0
        members = hits = 0
        for lemma, codes in lexicon.items():
            if topic not in codes:
                continue
            weight = modern.get(lemma)
            if weight is None and topic == "religion":
                weight = bible.get(lemma)
            if weight is None:
                continue
            members += 1
            total += weight
            if lemma in knows:
                hits += 1
                mine += weight
        share = mine / total if total else 0.0
        drawn = members >= TOPIC_FLOOR and topic in visible
        out.append(Share(topic, share, hits, members, drawn, topic in visible))
    return out


#: Three made-up readers, from the tables alone, so the formula and the floors can be
#: seen before any real reader is: (who, register, how many of its commonest lemmas they
#: know). No real account is ever read for this.
SYNTHETIC: dict[str, tuple[str, tuple[str, ...], int]] = {
    "beginner": (
        "A beginner: the 400 commonest words of conversation",
        ("conversation", "scenes"),
        400,
    ),
    "oleh": (
        "An oleh after a year: the 2,500 commonest words of conversation",
        ("conversation", "scenes"),
        2500,
    ),
    "news": ("A news reader: the 4,000 commonest words of the news", ("news",), 4000),
}


def synthetic_known(store: Store, person: str) -> list[str]:
    """What one synthetic reader knows: the commonest lemmas of the first of its registers
    the tables hold anything for. Conversation falls back to targum's own scenes, which
    are modern conversation too, where no conversation is counted yet."""
    from .tables.words import WORDS

    _, registers, depth = SYNTHETIC[person]
    for register in registers:
        top = store.top(WORDS, register, limit=depth)
        if top:
            return [key for key, _ in top]
    return []
