"""What comes out on its own clock, and where each one is this week.

A series is a thing a reader can follow (2026-09-11): the weekly, the weekly portion, and
each learning cycle. Following is the browser's business (`follow.js`); this is the
server's half — the current instalment of each, with the address of its reader, so the
front page can put a new one in the sheet and the bell can say it landed. Every series is
read off what is built, never off the network, and one that cannot be read on this box
simply has no instalment.
"""

from __future__ import annotations

import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .accounts import Store
    from .mail import Mailer

log = logging.getLogger(__name__)


def _weekly() -> dict[str, Any]:
    from .weekly import index as weekly
    from .weekly.models import LEVELS, folder

    out: dict[str, Any] = {
        "id": "weekly",
        "name": "Weekly News Digest",
        "hebrew": "מבט השבוע",
        "what": "Hebrew news, written three ways, every week.",
        "page": "/weekly",
        "instalment": None,
    }
    issue = next(iter(weekly.readable()), None)
    if issue is None:
        return out
    out["instalment"] = {
        "id": issue.id,
        "title": issue.title,
        "when": issue.dated,
        # One reader a level; the page picks the level for its reader.
        "levels": [
            {
                "level": edition.level.value,
                "name": LEVELS[edition.level].name,
                "folder": folder(issue.id, edition.level),
                "reader": f"/reader/{folder(issue.id, edition.level)}/reader/index.html",
            }
            for edition in issue.editions
        ],
    }
    return out


def _parasha(schedule: str) -> dict[str, Any]:
    from .parasha import build as corpus
    from .parasha.calendar import Schedule, pointing_at

    out: dict[str, Any] = {
        "id": "parasha",
        "name": "The weekly portion",
        "hebrew": "פרשת השבוע",
        "what": "This Shabbat's reading, with its cantillation, every week.",
        "page": "/parasha",
        "instalment": None,
    }
    index = corpus.load()
    if not index.portions:
        return out
    which = Schedule.israel if schedule == "israel" else Schedule.diaspora
    portion = corpus.current(which, index=index)
    if portion is None or portion.folder not in corpus.readable(index):
        return out
    out["instalment"] = {
        "id": portion.slug,
        "title": portion.name,
        "hebrew": portion.hebrew,
        "when": pointing_at().isoformat(),
        "reader": f"/parasha/read/{portion.folder}/reader/sec-0001.html",
    }
    return out


def _daily() -> list[dict[str, Any]]:
    from .daily import build as corpus
    from .daily.calendar import for_day, today
    from .daily.cycles import CYCLES

    out: list[dict[str, Any]] = []
    for cycle in CYCLES:
        one: dict[str, Any] = {
            "id": cycle.slug,
            "name": cycle.name,
            "hebrew": cycle.hebrew,
            "what": cycle.blurb,
            "page": f"/{cycle.slug}",
            "instalment": None,
        }
        day = for_day(cycle, today(), allow_fetch=False)
        if day is not None and corpus.readable(cycle.slug, day.day):
            one["instalment"] = {
                "id": day.slug,
                "title": day.title,
                "hebrew": day.hebrew,
                "when": day.slug,
                "reader": f"/{cycle.slug}/read/{day.slug}/reader/"
                f"{corpus.opens_at(cycle.slug, day.day)}",
            }
        out.append(one)
    return out


def current(schedule: str = "diaspora", *, public: bool = True) -> list[dict[str, Any]]:
    """Every series, each with its current instalment where this box has one built.

    The portion and the cycles have pages only where the shelves are public; on a box that
    keeps them shut they are not offered, since a page nobody can reach is not a series to
    follow. The weekly's readers are on every shelf.
    """
    found: list[dict[str, Any]] = []
    for name, ask in (
        ("weekly", _weekly),
        ("parasha", lambda: _parasha(schedule)),
        ("daily", _daily),
    ):
        if name != "weekly" and not public:
            continue
        try:
            got = ask()
        except Exception as error:  # pragma: no cover - a box missing one corpus
            log.warning("series: %s unavailable: %s", name, error)
            continue
        found.extend(got if isinstance(got, list) else [got])
    return found


# -- telling followers (2026-09-11) --------------------------------------------------------
#
# The weekly has a mailout of its own (`weekly.mailout`) and is left to it; this is for
# the rest. The same one property: running it twice sends nothing the second time.

BATCH = 25
PAUSE = 2.0

SUBJECT = "{name}: {title}"

BODY = """{name} — {title}{hebrew}

It is on targum now: {where}

You are getting this because you follow {name}. To stop: {stop}
"""


@dataclass
class Report:
    sent: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    stopped: str = ""

    def __str__(self) -> str:
        line = f"{len(self.sent)} sent"
        if self.failed:
            line += f", {len(self.failed)} failed"
        if self.stopped:
            line += f" — stopped: {self.stopped}"
        return line


def letter(one: dict[str, Any], address: str, stop_token: str) -> tuple[str, str]:
    inst = one["instalment"]
    hebrew = f" · {inst['hebrew']}" if inst.get("hebrew") else ""
    where = f"{address.rstrip('/')}{one['page']}"
    body = BODY.format(
        name=one["name"],
        title=inst["title"],
        hebrew=hebrew,
        where=where,
        stop=f"{address.rstrip('/')}/series/stop?t={stop_token}",
    )
    return SUBJECT.format(name=one["name"], title=inst["title"]), body


def announce(
    store: Store,
    mailer: Mailer,
    address: str,
    found: list[dict[str, Any]] | None = None,
    *,
    batch: int = BATCH,
    pause: float = PAUSE,
) -> Report:
    """Mail everyone who follows a series and has not had its current instalment."""
    from .mail import SmtpMailer

    report = Report()
    for one in found if found is not None else current():
        if one["id"] == "weekly" or not one.get("instalment"):
            continue
        inst = one["instalment"]
        waiting = store.followers(one["id"], not_sent=str(inst["id"]))
        if not waiting:
            continue
        holding = mailer.session() if isinstance(mailer, SmtpMailer) else contextlib.nullcontext()
        try:
            with holding:
                for index, (email, stop_token) in enumerate(waiting):
                    subject, body = letter(one, address, stop_token)
                    unsubscribe = f"<{address.rstrip('/')}/series/stop?t={stop_token}>"
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
                        continue
                    store.mark_series_sent(email, one["id"], str(inst["id"]))
                    report.sent.append(email)
                    if pause and batch and (index + 1) % batch == 0 and index + 1 < len(waiting):
                        time.sleep(pause)
        except Exception as error:  # noqa: BLE001 - the session itself, not one address
            report.stopped = str(error)
            break
    return report
