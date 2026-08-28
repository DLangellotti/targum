"""Difficulty bands.

Six bands, from the word a learner meets in their first week to the one a native
speaker looks up. What puts a word in a band is stated in the artifact and shown in
the reader, because a learner should know whether they are looking at curated level
data or a frequency proxy.
"""

from __future__ import annotations

from typing import Protocol

from ..models import Segment, Token

BAND_COUNT = 6

# A word nothing can rate, because the language has no frequency data behind it. Shown
# as no level at all rather than as a guess.
UNRATED = 0

# Words a learner does not have to acquire, and so words a difficulty count leaves out.
# They are still tokens — the reader can tap a name, hear it read, and press `i` — but
# a frequency band for אחשורוש says nothing true about how hard Esther is, and counting
# every name in a chronicle as a hard word would move it a shelf up the library.
NOT_VOCABULARY = frozenset({"PROPN", "NUM"})

# The same fact, as the reader receives it: a seventh column on every token row, 0 for
# a word, 1 for a name, 2 for a number. What the reader calls them is `KIND_NAMES` in
# reader.js, and a word marked while wearing one of those keeps it as its band — which
# is how the ledger and the ulpan ladder know to leave it out.
KIND_COLUMN = {"PROPN": 1, "NUM": 2}

# Plain difficulty, easiest first. Deliberately not CEFR levels: these come from
# frequency, and calling level 3 "B1" would claim a correspondence that has not been
# established. Deliberately not numbers either, in anything a reader sees.
BAND_NAMES = {
    1: "easy",
    2: "fairly easy",
    3: "moderate",
    4: "hard",
    5: "very hard",
    6: "extremely hard",
}

# What the reader offers: mark this level and everything harder.
HIGHLIGHT_LABELS = {
    2: "fairly easy and up",
    3: "moderate and up",
    4: "hard and up",
    5: "very hard and up",
    6: "extremely hard only",
}

# How the levels were worked out, said in the reader rather than left implied.
METHOD_LABELS = {
    "frequency": "by how common each word is",
    "none": "not rated, since this language has no frequency data",
}


def method_label(method: str) -> str:
    if method.startswith("curated:"):
        return f"from the {method.split(':', 1)[1]} word list"
    return METHOD_LABELS.get(method, method)


NO_METHOD = "none"


def highlight_levels() -> list[dict[str, object]]:
    return [{"value": value, "label": label} for value, label in sorted(HIGHLIGHT_LABELS.items())]


class Lemmatizer(Protocol):
    """Surface forms into dictionary forms.

    Load-bearing rather than optional. Hebrew attaches ו, ה, ב, כ, ל, מ and ש directly
    to the word, and Russian inflects heavily, so looking up the surface form misses
    the majority of tokens in both.
    """

    @property
    def name(self) -> str:
        """Model identity, recorded on the annotation."""

    def lemmas(self, segments: list[Segment], language: str) -> dict[str, list[Token]]:
        """Tokens per segment id, with lemma and offsets but no band yet."""


class Pronouncer(Protocol):
    """Pointed words into how they are said.

    Optional, unlike the lemmatizer: a text with no reading is a text that reads exactly
    as it did before. The vowels are the input, so this can only ever run after the
    document has been pointed.
    """

    @property
    def name(self) -> str:
        """Engine identity, recorded on the annotation through the annotator's name."""

    def available(self) -> tuple[bool, str]:
        """Whether it can run here, and why not when it cannot."""

    def say(self, surfaces: list[str]) -> dict[str, str]:
        """A reading for each distinct pointed form that has one."""


class Bands(Protocol):
    """What makes a lemma hard."""

    @property
    def name(self) -> str: ...

    @property
    def method(self) -> str:
        """'frequency' or 'curated:<source>'. Shown to the reader."""

    @property
    def note(self) -> str:
        """One line on where the bands came from."""

    def supports(self, language: str) -> bool:
        """Whether this source can rate words in the language at all."""

    def band(self, lemma: str, language: str) -> int: ...
