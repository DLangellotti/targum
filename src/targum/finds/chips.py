"""The topics "Find me something" offers to steer by (targum-internal#615; David,
2026-11-01).

About forty everyday topics, wider than the sixteen of the topic lexicon (`topics.py`),
because what a reader wants to read about is narrower than what a word is about: a
reader asks for football, and the lexicon knows only Free time & culture. Each chip is:

- its English label (the string `find.chip.<code>`; the Russian is a draft for David);
- the lexicon topic whose words say a pool find is about it, where the lexicon has one
  close enough. It counts only where that topic is shown (`topics.load_shown`): a topic
  whose tags failed ling-he's gold set is not trusted to match. A chip with none is
  matched in the pool only by a find a live look brought in for that chip (`TAG`), and
  otherwise goes straight to a live look;
- a fixed Hebrew search phrase, so the live queries (`live.queries`) still contain only
  words targum wrote. The phrases are ling-he's (2026-11-01,
  `~/targum-team/ling-he/keep/find-chips-hebrew-2026-11-01.md`): fourteen changed for a
  word that pulls a second meaning (יחסים, ביטחון, משפט), a phrase that finds writing
  *about* a topic rather than the thing (הומור), or wording dated or awkward;
- the catalogue registers whose shelf texts are about it whatever the lexicon shows
  (`registers`), for "Show me something harder", which ranks the shelf as well as the
  pool. Religion alone has them (2026-11-03): its lexicon topic is not shown, so no shelf
  text could match the chip, and the press vanished for a reader who chose it with the
  Tanakh, the Mishnah and the siddur all on the shelf under the floor.

**Russian** (targum-internal#635; ling-ru's draft of 2026-11-05,
`~/targum-team/ling-ru/keep/arrival-and-chips-ru-2026-11-05.md`, awaiting David's read)
has a phrase for every chip but three: `israel` and `holidays` have no Russian
equivalent and are dropped, and `army` is hidden, since *армия* in Russian today pulls
mostly the war (David, 2026-11-05). A chip with no phrase in a language that has phrases
is not offered in it (`ordered`, `offered`).

There is no free-text box (David, 2026-11-01): a reader steers by these chips or not at
all, which is also what keeps a reader's own words off a search provider.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Chip:
    code: str
    label: str
    #: The lexicon topic whose words match a pool find to this chip, or "".
    lexicon: str
    #: What the live look searches for, per language.
    phrases: dict[str, str]
    #: Catalogue registers (`catalogue.Register` values) whose shelf texts are about
    #: this chip, matched by the register alone; empty for most chips.
    registers: frozenset[str] = frozenset()


#: The Russian phrase per chip code (ling-ru, 2026-11-05; targum-internal#634, #635).
#: DRAFT, awaiting David's read. No `israel` or `holidays` (no Russian equivalent) and
#: no `army` (hidden for Russian): David, 2026-11-05. No ё: engines fold it, and the
#: queries then stay equal to what `live.ran_lately` compares.
PHRASES_RU: dict[str, str] = {
    "sport": "спорт",
    "football": "футбол",
    "basketball": "баскетбол",
    "music": "музыка",
    "film": "фильмы и сериалы",
    "tech": "технологии",
    "gaming": "видеоигры",
    "cooking": "кулинарные рецепты",
    "food": "еда и рестораны",
    "travel": "путешествия и отдых",
    "fashion": "мода и стиль",
    "health": "здоровье",
    "fitness": "фитнес и тренировки",
    "science": "наука",
    "space": "космос и астрономия",
    "history": "история",
    "politics": "политика",
    "world": "международные новости",
    "religion": "религия и традиции",
    "nature": "природа",
    "animals": "животные",
    "cars": "автомобили",
    "business": "бизнес и экономика",
    "money": "личные финансы",
    "work": "работа и карьера",
    "art": "искусство",
    "books": "книги и литература",
    "comedy": "стендап и юмор",
    "celebrities": "шоу-бизнес и знаменитости",
    "parenting": "воспитание детей",
    "school": "школа и образование",
    "relationships": "отношения и любовь",
    "home": "дизайн интерьера",
    "gardening": "сад и огород",
    "crime": "криминал и происшествия",
    "weather": "погода",
    "language": "русский язык",
}


def _chip(code: str, label: str, lexicon: str, he: str, registers: Iterable[str] = ()) -> Chip:
    phrases = {"he": he}
    if code in PHRASES_RU:
        phrases["ru"] = PHRASES_RU[code]
    return Chip(code, label, lexicon, phrases, frozenset(registers))


#: In the order a page lists them after the reader's likely ones.
CHIPS: tuple[Chip, ...] = (
    _chip("sport", "Sport", "", "ספורט"),
    _chip("football", "Football", "", "כדורגל"),
    _chip("basketball", "Basketball", "", "כדורסל"),
    _chip("music", "Music", "", "מוזיקה"),
    _chip("film", "Film & TV", "", "סרטים וסדרות"),
    _chip("tech", "Tech", "science", "טכנולוגיה"),
    _chip("gaming", "Gaming", "", "משחקי וידאו"),
    _chip("cooking", "Cooking", "food", "מתכונים ובישול"),
    _chip("food", "Food", "food", "אוכל ומסעדות"),
    _chip("travel", "Travel", "travel", "טיולים וחופשות"),
    _chip("fashion", "Fashion", "", "אופנה"),
    _chip("health", "Health", "health", "בריאות"),
    _chip("fitness", "Fitness", "health", "כושר ואימונים"),
    _chip("science", "Science", "science", "מדע"),
    _chip("space", "Space", "science", "חלל ואסטרונומיה"),
    _chip("history", "History", "", "היסטוריה"),
    _chip("politics", "Politics", "politics", "פוליטיקה"),
    _chip("israel", "Israel", "", "החיים בישראל"),
    _chip("world", "The world", "", "חדשות בעולם"),
    # The Tanakh; the Mishnah, Talmud, midrash, codes and liturgy; Andalusian philosophy.
    _chip("religion", "Religion", "religion", "דת ומסורת", ("biblical", "rabbinic", "medieval")),
    _chip("nature", "Nature", "nature", "טבע"),
    _chip("animals", "Animals", "nature", "בעלי חיים"),
    _chip("cars", "Cars", "travel", "מכוניות ורכב"),
    _chip("business", "Business", "work", "עסקים וכלכלה"),
    _chip("money", "Money", "money", "כלכלה אישית וחיסכון"),
    _chip("work", "Work", "work", "עבודה וקריירה"),
    _chip("art", "Art", "", "אמנות"),
    _chip("books", "Books", "", "ספרים וספרות"),
    _chip("comedy", "Comedy", "", "מערכונים וסטנדאפ"),
    _chip("celebrities", "Celebrities", "", "סלבס ורכילות"),
    _chip("parenting", "Parenting", "family", "הורות וגידול ילדים"),
    _chip("school", "School", "school", "לימודים ובית ספר"),
    _chip("relationships", "Relationships", "people", "זוגיות ואהבה"),
    _chip("home", "Home", "family", "עיצוב הבית"),
    _chip("gardening", "Gardening", "nature", "גינון"),
    _chip("crime", "Crime", "law", "פלילים ומשטרה"),
    _chip("army", "The army", "security", "צבא ושירות צבאי"),
    _chip("weather", "Weather", "nature", "מזג אוויר"),
    _chip("holidays", "Holidays", "religion", "חגי ישראל"),
    _chip("language", "Language", "", "השפה העברית"),
)

BY_CODE: dict[str, Chip] = {chip.code: chip for chip in CHIPS}

#: What a find a live look brought in for a chip carries in its `topics`, so the pool
#: matches it to that chip from then on, whatever the lexicon knows.
TAG = "chip:"


def tag(code: str) -> str:
    return f"{TAG}{code}"


def matcher(code: str, shown: Iterable[str]) -> str:
    """The lexicon topic a chip is matched by in the pool, or "" where none is shown."""
    chip = BY_CODE.get(code)
    if chip is None or not chip.lexicon:
        return ""
    return chip.lexicon if chip.lexicon in set(shown) else ""


def on_shelf(code: str, shown: Iterable[str], about: Iterable[str], register: str) -> bool:
    """Whether a shelf text is about a chip: its words are the chip's lexicon topic where
    that is shown, or its register is one of the chip's (`Chip.registers`)."""
    chip = BY_CODE.get(code)
    if chip is None:
        return False
    if register and register in chip.registers:
        return True
    topic = matcher(code, shown)
    return bool(topic) and topic in set(about)


#: The languages the chips carry phrases for: Hebrew, and Russian since #635.
LANGUAGES: tuple[str, ...] = tuple(dict.fromkeys(one for chip in CHIPS for one in chip.phrases))


def offered(code: str, language: str = "") -> bool:
    """Whether a chip is offered in a language: every chip where the language has no
    phrases at all, as before; otherwise only a chip with a phrase in it."""
    chip = BY_CODE.get(code)
    if chip is None:
        return False
    lang = (language or "").split("-")[0].lower()
    return lang not in LANGUAGES or bool(chip.phrases.get(lang))


def ordered(liked: Sequence[str], language: str = "") -> list[tuple[Chip, bool]]:
    """Every chip offered in the language (`offered`), the reader's likely ones first
    (those whose lexicon topic their reading suggests, in the order of `liked`), each
    with whether it is suggested."""
    shown = [chip for chip in CHIPS if offered(chip.code, language)]
    first: list[Chip] = []
    for topic in liked:
        first.extend(chip for chip in shown if chip.lexicon == topic and chip not in first)
    return [(chip, True) for chip in first] + [(chip, False) for chip in shown if chip not in first]


def phrase(code: str, language: str) -> str:
    chip = BY_CODE.get(code)
    return "" if chip is None else chip.phrases.get(language, "")
