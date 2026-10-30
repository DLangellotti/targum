"""Russian aspect partners, from a list targum owns, ahead of OpenRussian's.

The card's "the other aspect" line was OpenRussian's partner column read as it stands
(`annotate/openrussian.py`), and on the commonest verbs it was wrong where a learner
looks first: знать → узнать, видеть → завидеть, ходить → сходить, and a run of verbs
that lead with a for-a-while or a begin verb no course calls a pair — стоять → постоять,
плакать → заплакать. Those nine wrong leads were 4.0% of every verb a reader taps, and the
procedural ones another 2.8% (ling-ru, 2026-10-30).

`aspect_partners.json` is the fix for the 300 commonest verbs in the built Russian texts,
55.6% of verb tokens: for each, the true partner or partners, or an explicit none, and
apart from them the **related** verbs a learner meets beside it with what each adds — for
a while (постоять), begin (заплакать), once (крикнуть), there and back (сходить), a
little (попить), the whole time (прожить). David decided both on 2026-10-30: the partner
line fixed now, and the procedural verbs on a line of their own, never as a partner.

**It is targum's own judgement**, written by ling-ru and shipped under targum's licence.
English Wiktionary and OpenRussian, both CC BY-SA, were read beside it as checks and
nothing of theirs is in it. Stress is marked as print marks it: U+0301 on a word of more
than one vowel, nothing on ё or on a word of one. **David has not read it yet**, and
`reviewed` says so until he has.

A verb on the list takes its partners from the list, even where the list says none; a
verb off it falls back to OpenRussian as before. Render time only: nothing is
re-annotated and no cache key moves.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import NamedTuple, Protocol

_TABLE = Path(__file__).with_name("aspect_partners.json")

#: What a related verb adds to the verb it is made from, in the order a card may name
#: them. `from` points the other way: on постоять's card, стоять is what it is made from.
KINDS = ("while", "bit", "start", "once", "trip", "through", "from")


class Entry(NamedTuple):
    partners: tuple[str, ...]
    related: tuple[tuple[str, str], ...]


def fold(lemma: str) -> str:
    """The key a lemma is filed under: lower case, ё as е, no stress mark."""
    return lemma.replace("́", "").lower().replace("ё", "е").strip()


@cache
def table() -> dict[str, Entry]:
    rows = json.loads(_TABLE.read_text(encoding="utf-8"))["entries"]
    return {
        fold(str(row["verb"])): Entry(
            tuple(str(partner) for partner in row["partners"]),
            tuple((str(verb), str(kind)) for verb, kind in row.get("related", [])),
        )
        for row in rows
    }


def listed(lemma: str) -> bool:
    return fold(lemma) in table()


def partners_of(lemma: str) -> tuple[str, ...] | None:
    """The list's partners for a verb on it — `()` where it says none — and None for a
    verb the list does not cover, which is OpenRussian's to answer."""
    entry = table().get(fold(lemma))
    return entry.partners if entry is not None else None


def related_of(lemma: str) -> tuple[tuple[str, str], ...]:
    """The verbs beside it that are not partners, each with its kind (`KINDS`)."""
    entry = table().get(fold(lemma))
    return entry.related if entry is not None else ()


def related_line(lemma: str) -> str:
    """The related verbs as a card's table carries them: "постоя́ть:while", several
    joined by " · ", or "" for none."""
    return " · ".join(f"{verb}:{kind}" for verb, kind in related_of(lemma))


class _Partners(Protocol):
    def partners(self, lemma: str) -> list[str]: ...


def partner_line(lemma: str, lexicon: _Partners | None, limit: int) -> tuple[list[str], bool]:
    """The partners a card names for a verb, and whether OpenRussian supplied them: the
    list's for a verb on it, a none included; OpenRussian's for the rest, where this
    machine has the tables; nothing otherwise. What the builder draws and what
    `scripts/eval_aspect_partners.py` scores are this one function."""
    own = partners_of(lemma)
    if own is not None:
        return list(own[:limit]), False
    if lexicon is None:
        return [], False
    quoted = lexicon.partners(lemma)[:limit]
    return quoted, bool(quoted)
