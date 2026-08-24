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

import json
from dataclasses import dataclass, field
from enum import StrEnum
from functools import cache
from pathlib import Path


class Shelf(StrEnum):
    """Which room a text belongs in.

    Tanakh is kept apart from everything else, and not only for tidiness. The registers
    differ enough that difficulty bands built for one are wrong for the other; some
    readers do not wish to be shown secular material at all; and the two may one day be
    paid for differently. All three want this to be data rather than a heading.
    """

    library = "library"
    beit_midrash = "beit-midrash"


@dataclass(frozen=True)
class Line:
    """One sentence of a text beside its translation.

    A handful of these ship with each entry so the public page has real reading on it.
    Fetching them at render time would put the network between a visitor and a page, and
    a page that sometimes fails to load is a page that does not get indexed.
    """

    source: str
    target: str


@cache
def _samples() -> dict[str, list[Line]]:
    """The opening lines, kept as data beside this module.

    Not written inline below, for two reasons: real sentences are longer than the line
    limit this codebase holds itself to, and a catalogue of two dozen Tanakh books would
    bury the entries under their own excerpts. It is content, so it lives in a file.
    """
    path = Path(__file__).with_name("samples.json")
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        entry_id: [Line(source=line["source"], target=line["target"]) for line in lines]
        for entry_id, lines in raw.items()
    }


def sample_for(entry_id: str) -> list[Line]:
    """The opening of one text, or nothing if none has been chosen yet."""
    return _samples().get(entry_id, [])


@dataclass(frozen=True)
class Rendering:
    """One published translation of a catalogue text.

    `publisher` and `licence` are not bookkeeping. A reader decides whether to trust a
    translation of scripture by who made it, so both are shown wherever the text is —
    and naming the licence is also how a CC-BY obligation gets discharged by the code
    rather than remembered by a person.
    """

    name: str
    source: str
    note: str = ""
    publisher: str = ""
    licence: str = ""


@dataclass(frozen=True)
class Entry:
    id: str
    title: str
    author: str
    language: str
    source: str
    blurb: str
    words: int
    shelf: Shelf = Shelf.library
    translations: list[Rendering] = field(default_factory=list)

    @property
    def sample(self) -> list[Line]:
        """The opening, both languages, for the public page.

        Looked up by id rather than stored on the entry, so the excerpt and the entry
        cannot drift apart. Empty is allowed: the page drops the section rather than
        showing a heading over nothing.
        """
        return sample_for(self.id)

    def state(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "language": self.language,
            "source": self.source,
            "blurb": self.blurb,
            "words": self.words,
            "shelf": self.shelf.value,
            "translations": [
                {
                    "name": t.name,
                    "source": t.source,
                    "note": t.note,
                    "publisher": t.publisher,
                    "licence": t.licence,
                }
                for t in self.translations
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


def on(shelf: Shelf) -> list[Entry]:
    """Everything on one shelf, in catalogue order.

    The list itself stays flat. `matching()` below has to see every entry whichever
    shelf it sits on, or the guard that stops somebody paying for a text that is already
    free would quietly stop covering half the catalogue.
    """
    return [entry for entry in CATALOGUE if entry.shelf is shelf]


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
