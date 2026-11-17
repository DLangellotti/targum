"""What grows a language's shelf by itself, on the box, with no laptop in the loop.

design.md §12, "The shelf grows by itself, inside a month's credits" (draft, ops,
2026-11-17). The standard asks two things of a Beta language that a person doing the work
by hand cannot be (`stages.GROWING`, `stages.BUILDS_UNATTENDED`): a feed that grows the
shelf by itself, and the box building a new text with no laptop in the loop. Hebrew has
the weekly, the portion and the daily. Until this, every French video on the shelf was
found by hand and built on the box by somebody running `systemd-run` as targum.

**The sources are the catalogue's own.** A collection in the private catalogue that names
a YouTube channel (`Collection.channel`, the address its Subscribe already reads) and
says `"grows": true` is a source, in the language of its members. Nothing about which
channels lives in this repository, for the reason the catalogue does not.

**A round, once a day** (`targum grow`, `targum-grow.timer`, as targum):

1. The channel's newest uploads through the Data API (`video.channels.newest`, free inside
   the quota), and each asked again through `videos.list`, whose `status.license` is the
   video's own field (`video.discover.check`): Creative Commons, public, embeddable,
   finished, a credit to name, not music, not said to be in another language. And one
   YouTube says has a track somebody wrote (`contentDetails.caption`), and no longer than
   ten minutes (`MAX_SECONDS`), so the build is one part, the whole video.
2. The track, in the language, through the proxy (`youtube.fetch_subtitles`). None, and
   the video is passed over: nothing is ever transcribed here, so a hearing is never
   bought.
3. A job of kind `grow`, quoted by `Library.prepare` and pressed through `Library.press`,
   and so through `Library.claim` like every build: targum's to pay (`gift`), held to the
   box's daily ceiling. Before the press, the month's credits so far — read off the `grow`
   job rows, so there is no second counter — and the quote must fit `TARGUM_GROW_CREDITS`.
   It is built by the same worker a reader's build is.
4. The finished build is curated into the video shelf (`video.curate`) with its credit and
   the licence the field grants, measured on the shelf's ruler, and entered in
   `grown.json` beside the videos, which `catalogue.everything` joins on the way the
   weekly's issues are: a new row appears without a deploy. The build folder is then
   deleted; the curated copy is the one the shelf reads.

**Beside the server, never in its place** (qa on #1288). The round is its own process
on the server's database, so its Library is a side one (`Library(side=True)`): the same
press, claim and worker, and none of a server's start-up. A server's recovery fails every
working or queued row (`Store.interrupt_running`), which run from here would fail the
readers' builds the live server has in hand; the sweeps are the server's to run. A
server restarted mid-round fails the round's row the same way, with its claim kept; the
round's own worker goes on and writes it done, settled to what it spent. A round whose
process died leaves its row working, and the next round, under the round's lock so that
no live round's rows are among them, fails it with the claim kept (`_settle_stale`).

**Held to the cap however a build ends.** The month counts every `grow` row that is
building, built, or failed with its claim kept; a round counts presses, not videos that
came through. One round at a time (`ROUND_LOCK`), and the index is re-read and changed
under its own lock at every write, so a `drop` made during a round stays made.

**Off until the box says so.** `TARGUM_GROW` names the languages a round runs for and
`TARGUM_GROW_CREDITS` the month's cap; with either unset the round says what is off and
spends nothing. A video passed over is written down with why, and never asked about again.

**Nobody reads a grown video before it is on the shelf**, as nobody reads the weekly
before it goes out. What stands in for the read is the source: a channel a person chose
and filed in the catalogue. `targum grow drop <id>` takes one down.
"""

from __future__ import annotations

import logging
import os
import secrets
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .shelf_file import ShelfFile, locked

if TYPE_CHECKING:
    from .accounts import Store
    from .catalogue import Collection, Entry
    from .serve import Library

log = logging.getLogger(__name__)

#: The languages a round runs for, comma-separated ("fr"). Unset is off.
FLAG = "TARGUM_GROW"
#: The month's cap, in credits (a credit is a minute of video), every language together.
#: Unset or 0 is off: nothing is pressed without a cap somebody chose.
CREDITS_ENV = "TARGUM_GROW_CREDITS"

#: The job kind every grown build is, which is also how the month is counted.
KIND = "grow"

#: The most videos one round builds.
ROUND = 3

#: Well inside one part (`audio.parts` cuts near twelve minutes, give or take its
#: window): a grown video is built whole, never left with parts waiting on a press
#: nobody will make.
MAX_SECONDS = 10 * 60

#: Beside the videos, in the store the shelf reads them from.
INDEX = "grown.json"
#: Held for a whole round: two rounds at once would both pass the month's cap.
ROUND_LOCK = ".grow-round.lock"

#: Where the round's builds are made, under the Library's own root: a home nobody owns,
#: as `shared` and `weekly` are.
WORKSPACE = "grown"


@dataclass(frozen=True)
class Source:
    collection: str
    language: str
    channel: str


@dataclass
class Grown:
    built: list[str] = field(default_factory=list)
    passed: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    stopped: str = ""

    def __str__(self) -> str:
        line = f"{len(self.built)} built, {len(self.passed)} passed over, {len(self.failed)} failed"
        return f"{line} — stopped: {self.stopped}" if self.stopped else line


def languages() -> frozenset[str]:
    raw = os.environ.get(FLAG, "")
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


def cap() -> int:
    raw = os.environ.get(CREDITS_ENV, "").strip()
    try:
        return max(0, int(raw)) if raw else 0
    except ValueError:
        return 0


# -- what the shelf reads -------------------------------------------------------------


def index_path() -> Path:
    from .video import store

    return store.root() / INDEX


#: The grown rows, as every file of rows the box writes for itself is kept
#: (`shelf_file.ShelfFile`): read again only when it changed, changed under its lock.
#: Beside the rows, `passed`: what a round looked at and will not build, and why.
GROWN = ShelfFile(index_path)


def _update(change: Callable[[dict[str, Any]], None]) -> None:
    """Read the index afresh, change it and write it, under its lock: a `drop` made while
    a round runs is never written over by the round's older copy."""

    def with_passed(held: dict[str, Any]) -> None:
        if not isinstance(held.get("passed"), dict):
            held["passed"] = {}
        change(held)

    GROWN.update(with_passed)


def _passed() -> dict[str, str]:
    found = GROWN.read().get("passed")
    return dict(found) if isinstance(found, dict) else {}


def _pass_over(identifier: str, why: str) -> None:
    def change(held: dict[str, Any]) -> None:
        held["passed"][identifier] = why[:200]

    _update(change)


def entries() -> list[Entry]:
    """Every grown video, as a catalogue entry. Empty on a machine that grew none."""
    return GROWN.entries()


def members() -> dict[str, list[str]]:
    """Grown entry ids by the collection whose channel brought them."""
    out: dict[str, list[str]] = {}
    for row in GROWN.rows():
        if row.get("collection"):
            out.setdefault(str(row["collection"]), []).append(str(row["id"]))
    return out


# -- where it grows from --------------------------------------------------------------


def sources(collections: list[Collection] | None = None) -> list[Source]:
    """Each catalogue collection that names a channel and says it grows, in the language
    of its members."""
    from . import catalogue

    out: list[Source] = []
    for collection in collections if collections is not None else catalogue.COLLECTIONS:
        if not collection.grows or not collection.channel:
            continue
        language = next(
            (
                found.language
                for member in collection.members
                if (found := catalogue.by_id(member)) is not None
            ),
            "",
        )
        if language:
            out.append(Source(collection.id, language, collection.channel))
    return out


def credits_this_month(store: Store, month_from: int) -> int:
    """What the round has pressed this month, in credits, off its own job rows: what is
    building, what was built, and what failed with its claim kept — a build that died
    part way had very likely spent (`Store.interrupt_running`), so it counts. Only a
    claim handed back whole (`unclaim`, to 0) does not."""
    from .accounts import SECONDS_A_CREDIT

    row = store.db.execute(
        "SELECT COALESCE(SUM(seconds), 0) AS used FROM job WHERE kind = ? AND made >= ?"
        " AND (claimed > 0 OR stage IN ('queued', 'working', 'done'))",
        (KIND, month_from),
    ).fetchone()
    return round(float(row["used"]) / SECONDS_A_CREDIT)


def _settle_stale(store: Store) -> int:
    """A round's own builds an earlier round left at working or queued, because its
    process died: failed, with their claim kept so they still count. Only ever under the
    round's lock, so no live round's builds are among them, and only rows of kind `grow`:
    the server's are its own (`Store.interrupt_running`, at its start)."""
    with store.write() as db:
        cursor = db.execute(
            "UPDATE job SET stage = 'failed', error = 'interrupted'"
            " WHERE kind = ? AND stage IN ('working', 'queued')",
            (KIND,),
        )
        return int(cursor.rowcount or 0)


def _credits(seconds: float) -> int:
    from .subscriptions import credits_of

    return credits_of(seconds)


# -- a round ----------------------------------------------------------------------------

Fetch = Callable[[str, Mapping[str, str]], dict[str, Any]]
Track = Callable[[str, Path, tuple[str, ...]], Path]


def _gate(item: Mapping[str, Any], language: str) -> str:
    """Why this upload is passed over, or "" where it may be built."""
    from .finds import screen
    from .video import discover

    why = discover.check(item, language)
    if why:
        return why
    details = item.get("contentDetails") or {}
    if str(details.get("caption", "false")).lower() != "true":
        return "no track anybody wrote"
    if discover.seconds(str(details.get("duration") or "")) > MAX_SECONDS:
        return "longer than ten minutes"
    snippet = item.get("snippet") or {}
    if screen.term_in(f"{snippet.get('title', '')}\n{snippet.get('description', '')}"):
        return "screened"
    return ""


def _no_track(error: BaseException) -> bool:
    """Whether a track fetch failed because the video has none anybody wrote, rather than
    because the way out did (`youtube.fetch_subtitles`'s own refusal)."""
    from .errors import TargumError

    said = str(error.args[0]) if error.args else ""
    return isinstance(error, TargumError) and said.startswith("That video has no subtitle track")


def _uploads(source: Source, get: Fetch, api_key: str) -> list[dict[str, Any]]:
    """The channel's newest uploads, newest first, as `videos.list` answers for each."""
    from .video import channels, discover

    channel = channels.find(source.channel, get=get, api_key=api_key)
    ids = [upload.id for upload in channels.newest(channel, get=get, api_key=api_key)]
    if not ids:
        return []
    answer = get(
        discover.VIDEOS,
        {"key": api_key, "part": "status,contentDetails,snippet", "id": ",".join(ids[:50])},
    )
    found = {str(item.get("id") or ""): item for item in answer.get("items") or []}
    return [found[one] for one in ids if one in found]


def _known(identifier: str) -> bool:
    from . import catalogue
    from .video import store

    if identifier in _passed() or store.folder(identifier).exists():
        return True
    return catalogue.matching(f"video:{identifier}") is not None


def _entry_for(
    folder: Path, curated: Path, source: Source, item: Mapping[str, Any], today: date
) -> dict[str, Any]:
    from . import promote
    from .models import Document, read_artifact
    from .video import discover

    document = read_artifact(Document, curated / "document.json")
    snippet = item.get("snippet") or {}
    credit = str(snippet.get("channelTitle") or "").strip()
    identifier = curated.name
    words = sum(len(block.text.split()) for block in document.blocks) if document else 0
    return {
        "id": f"video-{source.language}-{identifier}",
        "title": (document.title if document else "") or str(snippet.get("title") or ""),
        "author": credit,
        "language": source.language,
        "source": f"video:{identifier}",
        "blurb": "",
        "english": "",
        "words": words,
        "tags": [],
        "translations": [],
        "kind": "talk",
        "register": "modern",
        "difficulty": promote._difficulty(folder, source.language),
        "sentence": promote._sentence(folder),
        "model": "",
        "licence": discover.LICENCE,
        "credit": credit,
        "licence_url": discover.LICENCE_URL,
        "licence_from": "youtube",
        "added": today.isoformat(),
        "collection": source.collection,
    }


def grow(
    library: Library,
    store: Store,
    *,
    get: Fetch | None = None,
    track: Track | None = None,
    api_key: str = "",
    most: int = ROUND,
    today: date | None = None,
) -> Grown:
    """One round, under the round's lock: for each source in a language switched on,
    build what is new and passes, inside the month's credits, through `Library.press`.
    At most `most` presses, built or not. Never raises for one video: it is written down
    and the round goes on."""
    report = Grown()
    if not languages():
        report.stopped = f"off ({FLAG} names no language)"
        return report
    if cap() <= 0:
        report.stopped = f"off ({CREDITS_ENV} sets no cap)"
        return report
    with locked(index_path().with_name(ROUND_LOCK), wait=False) as taken:
        if not taken:
            report.stopped = "another round is running"
            return report
        _settle_stale(store)
        _round(
            library, store, report, get=get, track=track, api_key=api_key, most=most, today=today
        )
    return report


def _round(
    library: Library,
    store: Store,
    report: Grown,
    *,
    get: Fetch | None,
    track: Track | None,
    api_key: str,
    most: int,
    today: date | None,
) -> None:
    from .serve import Job
    from .video import curate, discover, youtube

    on = languages()
    limit = cap()
    ask = get or discover.fetch
    fetch_track = track or youtube.fetch_subtitles
    held_key = api_key or discover.key()
    work = library.out / WORKSPACE
    month_from = int(library._month_from())
    started = False
    pressed = 0
    for source in sources():
        if source.language not in on or pressed >= most or report.stopped:
            continue
        try:
            uploads = _uploads(source, ask, held_key)
        except Exception as error:  # noqa: BLE001 - one channel down is not the round down
            report.failed.append((source.collection, str(error)))
            continue
        for item in uploads:
            if pressed >= most or report.stopped:
                break
            identifier = str(item.get("id") or "")
            if not identifier or _known(identifier):
                continue
            why = _gate(item, source.language)
            if why:
                _pass_over(identifier, why)
                report.passed.append((identifier, why))
                continue
            seconds = discover.seconds(str((item.get("contentDetails") or {}).get("duration")))
            used = credits_this_month(store, month_from)
            if used + _credits(seconds) > limit:
                report.stopped = f"the month's {limit} credits ({used} used)"
                break
            address = f"{youtube.WATCH}{identifier}"
            tracks = work / ".tracks" / identifier
            try:
                written = fetch_track(address, tracks, (source.language,))
            except Exception as error:  # noqa: BLE001 - no track is the ordinary case
                shutil.rmtree(tracks, ignore_errors=True)
                if _no_track(error):
                    _pass_over(identifier, "no track anybody wrote")
                    report.passed.append((identifier, "no track anybody wrote"))
                else:
                    # The proxy or YouTube, not the video: asked again tomorrow.
                    report.failed.append((identifier, str(error)[:200]))
                continue
            job = Job(
                id=secrets.token_hex(8),
                source=address,
                title=str((item.get("snippet") or {}).get("title") or ""),
                options={
                    "to": "en",
                    "words": True,
                    "from": source.language,
                    # The track somebody wrote, fetched above: nothing is heard here.
                    "transcript": str(written),
                    "via": KIND,
                },
                owner=None,
                admin=True,
                # targum's to pay, and nobody's hours (targum-internal#543).
                gift=True,
                home=work,
                kind=KIND,
            )
            library.jobs[job.id] = job
            library.remember(job)
            library.prepare(job)
            library.remember(job)
            if job.stage != "ready":
                # Nothing was spent on a quote, and a refusal at one is as often the way
                # out as the video: it is asked again tomorrow, never written off.
                report.failed.append((identifier, job.error or job.blocked or "not ready"))
                shutil.rmtree(tracks, ignore_errors=True)
                continue
            # Held to the cap at the quote's own length as well as the feed's.
            if used + _credits(job.seconds) > limit:
                report.stopped = f"the month's {limit} credits ({used} used)"
                shutil.rmtree(tracks, ignore_errors=True)
                break
            refused = library.press(job)
            if refused:
                # The box's day is full: tried again tomorrow, as a subscription waits.
                report.stopped = refused
                shutil.rmtree(tracks, ignore_errors=True)
                break
            # A press counts toward the round whether or not its build comes through.
            pressed += 1
            if not started:
                library.start_workers(1)
                started = True
            library.queue.join()
            shutil.rmtree(tracks, ignore_errors=True)
            if job.stage != "done" or not job.reader:
                why = job.error or job.message or job.stage
                _pass_over(identifier, f"build {why}")
                report.failed.append((identifier, why))
                continue
            folder = work / job.reader.split("/")[0]
            try:
                credit = str((item.get("snippet") or {}).get("channelTitle") or "")
                curated = curate.curate(
                    folder,
                    credit=credit,
                    licence=discover.LICENCE,
                    licence_url=discover.LICENCE_URL,
                )
                entry = _entry_for(folder, curated, source, item, today or date.today())
            except Exception as error:  # noqa: BLE001 - written down, the round goes on
                _pass_over(identifier, f"curate {error}")
                report.failed.append((identifier, str(error)))
                continue

            def add(held: dict[str, Any], entry: dict[str, Any] = entry) -> None:
                held["entries"].append(entry)

            _update(add)
            shutil.rmtree(folder, ignore_errors=True)
            report.built.append(identifier)


def drop(identifier: str) -> bool:
    """Take a grown video off the shelf: its row and its curated folder go, and it is
    written down as passed over, so the round never builds it again."""
    from .video import store

    name = identifier.removeprefix("video:")
    gone: set[str] = set()

    def change(held: dict[str, Any]) -> None:
        kept = [
            row
            for row in held["entries"]
            if str(row.get("source")) != f"video:{name}" and str(row.get("id")) != identifier
        ]
        gone.update(
            str(row.get("source", "")).removeprefix("video:")
            for row in held["entries"]
            if row not in kept
        )
        held["entries"] = kept
        for one in gone:
            held["passed"][one] = "taken down"

    _update(change)
    for one in gone:
        shutil.rmtree(store.folder(one), ignore_errors=True)
    return bool(gone)
