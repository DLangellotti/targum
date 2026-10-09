"""Plans, behind a switch (design.md §12, "A monthly cap is the second press that lasts",
2026-10-09; David, 2026-10-08: plans ship behind `TARGUM_PLANS=0`).

Today every account gets the same month of credits, and there is no paid plan to be on:
the free/paid split waits for a payment provider. What the switch decides already is the
one thing the Subscriptions slice made paid-only — **a YouTube channel or a podcast that
gets its new items ready by itself.** Series and news are free to everybody either way.

With the switch off, as it is on the box, everybody may subscribe to a channel or a
podcast. With it on, only somebody on a paid plan may; until there is a payment provider
nobody is, so on it means the operator alone (`Person.admin`), which is how a box can be
tried with plans on before anybody can buy one.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .accounts import Person


def on() -> bool:
    """Whether plans are switched on (`TARGUM_PLANS`). Off unless the deployment says."""
    return os.environ.get("TARGUM_PLANS", "").strip().lower() in {"1", "true", "yes", "on"}


def paid(person: Person | None) -> bool:
    """Whether this account is on a paid plan. Nobody is until there is a way to pay; the
    operator stands in for one so the switch can be tried."""
    return person is not None and bool(person.admin)


def builds_by_itself(person: Person | None) -> bool:
    """Whether this reader may subscribe to something that gets ready by itself: a
    channel or a podcast. Everybody while plans are off; a paid plan once they are on."""
    return not on() or paid(person)
