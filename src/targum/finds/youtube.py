"""The nightly round over YouTube (targum-internal#620; plan §1.2; David, 2026-10-31).

Videos in Hebrew with a Hebrew subtitle track **somebody wrote**, found through YouTube's
Data API and scored on that track, so Home's card and "More that fit you" can offer
them as `video` finds. Any licence: a find is personal reading, built as the reader's
own import when they press Watch (`serve.Handler._open_find`, a pasted link's press),
and never shelved.

One round, on a timer on the box (`targum finds youtube`, `targum-finds-youtube.timer`):

1. **Search** (`search.list`, 100 units a query), one query per chip (`chips.CHIPS`,
   its fixed Hebrew phrase) and a few for easy Hebrew (`EASY`), each with
   `videoCaption=closedCaption`, `relevanceLanguage=he`, `regionCode=IL`,
   `safeSearch=strict` and the last thirty days. Forty-odd queries do not fit a night's
   units (`UNITS_DEFAULT`), so the night starts where the last one stopped and the
   whole list is asked every two nights or so.
2. **The gate** (`videos.list`, 1 unit for fifty), free of the proxy: an age-restricted
   video, one not public, not embeddable, live, blocked in Israel, under a minute or
   over thirty, said to be in another language or titled in another script is dropped;
   so is one YouTube says has no track anybody wrote (`contentDetails.caption`), and
   one whose title or description the screen refuses (`screen.passes`).
3. **The track**, through the residential proxy, for at most `NIGHT_MOST` videos a day
   (`video.youtube.subtitles_for_finding`: `--skip-download`, manual tracks only). An
   `age_limit` of 18 or more drops the video; no Hebrew track anybody wrote drops it.
   The track's words are screened again, scored (`score.Forms.score`) and let go: the
   folder is deleted, and the pool keeps the counts (`pool.add`), never the words.

**What it costs targum.** The Data API is free inside its daily quota. The proxy is
DataImpulse's $1 a gigabyte, and one track's run is counted at `RUN_BYTES` (the plan's
estimate for the player's answer) plus the track's own size, written on the run as it
goes (`pool.spend`) and held to `TARGUM_FINDS_BUDGET_USD` with the other sources: a
round stops fetching when the month's budget would not cover the next track.

**Off unless the box says so** (`TARGUM_FINDS_YOUTUBE`): the timer runs every night and
does nothing until then.

**Counted into the language tables as counts** (David, 2026-11-01): the nightly sweep
folds each kept find's lemma counts into the `video` register (`tables.finds`), never
its words, which were never kept.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import chips, news, pool, screen
from . import score as score_module

if TYPE_CHECKING:
    from ..accounts import Store

log = logging.getLogger(__name__)

FLAG = "TARGUM_FINDS_YOUTUBE"

SOURCE = "youtube"

#: The host every find here is on, as the pool and the screen read it.
HOST = "www.youtube.com"

#: The Data API units a night may spend (plan §4: 3,000 a day of the project's 10,000,
#: which the box's lookups and subscriptions share), unless the environment says.
UNITS_ENV = "TARGUM_FINDS_YOUTUBE_UNITS"
UNITS_DEFAULT = 3000

#: The most subtitle tracks fetched through the proxy in a day (David, 2026-10-31).
NIGHT_MOST = 120

#: A video under a minute has too little to read; over thirty is past a sitting.
MIN_SECONDS = 60
MAX_SECONDS = 30 * 60

#: How far back a search looks, in days: fresh, and inside the API's thirty-day rule.
FRESH_DAYS = 30

#: What one subtitle run is counted as through the proxy, before the track itself: the
#: plan's estimate for the watch page and player answer yt-dlp reads (§1.2). To measure
#: on the box against the provider's dashboard and set again.
RUN_BYTES = 1_500_000

#: Easy Hebrew, searched beside the chips: for the bottom of the ladder, where a chip's
#: phrase alone finds mostly native-speed talk.
EASY: dict[str, tuple[str, ...]] = {
    "he": ("עברית קלה", "עברית למתחילים", "סיפור לילדים", "הסבר פשוט"),
}

#: The languages a round runs for: those the scorer has a map for and the chips a phrase.
LANGUAGES = ("he",)


def on() -> bool:
    return os.environ.get(FLAG, "").strip().lower() in {"1", "true", "yes"}


def units() -> int:
    raw = os.environ.get(UNITS_ENV, "").strip()
    try:
        return max(0, int(raw)) if raw else UNITS_DEFAULT
    except ValueError:
        return UNITS_DEFAULT


# -- the queries --------------------------------------------------------------------


@dataclass(frozen=True)
class Query:
    words: str
    #: What a video it finds carries in its `topics`: the chip's tag, or nothing.
    tags: tuple[str, ...] = ()


def queries(language: str) -> list[Query]:
    """Every query a round may ask, in order: one per chip, then the easy ones."""
    out = [
        Query(chip.phrases[language], (chips.tag(chip.code),))
        for chip in chips.CHIPS
        if chip.phrases.get(language)
    ]
    out += [Query(words) for words in EASY.get(language, ())]
    return out


def rotated(asked: Sequence[Query], start: int) -> list[Query]:
    """The queries starting at `start`, round to the beginning."""
    if not asked:
        return []
    at = start % len(asked)
    return [*asked[at:], *asked[:at]]


# -- the gate -----------------------------------------------------------------------


def gate(item: Mapping[str, Any], language: str) -> str:
    """Why a video is dropped before anything crosses the proxy, or "". `age` for an
    age-restricted one, `host` or `words` for what the screen refuses, `subs` for one
    YouTube says has no track anybody wrote, `gate` for the rest."""
    from ..video.discover import SCRIPTS, seconds, speaks, titled_in

    status = item.get("status") or {}
    details = item.get("contentDetails") or {}
    snippet = item.get("snippet") or {}
    if (details.get("contentRating") or {}).get("ytRating") == "ytAgeRestricted":
        return "age"
    if status.get("privacyStatus") != "public":
        return "gate"
    if status.get("uploadStatus", "processed") != "processed":
        return "gate"
    if not status.get("embeddable", False):
        return "gate"
    if snippet.get("liveBroadcastContent", "none") != "none":
        return "gate"
    region = details.get("regionRestriction") or {}
    if "IL" in (region.get("blocked") or ()) or (
        "allowed" in region and "IL" not in (region.get("allowed") or ())
    ):
        return "gate"
    length = seconds(str(details.get("duration") or ""))
    if not MIN_SECONDS <= length <= MAX_SECONDS:
        return "gate"
    title = str(snippet.get("title") or "")
    if not speaks(language, snippet) or not titled_in(language, title):
        return "gate"
    # A title with none of the language's letters: measured on 2026-11-01, a Hebrew
    # search with closed captions answers mostly English channels (Fox Sports, the NFL),
    # and not one of them had a Hebrew letter in its title.
    letters = SCRIPTS.get(language)
    if letters and not re.search(f"[{letters}]", title):
        return "gate"
    why = screen.passes(HOST, title, str(snippet.get("description") or ""))
    if why:
        return why
    if str(details.get("caption", "")).lower() != "true":
        return "subs"
    return ""


@dataclass
class Video:
    """A video through the gate, waiting for its track."""

    id: str
    title: str
    channel: str
    seconds: int
    published: int
    tags: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        from ..video.youtube import WATCH
        from ..weekly.feeds import link_key

        return link_key(f"{WATCH}{self.id}")


def _published(said: str) -> int:
    try:
        return int(datetime.fromisoformat(said.replace("Z", "+00:00")).timestamp() * 1000)
    except ValueError:
        return 0


def _video(item: Mapping[str, Any], tags: Sequence[str]) -> Video:
    from ..video.discover import seconds

    snippet = item.get("snippet") or {}
    return Video(
        id=str(item.get("id") or ""),
        title=str(snippet.get("title") or ""),
        channel=str(snippet.get("channelTitle") or ""),
        seconds=seconds(str((item.get("contentDetails") or {}).get("duration") or "")),
        published=_published(str(snippet.get("publishedAt") or "")),
        tags=list(tags),
    )


# -- the track ----------------------------------------------------------------------


@dataclass(frozen=True)
class Track:
    """What one subtitle run brought back: the words, or why there are none."""

    text: str = ""
    #: yt-dlp's `age_limit` for the video, 0 where it said none.
    age_limit: int = 0
    #: The track's own size, which crossed the proxy on top of `RUN_BYTES`.
    size: int = 0


#: One subtitle run: a watch address in, the track out. Raises where yt-dlp failed.
Fetch = Callable[[str], Track]


def track(url: str) -> Track:
    """One video's Hebrew track somebody wrote, read in a folder that is then deleted."""
    from ..ingest.subtitles import load_cues
    from ..video.youtube import subtitles_for_finding

    with tempfile.TemporaryDirectory(prefix="targum-find-") as folder:
        found, info = subtitles_for_finding(url, Path(folder))
        age = int(info.get("age_limit") or 0)
        if found is None:
            return Track(age_limit=age)
        size = found.stat().st_size
        text = "\n".join(cue.text for cue in load_cues(found) if cue.text.strip())
        return Track(text=text, age_limit=age, size=size)


def run_cost(size: int) -> float:
    """What one subtitle run costs targum in dollars: nothing without the proxy."""
    from ..video.youtube import proxy

    if not proxy():
        return 0.0
    return (RUN_BYTES + size) / 1e9 * news.PROXY_USD_PER_GB


# -- one round ----------------------------------------------------------------------


@dataclass
class Round(news.Round):
    """What one night did, with the Data API units it spent."""

    units: int = 0
    asked: int = 0

    def __str__(self) -> str:
        return f"{super().__str__()}, {self.asked} searches, {self.units} units"


def fetched_today(store: Store, when: int) -> int:
    """Subtitle runs the rounds started today (UTC) have made: off their own rows."""
    total = 0
    for (note,) in store.db.execute(
        "SELECT note FROM find_run WHERE source = ? AND started >= ?",
        (SOURCE, (when // pool.DAY_MS) * pool.DAY_MS),
    ):
        try:
            said = json.loads(note or "{}")
        except ValueError:
            continue
        if isinstance(said, dict):
            total += int(said.get("fetched") or 0)
    return total


def _start(store: Store) -> int:
    """Where tonight's queries start: where the last round stopped."""
    row = store.db.execute(
        "SELECT note FROM find_run WHERE source = ? AND finished > 0 ORDER BY id DESC LIMIT 1",
        (SOURCE,),
    ).fetchone()
    try:
        said = json.loads(row[0] or "{}") if row else {}
    except ValueError:
        said = {}
    return int(said.get("next") or 0) if isinstance(said, dict) else 0


def refresh(
    store: Store,
    *,
    language: str = "he",
    get: Callable[[str, Mapping[str, str]], dict[str, Any]] | None = None,
    api_key: str | None = None,
    fetch: Fetch = track,
    forms_for: Callable[[str], score_module.Forms | None] = score_module.load,
    budget_units: int | None = None,
    at: int | None = None,
) -> Round:
    """One night: search, gate, fetch the tracks and pool what passes. Each video is
    written as it is done, and each run's cost as it is spent, so a killed round has
    kept what it found and said what it cost."""
    from ..video import discover

    when = pool.now_ms() if at is None else at
    pool.expire(store, when)
    found = Round()
    code = score_module.code(language)
    forms = forms_for(code) if code in score_module.POOLED else None
    if forms is None:
        found.stopped = "no map for the language"
        return found
    key = api_key if api_key is not None else discover.key()
    ask = get or discover.fetch
    allowed = units() if budget_units is None else budget_units
    run = pool.start_run(store, SOURCE, when)
    asked = queries(code)
    start = _start(store)
    order = rotated(asked, start)
    after = datetime.fromtimestamp((when - FRESH_DAYS * pool.DAY_MS) / 1000, tz=UTC)

    def dropped(url: str, why: str) -> None:
        found.dropped[why] += 1
        pool.drop(store, language=code, source=SOURCE, url=url, reason=why, host=HOST, at=when)

    # -- search and gate: per query, the videos in the order YouTube ranked them --
    by_query: list[list[Video]] = []
    held: dict[str, Video] = {}
    done = 0
    try:
        for query in order:
            if found.units + discover.SEARCH_UNITS + discover.VIDEOS_UNITS > allowed:
                found.stopped = f"the night's {allowed} units"
                break
            found.units += discover.SEARCH_UNITS
            answer = ask(
                discover.SEARCH,
                {
                    "key": key,
                    "part": "id",
                    "type": "video",
                    "q": query.words,
                    "videoCaption": "closedCaption",
                    "relevanceLanguage": code,
                    "regionCode": "IL",
                    "safeSearch": "strict",
                    "videoEmbeddable": "true",
                    "publishedAfter": after.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "maxResults": str(discover.PAGE),
                },
            )
            done += 1
            found.asked += 1
            ids: list[str] = []
            for item in answer.get("items") or ():
                vid = str((item.get("id") or {}).get("videoId") or "")
                if not vid or vid in ids:
                    continue
                if vid in held:
                    held[vid].tags.extend(t for t in query.tags if t not in held[vid].tags)
                    continue
                ids.append(vid)
            fresh = [vid for vid in ids if not pool.known(store, Video(vid, "", "", 0, 0).url)]
            mine: list[Video] = []
            for at_id in range(0, len(fresh), discover.PAGE):
                if at_id and found.units + discover.VIDEOS_UNITS > allowed:
                    break
                found.units += discover.VIDEOS_UNITS
                listed = ask(
                    discover.VIDEOS,
                    {
                        "key": key,
                        "part": "status,contentDetails,snippet",
                        "id": ",".join(fresh[at_id : at_id + discover.PAGE]),
                    },
                )
                for item in listed.get("items") or ():
                    found.seen += 1
                    video = _video(item, query.tags)
                    why = gate(item, code)
                    if why:
                        dropped(video.url, why)
                        continue
                    held[video.id] = video
                    mine.append(video)
            by_query.append(mine)
    except Exception as error:  # noqa: BLE001 - what was found is still fetched
        log.warning("finds: a YouTube search failed: %s", error)
        found.stopped = found.stopped or "the Data API did not answer"

    # -- the tracks: one from each query in turn, so every chip has its share --
    queue: list[Video] = []
    while any(by_query):
        for mine in by_query:
            if mine:
                queue.append(mine.pop(0))
    room = max(0, NIGHT_MOST - fetched_today(store, when))
    if len(queue) > room:
        # Before the units: a night that ran out of searches had more than it could fetch.
        found.stopped = f"the day's {NIGHT_MOST} tracks"
    note: dict[str, Any] = {"next": (start + done) % max(1, len(asked)), "units": found.units}

    def checkpoint() -> None:
        note["fetched"] = found.fetched
        pool.finish_run(
            store,
            run,
            seen=found.seen,
            kept=found.kept,
            dropped=found.dropped,
            note={**note, **({"stopped": found.stopped} if found.stopped else {})},
            at=when,
        )

    for video in queue[:room]:
        if pool.left(store, when) < run_cost(0):
            found.stopped = "the month's discovery budget"
            break
        try:
            got = fetch(video.url)
        except Exception as error:  # noqa: BLE001 - one video never stops a round
            log.info("finds: no track for %s: %s", video.id, error)
            found.fetched += 1
            cost = run_cost(0)
            found.spent += cost
            pool.spend(store, run, cost)
            dropped(video.url, "unreadable")
            checkpoint()
            continue
        found.fetched += 1
        cost = run_cost(got.size)
        found.spent += cost
        pool.spend(store, run, cost)
        _keep(store, video, got, forms, code, found, dropped, when)
        checkpoint()
    checkpoint()
    return found


def _keep(
    store: Store,
    video: Video,
    got: Track,
    forms: score_module.Forms,
    language: str,
    found: Round,
    dropped: Callable[[str, str], None],
    when: int,
) -> None:
    from ..chat.tools import credits_for

    if got.age_limit >= 18:
        dropped(video.url, "age")
        return
    if not got.text.strip():
        dropped(video.url, "subs")
        return
    if screen.term_in(f"{video.title}\n{got.text}"):
        dropped(video.url, "words")
        return
    scored = forms.score(f"{video.title}\n{got.text}")
    if scored.tokens < news.LEAST_WORDS:
        dropped(video.url, "short")
        return
    fingerprint = news.digest(got.text)
    if pool.known_digest(store, fingerprint):
        dropped(video.url, "same")
        return
    added = pool.add(
        store,
        language=language,
        source=SOURCE,
        url=video.url,
        bag=scored.bag,
        tokens=scored.tokens,
        unresolved=scored.unresolved,
        rung=forms.rung_of(scored),
        digest=fingerprint,
        title=video.title,
        host=HOST,
        publisher=video.channel,
        published=video.published,
        medium="video",
        seconds=float(video.seconds),
        # What Watch will quote: a credit a minute of the video (`Handler._open_find`
        # builds nothing where the quote is higher than the card).
        credits=credits_for(video.seconds),
        topics=video.tags,
        at=when,
    )
    if added:
        found.kept += 1
