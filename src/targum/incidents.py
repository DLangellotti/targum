"""Somewhere an error is recorded, other than the journal (targum-internal#24).

A build that dies at 80% leaves nothing to read, and until now the only trace was a
traceback in the box's journal, which nobody opens unless a reader has already written
to say something is wrong. This is the other half of "I find out it broke before she
tells me": every exception a request or a build swallows is written here, and the back
office lists them.

**A file, not a vendor.** Sentry's free tier was the obvious answer and is not the one
taken, for the reason the back office gives for itself: the box is a thing one person
runs, and a page it already serves to that person is a smaller door than an account on
somebody else's service with a copy of every traceback. Nothing leaves the box.

**A ring, not a log.** The last `KEEP` incidents, newest last on disk and newest first
when read. An operator who has not looked in a month wants the recent ones, and a file
that grows without bound on a box that has OOM-killed a rebuild is its own incident.

**Counts and causes, never content.** What is kept: when, where (a route with its query
string cut off, or a build stage), the exception's type, its message and the tail of its
traceback, and a job id. What is never kept: a request body, an address, a reader's text.
A message is cut short and anything shaped like an email address in it is replaced,
because the mailer's own errors quote the address they failed to reach.
"""

from __future__ import annotations

import json
import re
import threading
import traceback
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

#: How many incidents the file keeps.
KEEP = 200

#: How many it is allowed to grow to before it is trimmed back to `KEEP`, so the rewrite
#: is not on every append.
TRIM_AT = KEEP * 2

#: How much of a message and a traceback are kept.
MESSAGE_CHARS = 300
TRACE_LINES = 12

_ADDRESS = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")

_lock = threading.Lock()


@dataclass(frozen=True)
class Incident:
    at: str
    where: str
    kind: str
    message: str
    trace: str = ""
    job: str = ""


def scrub(text: str) -> str:
    """A message safe to keep: cut short, and no address left in it."""
    return _ADDRESS.sub("<address>", text or "")[:MESSAGE_CHARS]


def _trace(error: BaseException) -> str:
    lines = traceback.format_exception(type(error), error, error.__traceback__)
    tail = "".join(lines).strip().splitlines()[-TRACE_LINES:]
    return scrub("\n".join(tail))


def record(
    path: Path,
    where: str,
    error: BaseException | None = None,
    *,
    message: str = "",
    job: str = "",
) -> Incident:
    """Write one incident down. Never raises: a recorder that fails inside an exception
    handler turns one incident into two and hides the first."""
    incident = Incident(
        at=datetime.now(UTC).isoformat(timespec="seconds"),
        where=where.split("?", 1)[0][:120],
        kind=type(error).__name__ if error is not None else "",
        message=scrub(message or (str(error) if error is not None else "")),
        trace=_trace(error) if error is not None else "",
        job=job,
    )
    try:
        with _lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as out:
                out.write(json.dumps(asdict(incident), ensure_ascii=False) + "\n")
            _trim(path)
    except Exception:  # noqa: BLE001 - see the docstring
        pass
    return incident


def _trim(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) <= TRIM_AT:
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(lines[-KEEP:]) + "\n", encoding="utf-8")
    tmp.replace(path)


def recent(path: Path, limit: int = 50) -> list[Incident]:
    """The latest incidents, newest first. No file, no incidents."""
    if not path.is_file():
        return []
    found: list[Incident] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        try:
            found.append(Incident(**raw))
        except TypeError:
            continue
    return list(reversed(found[-limit:]))
