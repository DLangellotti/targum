"""What a reader subscribed to, and what each subscription brought.

design.md §12, "A subscription is the account's, and what it brings comes under
Continue" (2026-10-09). A subscription is a row on the account (`Store.add_subscription`):
one of targum's series, a news topic, one outlet, a YouTube channel or a podcast. What it
brings is a `sub_item` row each — an instalment, an article, a video, an episode.

This module says what the rows are for the page: the Subscriptions tab on home and each
subscription's own page read `shown` and `one`, which add what the row does not hold —
a series' name and its instalment this week, how often something comes out, and the
month's credits a channel or a podcast has built with. Everything here reads; nothing
fetches and nothing spends.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from .accounts import CAPS, DEFAULT_CAP, SUB_BUILDS, SUB_KINDS

if TYPE_CHECKING:
    from .accounts import Store

#: The order the tab's rows and chips go in.
ORDER = {kind: n for n, kind in enumerate(SUB_KINDS)}

#: How far back "how often it comes out" is counted from what a subscription brought.
CADENCE_DAYS = 30

#: An item is New on home for this long after it was found, and no longer: news for as
#: long as it is the week's (follow.js's ten days, 2026-09-14).
NEW_FOR_MS = 10 * 24 * 3600 * 1000

__all__ = ["CAPS", "DEFAULT_CAP", "ORDER", "SUB_BUILDS", "one", "shown"]


def _series_rows(schedule: str, public: bool, language: str) -> dict[str, dict[str, Any]]:
    from . import series

    return {
        str(row["id"]): row for row in series.current(schedule, public=public, language=language)
    }


def _every(kind: str, key: str, series_row: Mapping[str, Any] | None) -> str:
    """How often a subscription comes out, as a word the page says: `day`, `week`,
    `monday` (the weekly), or `feed` for anything that comes out when it comes out."""
    if kind != "series":
        return "feed"
    if key == "weekly":
        return "monday"
    if series_row is not None and series_row.get("cadence") == "daily":
        return "day"
    return "week"


def per_week(items: Iterable[Mapping[str, Any]], now_ms: int) -> float:
    """How many a week came out over the last thirty days, from what was found: a
    channel's "about 2 a week". Zero where nothing in that window says."""
    since = now_ms - CADENCE_DAYS * 24 * 3600 * 1000
    count = sum(
        1 for item in items if int(item.get("published") or item.get("found") or 0) >= since
    )
    return round(count * 7 / CADENCE_DAYS, 1)


def _instalment_item(series_row: Mapping[str, Any]) -> dict[str, Any] | None:
    """A series' current instalment as an item, where this box has one built: what the
    tab shows as Latest before the poll has written any (`series.current`)."""
    inst = series_row.get("instalment")
    if not inst:
        return None
    reader = str(inst.get("reader") or "")
    if not reader and inst.get("levels"):
        first = inst["levels"][0]
        reader = str(first.get("reader") or "")
    return {
        "key": str(inst.get("id") or ""),
        "title": str(inst.get("hebrew") or inst.get("title") or ""),
        "english": str(inst.get("title") or ""),
        "reader": reader,
        "state": "ready",
        "when": str(inst.get("when") or ""),
        "levels": inst.get("levels") or [],
        "came": "",
    }


def _named(row: Mapping[str, Any], series_row: Mapping[str, Any] | None) -> dict[str, str]:
    if series_row is not None:
        return {
            "name": str(series_row.get("name") or row["key"]),
            "hebrew": str(series_row.get("hebrew") or ""),
            "page": str(series_row.get("page") or ""),
        }
    return {"name": str(row.get("name") or row["key"]), "hebrew": "", "page": ""}


def _item(item: Mapping[str, Any]) -> dict[str, Any]:
    """An item as the page reads it: no job ids, nothing the page has no use for."""
    return {
        "key": item["key"],
        "title": item["title"],
        "link": item["link"],
        "reader": item["reader"],
        "published": int(item["published"] or 0),
        "found": int(item["found"] or 0),
        "seconds": float(item["seconds"] or 0),
        "state": item["state"],
        "why": item["why"],
        "credits": int(item["credits"] or 0),
        "came": item["came"],
        "seen": bool(item["seen"]),
        "building": bool(item["job"]) and item["state"] == "building",
    }


def _opened(store: Store, person_id: int, items: list[dict[str, Any]]) -> None:
    """Where a listed item was got ready by the reader's own press since — on the Upload
    page, from the link it carries — it opens as that text. Read off their job rows, so
    nothing else has to remember it."""
    links = [item["link"] for item in items if item["state"] == "listed" and item["link"]]
    if not links:
        return
    holes = ", ".join("?" for _ in links)
    rows = store.db.execute(
        f"SELECT source, reader, stage FROM job WHERE owner = ? AND source IN ({holes})"
        " ORDER BY made",
        (person_id, *links),
    ).fetchall()
    built = {str(row["source"]): str(row["reader"]) for row in rows if row["stage"] == "done"}
    for item in items:
        reader = built.get(item["link"])
        if item["state"] == "listed" and reader:
            item["state"] = "ready"
            item["reader"] = f"/reader/{reader}/reader/index.html"


def shown(
    store: Store,
    person_id: int,
    *,
    month_from: int,
    now_ms: int,
    schedule: str = "diaspora",
    public: bool = True,
    language: str = "en",
) -> list[dict[str, Any]]:
    """Every subscription of this reader's that is not stopped, as the tab draws it."""
    series_rows = _series_rows(schedule, public, language)
    out = []
    for row in store.subscriptions(person_id):
        out.append(
            _shown_row(store, person_id, row, series_rows, month_from=month_from, now_ms=now_ms)
        )
    out.sort(key=lambda one: (ORDER.get(one["kind"], 9), one["name"].lower()))
    return out


def _shown_row(
    store: Store,
    person_id: int,
    row: Mapping[str, Any],
    series_rows: Mapping[str, Mapping[str, Any]],
    *,
    month_from: int,
    now_ms: int,
) -> dict[str, Any]:
    series_row = series_rows.get(str(row["key"])) if row["kind"] == "series" else None
    items = store.sub_items(int(row["id"]), limit=40)
    latest = row.get("latest")
    shown_latest = _item(latest) if latest else None
    if row["kind"] == "series" and series_row is not None:
        current = _instalment_item(series_row)
        if current is not None and (shown_latest is None or shown_latest["key"] != current["key"]):
            shown_latest = current
    if shown_latest is not None:
        _opened(store, person_id, [shown_latest])
    builds = row["kind"] in SUB_BUILDS
    return {
        "id": int(row["id"]),
        "kind": row["kind"],
        "key": row["key"],
        **_named(row, series_row),
        "language": row["language"] or "he",
        "source": row["source"],
        "state": row["state"],
        "since": int(row["since"]),
        "paused": int(row["paused"] or 0),
        "every": _every(str(row["kind"]), str(row["key"]), series_row),
        "perWeek": per_week(items, now_ms) if row["kind"] != "series" else 0,
        "builds": builds,
        "cap": int(row["cap"] or 0) if builds else 0,
        "used": store.month_credits(person_id, int(row["id"]), month_from) if builds else 0,
        "latest": shown_latest,
        "new": int(row.get("new") or 0),
        "page": f"/subscriptions/{int(row['id'])}",
    }


def one(
    store: Store,
    person_id: int,
    sub_id: int,
    *,
    month_from: int,
    now_ms: int,
    schedule: str = "diaspora",
    public: bool = True,
    language: str = "en",
) -> dict[str, Any] | None:
    """One subscription with everything it brought, newest first, for its own page. None
    where it is not this reader's."""
    row = store.subscription(person_id, sub_id)
    if row is None:
        return None
    row = {**row, "latest": None, "new": 0}
    series_rows = _series_rows(schedule, public, language)
    out = _shown_row(store, person_id, row, series_rows, month_from=month_from, now_ms=now_ms)
    items = [_item(item) for item in store.sub_items(sub_id, limit=120)]
    series_row = series_rows.get(str(row["key"])) if row["kind"] == "series" else None
    if series_row is not None:
        current = _instalment_item(series_row)
        if current is not None and not any(item["key"] == current["key"] for item in items):
            items.insert(0, {**current, "published": 0, "found": 0, "seconds": 0.0})
    _opened(store, person_id, items)
    out["items"] = items
    out["caps"] = list(CAPS)
    return out
