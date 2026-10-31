"""One chooser for what to read next (design.md §12, "What to read next is chosen on
running words", 2026-10-31; targum-internal#612).

Home's card and Your Progress's "Texts at your level" chose in opposite directions: the
list put the text nearest the line first, "because a text at 99% teaches nothing", and
the card put the text the reader knew *most* of first, so a reader who marked diligently
was offered one at 99–100%. Both now ask this module, so they cannot drift apart again.

**The band** (David, 2026-10-31, from ling-he's research of the same day). A text fits
when the reader knows at least `FLOOR` of its running words; inside the band, the nearest
to the `AIM` comes first. Glosses rescue a text at 90–95%, and a text at 98%+ teaches
about two new words in a hundred, so the aim sits between. A text at `TOO_EASY` or more
is never put ahead of one in the band.

**Real before scenes.** The model-written scenes are beginner supply until real easy
content fills the gap: where a real text and a scene both fit, the real one comes first.

**What it is not, yet.** The share is the reader's marks only. The estimate of what an
unmarked word is likely to be (Phase 1, targum-internal#613), medium bands and learning
value (Phase 2) come later; each changes `key`, not its callers.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

#: The least share of a text's running words a reader must know for it to fit.
FLOOR = 0.90
#: Where inside the band a text teaches most and still reads: nearest first.
AIM = (0.94, 0.97)
#: Known this well, a text teaches nothing new; after anything in the band.
TOO_EASY = 0.995

#: Where a candidate came from, as a recommendation's record will say it: the shelf, or
#: a fresh item found on demand (targum-internal#619).
ORIGINS = ("shelf", "find")

BAND = "band"
UNDER = "under"
EASY = "easy"
UNMEASURED = "unmeasured"


def fit(share: float | None) -> str:
    """Where a share sits: in the band, under the floor, too easy, or not measured."""
    if share is None:
        return UNMEASURED
    if share >= TOO_EASY:
        return EASY
    if share >= FLOOR:
        return BAND
    return UNDER


def from_aim(share: float) -> float:
    """How far a share is from the aim: nought inside it."""
    low, high = AIM
    if share < low:
        return low - share
    if share > high:
        return share - high
    return 0.0


def key(
    share: float | None,
    *,
    scene: bool = False,
    gentle: int = 0,
    liked: bool = False,
) -> tuple[Any, ...]:
    """The sort key every chooser uses, lowest first.

    1. In the band, real texts before scenes, then nearest the aim.
    2. Under the floor, nearest the floor first: the fallback that keeps a reader who has
       marked little from being offered nothing.
    3. Too easy, the least known first.
    4. Not measured: the gentlest by the catalogue's own difficulty, and a text with no
       difficulty either last.

    `gentle` is the catalogue's difficulty (the share of rare words, 0 where unmeasured),
    and `liked` a text in a register the reader brought in themselves; both only break
    ties inside a tier.
    """
    tilt = -1 if liked else 0
    where = fit(share)
    if share is not None and where == BAND:
        return (0, int(scene), round(from_aim(share), 4), tilt, gentle)
    if share is not None and where == UNDER:
        return (1, 0, round(FLOOR - share, 4), tilt, gentle)
    if share is not None and where == EASY:
        return (2, int(scene), round(share, 4), tilt, gentle)
    if gentle:
        return (3, 0, gentle - 10 * (1 if liked else 0), 0, 0)
    return (4, 0, 0, 0, 0)


def cluster(row: dict[str, Any]) -> tuple[str, str]:
    """What makes two picks the same kind of thing, for "Something else": the kind of
    text, and its collection, or its register where it is in none. There is no topic per
    text yet (targum-internal#614), so kind and collection stand in for topic and
    medium."""
    return (
        str(row.get("kind") or ""),
        str(row.get("collection") or row.get("register") or ""),
    )


def alternative(
    ranked: Sequence[tuple[tuple[Any, ...], dict[str, Any]]],
    shown: tuple[str, str] | None,
) -> int:
    """Which of the ranked candidates "Something else" offers, as an index into them.

    The next best, unless one in the same tier is of another kind or collection than the
    text set aside: the first of those, so the second pick is a different sort of thing
    rather than the first one's neighbour. Never a worse tier for the sake of variety.
    """
    if not ranked:
        return -1
    if shown is None:
        return 0
    tier = ranked[0][0][0]
    for at, (rank, row) in enumerate(ranked):
        if rank[0] != tier:
            break
        if cluster(row) != shown:
            return at
    return 0
