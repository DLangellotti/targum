"""Where a reader is, said in levels of text they could open (design.md §12, "Your level
leads with what you can read", 2026-10-28, which replaced "Your Progress is a story in
three parts"'s ladder of kinds, 2026-10-09).

David, 2026-10-28: kinds of text don't have one difficulty — an easy video is easier than
a hard conversation — so the ladder is the texts' own measured levels, Beginner · A1, A2,
B1 and B2 and up (`levelmap.text_level`, the rule `levelmap.cefr_rows` counts the shelf
by). Each row counts the texts at that level this reader could read now, by the Library's
Read it now measure (90% of a text's words known), so the number on a row is the number
on the shelf it opens; a level is easy for you where most of its measured texts are.
Aramaic climbs its Targums instead (2026-10-25), which no level has been measured for.

Nothing on the page is a percentage. Everything here is arithmetic over the catalogue and
the lemma index beside it, with nothing fetched and nothing spent.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from statistics import median
from typing import Any

from .coverage import Index

#: The rows of a modern ladder, easiest first: the texts' own levels.
LEVELS = ("A1", "A2", "B1", "B2+")

#: No ladder at all. Aramaic was here from 2026-10-08, when wordfreq's missing list made
#: every Aramaic text measure 0; it climbs `aramaic_ladder` since the shelf's own Aramaic
#: was counted (`annotate.aramaic_frequency`, targum-internal G1; design.md §12, "Aramaic
#: gets a ladder, from our own counts", 2026-10-25).
NO_LADDER: frozenset[str] = frozenset()

#: Aramaic's rungs, in the order ling-arc's plan climbs them (2026-10-25): the shelf's
#: Aramaic is all prose and poetry by the catalogue's kinds, so a rung is a body of Targum
#: rather than a kind of text. Each is named by the test a source passes.
ARAMAIC_FAMILIES: tuple[tuple[str, Callable[[str], bool]], ...] = (
    ("onkelos", lambda book: "Targum" not in book),
    (
        "former-prophets",
        lambda book: (
            book.startswith("Targum Jonathan on ")
            and book.removeprefix("Targum Jonathan on ")
            in {"Joshua", "Judges", "I Samuel", "II Samuel", "I Kings", "II Kings"}
        ),
    ),
    (
        "jonathan-torah",
        lambda book: (
            book.startswith("Targum Jonathan on ")
            and book.removeprefix("Targum Jonathan on ")
            in {"Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy"}
        ),
    ),
    ("latter-prophets", lambda book: book.startswith("Targum Jonathan on ")),
    ("writings", lambda book: book.startswith(("Aramaic Targum to ", "Targum of "))),
)


def aramaic_family(source: str) -> str | None:
    """Which body of Targum an Aramaic source belongs to, or None for anything else."""
    if not source.startswith("sefaria:arc:"):
        return None
    book = source.removeprefix("sefaria:arc:")
    for family, belongs in ARAMAIC_FAMILIES:
        if belongs(book):
            return family
    return None


def aramaic_ladder(entries: Iterable[Any]) -> list[Rung]:
    """Aramaic's rungs, easiest first, by the median measured difficulty of each family.

    The same rule as `ladder`: a family with no measured text is not a rung, and ties keep
    the plan's order. Measured on 2026-10-25 off the counted list, Onkelos's five books
    came out at 9 to 13, Jonathan on the Former Prophets 11 to 14, on the Torah 16 to 20,
    the Latter Prophets 11 to 28 and the Writings 14 to 37 — the order ling-arc's plan
    climbs, found rather than assumed.
    """
    order = [family for family, _ in ARAMAIC_FAMILIES]
    by_family: dict[str, list[Any]] = {}
    for entry in entries:
        if str(getattr(entry, "language", "")) != "arc":
            continue
        family = aramaic_family(str(getattr(entry, "source", "")))
        if family is not None:
            by_family.setdefault(family, []).append(entry)
    rungs: list[Rung] = []
    for family, members in by_family.items():
        measured = [int(getattr(m, "difficulty", 0) or 0) for m in members]
        measured = [d for d in measured if d > 0]
        if not measured:
            continue
        rungs.append(
            Rung(
                kind=family,
                name=family,
                difficulty=float(median(measured)),
                texts=tuple(str(m.id) for m in members),
            )
        )
    rungs.sort(key=lambda rung: (rung.difficulty, order.index(rung.kind)))
    return rungs


#: A text is on the Library's Read it now shelf from this share of its words (percent).
NEARLY = 90

#: How many texts "Texts at your level now" names, and how many words the other half.
TEXTS = 3
WORDS = 5
#: A word met in fewer texts than this is not one you "keep meeting".
OFTEN = 2


@dataclass(frozen=True)
class Rung:
    """One row of a language's ladder: a level of text, or for Aramaic a body of Targum."""

    kind: str
    name: str
    difficulty: float
    texts: tuple[str, ...]


def in_language(entry: Any, language: str) -> bool:
    """Whether a row is on this language's shelf, as `inLanguage` in library.js reads it:
    any of the languages it is written in."""
    codes = getattr(entry, "languages", None) or [getattr(entry, "language", "")]
    return language in {str(code).split("-")[0].lower() for code in codes}


def ladder(
    entries: Iterable[Any], language: str, level_of: Callable[[Any], str] | None = None
) -> list[Rung]:
    """A language's rows, easiest first: each level of text it has a measured text at.

    A level with nothing on this language's shelf is not a row. Empty for a language the
    library has nothing measured in. Aramaic's rows are bodies of Targum
    (`aramaic_ladder`). `level_of` says a text's level; `levelmap.text_level` by default.
    """
    if language in NO_LADDER:
        return []
    if language == "arc":
        return aramaic_ladder(entries)
    if level_of is None:
        from .levelmap import text_level

        level_of = text_level
    by_level: dict[str, list[str]] = {}
    for entry in entries:
        if not in_language(entry, language):
            continue
        level = level_of(entry)
        if level in LEVELS:
            by_level.setdefault(level, []).append(str(entry.id))
    return [
        Rung(kind=level, name=level, difficulty=float(at), texts=tuple(by_level[level]))
        for at, level in enumerate(LEVELS)
        if by_level.get(level)
    ]


def percent(share: float) -> int:
    """A share as the whole percentage the page prints, never rounded up into a band:
    89.6% is "most of", not "nearly all of"."""
    return max(0, min(100, int(share * 100)))


def standing(rungs: list[Rung], known_of: Callable[[str], float | None]) -> dict[str, Any]:
    """The ladder as the page draws it: each row easy, the next step or not yet, and how
    many of its texts the reader could read now.

    `known_of` answers a text's share of words known the way the Library does (a built
    copy's own measure over the catalogue's, None where nothing was measured), so a row's
    count is the Library's Read it now at that level. A row is easy for you where more
    than half its measured texts are on that shelf, and so is every row below the hardest
    easy one: the ladder climbs. The next step is the row after it, or the first row where
    none is easy yet.
    """
    counts: list[int] = []
    easy: list[bool] = []
    for rung in rungs:
        shares = [known_of(entry_id) for entry_id in rung.texts]
        measured = [share for share in shares if share is not None]
        readable = sum(1 for share in measured if share * 100 >= NEARLY)
        counts.append(readable)
        easy.append(bool(measured) and readable * 2 > len(measured))

    here: int | None = None
    for at, yes in enumerate(easy):
        if yes:
            here = at
    following: int | None
    if here is None:
        following = 0 if rungs else None
    else:
        following = here + 1 if here + 1 < len(rungs) else None

    out = []
    for at, rung in enumerate(rungs):
        if here is not None and at <= here:
            state = "easy"
        elif at == following:
            state = "next"
        else:
            state = "ahead"
        out.append(
            {
                "kind": rung.kind,
                "name": rung.name,
                "state": state,
                "texts": len(rung.texts),
                "readable": counts[at],
            }
        )
    return {"ladder": out, "here": here, "next": following}


def at_level(
    entries: Iterable[Any],
    index: Index,
    marked: Mapping[str, int],
    language: str,
    ui_language: str = "en",
    limit: int = TEXTS,
) -> list[dict[str, Any]]:
    """Texts this reader could read now: 90% of their words known and up, the share the
    Library's Read it now shelf uses, so the two pages never disagree about a text. The
    nearest to the line first, because a text at 99% teaches nothing."""
    found: list[tuple[float, Any]] = []
    for entry in entries:
        if str(getattr(entry, "language", "")) != language:
            continue
        measured = index.against(str(entry.id), dict(marked))
        if measured is None or measured.known * 100 < NEARLY:
            continue
        found.append((measured.known, entry))
    found.sort(key=lambda pair: (pair[0], -int(getattr(pair[1], "difficulty", 0) or 0)))
    out = []
    for share, entry in found[:limit]:
        named = getattr(entry, "named", {}) or {}
        out.append(
            {
                "id": str(entry.id),
                "title": str(entry.title),
                "english": str(named.get(ui_language) or getattr(entry, "english", "") or ""),
                "author": str(getattr(entry, "author", "") or ""),
                "kind": str(getattr(entry, "kind", "")),
                "known": percent(share),
            }
        )
    return out


def learning(marked: Mapping[str, int]) -> list[str]:
    """The words at steps 1 to 3: on the list, not known, not ignored."""
    return [lemma for lemma, status in marked.items() if status in (1, 2, 3)]


def met_often(
    lemmas: Iterable[str],
    texts_met: Callable[[str], int],
    limit: int = WORDS,
) -> list[dict[str, Any]]:
    """The words still being learned that the reader keeps meeting, most texts first.

    `texts_met` says in how many texts a word was met; a word met in fewer than two is
    not one anybody keeps meeting, and is left out rather than padded in.
    """
    counted = [(texts_met(lemma), lemma) for lemma in lemmas]
    counted = [(n, lemma) for n, lemma in counted if n >= OFTEN]
    counted.sort(key=lambda pair: (-pair[0], pair[1]))
    return [{"lemma": lemma, "texts": n} for n, lemma in counted[:limit]]
