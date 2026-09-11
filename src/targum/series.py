"""What comes out on its own clock, and where each one is this week.

A series is a thing a reader can follow (2026-09-11): the weekly, the weekly portion, and
each learning cycle. Following is the browser's business (`follow.js`); this is the
server's half — the current instalment of each, with the address of its reader, so the
front page can put a new one in the sheet and the bell can say it landed. Every series is
read off what is built, never off the network, and one that cannot be read on this box
simply has no instalment.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def _weekly() -> dict[str, Any]:
    from .weekly import index as weekly
    from .weekly.models import LEVELS, folder

    out: dict[str, Any] = {
        "id": "weekly",
        "name": "The weekly",
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
