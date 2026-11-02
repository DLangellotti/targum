"""The reviewed mishkalim: the noun and adjective patterns that say something, in one
fixed order (design.md §12, "The Mishkal list beside the Grammar grid", 2026-11-02).

ling-he reviewed the 25 on 2026-11-02 (`~/targum-team/ling-he/keep/
mishkal-meanings-2026-11-02.md`). This is the one list both the word card's Mishkal row
and Your Progress's Mishkal list read: the key a pattern is said by and the templates the
root lexicon (`root_card`) writes for it. What each one means is said in the string
catalogue, under `reader.card.mishkal.<key>`, so a meaning is written once, in each
language, for both.

A pattern not on the list is still a pattern: the card shows its template alone, and the
list leaves it out. Nothing here is counted into a level, a ledger or a yardstick.
"""

from __future__ import annotations

import unicodedata

#: (key, templates), in the list's fixed order. The first template is the one drawn; the
#: rest are other spellings of the same pattern the lexicon writes. קַטְלוּת and the suffix
#: ־ות are one pattern to a learner (יַלְדוּת and אַחְרָיוּת), so they are one row.
PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("qattal", ("קַטָּל",)),
    ("qattelet", ("קַטֶּלֶת",)),
    ("miqtal", ("מִקְטָל",)),
    ("miqtala", ("מִקְטָלָה",)),
    ("maqtel", ("מַקְטֵל",)),
    ("maqtela", ("מַקְטֵלָה",)),
    ("miqtelet", ("מִקְטֶלֶת",)),
    ("maqtelet", ("מַקְטֶלֶת",)),
    ("qtila", ("קְטִילָה",)),
    ("qittul", ("קִטּוּל",)),
    ("haqtala", ("הַקְטָלָה",)),
    ("hitqattlut", ("הִתְקַטְּלוּת",)),
    ("hiqqatlut", ("הִקָּטְלוּת",)),
    ("qatul", ("קָטוּל",)),
    ("qatil", ("קָטִיל",)),
    ("qatlan", ("קַטְלָן",)),
    ("qotel", ("קוֹטֵל",)),
    ("meqattel", ("מְקַטֵּל",)),
    ("taqtil", ("תַּקְטִיל",)),
    ("qatlut", ("־ות", "קַטְלוּת")),
    ("suffix-i", ("־י",)),
    ("suffix-ai", ("־אי",)),
    ("suffix-iya", ("־ייה",)),
    ("suffix-it", ("־ית",)),
    ("suffix-on", ("־ון",)),
)

KEYS: tuple[str, ...] = tuple(key for key, _templates in PATTERNS)

_BY_TEMPLATE = {
    unicodedata.normalize("NFC", template): key
    for key, templates in PATTERNS
    for template in templates
}
_DRAWN = {key: templates[0] for key, templates in PATTERNS}


def key_of(pattern: str | None) -> str:
    """The list's key for a pattern as the lexicon writes it, or "" for one not on it."""
    return _BY_TEMPLATE.get(unicodedata.normalize("NFC", pattern or ""), "")


def template(key: str) -> str:
    """The pointed template (or suffix) a key is drawn as."""
    return _DRAWN[key]
