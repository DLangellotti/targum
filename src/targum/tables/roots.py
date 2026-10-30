"""Table 2, `roots`: how often a root occurs, in each register (targum-internal#589).

Folded beside `words`, by the same fold, from the same public texts and behind the same
guard (`tables.public_text`), so a reader's import writes no root row either. The key is
the root as the page draws it (`annotate.verb_roots.root_for`): the annotation's, less
the roots known to be wrong, filled from the CC0 paradigm table where it gave none. The
variant is the binyan the annotation gave, "" where the root was filled and the
annotation said no binyan.

Verbs only for now. A noun's root waits for targum's own root lexicon; until then a
noun has no root anywhere, and nothing here guesses one.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

ROOTS = "roots"


def rule() -> str:
    """The counting rule's version, carrying `verb_roots.VERSION`: a change to what is a
    root counts every text again, and supersedes what the old answer gave."""
    from ..annotate.verb_roots import VERSION

    return f"roots/1+verb-roots/{VERSION}"


def count(
    tokens: Mapping[str, Sequence[Mapping[str, Any]]], language: str
) -> Counter[tuple[str, str]]:
    """The roots of one annotation's verbs, keyed (root, binyan): never written, only
    counted. A name is no verb, whatever it was tagged."""
    from ..annotate.base import NOT_A_WORD, is_named
    from ..annotate.verb_roots import root_for

    out: Counter[tuple[str, str]] = Counter()
    for run in tokens.values():
        for token in run:
            if not isinstance(token, Mapping) or token.get("pos") != "VERB":
                continue
            lemma = str(token.get("lemma") or "")
            entity = token.get("entity")
            if lemma in NOT_A_WORD or (entity and is_named(entity)):
                continue
            root = root_for(lemma, token.get("root"), "VERB", language)
            if root:
                out[(root, str(token.get("binyan") or ""))] += 1
    return out
