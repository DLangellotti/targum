"""Where a reader is, said in kinds of text they could open (design.md §12, "Your
Progress is a story in three parts", 2026-10-09).

David, 2026-10-08: Your Progress opens on a short ladder of real kinds of text from the
language's own library — a dialogue, a video, a news article, a short story, a novel,
a poem — ordered by how hard the catalogue measured each kind (`Entry.difficulty`,
the median of the texts of that kind that have been measured), and a headline naming the
hardest of them the reader would follow. Not a placement (§6): every rung is a shelf of
real texts they can open.

How much of a kind they would follow is the share of its **running words** whose
dictionary form they have marked known, text by text, and the middle text of the kind:
one long book cannot speak for forty short stories. The words are said by the share:

- 95% and up: "You'd follow a news article";
- 90–95%: "You'd follow nearly all of a news article";
- 75–90%: "You'd follow most of a news article".

Below 75% nothing is claimed. Everything here is arithmetic over the catalogue and the
lemma index beside it, with nothing fetched and nothing spent.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from statistics import median
from typing import Any

from .coverage import KNOWN, Index

#: The kinds a ladder is made of, the board's six (Progress, 2026-10-08). The catalogue
#: has more — Bible narrative, essays, plays, documents, prayer — and they stay on their
#: shelves; a ladder of eleven rungs is a table, not a sentence anybody reads. Which of
#: these a language's ladder has, and in what order, is the catalogue's to say.
KINDS = ("dialogue", "talk", "article", "story", "novel", "poetry")

#: No ladder at all. wordfreq has no Aramaic list, so the difficulty measure says 0 of
#: every Aramaic text, which is false (David, 2026-10-08): Aramaic shows known words only.
NO_LADDER = frozenset({"arc"})

#: What a kind is called where the language's shelf of it is something more particular.
#: Italian's stories are StoryWeaver's children's books, and a rung says so in everyday
#: words (David, 2026-10-09: "what is a picture book?").
NAMED: Mapping[str, Mapping[str, str]] = {"it": {"story": "children-book"}}

#: The three wordings, by the share of running words known (percent).
FOLLOW = 95
NEARLY = 90
MOST = 75

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


def said(share: int | None) -> str:
    """Which wording a share earns: "follow", "nearly", "most", or "" for nothing."""
    if share is None:
        return ""
    if share >= FOLLOW:
        return "follow"
    if share >= NEARLY:
        return "nearly"
    return "most" if share >= MOST else ""


def ladder(entries: Iterable[Any], language: str) -> list[Rung]:
    """A language's rungs, easiest first, by the median measured difficulty of each kind.

    A kind with no measured text in this language is not a rung: an unmeasured 0 would
    put it at the bottom, which is a claim nobody made. Empty for Aramaic, and for a
    language the library has nothing in.
    """
    if language in NO_LADDER:
        return []
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
    """The share of one text's running words whose dictionary form is marked known.

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
        total += count
        if at < len(index.words) and marked.get(index.words[at]) == KNOWN:
            known += count
    return known / total if total else None


def percent(share: float) -> int:
    """A share as the whole percentage the page prints, never rounded up into a band:
    89.6% is "most of", not "nearly all of"."""
    return max(0, min(100, int(share * 100)))


def standing(rungs: list[Rung], index: Index, marked: Mapping[str, int]) -> dict[str, Any]:
    """The ladder as the page draws it: each rung's share, and which one is "here".

    Here is the hardest rung followed at 90% or more, or failing that at 75% or more; the
    rungs before it are passed, the one after it is next, and with no rung reached the
    first one is next — the place to start.
    """
    shares: list[int | None] = []
    for rung in rungs:
        found = [running_share(index, entry_id, marked) for entry_id in rung.texts]
        measured = [share for share in found if share is not None]
        shares.append(percent(median(measured)) if measured else None)

    here: int | None = None
    for floor in (NEARLY, MOST):
        for at, share in enumerate(shares):
            if share is not None and share >= floor:
                here = at
        if here is not None:
            break

    out = []
    for at, rung in enumerate(rungs):
        if here is None:
            state = "next" if at == 0 else "ahead"
        elif at < here:
            state = "passed"
        elif at == here:
            state = "here"
        else:
            state = "next" if at == here + 1 else "ahead"
        out.append(
            {
                "kind": rung.kind,
                "name": rung.name,
                "share": shares[at],
                "state": state,
                "texts": len(rung.texts),
            }
        )
    return {
        "ladder": out,
        "here": here,
        "said": said(shares[here]) if here is not None else "",
    }


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
