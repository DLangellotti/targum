"""A Hebrew noun's or adjective's headword, where the annotator gave another of its forms.

DICTA sometimes files a plural or a feminine under itself: עצים under עצים, לירות under
לירות, צעירות under צעירה rather than צעיר (ling-he's analyser read, targum-internal#697e).
The meaning is bought and looked up under the lemma, so such a card says it has no
meaning. Taking the ending off by rule would be wrong as often as right, because a great
many singulars end the way plurals do (חנות, מלכות, חיים, מים), so the answer is looked up.

The table is Wikidata's lexemes, CC0, the same source as the verb tables
(`paradigms.py`), written by `scripts/hebrew_nouns.py`. Each part of speech's forms map
to their one headword, bare, and a spelling that is itself a headword is never in it.
A build with no table reduces nothing rather than failing.
"""

from __future__ import annotations

import gzip
import json
from functools import lru_cache
from pathlib import Path

#: Beside this module, so the wheel carries it and a reader never fetches it.
TABLE = Path(__file__).parent / "nouns.json.gz"

#: The parts of speech the table answers for, in the tagger's own names.
PARTS = frozenset({"NOUN", "ADJ"})

#: Spellings the table files under a headword they are seldom the form of, found by
#: reading every change it made over the laptop's 483 Hebrew texts (2026-11-18): each is
#: kept as DICTA gave it. ימות is יום's ("ימות המשיח") and not ימה's; אמהות "mothers"
#: and אמות, which is as often the Talmud's cubits, are no אמה's or אם's to guess at;
#: שניים and שנים are the number as often as not; רבות is mostly "many"; לחיים is
#: "cheers" as often as "cheeks"; בעלים "owner", עשירות "wealth", בכירות "seniority" and
#: קרות "coldness" are words of their own; a people is not its country (אירופאים,
#: ונצואלית), and הגויות is no הגות's.
KEPT = frozenset(
    {
        "ימות",
        "אמהות",
        "אמות",
        "שניים",
        "שנים",
        "רבות",
        "לחיים",
        "בעלים",
        "עשירות",
        "בכירות",
        "קרות",
        "אירופאים",
        "ונצואלית",
        "הגויות",
    }
)


@lru_cache(maxsize=1)
def _forms() -> dict[str, dict[str, str]]:
    try:
        with gzip.open(TABLE, "rt", encoding="utf-8") as raw:
            loaded = json.load(raw)
    except (OSError, ValueError):
        return {}
    forms = loaded.get("forms") if isinstance(loaded, dict) else None
    if not isinstance(forms, dict):
        return {}
    return {
        str(pos): {str(k): str(v) for k, v in table.items()}
        for pos, table in forms.items()
        if isinstance(table, dict)
    }


def headword(lemma: str, pos: str | None) -> str | None:
    """The headword `lemma` is a form of, for a noun or an adjective; None where the
    lemma is a headword already, or where the table does not say."""
    if pos not in PARTS or not lemma or lemma in KEPT:
        return None
    found = _forms().get(pos, {}).get(lemma)
    return found if found and found != lemma else None


__all__ = ["KEPT", "PARTS", "TABLE", "headword"]
