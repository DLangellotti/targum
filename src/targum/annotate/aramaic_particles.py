"""ד־ and ית, read off the hand table's answer: Aramaic's first hard spot and the object
marker (design.md §12, "Aramaic has a hard-spot list" and "Aramaic's lenses", 2026-10-25).

**ד־ is "of", "which", "that" and "because"**, and it is written onto the next word, where
a reader from Hebrew sees a ד that belongs to the root: דְאַרְעָא is "of the earth", and
דַּהֲבָא is "the gold". So only what the annotator has already answered is said here: a word
it found in the hand table or among the verse's names with ד taken off the front
(`Token.built`, "ד + ארעא"), and the word דִּי itself. A ד the table could not account
for is left alone, which costs recall and never says a root letter is a particle.

**ית marks the object**, as אֶת does in Hebrew, and carries its pronoun on the end (יָתֵהּ,
יָתְהוֹן). It is the hand table's headword יָת, in all its forms.

Scored against Open Scriptures in Daniel and Ezra, where דִּי is the lexeme 1768 in every
role it plays (`scripts/eval_aramaic_particles.py`). Biblical Aramaic writes ד־ apart as
דִּי far more than Onkelos does, so the score says little about the prefix; ling-arc's
hand gold on Onkelos is owed for that, as for the state.
"""

from __future__ import annotations

from ..models import Token
from .aramaic import key

NAME = "arc-particles/1"

#: What the lens shows, as the grammar line says it.
DALET = "D"
YAT = "Yat"


def particle(token: Token) -> str:
    """`D` for a word that is or starts with ד־, `Yat` for the object marker, or ""."""
    headword = key(token.headword or "")
    if headword == "ית":
        return YAT
    if headword == "די":
        return DALET
    pieces = [piece.strip() for piece in (token.built or "").split("+")]
    # The prefixes come first: "ו + ד + ארעא". A ד that is the stem itself is not one.
    if len(pieces) > 1 and "ד" in pieces[:-1]:
        return DALET
    return ""
