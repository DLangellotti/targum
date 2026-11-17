"""Plans, behind a switch (design.md §12, "Free and Plan, behind a switch", "The plans
page is the one place money shows" and "A free reader meets the plan where they reach for
it", 2026-10-09; David, 2026-10-08: plans ship behind `TARGUM_PLANS=0`).

**With the switch off, as it is on the box, nothing here changes anything:** every
account gets the library's whole month of credits (480) and a word list of any length,
and anybody may subscribe to a channel or a podcast.

With it on there are two plans. **Free** gets 60 credits a month and a word list of 300
words being learned; **Plan** gets the whole month and no cap, and is the only one that
may subscribe to something that gets ready by itself. Until there is a payment provider
nobody can buy Plan, so on means the operator (`Person.admin`), which is how a box can
be tried with plans on before anybody can buy one, and the beta comped to Plan.

**The comp** (design.md §12, "Signup opens before payments, and the beta is comped to
Plan", 2026-11-15; targum-internal#59). Every account that exists on switch day, and
anyone let in from the waitlist while invitations are still going out, is on Plan until
`BETA_UNTIL` (`Person.plan_until`, set by `targum comp-beta` and by `doorway`'s Let in).
On that day the comp simply ends and the reader is on Free: no mail, nothing automatic,
because what happens then is not decided yet.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime
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
#: The first day the beta's comp to Plan no longer holds: Launch (targum-internal#481).
BETA_UNTIL = "2027-03-04"


def on() -> bool:
    """Whether plans are switched on (`TARGUM_PLANS`). Off unless the deployment says."""
    return os.environ.get("TARGUM_PLANS", "").strip().lower() in {"1", "true", "yes", "on"}


#: The operator's preview of plans while they are off (targum-internal#59 phase 2): set to
#: `operators`, an admin account sees `/plans` and its own plan as a reader would, so
#: paying through Paddle's sandbox can be tried on the box before switch day. Nothing
#: else reads it: `on()` stays off, and so does every limit, for everybody.
PREVIEW_ENV = "TARGUM_PLANS_PREVIEW"


def previewing(person: Person | None) -> bool:
    """Whether this account sees plans in the operator's preview: plans off, the preview
    set to `operators`, and the account an admin. Never anybody else, and never while
    plans are on, when everybody sees them anyway."""
    if on() or person is None or not bool(getattr(person, "admin", False)):
        return False
    return os.environ.get(PREVIEW_ENV, "").strip().lower() == "operators"


def shown(person: Person | None) -> bool:
    """Whether the plan pages are there for this account: plans on, or its preview."""
    return on() or previewing(person)


def _until(person: Person | None) -> date | None:
    """The day this reader's comp ends, if they have one that reads as a day."""
    # Read leniently: a stand-in for a person that says only `admin` has no comp.
    said = str(getattr(person, "plan_until", "") or "")
    try:
        return date.fromisoformat(said) if said else None
    except ValueError:
        return None


def comped(person: Person | None, today: date | None = None) -> bool:
    """Whether this reader is comped to Plan today: before the comp's day, never on it."""
    until = _until(person)
    return until is not None and (today or datetime.now(UTC).date()) < until


def paid(person: Person | None) -> bool:
    """Whether this account is on Plan. Nobody can pay yet; the operator stands in for
    one so the switch can be tried, and a beta reader is comped until `BETA_UNTIL`."""
    return person is not None and (bool(person.admin) or comped(person))


def until_said(until: str, language: str = "en") -> str:
    """The comp's day in a sentence, month first in English as every date in the product
    ("March 4, 2027"), «4 марта 2027» in Russian."""
    from .strings import said_day

    when = date.fromisoformat(until)
    if language.split("-")[0].lower() == "en":
        return when.strftime("%B %-d, %Y")
    return said_day(when, language, year=True)


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


def summary(person: Person | None, *, listed: int = 0, language: str = "en") -> dict[str, Any]:
    """What a page needs to draw the plan: whether plans are on, which plan this is, the
    month's credits, and the word cap with how many words are on the list now. A comped
    reader's also says until when (`comp`, an ISO day, and `compSaid`, in `language`).

    In the operator's preview (`previewing`) the operator is drawn as the reader they
    would be without being the operator, so Start the plan is offered and a plan paid
    for in the sandbox shows as it will for a reader; `preview` says so. Only the
    drawing: what the account may spend is `paid`, which still counts the operator."""
    preview = previewing(person)
    if not on() and not preview:
        return {"on": False}
    if preview and person is not None:
        from dataclasses import replace

        person = replace(person, admin=False)
    is_paid = paid(person)
    comp: dict[str, Any] = {}
    if comped(person) and person is not None:
        comp = {"comp": person.plan_until, "compSaid": until_said(person.plan_until, language)}
    return {
        **comp,
        "on": True,
        "plan": "plan" if is_paid else "free",
        "credits": PLAN_CREDITS if is_paid else FREE_CREDITS,
        "planCredits": PLAN_CREDITS,
        "words": None if is_paid else FREE_WORDS,
        "listed": listed,
        "topUps": list(TOP_UPS) if is_paid else [],
        **({"preview": True} if preview else {}),
    }
