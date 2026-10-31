"""Root lexicons: a Hebrew root and pattern, and a Russian root and its affixes, for each
common lemma (targum-internal#592 and #596, epic #597).

David's decisions of 2026-10-30: modern-Hebrew roots come from targum's own lexicon, a
model's proposal checked against Wiktionary and Strong's and never copied from them; the
Russian lexicon runs alongside it, with DerivBase.Ru (Apache 2.0) the only open source
used directly and MorphyNet and Wiktionary (CC BY-SA) for checking only. The research is
ling-he's `sublexical-vocabulary-2026-10-30.md` and ling-ru's
`russian-sublexical-2026-10-30.md`.

**What a model is shown.** For each lemma: the lemma, its pointed form (Hebrew, where the
gloss cache gave one) or its stressed form (Russian, looked up in OpenRussian), its part
of speech and its cached English gloss. Never a sentence. The lemmas come only from the
language tables (`tables.Store.top`), which only public texts reach
(`tables.public_text`); never from `word` rows or the gloss cache, which hold private
imports. Russian is not folded into the corpus ledger (`tables.words.LANGUAGES`), so the
generator folds the public Russian texts into a store file of its own
(`russian_store`), under the same guard, where no Hebrew yardstick reads it.

**What comes back.** Hebrew: the root as letters joined by a maqaf, or none; the pattern
(the binyan of a verb, the mishkal of a noun or adjective as a ק־ט־ל template, a linear
suffix); whether the word is borrowed; the root's meaning; how transparent the word is
from its root; the pointed form the model read; a confidence. Russian: the root morphs
with their other spellings and a sense, the prefixes, the suffixes, a transparency
grade, whether the word is borrowed, and a confidence.

**Checks, never sources.** Hebrew: the CC0 paradigm table's verb roots
(`annotate.verb_roots.filled`), the letters-in-order and template rules, English
Wiktionary's roots and Strong's derivations. Russian: the letters-in-the-lemma rule,
DerivBase.Ru's edges, and MorphyNet's. Nothing a check reads is written into a lexicon.

The lexicons are private: `~/.targum/roots-<language>-<run>.json`, with the run's raw
answers under `~/.targum/research/roots/<run>/`. This module is the open half: the
prompts, the answers' shape, the checks and the scores. The paid run is
`scripts/build_roots.py`.
"""

from __future__ import annotations

import csv
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .topics import Lemma

if TYPE_CHECKING:
    from .tables import Store

LANGUAGES = ("he", "ru")
VERSION = {"he": "roots/1", "ru": "ru-roots/1"}
#: The prompts' own version, apart from the lexicons'.
PROMPT_VERSION = "prompt/1"

#: Where a run keeps its lemma list, raw answers, review files and check sources.
RESEARCH = Path.home() / ".targum" / "research" / "roots"
#: The check sources, fetched by hand into the research directory. None is in the repo.
SOURCES = RESEARCH / "sources"
#: The private store the public Russian texts are folded into for this generator alone.
RUSSIAN_TABLES = RESEARCH / "tables-ru.db"

#: The registers each language's lemmas are drawn from, by default: every register the
#: laptop's tables hold modern text under (`tables.registers`), and for Russian the two
#: its texts are filed under.
REGISTERS: dict[str, tuple[str, ...]] = {
    "he": ("news", "modern", "unfiled", "scenes", "weekly"),
    "ru": ("news", "unfiled"),
}


def lexicon_file(language: str, run: str) -> Path:
    """A run's agreed rows, as a private lexicon beside the others in `~/.targum`."""
    return Path.home() / ".targum" / f"roots-{language}-{run}.json"


# --- The lemmas -------------------------------------------------------------------------


def cached_gloss(language: str) -> Callable[[str], tuple[str, str] | None]:
    """The gloss-cache reader for one language: (gloss, pointed citation) or None. Never
    spends. Asked only about a lemma the tables gave."""
    from .annotate.gloss import GLOSS_MODEL, gloss_provider_name
    from .annotate.gloss import cached_gloss as held

    provider = gloss_provider_name(GLOSS_MODEL)

    def read(filed: str) -> tuple[str, str] | None:
        sense = held(filed, language, "en", provider)
        return None if sense is None else (sense.gloss, sense.citation)

    return read


def universe(
    store: Store,
    language: str,
    *,
    modern: int,
    bible: int = 0,
    registers: Sequence[str] | None = None,
    gloss: Callable[[str], tuple[str, str] | None] | None = None,
    stress: Callable[[str], str] | None = None,
) -> tuple[list[Lemma], list[dict[str, str]], list[str]]:
    """The lemmas to ask about, commonest first; the ones screened out, with the reason;
    and the ones passed over for want of a gloss.

    The draw and the screen are the topic tagger's (`topics.universe`, `topics.screen`),
    over `store`. A Russian lemma's `pointed` is its stressed form where `stress` (by
    default OpenRussian's headword, looked up and never shipped) gives one.
    """
    from . import topics

    chosen = tuple(registers or REGISTERS[language])
    drawn, missing = topics.universe(
        store,
        modern=modern,
        bible=bible if language == "he" else 0,
        gloss=gloss or cached_gloss(language),
        registers=chosen,
    )
    kept, dropped = topics.screen(store, drawn)
    if language == "ru":
        stress = stress or _openrussian_stress()
        kept = [replace(one, pointed=stress(one.lemma) or one.pointed) for one in kept]
    return kept, dropped, missing


def _openrussian_stress() -> Callable[[str], str]:
    from .annotate import openrussian

    held = openrussian.lexicon()
    if held is None:
        return lambda lemma: ""
    return held.headword


def russian_store(library: Path, file: Path | None = None) -> tuple[Store, Any]:
    """The public Russian texts under `library` folded into a store file of their own, and
    the sweep's result. Reads files and writes rows; runs no model and spends nothing. A
    reader's home is skipped, exactly as in the corpus ledger's own sweep."""
    from .tables import Store, no_models, sweep

    store = Store(file or RUSSIAN_TABLES)
    store.file.parent.mkdir(parents=True, exist_ok=True)
    with no_models():
        result = sweep(library, store, ("ru",))
    return store, result


# --- Prices -----------------------------------------------------------------------------
# The topic tagger's: the same two models at the same rates (`topics.PRICES`).

#: Lemmas a request carries, and the output tokens it may spend: the JSON (about 45 a
#: Hebrew row and 60 a Russian one, measured on the pilots) and the thinking.
PER_REQUEST = {"he": 100, "ru": 60}
MAX_TOKENS = {"he": 10000, "ru": 9000}
#: For a quote before anything is measured.
IN_PER_LEMMA = {"he": 30, "ru": 30}
OUT_PER_LEMMA = {"he": 45, "ru": 60}


# --- Hebrew -----------------------------------------------------------------------------

MAQAF = "־"
_FINALS = str.maketrans("םןץףך", "מנצפכ")
#: The letters a weak root can lose from its written word: I-נ (נפל → יפול), I-י,
#: hollow ו and י, III-ה, and א. A radical missing from the lemma must be one of these,
#: or the radical before it again (a geminate).
WEAK = frozenset("אהוינ")
#: The seven binyanim as the answer names them.
BINYANIM = ("פעל", "נפעל", "פיעל", "פועל", "הפעיל", "הופעל", "התפעל")


def letters(text: str | None) -> str:
    """The Hebrew letters alone: points and marks dropped, final forms folded."""
    bare = "".join(
        ch for ch in unicodedata.normalize("NFD", text or "") if not unicodedata.combining(ch)
    )
    return "".join(ch for ch in bare if "א" <= ch <= "ת").translate(_FINALS)


def root_key(root: str | None) -> str:
    """A root as one comparable string: its letters joined by a maqaf, or "" for none."""
    return MAQAF.join(letters(root))


def in_order(root: str, lemma: str) -> bool:
    """Whether a root's radicals can be read off the lemma in order: each radical found
    after the last one, or missing only where a weak root may lose it."""
    radicals = letters(root)
    word = letters(lemma)
    if not radicals or len(radicals) > 4:
        return False

    def fits(r: int, at: int) -> bool:
        if r == len(radicals):
            return True
        radical = radicals[r]
        found = word.find(radical, at)
        while found >= 0:
            if fits(r + 1, found + 1):
                return True
            found = word.find(radical, found + 1)
        weak = radical in WEAK or (r > 0 and radical == radicals[r - 1])
        return weak and fits(r + 1, at)

    return fits(0, 0)


def template_fits(pattern: str, root: str, lemma: str) -> bool | None:
    """Whether a mishkal template (ק־ט־ל for the radicals) spells the lemma once the root
    is put in, or None where the check does not apply: no template, not three radicals,
    or a weak radical. ו and י are dropped from both sides first, because the lemma is
    spelled plene and the template is pointed."""
    radicals = letters(root)
    shape = letters(pattern)
    if len(radicals) != 3 or any(r in WEAK for r in radicals):
        return None
    if not all(ch in shape for ch in "קטל") or shape.count("ק") != 1:
        return None
    filled = shape.replace("ק", "\x01").replace("ט", "\x02").replace("ל", "\x03")
    for mark, radical in zip("\x01\x02\x03", radicals, strict=True):
        filled = filled.replace(mark, radical)
    strip = str.maketrans("", "", "וי")
    return filled.translate(strip) == letters(lemma).translate(strip)


@dataclass(frozen=True)
class HebrewRoot:
    root: str
    """The root's letters joined by a maqaf (`root_key`), or "" where it has none."""
    pattern: str
    borrowed: bool
    meaning: str
    transparent: str
    pointed: str
    confidence: str


#: Worked examples: (lemma, pointed form shown, part of speech, gloss, root, pattern,
#: borrowed, meaning, transparent, pointed form read). "" is null in the answer.
_HE_EXAMPLES: tuple[tuple[str, str, str, str, str, str, bool, str, str, str], ...] = (
    ("כתב", "לִכְתֹּב", "VERB", "to write", "כ־ת־ב", "פעל", False, "write", "yes", "כָּתַב"),
    ("מכתב", "", "NOUN", "letter", "כ־ת־ב", "מִקְטָל", False, "write", "yes", "מִכְתָּב"),
    ("התכתב", "לְהִתְכַּתֵּב", "VERB", "to correspond", "כ־ת־ב", "התפעל", False, "write", "yes", "הִתְכַּתֵּב"),
    (
        "הוריד",
        "לְהוֹרִיד",
        "VERB",
        "to lower, take down",
        "י־ר־ד",
        "הפעיל",
        False,
        "go down",
        "yes",
        "הוֹרִיד",
    ),
    ("דיבר", "לְדַבֵּר", "VERB", "to speak", "ד־ב־ר", "פיעל", False, "speak", "yes", "דִּבֵּר"),
    ("נפל", "לִפֹּל", "VERB", "to fall", "נ־פ־ל", "פעל", False, "fall", "yes", "נָפַל"),
    ("קם", "לָקוּם", "VERB", "to get up", "ק־ו־ם", "פעל", False, "rise", "yes", "קָם"),
    (
        "חשבון",
        "",
        "NOUN",
        "bill; account",
        "ח־ש־ב",
        "קֶטְלוֹן",
        False,
        "think, count",
        "partly",
        "חֶשְׁבּוֹן",
    ),
    ("משבר", "", "NOUN", "crisis", "ש־ב־ר", "מַקְטֵל", False, "break", "partly", "מַשְׁבֵּר"),
    ("ערב", "", "NOUN", "evening", "ע־ר־ב", "קֶטֶל", False, "evening", "yes", "עֶרֶב"),
    ("ערבות", "", "NOUN", "guarantee, bail", "ע־ר־ב", "קַטְלוּת", False, "guarantee", "yes", "עַרְבוּת"),
    ("אדמת", "", "NOUN", "rubella", "א־ד־ם", "קַטֶּלֶת", False, "red", "partly", "אַדֶּמֶת"),
    ("נגר", "", "NOUN", "carpenter", "נ־ג־ר", "קַטָּל", False, "carpentry", "yes", "נַגָּר"),
    ("כלכלי", "", "ADJ", "economic", "כ־ל־כ־ל", "־י", False, "economy, provide", "yes", "כַּלְכָּלִי"),
    ("אפשרות", "", "NOUN", "possibility", "א־פ־ש־ר", "־ות", False, "possible", "yes", "אֶפְשָׁרוּת"),
    ("טלפון", "", "NOUN", "telephone", "", "", True, "", "", "טֶלֶפוֹן"),
    ("טלפן", "לְטַלְפֵּן", "VERB", "to phone", "ט־ל־פ־נ", "פיעל", True, "telephone", "yes", "טִלְפֵּן"),
    ("אוניברסיטה", "", "NOUN", "university", "", "", True, "", "", "אוּנִיבֶרְסִיטָה"),
    ("בית", "", "NOUN", "house", "", "", False, "", "", "בַּיִת"),
    ("גדול", "", "ADJ", "big", "ג־ד־ל", "קָטוֹל", False, "grow, big", "yes", "גָּדוֹל"),
    ("מאוד", "", "ADV", "very", "", "", False, "", "", "מְאֹד"),
)


def _he_example(row: tuple[str, str, str, str, str, str, bool, str, str, str]) -> str:
    lemma, shown, pos, gloss, root, pattern, borrowed, meaning, transparent, pointed = row
    answer = {
        "root": root or None,
        "pattern": pattern or None,
        "borrowed": borrowed,
        "meaning": meaning or None,
        "transparent": transparent or None,
        "pointed": pointed,
    }
    head = f"{lemma} ({shown})" if shown else lemma
    return f'- {head}, {pos}, "{gloss}" -> {json.dumps(answer, ensure_ascii=False)}'


def _system_he() -> str:
    examples = "\n".join(_he_example(row) for row in _HE_EXAMPLES)
    return f"""You analyse Modern Hebrew dictionary words into root and pattern, for a \
reading app that shows learners which words share a root. A wrong root is worse than \
none: a learner trusts it.

For each word you get an id, the unpointed lemma, a pointed form when there is one (for \
verbs, usually the infinitive), the part of speech and an English gloss. Analyse the \
word's commonest sense in Modern Hebrew today. The gloss and the part of speech are \
hints and can be wrong.

Fields:
- `root`: the radicals, unpointed, joined by a maqaf (כ־ת־ב), with no final letter forms \
(מ, not ם). Usually three letters, sometimes four (ת־ר־ג־מ), rarely two. Weak roots keep \
the radical the word hides (הוריד: י־ר־ד; קם: ק־ו־ם; נתן: נ־ת־ן). null for a loanword or \
internationalism with no Semitic root (טלפון), a function word, a name, and a primary \
noun with no live family of words on a root (בית, אב, ארץ).
- `pattern`: for a verb, its binyan, one of {", ".join(BINYANIM)}. For a noun or \
adjective, its mishkal as a pointed template with ק, ט, ל for the radicals (קֶטֶל, \
מִקְטָל, קַטָּל, קְטִילָה, הַקְטָלָה, הִתְקַטְּלוּת, קַטֶּלֶת, קִטָּלוֹן; a fourth radical \
repeats ל: קִטְלֵל). For a word made by adding a suffix to another word (כלכלי from \
כלכלה, אפשרות from אפשר), the suffix after a maqaf: ־אי, ־ות, ־י, ־ן, ־ייה. null where \
there is no root or no recognisable pattern.
- `borrowed`: true for a loanword, including one Hebrew has since given a root and a \
binyan (טלפן). false otherwise.
- `meaning`: the root's core meaning in one or two English words. Where one root string \
carries unrelated meanings, name the one this word belongs to: ע־ר־ב is "evening", \
"guarantee", "mix" or "Arab"; ס־פ־ר "count, tell", "barber" or "border"; ח־ל־ל "hollow", \
"profane" or "begin"; ק־ל־ל "curse" or "light". null where `root` is null.
- `transparent`: "yes" when a learner who knows the root's meaning could guess this \
word's meaning from it (מכתב from "write"), "partly" when the link is real but loose \
(משבר from "break", חשבון from "think"), "no" when it is historical only. null where \
`root` is null.
- `pointed`: the word's citation form, fully pointed, as you read it (a verb's \
third-person masculine singular past).
- `confidence`: "low" when you are unsure of the root or the pattern, when the word \
could be read two ways, or when you do not know the word. Otherwise "high".

Examples:
{examples}

Answer for every id you are given, once each, in the JSON shape required."""


def _schema_he() -> dict[str, Any]:
    nullable = {"type": ["string", "null"]}
    return {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "root": nullable,
                        "pattern": nullable,
                        "borrowed": {"type": "boolean"},
                        "meaning": nullable,
                        "transparent": {
                            "anyOf": [
                                {"type": "string", "enum": ["yes", "partly", "no"]},
                                {"type": "null"},
                            ]
                        },
                        "pointed": {"type": "string"},
                        "confidence": {"type": "string", "enum": ["high", "low"]},
                    },
                    "required": [
                        "id",
                        "root",
                        "pattern",
                        "borrowed",
                        "meaning",
                        "transparent",
                        "pointed",
                        "confidence",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["rows"],
        "additionalProperties": False,
    }


def _checked_he(row: Mapping[str, Any]) -> HebrewRoot | None:
    """One Hebrew answer made comparable, or None for one that breaks the shape: a root
    of one letter or more than four."""
    root = root_key(row.get("root") if isinstance(row.get("root"), str) else None)
    if root and not 2 <= len(letters(root)) <= 4:
        return None
    pattern = row.get("pattern")
    pattern = unicodedata.normalize("NFC", pattern.strip()) if isinstance(pattern, str) else ""
    if pattern and letters(pattern) in BINYANIM and not re.search(r"[֑-ׇ]", pattern):
        pattern = letters(pattern)
    transparent = row.get("transparent")
    return HebrewRoot(
        root=root,
        pattern=pattern,
        borrowed=bool(row.get("borrowed")),
        meaning=str(row.get("meaning") or "").strip().lower() if root else "",
        transparent=str(transparent) if root and transparent in ("yes", "partly", "no") else "",
        pointed=unicodedata.normalize("NFC", str(row.get("pointed") or "")),
        confidence="low" if row.get("confidence") == "low" else "high",
    )


# --- Russian ----------------------------------------------------------------------------

TRANSPARENCY = ("transparent", "partial", "opaque")


def fold_ru(text: str | None) -> str:
    """A Russian spelling made comparable: lower case, ё as е, stress marks and hyphens
    dropped."""
    # Only the stress marks go: NFD also splits й into и and a breve, which must stay.
    bare = unicodedata.normalize("NFD", text or "").replace("\u0301", "").replace("\u0300", "")
    folded = unicodedata.normalize("NFC", bare).lower().replace("ё", "е")
    return folded.replace("-", "").replace("'", "").strip()


@dataclass(frozen=True)
class Morph:
    morph: str
    variants: tuple[str, ...] = ()
    sense: str = ""

    @property
    def spellings(self) -> frozenset[str]:
        return frozenset(s for s in (self.morph, *self.variants) if s)


@dataclass(frozen=True)
class RussianRoot:
    roots: tuple[Morph, ...]
    prefixes: tuple[str, ...]
    suffixes: tuple[str, ...]
    transparency: str
    borrowed: bool
    confidence: str

    @property
    def spellings(self) -> frozenset[str]:
        """Every spelling of the first root: the one a family is keyed on."""
        return self.roots[0].spellings if self.roots else frozenset()


#: Worked examples: (lemma, stressed form, part of speech, gloss, roots, prefixes,
#: suffixes, transparency, borrowed). Roots are "morph/variant/variant:sense", several
#: joined by " + "; affixes are joined by "-".
_RU_EXAMPLES: tuple[tuple[str, str, str, str, str, str, str, str, bool], ...] = (
    (
        "написать",
        "написа́ть",
        "VERB",
        "to write (pf)",
        "пис/пиш:write",
        "на",
        "а",
        "transparent",
        False,
    ),
    (
        "понять",
        "поня́ть",
        "VERB",
        "to understand",
        "ня/ним/ем/им/ьм/йм:take",
        "по",
        "",
        "opaque",
        False,
    ),
    (
        "собирать",
        "собира́ть",
        "VERB",
        "to collect",
        "бир/бер/бр/бор:take",
        "со",
        "а",
        "partial",
        False,
    ),
    (
        "приходить",
        "приходи́ть",
        "VERB",
        "to come, arrive",
        "ход/хож/й/ш:go",
        "при",
        "и",
        "transparent",
        False,
    ),
    (
        "заниматься",
        "занима́ться",
        "VERB",
        "to study, be engaged in",
        "ним/ня/ем/им/ьм/йм:take",
        "за",
        "а-ся",
        "opaque",
        False,
    ),
    ("вода", "вода́", "NOUN", "water", "вод:water", "", "", "transparent", False),
    ("водитель", "води́тель", "NOUN", "driver", "вод/вож:lead", "", "и-тель", "transparent", False),
    (
        "пароход",
        "парохо́д",
        "NOUN",
        "steamship",
        "пар:steam + ход/хож:go",
        "",
        "",
        "transparent",
        False,
    ),
    ("деревня", "дере́вня", "NOUN", "village", "дерев/древ:wood", "", "н", "opaque", False),
    (
        "интересный",
        "интере́сный",
        "ADJ",
        "interesting",
        "интерес:interest",
        "",
        "н",
        "transparent",
        True,
    ),
    ("блог", "блог", "NOUN", "blog", "блог:blog", "", "", "transparent", True),
    (
        "человек",
        "челове́к",
        "NOUN",
        "person",
        "человек/человеч:person",
        "",
        "",
        "transparent",
        False,
    ),
    ("очень", "о́чень", "ADV", "very", "очень:very", "", "", "opaque", False),
    ("выиграть", "вы́играть", "VERB", "to win", "игр:play", "вы", "а", "partial", False),
)


def _ru_example(row: tuple[str, str, str, str, str, str, str, str, bool]) -> str:
    lemma, stressed, pos, gloss, roots, prefixes, suffixes, transparency, borrowed = row
    morphs = []
    for one in roots.split(" + "):
        spellings, _, sense = one.partition(":")
        first, *variants = spellings.split("/")
        morphs.append({"morph": first, "variants": variants, "sense": sense})
    answer = {
        "roots": morphs,
        "prefixes": [p for p in prefixes.split("-") if p],
        "suffixes": [p for p in suffixes.split("-") if p],
        "transparency": transparency,
        "borrowed": borrowed,
    }
    return f'- {lemma} ({stressed}), {pos}, "{gloss}" -> {json.dumps(answer, ensure_ascii=False)}'


def _system_ru() -> str:
    examples = "\n".join(_ru_example(row) for row in _RU_EXAMPLES)
    return f"""You analyse Russian dictionary words into morphemes, for a reading app that \
shows learners which words share a root. A wrong root is worse than a vague one: a learner \
trusts it.

For each word you get an id, the lemma, its stressed form when there is one, the part of \
speech and an English gloss. Analyse the word's commonest sense in Russian today. The \
gloss and the part of speech are hints and can be wrong.

Use a learner's convention, not Tikhonov's: split off a prefix wherever a learner can see \
the same root elsewhere without it (по-ня-ть beside при-ня-ть and взя-ть; от-вет-ить \
beside со-вет), and say how transparent the result is.

Fields:
- `roots`: the root morphs in order, usually one; two for a compound (пароход). Each has \
`morph`, the root as it is spelled in this lemma, lower case; `variants`, the other \
spellings the same root takes in its family through alternation (пис/пиш, бир/бер/бр/бор, \
ня/ним/ем/им, ход/хож/й/ш, лаг/лож, ча/чин), empty when there are none; and `sense`, the \
root's core meaning in one or two English words. Where one root string carries unrelated \
meanings, name the one this word belongs to: вод is "water" or "lead"; гор "mountain" or \
"burn"; лег "light" or "lie down"; мир "world" or "peace". A loanword's root is its \
borrowed stem (интерес).
- `prefixes`: the prefixes in order, as spelled in this word (раз or рас, вз or вс), \
including не- where it is a prefix. Empty when there are none.
- `suffixes`: the derivational and stem-forming suffixes in order (тель, ник, ость, н, ов, \
ск, а, и, ну, ова, ыва, ива), then the reflexive ся or сь. Leave out the inflectional \
ending (ть, ти, ый, ий, а of a noun).
- `transparency`: "transparent" when a learner who knows the root could guess the word's \
meaning (водитель from "lead"), "partial" when the link is real but loose (собирать), \
"opaque" when it is historical only (понять, деревня).
- `borrowed`: true for a word whose root is not Slavic (интересный, блог), false otherwise.
- `confidence`: "low" when you are unsure of the root or the split, when the word could \
be read two ways, or when you do not know the word. Otherwise "high".

Examples:
{examples}

Answer for every id you are given, once each, in the JSON shape required."""


def _schema_ru() -> dict[str, Any]:
    strings = {"type": "array", "items": {"type": "string"}}
    return {
        "type": "object",
        "properties": {
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "roots": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "morph": {"type": "string"},
                                    "variants": strings,
                                    "sense": {"type": "string"},
                                },
                                "required": ["morph", "variants", "sense"],
                                "additionalProperties": False,
                            },
                        },
                        "prefixes": strings,
                        "suffixes": strings,
                        "transparency": {"type": "string", "enum": list(TRANSPARENCY)},
                        "borrowed": {"type": "boolean"},
                        "confidence": {"type": "string", "enum": ["high", "low"]},
                    },
                    "required": [
                        "id",
                        "roots",
                        "prefixes",
                        "suffixes",
                        "transparency",
                        "borrowed",
                        "confidence",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["rows"],
        "additionalProperties": False,
    }


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out: list[str] = []
    for one in value:
        folded = fold_ru(str(one))
        if folded and folded not in out:
            out.append(folded)
    return tuple(out)


def _checked_ru(row: Mapping[str, Any]) -> RussianRoot | None:
    """One Russian answer made comparable, or None for one with no root at all."""
    roots: list[Morph] = []
    for one in row.get("roots") or []:
        if not isinstance(one, dict):
            continue
        morph = fold_ru(str(one.get("morph") or ""))
        if not morph:
            continue
        variants = tuple(v for v in _strings(one.get("variants")) if v != morph)
        roots.append(Morph(morph, variants, str(one.get("sense") or "").strip().lower()))
    if not roots:
        return None
    transparency = row.get("transparency")
    return RussianRoot(
        roots=tuple(roots),
        prefixes=_strings(row.get("prefixes")),
        suffixes=_strings(row.get("suffixes")),
        transparency=str(transparency) if transparency in TRANSPARENCY else "",
        borrowed=bool(row.get("borrowed")),
        confidence="low" if row.get("confidence") == "low" else "high",
    )


# --- Both -------------------------------------------------------------------------------

Answer = HebrewRoot | RussianRoot


def system_prompt(language: str) -> str:
    """The same on every request of a language, so it is cached."""
    return _system_he() if language == "he" else _system_ru()


def schema(language: str) -> dict[str, Any]:
    """The answer's shape, held to by structured outputs (`output_config.format`)."""
    return _schema_he() if language == "he" else _schema_ru()


def user_message(language: str, lemmas: Sequence[Lemma], start: int) -> str:
    """One request's words, numbered from `start`. Nothing but the four fields."""
    lines = []
    for offset, one in enumerate(lemmas):
        shown = f" ({one.pointed})" if one.pointed and one.pointed != one.lemma else ""
        lines.append(f"{start + offset}\t{one.lemma}{shown}\t{one.pos or '?'}\t{one.gloss}")
    form = "pointed form" if language == "he" else "stressed form"
    return (
        f"Analyse these words. Columns: id, lemma ({form}), part of speech, gloss.\n\n"
        + "\n".join(lines)
    )


def parse(language: str, text: str, ids: Iterable[int]) -> dict[int, Answer]:
    """The answers in one reply, for the ids that were asked; an id answered twice keeps
    its first answer, and one answered badly is left out, to be asked again."""
    wanted = set(ids)
    try:
        rows = json.loads(text)["rows"]
    except (ValueError, KeyError, TypeError):
        return {}
    checker: Callable[[Mapping[str, Any]], Answer | None] = (
        _checked_he if language == "he" else _checked_ru
    )
    out: dict[int, Answer] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        number = row.get("id")
        if not isinstance(number, int) or number not in wanted or number in out:
            continue
        answer = checker(row)
        if answer is not None:
            out[number] = answer
    return out


def same_root(first: Answer | None, second: Answer | None) -> bool | None:
    """Whether two answers give one root: the same letters after the weak-letter rules
    (`same_he_root`; both none counting as the same), or a first root whose spellings
    meet, directly or through `RU_ROOTS` and `RU_FUSED` (Russian). None where either is
    missing."""
    if first is None or second is None:
        return None
    if isinstance(first, HebrewRoot) and isinstance(second, HebrewRoot):
        return same_he_root(first.root, second.root)
    if isinstance(first, RussianRoot) and isinstance(second, RussianRoot):
        return any(same_ru_root(s, second.spellings) for s in first.spellings)
    return False


def agreed(first: Answer | None, second: Answer | None) -> dict[str, Any] | None:
    """The lexicon row two answers settle, or None where their roots differ (a row for
    the reviewer). A field the two disagree on is left empty rather than chosen."""
    if not same_root(first, second):
        return None
    if isinstance(first, HebrewRoot) and isinstance(second, HebrewRoot):
        return {
            "root": first.root or None,
            "pattern": (first.pattern if first.pattern == second.pattern else "") or None,
            "borrowed": first.borrowed if first.borrowed == second.borrowed else None,
            "meaning": first.meaning or None,
            "transparent": (first.transparent if first.transparent == second.transparent else None)
            or None,
        }
    assert isinstance(first, RussianRoot) and isinstance(second, RussianRoot)
    return {
        "roots": [
            {"morph": m.morph, "variants": list(m.variants), "sense": m.sense} for m in first.roots
        ],
        "prefixes": list(first.prefixes) if first.prefixes == second.prefixes else None,
        "suffixes": list(first.suffixes) if first.suffixes == second.suffixes else None,
        "transparency": (first.transparency if first.transparency == second.transparency else None),
        "borrowed": first.borrowed if first.borrowed == second.borrowed else None,
    }


def cells(answer: Answer | None) -> dict[str, str]:
    """An answer as flat text columns, for a review sheet."""
    if answer is None:
        return {}
    if isinstance(answer, HebrewRoot):
        return {
            "root": answer.root,
            "pattern": answer.pattern,
            "borrowed": "yes" if answer.borrowed else "",
            "meaning": answer.meaning,
            "transparent": answer.transparent,
            "pointed": answer.pointed,
            "confidence": answer.confidence,
        }
    return {
        "roots": " + ".join(
            m.morph + (f" ({'/'.join(m.variants)})" if m.variants else "") + f" [{m.sense}]"
            for m in answer.roots
        ),
        "prefixes": "-".join(answer.prefixes),
        "suffixes": "-".join(answer.suffixes),
        "transparency": answer.transparency,
        "borrowed": "yes" if answer.borrowed else "",
        "confidence": answer.confidence,
    }


# --- The checks -------------------------------------------------------------------------


@dataclass
class Tally:
    """How many answers a check could ask about, and how many it agreed with."""

    asked: int = 0
    agreed: int = 0
    #: A few that disagreed, as (lemma, the answer's, the check's), for the review.
    misses: list[tuple[str, str, str]] = field(default_factory=list)

    def add(self, ok: bool, lemma: str = "", ours: str = "", theirs: str = "") -> None:
        self.asked += 1
        if ok:
            self.agreed += 1
        elif len(self.misses) < 40:
            self.misses.append((lemma, ours, theirs))

    def as_dict(self) -> dict[str, Any]:
        return {
            "asked": self.asked,
            "agreed": self.agreed,
            "rate": round(self.agreed / self.asked, 3) if self.asked else None,
            "misses": self.misses,
        }


def wiktionary_roots(file: Path | None = None) -> dict[str, frozenset[str]]:
    """English Wiktionary's Hebrew roots by unpointed lemma, as `root_key`s: a check only
    (CC BY-SA), never a source. An entry with no root is left out, since Wiktionary not
    giving one says nothing either way."""
    file = file or SOURCES / "wiktionary" / "he-roots.json"
    try:
        held = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, frozenset[str]] = {}
    for lemma, entry in held.items() if isinstance(held, dict) else ():
        roots = entry.get("roots") if isinstance(entry, dict) else None
        keys = frozenset(root_key(r) for r in roots or [] if root_key(r))
        if keys:
            out[letters(lemma)] = keys
    return out


_PRIMITIVE = "a primitive root"
_DERIVED = re.compile(
    r"^\s*(?:\(Aramaic\)\s*)?(?:from|active participle of|"
    r"active of participle of|passive participle of|the same as|"
    r"feminine of|denominative from|intensive from|causative from)\b",
    re.IGNORECASE,
)


def strongs_roots(file: Path | None = None) -> dict[str, frozenset[str]]:
    """The root Strong's derivations reach for each unpointed Hebrew headword: follow
    "from H…" back to "a primitive root" and take that entry's letters. Strong's and BDB
    are public domain (OSHB's compilation CC BY 4.0); used here as a check. A spelling
    whose entries reach different roots keeps all of them; one that reaches none (a name,
    a word "of foreign origin", a chain that ends elsewhere) is left out."""
    file = file or SOURCES / "strongs" / "HebrewStrong.xml"
    try:
        tree = ET.parse(file)
    except (OSError, ET.ParseError):
        return {}
    ns = {"o": "http://openscriptures.github.com/morphhb/namespace"}
    entries: dict[str, tuple[str, str, str]] = {}
    for entry in tree.getroot().iter():
        if not entry.tag.endswith("entry"):
            continue
        word = entry.find("o:w", ns)
        if word is None:
            word = entry.find("w")
        source = entry.find("o:source", ns)
        if source is None:
            source = entry.find("source")
        if word is None or word.get("{http://www.w3.org/XML/1998/namespace}lang") != "heb":
            continue
        prose = "".join(source.itertext()) if source is not None else ""
        link = ""
        if source is not None and _DERIVED.search(prose):
            first = next((w for w in source.iter() if w.get("src")), None)
            link = first.get("src", "") if first is not None else ""
        entries[entry.get("id", "")] = (letters(word.text), prose, link)

    def reach(number: str, depth: int = 0) -> str:
        held = entries.get(number)
        if held is None or depth > 6:
            return ""
        word, prose, link = held
        if _PRIMITIVE in prose:
            return word
        return reach(link, depth + 1) if link else ""

    out: dict[str, set[str]] = {}
    for number, (spelling, _, _) in entries.items():
        root = reach(number)
        if root and 2 <= len(root) <= 4:
            out.setdefault(spelling, set()).add(root_key(root))
    return {spelling: frozenset(roots) for spelling, roots in out.items()}


def check_he(
    lemmas: Sequence[Lemma],
    answers: Mapping[int, HebrewRoot],
    *,
    cc0: Callable[[str], str] | None = None,
    wiktionary: Mapping[str, frozenset[str]] | None = None,
    strongs: Mapping[str, frozenset[str]] | None = None,
) -> dict[str, Any]:
    """One model's Hebrew answers against the rules and the three checks."""
    if cc0 is None:
        from .annotate.verb_roots import filled

        cc0 = filled
    wiktionary = wiktionary if wiktionary is not None else wiktionary_roots()
    strongs = strongs if strongs is not None else strongs_roots()
    rule, template, cc0_tally, wikt, strong = Tally(), Tally(), Tally(), Tally(), Tally()
    counts = {"rooted": 0, "no_root": 0, "borrowed": 0, "low": 0}
    for i, answer in answers.items():
        one = lemmas[i]
        counts["rooted" if answer.root else "no_root"] += 1
        counts["borrowed"] += answer.borrowed
        counts["low"] += answer.confidence == "low"
        if answer.root:
            rule.add(in_order(answer.root, one.lemma), one.lemma, answer.root)
            fits = template_fits(answer.pattern, answer.root, one.lemma)
            if fits is not None:
                template.add(fits, one.lemma, answer.pattern)
        if one.pos == "VERB":
            theirs = root_key(cc0(one.lemma))
            if theirs:
                cc0_tally.add(answer.root == theirs, one.lemma, answer.root, theirs)
        key = letters(one.lemma)
        if key in wiktionary:
            wikt.add(
                answer.root in wiktionary[key],
                one.lemma,
                answer.root,
                " ".join(sorted(wiktionary[key])),
            )
        if one.register == "bible" and key in strongs:
            strong.add(
                answer.root in strongs[key], one.lemma, answer.root, " ".join(sorted(strongs[key]))
            )
    return {
        **counts,
        "answered": len(answers),
        "letters_in_order": rule.as_dict(),
        "template_fits": template.as_dict(),
        "cc0_verb_roots": cc0_tally.as_dict(),
        "wiktionary": wikt.as_dict(),
        "strongs_bible": strong.as_dict(),
    }


def derivbase_edges(folder: Path | None = None) -> list[tuple[str, str, str]]:
    """DerivBase.Ru's edges (Apache 2.0) as (source word, derived word, PFX or SFX…)."""
    folder = folder or SOURCES / "derivbase"
    out: list[tuple[str, str, str]] = []
    for file in sorted(folder.glob("connections_*.csv")):
        with file.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                out.append((fold_ru(row["word_s"]), fold_ru(row["word_d"]), row["der_type"]))
    return out


def morphynet_edges(file: Path | None = None) -> list[tuple[str, str, str, str]]:
    """MorphyNet's Russian edges (CC BY-SA 3.0; a check only) as (base, derived, affix,
    prefix or suffix)."""
    file = file or SOURCES / "morphynet" / "deriv.tsv"
    out: list[tuple[str, str, str, str]] = []
    try:
        lines = file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        parts = line.split("\t")
        if len(parts) >= 6:
            out.append((fold_ru(parts[0]), fold_ru(parts[1]), fold_ru(parts[4]), parts[5]))
    return out


def check_ru(
    lemmas: Sequence[Lemma],
    answers: Mapping[int, RussianRoot],
    *,
    derivbase: Sequence[tuple[str, str, str]] | None = None,
    morphynet: Sequence[tuple[str, str, str, str]] | None = None,
) -> dict[str, Any]:
    """One model's Russian answers against the rules, DerivBase.Ru and MorphyNet.

    Along an edge whose two ends were both answered, the two roots should meet; and where
    MorphyNet says a word was made with a prefix or a suffix, the answer should list it.
    DerivBase.Ru's edges are about 75% right (ling-ru measured it), so its rate is a
    floor to watch, not a score.
    """
    derivbase = derivbase if derivbase is not None else derivbase_edges()
    morphynet = morphynet if morphynet is not None else morphynet_edges()
    by_lemma = {fold_ru(lemmas[i].lemma): a for i, a in answers.items()}
    in_lemma, starts, db_root, mn_root, mn_affix = Tally(), Tally(), Tally(), Tally(), Tally()
    counts = {"borrowed": 0, "low": 0, "compound": 0, "prefixed": 0}
    for i, answer in answers.items():
        word = fold_ru(lemmas[i].lemma)
        counts["borrowed"] += answer.borrowed
        counts["low"] += answer.confidence == "low"
        counts["compound"] += len(answer.roots) > 1
        counts["prefixed"] += bool(answer.prefixes)
        for morph in answer.roots:
            in_lemma.add(any(s in word for s in morph.spellings), word, morph.morph)
        starts.add(word.startswith("".join(answer.prefixes)), word, "-".join(answer.prefixes))
    for source, derived, kind in derivbase:
        a, b = by_lemma.get(source), by_lemma.get(derived)
        if a is not None and b is not None:
            db_root.add(
                bool(a.spellings & b.spellings),
                f"{source} > {derived} ({kind})",
                "/".join(sorted(a.spellings)),
                "/".join(sorted(b.spellings)),
            )
    for base, derived, affix, kind in morphynet:
        b = by_lemma.get(derived)
        if b is None:
            continue
        a = by_lemma.get(base)
        if a is not None:
            mn_root.add(
                bool(a.spellings & b.spellings),
                f"{base} > {derived}",
                "/".join(sorted(a.spellings)),
                "/".join(sorted(b.spellings)),
            )
        if affix and kind == "prefix":
            mn_affix.add(affix in b.prefixes, derived, "-".join(b.prefixes), affix + "-")
        elif affix and kind == "suffix":
            mn_affix.add(
                any(affix.startswith(s) or s.startswith(affix) for s in b.suffixes),
                derived,
                "-".join(b.suffixes),
                "-" + affix,
            )
    return {
        **counts,
        "answered": len(answers),
        "root_in_lemma": in_lemma.as_dict(),
        "prefixes_start_lemma": starts.as_dict(),
        "derivbase_edges_share_root": db_root.as_dict(),
        "morphynet_edges_share_root": mn_root.as_dict(),
        "morphynet_affix_listed": mn_affix.as_dict(),
    }


def agreement(
    language: str, first: Mapping[int, Answer], second: Mapping[int, Answer]
) -> dict[str, Any]:
    """How often two models' answers agree, field by field, over the rows both gave."""
    both = [i for i in first if i in second]
    if not both:
        return {"rows_both_answered": 0}

    def rate(test: Callable[[Any, Any], bool]) -> float:
        return round(sum(test(first[i], second[i]) for i in both) / len(both), 3)

    out: dict[str, Any] = {
        "rows_both_answered": len(both),
        "root": rate(lambda a, b: bool(same_root(a, b))),
        "borrowed": rate(lambda a, b: a.borrowed == b.borrowed),
    }
    if language == "he":
        out["pattern"] = rate(lambda a, b: a.pattern == b.pattern)
        out["root_and_pattern"] = rate(
            lambda a, b: bool(same_root(a, b)) and a.pattern == b.pattern
        )
        rooted = [i for i in both if first[i].root and second[i].root]  # type: ignore[union-attr]
        out["root_where_both_give_one"] = (
            round(sum(bool(same_root(first[i], second[i])) for i in rooted) / len(rooted), 3)
            if rooted
            else None
        )
    else:
        out["prefixes"] = rate(lambda a, b: a.prefixes == b.prefixes)
        out["suffixes"] = rate(lambda a, b: a.suffixes == b.suffixes)
        out["transparency"] = rate(lambda a, b: a.transparency == b.transparency)
        out["root_and_prefixes"] = rate(
            lambda a, b: bool(same_root(a, b)) and a.prefixes == b.prefixes
        )
    return out


# --- The blind gold set -----------------------------------------------------------------

GOLD_COLUMNS = {
    "he": ["row", "lemma", "pointed", "pos", "gloss", "root", "pattern", "borrowed", "notes"],
    "ru": [
        "row",
        "lemma",
        "stressed",
        "pos",
        "gloss",
        "roots",
        "prefixes",
        "suffixes",
        "transparency",
        "borrowed",
        "notes",
    ],
}


def _yes(cell: str) -> bool:
    return cell.strip().lower() in {"yes", "y", "true", "1", "כן", "да"}


# --- Equivalences -----------------------------------------------------------------------
# The same analysis written under another convention, listed by the two blind labellers
# before either saw a model's answer (ling-he's and ling-ru's gold notes, 2026-10-31).
# Each is a rule or a short table, never a fuzzy match. The rules that need nothing from
# the gold set (weak letters, the tables) also decide whether two models agree.


def weak_key(root: str | None) -> str:
    """A Hebrew root with its weak-letter conventions folded, as a `root_key`: two letters
    are a geminate (ק־ל = ק־ל־ל), and of three, a first ו is written י (ו־כ־ח = י־כ־ח), a
    middle י is written ו (ב־י־נ = ב־ו־נ) and a last י is written ה (ר־צ־י = ר־צ־ה)."""
    radicals = list(letters(root))
    if len(radicals) == 2:
        radicals.append(radicals[1])
    if len(radicals) == 3:
        radicals[0] = "י" if radicals[0] == "ו" else radicals[0]
        radicals[1] = "ו" if radicals[1] == "י" else radicals[1]
        radicals[2] = "ה" if radicals[2] == "י" else radicals[2]
    return MAQAF.join(radicals)


#: A root made from a word, beside the root of that word: a quadriliteral (ארגון,
#: ריאיון, מלאכותי) or a root cut from a ת- form (התחיל, תוכנית). Either is right.
HE_SOURCES: tuple[frozenset[str], ...] = tuple(
    frozenset(weak_key(r) for r in pair)
    for pair in (
        ("א־ר־ג־נ", "א־ר־ג"),
        ("ר־א־י־נ", "ר־א־ה"),
        ("ל־א־כ", "מ־ל־א־כ"),
        ("ת־ח־ל", "ח־ל־ל"),
        ("ת־כ־נ", "כ־ו־נ"),
    )
)


def same_he_root(first: str | None, second: str | None) -> bool:
    """Whether two Hebrew roots are one root under the weak-letter rules or `HE_SOURCES`.
    Two answers of no root are the same; no root and a root are not."""
    a, b = weak_key(first), weak_key(second)
    return a == b or any(a in pair and b in pair for pair in HE_SOURCES)


_NOTE_ROOT = re.compile(r"[א-ת](?:־[א-ת])+")


def gold_roots_he(cell: str, notes: str) -> frozenset[str]:
    """Every root a Hebrew gold row accepts, "" for none: the cell's; on a primary noun
    (notes starting `primary:`) also none and each root the notes name as its dictionary
    root; and none where the notes say `accept "-"`."""
    out = {"" if cell.strip() == "-" else root_key(cell)}
    notes = notes.strip()
    if notes.startswith("primary:"):
        out |= {"", *(root_key(r) for r in _NOTE_ROOT.findall(notes))}
    if 'accept "-"' in notes:
        out.add("")
    return frozenset(out)


_HOLAM, _QUBBUTS, _DAGESH = "ֹ", "ֻ", "ּ"


def skeleton(pattern: str | None) -> str:
    """A pattern's consonants, to compare two templates by: the pointing dropped, except
    that a holam or a qubbuts is written as the ו it stands for (קֹטֵל = קוֹטֵל) and a
    dagesh in a radical as the radical doubled (קַטָּל is not קֶטֶל). A vowel alone never
    tells two templates apart, so מִקְטָל = מַקְטָל."""
    out: list[str] = []
    for ch in unicodedata.normalize("NFD", pattern or ""):
        if "א" <= ch <= "ת":
            out.append(ch.translate(_FINALS))
        elif not out:
            continue
        elif ch == _DAGESH and out[-1] in "קטל":
            out.append(out[-1])
        elif ch in (_HOLAM, _QUBBUTS) and out[-1] != "ו":
            out.append("ו")
    return "".join(out)


#: The participle templates of each binyan: a participle used as an adjective (נוסף,
#: נכון, מתאים) may be given either its binyan or its template.
PARTICIPLES: dict[str, frozenset[str]] = {
    binyan: frozenset(skeleton(t) for t in templates)
    for binyan, templates in {
        "פעל": ("קוֹטֵל", "קָטוּל"),
        "נפעל": ("נִקְטָל",),
        "פיעל": ("מְקַטֵּל",),
        "פועל": ("מְקֻטָּל",),
        "הפעיל": ("מַקְטִיל",),
        "הופעל": ("מֻקְטָל",),
        "התפעל": ("מִתְקַטֵּל",),
    }.items()
}


def same_pattern(first: str | None, second: str | None) -> bool:
    """Whether two Hebrew patterns are one: the same binyan, the same `skeleton`, or a
    binyan and one of its participle templates."""
    first, second = first or "", second or ""
    if not first or not second:
        return first == second
    a, b = letters(first), letters(second)
    if a in BINYANIM and b in BINYANIM:
        return a == b
    if a in BINYANIM or b in BINYANIM:
        binyan, template = (a, second) if a in BINYANIM else (b, first)
        return skeleton(template) in PARTICIPLES[binyan]
    return skeleton(first) == skeleton(second)


def _groups(*spellings: str) -> tuple[frozenset[str], ...]:
    return tuple(frozenset(fold_ru(s) for s in one.split("/")) for one in spellings)


#: Russian spellings that are one root: a root with and without a suffix-like extension;
#: the go and take allomorphs; the pronoun stems; spellings of one morph.
RU_ROOTS: tuple[frozenset[str], ...] = _groups(
    "полн/пол",
    "тем/темн",
    "черн/чер",
    "числ/чис",
    "звук/зв",
    "чувств/чу",
    "действ/дей",
    "существ/сущ",
    "жи/жиз/жизн",
    "трет/тре",
    "сторон/стор",
    "знач/зна",
    "власт/влас/влад",
    "окн/ок",
    "работ/раб",
    "рубл/руб",
    "богат/бог",
    "й/йд/ид/ход",
    "ня/я",
    "т/то/тот/том",
    "ч/что/чег/чем",
    "к/коль/скольк",
    "вс/весь/все",
    "моч/мог/мо",
    "сес/се/сяд",
    "огон/огн",
    "стел/постел",
    "де/деж/одеж",
)

#: A prefix left fused into its root, or split off: (the fused stem, the prefix, the
#: root once it is split). Last, the two fused words whose historical root is accepted.
RU_FUSED: tuple[tuple[str, str, frozenset[str]], ...] = tuple(
    (fused, prefix, frozenset(split.split("/")))
    for fused, prefix, split in (
        ("наде", "на", "де"),
        ("ужас", "у", "жас"),
        ("улыб", "у", "лыб"),
        ("помн", "по", "мн/мин"),
        ("закон", "за", "кон"),
        ("недел", "не", "дел"),
        ("случ", "с", "луч"),
        ("нельзя", "не", "льз"),
        ("неужели", "не", "уж"),
        ("обыч", "об", "ыч"),
        ("обращ", "об", "ращ/врат/вращ"),
        ("опять", "о", "пят"),
        ("почти", "по", "чт"),
    )
)

#: Prefix spellings that are one prefix (встать: в or вс; войти: в or во; подойти).
RU_PREFIXES = {"вс": "в", "во": "в", "подо": "под"}


def _ru_classes() -> tuple[frozenset[str], ...]:
    return RU_ROOTS + tuple(frozenset({fused, *split}) for fused, _, split in RU_FUSED)


def same_ru_root(gold: str, spellings: Iterable[str]) -> bool:
    """Whether a Russian root morph is among an answer's spellings, directly or through
    `RU_ROOTS` or `RU_FUSED`."""
    held = frozenset(spellings)
    if gold in held:
        return True
    return any(gold in one and one & held for one in _ru_classes())


def ru_prefixes(prefixes: Iterable[str]) -> tuple[str, ...]:
    """Prefixes with their spellings folded (`RU_PREFIXES`), and a doubled letter written
    as a prefix of its own dropped (рас-с = рас)."""
    out: list[str] = []
    for one in prefixes:
        if len(one) == 1 and out and out[-1].endswith(one):
            continue
        out.append(RU_PREFIXES.get(one, one))
    return tuple(out)


def gold_prefixes_ru(root: str, prefixes: Sequence[str]) -> frozenset[tuple[str, ...]]:
    """Every prefix sequence a Russian gold row accepts: its own, and where its root is a
    fused stem or the root of one (`RU_FUSED`), the same with that prefix split off or
    left in."""
    want = ru_prefixes(prefixes)
    out = {want}
    for fused, prefix, split in RU_FUSED:
        if root == fused or root in split:
            bare = tuple(p for p in want if p != prefix)
            out |= {bare, (*bare, prefix)}
    return frozenset(out)


# --- The blind gold set -----------------------------------------------------------------


def _gold(gold_file: Path) -> list[dict[str, str]]:
    with gold_file.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def judge(
    language: str, row: Mapping[str, str], answer: Answer | None
) -> dict[str, tuple[bool, str, str]] | None:
    """One answer against one gold row, field by field: (right, the answer's, the
    gold's). None for an unlabelled row; a field the row leaves blank is not judged.

    Hebrew: the root under `same_he_root` with `gold_roots_he`; the pattern under
    `same_pattern` where the reviewer gave one; the borrowed flag. A blank root with no
    "borrowed" is unlabelled, and "-" means the reviewer says the word has none.
    Russian: the reviewer's first morph under `same_ru_root`; the prefixes under
    `gold_prefixes_ru`; the transparency where given; the borrowed flag.
    """
    borrowed_cell = row.get("borrowed", "")
    if language == "he":
        cell = row.get("root", "").strip()
        if not cell and not _yes(borrowed_cell):
            return None
        if not isinstance(answer, HebrewRoot):
            return {"root": (False, "(no answer)", cell)}
        accepted = gold_roots_he(cell, row.get("notes", ""))
        theirs = "" if cell == "-" else root_key(cell)
        out = {
            "root": (any(same_he_root(answer.root, r) for r in accepted), answer.root, theirs),
            "borrowed": (
                answer.borrowed == _yes(borrowed_cell),
                str(answer.borrowed),
                borrowed_cell,
            ),
        }
        want = unicodedata.normalize("NFC", row.get("pattern", "").strip())
        if want:
            out["pattern"] = (same_pattern(answer.pattern, want), answer.pattern, want)
        return out
    cell = fold_ru(row.get("roots", "").split("+")[0].split("(")[0])
    if not cell:
        return None
    if not isinstance(answer, RussianRoot):
        return {"root": (False, "(no answer)", cell)}
    want_p = [p for p in (fold_ru(x) for x in re.split(r"[-,\s]+", row.get("prefixes", ""))) if p]
    out = {
        "root": (
            same_ru_root(cell, answer.spellings),
            "/".join(sorted(answer.spellings)),
            cell,
        ),
        "prefixes": (
            ru_prefixes(answer.prefixes) in gold_prefixes_ru(cell, want_p),
            "-".join(answer.prefixes),
            "-".join(want_p),
        ),
        "borrowed": (answer.borrowed == _yes(borrowed_cell), str(answer.borrowed), borrowed_cell),
    }
    want_t = row.get("transparency", "").strip().lower()
    if want_t in TRANSPARENCY:
        out["transparency"] = (answer.transparency == want_t, answer.transparency, want_t)
    return out


def _fields(language: str) -> tuple[str, ...]:
    if language == "he":
        return ("root", "borrowed", "pattern")
    return ("root", "borrowed", "prefixes", "transparency")


def score(
    language: str, gold_file: Path, answers: Mapping[int, Answer], rows_to_ids: Mapping[int, int]
) -> dict[str, Any]:
    """One model's answers scored against a filled-in blind set, field by field (`judge`)."""
    tallies = {name: Tally() for name in _fields(language)}
    for row in _gold(gold_file):
        answer = answers.get(rows_to_ids.get(int(row["row"]), -1))
        verdicts = judge(language, row, answer)
        for name, (ok, ours, theirs) in (verdicts or {}).items():
            tallies[name].add(ok, row["lemma"], ours, theirs)
    return {name: tally.as_dict() for name, tally in tallies.items()}


def _agree(name: str, first: Answer, second: Answer) -> bool:
    """Whether the lexicon would settle a field on two answers, as `agreed` does."""
    if not same_root(first, second):
        return False
    if name == "root":
        return True
    mine, theirs = getattr(first, name), getattr(second, name)
    if name in ("pattern", "transparency") and not mine:
        return False  # nothing to ship
    return bool(mine == theirs)


def score_agreed(
    language: str,
    gold_file: Path,
    first: Mapping[int, Answer],
    second: Mapping[int, Answer],
    rows_to_ids: Mapping[int, int],
) -> dict[str, Any]:
    """What the lexicon would ship, scored: for each field, the gold rows judged on it,
    how many of them the two models settle (`agreed`: the root after the equivalences,
    any other field only where the root is settled too, and a pattern or a grade only
    where there is one to ship), and how many of those the shipped value, the first
    model's, gets right."""
    out: dict[str, dict[str, Any]] = {}
    for name in _fields(language):
        out[name] = {"rows": 0, "agreed": 0, "right": 0}
    for row in _gold(gold_file):
        at = rows_to_ids.get(int(row["row"]), -1)
        a, b = first.get(at), second.get(at)
        verdicts = judge(language, row, a)
        for name, (ok, _, _) in (verdicts or {}).items():
            tally = out[name]
            tally["rows"] += 1
            if a is not None and b is not None and _agree(name, a, b):
                tally["agreed"] += 1
                tally["right"] += ok
    for tally in out.values():
        tally["coverage"] = round(tally["agreed"] / tally["rows"], 3) if tally["rows"] else None
        tally["accuracy"] = round(tally["right"] / tally["agreed"], 3) if tally["agreed"] else None
    return out
