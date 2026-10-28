"""Where a reader is, said in kinds of text they could open (design.md §12, "Your
Progress is a story in three parts", 2026-10-09, and "Your level leads with what you can
read", 2026-10-28).

David, 2026-10-08: Your Progress opens on a short ladder of real kinds of text from the
language's own library — a conversation, a video, a news article, a short story, a novel,
a poem — ordered by how hard the catalogue measured each kind (`Entry.difficulty`,
the median of the texts of that kind that have been measured), and a headline naming the
hardest of them the reader can read on their own. Not a placement (§6): every rung is a
shelf of real texts they can open.

How much of a kind they would follow is the share of its **running words** whose
dictionary form they have marked known, text by text, and the middle text of the kind:
one long book cannot speak for forty short stories. At 95% and up the kind is easy for
them; the page says so in words and never prints the share (David, 2026-10-28: "no
percentages anywhere"). Each rung also counts the texts of its kind on the Library's Read
it now shelf, so the number on the row is the number on the shelf it opens.

Everything here is arithmetic over the catalogue and the lemma index beside it, with
nothing fetched and nothing spent.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from statistics import median
from typing import Any

from .coverage import IGNORED, KNOWN, Index

#: The kinds a ladder is made of, the board's six (Progress, 2026-10-08). The catalogue
#: has more — Bible narrative, essays, plays, documents, prayer — and they stay on their
#: shelves; a ladder of eleven rungs is a table, not a sentence anybody reads. Which of
#: these a language's ladder has, and in what order, is the catalogue's to say.
KINDS = ("dialogue", "talk", "article", "story", "novel", "poetry")

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


#: What a kind is called where the language's shelf of it is something more particular.
#: Italian's stories are StoryWeaver's children's books, and a rung says so in everyday
#: words (David, 2026-10-09: "what is a picture book?").
NAMED: Mapping[str, Mapping[str, str]] = {"it": {"story": "children-book"}}

#: A kind is easy for you from this share of running words known (percent), and a text
#: is on the Library's Read it now shelf from this share of its words.
FOLLOW = 95
NEARLY = 90

#: How many texts "Texts at your level now" names, and how many words the other half.
TEXTS = 3
WORDS = 5
#: A word met in fewer texts than this is not one you "keep meeting".
OFTEN = 2


@dataclass(frozen=True)
class Rung:
    """One kind of text on a language's ladder."""

    kind: str
    name: str
    difficulty: float
    texts: tuple[str, ...]


def ladder(entries: Iterable[Any], language: str) -> list[Rung]:
    """A language's rungs, easiest first, by the median measured difficulty of each kind.

    A kind with no measured text in this language is not a rung: an unmeasured 0 would
    put it at the bottom, which is a claim nobody made. Empty for a language the library
    has nothing in. Aramaic's rungs are bodies of Targum, not kinds (`aramaic_ladder`).
    """
    if language in NO_LADDER:
        return []
    if language == "arc":
        return aramaic_ladder(entries)
    by_kind: dict[str, list[Any]] = {}
    for entry in entries:
        if str(getattr(entry, "language", "")) != language:
            continue
        kind = str(getattr(entry, "kind", ""))
        if kind in KINDS:
            by_kind.setdefault(kind, []).append(entry)
    rungs: list[Rung] = []
    for kind, members in by_kind.items():
        measured = [int(getattr(m, "difficulty", 0) or 0) for m in members]
        measured = [d for d in measured if d > 0]
        if not measured:
            continue
        rungs.append(
            Rung(
                kind=kind,
                name=NAMED.get(language, {}).get(kind, kind),
                difficulty=float(median(measured)),
                texts=tuple(str(m.id) for m in members),
            )
        )
    # Ties keep the board's order, which is also the order a learner meets them in.
    rungs.sort(key=lambda rung: (rung.difficulty, KINDS.index(rung.kind)))
    return rungs


def running_share(index: Index, entry_id: str, marked: Mapping[str, int]) -> float | None:
    """The share of one text's running words whose dictionary form is marked known, the
    ones marked ignored left out of it.

    Falls back to the share of its distinct words where the index carries no counts for
    it (an entry indexed before counts were), and None where it is not indexed at all:
    "not measured" is never said as 0%.
    """
    positions = index.texts.get(entry_id)
    if not positions:
        return None
    counts = index.counts.get(entry_id)
    if counts is None or len(counts) != len(positions):
        measured = index.against(entry_id, dict(marked))
        return measured.known if measured is not None else None
    total = 0
    known = 0
    for at, count in zip(positions, counts, strict=True):
        status = marked.get(index.words[at]) if at < len(index.words) else None
        # An ignored word is not vocabulary, and is left out as the reader leaves it out.
        if status == IGNORED:
            continue
        total += count
        if status == KNOWN:
            known += count
    return known / total if total else None


def percent(share: float) -> int:
    """A share as the whole percentage the page prints, never rounded up into a band:
    89.6% is "most of", not "nearly all of"."""
    return max(0, min(100, int(share * 100)))


def standing(
    rungs: list[Rung],
    index: Index,
    marked: Mapping[str, int],
    readable: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    """The ladder as the page draws it (design.md §12, "Your level leads with what you can
    read", 2026-10-28): each rung easy, the next step, or not yet, and how many of its
    texts the reader could read now.

    A rung is easy for you where its middle text's running words are 95% known (`FOLLOW`),
    and so is every rung below the hardest easy one: the ladder climbs. The next step is
    the rung after it, or the first rung where none is easy yet. The share stays in the
    answer for the tests and nothing else: the page prints no percentage.

    `readable` is how many texts of each kind the Library's Read it now shelf holds for
    this reader (`readable`), so a row's count is the shelf it opens.
    """
    shares: list[int | None] = []
    for rung in rungs:
        found = [running_share(index, entry_id, marked) for entry_id in rung.texts]
        measured = [share for share in found if share is not None]
        shares.append(percent(median(measured)) if measured else None)

    here: int | None = None
    for at, share in enumerate(shares):
        if share is not None and share >= FOLLOW:
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
                "share": shares[at],
                "state": state,
                "texts": len(rung.texts),
                "readable": int((readable or {}).get(rung.kind, 0)),
            }
        )
    return {"ladder": out, "here": here, "next": following}


def readable(
    entries: Iterable[Any],
    language: str,
    known_of: Callable[[str], float | None],
) -> dict[str, int]:
    """How many texts of each ladder kind sit on the Library's Read it now shelf.

    The Library's own rule, row for row (`library.js` `matches` and `fitOf`): a catalogue
    row in this language (any of its languages, as `inLanguage` reads them), of this
    kind, whose share of words known is 90% or more. `known_of` answers that share the
    way the Library does, a built copy's own measure over the catalogue's, and None where
    nothing was measured, which the Library never shelves as Read it now.
    """
    counts: dict[str, int] = {}
    for entry in entries:
        kind = str(getattr(entry, "kind", ""))
        if kind not in KINDS:
            continue
        codes = getattr(entry, "languages", None) or [getattr(entry, "language", "")]
        if language not in {str(code).split("-")[0].lower() for code in codes}:
            continue
        share = known_of(str(entry.id))
        if share is None or share * 100 < NEARLY:
            continue
        counts[kind] = counts.get(kind, 0) + 1
    return counts


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
