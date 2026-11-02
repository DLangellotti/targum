"""Your biggest grammar gap: What next's Grammar grid (design.md §12, "What next leads
with your biggest grammar gap", 2026-10-30; targum-internal#604).

A square is the share of the verb tokens of one binyan and one tense, in the sections a
reader finished, whose dictionary form they have marked known. Everything is read off
what a build already wrote: the tense in each Hebrew verb token's `feats`, and its binyan
where the annotation named one, or the CC0 paradigm table's where every verb it finds
agrees, kept beside each form in the occurrences cache. Nothing is annotated again,
nothing is bought, and nothing here is a source of truth.

The Mishkal list beside it (design.md §12, "The Mishkal list beside the Grammar grid",
2026-11-02) is the same arithmetic over Hebrew nouns and adjectives, a row a pattern on
ling-he's reviewed list (`annotate.mishkal`), read off the root lexicon the word card
reads. What next names one gap of the two (`lead`). Neither feeds the level ruler, the
ledger, "How much Hebrew you understand" or any headline count.
"""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
from typing import Any

from .coverage import IGNORED, KNOWN
from .level import known_percent

#: The seven binyanim, in the grid's order, keyed by the name the annotation stores
#: (`annotate.hebrew.binyan_of`) and said on the page by the key on the right.
BINYANIM: tuple[tuple[str, str], ...] = (
    ("פעל", "paal"),
    ("נפעל", "nifal"),
    ("פיעל", "piel"),
    ("פועל", "pual"),
    ("הפעיל", "hifil"),
    ("הופעל", "hufal"),
    ("התפעל", "hitpael"),
)

#: The grid's columns.
TENSES: tuple[str, ...] = ("past", "present", "future", "imperative", "infinitive")

_TENSE = {"Past": "past", "Pres": "present", "Fut": "future", "Imp": "imperative"}

#: A square with fewer verb tokens than this shows "—": a share of four forms says more
#: about which four than about the reader.
CELL_FLOOR = 10

#: A binyan needs this many verb tokens across its row to be named the gap.
ROW_FLOOR = 30

#: How many words a square lists when it is opened, and how many a gap offers as
#: examples for the page to choose two from.
WORDS = 12
EXAMPLES = 8


def tense_of(feats: str | None) -> str | None:
    """The grid's column for a verb's morphology, or None where it says no tense.

    The infinitive is `VerbForm=Inf`; a participle with no tense counts as Present,
    which is what a Hebrew participle is when it stands as a verb."""
    found: dict[str, str] = {}
    for part in (feats or "").split("|"):
        name, _, value = part.partition("=")
        if name:
            found[name] = value
    if found.get("VerbForm") == "Inf":
        return "infinitive"
    if found.get("Tense") in _TENSE:
        return _TENSE[found["Tense"]]
    if found.get("VerbForm") == "Part":
        return "present"
    return None


_KEYS = dict(BINYANIM)


@lru_cache(maxsize=65536)
def filled_binyan(lemma: str) -> str | None:
    """The binyan the CC0 paradigm table gives a verb lemma, or None.

    Since the DICTA swap the annotation names a binyan only where the lemma's letters
    cannot be anything else (`annotate.dicta._binyan_of`): three letters for pa'al and
    הת plus three for hitpa'el, so the other five were never named. The table finds a
    verb by any of its forms, and its binyan is read off the verb's own pointed lemma
    and forms (`paradigms.Table.binyan_of`). Taken only where every verb the table finds
    is in one binyan and the same one, the rule `verb_roots.filled` keeps for roots: a
    gap rather than a guess. Count time only; the annotation is never rewritten.
    """
    from .annotate.paradigms import bare, table

    book = table()
    found = book.candidates(bare(lemma))
    named = {book.binyan_of(lid) for lid in found}
    if len(named) != 1:
        return None
    return named.pop()


def verb_form(token: Mapping[str, Any]) -> tuple[str, str] | None:
    """(binyan key, tense) for a verb token whose binyan and tense are both known, or
    None. The binyan is the annotation's, and where it named none, the CC0 table's
    (`filled_binyan`)."""
    if token.get("pos") != "VERB":
        return None
    tense = tense_of(token.get("feats"))
    if tense is None:
        return None
    named = str(token.get("binyan") or "")
    if not named:
        named = filled_binyan(str(token.get("lemma") or "")) or ""
    binyan = _KEYS.get(named)
    if binyan is None:
        return None
    return binyan, tense


#: (binyan key, tense) -> dictionary form -> verb tokens met.
Forms = Mapping[tuple[str, str], Mapping[str, int]]


def grid(forms: Forms, marked: Mapping[str, int]) -> dict[str, Any] | None:
    """The Grammar grid and the gap, as the page draws them; None where no binyan has
    `ROW_FLOOR` tokens, and then the page shows the two lists alone.

    A word set aside as ignored comes out of the count, as it comes out of a text's
    share. Percentages are the page's exact ones (`level.known_percent`)."""
    rows: list[dict[str, Any]] = []
    totals: dict[str, tuple[int, int]] = {}
    for _name, key in BINYANIM:
        cells: dict[str, Any] = {}
        row_known = row_total = 0
        for tense in TENSES:
            met = {
                lemma: n
                for lemma, n in (forms.get((key, tense)) or {}).items()
                if marked.get(lemma) != IGNORED and n > 0
            }
            total = sum(met.values())
            known = sum(n for lemma, n in met.items() if marked.get(lemma) == KNOWN)
            row_known += known
            row_total += total
            if total < CELL_FLOOR:
                cells[tense] = None
                continue
            ordered = sorted(met.items(), key=lambda pair: (-pair[1], pair[0]))
            cells[tense] = {
                "known": known_percent(known / total),
                "tokens": total,
                "words": [
                    {"lemma": lemma, "count": n, "known": marked.get(lemma) == KNOWN}
                    for lemma, n in ordered[:WORDS]
                ],
            }
        totals[key] = (row_known, row_total)
        rows.append({"binyan": key, "cells": cells, "tokens": row_total})
    enough = [key for key, (_known, total) in totals.items() if total >= ROW_FLOOR]
    if not enough:
        return None
    answer: dict[str, Any] = {
        "rows": rows,
        "cellFloor": CELL_FLOOR,
        "rowFloor": ROW_FLOOR,
        "gap": None,
    }
    if len(enough) < 2:
        return answer

    def share(key: str) -> float:
        known, total = totals[key]
        return known / total

    weakest = min(enough, key=lambda key: (share(key), key))
    others_known = sum(totals[key][0] for key in enough if key != weakest)
    others_total = sum(totals[key][1] for key in enough if key != weakest)
    others = others_known / others_total
    if share(weakest) >= others:
        return answer
    examples: dict[str, int] = {}
    for tense in TENSES:
        for lemma, n in (forms.get((weakest, tense)) or {}).items():
            if marked.get(lemma) != IGNORED and n > 0:
                examples[lemma] = examples.get(lemma, 0) + n
    answer["gap"] = {
        "binyan": weakest,
        "known": known_percent(share(weakest)),
        "others": known_percent(others),
        "examples": _most_met(examples),
    }
    return answer


def _most_met(counted: Mapping[str, int]) -> list[str]:
    ordered = sorted(counted.items(), key=lambda pair: (-pair[1], pair[0]))
    return [lemma for lemma, _n in ordered[:EXAMPLES]]


#: pattern key -> dictionary form -> noun and adjective tokens met.
Patterns = Mapping[str, Mapping[str, int]]


def mishkal_list(patterns: Patterns, marked: Mapping[str, int]) -> dict[str, Any] | None:
    """The Mishkal list and its gap, as the page draws them; None where no pattern on the
    list was met at all.

    A row a pattern met at least once, in the list's fixed order (`annotate.mishkal`),
    each one square: the share of its tokens whose word is known, or None under
    `CELL_FLOOR`. A pattern needs `ROW_FLOOR` tokens to be named the gap, as a binyan
    does; the weakest of those is the gap where it sits under the others pooled.
    """
    from .annotate.mishkal import PATTERNS, template

    rows: list[dict[str, Any]] = []
    totals: dict[str, tuple[int, int]] = {}
    kept: dict[str, dict[str, int]] = {}
    for key, _templates in PATTERNS:
        met = {
            lemma: n
            for lemma, n in (patterns.get(key) or {}).items()
            if marked.get(lemma) != IGNORED and n > 0
        }
        total = sum(met.values())
        if not total:
            continue
        known = sum(n for lemma, n in met.items() if marked.get(lemma) == KNOWN)
        totals[key] = (known, total)
        kept[key] = met
        row: dict[str, Any] = {"pattern": key, "template": template(key), "tokens": total}
        if total < CELL_FLOOR:
            row["known"] = None
            row["words"] = []
        else:
            ordered = sorted(met.items(), key=lambda pair: (-pair[1], pair[0]))
            row["known"] = known_percent(known / total)
            row["words"] = [
                {"lemma": lemma, "count": n, "known": marked.get(lemma) == KNOWN}
                for lemma, n in ordered[:WORDS]
            ]
        rows.append(row)
    if not rows:
        return None
    answer: dict[str, Any] = {
        "rows": rows,
        "cellFloor": CELL_FLOOR,
        "rowFloor": ROW_FLOOR,
        "gap": None,
    }
    enough = [key for key, (_known, total) in totals.items() if total >= ROW_FLOOR]
    if len(enough) < 2:
        return answer

    def share(key: str) -> float:
        known, total = totals[key]
        return known / total

    weakest = min(enough, key=lambda key: (share(key), key))
    others_known = sum(totals[key][0] for key in enough if key != weakest)
    others_total = sum(totals[key][1] for key in enough if key != weakest)
    others = others_known / others_total
    if share(weakest) >= others:
        return answer
    answer["gap"] = {
        "pattern": weakest,
        "template": template(weakest),
        "known": known_percent(share(weakest)),
        "others": known_percent(others),
        "examples": _most_met(kept[weakest]),
    }
    return answer


def lead(grammar: Mapping[str, Any] | None, mishkal: Mapping[str, Any] | None) -> str | None:
    """Which gap What next names: "binyan", "mishkal" or None.

    Raw shares are not compared across the two kinds, since noun patterns run higher than
    verb forms. Each gap is measured against the other common patterns of its own kind,
    and the one further under them is named; a tie goes to the binyan (David,
    2026-11-02)."""
    verbs = (grammar or {}).get("gap")
    nouns = (mishkal or {}).get("gap")
    if verbs and nouns:
        # In the points the two sentences say ("31%, against 80%"), so a tie is one a
        # reader could see.
        further = nouns["others"] - nouns["known"] > verbs["others"] - verbs["known"]
        return "mishkal" if further else "binyan"
    if verbs:
        return "binyan"
    if nouns:
        return "mishkal"
    return None
