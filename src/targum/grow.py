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

**Off until the box says so.** `TARGUM_GROW` names the languages a round runs for and
`TARGUM_GROW_CREDITS` the month's cap; with either unset the round says what is off and
spends nothing. A video passed over is written down with why, and never asked about again.

**Nobody reads a grown video before it is on the shelf**, as nobody reads the weekly
before it goes out. What stands in for the read is the source: a channel a person chose
and filed in the catalogue. `targum grow drop <id>` takes one down.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import shutil
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .paths import write_atomic

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


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"entries": [], "passed": {}}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"entries": [], "passed": {}}
    if not isinstance(loaded, dict):
        return {"entries": [], "passed": {}}
    loaded.setdefault("entries", [])
    loaded.setdefault("passed", {})
    return loaded


def _write(path: Path, held: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, json.dumps(held, ensure_ascii=False, indent=1) + "\n")


_held: dict[Path, tuple[tuple[int, int], list[Entry], dict[str, list[str]]]] = {}


def _loaded() -> tuple[list[Entry], dict[str, list[str]]]:
    """The index as entries and as collection members, read again only when it changed:
    `catalogue.everything` asks on every page."""
    from .catalogue import _entry

    path = index_path()
    try:
        stat = path.stat()
    except OSError:
        return [], {}
    stamp = (stat.st_mtime_ns, stat.st_size)
    held = _held.get(path)
    if held is not None and held[0] == stamp:
        return held[1], held[2]
    entries: list[Entry] = []
    members: dict[str, list[str]] = {}
    for raw in _read(path)["entries"]:
        try:
            entries.append(_entry(raw))
        except (KeyError, ValueError, TypeError):
            continue
        if raw.get("collection"):
            members.setdefault(str(raw["collection"]), []).append(str(raw["id"]))
    _held[path] = (stamp, entries, members)
    return entries, members


def entries() -> list[Entry]:
    """Every grown video, as a catalogue entry. Empty on a machine that grew none."""
    return list(_loaded()[0])


def members() -> dict[str, list[str]]:
    """Grown entry ids by the collection whose channel brought them."""
    return {key: list(value) for key, value in _loaded()[1].items()}


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
    building and what was built. A build that failed handed its claim back."""
    from .accounts import SECONDS_A_CREDIT

    row = store.db.execute(
        "SELECT COALESCE(SUM(seconds), 0) AS used FROM job"
        " WHERE kind = ? AND made >= ? AND stage IN ('queued', 'working', 'done')",
        (KIND, month_from),
    ).fetchone()
    return round(float(row["used"]) / SECONDS_A_CREDIT)


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


def _known(identifier: str, held: Mapping[str, Any]) -> bool:
    from . import catalogue
    from .video import store

    if identifier in held["passed"] or store.folder(identifier).exists():
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
    """One round: for each source in a language switched on, build what is new and
    passes, inside the month's credits, through `Library.press`. Never raises for one
    video: it is written down and the round goes on."""
    from .serve import Job
    from .video import curate, discover, youtube

    report = Grown()
    on = languages()
    if not on:
        report.stopped = f"off ({FLAG} names no language)"
        return report
    limit = cap()
    if limit <= 0:
        report.stopped = f"off ({CREDITS_ENV} sets no cap)"
        return report
    ask = get or discover.fetch
    fetch_track = track or youtube.fetch_subtitles
    held_key = api_key or discover.key()
    path = index_path()
    held = _read(path)
    work = library.out / WORKSPACE
    month_from = int(library._month_from())
    started = False
    for source in sources():
        if source.language not in on or len(report.built) >= most:
            continue
        try:
            uploads = _uploads(source, ask, held_key)
        except Exception as error:  # noqa: BLE001 - one channel down is not the round down
            report.failed.append((source.collection, str(error)))
            continue
        for item in uploads:
            if len(report.built) >= most or report.stopped:
                break
            identifier = str(item.get("id") or "")
            if not identifier or _known(identifier, held):
                continue
            why = _gate(item, source.language)
            if why:
                held["passed"][identifier] = why
                report.passed.append((identifier, why))
                _write(path, held)
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
                    held["passed"][identifier] = "no track anybody wrote"
                    report.passed.append((identifier, "no track anybody wrote"))
                    _write(path, held)
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
            refused = library.press(job)
            if refused:
                # The box's day is full: tried again tomorrow, as a subscription waits.
                report.stopped = refused
                shutil.rmtree(tracks, ignore_errors=True)
                break
            if not started:
                library.start_workers(1)
                started = True
            library.queue.join()
            shutil.rmtree(tracks, ignore_errors=True)
            if job.stage != "done" or not job.reader:
                why = job.error or job.message or job.stage
                held["passed"][identifier] = f"build {why}"[:200]
                report.failed.append((identifier, why))
                _write(path, held)
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
                held["passed"][identifier] = f"curate {error}"[:200]
                report.failed.append((identifier, str(error)))
                _write(path, held)
                continue
            held = _read(path) | {"passed": held["passed"]}
            held["entries"].append(entry)
            _write(path, held)
            shutil.rmtree(folder, ignore_errors=True)
            report.built.append(identifier)
    return report


def drop(identifier: str) -> bool:
    """Take a grown video off the shelf: its row and its curated folder go, and it is
    written down as passed over, so the round never builds it again."""
    from .video import store

    path = index_path()
    held = _read(path)
    name = identifier.removeprefix("video:")
    kept = [
        row
        for row in held["entries"]
        if str(row.get("source")) != f"video:{name}" and str(row.get("id")) != identifier
    ]
    if len(kept) == len(held["entries"]):
        return False
    gone = {str(row.get("source", "")).removeprefix("video:") for row in held["entries"]} - {
        str(row.get("source", "")).removeprefix("video:") for row in kept
    }
    held["entries"] = kept
    for one in gone:
        held["passed"][one] = "taken down"
        shutil.rmtree(store.folder(one), ignore_errors=True)
    _write(path, held)
    return True
