""" "Find me something": one real article, chosen for one reader (targum-internal#615).

David's spec, 2026-11-01. A button on Your targums finds **one** real article that
interests the reader and that they can read; "Another" shows the next best; one tap
builds it as the reader's own targum on their credits, through the web find's own press
(`serve.Handler._open_find`, so `Library.prepare`, `Library.press` and `Library.claim`).

**Where it looks.** The ready pool first, which answers at once and fetches nothing
(`provider.offered`: measured, in the band and clear of the floor by the scorer's
margin). Only when nothing there fits does it look on the web (`live.py`), and that is
targum's spend inside the discovery budget, never the reader's.

**What fits.** A find in the band (`choose.FLOOR`, 90% of its running words, plus the
provider's margin). Where the reader chose chips (`chips.CHIPS`), a find must also be
about one of them: brought in by a live look for that chip, or carrying its lexicon
topic's words (`interests.ABOUT_LEAST`) where the lexicon has the topic. Where they
skipped the chips, the topics their reading suggests (`interests.inferred`) put a find
ahead of an equal one and keep none out. Inside that, `choose.key`: nearest the 94–97% aim
first, and among finds that fit as well, the one whose new words come back (`learning.
bag_value`, targum-internal#614).

**Credits.** A find that costs more than the reader has left is still offered here, and
says so (`over`), because the reader asked; Read next leaves it out, because it was not
asked for (web discovery plan §7).

Off unless the deployment says so (`TARGUM_FIND_BUTTON`): the page draws no button and
`POST /find` answers 404.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .. import choose, learning
from . import chips, provider
from . import interests as interests_module

if TYPE_CHECKING:
    from ..accounts import Store
    from ..estimate import Estimate

FLAG = "TARGUM_FIND_BUTTON"


def on() -> bool:
    """Whether the button is drawn and `POST /find` answers."""
    return os.environ.get(FLAG, "").strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Ask:
    """What one press of the button asks for."""

    language: str
    #: Chips the reader chose (`chips.CHIPS` codes); empty where they skipped them.
    chosen: tuple[str, ...] = ()
    #: Lexicon topics their reading suggests (`interests.inferred`), used only where
    #: `chosen` is empty.
    liked: tuple[str, ...] = ()
    #: Card ids already shown on this visit, which "Another" passes over.
    skip: tuple[str, ...] = ()

    @property
    def wanted(self) -> tuple[str, ...]:
        """What a live look searches for: the chips chosen, else the topics liked."""
        return self.chosen or self.liked

    @property
    def steered(self) -> bool:
        return bool(self.chosen)


def _chip_matched(
    ask: Ask, find_topics: Iterable[str], about: Mapping[str, float], shown: Iterable[str]
) -> str:
    """The first chosen chip a find is about, or "": a find a live look brought in for
    the chip, or one whose words are the chip's lexicon topic where that is shown."""
    tags = set(find_topics)
    for code in ask.chosen:
        if chips.tag(code) in tags:
            return code
        topic = chips.matcher(code, shown)
        if topic and about.get(topic, 0.0) >= interests_module.ABOUT_LEAST:
            return code
    return ""


def ranked(
    store: Store,
    ask: Ask,
    marked: Mapping[str, int],
    *,
    estimate: Estimate | None = None,
    rung: int | None = None,
    built: Iterable[str] = (),
    credits_left: int | None = None,
    known: interests_module.Lexicon | None = None,
    at: int | None = None,
) -> list[dict[str, Any]]:
    """Every pool find this reader could be offered for this press, best first, each as
    the card's row. Fetches nothing. With chips chosen, only finds about one of them."""
    found = provider.offered(
        store,
        ask.language,
        marked,
        rung=rung,
        credits_left=None,
        built=built,
        skip=ask.skip,
        at=at,
        estimate=estimate,
    )
    shown = known.shown if known else ()
    useful = learning.usefulness(ask.language)
    out: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    for scored in found:
        find = scored.find
        topics = interests_module.about(find.bag, find.tokens, known) if known else {}
        row = provider.row(scored)
        if ask.steered:
            chip = _chip_matched(ask, find.topics, topics, shown)
            if not chip:
                continue
            row["chip"] = chip
            on_topic = True
        else:
            liked = [
                code for code in ask.liked if topics.get(code, 0.0) >= interests_module.ABOUT_LEAST
            ]
            on_topic = bool(liked)
            if liked:
                row["because_topic"] = max(liked, key=lambda code: topics[code])
        row["about"] = sorted(topics, key=lambda code: -topics[code])
        row["topics"] = [one for one in find.topics if not one.startswith(chips.TAG)]
        row["over"] = credits_left is not None and find.credits > credits_left
        medium = choose.medium_of(find.medium)
        row["fit"] = choose.fit(scored.chosen_on, medium)
        learn = 0.0
        if estimate is not None:
            learn = learning.bag_value(
                find.bag,
                find.tokens,
                estimate.p_known,
                useful,
                liked=ask.wanted,
                lexicon=known,
            )
            row["learn"] = round(learn, 3)
        rank = choose.key(scored.chosen_on, medium=medium, learn=learn)
        # Inside a tier, a find on the reader's topics first, then fit and what it would
        # teach (`choose.key`), then fresh.
        key = (rank[0], 0 if on_topic else 1, *rank[1:], -find.published, find.id)
        out.append((key, row))
    out.sort(key=lambda pair: pair[0])
    return [row for _, row in out]


def fits(rows: Sequence[dict[str, Any]]) -> bool:
    """Whether the best row is one to offer without looking further: in the band."""
    return bool(rows) and rows[0].get("fit") == choose.BAND
