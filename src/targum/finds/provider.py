"""The pool as candidates for Read next (targum-internal#619; plan §2.4, §3, §7).

Per reader, at request time, with nothing fetched: the finds near the reader's rung
(`pool.pick`, at most 300 off an index), each scored against the marks the chooser
already loaded with the same running-word rule (`score.Score.coverage`), and handed to
the chooser beside the shelf. A find carries `origin: find` and its pool id, which a
recommendation's record will say (targum-internal#612).

What is never offered on Read next:

- a find that is not measured (`score.Score.measured`: too short, or more than 8% of its
  words the map could not place);
- a find inside the 1.5 points just above the floor (`MARGIN`): the cheap figure carries
  about ±2 points, so the floor holds after the bias;
- a find under the floor: the fallback for a reader who has marked little is the shelf;
- a find costing more credits than the reader has left: a one-tap card cannot honestly
  be a dead end;
- a find the reader has already built: it is their targum now, and Continue has it.

An empty or stale pool contributes nothing, and Read next is what the shelf makes it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .. import level as level_module
from . import pool
from .score import Score

if TYPE_CHECKING:
    from ..accounts import Store

#: The chooser's floor (`choose.FLOOR`), restated so this module has no import cycle
#: with it; a test holds the two equal.
FLOOR = 0.90

#: How far above the floor a find must be to be offered (plan §2.3).
MARGIN = 0.015

#: What a find's card id starts with, so it never collides with a catalogue id.
PREFIX = "find-"

#: What makes two finds the same kind of thing for "Something else" (`choose.cluster`):
#: a news find is an article from the news, and the next pick prefers anything else.
CLUSTER = ("article", "find:news")

#: Under this many rows near the reader's rung, the freshest whatever their rung are
#: scored too: the rung is only a cut for speed, and a thin pool should still be read.
NEAR_LEAST = 30


@dataclass(frozen=True)
class Scored:
    find: pool.Find
    share: float


def share_of(find: pool.Find, marked: Mapping[str, int]) -> float | None:
    """A find's running-word coverage for one reader, or None where it is not measured."""
    scored = Score(tokens=find.tokens, unresolved=find.unresolved, bag=dict(find.bag))
    if not scored.measured:
        return None
    return scored.coverage(marked)


def offered(
    store: Store,
    language: str,
    marked: Mapping[str, int],
    *,
    rung: int | None = None,
    credits_left: int | None = None,
    built: Iterable[str] = (),
    skip: Iterable[str] = (),
    at: int | None = None,
) -> list[Scored]:
    """The finds this reader may be offered on Read next, each with its share.

    `credits_left` is None for a reader held to no monthly allowance. `built` is the
    addresses of the reader's own texts, as `weekly.feeds.link_key` writes them. `skip`
    is card ids the page set aside on this visit."""
    code = (language or "").split("-")[0].lower()
    own = set(built)
    passed = set(skip)
    out: list[Scored] = []
    near = pool.pick(store, code, rung, at=at)
    if rung is not None and len(near) < NEAR_LEAST:
        held = {find.id for find in near}
        near += [find for find in pool.pick(store, code, None, at=at) if find.id not in held]
    for find in near:
        if find.url in own or f"{PREFIX}{find.id}" in passed:
            continue
        if credits_left is not None and find.credits > credits_left:
            continue
        share = share_of(find, marked)
        if share is None or share < FLOOR + MARGIN:
            continue
        out.append(Scored(find, share))
    return out


def row(scored: Scored) -> dict[str, Any]:
    """A find as a suggestion row: the fields the card draws, in the shape
    `chat.tools.suggest_next` gives a shelf text, with `origin` and `find` added."""
    find = scored.find
    known_line = level_module.known_line(scored.share)
    return {
        "id": f"{PREFIX}{find.id}",
        "find": find.id,
        "origin": "find",
        "title": find.title or find.host,
        "language": find.language,
        "kind": "article" if find.medium == "text" else find.medium,
        "register": "modern",
        "collection": f"find:{find.source}",
        "host": find.host,
        "publisher": find.publisher,
        "url": find.url,
        "minutes": find.minutes,
        "credits": find.credits,
        "topics": list(find.topics),
        "published": find.published,
        "on_shelf": False,
        "reader": "",
        "running_share": round(scored.share, 4),
        "known_share": level_module.page_share(scored.share),
        "known_line": known_line,
        "because": known_line,
        "reason": {"key": "suggest.known", "share": level_module.known_percent(scored.share)},
    }
