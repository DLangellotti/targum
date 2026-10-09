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

import secrets
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
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


def door(item: Mapping[str, Any]) -> str:
    """Where an item opens: its reader once it has one, else the Upload page with its
    address in the box, where it is got ready on the reader's own press."""
    from urllib.parse import quote

    if item.get("reader"):
        return str(item["reader"])
    if item.get("link"):
        return "/add?source=" + quote(str(item["link"]), safe="")
    return ""


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


# -- what a subscription would be: the confirm page (design.md §12, 2026-10-09) --------
#
# Asked when the confirm page is drawn and again when it is pressed, so what is written
# is what the source says at the press and never what a form or a model claims it is.

#: How many of a channel's or a podcast's newest are listed as "Out before you
#: subscribed", each with a press of its own.
BEFORE_LISTED = 10


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _per_week_from(published: list[int], now_ms: int) -> float:
    return per_week(({"published": when} for when in published), now_ms)


def credits_of(seconds: float) -> int:
    """Seconds as the credits they use: a credit is a minute (design.md §12, 2026-09-23)."""
    from .accounts import SECONDS_A_CREDIT

    return max(1, round(float(seconds) / SECONDS_A_CREDIT)) if seconds else 0


def describe(
    kind: str, given: str, *, language: str = "he", ui: str = "en", now_ms: int = 0
) -> dict[str, Any]:
    """What subscribing to `given` would be: its key, its name, how often it comes out,
    what a new one usually uses, and — for a channel or a podcast — what was out before.

    `given` is a series' id, a topic, an outlet's key, a channel's address or a podcast's
    address. Raises `TargumError` with a key where it is none of those.
    """
    import time

    from .errors import TargumError

    stamp = now_ms or int(time.time() * 1000)
    given = given.strip()
    if kind not in SUB_KINDS or not given:
        raise TargumError("We couldn't tell what to subscribe to.", key="subscribe.what")
    out: dict[str, Any] = {
        "kind": kind,
        "key": given,
        "source": "",
        "name": "",
        "hebrew": "",
        "what": "",
        "language": language or "he",
        "perWeek": 0.0,
        "seconds": 0.0,
        "creditsEach": 0,
        "builds": kind in SUB_BUILDS,
        "outlets": 0,
        "before": [],
    }
    if kind == "series":
        from . import series

        row = next(
            (one for one in series.current(public=True, language=ui) if one["id"] == given), None
        )
        if row is None:
            raise TargumError("There's no such series.", key="subscribe.no-series")
        out.update(
            name=str(row.get("name") or given),
            hebrew=str(row.get("hebrew") or ""),
            what=str(row.get("what") or ""),
            language="he",
            every=_every("series", given, row),
        )
        return out
    if kind in ("topic", "outlet"):
        from .chat import sources

        if kind == "topic":
            if given not in sources.TOPICS:
                raise TargumError("There's no such topic.", key="subscribe.no-topic")
            code = (language or "he").split("-")[0].lower()
            out["outlets"] = sum(
                1
                for one in sources.load()
                if one.feed and one.language.split("-")[0].lower() == code
            )
            out["language"] = code
            return out
        publisher = sources.by_key(given)
        if publisher is None or not publisher.feed:
            raise TargumError("We don't follow that outlet.", key="subscribe.no-outlet")
        out.update(
            name=publisher.publisher or publisher.name,
            language=publisher.language.split("-")[0].lower() or "he",
            source=publisher.homepage or publisher.feed,
        )
        return out
    if kind == "channel":
        from .video import channels

        found = channels.find(given)
        uploads = channels.newest(found)
        lengths = [float(upload.seconds) for upload in uploads]
        out.update(
            key=found.id,
            source=f"https://www.youtube.com/channel/{found.id}",
            name=found.title,
            language=found.language or language or "he",
            perWeek=_per_week_from([upload.published for upload in uploads], stamp),
            seconds=_median(lengths),
            before=[
                {
                    "key": upload.id,
                    "title": upload.title,
                    "link": upload.link,
                    "published": upload.published,
                    "seconds": upload.seconds,
                }
                for upload in uploads[:BEFORE_LISTED]
            ],
        )
        out["creditsEach"] = credits_of(out["seconds"])
        return out
    # A podcast: its feed, and the episodes in it.
    from .audio import episode
    from .weekly.feeds import link_key

    feed = episode.feed_of(given)
    if not feed:
        raise TargumError(
            "We couldn't find that podcast's feed.",
            "Paste its RSS address, or its page on Apple Podcasts.",
            key="subscribe.no-feed",
        )
    title, items = episode.episodes(feed)
    if not items:
        raise TargumError("That feed has no episodes we can read.", key="subscribe.no-episodes")
    published = [
        int(item.published.timestamp() * 1000) for item in items if item.published is not None
    ]
    out.update(
        key=link_key(feed),
        source=feed,
        name=title or feed,
        perWeek=_per_week_from(published, stamp),
        seconds=_median([float(item.seconds) for item in items if item.seconds]),
        before=[podcast_item(item) for item in items[:BEFORE_LISTED]],
    )
    out["creditsEach"] = credits_of(out["seconds"])
    return out


def podcast_item(item: Any) -> dict[str, Any]:
    """One episode as a subscription's item: keyed by its guid, built from its audio."""
    return {
        "key": str(item.guid or item.enclosure),
        "title": item.title,
        "link": item.enclosure,
        "published": int(item.published.timestamp() * 1000) if item.published else 0,
        "seconds": float(item.seconds or 0),
    }


def subscribe(
    store: Store, person_id: int, offer: Mapping[str, Any], *, cap: int, said: str
) -> dict[str, Any]:
    """Write the subscription the reader pressed for, and list what was out before it as
    a press each. The cap is the reader's choice from the page, and nothing else's."""
    builds = offer["kind"] in SUB_BUILDS
    row = store.add_subscription(
        person_id,
        str(offer["kind"]),
        str(offer["key"]),
        name=str(offer.get("name") or ""),
        language=str(offer.get("language") or ""),
        source=str(offer.get("source") or ""),
        cap=(cap if cap in CAPS else DEFAULT_CAP) if builds else 0,
        said=said,
    )
    before = [
        {**item, "state": "listed", "came": "before"}
        for item in offer.get("before") or []
        if int(item.get("published") or 0) < int(row["since"])
    ]
    if before:
        store.add_sub_items(int(row["id"]), before)
    return row


# -- looking for what is new: the poll (design.md §12, 2026-10-09) -----------------------
#
# Run by targum-subscriptions.timer on the box (`targum subscriptions poll`). It reads
# every source a live subscription names and writes what it finds as items; it never
# builds and never spends. Idempotent — an item is keyed by what its source calls it, so
# a look that runs twice finds nothing the second time — and checkpointed: a
# subscription is stamped as looked at once its items are written, and the next run
# starts with the ones looked at longest ago, so a run that dies resumes where it stopped.

#: How many of a news subscription's items are kept a day: "up to 3 a day" (board
#: SubsTab). A topic across a dozen papers is a hundred headlines a day, and a mail or a
#: home of a hundred links is one nobody opens.
NEWS_A_DAY = 3


@dataclass
class Looked:
    """What one run of the poll found: how many items, from how many subscriptions, and
    what would not answer."""

    looked: int = 0
    found: int = 0
    failed: list[tuple[int, str]] = field(default_factory=list)

    def __str__(self) -> str:
        line = f"{self.looked} looked at, {self.found} new"
        if self.failed:
            line += f", {len(self.failed)} would not answer"
        return line


def _came(row: Mapping[str, Any], published: int) -> str:
    """Whether an item is news to this subscription: what came out before it began is
    `before`, what came out while it was paused is `paused`, and either waits for a press."""
    if published and published < int(row["since"]):
        return "before"
    if row["state"] == "paused":
        return "paused"
    return ""


def _series_items(row: Mapping[str, Any], public: bool) -> list[dict[str, Any]]:
    from . import series

    found = next((one for one in series.current(public=public) if one["id"] == row["key"]), None)
    current = _instalment_item(found) if found is not None else None
    if current is None or not current["key"]:
        return []
    return [
        {
            "key": current["key"],
            "title": current["title"],
            "reader": current["reader"],
            "state": "ready",
            "came": "paused" if row["state"] == "paused" else "",
        }
    ]


def _published_ms(item: Any) -> int:
    when = getattr(item, "published", None)
    return int(when.timestamp() * 1000) if when is not None else 0


def _news_items(
    row: Mapping[str, Any], now_ms: int, pull: Callable[[str], list[Any]]
) -> list[dict[str, Any]]:
    """A topic's articles across the outlets in its language, or one outlet's: the
    newest few of today's, as links with a press each."""
    from .chat import sources
    from .weekly.feeds import link_key

    code = str(row["language"] or "he").split("-")[0].lower()
    if row["kind"] == "outlet":
        one = sources.by_key(str(row["key"]))
        outlets = [one] if one is not None and one.feed else []
    else:
        outlets = [
            one for one in sources.load() if one.feed and one.language.split("-")[0].lower() == code
        ]
    found: list[dict[str, Any]] = []
    for outlet in outlets:
        try:
            items = pull(outlet.feed)
        except Exception:  # noqa: BLE001 - one paper down is not the topic down
            continue
        for item in items:
            if row["kind"] == "topic" and str(row["key"]) not in topics(outlet, item):
                continue
            published = _published_ms(item)
            if published and published < int(row["since"]):
                continue
            found.append(
                {
                    "key": link_key(item.link),
                    "title": item.title,
                    "link": item.link,
                    "published": published or now_ms,
                    "state": "listed",
                    "came": "paused" if row["state"] == "paused" else "",
                }
            )
    found.sort(key=lambda one: one["published"], reverse=True)
    return found


def topics(outlet: Any, item: Any) -> tuple[str, ...]:
    """What one feed item is about: its outlet's section, and its own categories — or,
    where the feed gives it none, the section its address names. `search_sources`' rule
    (2026-10-07), so a topic subscribed to and a topic searched for find the same items."""
    from .chat import sources

    found = set(getattr(outlet, "topics", ()) or ())
    categories = getattr(item, "categories", ()) or ()
    if categories:
        found.update(sources.topics_of(categories))
    else:
        found.update(sources.topics_of_link(str(getattr(item, "link", "") or "")))
    return tuple(one for one in sources.TOPICS if one in found)


def _channel_items(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    from .video import channels

    found = channels.find(f"https://www.youtube.com/channel/{row['key']}")
    out = []
    for upload in channels.newest(found):
        came = _came(row, upload.published)
        out.append(
            {
                "key": upload.id,
                "title": upload.title,
                "link": upload.link,
                "published": upload.published,
                "seconds": upload.seconds,
                # New, and subscribed: it gets ready by itself, inside the cap.
                "state": "due" if came == "" else "listed",
                "came": came,
            }
        )
    return out


def _podcast_items(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    from .audio import episode

    _, items = episode.episodes(str(row["source"] or row["key"]))
    out = []
    for item in items:
        one = podcast_item(item)
        came = _came(row, int(one["published"]))
        out.append({**one, "state": "due" if came == "" else "listed", "came": came})
    return out


def _kept_today(store: Store, sub_id: int, now_ms: int) -> int:
    since = now_ms - 24 * 3600 * 1000
    row = store.db.execute(
        "SELECT COUNT(*) AS n FROM sub_item WHERE subscription = ? AND found >= ? AND came = ''",
        (sub_id, since),
    ).fetchone()
    return int(row["n"])


def poll(
    store: Store,
    *,
    now_ms: int = 0,
    public: bool = False,
    pull: Callable[[str], list[Any]] | None = None,
    only: Iterable[str] = (),
) -> Looked:
    """Look at every live subscription once and write what is new. Never builds."""
    import time

    from .weekly import feeds

    stamp = now_ms or int(time.time() * 1000)
    reading = pull or (lambda url: feeds.pull(url, limit=60))
    kinds = set(only)
    report = Looked()
    # One pull of each paper a run, however many topics read it.
    held: dict[str, list[Any]] = {}

    def once(url: str) -> list[Any]:
        if url not in held:
            held[url] = reading(url)
        return held[url]

    for row in store.live_subscriptions():
        if kinds and row["kind"] not in kinds:
            continue
        sub_id = int(row["id"])
        try:
            if row["kind"] == "series":
                items = _series_items(row, public)
            elif row["kind"] in ("topic", "outlet"):
                room = max(0, NEWS_A_DAY - _kept_today(store, sub_id, stamp))
                known = {item["key"] for item in store.sub_items(sub_id, limit=200)}
                items = [one for one in _news_items(row, stamp, once) if one["key"] not in known]
                items = items[:room]
            elif row["kind"] == "channel":
                items = _channel_items(row)
            else:
                items = _podcast_items(row)
        except Exception as error:  # noqa: BLE001 - one source down is not the run down
            report.failed.append((sub_id, str(error)))
            continue
        report.found += store.add_sub_items(sub_id, items)
        store.polled(sub_id)
        report.looked += 1
    return report


# -- getting what is new ready: the box's own loop (design.md §12, 2026-10-09) ------------
#
# A channel's or a podcast's new item that the poll marked `due` is got ready here, in the
# server, where the build queue is: made the way a pasted link is (`Library.prepare`),
# held to the subscription's month (`month_credits` against `cap`), and claimed through
# `Library.press` — the plan's credits and the box's ceiling — exactly as any build is.
# What does not fit waits, and is tried again each round: a new month, a raised cap or a
# box with room again lets it go by itself. The job's id is written on the item before
# anything is claimed, so a round that dies between the two is picked up, not repeated.

#: How many items one round prepares at most: each asks yt-dlp or a feed, through the
#: proxy, before anything is claimed.
ROUND = 5


@dataclass
class Readied:
    started: list[str] = field(default_factory=list)
    waiting: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    settled: int = 0

    def __str__(self) -> str:
        return (
            f"{len(self.started)} started, {len(self.waiting)} waiting, "
            f"{len(self.failed)} failed, {self.settled} settled"
        )


def _settle(store: Store) -> int:
    """Items whose build has ended: ready to open, or failed. Read off the job rows."""
    done = 0
    for item in store.sub_items_in(("building",)):
        job = store.job(str(item["job"])) if item["job"] else None
        if job is None:
            continue
        stage = str(job["stage"])
        if stage == "done" and job["reader"]:
            store.set_sub_item(
                int(item["subscription"]),
                str(item["key"]),
                state="ready",
                reader=f"/reader/{job['reader']}/reader/index.html",
            )
            done += 1
        elif stage in ("failed", "blocked"):
            store.set_sub_item(
                int(item["subscription"]),
                str(item["key"]),
                state="failed",
                why=str(job["error"] or job["blocked"] or "")[:200],
            )
            done += 1
    return done


def _into(store: Store, person_id: int) -> str:
    """The language a subscription's build is translated into: the reader's own, as a
    quote's is (`chat.tools._wanted_language`)."""
    from .translate.prompts import INTO

    offered = {code for code, _ in INTO}
    reads = store.reads(person_id) & offered or offered
    return "en" if "en" in reads else sorted(reads)[0]


def get_ready(library: Any, store: Store, *, most: int = ROUND) -> Readied:
    """One round: settle what finished, then get the due items ready, inside the cap."""
    from . import plans
    from .serve import Job

    report = Readied(settled=_settle(store))
    month_from = int(library._month_from())
    prepared = 0
    for item in store.sub_items_in(("due", "waiting")):
        if item["sub_state"] != "on":
            continue
        sub_id, key = int(item["subscription"]), str(item["key"])
        person = store.person_by_id(int(item["person"]))
        if person is None:
            continue
        if not plans.builds_by_itself(person):
            store.set_sub_item(sub_id, key, state="waiting", why="plan")
            report.waiting.append((key, "plan"))
            continue
        cap = int(item["cap"] or DEFAULT_CAP)
        used = store.month_credits(person.id, sub_id, month_from)
        # Known from an earlier round: no need to ask the source again to know it waits.
        if item["credits"] and used + int(item["credits"]) > cap:
            if item["state"] != "waiting" or item["why"] != "cap":
                store.set_sub_item(sub_id, key, state="waiting", why="cap")
            report.waiting.append((key, "cap"))
            continue
        job = library.jobs.get(str(item["job"])) if item["job"] else None
        if job is not None and job.stage in library.PRESSED:
            store.set_sub_item(sub_id, key, state="building")
            continue
        if job is None or job.stage != "ready":
            if prepared >= most:
                continue
            prepared += 1
            job = Job(
                id=secrets.token_hex(8),
                source=str(item["link"]),
                title=str(item["title"]),
                options={
                    "words": True,
                    "to": _into(store, person.id),
                    "source": str(item["link"]),
                    "via": "subscription",
                    "subscription": sub_id,
                    "item": key,
                },
                owner=person.id,
                admin=bool(person.admin),
                home=library.home(person),
                kind="subscription",
                ui=str(item["said"] or "en"),
            )
            library.jobs[job.id] = job
            library.remember(job)
            # Written before anything is claimed: the checkpoint.
            store.set_sub_item(sub_id, key, job=job.id)
            library.prepare(job)
            if not job.title or job.title == job.source:
                job.title = str(item["title"]) or job.title
            # An episode's own address says nothing of its length, and is priced at the
            # hour `_prepare_episode` guesses; the feed said how long it is, so the cap
            # and the plan are held to that (found in the first real run, 2026-10-09).
            if (
                job.stage == "ready"
                and job.options.get("episode")
                and float(item["seconds"] or 0) > 0
            ):
                job.seconds = float(item["seconds"])
                job.parts = max(1, round(job.seconds / 720))
                library._price_recording(job, transcribed=job.transcription > 0)
            library.remember(job)
        if job.stage == "blocked" and job.blocked and not job.error:
            # Priced over what the box has left today: a wait, not a failure.
            job.stage, job.blocked = "ready", ""
            library.remember(job)
            store.set_sub_item(sub_id, key, state="waiting", why="box")
            report.waiting.append((key, "box"))
            continue
        if job.stage != "ready":
            why = job.error or job.blocked or "not ready"
            store.set_sub_item(sub_id, key, state="failed", why=str(why)[:200])
            report.failed.append((key, str(why)))
            continue
        credits = credits_of(job.seconds) if job.audio else 0
        store.set_sub_item(sub_id, key, credits=credits)
        if used + credits > cap:
            store.set_sub_item(sub_id, key, state="waiting", why="cap")
            report.waiting.append((key, "cap"))
            continue
        refused = library.press(job)
        if refused:
            allowed = library.upload_seconds
            spent = store.hours_used(person.id, month_from)
            why = (
                "credits"
                if allowed is not None and not person.admin and spent + job.seconds > allowed
                else "box"
            )
            # Pressed and refused is a quote again: tried next round, as a new month or a
            # box with room again lets it.
            job.stage, job.blocked = "ready", ""
            library.remember(job)
            store.set_sub_item(sub_id, key, state="waiting", why=why)
            report.waiting.append((key, why))
            continue
        store.set_sub_item(sub_id, key, state="building", why="")
        report.started.append(key)
    return report


# -- the one mail a day (design.md §12, "Everything new comes in one mail a day") --------
#
# Run once a day by targum-subscriptions-mail.timer (`targum subscriptions mail`). Every
# reader with something new gets one mail with all of it, grouped by subscription — the
# daily cycles included, the weekly left to its Monday mail. An item is stamped as mailed
# once the mail that carries it went, so a run started twice sends nothing twice.

#: How far back an unmailed item is still news: a day and a half, so a run that missed a
#: day still carries yesterday's, and the first run after this ships does not mail the
#: whole of what the poll had found before.
MAIL_WINDOW_MS = 36 * 3600 * 1000

#: How many items one subscription shows in a mail; more is "and N more" on its page.
MAIL_A_SUBSCRIPTION = 5

#: Between batches of mail, as the weekly's mailout paces itself.
MAIL_BATCH = 25
MAIL_PAUSE = 2.0


@dataclass
class Mailed:
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


def _note(item: Mapping[str, Any], language: str, back: str) -> str:
    from .strings import text

    if item["state"] == "waiting":
        return text("mail.daily.waiting", language, date=back)
    if item["state"] == "listed":
        return text("mail.daily.link", language)
    if item["kind"] == "channel":
        return text("mail.daily.ready-watch", language)
    if item["kind"] == "podcast":
        return text("mail.daily.ready-listen", language)
    return text("mail.daily.ready-read", language)


def _named_for_mail(item: Mapping[str, Any], language: str, series_names: Mapping[str, str]) -> str:
    from .strings import catalogue

    if item["kind"] == "series":
        return series_names.get(str(item["sub_key"]), str(item["sub_key"]))
    if item["kind"] == "topic":
        key = f"subs.topic.{item['sub_key']}"
        return catalogue(language).get(key) or catalogue("en").get(key) or str(item["sub_key"])
    return str(item["sub_name"] or item["sub_key"])


def daily(
    store: Store,
    mailer: Any,
    address: str,
    *,
    now_ms: int = 0,
    month_from: int = 0,
    back: Callable[[str], str] | None = None,
    pause: float = MAIL_PAUSE,
    batch: int = MAIL_BATCH,
) -> Mailed:
    """Send each reader one mail with everything new from their subscriptions."""
    import contextlib
    import time
    from itertools import groupby

    from . import series
    from .letters import subscriptions_daily
    from .mail import SmtpMailer

    stamp = now_ms or int(time.time() * 1000)
    report = Mailed()
    rows = store.items_to_mail(stamp - MAIL_WINDOW_MS)
    if not rows:
        return report
    by_person = [list(group) for _, group in groupby(rows, key=lambda row: int(row["person"]))]
    names: dict[str, dict[str, str]] = {}
    holding = mailer.session() if isinstance(mailer, SmtpMailer) else contextlib.nullcontext()
    try:
        with holding:
            for index, items in enumerate(by_person):
                said = next((str(item["said"]) for item in items if item["said"]), "en")
                if said not in names:
                    names[said] = {
                        str(row["id"]): str(row["name"])
                        for row in series.current(public=True, language=said)
                    }
                when = back(said) if back is not None else ""
                groups: list[dict[str, Any]] = []
                mailed: list[tuple[int, str]] = []
                for sub_id, in_sub in groupby(items, key=lambda row: int(row["sub"])):
                    listed = list(in_sub)
                    waiting = [item for item in listed if item["state"] == "waiting"]
                    shown = [item for item in listed if item["state"] != "waiting"]
                    # Told once a month that something waits; what waits with it is not.
                    if waiting and not store.waiting_mailed(sub_id, month_from):
                        shown.append(waiting[0])
                    mailed += [(sub_id, str(item["key"])) for item in listed]
                    if not shown:
                        continue
                    first = listed[0]
                    rows_shown = [
                        (
                            str(item["title"]),
                            str(item["language"] or "he"),
                            _note(item, said, when),
                            f"/subscriptions/{sub_id}#sub-cap"
                            if item["state"] == "waiting"
                            else door(item),
                        )
                        for item in shown[:MAIL_A_SUBSCRIPTION]
                    ]
                    groups.append(
                        {
                            "name": _named_for_mail(first, said, names[said]),
                            "stop": str(first["stop"]),
                            "rows": rows_shown,
                        }
                    )
                email = str(items[0]["email"])
                if not groups:
                    store.mark_mailed(mailed)
                    continue
                stops = "&".join(f"t={group['stop']}" for group in groups)
                letter = subscriptions_daily(groups, address, stops, said)
                try:
                    mailer.notify(email, letter.subject, letter.text, letter.headers, letter.html)
                except Exception as error:  # noqa: BLE001 - one bad address, not the run
                    report.failed.append((email, str(error)))
                    continue
                store.mark_mailed(mailed)
                report.sent.append(email)
                if pause and batch and (index + 1) % batch == 0 and index + 1 < len(by_person):
                    time.sleep(pause)
    except Exception as error:  # noqa: BLE001 - the session itself, not one address
        report.stopped = str(error)
    return report
