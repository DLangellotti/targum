"""The words check on arrival (design.md §12, "The arrival asks which words you know",
2026-11-01; targum-internal#613).

A new reader is shown words in the language they are learning in two rounds and taps the
ones they know: Hebrew since 2026-11-01, French and Russian since 2026-11-05 (design.md
§12, "The words check in French and Russian"; targum-internal#631, under #628's parity).
Each language has its own lists, made by its own linguistics seat, and its own `VERSION`,
and the rules below are the same for all three.
Round one is the same 18 real words for everybody, three from each of six frequency
bands, and four made-up words. Round two is fifteen more from the three bands around
where round one's yeses ran out, and four more made-up words. Nothing is scored or
shown back: the ticks are evidence for `estimate.py`, and the made-up words ticked
measure how often this reader ticks a word they cannot know.

**Both rounds follow from the ticks alone.** Round one is fixed and round two is a
function of round one's ticks, so what the reader was shown, and so what they left
unticked, is worked out again from what they ticked. That is all an account keeps of
the check: the words the reader marked, and when (privacy notice clause 3.2, "words and
phrases marked by the Data Subject"). A word ticked here is never put on the reader's
list. `VERSION` names these lists; a change to any of them is a new version, and a
check taken against an older one is read by the lists it was taken against or not at
all, never by today's.

**The words are fixed rather than drawn**, and the made-up ones were vetted one by one
by the Hebrew linguistics seat (ling-he, 2026-11-01): none is in wordfreq's 592,000
Hebrew forms, in the 104,000 verb forms of `annotate/paradigms.json.gz` or in the Tanakh;
none becomes a word by restoring a ו or a י (which is how מרגזת is מרוגזת, "annoyed",
written short), by losing a prefix letter or by losing an ending; none is one letter from
a word in wordfreq's commonest 30,000 that a learner would confuse it with; and none has
the shape מ+root+ת, the feminine participle written short, which is how the check before
this let מסגפת, a real word, through. Each is a real pattern on a real root (taCCuCa as
in תחבורה, taCCoCet as in תלבושת) that Hebrew does not happen to use. The real words
include four of the same shape, so a ת at the start gives nothing away.

French's and Russian's were made the same way by ling-fr and ling-ru (2026-11-05, #632),
with one rule Hebrew did not need: no real word is an English cognate or an international
loan, since a reader who reads English would tick *famille* or *проблема* knowing no
French or Russian. Their made-up words are real stems with productive endings the real
lists also carry, so an ending gives nothing away; `tests/test_check.py` holds the checks
each linguist ran that can run here. **Russian's lists are a draft awaiting David's read.**
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .estimate import Estimate
    from .level import Rung

#: The lists' name. A check is kept with it and read back only by the lists it names.
VERSION = "2026-11-01"

#: Hebrew, the language the check was first made for, and the one a call that names none
#: means. `VERSION`, `BANDS` and `MADE_UP` are Hebrew's; `LISTS` has every language's.
LANGUAGE = "he"

#: Six bands, commonest first, by place in wordfreq's Hebrew list: about 50–160,
#: 200–470, 800–1,200, 1,700–3,500, 5,000–10,000 and 12,000–19,000. Each word is the
#: commonest spelling of its dictionary form, unpointed, with no prefix letter, and not a
#: name. The first three of each band are round one; the other five are round two's.
BANDS: tuple[tuple[str, ...], ...] = (
    ("עכשיו", "תמיד", "דרך", "יום", "בית", "זמן", "מקום", "גדול"),
    ("יפה", "כסף", "לילה", "עבודה", "חשוב", "קטן", "מים", "ערב"),
    ("תקופה", "חדר", "טעות", "שבוע", "שמחה", "סיבה", "שחור", "רחוק"),
    ("תחבורה", "רכבת", "חלום", "מתנה", "זקן", "כוכב", "מכתב", "חשמל"),
    ("תערוכה", "נשימה", "ויכוח", "עוצמה", "בושה", "אזהרה", "דמיון", "מצור"),
    ("עיירה", "ספסל", "הפוגה", "זעיר", "מחסן", "אכזבה", "רציף", "נזיר"),
)

#: How many of each band round one shows.
FIRST = 3

#: How many bands round two draws from, and how many of each.
WINDOW = 3
SECOND = 5

#: Made-up words, vetted (see above and ling-he's note of 2026-11-01). The first four are
#: round one's; round two takes four of the other twelve, by where its bands start, so
#: no reader sees one twice.
MADE_UP: tuple[str, ...] = (
    "תלבוטה",
    "תכסומת",
    "תצרובה",
    "תזלוגת",
    "תקמוטה",
    "תשגורת",
    "תגלושה",
    "תקדוחת",
    "תרפודה",
    "תגרוסת",
    "תדגורה",
    "תצבוטת",
    "תפלוטה",
    "תדרוסת",
    "תזרוקה",
    "תבלומת",
)

#: How many made-up words each round shows.
MADE_UP_EACH = 4

#: The guess rate before the made-up words say anything: `estimate.CLAIM_GUESS`, worth
#: this many made-up words. Eight answers move it most of the way.
GUESS_PRIOR = 0.15
GUESS_PRIOR_WEIGHT = 2.0

#: French (ling-fr, 2026-11-05; targum-internal#632). Bands by place in wordfreq's French
#: list, by `frequency.rank`, in Hebrew's six windows. Each word is the commonest spelling
#: of its dictionary form, a noun, adjective or adverb, not a name, and not an English
#: cognate (nor a loan shared with Russian, for readers on the Russian interface).
VERSION_FR = "2026-11-05"

BANDS_FR: tuple[tuple[str, ...], ...] = (
    ("toujours", "temps", "jour", "monde", "homme", "chose", "beaucoup", "gens"),
    ("maison", "semaine", "argent", "nuit", "souvent", "eau", "seul", "peur"),
    ("endroit", "lumière", "ciel", "chanson", "médecin", "hiver", "faible", "moitié"),
    ("cadeau", "poche", "colère", "bouteille", "plage", "printemps", "neige", "gentil"),
    (
        "poubelle",
        "trottoir",
        "tristesse",
        "grenier",
        "marteau",
        "orage",
        "brouillard",
        "poussière",
    ),
    ("oreiller", "parapluie", "tablier", "grêle", "balai", "mouchoir", "habile", "ampoule"),
)

#: Made-up words, vetted (ling-fr, 2026-11-05): not in Morphalou 3.1 or wordfreq's French
#: or English lists, with or without accents, not an inflection of a word, and not one
#: letter from any of wordfreq's commonest 30,000 French words (no judged exceptions).
MADE_UP_FR: tuple[str, ...] = (
    "laumoir",
    "vardesse",
    "pachière",
    "bricheau",
    "toumoir",
    "brounière",
    "chevrard",
    "tachelle",
    "grénesse",
    "vignoir",
    "drognier",
    "flauson",
    "bechière",
    "mourdage",
    "crestier",
    "grisseau",
)

#: Russian (ling-ru, 2026-11-05; targum-internal#632). **A DRAFT awaiting David's read**
#: (TEAM.md: Russian lines are drafted and flagged): it does not ship until he has read
#: it. Bands by place in wordfreq's Russian list, in Hebrew's six windows. Each word is
#: the commonest form of its dictionary form, has no ё, is a noun, adjective or adverb,
#: is not a name, and is not an international loan.
VERSION_RU = "2026-11-05"

BANDS_RU: tuple[tuple[str, ...], ...] = (
    ("сейчас", "день", "всегда", "человек", "место", "сегодня", "теперь", "хорошо"),
    ("деньги", "ночь", "друг", "новый", "вчера", "часто", "правда", "имя"),
    ("голос", "море", "брат", "огонь", "письмо", "взгляд", "однажды", "ясно"),
    ("праздник", "радость", "ветер", "дождь", "счастье", "запах", "поезд", "живой"),
    ("шутка", "тишина", "зеркало", "чужой", "дыхание", "поцелуй", "пыль", "забота"),
    ("шкаф", "молния", "паук", "ведро", "тоска", "ледяной", "жажда", "тетрадь"),
)

#: Made-up words, vetted (ling-ru, 2026-11-05; a DRAFT awaiting David's read): not in
#: OpenRussian's forms or wordfreq's Russian list (ё folded), not a case form of a word,
#: and not one letter from any of wordfreq's commonest 30,000 Russian words.
MADE_UP_RU: tuple[str, ...] = (
    "ломотник",
    "шемость",
    "тробанка",
    "хлудина",
    "дрепание",
    "солмость",
    "плешота",
    "моросло",
    "смурдота",
    "сквобление",
    "шелбание",
    "пурнище",
    "тесловина",
    "стебница",
    "бурнило",
    "сколдина",
)


@dataclass(frozen=True)
class Lists:
    """One language's check: the lists' name, six bands of eight and sixteen made-up
    words, the first four of them round one's."""

    language: str
    version: str
    bands: tuple[tuple[str, ...], ...]
    made_up: tuple[str, ...]


#: Every language with a check, by code. A language not here has none, and its arrival
#: ends on the level.
LISTS: dict[str, Lists] = {
    "he": Lists("he", VERSION, BANDS, MADE_UP),
    "fr": Lists("fr", VERSION_FR, BANDS_FR, MADE_UP_FR),
    "ru": Lists("ru", VERSION_RU, BANDS_RU, MADE_UP_RU),
}


def lists_for(language: str | None) -> Lists | None:
    """A language's check, or None where it has none."""
    return LISTS.get((language or "").split("-")[0].lower())


def _of(language: str) -> Lists:
    found = lists_for(language)
    if found is None:
        raise ValueError(f"No words check in {language!r}.")
    return found


def first_round(language: str = LANGUAGE) -> tuple[list[str], list[str]]:
    """Round one: (real words, made-up words), the same for everybody."""
    lists = _of(language)
    real = [word for band in lists.bands for word in band[:FIRST]]
    return real, list(lists.made_up[:MADE_UP_EACH])


def edge(ticked: Iterable[str], language: str = LANGUAGE) -> int:
    """The band where round one's yeses ran out: the last band in which the reader ticked
    at least half of round one's words. Nought where they ticked none anywhere."""
    said = set(ticked)
    out = 0
    for at, band in enumerate(_of(language).bands):
        yes = sum(1 for word in band[:FIRST] if word in said)
        if yes * 2 >= FIRST:
            out = at
    return out


def window(at: int, language: str = LANGUAGE) -> int:
    """The first of the `WINDOW` bands round two draws from: the edge and one each side,
    kept inside the six."""
    return max(0, min(at - 1, len(_of(language).bands) - WINDOW))


def second_round(ticked: Iterable[str], language: str = LANGUAGE) -> tuple[list[str], list[str]]:
    """Round two, given round one's ticks: (real words, made-up words)."""
    lists = _of(language)
    start = window(edge(ticked, language), language)
    real = [
        word
        for band in lists.bands[start : start + WINDOW]
        for word in band[FIRST : FIRST + SECOND]
    ]
    rest = lists.made_up[MADE_UP_EACH:]
    made = [rest[(start * 3 + k) % len(rest)] for k in range(MADE_UP_EACH)]
    return real, made


def every_word(language: str = LANGUAGE) -> frozenset[str]:
    """Every word either round can show."""
    lists = _of(language)
    return frozenset([*(word for band in lists.bands for word in band), *lists.made_up])


def band_of(word: str, language: str = LANGUAGE) -> int:
    """A real word's band, or -1 for a made-up word or a word not in the check."""
    for at, band in enumerate(_of(language).bands):
        if word in band:
            return at
    return -1


def shown(ticked: Iterable[str], language: str = LANGUAGE) -> tuple[list[str], list[str]]:
    """Everything both rounds showed a reader who ticked these: (real, made-up)."""
    said = list(ticked)
    one_real, one_made = first_round(language)
    first = set(one_real) | set(one_made)
    two_real, two_made = second_round((word for word in said if word in first), language)
    return [*one_real, *two_real], [*one_made, *two_made]


def kept(ticked: Iterable[str], language: str = LANGUAGE) -> list[str]:
    """What an account keeps of a check: the ticked words the two rounds could have
    shown this reader, in the order they were shown, each once. A word round two would
    not have shown, or no round has, is dropped rather than refused: the page and this
    agree, and anything else did not come from the page."""
    said = set(ticked)
    real, made = shown(said, language)
    return [word for word in [*real, *made] if word in said]


def guess(made_ticked: int, made_shown: int) -> float:
    """How often this reader ticks a word they do not know: the made-up words they ticked,
    pulled towards `GUESS_PRIOR` by `GUESS_PRIOR_WEIGHT` made-up words' worth."""
    return (made_ticked + GUESS_PRIOR * GUESS_PRIOR_WEIGHT) / (made_shown + GUESS_PRIOR_WEIGHT)


def answers(ticked: Iterable[str], language: str = LANGUAGE) -> tuple[list[str], list[str], float]:
    """What a kept check says: (real words known, real words not known, guess rate)."""
    said = set(ticked)
    real, made = shown(said, language)
    known = [word for word in real if word in said]
    unknown = [word for word in real if word not in said]
    return known, unknown, guess(sum(1 for word in made if word in said), len(made))


#: How deep "the language's commonest five thousand" goes, in lemmas, for the CEFR
#: ladder's measure (`level.CEFR`, `level.common`).
COMMON_DEPTH = 5000


def common_known(estimate: Estimate) -> float:
    """How many of the commonest `COMMON_DEPTH` lemmas the estimate expects this reader
    to know: the CEFR ladder's measure (`level.common`), worked out from theta rather
    than counted off marks. The k-th commonest lemma sits about `FORMS_PER_LEMMA` further
    down wordfreq's list of forms, so its chance is σ(slope × (θ − FORMS_PER_LEMMA − ln k)),
    which is even at k = `Estimate.words`."""
    import math

    from .estimate import FORMS_PER_LEMMA, sigmoid

    at = estimate.theta - FORMS_PER_LEMMA
    return sum(sigmoid(estimate.slope * (at - math.log(k))) for k in range(1, COMMON_DEPTH + 1))


def common_reach(estimate: Estimate) -> float:
    """Where the estimate stands on the CEFR ladder: the vocabulary theta stands for, as
    known words among the commonest `COMMON_DEPTH` lemmas, with every lemma below that
    place known and none past it.

    **Calibrated, 2026-11-05 (David, on qa-claude's review of targum#1112).** The ladder's
    figures (`level.CEFR`, Milton 2010) are counts of words a learner *knows* among the
    commonest five thousand, and the check climbed it by `common_known`, the words the
    estimate *expects* known there. At the Rasch slope of 0.8 that curve is shallow
    enough to credit a reader with hundreds of words past their own vocabulary: an
    A1-sized vocabulary of 250 lemmas expected about 950, and A2's 1,350 about 2,170,
    which is B1. Every band landed about one step high. Read as the vocabulary itself,
    an A2-sized vocabulary is A2 and each band's own size lands on that band
    (`tests/test_check.py` pins each one)."""
    import math

    from .estimate import FORMS_PER_LEMMA

    # Rounded to a millionth first, as `level.words_to` does: exp(log(1350)) is
    # 1349.9999999999998 in floating point, which is 1,350 lemmas and not one short.
    vocabulary = round(math.exp(estimate.theta - FORMS_PER_LEMMA), 6)
    return min(vocabulary, float(COMMON_DEPTH))


def rung_after(estimate: Estimate) -> Rung | None:
    """The rung the estimate stands at after a check, on the language's own ladder: the
    highest it reaches. The ulpan ladder is climbed by vocabulary (`Estimate.words`), the
    CEFR's by known words among the commonest five thousand (`common_reach`). None under
    the first rung, and for a language with no ladder."""
    from .level import ladder_for

    ladder = ladder_for(estimate.language)
    if ladder is None:
        return None
    reach = estimate.words() if ladder.measure == "weighted" else common_reach(estimate)
    reached = [rung for rung in ladder.rungs if rung.at <= reach]
    return reached[-1] if reached else None


def rung_id(rung: Rung) -> str:
    """A rung by the id the arrival and the account use: "bet-plus" on the ulpan ladder,
    "a2" on the CEFR's (`Store.DECLARED`)."""
    return rung.name.replace(" ", "-").lower()


def page_data(language: str = LANGUAGE) -> dict[str, Any]:
    """What `/welcome` needs to draw both rounds in one language and work out round two
    itself, by the same rules as `second_round` (`tests/test_check.py` holds the two
    together)."""
    lists = _of(language)
    return {
        "version": lists.version,
        "language": lists.language,
        "bands": [list(band) for band in lists.bands],
        "first": FIRST,
        "window": WINDOW,
        "second": SECOND,
        "madeUp": list(lists.made_up),
        "madeUpEach": MADE_UP_EACH,
    }


def pages() -> dict[str, dict[str, Any]]:
    """`page_data` for every language with a check, by code: the page does not know which
    language the reader will press until they press it."""
    return {code: page_data(code) for code in LISTS}
