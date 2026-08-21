"""Scoring an alignment against hand-checked gold links.

Two numbers, because they answer different questions. Strict link accuracy asks
whether the aligner found the same groupings a human did. Pairwise accuracy expands
every link into the sentence pairs it implies and scores those, which gives partial
credit: an aligner that finds two of the three English sentences belonging to a Hebrew
one is doing better than one that finds none, and a single aggregate hides that.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..models import Link

GoldLink = tuple[tuple[int, ...], tuple[int, ...]]


@dataclass(slots=True)
class Score:
    pair: str
    gold_links: int
    predicted_links: int
    strict_precision: float
    strict_recall: float
    pair_precision: float
    pair_recall: float
    null_recall: float

    @property
    def strict_f1(self) -> float:
        return _f1(self.strict_precision, self.strict_recall)

    @property
    def pair_f1(self) -> float:
        return _f1(self.pair_precision, self.pair_recall)

    def report(self) -> str:
        return (
            f"{self.pair}: "
            f"strict P {self.strict_precision:.2f} R {self.strict_recall:.2f} "
            f"F {self.strict_f1:.2f} | "
            f"pairwise P {self.pair_precision:.2f} R {self.pair_recall:.2f} "
            f"F {self.pair_f1:.2f} | "
            f"nulls {self.null_recall:.2f} "
            f"({self.predicted_links} links against {self.gold_links})"
        )


def _f1(precision: float, recall: float) -> float:
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


def _ratio(hits: int, total: int) -> float:
    return hits / total if total else 1.0


def load_gold(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    data["links"] = [(tuple(source), tuple(target)) for source, target in data["links"]]
    return data


def as_indices(links: list[Link], source_ids: list[str], target_ids: list[str]) -> list[GoldLink]:
    """Predicted links, expressed the way the gold file is written."""
    source_at = {segment_id: index for index, segment_id in enumerate(source_ids)}
    target_at = {segment_id: index for index, segment_id in enumerate(target_ids)}
    return [
        (
            tuple(source_at[i] for i in link.source if i in source_at),
            tuple(target_at[j] for j in link.target if j in target_at),
        )
        for link in links
    ]


def score(predicted: list[GoldLink], gold: list[GoldLink], pair: str) -> Score:
    predicted_set = set(predicted)
    gold_set = set(gold)
    strict_hits = len(predicted_set & gold_set)

    predicted_pairs = _pairs(predicted)
    gold_pairs = _pairs(gold)
    pair_hits = len(predicted_pairs & gold_pairs)

    gold_nulls = {link for link in gold if not link[0] or not link[1]}
    found_nulls = len(gold_nulls & predicted_set)

    return Score(
        pair=pair,
        gold_links=len(gold),
        predicted_links=len(predicted),
        strict_precision=_ratio(strict_hits, len(predicted_set)),
        strict_recall=_ratio(strict_hits, len(gold_set)),
        pair_precision=_ratio(pair_hits, len(predicted_pairs)),
        pair_recall=_ratio(pair_hits, len(gold_pairs)),
        null_recall=_ratio(found_nulls, len(gold_nulls)),
    )


def _pairs(links: list[GoldLink]) -> set[tuple[int, int]]:
    """Every sentence pair a set of links implies."""
    return {
        (source, target)
        for source_group, target_group in links
        for source in source_group
        for target in target_group
    }
