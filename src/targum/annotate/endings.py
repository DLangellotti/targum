"""Which French noun endings tell the gender, and which a word has (targum-internal#263).

`french_endings.json` is counted by `scripts/french_endings.py` from Grammalecte's lexicon
(MPL-2.0): an ending is there where 90% or more of the plain nouns in it share a gender.
What reaches a reader is a fact about one word — *nation* ends in *-tion*, and nouns in
*-tion* are feminine — never the table, and never the lexicon it was counted from.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

_TABLE = Path(__file__).with_name("french_endings.json")


@cache
def table() -> tuple[tuple[str, str], ...]:
    """The endings and their gender, longest first, so the first match is the most
    specific one a word has."""
    rows = json.loads(_TABLE.read_text(encoding="utf-8"))["endings"]
    pairs = [(str(row["ending"]), str(row["gender"])) for row in rows]
    return tuple(sorted(pairs, key=lambda pair: -len(pair[0])))


def ending_of(word: str) -> str:
    """`f:tion` for a word whose ending says feminine, `m:age` for masculine, "" where
    no ending it has says anything. The ending is only a candidate: the card names it
    only for a noun whose own gender agrees."""
    lowered = word.lower()
    if not lowered.isalpha():
        return ""
    for ending, gender in table():
        if len(lowered) > len(ending) + 1 and lowered.endswith(ending):
            return f"{gender}:{ending}"
    return ""
