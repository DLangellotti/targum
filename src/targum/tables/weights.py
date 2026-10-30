"""Which tally rows a weighting leaves out (targum-internal#577).

The raw counts keep every word: a tally is a measurement, and dropping a word on the way
in would make every later question about it unanswerable. What a learner has to know is
asked when the counts are read, here, so the rule can change without a re-fold.
"""

from __future__ import annotations

#: The closed-class parts of speech: the words a frequency list is mostly made of and a
#: learner meets on the first page whatever they read. Counted, never weighed.
EXCLUDED = frozenset({"ADP", "CCONJ", "SCONJ", "DET", "PRON", "AUX", "PART"})

#: The key a name is tallied under, so a phrase around a name is one phrase whoever is
#: named, and no person's name is a row of its own.
NAME = "<NAME>"

#: The part of speech a number carries, which `annotate.base.not_vocabulary` always
#: leaves out. A name is out by its key; a number keeps its lemma and is out by this.
_NUMBER = "NUM"


def function_word(pos: str | None, entity: str | None = None) -> bool:
    """Whether one token is left out of a weighting: a closed-class word, or a name or a
    number as `annotate.base.not_vocabulary` decides them, the NER first where it read."""
    from ..annotate.base import not_vocabulary

    return (pos or "") in EXCLUDED or not_vocabulary(pos, entity)


def weighed(key: str, variant: str) -> bool:
    """Whether a `words` tally row counts toward a weighting, asked of the row alone.

    The fold has already turned every name into `NAME`, so the entity it was decided by
    is not needed again here: a PROPN the NER overruled is a word, and kept.
    """
    return key != NAME and variant not in EXCLUDED and variant != _NUMBER
