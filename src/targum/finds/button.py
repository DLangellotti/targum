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
provider's margin). Where the reader chose topics on the chips, a find must also be about
one of them (`interests.ABOUT_LEAST`); where they skipped the chips, the topics their
reading suggests (`interests.inferred`) put a find ahead of an equal one and keep none
out. Inside that, `choose.key`: nearest the 94–97% aim first.

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

from .. import choose
from . import interests as interests_module
from . import provider

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
    #: Topics the reader chose on the chips; empty where they skipped them.
    chosen: tuple[str, ...] = ()
    #: Topics their reading suggests (`interests.inferred`), used only where `chosen`
    #: is empty.
    liked: tuple[str, ...] = ()
    #: Card ids already shown on this visit, which "Another" passes over.
    skip: tuple[str, ...] = ()

    @property
    def wanted(self) -> tuple[str, ...]:
        return self.chosen or self.liked

    @property
    def steered(self) -> bool:
        return bool(self.chosen)


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
    the card's row. Fetches nothing."""
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
    wanted = ask.wanted
    out: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    for scored in found:
        find = scored.find
        topics = interests_module.about(find.bag, find.tokens, known) if known else {}
        matched = max((topics.get(code, 0.0) for code in wanted), default=0.0)
        on_topic = matched >= interests_module.ABOUT_LEAST
        if ask.steered and not on_topic:
            continue
        row = provider.row(scored)
        row["fit"] = choose.fit(scored.chosen_on)
        row["about"] = sorted(topics, key=lambda code: -topics[code])
        if on_topic:
            row["because_topic"] = max(
                (code for code in wanted if topics.get(code, 0.0) >= interests_module.ABOUT_LEAST),
                key=lambda code: topics[code],
            )
        row["over"] = credits_left is not None and find.credits > credits_left
        rank = choose.key(scored.chosen_on)
        # Inside a tier, a find on the reader's topics first, then the aim, then fresh.
        key = (rank[0], 0 if on_topic else 1, *rank[1:], -find.published, find.id)
        out.append((key, row))
    out.sort(key=lambda pair: pair[0])
    return [row for _, row in out]


def fits(rows: Sequence[dict[str, Any]]) -> bool:
    """Whether the best row is one to offer without looking further: in the band."""
    return bool(rows) and rows[0].get("fit") == choose.BAND
