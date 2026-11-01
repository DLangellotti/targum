"""What a reader seems to like reading about, from what they read (targum-internal#615).

"Find me something" (David, 2026-11-01) picks one real article that interests the reader
and that they can read. Its interests come from two places:

- **What they read**, through the topic lexicon (`topics.py`, targum-internal#609): the
  dictionary forms of the words met in sections they finished (`Store.knowledge`'s
  `met`), and the words they saved themselves. A word saved counts more than a word met,
  because saving it was a choice. Words ticked on "Words you may already know" are left
  out: a tick says what somebody knows, not what they like.
- **The chips** the page shows when the button is tapped, which steer and can be skipped.

A topic is the reader's when its words make up more of what they read than they make up
of the lexicon: the lift over the lexicon's own share, so that a topic with many words
(People & feelings, Nature & weather) does not win for everybody. Only the topics a page
may show (`topics.load_shown`) are ever said or used: a topic whose tags failed ling-he's
gold set is not one to tell a reader they like.

Everything here runs on the box, over the reader's own record, and nothing leaves it: the
live search (`live.py`) is sent topic words, a language and a level, never this.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .. import topics as topics_module

#: Where the lexicon is read from when the environment names one; otherwise
#: `topics.LEXICON`. A box with neither infers nothing and shows no chips.
ENV = "TARGUM_TOPICS"

#: How much a saved word counts against a word met in a finished section.
SAVED_WEIGHT = 3.0
MET_WEIGHT = 1.0

#: Under this many lexicon words in what the reader read, nothing is inferred: a guess
#: from a handful of words would steer more than it knows.
LEAST_EVIDENCE = 40

#: A topic is the reader's when at least this many distinct words of it were read, and
#: its share of what they read is at least `LEAST_LIFT` times its share of the lexicon.
LEAST_HITS = 5
LEAST_LIFT = 1.3

#: The most topics inferred for one reader.
MOST = 3

#: A find is about a topic when the topic's words are at least this share of its running
#: words. Topic words are rare beside the general ones that carry every sentence: an
#: article about cooking with 600 words has 20 to 60 words of Food & drink.
ABOUT_LEAST = 0.03


@dataclass(frozen=True)
class Lexicon:
    """The lexicon as this module reads it: each lemma's topics, the topics a page may
    show, and each topic's share of the lexicon's words."""

    lemmas: Mapping[str, tuple[str, ...]]
    shown: tuple[str, ...]
    base: Mapping[str, float]


def path() -> Path | None:
    named = os.environ.get(ENV, "").strip()
    if named:
        return Path(named) if Path(named).is_file() else None
    return topics_module.LEXICON if topics_module.LEXICON.is_file() else None


_KEPT: dict[tuple[str, float], Lexicon] = {}
_LOCK = threading.Lock()


def lexicon(file: Path | None = None) -> Lexicon | None:
    """The lexicon, read once per file and change; None where there is none."""
    where = file or path()
    if where is None:
        return None
    try:
        stamp = where.stat().st_mtime
    except OSError:
        return None
    key = (str(where), stamp)
    with _LOCK:
        held = _KEPT.get(key)
    if held is not None:
        return held
    lemmas = topics_module.load(where)
    if not lemmas:
        return None
    made = from_lemmas(lemmas, topics_module.load_shown(where))
    with _LOCK:
        _KEPT.clear()
        _KEPT[key] = made
    return made


def from_lemmas(lemmas: Mapping[str, Sequence[str]], shown: Iterable[str]) -> Lexicon:
    counts: dict[str, int] = {}
    for codes in lemmas.values():
        for code in codes:
            counts[code] = counts.get(code, 0) + 1
    total = len(lemmas) or 1
    return Lexicon(
        lemmas={lemma: tuple(codes) for lemma, codes in lemmas.items()},
        shown=tuple(code for code in topics_module.TOPICS if code in set(shown)),
        base={code: n / total for code, n in counts.items() if code != topics_module.GENERAL},
    )


@dataclass(frozen=True)
class Interest:
    topic: str
    #: How many times its share of the lexicon the topic is of what the reader read.
    lift: float
    #: Distinct words of it the reader read.
    hits: int


def inferred(
    words: Iterable[tuple[str, int | None, str]],
    met: Iterable[str],
    known: Lexicon,
) -> list[Interest]:
    """The reader's topics, strongest first, from their list (`Store.knowledge`'s
    (lemma, status, source)) and the words met in finished sections. Only shown topics;
    nothing where too little was read to tell."""
    from ..coverage import IGNORED

    weight: dict[str, float] = {}
    for lemma, status, source in words:
        if not lemma or status is None or status == IGNORED or source == "claimed":
            continue
        weight[lemma] = max(weight.get(lemma, 0.0), SAVED_WEIGHT)
    for lemma in met:
        if lemma and lemma not in weight:
            weight[lemma] = MET_WEIGHT
    total = 0.0
    by_topic: dict[str, float] = {}
    hits: dict[str, int] = {}
    present = 0
    for lemma, w in weight.items():
        codes = known.lemmas.get(lemma)
        if not codes:
            continue
        present += 1
        total += w
        for code in codes:
            if code == topics_module.GENERAL:
                continue
            by_topic[code] = by_topic.get(code, 0.0) + w
            hits[code] = hits.get(code, 0) + 1
    if present < LEAST_EVIDENCE or total <= 0:
        return []
    out: list[Interest] = []
    for code in known.shown:
        base = known.base.get(code, 0.0)
        if base <= 0 or hits.get(code, 0) < LEAST_HITS:
            continue
        lift = (by_topic.get(code, 0.0) / total) / base
        if lift >= LEAST_LIFT:
            out.append(Interest(code, round(lift, 3), hits[code]))
    out.sort(key=lambda one: (-one.lift, one.topic))
    return out[:MOST]


def about(bag: Mapping[str, int], tokens: int, known: Lexicon) -> dict[str, float]:
    """Each shown topic's share of a find's running words, from its lemma counts: what
    the find is about, with nothing fetched. Topics under `ABOUT_LEAST` are left out."""
    if tokens <= 0:
        return {}
    shown = set(known.shown)
    counts: dict[str, int] = {}
    for lemma, n in bag.items():
        for code in known.lemmas.get(lemma, ()):
            if code in shown:
                counts[code] = counts.get(code, 0) + n
    return {code: round(n / tokens, 4) for code, n in counts.items() if n / tokens >= ABOUT_LEAST}


def forget() -> None:
    """Drop the kept lexicon (tests)."""
    with _LOCK:
        _KEPT.clear()
