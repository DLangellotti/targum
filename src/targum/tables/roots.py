"""Table 2, `roots`: how often a root occurs, in each register (targum-internal#589).

Folded beside `words`, by the same fold, from the same public texts and behind the same
guard (`tables.public_text`), so a reader's import writes no root row either. The key is
the root as the page draws it (`annotate.verb_roots.root_for`): the annotation's, less
the roots known to be wrong, filled from the CC0 paradigm table where it gave none. The
variant is the binyan the annotation gave, "" where the root was filled and the
annotation said no binyan.

Verbs only for now. A noun's root comes from targum's own root lexicon
(`annotate.root_card`) and is counted in a reader's family line, but not here: counting it
in the table is #594's, with the lexicon on the machine that folds.
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
    from ..annotate.verb_roots import root_for, said_roots

    # How the annotator spelled each lemma's root where it gave one, for a hollow root
    # the CC0 table files under both ו and י (`verb_roots.filled`, #601).
    said = said_roots(
        (str(token.get("lemma") or ""), token.get("root"))
        for run in tokens.values()
        for token in run
        if isinstance(token, Mapping) and token.get("pos") == "VERB"
    )
    out: Counter[tuple[str, str]] = Counter()
    for run in tokens.values():
        for token in run:
            if not isinstance(token, Mapping) or token.get("pos") != "VERB":
                continue
            lemma = str(token.get("lemma") or "")
            entity = token.get("entity")
            if lemma in NOT_A_WORD or (entity and is_named(entity)):
                continue
            root = root_for(lemma, token.get("root"), "VERB", language, said.get(lemma, ""))
            if root:
                out[(root, str(token.get("binyan") or ""))] += 1
    return out
