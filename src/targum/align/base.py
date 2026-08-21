"""Aligning an existing translation to the source.

The shape of the problem: translators merge sentences, split them, occasionally drop
one, and reorder within a paragraph. A 1:1 assumption fails on the first page of any
real book. So this is a dynamic program over a small set of link shapes, scored by
semantic similarity and by how long each side ought to be.

Two passes, coarse then fine. Blocks are aligned first, which keeps a bad match local
instead of letting it cascade through the rest of the document, and then sentences are
aligned inside each block pairing. Paragraph pairing is also the fallback when the fine
pass is not confident, which is why both passes run the same algorithm.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from ..models import Link, Segment

# The link shapes worth considering, as (source count, target count). Anything richer
# is rare enough that allowing it costs more in false matches than it recovers.
SHAPES: tuple[tuple[int, int], ...] = (
    (1, 1),
    (1, 2),
    (2, 1),
    (2, 2),
    (1, 3),
    (3, 1),
    (1, 0),
    (0, 1),
)

# What a null link costs. A match costs at most about 1.0 from similarity plus the
# length term, so this has to sit inside that range: any higher and a null link is
# never the cheapest option, which quietly turns every dropped sentence into a bad
# merge. Tuned against the gold links in tests/fixtures/gold.
NULL_PENALTY = 0.6
# How much the length prior counts against similarity.
LENGTH_WEIGHT = 0.35
# Below this, a sentence pairing is not trusted and its region collapses to paragraphs.
CONFIDENCE_FLOOR = 0.45

# How far off the diagonal the search may wander. An alignment is monotone, so a
# sentence two thirds of the way through one text pairs with something near two thirds
# of the way through the other. Without this the table is quadratic, and a novel with
# a few thousand sentences a side stops being something you can run.
BEAM = 60


class Encoder(Protocol):
    """Turns text into vectors that can be compared across languages."""

    @property
    def name(self) -> str:
        """Model identity, recorded on the alignment."""

    def similarity(self, source: Sequence[str], target: Sequence[str]) -> list[list[float]]:
        """Cosine similarity for every source against every target."""


@dataclass(slots=True)
class Candidate:
    source: list[int]
    target: list[int]
    confidence: float


def length_ratio(source: Sequence[str], target: Sequence[str]) -> float:
    """Characters of target per character of source, measured on this pair.

    Calibrating from the documents themselves rather than from a table is what makes
    this work across scripts. Hebrew says in 30 characters what English needs 45 for,
    and a prior tuned on European pairs would call every correct Hebrew link too short.
    """
    source_chars = sum(len(text) for text in source)
    target_chars = sum(len(text) for text in target)
    if not source_chars or not target_chars:
        return 1.0
    return target_chars / source_chars


def length_penalty(source_chars: int, target_chars: int, ratio: float) -> float:
    """How far this pairing is from the length the calibrated ratio predicts."""
    expected = max(1.0, source_chars * ratio)
    return abs(math.log((target_chars + 1) / (expected + 1)))


def align_sequences(
    source: Sequence[str],
    target: Sequence[str],
    similarity: list[list[float]],
    ratio: float,
    *,
    shapes: Sequence[tuple[int, int]] = SHAPES,
    beam: int = BEAM,
) -> list[Candidate]:
    """Dynamic program over link shapes. Returns links in reading order."""
    rows, columns = len(source), len(target)
    if not rows and not columns:
        return []

    slope = (columns / rows) if rows else 0.0
    width = max(beam, abs(columns - rows) + 2)

    def in_band(i: int, j: int) -> bool:
        return abs(j - i * slope) <= width

    best: list[list[float]] = [[math.inf] * (columns + 1) for _ in range(rows + 1)]
    back: list[list[tuple[int, int] | None]] = [[None] * (columns + 1) for _ in range(rows + 1)]
    best[0][0] = 0.0

    for i in range(rows + 1):
        for j in range(columns + 1):
            if best[i][j] is math.inf or not in_band(i, j):
                continue
            for take_source, take_target in shapes:
                next_i, next_j = i + take_source, j + take_target
                if next_i > rows or next_j > columns or not in_band(next_i, next_j):
                    continue
                step = _cost(
                    source[i:next_i],
                    target[j:next_j],
                    similarity,
                    i,
                    j,
                    take_source,
                    take_target,
                    ratio,
                )
                if best[i][j] + step < best[next_i][next_j]:
                    best[next_i][next_j] = best[i][j] + step
                    back[next_i][next_j] = (take_source, take_target)

    # Walk the choices back from the end.
    path: list[tuple[int, int]] = []
    i, j = rows, columns
    while (i, j) != (0, 0):
        choice = back[i][j]
        if choice is None:
            # The band cut off every route to here. Rather than return a partial
            # alignment that silently drops the opening of the text, pair whatever is
            # left in one link and let its confidence say how much to trust it.
            path.append((i, j))
            break
        path.append(choice)
        i, j = i - choice[0], j - choice[1]
    path.reverse()

    out: list[Candidate] = []
    i = j = 0
    for take_source, take_target in path:
        confidence = _confidence(similarity, i, j, take_source, take_target, source, target, ratio)
        out.append(
            Candidate(
                source=list(range(i, i + take_source)),
                target=list(range(j, j + take_target)),
                confidence=confidence,
            )
        )
        i += take_source
        j += take_target
    return out


# A merge is only justified when every sentence in it belongs. Scoring a group by the
# mean lets one strong pair carry an unrelated sentence along, which turns a sentence
# the translator dropped into a confident and wrong merge. Weighting the weakest pair
# makes a group pay for its worst member.
_WEAKEST_WEIGHT = 0.6

# A group whose weakest pair is below this is not a merge at all, it is one real match
# with something unrelated stapled to it. Weighting the weakest pair is not enough on
# its own: two lines a translator dropped are cheaper to absorb into the neighbouring
# sentence than to pay the null penalty twice. This makes that trade explicit.
MERGE_FLOOR = 0.3
MERGE_VETO = 1.0


def _group_values(
    similarity: list[list[float]], i: int, j: int, take_source: int, take_target: int
) -> list[float]:
    return [similarity[a][b] for a in range(i, i + take_source) for b in range(j, j + take_target)]


def _group_quality(
    similarity: list[list[float]], i: int, j: int, take_source: int, take_target: int
) -> float:
    if not take_source or not take_target:
        return 0.0
    values = _group_values(similarity, i, j, take_source, take_target)
    mean = sum(values) / len(values)
    if len(values) == 1:
        return mean
    return (1 - _WEAKEST_WEIGHT) * mean + _WEAKEST_WEIGHT * min(values)


def _cost(
    source_slice: Sequence[str],
    target_slice: Sequence[str],
    similarity: list[list[float]],
    i: int,
    j: int,
    take_source: int,
    take_target: int,
    ratio: float,
) -> float:
    if not take_source or not take_target:
        return NULL_PENALTY
    semantic = 1.0 - _group_quality(similarity, i, j, take_source, take_target)
    length = length_penalty(
        sum(len(text) for text in source_slice),
        sum(len(text) for text in target_slice),
        ratio,
    )
    # Merges and splits are real but less common than one to one.
    shape_penalty = 0.05 * (take_source + take_target - 2)
    values = _group_values(similarity, i, j, take_source, take_target)
    if len(values) > 1 and min(values) < MERGE_FLOOR:
        shape_penalty += MERGE_VETO
    return semantic + LENGTH_WEIGHT * length + shape_penalty


def _confidence(
    similarity: list[list[float]],
    i: int,
    j: int,
    take_source: int,
    take_target: int,
    source: Sequence[str],
    target: Sequence[str],
    ratio: float,
) -> float:
    if not take_source or not take_target:
        return 0.0
    semantic = _group_quality(similarity, i, j, take_source, take_target)
    length = length_penalty(
        sum(len(text) for text in source[i : i + take_source]),
        sum(len(text) for text in target[j : j + take_target]),
        ratio,
    )
    # A pairing that reads alike but is the wrong length is not trustworthy.
    return max(0.0, min(1.0, semantic * math.exp(-0.5 * length)))


def to_links(
    candidates: Sequence[Candidate],
    source: Sequence[Segment],
    target: Sequence[Segment],
    *,
    coarse: bool = False,
) -> list[Link]:
    return [
        Link(
            source=[source[index].id for index in candidate.source],
            target=[target[index].id for index in candidate.target],
            confidence=round(candidate.confidence, 4),
            coarse=coarse,
        )
        for candidate in candidates
    ]
