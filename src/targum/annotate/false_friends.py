"""English–French false friends, from a list targum owns (targum-internal#267).

`false_friends.json` was drafted by the model and checked by it in a second pass, then
against Grammalecte's lexicon so that every entry is a dictionary form the French
lemmatizer emits (`scripts/false_friends.py` says how). It is targum's own work: no
published list was copied, and Wiktionary's appendix, which is CC BY-SA, is lookup only.
**No person has reviewed it yet**, and the table says so in `reviewed` until one has.

The card reads one line from it, for a French word read into English: "false friend:
not *actually* — currently". **Only while `TARGUM_FALSE_FRIENDS` is set** (David,
2026-09-28), until he has read the list. It is decided when a reader is written, because
a reader is a file that works off a disk: turned on, it reaches a text at its next
rebuild, and a page written with it keeps it. Unset, a reader is byte for byte what it
was: no table, no script.
"""

from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path

_TABLE = Path(__file__).with_name("false_friends.json")

#: The switch, off unless the deployment says otherwise.
ENV = "TARGUM_FALSE_FRIENDS"


def is_on() -> bool:
    """Whether a reader written now carries the list. Off unless the deployment says so."""
    return os.environ.get(ENV, "").strip().lower() in {"1", "true", "yes"}


@cache
def table() -> dict[str, tuple[str, str]]:
    """What each French dictionary form looks like in English, and what it means."""
    rows = json.loads(_TABLE.read_text(encoding="utf-8"))["entries"]
    return {str(row["french"]): (str(row["looks_like"]), str(row["means"])) for row in rows}


def friend_of(lemma: str) -> list[str]:
    """`["actually", "currently"]` for a lemma on the list, `[]` for any other."""
    return list(table().get(lemma, ()))
