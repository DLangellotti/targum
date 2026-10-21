"""Plans, behind a switch (design.md §12, "Free and Plan, behind a switch", "The plans
page is the one place money shows" and "A free reader meets the plan where they reach for
it", 2026-10-09; David, 2026-10-08: plans ship behind `TARGUM_PLANS=0`).

**With the switch off, as it is on the box, nothing here changes anything:** every
account gets the library's whole month of credits (480) and a word list of any length,
and anybody may subscribe to a channel or a podcast.

With it on there are two plans. **Free** gets 60 credits a month and a word list of 300
words being learned; **Plan** gets the whole month and no cap, and is the only one that
may subscribe to something that gets ready by itself. Until there is a payment provider
nobody is on Plan, so on means the operator alone (`Person.admin`), which is how a box
can be tried with plans on before anybody can buy one.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .accounts import Person

#: What Free gets in a month, in credits (a credit is a minute of audio or video).
FREE_CREDITS = 60
#: What Plan gets in a month. The library's own allowance, `serve.UPLOAD_CREDITS`, says the
#: same; this is the figure the pricing page quotes when the server has no other.
PLAN_CREDITS = 480
#: How many words a free word list holds while they are being learned (stages 1 to 3).
FREE_WORDS = 300
#: What Plan costs, for the one page that says it: whole US dollars.
PRICE_MONTH = 16
PRICE_QUARTER = 39
#: What an hour of top-up costs, said on the pricing page only.
TOP_UP_HOUR = 3
#: The top-ups a reader on Plan is offered, in credits. Greyed until there is a provider.
TOP_UPS = (60, 180, 300)


def on() -> bool:
    """Whether plans are switched on (`TARGUM_PLANS`). Off unless the deployment says."""
    return os.environ.get("TARGUM_PLANS", "").strip().lower() in {"1", "true", "yes", "on"}


def paid(person: Person | None) -> bool:
    """Whether this account is on a paid plan. Nobody is until there is a way to pay; the
    operator stands in for one so the switch can be tried."""
    return person is not None and bool(person.admin)


def free(person: Person | None) -> bool:
    """Whether this reader is held to Free: plans on, and not on Plan."""
    return on() and not paid(person)


def builds_by_itself(person: Person | None) -> bool:
    """Whether this reader may subscribe to something that gets ready by itself: a
    channel or a podcast. Everybody while plans are off; a paid plan once they are on."""
    return not on() or paid(person)


def month_seconds(full: float | None, *, paid_plan: bool) -> float | None:
    """The month's allowance for one reader, in seconds, given the library's whole one.

    `full` is the library's (`Library.upload_seconds`), None where nobody is held to a
    month. Free gets the smaller of it and an hour, so a test library set to thirty
    seconds is not handed an hour by the switch."""
    if full is None or not on() or paid_plan:
        return full
    return min(full, FREE_CREDITS * 60.0)


def word_cap(person: Person | None) -> int | None:
    """How many words this reader's list may hold while being learned, or None."""
    return FREE_WORDS if free(person) else None


def summary(person: Person | None, *, listed: int = 0) -> dict[str, Any]:
    """What a page needs to draw the plan: whether plans are on, which plan this is, the
    month's credits, and the word cap with how many words are on the list now."""
    if not on():
        return {"on": False}
    is_paid = paid(person)
    return {
        "on": True,
        "plan": "plan" if is_paid else "free",
        "credits": PLAN_CREDITS if is_paid else FREE_CREDITS,
        "planCredits": PLAN_CREDITS,
        "words": None if is_paid else FREE_WORDS,
        "listed": listed,
        "topUps": list(TOP_UPS) if is_paid else [],
    }
