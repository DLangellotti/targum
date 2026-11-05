"""The nightly search leans toward what readers ask for and the pool lacks (targum-internal#622;
David, 2026-11-05; design.md §12, "The night's search leans toward the topics readers ask
for").

Two halves:

- **A count, naming nobody.** Each Filter press on Home's one card (`POST /find` with
  `pressed`, design.md §12 2026-11-05) adds one to a single row keyed by the month, the
  language, the medium chosen, the topic chosen and the rung the reader was at
  (`chip_press`). There is no reader, no account, no time finer than the month and no
  text in it: it is a tally of the cell, and it could not be turned back into who pressed.
- **A lean, at no extra cost.** Before the open-web night (`web.refresh`) starts its
  searches, each topic is weighed by the presses that wanted something to read on it
  (medium Read, or none chosen) at each rung, over this month and the last, divided by
  what the pool already holds on it for a reader at that rung. Up to `STEER_MOST` topics
  that weigh most go first tonight; the rest follow in the usual rotation. The night's
  dollar and the month's pacing are unchanged, so what moves is which topics the same
  spend buys, never how much is spent.

**Off unless the box says so** (`TARGUM_CHIP_COUNTS`), because no clause of the privacy
notice names this count yet: off, nothing is counted and the night does not lean.
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from typing import TYPE_CHECKING, Any

from . import chips, pool

if TYPE_CHECKING:
    from ..accounts import Store
    from .interests import Lexicon

FLAG = "TARGUM_CHIP_COUNTS"

SCHEMA = """
-- Filter presses on Home's one card, tallied (targum-internal#622; design.md §12, "The
-- night's search leans toward the topics readers ask for", 2026-11-05). One row a cell:
-- the month (`finds.pool.month_from`, ms), the language, the medium chosen ('' for any),
-- the topic chosen ('' for any) and the rung the reader was at (-1 where there is no
-- ladder). `n` is how many presses. No reader, no account and no finer time: a count of
-- the cell, nothing more.
CREATE TABLE IF NOT EXISTS chip_press (
  month    INTEGER NOT NULL,
  language TEXT    NOT NULL,
  medium   TEXT    NOT NULL DEFAULT '',
  topic    TEXT    NOT NULL DEFAULT '',
  rung     INTEGER NOT NULL DEFAULT -1,
  n        INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (month, language, medium, topic, rung)
) WITHOUT ROWID;
"""

#: The media a press may name; '' is any.
MEDIA = frozenset({"", "read", "watch", "listen"})
#: The presses that ask for something to read, which is what a web search brings.
READING = frozenset({"", "read"})

#: The most topics a night puts first; the rest keep the rotation, so every topic still
#: comes round.
STEER_MOST = 10
#: A topic holding at least this many finds for a rung is not thin there.
THIN = 12


def on() -> bool:
    return os.environ.get(FLAG, "").strip().lower() in {"1", "true", "yes"}


def count(
    store: Store,
    *,
    language: str,
    medium: str,
    topic: str,
    rung: int | None,
    at: int | None = None,
) -> bool:
    """One Filter press, added to its cell. Whether it was counted: never while off, and
    never for a medium or topic the page does not offer."""
    if not on():
        return False
    medium = medium if medium in MEDIA else ""
    topic = topic if topic in chips.BY_CODE else ""
    if not language or not language.isalpha() or len(language) > 8:
        return False
    when = pool.now_ms() if at is None else at
    with store.write() as db:
        db.execute(
            "INSERT INTO chip_press (month, language, medium, topic, rung, n)"
            " VALUES (?, ?, ?, ?, ?, 1) ON CONFLICT (month, language, medium, topic, rung)"
            " DO UPDATE SET n = n + 1",
            (pool.month_from(when), language, medium, topic, -1 if rung is None else int(rung)),
        )
    return True


def _last_month(at: int) -> int:
    return pool.month_from(pool.month_from(at) - pool.DAY_MS)


def demand(store: Store, language: str, at: int | None = None) -> Counter[tuple[str, int]]:
    """Presses for something to read, by (topic, rung), this month and the last."""
    when = pool.now_ms() if at is None else at
    out: Counter[tuple[str, int]] = Counter()
    for topic, rung, n in store.db.execute(
        "SELECT topic, rung, SUM(n) FROM chip_press WHERE language = ? AND month >= ?"
        " AND topic != '' AND medium IN ('', 'read') GROUP BY topic, rung",
        (language, _last_month(when)),
    ):
        if topic in chips.BY_CODE:
            out[(str(topic), int(rung))] += int(n or 0)
    return out


def about_chip(find: pool.Find, known: Lexicon | None) -> set[str]:
    """The chips a find is about: those it was found for, and those whose lexicon topic
    its words are, as the card matches them (`button._chip_matched`)."""
    from . import interests

    found = {one.removeprefix(chips.TAG) for one in find.topics if one.startswith(chips.TAG)}
    if known is not None:
        shown = set(known.shown)
        topics = interests.about(find.bag, find.tokens, known)
        for chip in chips.CHIPS:
            topic = chips.matcher(chip.code, shown)
            if topic and topics.get(topic, 0.0) >= interests.ABOUT_LEAST:
                found.add(chip.code)
    return found


def supply(
    store: Store,
    language: str,
    rungs: Iterable[int],
    known: Lexicon | None,
    at: int | None = None,
) -> Counter[tuple[str, int]]:
    """What the pool holds to read on each topic for a reader at each rung: the finds Home
    would score for them (`pool.pick`), counted by the chips they are about."""
    out: Counter[tuple[str, int]] = Counter()
    for rung in set(rungs):
        held = pool.pick(store, language, None if rung < 0 else rung, at=at)
        for find in held:
            if find.medium != "text":
                continue
            for code in about_chip(find, known):
                out[(code, rung)] += 1
    return out


def weights(
    store: Store,
    language: str,
    *,
    known: Lexicon | None = None,
    at: int | None = None,
) -> dict[str, float]:
    """Each topic's lean tonight: for each rung where it is thin, the presses for it over
    one more than what is held. Topics nobody pressed, or held well, weigh nothing."""
    wanted = demand(store, language, at)
    if not wanted:
        return {}
    held = supply(store, language, {rung for _, rung in wanted}, known, at)
    out: dict[str, float] = {}
    for (topic, rung), n in wanted.items():
        have = held.get((topic, rung), 0)
        if have >= THIN:
            continue
        out[topic] = out.get(topic, 0.0) + n / (1 + have)
    return out


def leaning(
    order: Sequence[tuple[str, Any]], lean: Mapping[str, float], most: int = STEER_MOST
) -> list[tuple[str, Any]]:
    """The night's queries with the heaviest topics first, at most `most` of them, then
    the rest in the order given."""
    first = sorted(
        (pair for pair in order if lean.get(pair[0], 0.0) > 0),
        key=lambda pair: -lean[pair[0]],
    )[:most]
    return [*first, *(pair for pair in order if pair not in first)]
