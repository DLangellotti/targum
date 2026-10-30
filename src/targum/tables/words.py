"""Table 1, `words` and `phrases`: how often a lemma, or a run of two or three, occurs.

Folded from an `annotation.json` the pipeline has already written, so it runs no model
and costs nothing. The key is the reader's own word identity, the lemma a `word` row and
a mark are filed under; the variant is its part of speech, so a weighting can leave the
closed classes out when it reads (`weights`) and nothing is dropped when it writes.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from . import roots, weights
from .store import Contribution, Store

if TYPE_CHECKING:
    from . import PublicText

WORDS = "words"
PHRASES = "phrases"
ROOTS = roots.ROOTS
#: Every table one fold writes. `roots` (sublexical slice 1) rides the same fold and the
#: same guard, so a text is read once for all three.
TABLES = (WORDS, PHRASES, ROOTS)

#: The version of the counting rule below. A change to what is counted is a new number,
#: so every text is counted again under it and supersedes what the old rule gave.
RULE = "words/1"

#: How long a phrase is: two lemmas and three.
LENGTHS = (2, 3)

#: The languages folded. DICTA's lemmas are the ones the spec measures; another
#: language's annotator is a different yardstick and waits for its own decision.
LANGUAGES = ("he",)


def _key(token: Mapping[str, Any]) -> tuple[str, str, bool] | None:
    """(key, variant, is a function word) for one token, or None for one that is not a
    word at all (`annotate.base.NOT_A_WORD`)."""
    from ..annotate.base import NOT_A_WORD, is_named

    lemma = str(token.get("lemma") or "")
    if lemma in NOT_A_WORD:
        return None
    pos = token.get("pos")
    entity = token.get("entity")
    # A name as `not_vocabulary` decides one: the NER where it read the word, the tag
    # where it did not.
    named = is_named(entity) if entity else pos == "PROPN"
    key = weights.NAME if named else lemma
    return key, str(pos or ""), weights.function_word(pos, entity)


def count(tokens: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Counter[tuple[str, str]]]:
    """The tallies of one annotation's tokens, by table: never written, only counted.

    A phrase is a run of lemmas inside one segment, never across two, and never across a
    token that is not a word. One made only of function words is not counted: "of the",
    "and he" are the language's glue, and would fill the top of every list.
    """
    words: Counter[tuple[str, str]] = Counter()
    phrases: Counter[tuple[str, str]] = Counter()
    for run in tokens.values():
        keyed: list[tuple[str, str, bool] | None] = [
            _key(token) for token in run if isinstance(token, Mapping)
        ]
        for one in keyed:
            if one is not None:
                words[(one[0], one[1])] += 1
        for length in LENGTHS:
            for start in range(len(keyed) - length + 1):
                window = keyed[start : start + length]
                if any(one is None for one in window):
                    continue
                parts = [one for one in window if one is not None]
                if all(one[2] for one in parts):
                    continue
                phrases[(" ".join(one[0] for one in parts), " ".join(one[1] for one in parts))] += 1
    return {WORDS: words, PHRASES: phrases}


def fold(text: PublicText, annotation: Mapping[str, Any], store: Store | None = None) -> int:
    """Count one public text's annotation into the tables. Returns the contributions
    written: 0 when every one is already current, when the ledger is off, or for a language
    not folded.

    `text` must come from `tables.public_text`, which is the only way to get one, so a
    reader's import cannot reach this by any path. The annotation must be that text's:
    one naming another document is refused rather than filed under this one's licence.
    """
    from . import PublicText

    if not isinstance(text, PublicText) or not text.sealed:
        raise TypeError("fold takes a text from tables.public_text, and nothing else")
    if str(annotation.get("document_hash") or "") != text.document_hash:
        raise ValueError("the annotation is of another document")
    language = str(annotation.get("language") or "")
    if not any(language == one or language.startswith(f"{one}-") for one in LANGUAGES):
        return 0
    store = store if store is not None else Store.from_env()
    if store is None:
        return 0
    tool = str(annotation.get("annotator") or "")
    if not tool:
        raise ValueError("the annotation does not name its annotator")
    tokens = annotation.get("tokens")
    if not isinstance(tokens, Mapping):
        raise ValueError("the annotation has no tokens")
    written = 0
    counted: dict[str, Counter[tuple[str, str]]] | None = None
    for table in TABLES:
        contribution = contribution_for(text, table, tool)
        if store.is_current(contribution.id):
            continue
        if counted is None:
            counted = {**count(tokens), ROOTS: roots.count(tokens, language)}
        if store.write(contribution, counted[table]):
            written += 1
    return written


def contribution_for(text: PublicText, table: str, tool: str) -> Contribution:
    """What a fold of one text into one table under one annotator is filed as."""
    return Contribution(
        table=table,
        register=text.register,
        unit=text.document_hash,
        source=text.source,
        licence=text.licence,
        tool=tool,
        rule=roots.rule() if table == ROOTS else RULE,
    )
