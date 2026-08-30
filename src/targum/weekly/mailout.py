"""Telling everybody a new issue is out.

Public, and small on purpose. The one property that matters here is that running it
twice sends nothing the second time: a mailout that re-sends the whole list is the
failure that costs a sending domain its reputation, and on this box the sign-in link
goes out over the same domain — so losing it would take the product down with it.

Publishing and announcing are two verbs. An issue stays published whether or not the
mail went, and a mailout that died halfway is resumed by running it again.
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..mail import Mailer, SmtpMailer
from .entries import NOTICE
from .models import LEVELS, Issue, Level

if TYPE_CHECKING:
    from ..accounts import Store

#: How many go out before the run pauses. Not a provider limit — a courtesy, so a run
#: that turns out to be wrong can be stopped after twenty-five rather than after all of
#: them, and so a shared box is not saturated for the length of a mailout.
BATCH = 25
PAUSE = 2.0

SUBJECT = "the weekly — {dated}"

BODY = """{title}, for the week of {dated}.

Five sections in Modern Hebrew, written at three levels:

{levels}

{notice}

Read it: {where}

You are getting this because you asked for it. To stop: {stop}
"""


@dataclass
class Report:
    sent: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    #: Set when the whole session failed — a bad password, a provider refusing the
    #: connection — as against one address that would not take it. The difference
    #: decides whether the rest of the list is still worth trying.
    stopped: str = ""

    def __str__(self) -> str:
        line = f"{len(self.sent)} sent"
        if self.failed:
            line += f", {len(self.failed)} failed"
        if self.stopped:
            line += f" — stopped: {self.stopped}"
        return line


def letter(issue: Issue, address: str, stop_token: str) -> tuple[str, str]:
    where = f"{address.rstrip('/')}/weekly/{issue.id}"
    levels = "\n".join(
        f"  {LEVELS[level].label} — {where}/{level.value}"
        for level in Level
        if issue.edition(level) is not None
    )
    body = BODY.format(
        title=issue.title,
        dated=issue.dated,
        levels=levels,
        notice=NOTICE,
        where=where,
        stop=f"{address.rstrip('/')}/weekly/stop?t={stop_token}",
    )
    return SUBJECT.format(dated=issue.dated), body


def announce(
    store: Store,
    mailer: Mailer,
    issue: Issue,
    address: str,
    *,
    batch: int = BATCH,
    pause: float = PAUSE,
) -> Report:
    """Send this issue to everybody who has not had it.

    The list is selected on "has not had *this* issue" rather than on "is subscribed",
    which is the whole of the idempotence: a crashed run resumed re-mails nobody, and a
    second run on a finished issue finds an empty list.
    """
    report = Report()
    waiting = store.subscribers(not_sent=issue.id)
    if not waiting:
        return report

    holding = mailer.session() if isinstance(mailer, SmtpMailer) else contextlib.nullcontext()
    try:
        with holding:
            for index, (email, stop_token) in enumerate(waiting):
                subject, body = letter(issue, address, stop_token)
                unsubscribe = f"<{address.rstrip('/')}/weekly/stop?t={stop_token}>"
                try:
                    mailer.notify(
                        email,
                        subject,
                        body,
                        {
                            "List-Unsubscribe": unsubscribe,
                            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                        },
                    )
                except Exception as error:  # noqa: BLE001 - one bad address, not the run
                    report.failed.append((email, str(error)))
                    store.bounced(email)
                    continue
                # Recorded per address rather than at the end, so an interrupted run has
                # already remembered everyone it reached.
                store.mark_sent(email, issue.id)
                report.sent.append(email)
                if pause and batch and (index + 1) % batch == 0 and index + 1 < len(waiting):
                    time.sleep(pause)
    except Exception as error:  # noqa: BLE001 - the session itself, not one address
        # Whoever is left keeps their place: they have not been marked, so the next run
        # picks them up.
        report.stopped = str(error)
    return report
