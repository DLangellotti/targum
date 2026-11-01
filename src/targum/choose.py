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

**The share is an estimate** since 2026-11-01 (Phase 1, targum-internal#613; design.md
§12, "The chooser estimates the words you have not marked"): the callers pass the share
of running words the reader is estimated to know (`coverage.Index.expected`, from
`estimate.py`), and pages still print the marked share.

**Medium bands and learning value** since 2026-11-01 (Phase 2, targum-internal#614;
design.md §12, "What to read next teaches words that come back"). A medium's band is its
own (`BANDS`): text read with targum's glosses and video keep the 90% floor, audio with no
text on screen needs 95%. Inside the band the order is fit, then learning value
(`learning.py`), then interest, then freshness: `key` says how.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

#: The least share of a text's running words a reader must know for it to fit.
FLOOR = 0.90
#: Where inside the band a text teaches most and still reads: nearest first.
AIM = (0.94, 0.97)
#: Known this well, a text teaches nothing new; after anything in the band.
TOO_EASY = 0.995


@dataclass(frozen=True)
class Band:
    """One medium's band: the least share that fits, and the aim inside it."""

    floor: float
    aim: tuple[float, float]


#: What a reader is given besides the words (ling-he, 2026-10-31, §1.2–1.6): reading with
#: targum's glosses, and video with its pictures and captions, comprehend from about 90%
#: of running words; audio with no text on screen needs about 95%, and its aim sits higher.
TEXT = "text"
VIDEO = "video"
AUDIO = "audio"
BANDS: dict[str, Band] = {
    TEXT: Band(FLOOR, AIM),
    VIDEO: Band(FLOOR, AIM),
    AUDIO: Band(0.95, (0.97, 0.99)),
}

#: "Something light": a text known this well reads with no effort at all. Named for the
#: research's third band and not offered anywhere yet.
LIGHT = 0.98

#: Inside the band, texts this close to each other in fit count as fitting equally, so
#: what they teach decides between them: every text inside the aim is one step, and each
#: point outside it one more.
FIT_STEP = 0.01

#: Learning values this close count as equal, so interest decides between them: a
#: quarter of a word worth learning per hundred running words.
LEARN_STEP = 0.25


def band(medium: str = TEXT) -> Band:
    """A medium's band; a medium not named here reads as text."""
    return BANDS.get(medium, BANDS[TEXT])


def medium_of(kind: str, *, source: str = "", text_on_screen: bool = True) -> str:
    """Which band a candidate is held to: audio where it is heard with no text on screen,
    video where it is watched, text otherwise. Every reader targum builds shows its text,
    so nothing on the shelf or in the finds is audio-only yet."""
    if not text_on_screen and kind in (AUDIO, "podcast", "recording"):
        return AUDIO
    if kind in (VIDEO, "youtube") or source.startswith("video:"):
        return VIDEO
    return TEXT


def freshness(published_ms: int, now_ms: int) -> int:
    """How fresh a found item is, in steps: 2 within a day, 1 within a week, 0 after or
    for anything on the shelf, which is never news."""
    if published_ms <= 0:
        return 0
    days = (now_ms - published_ms) / 86_400_000
    return 2 if days <= 1 else 1 if days <= 7 else 0


#: Where a candidate came from, as a recommendation's record will say it: the shelf, or
#: a fresh item found on demand (targum-internal#619).
ORIGINS = ("shelf", "find")

BAND = "band"
UNDER = "under"
EASY = "easy"
UNMEASURED = "unmeasured"


def fit(share: float | None, medium: str = TEXT) -> str:
    """Where a share sits: in the medium's band, under its floor, too easy, or not
    measured."""
    if share is None:
        return UNMEASURED
    if share >= TOO_EASY:
        return EASY
    if share >= band(medium).floor:
        return BAND
    return UNDER


def from_aim(share: float, medium: str = TEXT) -> float:
    """How far a share is from the medium's aim: nought inside it."""
    low, high = band(medium).aim
    if share < low:
        return low - share
    if share > high:
        return share - high
    return 0.0


def fit_step(share: float, medium: str = TEXT) -> int:
    """How far from the aim a share in the band is, in whole `FIT_STEP`s: 0 inside it."""
    return math.ceil(round(from_aim(share, medium) / FIT_STEP, 6))


def learn_step(learn: float) -> int:
    """A learning value in whole `LEARN_STEP`s."""
    return int(max(0.0, learn) / LEARN_STEP)


def key(
    share: float | None,
    *,
    scene: bool = False,
    gentle: int = 0,
    liked: bool = False,
    medium: str = TEXT,
    learn: float = 0.0,
    interest: int = 0,
    fresh: int = 0,
) -> tuple[Any, ...]:
    """The sort key every chooser uses, lowest first.

    1. In the medium's band: real texts before scenes; then fit, in steps of a point from
       the aim (every text inside the aim is one step); then learning value, in steps of
       a quarter of a word per hundred (`learning.value`); then interest; then
       freshness; then exactly how near the aim. Fit stays first so a text never jumps
       the band's order for what it teaches, and what it teaches decides between texts
       that fit as well as each other.
    2. Under the floor, nearest the floor first: the fallback that keeps a reader who has
       marked little from being offered nothing.
    3. Too easy, the least known first.
    4. Not measured: the gentlest by the catalogue's own difficulty, and a text with no
       difficulty either last.

    `gentle` is the catalogue's difficulty (the share of rare words, 0 where unmeasured),
    and `liked` a text in a register the reader brought in themselves; both only break
    ties inside a tier. `interest` is how far the text is on the reader's topics, or
    continues what they have read (a small whole number, more is nearer), and `fresh` a
    find's `freshness`.
    """
    tilt = -1 if liked else 0
    where = fit(share, medium)
    if share is not None and where == BAND:
        return (
            0,
            int(scene),
            fit_step(share, medium),
            -learn_step(learn),
            -interest,
            -fresh,
            round(from_aim(share, medium), 4),
            tilt,
            gentle,
        )
    if share is not None and where == UNDER:
        return (1, 0, round(band(medium).floor - share, 4), tilt, gentle)
    if share is not None and where == EASY:
        return (2, int(scene), round(share, 4), tilt, gentle)
    if gentle:
        return (3, 0, gentle - 10 * (1 if liked else 0), 0, 0)
    return (4, 0, 0, 0, 0)


def cluster(row: dict[str, Any]) -> tuple[str, str]:
    """What makes two picks the same kind of thing, for "Something else": the kind of
    text, and its collection, or its register where it is in none."""
    return (
        str(row.get("kind") or ""),
        str(row.get("collection") or row.get("register") or ""),
    )


def topic(row: dict[str, Any]) -> str:
    """A pick's strongest topic, where the topic lexicon gives it one (`learning.
    text_topics`), else ""."""
    about = row.get("about") or ()
    return str(about[0]) if about else ""


def alternative(
    ranked: Sequence[tuple[tuple[Any, ...], dict[str, Any]]],
    shown: tuple[str, str] | None,
    shown_topic: str = "",
) -> int:
    """Which of the ranked candidates "Something else" offers, as an index into them.

    The next best, unless one in the same tier is of another kind or collection than the
    text set aside: the first of those that is also on another topic, where the text set
    aside had one, else the first of another kind or collection, so the second pick is a
    different sort of thing rather than the first one's neighbour. Never a worse tier for
    the sake of variety.
    """
    if not ranked:
        return -1
    if shown is None:
        return 0
    tier = ranked[0][0][0]
    other = -1
    for at, (rank, row) in enumerate(ranked):
        if rank[0] != tier:
            break
        if cluster(row) == shown:
            continue
        if not shown_topic or topic(row) != shown_topic:
            return at
        if other < 0:
            other = at
    return max(other, 0)
