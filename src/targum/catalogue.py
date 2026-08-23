"""Texts worth reading that already have a published translation.

Every entry here is a pair: a source, and one or more translations somebody has
already made and put in the public domain. Building from one costs nothing at all —
no model is asked to translate anything, the two texts are matched to each other with
embeddings on this machine — and the reading is better for it, because a translator
who worked on a text for a year beats a model that saw it once.

Each entry has been fetched and checked. Wikisource is full of index pages that look
like texts and turn out to be four links: a Hebrew Tanakh book is usually a list of
its chapters, not the chapters. Nothing goes in here until both sides come back with
a plausible amount of prose in them, so add entries the same way — fetch both, look
at the word counts, and only then write them down.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Rendering:
    """One published translation of a catalogue text."""

    name: str
    source: str
    note: str = ""


@dataclass(frozen=True)
class Entry:
    id: str
    title: str
    author: str
    language: str
    source: str
    blurb: str
    words: int
    translations: list[Rendering] = field(default_factory=list)

    def state(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "language": self.language,
            "source": self.source,
            "blurb": self.blurb,
            "words": self.words,
            "translations": [
                {"name": t.name, "source": t.source, "note": t.note} for t in self.translations
            ],
        }


CATALOGUE: list[Entry] = [
    Entry(
        id="il-declaration",
        title="מגילת העצמאות",
        author="State of Israel, 1948",
        language="he",
        source="wikisource:he:מגילת העצמאות של מדינת ישראל",
        blurb=(
            "The founding declaration, in the formal register Hebrew keeps for occasions. "
            "Short, and every sentence of it is quoted somewhere."
        ),
        words=655,
        translations=[
            Rendering(
                name="Official English",
                source="wikisource:Declaration of Independence (Israel)",
                note="Published by the State of Israel alongside the Hebrew.",
            )
        ],
    ),
    Entry(
        id="us-declaration-he",
        title="הכרזת העצמאות של ארצות הברית",
        author="Thomas Jefferson, 1776",
        language="he",
        source="wikisource:he:הכרזת העצמאות של ארצות הברית",
        blurb=(
            "A Hebrew translation of a text you very likely already know in English, "
            "which makes it an easy way in: you can guess ahead and check yourself."
        ),
        words=998,
        translations=[
            Rendering(
                name="The English original",
                source="wikisource:United States Declaration of Independence (engrossed copy)",
                note="Not a translation but the text it was translated from.",
            )
        ],
    ),
    Entry(
        id="father-sergius",
        title="Отец Сергий",
        author="Лев Толстой, 1898",
        language="ru",
        source="wikisource:ru:Отец Сергий (Толстой)",
        blurb=(
            "Late Tolstoy, novella length, plain sentences and a plot that pulls. "
            "Long enough to be a real reading project rather than an afternoon."
        ),
        words=13806,
        translations=[
            Rendering(
                name="Louise and Aylmer Maude",
                source="gutenberg:985",
                note="The Maudes knew Tolstoy and he approved of their translations.",
            )
        ],
    ),
]


def by_id(entry_id: str) -> Entry | None:
    for entry in CATALOGUE:
        if entry.id == entry_id:
            return entry
    return None


def _key(source: str) -> str:
    """A source flattened enough that two spellings of one text match.

    Wikisource titles arrive with underscores or spaces and in either case, and a
    Gutenberg id can be typed with or without the prefix.
    """
    return source.strip().lower().replace("_", " ").rstrip("/")


def matching(source: str) -> Entry | None:
    """The catalogue entry a source is already, if it is one.

    Used to stop someone paying to translate a text that is sitting here with a
    published translation attached to it.
    """
    wanted = _key(source)
    if not wanted:
        return None
    for entry in CATALOGUE:
        if _key(entry.source) == wanted:
            return entry
        for rendering in entry.translations:
            if _key(rendering.source) == wanted:
                return entry
    return None
