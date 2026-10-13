"""Russian verbs of motion: which way a verb goes, and the other verb of its pair.

One of Russian's hard spots (`stages.HARD_SPOTS`, research/hard-spots-2026-10-11 in
targum-internal). Fourteen unprefixed pairs split a single English verb in two: one
goes one way, or is under way now (идти, "is going"); the other goes and comes back,
or happens as a habit or an ability (ходить, "goes, as a rule"). Both are imperfective,
so the aspect line cannot tell them apart, and a learner who reads ходил as "went" has
read a round trip as a departure.

A prefixed verb (прийти, приходить) is left alone: a prefix turns the pair into an
ordinary aspect pair, which the partner line already names.

The list is closed and short, so it is written here rather than read from a dictionary,
and it is computed from the dictionary form alone: a wrong answer on the card is a wrong
lemma, which `scripts/eval_lemma.py` scores as `motion_precision` and `motion_recall`.
"""

from __future__ import annotations

#: One way, then the other: (unidirectional, multidirectional).
PAIRS: tuple[tuple[str, str], ...] = (
    ("идти", "ходить"),
    ("ехать", "ездить"),
    ("бежать", "бегать"),
    ("лететь", "летать"),
    ("плыть", "плавать"),
    ("нести", "носить"),
    ("вести", "водить"),
    ("везти", "возить"),
    ("ползти", "ползать"),
    ("лезть", "лазить"),
    ("брести", "бродить"),
    ("катить", "катать"),
    ("тащить", "таскать"),
    ("гнать", "гонять"),
)

ONE_WAY = "one"
BOTH_WAYS = "both"

_WHICH: dict[str, tuple[str, str]] = {}
for _one, _both in PAIRS:
    _WHICH[_one] = (ONE_WAY, _both)
    _WHICH[_both] = (BOTH_WAYS, _one)


def _bare(lemma: str) -> str:
    return lemma.replace("\u0301", "").replace("ё", "е").casefold()


def motion_of(lemma: str) -> str:
    """A verb of motion's way and its pair: "one:ходить" for идти, which goes one way;
    "both:идти" for ходить, which goes and comes back; "" for every other word."""
    found = _WHICH.get(_bare(lemma))
    return f"{found[0]}:{found[1]}" if found else ""
