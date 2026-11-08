"""English–French false friends, from a list targum owns (targum-internal#267).

`false_friends.json` was drafted by the model and checked by it in a second pass, then
against Grammalecte's lexicon so that every entry is a dictionary form the French
lemmatizer emits (`scripts/false_friends.py` says how). It is targum's own work: no
published list was copied, and Wiktionary's appendix, which is CC BY-SA, is lookup only.
**ling-fr read every line of it, and every line it says on the French shelf in its
sentence, on 2026-11-05** (targum-internal#644), and the table says so in `reviewed`.

The card reads one line from it, for a French word read into English: "false friend:
not *actually* — currently". **On for every French reader since ling-fr's read cleared
the card's floor** (David's D6, 2026-11-05: 0.97 in context, `scripts/eval_false_friends.py`);
before that it waited behind `TARGUM_FALSE_FRIENDS` (David, 2026-09-28). The switch is
still there to turn it off with `TARGUM_FALSE_FRIENDS=0`. It is decided when a reader is
written, because a reader is a file that works off a disk: a text gets it at its next
rebuild, and a page written with it keeps it. Off, a reader is byte for byte what it was:
no table, no script.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from functools import cache
from pathlib import Path

_TABLE = Path(__file__).with_name("false_friends.json")

#: The switch, on unless the deployment turns it off (D6, 2026-11-05).
ENV = "TARGUM_FALSE_FRIENDS"


def is_on() -> bool:
    """Whether a reader written now carries the list. On unless the deployment says not."""
    return os.environ.get(ENV, "").strip().lower() not in {"0", "false", "no", "off"}


@cache
def table() -> dict[str, tuple[str, str]]:
    """What each French dictionary form looks like in English, and what it means."""
    rows = json.loads(_TABLE.read_text(encoding="utf-8"))["entries"]
    return {str(row["french"]): (str(row["looks_like"]), str(row["means"])) for row in rows}


@cache
def gates() -> dict[str, tuple[str, frozenset[str]]]:
    """The entries said only in some uses (ling-fr, 2026-11-05): the part of speech the
    word must have, and the words one of which must follow it, "" or empty where either
    is open. *matériel* the noun is equipment and the adjective is material; *assister à*
    is to attend and *assister quelqu'un* is to assist."""
    rows = json.loads(_TABLE.read_text(encoding="utf-8"))["entries"]
    return {
        str(row["french"]): (
            str(row.get("only_pos") or ""),
            frozenset(str(word) for word in row.get("only_before") or ()),
        )
        for row in rows
        if row.get("only_pos") or row.get("only_before")
    }


#: A use of a word: its part of speech and the word written after it, lowercased.
Use = tuple[str, str]


def friend_of(lemma: str, uses: Iterable[Use] | None = None) -> list[str]:
    """`["actually", "currently"]` for a lemma on the list, `[]` for any other.

    An entry said only in some uses (`gates`) is said where every one of `uses` is such a
    use, and never where the uses are not known: a line that is true of the noun and false
    of the adjective is not said of a word that may be either."""
    found = table().get(lemma)
    if found is None:
        return []
    gate = gates().get(lemma)
    if gate is not None:
        seen = list(uses or ())
        pos, before = gate
        if not seen or not all(
            (not pos or used == pos) and (not before or after in before) for used, after in seen
        ):
            return []
    return list(found)
