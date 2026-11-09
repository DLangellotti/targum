"""Russian grammar on Your Progress: aspect, case and More (design.md §12, "Russian
grammar on Your Progress", 2026-11-09; targum-internal#639).

Hebrew's What next has a Grammar grid and a Mishkal list (`gaps.py`). This is Russian's,
on the same arithmetic: a square is the share of the tokens of one kind, in the sections
a reader finished, whose dictionary form they have marked known. Six views, as David
chose them from ling-ru's list on 2026-11-06 and passed design's mock on 2026-11-09:

- **Aspect × tense**, with **aspect pairs** under it (the Aspect tab);
- **Case × number**, the accusative split animate and inanimate, with **where and where
  to** (в, на, за, под by где? and куда?) under it (the Cases tab);
- under both, in More: **verbs of motion** (pooled one way and there and back, and each
  pair known or not), **nouns in -ь** (feminine and masculine) and **participles and
  gerunds** by aspect.

Everything is read off what the free Russian annotator already stored in each token's
`feats` (Case, Number, Gender, Animacy, Aspect, Tense, VerbForm, Mood), its part of speech
and its lemma: nothing is annotated again, nothing is bought, and no cache key moves but
`occurrences.VERSION`, which is free. What the annotator does not give is left out rather
than guessed: a biaspectual verb (no Aspect), a vocative, a participle the suffix rule
cannot sort, a neuter -ь noun. Only an aspect row or a case row can be named the gap;
where and where to is read by adjacency, not a parse, and is never the gap.

Nothing here feeds the level ruler, the ledger or any headline count.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .annotate.aspect_partners import fold, table
from .annotate.motion import PAIRS as MOTION_PAIRS
from .annotate.motion import motion_of
from .coverage import IGNORED, KNOWN
from .gaps import CELL_FLOOR, EXAMPLES, ROW_FLOOR, TENSES, WORDS
from .level import known_percent

#: The aspect grid's rows; its columns are Hebrew's five (`gaps.TENSES`).
ASPECTS: tuple[str, ...] = ("imperfective", "perfective")
_ASPECT = {"Imp": "imperfective", "Perf": "perfective"}

#: The case grid's rows: the six cases, the accusative split by animacy. The partitive
#: folds into the genitive and the second locative into the prepositional; the vocative is
#: left out.
CASES: tuple[str, ...] = ("nom", "gen", "dat", "acc", "acca", "ins", "loc")
_CASE = {
    "Nom": "nom",
    "Gen": "gen",
    "Par": "gen",
    "Dat": "dat",
    "Acc": "acc",
    "Ins": "ins",
    "Loc": "loc",
}
NUMBERS: tuple[str, ...] = ("sing", "plur")
_NUMBER = {"Sing": "sing", "Plur": "plur"}

#: Where and where to: four prepositions, by где? and куда?.
PREPOSITIONS: tuple[str, ...] = ("v", "na", "za", "pod")
_PREPOSITION = {"в": "v", "во": "v", "на": "na", "за": "za", "под": "pod", "подо": "pod"}
PLACES: tuple[str, ...] = ("where", "whereto")
#: The case each preposition says "where" with; every one says "where to" with the
#: accusative. Any other case after it is left out.
_WHERE = {"v": "Loc", "na": "Loc", "za": "Ins", "pod": "Ins"}
#: How far after the preposition its word may stand: an adjective or two between.
_REACH = 3

#: Verbs of motion: one row, every pair pooled, one way and there and back.
WAYS: tuple[str, ...] = ("one", "back")

#: Nouns in -ь, by gender; a neuter one is tagger noise and left out.
GENDERS: tuple[str, ...] = ("fem", "masc")
_GENDER = {"Fem": "fem", "Masc": "masc"}

#: Participles and gerunds, by aspect.
FORMS: tuple[str, ...] = ("partact", "partpass", "short", "gerund")

#: The views a token can be counted in, and the ones that can name the gap.
VIEWS: tuple[str, ...] = ("aspect", "cases", "place", "motion", "soft", "forms")

# Voice is not stored, so a full participle is sorted by its suffix, as a course teaches
# it: -вш-, -ш- after a consonant, -ущ-, -ющ-, -ащ-, -ящ- active; -нн-, -т-, -ем-, -им-,
# -ом- passive. What neither matches is left out, and the note says so.
_ACTIVE = re.compile(
    r"(?:вш|(?<=[бгджзклмнпрстфхцчщ])ш|ущ|ющ|ащ|ящ)"
    r"(?:ий|ая|ее|ие|его|ей|ему|им|ую|ем|их|ими)(?:ся|сь)?$"
)
_PASSIVE = re.compile(r"(?:нн|т|ем|им|ом)(?:ый|ая|ое|ые|ого|ой|ому|ым|ую|ом|ых|ыми)$")

_VERBS = frozenset({"VERB", "AUX"})
_NOMINALS = frozenset({"NOUN", "ADJ", "PRON"})


def feats_of(raw: str | None) -> dict[str, str]:
    """A token's `feats` string as a map: "UPOS=VERB|Aspect=Perf" -> {"UPOS": "VERB", …}."""
    found: dict[str, str] = {}
    for part in (raw or "").split("|"):
        name, _, value = part.partition("=")
        if name:
            found[name] = value
    return found


def _surface(token: Mapping[str, Any]) -> str:
    return str(token.get("surface") or "").lower()


def _is_bud(token: Mapping[str, Any], feats: Mapping[str, str]) -> bool:
    """A finite буд- form of быть: the tagger stores будет as `Tense=Pres` (ling-ru,
    2026-11-06), so the future is read off the spelling."""
    return (
        str(token.get("lemma") or "").lower() == "быть"
        and feats.get("VerbForm", "Fin") == "Fin"
        and _surface(token).startswith("буд")
    )


def participle_of(surface: str, feats: Mapping[str, str]) -> str | None:
    """Which row of participles and gerunds a verb form is, or None: a gerund, a short
    participle (one with no case), or a full one the suffix rule sorts."""
    form = feats.get("VerbForm")
    if form == "Conv":
        return "gerund"
    if form != "Part":
        return None
    if not feats.get("Case"):
        return "short"
    if _ACTIVE.search(surface):
        return "partact"
    if _PASSIVE.search(surface):
        return "partpass"
    return None


def _tense(token: Mapping[str, Any], feats: Mapping[str, str], aspect: str) -> str | None:
    """The aspect grid's column for a finite verb, an imperative or an infinitive."""
    if feats.get("VerbForm") == "Inf":
        return "infinitive"
    if feats.get("Mood") == "Imp" or feats.get("Tense") == "Imp":
        return "imperative"
    tense = feats.get("Tense")
    if tense == "Past":
        return "past"
    if tense == "Fut":
        return "future"
    if tense == "Pres":
        # A perfective has no present: what the tagger stored as one is its future, and
        # never lands in the no-such-form square (ling-ru, 2026-11-06).
        if aspect == "perfective" or _is_bud(token, feats):
            return "future"
        return "present"
    return None


Cell = tuple[str, str]


def classify(run: Sequence[Mapping[str, Any]]) -> list[list[Cell]]:
    """For each token of one segment, the squares it is counted in, as (square, form met).

    A square is "view:row:col" ("aspect:perfective:past", "soft:fem" for a view with one
    column). The form is what the page lists: the word as written, lower case, and for a
    compound future or a preposition's word the phrase ("буду читать", "в доме"). The
    segment is read whole because two of the views need their neighbours: an
    imperfective infinitive after a буд- form is that verb's future, and a preposition
    gives its case's word a place.
    """
    feats = [feats_of(token.get("feats")) for token in run]
    out: list[list[Cell]] = [[] for _ in run]
    # A compound future: буду, будешь… then an imperfective infinitive, directly or with
    # one word between. The infinitive is that verb's future, and its буд- form is the
    # auxiliary rather than быть's own future, so it is not counted twice.
    future_of: dict[int, str] = {}
    auxiliary: set[int] = set()
    for at, token in enumerate(run):
        if str(token.get("pos") or "") not in _VERBS or not _is_bud(token, feats[at]):
            continue
        for ahead in (at + 1, at + 2):
            if ahead >= len(run):
                break
            said = feats[ahead]
            if (
                str(run[ahead].get("pos") or "") == "VERB"
                and said.get("VerbForm") == "Inf"
                and said.get("Aspect") == "Imp"
            ):
                future_of[ahead] = " ".join(_surface(run[n]) for n in range(at, ahead + 1))
                auxiliary.add(at)
                break
    for at, token in enumerate(run):
        pos = str(token.get("pos") or "")
        said = feats[at]
        lemma = str(token.get("lemma") or "")
        surface = _surface(token)
        if pos in _VERBS:
            aspect = _ASPECT.get(said.get("Aspect", ""), "")
            row = participle_of(surface, said)
            if aspect and said.get("VerbForm") in ("Part", "Conv"):
                if row:
                    out[at].append((f"forms:{row}:{aspect}", surface))
            elif aspect and at not in auxiliary:
                if at in future_of:
                    out[at].append((f"aspect:{aspect}:future", future_of[at]))
                elif tense := _tense(token, said, aspect):
                    out[at].append((f"aspect:{aspect}:{tense}", surface))
            if pos == "VERB" and (way := motion_of(lemma)):
                out[at].append(
                    (f"motion:all:{'one' if way.startswith('one') else 'back'}", surface)
                )
        if pos in ("NOUN", "ADJ"):
            case = _CASE.get(said.get("Case", ""))
            number = _NUMBER.get(said.get("Number", ""))
            if case and number:
                animate = said.get("Animacy") == "Anim"
                if case == "acc" and pos == "NOUN" and animate:
                    case = "acca"
                # An adjective agreeing with an animate noun is not split, since no head
                # is stored: it is left out of both accusative rows rather than counted
                # as inanimate.
                if not (case == "acc" and pos == "ADJ" and animate):
                    out[at].append((f"cases:{case}:{number}", surface))
        if pos == "NOUN" and lemma.endswith("ь"):
            gender = _GENDER.get(said.get("Gender", ""))
            if gender:
                out[at].append((f"soft:{gender}", surface))
        if pos == "ADP":
            preposition = _PREPOSITION.get(lemma.lower())
            if preposition:
                for ahead in range(at + 1, min(at + 1 + _REACH, len(run))):
                    case_said = feats[ahead].get("Case")
                    if not case_said:
                        continue
                    if str(run[ahead].get("pos") or "") in _NOMINALS:
                        column = (
                            "where"
                            if case_said == _WHERE[preposition]
                            else "whereto"
                            if case_said == "Acc"
                            else ""
                        )
                        if column:
                            phrase = " ".join(_surface(run[n]) for n in range(at, ahead + 1))
                            out[ahead].append((f"place:{preposition}:{column}", phrase))
                    break
    return out


#: square -> (dictionary form, form met) -> tokens met.
Forms = Mapping[str, Mapping[tuple[str, str], int]]

Meaning = Callable[[str], str]


def _none(_lemma: str) -> str:
    return ""


def _square(
    met: Mapping[tuple[str, str], int], marked: Mapping[str, int], meaning: Meaning
) -> tuple[dict[str, Any] | None, int, int]:
    """One square, and the known and total tokens under it whether or not it says a
    figure. The words listed are the forms met, most met first, each with its dictionary
    form, whether that is known, and its meaning where the glossary already holds one."""
    kept = {pair: n for pair, n in met.items() if marked.get(pair[0]) != IGNORED and n > 0}
    total = sum(kept.values())
    known = sum(n for (lemma, _form), n in kept.items() if marked.get(lemma) == KNOWN)
    if total < CELL_FLOOR:
        return None, known, total
    ordered = sorted(kept.items(), key=lambda item: (-item[1], item[0][1], item[0][0]))
    return (
        {
            "known": known_percent(known / total),
            "tokens": total,
            "words": [
                {
                    "lemma": lemma,
                    "form": form,
                    "count": n,
                    "known": marked.get(lemma) == KNOWN,
                    "meaning": meaning(lemma),
                }
                for (lemma, form), n in ordered[:WORDS]
            ],
        },
        known,
        total,
    )


def _key(view: str, row: str, column: str) -> str:
    return ":".join(part for part in (view, row, column) if part)


def _grid(
    view: str,
    rows: Sequence[str],
    columns: Sequence[str],
    forms: Forms,
    marked: Mapping[str, int],
    meaning: Meaning,
) -> tuple[list[dict[str, Any]], dict[str, tuple[int, int]]]:
    out: list[dict[str, Any]] = []
    totals: dict[str, tuple[int, int]] = {}
    for row in rows:
        cells: dict[str, Any] = {}
        row_known = row_total = 0
        for column in columns:
            cell, known, total = _square(forms.get(_key(view, row, column)) or {}, marked, meaning)
            cells[column or "all"] = cell
            row_known += known
            row_total += total
        totals[row] = (row_known, row_total)
        out.append({"row": row, "cells": cells, "tokens": row_total})
    return out, totals


def _enough(totals: Mapping[str, tuple[int, int]]) -> list[str]:
    return [row for row, (_known, total) in totals.items() if total >= ROW_FLOOR]


def _gap(
    view: str,
    totals: Mapping[str, tuple[int, int]],
    forms: Forms,
    columns: Sequence[str],
    marked: Mapping[str, int],
    meaning: Meaning,
) -> dict[str, Any] | None:
    """The weakest row with `ROW_FLOOR` tokens, where it sits under the others pooled, as
    `gaps.grid` finds a binyan's; None with fewer than two such rows."""
    enough = _enough(totals)
    if len(enough) < 2:
        return None

    def share(row: str) -> float:
        known, total = totals[row]
        return known / total

    weakest = min(enough, key=lambda row: (share(row), row))
    others_known = sum(totals[row][0] for row in enough if row != weakest)
    others_total = sum(totals[row][1] for row in enough if row != weakest)
    others = others_known / others_total
    if share(weakest) >= others:
        return None
    counted: dict[str, int] = {}
    shown: dict[str, tuple[int, str]] = {}
    for column in columns:
        for (lemma, form), n in (forms.get(_key(view, weakest, column)) or {}).items():
            if marked.get(lemma) == IGNORED or n <= 0:
                continue
            counted[lemma] = counted.get(lemma, 0) + n
            if n > shown.get(lemma, (0, ""))[0]:
                shown[lemma] = (n, form)
    ordered = sorted(counted.items(), key=lambda pair: (-pair[1], pair[0]))[:EXAMPLES]
    return {
        "row": weakest,
        "known": known_percent(share(weakest)),
        "others": known_percent(others),
        "examples": [
            {"lemma": lemma, "form": shown[lemma][1], "meaning": meaning(lemma)}
            for lemma, _n in ordered
        ],
    }


def _view(
    view: str,
    rows: Sequence[str],
    columns: Sequence[str],
    forms: Forms,
    marked: Mapping[str, int],
    meaning: Meaning,
    gap: bool = False,
) -> dict[str, Any] | None:
    """A view's rows, drawn once one row has `ROW_FLOOR` tokens; None under that."""
    drawn, totals = _grid(view, rows, columns, forms, marked, meaning)
    if not _enough(totals):
        return None
    return {
        "rows": drawn,
        "gap": _gap(view, totals, forms, columns, marked, meaning) if gap else None,
    }


def _verbs_met(forms: Forms) -> dict[str, dict[str, int]]:
    """Each verb lemma met, with its tokens by aspect: off the aspect grid and the
    participles, so a verb is counted once a token."""
    out: dict[str, dict[str, int]] = {}
    for square, met in forms.items():
        view, _, rest = square.partition(":")
        if view == "aspect":
            aspect = rest.split(":", 1)[0]
        elif view == "forms":
            aspect = rest.rsplit(":", 1)[-1]
        else:
            continue
        for (lemma, _form), n in met.items():
            if n > 0:
                held = out.setdefault(lemma, {})
                held[aspect] = held.get(aspect, 0) + n
    return out


#: How many aspect pairs the list shows; the rest are counted in its line.
PAIR_ROWS = 4


def _status(first: bool, second: bool, names: tuple[str, str]) -> str:
    if first and second:
        return "both"
    if first:
        return names[0]
    if second:
        return names[1]
    return "neither"


def aspect_pairs(
    forms: Forms, marked: Mapping[str, int], meaning: Meaning = _none
) -> dict[str, Any] | None:
    """The aspect pairs on ling-ru's reviewed list (`annotate/aspect_partners.json`)
    whose two halves the reader has both met, and whether they know one, both or neither;
    None with no such pair.

    A pair's imperfective and perfective are the aspects its verbs were met in. A pair
    with one half known comes first, the most met first, then those with neither, then
    those with both: what is one verb from done leads. `PAIR_ROWS` are listed; the line
    counts all of them."""
    verbs = _verbs_met(forms)
    if not verbs:
        return None
    by_fold: dict[str, str] = {}
    for lemma in verbs:
        by_fold.setdefault(fold(lemma), lemma)

    def aspect_of(lemma: str) -> str:
        held = verbs[lemma]
        return max(held, key=lambda aspect: (held[aspect], aspect))

    seen: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for verb, entry in table().items():
        mine = by_fold.get(verb)
        if mine is None:
            continue
        for partner in entry.partners:
            theirs = by_fold.get(fold(partner))
            if theirs is None or theirs == mine:
                continue
            aspects = {mine: aspect_of(mine), theirs: aspect_of(theirs)}
            if aspects[mine] == aspects[theirs]:
                continue
            imperfective = mine if aspects[mine] == "imperfective" else theirs
            perfective = theirs if imperfective == mine else mine
            if (imperfective, perfective) in seen:
                continue
            seen.add((imperfective, perfective))
            rows.append(
                {
                    "imperfective": imperfective,
                    "perfective": perfective,
                    "known": _status(
                        marked.get(imperfective) == KNOWN,
                        marked.get(perfective) == KNOWN,
                        ("imperfective", "perfective"),
                    ),
                    "count": sum(verbs[imperfective].values()) + sum(verbs[perfective].values()),
                }
            )
    if not rows:
        return None
    order = {"imperfective": 0, "perfective": 0, "neither": 1, "both": 2}
    rows.sort(key=lambda row: (order[row["known"]], -row["count"], row["imperfective"]))
    for row in rows[:PAIR_ROWS]:
        row["meaning"] = meaning(row["imperfective"]) or meaning(row["perfective"])
    return {
        "met": len(rows),
        "both": sum(1 for row in rows if row["known"] == "both"),
        "rows": rows[:PAIR_ROWS],
    }


def motion(
    forms: Forms, marked: Mapping[str, int], meaning: Meaning = _none
) -> dict[str, Any] | None:
    """Verbs of motion: the two pooled squares, one way and there and back, and each of
    the fourteen pairs met (`annotate.motion`), in the list's order, its verbs known or
    not. A pair is one dictionary word each way, so its row says known or not, never a
    share. None until the pooled row has `ROW_FLOOR` tokens."""
    drawn, totals = _grid("motion", ("all",), WAYS, forms, marked, meaning)
    if not _enough(totals):
        return None
    met: set[str] = set()
    for way in WAYS:
        for (lemma, _form), n in (forms.get(_key("motion", "all", way)) or {}).items():
            if n > 0:
                met.add(lemma.replace("ё", "е"))
    pairs = []
    for one, back in MOTION_PAIRS:
        if one not in met and back not in met:
            continue
        pairs.append(
            {
                "one": one,
                "back": back,
                "known": _status(
                    marked.get(one) == KNOWN, marked.get(back) == KNOWN, ("one", "back")
                ),
                "meaning": meaning(one),
            }
        )
    return {"cells": drawn[0]["cells"], "tokens": drawn[0]["tokens"], "pairs": pairs}


def soft_nouns(
    forms: Forms, marked: Mapping[str, int], meaning: Meaning = _none
) -> dict[str, Any] | None:
    """Nouns in -ь, feminine and masculine, one square a row in the Mishkal list's shape,
    each with the three commonest such nouns the reader met; None until a row has
    `ROW_FLOOR` tokens."""
    drawn, totals = _grid("soft", GENDERS, ("",), forms, marked, meaning)
    if not _enough(totals):
        return None
    for row in drawn:
        counted: dict[str, int] = {}
        for (lemma, _form), n in (forms.get(_key("soft", row["row"], "")) or {}).items():
            if marked.get(lemma) != IGNORED and n > 0:
                counted[lemma] = counted.get(lemma, 0) + n
        row["examples"] = [
            lemma for lemma, _n in sorted(counted.items(), key=lambda pair: (-pair[1], pair[0]))[:3]
        ]
    return {"rows": drawn}


def lead(aspect: Mapping[str, Any] | None, cases: Mapping[str, Any] | None) -> str | None:
    """Which gap What next names: "aspect", "cases" or None. Each is measured against its
    own kind and the one further under it is named, a tie going to aspect, as
    `gaps.lead` weighs a binyan against a mishkal."""
    verbs = (aspect or {}).get("gap")
    nouns = (cases or {}).get("gap")
    if verbs and nouns:
        further = nouns["others"] - nouns["known"] > verbs["others"] - verbs["known"]
        return "cases" if further else "aspect"
    if verbs:
        return "aspect"
    if nouns:
        return "cases"
    return None


def progress(
    forms: Forms, marked: Mapping[str, int], meaning: Meaning = _none
) -> dict[str, Any] | None:
    """Russian's Grammar on What next, as the page draws it; None where neither the
    aspect grid nor the case grid has a row with `ROW_FLOOR` tokens, and then the page
    shows the two lists alone, with no More either.

    A tab's companion is drawn only with its tab's grid; More's three only when one of
    their rows has `ROW_FLOOR` tokens."""
    seen: dict[str, str] = {}

    def said(lemma: str) -> str:
        if lemma not in seen:
            seen[lemma] = meaning(lemma)
        return seen[lemma]

    aspect = _view("aspect", ASPECTS, TENSES, forms, marked, said, gap=True)
    cases = _view("cases", CASES, NUMBERS, forms, marked, said, gap=True)
    if aspect is None and cases is None:
        return None
    return {
        "aspect": aspect,
        "pairs": aspect_pairs(forms, marked, said) if aspect else None,
        "cases": cases,
        # Read by adjacency, not a parse: never the gap (David, 2026-11-09).
        "place": _view("place", PREPOSITIONS, PLACES, forms, marked, said) if cases else None,
        "motion": motion(forms, marked, said),
        "soft": soft_nouns(forms, marked, said),
        "forms": _view("forms", FORMS, ASPECTS, forms, marked, said),
        "lead": lead(aspect, cases),
        "cellFloor": CELL_FLOOR,
        "rowFloor": ROW_FLOOR,
    }
