"""Letting the next few people in (targum-internal#292).

The front door takes an address and promises one thing: "We're opening in small groups.
We'll email you when your turn comes." Everything needed to keep that promise was already
here and none of it was joined up — `waiting_for_a_way_in` had no caller, `invite` never
read the waitlist, and no invitation mail existed. This is the join.

**Three acts, in this order, per person.** Invite them, mail them, stamp them. The order
is the careful part: `invite` before the mail, so a link that arrives first still works;
the stamp last, so a mail that could not be sent leaves the row unstamped and the next
run tries again. A crash between the mail and the stamp sends somebody a second
invitation, which is a duplicate in an inbox; a crash the other way round would leave
somebody stamped as invited who never heard, and they would wait for ever. The cheap
failure is the one to choose.

**It never opens the door to somebody who did not ask.** The only source is
`waiting_for_a_way_in`: confirmed, not yet invited, oldest first. There is no argument
for an arbitrary address, because `targum invite` is already that and says so.

**And then their saved link is built** (targum-internal#399; David, 2026-10-01). Somebody
who tried a link on the front page joined with it, and the door promised it would be
waiting. `then` is told each address that was let in, after the stamp, and whatever it
does — the server starts the build, on targum's budget — cannot undo the invitation: it
runs last and anything it raises is swallowed here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .accounts import Store
    from .letters import Letter
    from .mail import Mailer


@dataclass(frozen=True)
class Opened:
    """One person let in, or not, and which."""

    email: str
    language: str
    #: Empty where it worked; what went wrong where it did not.
    failed: str = ""

    @property
    def ok(self) -> bool:
        return not self.failed


def invitation(address: str, language: str) -> Letter:
    """The mail, in the language they joined in, drawn by `letters.invitation`.

    It carries no sign-in token. The address is on the guest list by the time this is
    written, so the ordinary sign-in page mints them a link the usual way — and a token
    minted here would be one sitting in an inbox for however long it takes them to read
    it, which is longer than a sign-in link is meant to live.
    """
    from . import letters

    return letters.invitation(address, language)


def open_the_door(
    store: Store,
    mailer: Mailer | None,
    address: str,
    count: int,
    dry_run: bool = False,
    then: Callable[[str, str], None] | None = None,
) -> list[Opened]:
    """Let the next `count` people in, oldest first, and write to each of them.

    Returns one row per person, in the order they were taken. A dry run resolves exactly
    the same list and changes nothing — no invitation, no mail, no stamp — so the answer
    to "who is next" is the same question as "who would this let in", asked safely.
    """
    if count <= 0:
        return []
    waiting = store.waiting_for_a_way_in(limit=count)
    if dry_run:
        return [Opened(email, language) for email, language in waiting]
    if mailer is None:
        raise ValueError("No mailer configured, so nobody can be told their turn has come.")
    if not address:
        raise ValueError("No address for this install, so the mail would carry no link.")

    return [_let(store, mailer, address, email, language, then) for email, language in waiting]


def let_in(
    store: Store,
    mailer: Mailer | None,
    address: str,
    email: str,
    then: Callable[[str, str], None] | None = None,
) -> Opened | None:
    """Let one person in, chosen by the operator from the waitlist (2026-09-28).

    David wanted to accept each person himself rather than the next few in order. The
    rule above still holds: only an address that asked and confirmed, and has not been
    let in, can be let in here — anything else answers None and changes nothing, so a
    form cannot be made to invite an address that never joined.
    """
    wanted = email.strip().lower()
    for waiting, language in store.waiting_for_a_way_in():
        if waiting.lower() == wanted:
            if mailer is None:
                raise ValueError("No mailer configured, so nobody can be told their turn has come.")
            if not address:
                raise ValueError("No address for this install, so the mail would carry no link.")
            return _let(store, mailer, address, waiting, language, then)
    return None


def _let(
    store: Store,
    mailer: Mailer,
    address: str,
    email: str,
    language: str,
    then: Callable[[str, str], None] | None = None,
) -> Opened:
    """Invite, mail, stamp: the three acts, in the order the module's docstring gives."""
    try:
        store.invite(email)
        letter = invitation(address, language)
        mailer.notify(email, letter.subject, letter.text, None, letter.html)
    except Exception as error:  # noqa: BLE001 — one bad address must not stop the rest
        # Left unstamped on purpose: the next run picks them up again. Reported rather
        # than raised, because a batch of ten in which one address bounces should let
        # the other nine in.
        return Opened(email, language, failed=str(error) or error.__class__.__name__)
    store.waiting_invited(email)
    if then is not None:
        try:
            then(email, language)
        except Exception:  # noqa: BLE001 — the invitation has gone; the link stays saved
            pass
    return Opened(email, language)
