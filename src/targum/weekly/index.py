"""The list of issues the box has, and where it keeps them.

Read from disk rather than from the account database on purpose. The database holds
people; this holds content. Keeping the two apart is what makes "a subscriber is not an
account" structurally true rather than a promise, and it means the process that writes an
issue never opens the file every reader's vocabulary is in.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from ..paths import write_atomic
from .models import Index, Issue, Level, State, folder

#: `catalogue._read` is `@cache`d because a catalogue file only changes across a
#: restart. This one changes while the process is up — an issue is published under a
#: running server — so it is keyed on the file's own mtime and size instead, behind a
#: lock, because `ThreadingHTTPServer` hands every request to a different thread.
_lock = threading.Lock()
_cached: tuple[tuple[Path, int, int], Index] | None = None


def root() -> Path:
    """Where the issues are.

    Named in the environment, the way the catalogue is, rather than handed in by
    whichever object happened to be built last. It was a module-level override set from
    `Library.__init__` first, and that is process-global state written by a constructor:
    two servers in one process — which is a test suite, not a deployment, but a real
    thing that happens — then took it in turns to point it at each other's directories,
    and the failures landed in whichever tests ran while it was pointed elsewhere.
    """
    named = os.environ.get("TARGUM_WEEKLY_DIR", "").strip()
    if named:
        return Path(named).expanduser()
    return Path.cwd() / "targum-out" / "weekly"


def index_path() -> Path:
    return root() / "index.json"


def load() -> Index:
    """Every issue on disk, or an empty index where there is no weekly at all.

    Absent is not an error. With no file the whole weekly surface is simply missing,
    the same way the library is empty without a catalogue.
    """
    global _cached
    path = index_path()
    try:
        stat = path.stat()
    except OSError:
        return Index()
    stamp = (path, stat.st_mtime_ns, stat.st_size)
    with _lock:
        if _cached is not None and _cached[0] == stamp:
            return _cached[1]
        try:
            index = Index.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValueError):
            # A half-written or hand-broken index leaves the weekly absent rather than
            # taking the library down with it. `save` writes atomically, so this is a
            # file somebody edited, and they will want the server still answering.
            return Index()
        _cached = (stamp, index)
        return index


def save(index: Index) -> Path:
    """Write the index whole. Always last: a folder is not atomic and an issue listed
    before its reader has finished uploading is an issue that 404s."""
    return write_atomic(
        index_path(), json.dumps(index.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
    )


def issues() -> list[Issue]:
    """Everything, newest first, drafts included."""
    return sorted(load().issues, key=lambda issue: issue.dated, reverse=True)


def published() -> list[Issue]:
    return [issue for issue in issues() if issue.state is State.published]


def latest() -> Issue | None:
    return next(iter(published()), None)


def built(week: str, level: Level) -> bool:
    """Whether this edition has a reader on disk.

    Published and readable are not the same fact, and the gap between them is a real
    state: a publish that ran before a build, or a copy to the box that only half
    arrived. Asked of the weekly's own root, which is where both the index and the
    readers live.
    """
    return (root() / folder(week, level) / "reader" / "index.html").is_file()


def readable() -> list[Issue]:
    """Published issues, holding only the editions somebody can actually open.

    Every surface that offers the weekly asks this rather than `published`: the front
    page, the sitemap, the library's rows, the redirect from a catalogue id. They used
    to ask whether an issue was published, which meant a half-shipped issue put three
    dead URLs in the sitemap, a row on the shelf that led to a 404, and a redirect from
    one address to another that was not there.
    """
    out: list[Issue] = []
    for issue in published():
        editions = [one for one in issue.editions if built(issue.id, one.level)]
        if editions:
            out.append(issue.model_copy(update={"editions": editions}))
    return out


def by_week(week: str) -> Issue | None:
    return next((issue for issue in issues() if issue.id == week), None)
