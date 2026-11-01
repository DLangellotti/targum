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
- a fixed Hebrew search phrase, so the live query (`live.query`) still contains only
  words targum wrote. The phrases wait on ling-he's read
  (`~/targum-team/ling-he/keep/find-chips-hebrew-2026-11-01.md`).

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


def _chip(code: str, label: str, lexicon: str, he: str) -> Chip:
    return Chip(code, label, lexicon, {"he": he})


#: In the order a page lists them after the reader's likely ones.
CHIPS: tuple[Chip, ...] = (
    _chip("sport", "Sport", "", "ספורט"),
    _chip("football", "Football", "", "כדורגל"),
    _chip("basketball", "Basketball", "", "כדורסל"),
    _chip("music", "Music", "", "מוזיקה"),
    _chip("film", "Film & TV", "", "סרטים וסדרות טלוויזיה"),
    _chip("tech", "Tech", "science", "טכנולוגיה"),
    _chip("gaming", "Gaming", "", "משחקי מחשב"),
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
    _chip("world", "The world", "", "חדשות מהעולם"),
    _chip("religion", "Religion", "religion", "דת ומסורת"),
    _chip("nature", "Nature", "nature", "טבע"),
    _chip("animals", "Animals", "nature", "בעלי חיים"),
    _chip("cars", "Cars", "travel", "מכוניות ורכב"),
    _chip("business", "Business", "work", "עסקים וכלכלה"),
    _chip("money", "Money", "money", "כסף וחיסכון"),
    _chip("work", "Work", "work", "עבודה וקריירה"),
    _chip("art", "Art", "", "אמנות"),
    _chip("books", "Books", "", "ספרים וספרות"),
    _chip("comedy", "Comedy", "", "הומור וקומדיה"),
    _chip("celebrities", "Celebrities", "", "סלבס ורכילות"),
    _chip("parenting", "Parenting", "family", "הורות וגידול ילדים"),
    _chip("school", "School", "school", "לימודים ובית ספר"),
    _chip("relationships", "Relationships", "people", "זוגיות ויחסים"),
    _chip("home", "Home", "family", "הבית ועיצוב הבית"),
    _chip("gardening", "Gardening", "nature", "גינון"),
    _chip("crime", "Crime", "law", "פשיעה ומשטרה"),
    _chip("army", "The army", "security", "צבא וביטחון"),
    _chip("weather", "Weather", "nature", "מזג אוויר"),
    _chip("holidays", "Holidays", "religion", "חגים ומועדים"),
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


def ordered(liked: Sequence[str]) -> list[tuple[Chip, bool]]:
    """Every chip, the reader's likely ones first (those whose lexicon topic their reading
    suggests, in the order of `liked`), each with whether it is suggested."""
    first: list[Chip] = []
    for topic in liked:
        first.extend(chip for chip in CHIPS if chip.lexicon == topic and chip not in first)
    return [(chip, True) for chip in first] + [(chip, False) for chip in CHIPS if chip not in first]


def phrase(code: str, language: str) -> str:
    chip = BY_CODE.get(code)
    return "" if chip is None else chip.phrases.get(language, "")
