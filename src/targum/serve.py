"""A local page for building readers without the terminal.

Not a hosted service: it binds to the loopback address, holds nothing but the readers
you build, and stops when you close it. It exists because pointing at a text and
choosing a language should not require remembering a command.

The pipeline runs in this process, so the page can only do what the CLI can do, and
the cost gate works the same way: ingest and segment first, show what a translation
would cost, and spend nothing until you say so.
"""

from __future__ import annotations

import base64
import contextlib
import errno
import gzip
import json
import os
import queue
import re
import secrets
import shutil
import threading
import traceback
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cache, lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlparse

from .accounts import Person, Store, now, plausible
from .errors import TargumError
from .mail import Mailer
from .models import Segment, SegmentedDocument, Style, glossary_path
from .pipeline import Build, Result
from .render.builder import about_page, holding_page, shelf_page, signin_page, text_page

MAX_UPLOAD = 32 * 1024 * 1024

# Which `Host` a request may claim. Loopback always, because that is what a machine
# somebody runs themselves is reached by and what a reverse proxy connects to. Hosted,
# the public address is added: behind a proxy the original Host survives the hop, so a
# signed-in reader at targum.page arrives claiming targum.page, and a loopback-only
# allowlist refuses every page they ask for — with a message telling them to open a
# Terminal they do not have. `www.` is included because a registrar's default redirect
# is not always in place on the first day.
SAFE_HOSTS = ("127.0.0.1", "localhost", "[::1]")


def hosts_for(public_address: str) -> frozenset[str]:
    """The names this server will answer to."""
    allowed = set(SAFE_HOSTS)
    host = urlparse(public_address).hostname if public_address else ""
    if host and host not in allowed:
        allowed.add(host)
        # A name, not an address: `www.` means nothing in front of an IP.
        if not host.replace(".", "").isdigit():
            allowed.add(host[4:] if host.startswith("www.") else f"www.{host}")
    return frozenset(allowed)


# A base64 body is a third larger than the file inside it, so this is the real ceiling
# on what someone can drop, and the number the page quotes when it refuses one.
MAX_FILE_MB = int(MAX_UPLOAD / 1.37 / (1024 * 1024))

# Said once, in the page, rather than as a stack trace after the wait. Without a key the
# builder can still open everything already built, so this blocks a text rather than
# stopping the server.
NO_KEY = "Nothing new can be built now. Everything you have still opens."

# A full-length novel costs real money to translate, and a page anyone on this machine
# can reach should not be able to spend it by accident. Both are estimates rather than
# billed amounts, so they are deliberately conservative.
HTML = "text/html; charset=utf-8"

# What the hosted product translates with. Opus stays reachable from the command line
# for anyone who wants it and is paying for it themselves.
HOSTED_MODEL = "claude-sonnet-5"

# A deleted Targum waits in the trash before it goes. Deleting is one press on a day
# somebody is tidying up, and a week is what makes that survivable — the same reasoning,
# and the same seven days, as an account that asks to be forgotten.
# How much of a book is bought before anybody has read a word of it. One: the reader
# waits under a minute instead of half an hour, and the next chapter is started while
# they are most of the way through this one.
FIRST_CHAPTERS = 1

TRASH_DAYS = 7

# Written inside the folder rather than kept in a table: the folder is the thing being
# deleted, and a marker inside it cannot drift away from what it describes.
TRASHED = "trashed"

# What a page is allowed to do. Readers are self-contained by construction — no script,
# stylesheet, font or image from anywhere, and the tests hold that — so the policy can
# be the strict one rather than a shrug: nothing loads from outside, the page cannot be
# framed, and there is no form to post anywhere.
#
# Inline script and style are the whole design here: a reader is one file that works off
# a disk with no server. Rather than `unsafe-inline`, which would allow anything a
# defect managed to inject, each block is named by the hash of its own contents, so only
# the code targum wrote will run.
POLICY = (
    "default-src 'none'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "base-uri 'none'; "
    # 'self', not 'none'. The sign-in landing page posts a real form back to targum —
    # it has to work with no JavaScript, because it arrives from an email in whatever
    # browser opened it — and 'none' forbids exactly that. A reader has no form at all,
    # so this permits nothing it could use.
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

# What one reader may spend in the window, against what the whole machine may. The
# per-account figure is a safety rail for the alpha and not a plan limit: Milestone C
# settles what a tier actually allows, in texts and pages rather than dollars, once the
# real numbers from `usage` have been watched for a while.
ACCOUNT_BUDGET = 3.00

# What one reader is allowed in a calendar month. The daily rail above is a rate limit —
# it stops one afternoon running away — and for a while it was standing in for a plan
# limit as well, which it is bad at: thirty days of $3.00 is $90.00, and nobody agreed to
# that. This is the number a reader is actually held to.
#
# A calendar month rather than a rolling thirty days, because it is the one a refusal can
# name — "back on the 1st" is a date somebody can plan around, where "back in a few days"
# is a shrug. It costs a month boundary where readers get their allowance back at once,
# which for an alpha of a handful of people is not a thundering herd.
MONTH_BUDGET = 10.00

# Hosted, everyone signs in first. Signed out, every home would be the same `local`
# directory, so one visitor would be reading another's library — and there is nowhere
# to put a build that belongs to nobody. On a machine somebody runs themselves the
# opposite is true: there is one person, they are the only one who can reach it, and
# making them make an account to read their own files would be absurd. So it is a
# switch, off by default, and the hosted deployment is what turns it on.
OPEN_TO_STRANGERS = frozenset(
    {"/about", "/account/signin", "/account/enter", "/account/sign-in", "/account/me", "/health"}
)

# The public shelves, and every text on them. Built, tested, and deliberately shut:
# nothing is open to strangers until there is something worth arriving at and a
# whitelist deciding who may come in.
#
# Shut means shut all the way down. A robots.txt that invites a crawler while every
# page it reaches says "Coming soon" is worse than none at all — what gets indexed is
# the holding page, and that is then what ranks for the product's own name later. So
# while this is off the sitemap is gone and robots refuses the whole site.
PUBLIC_TEXT = re.compile(r"^/library/([a-z0-9][a-z0-9-]{0,63})$")


def shelves_are_public() -> bool:
    """Whether strangers may see the catalogue. Off unless the deployment says so."""
    return os.environ.get("TARGUM_PUBLIC_SHELVES", "").strip().lower() in {"1", "true", "yes"}


# What somebody who has not been invited is told. Honest about the state of things and
# says nothing about who is on the list.
NOT_OPEN = "targum is not open yet."

#: What a drawn cover may be saved as. No SVG: these arrive from an image model and an
#: SVG is a script that runs, which is not a thing to serve from a directory anybody can
#: drop files into. Both halves of the app read this — one plans covers, one serves them.
THUMBS = ((".webp", "image/webp"), (".png", "image/png"), (".jpg", "image/jpeg"))

MAX_COST = 2.00
SESSION_BUDGET = 10.00

# The budget used to last as long as the process, which meant restarting handed it back
# in full. It is a rolling day instead: it survives a restart, and it does not brick the
# machine a week later the way a permanent total would. A4 replaces it with a per-account
# monthly limit; until then this is the ceiling on what one box will spend in a day.
BUDGET_HOURS = 24

# Builds run one at a time. Stanza and LaBSE are large enough that two at once is worse
# than two in sequence, and a thread per request is a way for one visitor to exhaust the
# machine — which mattered less on a laptop than it does on a box anyone can reach.
WORKERS = 1


# The dead end anyone reaches by bookmarking the address or leaving a tab open over a
# restart. The key changes every start, so this is a normal thing to hit, and a blank
# line of plain text left no way back.
STALE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>targum</title>
<style>
  :root { color-scheme: light dark; }
  body {
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    padding: 2rem; background: #faf8f4; color: #2b2724;
    font: 16px/1.6 system-ui, sans-serif;
  }
  main { max-width: 30rem; }
  h1 { font-size: 1.5rem; margin: 0 0 0.75rem; }
  p { margin: 0 0 0.75rem; }
  code { background: #ece7de; padding: 0.1em 0.35em; border-radius: 3px; font-size: 0.9em; }
  form { display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 1.25rem 0 0.75rem; }
  input, button {
    font: inherit; padding: 0.5rem 0.75rem; border-radius: 6px;
    border: 1px solid #d9d2c5; background: #fff; color: inherit;
  }
  input { flex: 1 1 14rem; min-width: 0; }
  button { background: #7a5c3a; border-color: #7a5c3a; color: #fff; cursor: pointer; }
  .said, .aside { color: #6b625a; font-size: 0.9375rem; }
  .said[hidden] { display: none; }
  @media (prefers-color-scheme: dark) {
    body { background: #17150f; color: #ece7de; }
    code { background: #2b2724; }
    input { background: #221f1a; border-color: #3b352c; }
    .said, .aside { color: #a79c8e; }
  }
</style>
</head>
<body>
<main>
  <h1>This tab has gone stale</h1>
  <p>Nothing is lost. Everything you were reading, and every word you have kept, is
  still there.</p>
  <p>Sign in and this stops happening: a signed-in tab keeps working, and your words
  follow you to whatever you read on next.</p>
  <form id="in">
    <input type="email" id="email" placeholder="you@example.com" autocomplete="email"
           spellcheck="false" required>
    <button type="submit">Email me a link</button>
  </form>
  <p class="said" id="said" hidden></p>
  <p class="aside">Running targum yourself? The Terminal window also prints a link, and
  that one works straight away.</p>
</main>
<script>
document.getElementById("in").addEventListener("submit", function (event) {
  event.preventDefault();
  var said = document.getElementById("said");
  said.hidden = false;
  said.textContent = "Sending\u2026";
  fetch("/account/sign-in", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: document.getElementById("email").value }),
  })
    .then(function (response) { return response.json(); })
    .then(function (answer) { said.textContent = answer.message || answer.error; })
    .catch(function () { said.textContent = "That did not go through. Try again."; });
});
</script>
</body>
</html>"""


@cache
def _icon() -> bytes:
    """The tab icon for /favicon.ico, which only takes a raster."""
    brand = Path(__file__).parent / "render" / "assets" / "brand"
    return (brand / "favicon-32.png").read_bytes()


@dataclass
class Job:
    id: str
    source: str
    title: str = ""
    language: str = ""
    segments: int = 0
    estimate: float = 0.0
    stage: str = "reading"
    done: int = 0
    total: int = 0
    message: str = ""
    error: str = ""
    reader: str = ""
    lemmas: int = 0
    meanings: float = 0.0
    blocked: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    # Whose build this is, and where its reader lands. The thread that runs it has no
    # request to ask, so both travel with the job rather than being looked up later.
    owner: int | None = None
    home: Path | None = None
    # Whether the person who asked for it is held to the per-account spend rails. Read
    # at claim time and never written down: it is a fact about who they are now, not
    # about this job, and a job recovered after a restart has already been claimed.
    admin: bool = False
    # What it really cost, once the API has said. Zero until it has.
    spent: float = 0.0
    # How many chapters the text has. One means it is not a book.
    chapters: int = 1
    made: int = field(default_factory=now)

    def state(self) -> dict[str, Any]:
        return {
            "blocked": self.blocked,
            "id": self.id,
            "made": self.made,
            "title": self.title,
            "language": self.language,
            "segments": self.segments,
            "chapters": self.chapters,
            "estimate": round(self.estimate, 2),
            "stage": self.stage,
            "done": self.done,
            "total": self.total,
            "message": self.message,
            "error": self.error,
            "reader": self.reader,
            "lemmas": self.lemmas,
            # Translation and word meanings are priced separately because they are
            # bought separately: one line quoting the sum made the meanings look free
            # and hid that unticking the box halves the bill.
            "meanings": round(self.meanings, 2),
            "translation": round(max(0.0, self.estimate - self.meanings), 2),
        }


# A person's home is `p` and their number, and nothing else. Matching on the `p` alone
# would treat a text called "poem-he" as somebody's home and leave it unadopted, which
# is to say invisible.
HOME = re.compile(r"p\d+")

# Either kind of home, in front of an uploaded text's cover — `p` and a number for
# somebody signed in, `local` for the machine's own signed-out shelf. A name arriving
# with one of these already on it is asking for a file by somebody else's key rather
# than its own; `_serve_thumb` puts the asker's own home on and never reads a name that
# came carrying one.
OWNED = re.compile(r"(?:p\d+|local)-")


def free_name(home: Path, name: str) -> Path:
    """A name in this home that nothing is using yet.

    Two documents can slug to the same name and hold different texts, and adopting one
    over the other would silently destroy work. Renaming over a directory that already
    has something in it does not even fail cleanly — it raises, part-way through
    start-up, and the server never comes up.
    """
    target = home / name
    nth = 2
    while target.exists():
        target = home / f"{name}-{nth}"
        nth += 1
    return target


@dataclass(frozen=True)
class Drawable:
    """A text a cover can be drawn for, whether or not the catalogue has heard of it.

    A catalogue `Entry` answers all four of these already; an upload answers them from
    its own document. Everything downstream of `cover_plan` asks for exactly this much,
    so neither has to know which it is holding.
    """

    id: str
    source: str
    title: str
    language: str


class Library:
    """Everything built so far, and the jobs building more."""

    def __init__(
        self,
        out: Path,
        max_cost: float = MAX_COST,
        budget: float = SESSION_BUDGET,
        store: Store | None = None,
        account_budget: float | None = ACCOUNT_BUDGET,
        month_budget: float | None = MONTH_BUDGET,
        mailer: Mailer | None = None,
        address: str = "",
    ) -> None:
        self.out = out
        # How to reach somebody whose build finished while they were away, and where
        # the reader is. Neither is needed on a machine somebody runs themselves.
        self.mailer = mailer
        self.address = address
        # A home nobody owns, read by everybody: what a reader with nothing on their
        # shelf is handed to start with. Written only by `targum seed`, never by a
        # request — nothing routed through `within(home, …)` can reach it, so a shared
        # text cannot be bought, trashed or rebuilt by whoever is reading it.
        self.shared = out / "shared"
        self.max_cost = max_cost
        self.budget = budget
        self.account_budget = account_budget
        self.month_budget = month_budget
        self.store = store
        self.adopt()
        self.empty_trash()
        self.purge_departed()
        self._committed = 0.0
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()
        self.queue: queue.Queue[str] = queue.Queue()
        self._workers: list[threading.Thread] = []
        if store is not None:
            self._recover(store)

    # -- durability -------------------------------------------------------------

    def _recover(self, store: Store) -> None:
        """Read back what the last run was doing.

        A build cannot be picked up from the middle: the work was in a thread that no
        longer exists. What it can do is stop lying about itself — a job left at
        "working" would sit there forever — and hand back the money it never spent.
        """
        store.interrupt_running()
        for row in store.jobs():
            job = Job(
                id=str(row["id"]),
                source=str(row["source"]),
                title=str(row["title"]),
                language=str(row["language"]),
                segments=int(row["segments"]),
                estimate=float(row["estimate"]),
                stage=str(row["stage"]),
                done=int(row["done"]),
                total=int(row["total"]),
                message=str(row["message"]),
                error=str(row["error"]),
                reader=str(row["reader"]),
                lemmas=int(row["lemmas"]),
                meanings=float(row["meanings"]),
                blocked=str(row["blocked"]),
                spent=float(row["spent"]),
                chapters=int(row["chapters"]),
                options=json.loads(row["options"] or "{}"),
                owner=row["owner"],
                home=Path(str(row["home"])),
            )
            self.jobs[job.id] = job

    def remember(self, job: Job) -> None:
        """Put a job's current state on disk. Cheap, and safe to call often."""
        if self.store is None:
            return
        self.store.save_job(
            {
                "id": job.id,
                "owner": job.owner,
                "home": str(job.home or self.out),
                "source": job.source,
                "options": json.dumps(job.options, ensure_ascii=False),
                "stage": job.stage,
                "title": job.title,
                "language": job.language,
                "segments": job.segments,
                "chapters": job.chapters,
                "estimate": job.estimate,
                "done": job.done,
                "total": job.total,
                "message": job.message,
                "error": job.error,
                "reader": job.reader,
                "lemmas": job.lemmas,
                "meanings": job.meanings,
                "blocked": job.blocked,
                "spent": job.spent,
                "made": job.made,
            }
        )

    # -- the queue --------------------------------------------------------------

    def start_workers(self, count: int = WORKERS) -> None:
        for _ in range(count):
            worker = threading.Thread(target=self._drain, daemon=True)
            worker.start()
            self._workers.append(worker)

    def _drain(self) -> None:
        while True:
            job = self.jobs.get(self.queue.get())
            if job is not None:
                self.run(job)
            self.queue.task_done()

    #: A finished build stays on the list this long, so the strip on every page can say
    #: it is ready and hand over the link. The page forgets one the reader has dismissed.
    RECENT_MS = 60 * 60 * 1000

    #: A build longer than this earns an email when it finishes: the reader has most
    #: likely gone to do something else, and the page they started it from is gone.
    LONG_BUILD_MS = 3 * 60 * 1000

    def mine(self, owner: int | None) -> list[dict[str, Any]]:
        """One person's builds, newest first, each saying how far back in the line it is.

        The queue itself is not safely introspectable, so the position is derived: the
        jobs waiting, in the order they were made, plus one for the job being worked on
        — which with one worker is exact. The reader's page can then say "waiting
        behind one other build" rather than leaving a second build to look stuck.
        """
        working = any(job.stage == "working" for job in self.jobs.values())
        waiting = sorted(
            (job for job in self.jobs.values() if job.stage == "queued"), key=lambda j: j.made
        )
        position = {job.id: index + (1 if working else 0) for index, job in enumerate(waiting)}
        cutoff = now() - self.RECENT_MS
        out: list[dict[str, Any]] = []
        for job in sorted(self.jobs.values(), key=lambda j: j.made, reverse=True):
            if job.owner != owner:
                continue
            if job.stage in ("done", "failed", "blocked") and job.made < cutoff:
                continue
            if job.stage in ("reading", "ready"):
                # Priced and not yet started: nothing is building, so there is nothing
                # to follow. The page that asked for the price is still showing it.
                continue
            out.append(
                {
                    **job.state(),
                    "behind": position.get(job.id, 0),
                    # Whether putting the strip away can honestly promise an email.
                    "mail": self.can_mail(owner),
                }
            )
        return out

    def can_mail(self, owner: int | None) -> bool:
        """Whether a finished build could reach this person by email at all: hosted,
        with an address to put in the link, and somebody signed in to send it to."""
        return (
            self.mailer is not None
            and bool(self.address)
            and self.store is not None
            and owner is not None
        )

    def tell(self, job: Job) -> None:
        """Email whoever asked for a build that took long enough for them to have left —
        or who put the strip away and was promised one.

        Best effort, and never a reason for a finished build to count as failed: the
        reader is on disk whether or not the message about it arrives.
        """
        # Spelt out rather than asked of `can_mail`, so the checker sees each is there.
        if self.mailer is None or self.store is None or job.owner is None:
            return
        if not self.address or not job.reader:
            return
        if not job.options.get("mail") and now() - job.made < self.LONG_BUILD_MS:
            return
        with contextlib.suppress(Exception):
            person = self.store.person_by_id(job.owner)
            if person is None:
                return
            path = "/".join(quote(part) for part in job.reader.split("/"))
            link = f"{self.address}/reader/{path}" if self.address else ""
            title = job.title or job.source
            self.mailer.notify(
                person.email,
                f"{title} is ready",
                f"{title} is ready to read.\n\n{link}\n".rstrip() + "\n",
            )

    def enqueue(self, job: Job) -> None:
        job.stage = "queued"
        self.remember(job)
        self.queue.put(job.id)

    def home(self, person: Person | None) -> Path:
        """Where this person's readers live.

        Every home is a directory of its own, including the signed-out one, so that no
        home contains another and the traversal guard below has something real to
        resolve against. Before this, one output directory was shared by whoever could
        reach the server, which on a machine somebody runs themselves is the same
        person and hosted is not.

        Signed out, everyone shares `local`. That is right for a single-user machine
        and wrong for a hosted box, which is why hosted has to require an account —
        the sign-in page in A2 is what closes it.
        """
        return self.out / (f"p{person.id}" if person else "local")

    def _sole_owner(self) -> Path | None:
        """The one person on this machine, if there is exactly one.

        A machine somebody runs themselves has one account on it, and everything built
        on it is theirs — including everything built before they made the account.
        Two or more, and who owns an old build is a guess, so it is not made.
        """
        if self.store is None:
            return None
        people = self.store.db.execute("SELECT id FROM person LIMIT 2").fetchall()
        if len(people) != 1:
            return None
        return self.out / f"p{int(people[0]['id'])}"

    def adopt(self) -> None:
        """Move what was built before homes existed into the home it belongs to.

        Without this, upgrading hides every reader already on disk: the code starts
        looking one directory deeper and finds nothing.

        Where they land is the part that is easy to get wrong, and I got it wrong once:
        everything went to the signed-out home, so the one person on the machine signed
        in and found an empty library. If there is exactly one account here, the
        builds are theirs.
        """
        if not self.out.is_dir():
            return
        local = self.out / "local"
        owner = self._sole_owner()
        home = owner or local
        # Builds already adopted into the signed-out home before this was understood.
        # Only when the person has no home yet, so this is a one-time upgrade and never
        # a way for one account to inherit what other people built while signed out.
        if owner is not None and not owner.exists() and local.is_dir():
            owner.mkdir(parents=True, exist_ok=True)
            for folder in list(local.iterdir()):
                if folder.is_dir():
                    with contextlib.suppress(OSError):
                        folder.rename(free_name(owner, folder.name))
        for folder in list(self.out.iterdir()):
            if not folder.is_dir() or folder.name == "local" or HOME.fullmatch(folder.name):
                continue
            # Any document folder, not only one that reached a rendered reader:
            # "ingested, then never translated" is a real state and orphaning it
            # would lose the work already paid for.
            if not (folder / "document.json").is_file():
                continue
            home.mkdir(parents=True, exist_ok=True)
            try:
                folder.rename(free_name(home, folder.name))
            except OSError:
                # One folder that will not move is not a reason for targum not to
                # start. It stays where it is and is tried again next time.
                continue

    def remaining(self) -> float:
        return max(0.0, self.budget - self.committed)

    @property
    def committed(self) -> float:
        if self.store is None:
            return self._committed
        return self.store.committed(self._since())

    @staticmethod
    def _since() -> int:
        return now() - BUDGET_HOURS * 60 * 60 * 1000

    @staticmethod
    def _month_from() -> int:
        """Midnight UTC on the first of this month, in the milliseconds `job.made` uses.

        UTC rather than the box's zone: the box moves and the ledger does not, and a
        budget that resets an hour early because somebody changed a timezone is a bug
        nobody would find.
        """
        today = datetime.now(UTC)
        first = datetime(today.year, today.month, 1, tzinfo=UTC)
        return int(first.timestamp() * 1000)

    @staticmethod
    def _month_ends() -> str:
        """When this month's allowance comes back, as a date a refusal can name."""
        today = datetime.now(UTC)
        year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
        return datetime(year, month, 1, tzinfo=UTC).strftime("%-d %B")

    def settle(self, job: Job) -> None:
        """Swap what a build reserved for what it spent."""
        if self.store is not None:
            self.store.settle(job.id, job.spent)

    def release(self, job: Job) -> None:
        """Give back what a failed build had claimed but never spent."""
        if self.store is not None:
            return self.store.unclaim(job.id)
        with self.lock:
            self._committed = max(0.0, self._committed - job.estimate)

    def already_over(self, job: Job) -> str:
        """Whether this person is out of money before the work is priced.

        `claim` is the real gate: it reserves an estimate inside a transaction, so two
        builds cannot both pass on the same balance. Buying a chapter cannot use it,
        because pricing one means lemmatising it and that is Stanza inside the request
        that a reader is waiting on.

        So this is the weaker check that path can afford: not "is there room for this",
        which needs a price, but "is there any room at all". It cannot stop a reader
        going over — the chapter that takes them past the line still runs — but it stops
        the one after it, and a chapter is small. Without it the cap does not apply to
        the way a book is actually bought, and the reader prefetches the next chapter at
        60% of this one, so that path spends on its own.
        """
        if job.admin or self.store is None:
            return ""
        day = self._since()
        if self.store.committed(day) >= self.budget:
            return self._out_of("everyone")
        if self.month_budget is not None:
            if self.store.committed(self._month_from(), job.owner) >= self.month_budget:
                return self._out_of("month")
        if self.account_budget is not None:
            if self.store.committed(day, job.owner) >= self.account_budget:
                return self._out_of("account")
        return ""

    def _out_of(self, whose: str) -> str:
        """Which ceiling stopped this, and when it lifts.

        A refusal that does not say which limit was hit, or when it stops applying, is
        indistinguishable from the product being broken.
        """
        when = f"in {BUDGET_HOURS} hours"
        if whose == "month":
            # A date rather than a duration: this one is a month away, and "in 30 days"
            # is a number somebody has to do arithmetic on to plan around.
            return (
                f"You have read your fill for this month. Back on {self._month_ends()}. "
                "The library is always free."
            )
        if whose == "account":
            return f"You have read your fill for now. Back {when}. The library is always free."
        return f"targum is at its limit. Try again {when}, or read from the library."

    def why_blocked(self, estimate: float) -> str:
        """Whether this build may go ahead, in words the page can show."""
        if estimate > self.max_cost:
            # The reader pays by the month and never by the text, so what stops them is
            # a limit on the thing itself, not a sum of money they have never been shown.
            return "Too long. Try a chapter, or something from the library."
        if estimate > self.remaining():
            return "Enough for one sitting. Come back later."
        return ""

    @staticmethod
    def trashed_at(folder: Path) -> int:
        """When this was thrown away, or 0 if it was not."""
        marker = folder / TRASHED
        if not marker.is_file():
            return 0
        try:
            return int(marker.read_text(encoding="utf-8").strip() or 0)
        except (OSError, ValueError):
            return 0

    def trash(self, home: Path, name: str) -> bool:
        """Throw one away. Nothing is deleted yet."""
        folder = self.within(home, name)
        if folder is None or not (folder / "reader" / "index.html").is_file():
            return False
        (folder / TRASHED).write_text(str(now()), encoding="utf-8")
        return True

    def restore(self, home: Path, name: str) -> bool:
        """Change your mind, while there is still something to change it about."""
        folder = self.within(home, name)
        if folder is None:
            return False
        (folder / TRASHED).unlink(missing_ok=True)
        return True

    @staticmethod
    def within(home: Path, name: str) -> Path | None:
        """A folder in this home, and nowhere else.

        The name arrives from a request, so it is resolved and checked rather than
        trusted: `../` in it would otherwise reach another person's Targums.
        """
        try:
            folder = (home / name).resolve()
        except OSError:
            return None
        if home.resolve() not in folder.parents or not folder.is_dir():
            return None
        return folder

    def purge_departed(self) -> list[int]:
        """Delete for real anyone whose grace period is up: their rows, and their home.

        Called at start-up beside `empty_trash`, which is the same kind of promise — a
        deletion that waits, and then happens. `Store.purge` had nothing calling it, so
        "Delete account" ended the session and the grace period never ended anything.
        """
        if self.store is None:
            return []
        gone = self.store.purge()
        for person_id in gone:
            shutil.rmtree(self.out / f"p{person_id}", ignore_errors=True)
        return gone

    def empty_trash(self, days: int = TRASH_DAYS) -> list[str]:
        """Delete for real anything whose week is up. Called at start-up."""
        gone: list[str] = []
        cutoff = now() - days * 24 * 60 * 60 * 1000
        if not self.out.is_dir():
            return gone
        for home in self.out.iterdir():
            if not home.is_dir():
                continue
            for folder in home.iterdir():
                when = self.trashed_at(folder) if folder.is_dir() else 0
                if when and when < cutoff:
                    shutil.rmtree(folder, ignore_errors=True)
                    gone.append(folder.name)
        return gone

    def _reads_of(self, owner: int | None) -> set[str] | None:
        """Which languages a build's owner reads, or None where there is nobody to ask —
        a signed-out build on a machine somebody runs themselves."""
        return None if self.store is None else (self.store.reads(owner) or None)

    @staticmethod
    def targets(folder: Path) -> list[str]:
        """Which languages a targum can be read in, most complete first.

        A folder holds a translation per language it was built into, and the reader's
        picker offers them all. Anything that has to name one — buying the next chapter,
        asking for the meanings — asks here rather than assuming English.
        """
        from .models import Translation, read_artifact

        weight: dict[str, int] = {}
        for path in sorted((folder / "translations").glob("*.json")):
            translation = read_artifact(Translation, path)
            if translation is None:
                continue
            said = sum(1 for text in translation.segments.values() if text)
            code = translation.target_language
            weight[code] = max(weight.get(code, 0), said)
        return sorted(weight, key=lambda code: (-weight[code], code))

    @staticmethod
    def chapters(folder: Path, target: str = "") -> list[dict[str, Any]]:
        """Every chapter of a targum, and whether it has been translated.

        Derived from the artifacts rather than recorded anywhere: a chapter is ready when
        every one of its segments has a translation. A second place saying so would drift
        from the truth the first time a build died between writing them.

        `target` asks about one language. Without it the question is "is there anything to
        read here", which is what a shelf wants; with it, "is there anything to read here
        in Russian" — which is what buying the next chapter has to ask, or a book whose
        English runs to chapter nine would refuse to sell chapter two in Russian on the
        grounds that it already exists.
        """
        from .models import SegmentedDocument, Translation, read_artifact
        from .render.builder import split_sections

        segmented = read_artifact(SegmentedDocument, folder / "segments.json")
        if segmented is None:
            return []
        sections = split_sections(segmented)
        if len(sections) < 2:
            # One section is a targum, not a book. A tree of one is furniture.
            return []
        done: set[str] = set()
        for path in sorted((folder / "translations").glob("*.json")):
            translation = read_artifact(Translation, path)
            if translation is None:
                continue
            if target and translation.target_language != target:
                continue
            done |= {sid for sid, text in translation.segments.items() if text}
        return [
            {
                "number": section.number,
                "title": section.title,
                "file": section.filename,
                "sentences": len(section.segment_ids),
                "ready": bool(section.segment_ids) and all(s in done for s in section.segment_ids),
            }
            for section in sections
        ]

    #: What a text this reader added is, worked out from where it came from. A catalogue
    #: text says what it is itself; everything else has only its address to go on, and an
    #: address is enough for the one distinction that matters here — an article somebody
    #: pasted in this morning against a book.
    OWN_KINDS = (("http://", "article"), ("https://", "article"), ("sefaria:", "prose"))

    @staticmethod
    @lru_cache(maxsize=512)
    def _own_difficulty(path: str, changed: float, language: str) -> int:
        """How hard a text nobody catalogued is, counted the same way the catalogue is.

        Keyed on the file's own modification time, so a rebuilt text is recounted and an
        unchanged one is counted once for the life of the process. Reading a whole
        annotation is not free — a book's worth is megabytes — and the library page is
        drawn every time somebody opens it.
        """
        from .annotate.base import NOT_VOCABULARY
        from .annotate.frequency import FrequencyBands
        from .models import Annotation, read_artifact

        annotation = read_artifact(Annotation, Path(path))
        if annotation is None:
            return 0
        bands = FrequencyBands()
        code = language.split("-")[0].lower()
        if not bands.supports(code):
            return 0
        looked_up = total = 0
        seen: dict[str, int] = {}
        for tokens in annotation.tokens.values():
            for token in tokens:
                if token.pos in NOT_VOCABULARY:
                    continue
                band = seen.get(token.lemma)
                if band is None:
                    band = seen[token.lemma] = bands.band(token.lemma, code)
                total += 1
                looked_up += band >= 4
        return round(looked_up / total * 100) if total else 0

    def _shape(self, folder: Path, source: str, language: str, words: int) -> dict[str, Any]:
        """What this text is, for a library that sorts and filters by it.

        A catalogue text is described by the catalogue: those numbers are measured off
        the whole text by `scripts/measure_difficulty.py` and are better than anything
        that could be worked out here. Everything else is the reader's own.
        """
        from . import catalogue as catalogue_module

        entry = next((e for e in catalogue_module.CATALOGUE if e.source == source), None)
        if entry is not None:
            return {
                "kind": entry.kind.value,
                "register": entry.register.value,
                "difficulty": entry.difficulty,
                "minutes": entry.minutes,
                "entry": entry.id,
                "drawn": any(
                    (self.out / "thumbs" / (entry.id + suffix)).is_file() for suffix, _ in THUMBS
                ),
            }
        kind = "prose"
        for prefix, named in self.OWN_KINDS:
            if source.startswith(prefix):
                kind = named
                break
        annotation = folder / "annotation.json"
        difficulty = (
            self._own_difficulty(str(annotation), annotation.stat().st_mtime, language)
            if annotation.is_file()
            else 0
        )
        return {
            "kind": kind,
            "register": "biblical" if source.startswith("sefaria:") else "modern",
            "difficulty": difficulty,
            "minutes": max(1, round(words / 130)),
            "entry": "",
            "drawn": False,
        }

    def readers(self, home: Path, trashed: bool = False) -> list[dict[str, Any]]:
        """Everything built, newest first, with what the page needs to show progress."""
        found: list[dict[str, Any]] = []
        if not home.is_dir():
            return found
        for folder in home.iterdir():
            index = folder / "reader" / "index.html"
            if not index.is_file():
                continue
            when = self.trashed_at(folder)
            if bool(when) != trashed:
                continue
            title = folder.name
            language = ""
            content_hash = ""
            source = ""
            words = 0
            sections = len(list((folder / "reader").glob("sec-*.html"))) or 1
            chapters = self.chapters(folder)
            document = folder / "document.json"
            if document.is_file():
                try:
                    data = json.loads(document.read_text(encoding="utf-8"))
                    title = data.get("title") or title
                    language = data.get("language", "")
                    source = data.get("source", "")
                    words = sum(len(str(b.get("text", "")).split()) for b in data.get("blocks", []))
                    # The same identity the reader keeps its word list under, so the
                    # page can say how far through each text you are.
                    content_hash = data.get("content_hash", "")
                except json.JSONDecodeError:
                    pass
            found.append(
                {
                    "name": folder.name,
                    "title": title,
                    "language": language,
                    # And which languages it can be read *into*. A text built twice is
                    # one text with two translations, and a shelf that said only what
                    # language it was in could not tell a reader of two which of them
                    # this one would open in.
                    "targets": self.targets(folder),
                    "document": content_hash,
                    "words": words,
                    **self._shape(folder, source, language, words),
                    "sections": sections,
                    "chapters": chapters,
                    "readyChapters": sum(1 for c in chapters if c["ready"]),
                    "trashed": when,
                    # How long is left, so the page can say it rather than imply it.
                    "goesIn": max(0, TRASH_DAYS - (now() - when) // (24 * 60 * 60 * 1000))
                    if when
                    else 0,
                    "built": int(index.stat().st_mtime),
                }
            )
        found.sort(key=lambda reader: reader["built"], reverse=True)
        return found

    @staticmethod
    def can_draw() -> bool:
        """Whether this deployment has an image key. A page with none never offers."""
        from . import covers as covers_module

        return covers_module.ready()

    def prepare(self, job: Job) -> None:
        """Ingest and segment, which costs nothing, then price the rest."""
        try:
            builder = self._builder(job)
            # Priced for what the build will buy, which for a book is one chapter. The
            # cap then applies to a chapter, not to a novel — which is the difference
            # between "no books at all" and "no chapter over two dollars".
            plan = builder.plan(chapters=FIRST_CHAPTERS)
            job.title = plan.document.title or job.source
            job.language = plan.document.language
            job.segments = len(plan.segmented.segments) if plan.segmented else 0
            job.chapters = plan.chapters
            job.estimate = plan.estimated_cost
            # The progress bar counts what is being translated now, not the whole book.
            job.total = plan.buying or job.segments
            usable, _ = builder.provider.available()
            if builder.machine and not usable:
                # Checked here, not at the first API call. The estimate falls back to a
                # character count when there is no key, so without this the page quotes
                # a plausible price, takes the click, and only then fails.
                job.blocked = NO_KEY
            else:
                job.blocked = self.why_blocked(job.estimate)
            if not job.blocked and builder.gloss and plan.segmented is not None:
                # Glossing is priced from the real count of distinct dictionary forms,
                # which means lemmatizing first. Only worth the wait once the
                # translation itself has cleared the cap.
                job.stage = "looking up words"
                cost, job.lemmas = self._gloss_cost(builder, plan.segmented, plan.buying_segments)
                job.meanings = cost
                job.estimate += cost
                job.blocked = self.why_blocked(job.estimate)
            job.stage = "blocked" if job.blocked else "ready"
        except TargumError as error:
            job.error = f"{error.message} {error.hint or ''}".strip()
            job.stage = "failed"
        except Exception as error:  # a bad file should not take the server down
            job.error = str(error)
            job.stage = "failed"

    def claim(self, job: Job) -> str:
        """Check the budget and spend from it in one step.

        Two builds started at once would otherwise both see the same money left and
        both pass, which is exactly how a budget gets overrun.
        """
        if job.estimate > self.max_cost:
            return self.why_blocked(job.estimate)
        if self.store is not None:
            # One transaction decides and spends. It holds across processes as well as
            # threads, which the lock below never did.
            # An admin is not held to the per-account rails. They exist to stop a reader
            # running up somebody else's bill, and the person paying it is not that
            # reader. The box ceiling below is not waived: that one is the runaway guard,
            # and a loop at three in the morning does not care whose account it is on.
            admin = bool(job.admin)
            refused = self.store.claim(
                job.id,
                job.estimate,
                self.budget,
                self._since(),
                owner=job.owner,
                per_account=None if admin else self.account_budget,
                month_from=self._month_from(),
                per_month=None if admin else self.month_budget,
            )
            if not refused:
                return ""
            return self._out_of(refused)
        with self.lock:
            blocked = self.why_blocked(job.estimate)
            if not blocked:
                self._committed += job.estimate
            return blocked

    @staticmethod
    def _gloss_cost(
        builder: Build, segmented: SegmentedDocument, buying: list[Segment]
    ) -> tuple[float, int]:
        """What the word meanings will cost, for the chapters being bought.

        Two things this used to do to every text it priced, both of them over the whole
        book however little of it was being bought. It quoted for meanings the build
        would not look up yet — Altneuland's first chapter costs $0.21 to translate and
        was quoted $4.23 of meanings, which the cap then refused, so a long book could
        not be opened at all. And it lemmatised five thousand sentences inside the
        request that draws the card: forty-eight seconds of Stanza before the page could
        say anything.

        The count is worth returning rather than discarding: it is what lets the page say
        how long they will keep arriving for after the reader opens.
        """
        from .annotate import Annotator, biblical
        from .annotate.gloss import AnthropicGlosses, estimate, unique_lemmas, unpaid

        run = SegmentedDocument(
            document_hash=segmented.document_hash,
            language=segmented.language,
            segmenter=segmented.segmenter,
            segments=buying or segmented.segments,
        )
        # Deliberately not `builder.annotate`, which writes annotation.json: a file
        # covering one chapter, written under the whole document's name, would be reused
        # by the build that follows and leave every other chapter unmarked.
        try:
            annotation = Annotator(bands=biblical.for_source(builder.source)).annotate(run)
        except TargumError:
            # Word help is worth saying goodbye to out loud; it is not worth a card that
            # will not draw. The build itself says so when it gets there.
            return 0.0, 0
        glosser = AnthropicGlosses(builder.gloss_model or builder.model)
        # A lemma looked up for another text is already bought. Quoting for it again
        # prices work that is about to be free.
        owed = unpaid(
            unique_lemmas(annotation),
            segmented.language,
            builder.target_language,
            glosser.name,
            builder.cache,
        )
        return estimate(len(owed), glosser.model), len(owed)

    def run(self, job: Job) -> None:
        # Covers first: a cover job carries no source to ingest, and everything below
        # would try to read its folder name as a file.
        if job.options.get("cover"):
            return self.run_covers(job)
        # On the list, not on `chapter`: preparing a whole book sets no single chapter
        # number, and a falsy 0 sent this down the ordinary build path — which then tried
        # to ingest the folder name as though it were a file.
        if job.options.get("chapters"):
            return self.run_chapter(job)
        try:
            job.stage = "working"
            self.remember(job)
            builder = self._builder(job)
            builder.notify = lambda message: setattr(job, "message", message)

            def progress(done: int) -> None:
                job.done += done

            def ready(result: Result) -> None:  # noqa: D401
                # The page is watching for this and navigates as soon as it sees it.
                # Looking up word meanings carries on in this thread afterwards, into a
                # reader that is already open.
                job.reader = f"{result.out_dir.name}/reader/index.html"
                job.stage = "done"
                job.message = ""
                self.remember(job)
                self.tell(job)

            # One chapter. A book is bought as it is read; a text with no chapters is
            # translated whole, which the pipeline decides for itself.
            result = builder.run(on_progress=progress, on_ready=ready, chapters=FIRST_CHAPTERS)
            # The reservation becomes the receipt. Until this, the ledger held an
            # estimate and the budget was an approximation of itself.
            job.spent = result.spent.cost()
            self.settle(job)
            self.remember(job)
        except TargumError as error:
            self._blame(job, error.message)
        except Exception:
            # Whatever a library chose to say about itself is not a sentence for someone
            # who wanted to read a poem. The detail belongs in the terminal.
            traceback.print_exc()
            self._blame(
                job,
                "Something went wrong. The Terminal has the detail.",
            )

    def cover_plan(self, folder: Path, chapters: bool) -> tuple[Any, list[tuple[str, str]]]:
        """What this text is, and every image worth drawing for it.

        A catalogue text is drawn from what the catalogue says it is — its title, its
        author, the sentence describing it — and those covers are shared between readers,
        because the catalogue is the same catalogue for everyone. An upload has none of
        that, so its subject is its title and its opening lines, and the picture is filed
        under the reader's own folder name rather than a catalogue id: it belongs to one
        text on one shelf.

        Most chapters are left out. See `catalogue.names_something`: a hundred and fifty
        psalms are numbered rather than titled, and a number is not a subject anything
        could draw. Those fall back to the book's cover when they are asked for.
        """
        from . import catalogue as catalogue_module
        from .catalogue import chapter_prompt, cover_prompt, cover_prompt_for, names_something
        from .models import Document, read_artifact

        document = read_artifact(Document, folder / "document.json")
        if document is None:
            return None, []
        entry = catalogue_module.matching(document.source)
        where = self.out / "thumbs"
        if entry is None:
            # An upload's cover carries its owner as well as its name. `thumbs/` is one
            # directory for the whole box, and a folder name is unique only within one
            # shelf — `free_name` keeps two of a reader's own texts apart and knows
            # nothing of anybody else's. Filed under the bare name, two readers who each
            # upload something called "notes" share one file: the second is told it is
            # already drawn, and shown the first reader's picture of the first reader's
            # text. A catalogue cover stays unprefixed, because that one really is the
            # same picture for everyone.
            mine = Drawable(
                id=f"{folder.parent.name}-{folder.name}",
                source=document.source,
                title=document.title or folder.name,
                language=document.language,
            )
            if any((where / (mine.id + suffix)).is_file() for suffix, _ in THUMBS):
                return mine, []
            opening = document.blocks[0].text if document.blocks else ""
            return mine, [(mine.id, cover_prompt_for(mine.title, opening))]

        wanted: list[tuple[str, str]] = []
        if not any((where / (entry.id + suffix)).is_file() for suffix, _ in THUMBS):
            wanted.append((entry.id, cover_prompt(entry)))
        if chapters:
            for chapter in self.chapters(folder):
                title = str(chapter.get("title") or "")
                name = f"{entry.id}-c{int(chapter['number']):03d}"
                if not names_something(title, entry.title):
                    continue
                if any((where / (name + suffix)).is_file() for suffix, _ in THUMBS):
                    continue
                wanted.append((name, chapter_prompt(entry, title)))
        return entry, wanted

    def run_covers(self, job: Job) -> None:
        """Draw a book's cover, then the chapters that have something of their own.

        The cover is drawn first and handed to every chapter after it as a reference —
        which is what makes a set look like a set. A chapter is therefore never drawn
        before its book, and if the book's own cover fails there is nothing to match.
        """
        from . import covers as covers_module

        illustrator = covers_module.build()
        usable, detail = illustrator.available()
        if not usable:
            return self._blame(job, detail)

        where = self.out / "thumbs"
        plan: list[tuple[str, str]] = job.options.get("plan") or []
        entry_id = str(job.options.get("cover") or "")
        job.stage = "working"
        job.total = len(plan)
        self.remember(job)

        drawn = 0
        # The book's cover as it came back, full size, for its chapters to be drawn
        # against. What gets kept on disk is a 320px tile — plenty to look at and thin
        # enough for a page, but a poor thing to hand an image model as a reference.
        # Only for the length of this run: a chapter drawn later matches the tile.
        original: bytes | None = None

        def owed() -> float:
            """What the answers said it cost, or the reservation rate if they did not.

            An image is billed by tokens rather than by the picture, so `drawn × price`
            was a receipt only while the price was flat. The illustrator counts what came
            back; this falls through to the old arithmetic for one that cannot.
            """
            counted = float(getattr(illustrator, "spent", 0.0) or 0.0)
            return counted or drawn * illustrator.price

        try:
            for name, prompt in plan:
                job.message = "Drawing…"
                self.remember(job)
                reference = None
                if name != entry_id:
                    reference = original or next(
                        (
                            (where / (entry_id + suffix)).read_bytes()
                            for suffix, _ in THUMBS
                            if (where / (entry_id + suffix)).is_file()
                        ),
                        None,
                    )
                    if reference is None:
                        # Its book was never drawn, so there is nothing for this to look
                        # like. Skipping beats drawing an orphan that matches nothing.
                        continue
                where.mkdir(parents=True, exist_ok=True)
                drawing = illustrator.draw(prompt, reference)
                if name == entry_id:
                    original = drawing
                (where / f"{name}.webp").write_bytes(covers_module.shrink(drawing))
                drawn += 1
                job.done = drawn
                self.remember(job)
        except TargumError as error:
            job.spent = owed()
            self.settle(job)
            return self._blame(job, error.message)

        job.spent = owed()
        self.settle(job)
        job.stage = "done"
        job.message = ""
        self.remember(job)

    def run_chapter(self, job: Job) -> None:
        """Buy one more chapter of a book already on disk.

        Nothing is ingested or segmented again — those are done, they are free, and they
        are sitting in the folder. This translates one chapter and rewrites the reader
        around it, which is the whole of what asking for a chapter costs.
        """
        from .models import Annotation, Document, SegmentedDocument, Vocalization, glossaries_in
        from .models import read_artifact as read
        from .render import render as render_reader

        folder = (job.home or self.out) / str(job.options.get("folder") or "")
        document = read(Document, folder / "document.json")
        segmented = read(SegmentedDocument, folder / "segments.json")
        if document is None or segmented is None:
            return self._blame(job, "That one is no longer on disk.")

        builder = self._builder(job)
        builder._resolved_out = folder
        numbers = job.options.get("chapters") or []
        wanted = [
            segment
            for number in numbers
            for segment in builder.chapter_segments(segmented, int(number))
        ]
        if not wanted:
            return self._blame(job, "No such chapter.")

        job.stage = "working"
        job.total = len(wanted)
        self.remember(job)
        try:
            translation = builder.translate(
                segmented, lambda done: setattr(job, "done", job.done + done), only=wanted
            )
            # Every translation the folder holds, with the one just bought at the front.
            # Rendering from this chapter's alone rewrote the reader without the others —
            # so buying chapter two of a book somebody reads in two languages took the
            # other language off every chapter of it.
            pages = render_reader(
                document,
                segmented,
                [translation, *builder.already_here([translation])],
                folder / "reader",
                annotation=read(Annotation, folder / "annotation.json"),
                glossaries=glossaries_in(folder),
                vocalization=read(Vocalization, folder / "vocalization.json"),
                clean=False,
                covers=self.out / "thumbs",
                # The same narrowing `_builder` hands a whole build. Without it, buying
                # a chapter put back every language the reader had said they do not read.
                reads=sorted(self._reads_of(job.owner) or ()) or None,
            )
        except TargumError as error:
            return self._blame(job, error.message)
        except Exception:
            traceback.print_exc()
            return self._blame(job, "Something went wrong. The Terminal has the detail.")

        job.spent = builder.spent.cost()
        job.reader = f"{folder.name}/reader/{pages[0].name}"
        job.stage = "done"
        self.settle(job)
        self.remember(job)
        self.tell(job)

    def _blame(self, job: Job, message: str) -> None:
        """Record a failure, unless there is already a reader to show for the work.

        Everything after the reader opens is a bonus. Failing the job at that point
        would replace a book someone is reading with an error, and the page has stopped
        watching for one anyway.
        """
        if job.stage == "done":
            job.message = message
            self.remember(job)
            return
        job.error = message
        job.stage = "failed"
        # The money was committed when the build was claimed. A build that failed spent
        # little or none of it, and without this three failures in a row exhaust a
        # session budget that paid for nothing.
        # Not simply released: a build that failed part-way still paid for the batches
        # it got through, and the API said how much. Releasing the whole claim would
        # hand that money back to the budget as though it had never gone.
        if job.spent > 0:
            self.settle(job)
        else:
            self.release(job)
        self.remember(job)

    def _builder(self, job: Job) -> Build:
        options = job.options

        # What the catalogue says about this source, if it is one of ours. Read here
        # rather than taken from the request: the model decides what a build costs, and
        # one that arrived in a payload would be a way to spend somebody else's money.
        from . import catalogue as catalogue_module
        from .annotate.gloss import GLOSS_MODEL

        entry = catalogue_module.matching(job.source)
        return Build(
            job.source,
            target_language=options.get("to", "en"),
            source_language=options.get("from") or None,
            # Natural, always. The word-for-word style is a command line option:
            # anyone who wants it can say so there, and putting the choice on this
            # page cost more in confusion than it bought.
            style=Style.natural,
            # Sonnet, not the provider's Opus default. Measured, a Hebrew novel is
            # $12.64 on Opus against $7.58 on Sonnet, and the difference in a reader's
            # translation does not show up beside the difference in the bill. The CLI
            # keeps the provider default: that is somebody spending their own key.
            # Sonnet, unless the catalogue says this text's English was bought with
            # something else. The cache is keyed on the model, so a book we translated
            # once on Opus would be translated again — at a reader's expense — by a build
            # that quietly asked for Sonnet instead.
            model=(entry.model if entry and entry.model else HOSTED_MODEL),
            # Whose build this is, which scopes the cache for anything that is not a
            # public text. Without it one person's uploaded book would be translated
            # once and served to everyone who happened to upload the same file.
            owner=f"p{job.owner}" if job.owner else "",
            # Whose reader this will be, and so which languages it may offer. A build
            # into a language they do not read is refused before it starts; this is the
            # other end of it — a folder that already holds one stops showing it.
            reads=sorted(self._reads_of(job.owner) or ()) or None,
            out_root=job.home or self.out,
            gloss=bool(options.get("gloss")),
            # Meanings are bought on the hosted model whatever the prose was bought with:
            # the catalogue is translated on Opus, and its 25k lemmas are cached under
            # Sonnet. Quoting or buying them under Opus paid twice for the same words.
            gloss_model=GLOSS_MODEL,
            difficulty=bool(options.get("words")),
            # A catalogue text arrives with a translation somebody already made, so
            # nothing is asked of a model and nothing is spent.
            translations=[str(t) for t in options.get("translations") or []],
            # Ben Yehuda's plain-text downloads carry no title: the first line of the file
            # is the title and the author, as prose. Without this a book lands on somebody's
            # shelf called "6600".
            title=entry.title if entry else "",
        )


# The cookie the browser carries once somebody has signed in. Not `Secure`, because
# this build serves plain HTTP on loopback and a Secure cookie would simply never be
# sent; a hosted install serving HTTPS must add it.
SESSION_COOKIE = "targum_session"

# What the sign-in page says, whether or not the address has an account, and whether or
# not the mail went out. Anything more specific turns the form into a way of asking
# which addresses are registered here.
SENT = "Check your email."


class Handler(BaseHTTPRequestHandler):
    # Overridden on the type built in start(). Off here so a Handler made by hand —
    # which is how the tests make one — behaves like a machine somebody runs themselves.
    require_account = False

    server_version = "targum"
    hosts: frozenset[str] = frozenset(SAFE_HOSTS)
    library: Library
    token: str
    page: str
    adding: str
    progress: str
    catalogue: str
    you: str
    #: The three list pages, by route name: everything Learn shows the top of. Empty by
    #: default so a handler built with only the pages it needs — which is what the tests
    #: build — serves no list pages rather than failing on the way past them.
    lists: dict[str, str] = {}
    store: Store
    mailer: Mailer
    address: str

    def log_message(self, format: str, *args: Any) -> None:
        return  # the console belongs to the build output

    # -- plumbing -----------------------------------------------------------

    # -- who is asking ------------------------------------------------------

    def _cookie(self, name: str) -> str:
        """One cookie by name. `SimpleCookie` would do this, and would also raise on a
        cookie somebody else's extension left behind with a character it dislikes."""
        for part in (self.headers.get("Cookie") or "").split(";"):
            key, _, value = part.strip().partition("=")
            if key == name:
                return unquote(value)
        return ""

    def _person(self) -> Person | None:
        return self.store.whoever(self._cookie(SESSION_COOKIE) or None)

    def _reads(self, person: Person | None = None) -> set[str]:
        """Which languages to offer whoever is asking.

        Everything, where there is nobody to ask: signed out, or a machine somebody runs
        themselves, where the person choosing and the person paying are the same and the
        command line is right there anyway. The gate is about a hosted box handing an
        account a language nobody said that account reads.
        """
        from .translate.prompts import INTO

        everything = {code for code, _ in INTO}
        who = person if person is not None else self._person()
        if who is None:
            return everything
        return self.store.reads(who.id) & everything

    def _learning(self, person: Person | None = None) -> set[str]:
        """Which languages whoever is asking is learning. Everything where there is
        nobody to ask, for the reason `_reads` gives."""
        from .translate.prompts import READING

        everything = {code for code, _ in READING}
        who = person if person is not None else self._person()
        if who is None:
            return everything
        return self.store.learning(who.id) & everything

    def _needs_account(self, route: str) -> bool:
        """Whether this request has to be turned away at the door.

        Hosted, always. On a machine somebody runs themselves, only once an account
        exists on it — because until then "signed out" describes nobody. A fresh install
        opens and works with nothing to sign into, which is what the README promises and
        what the command line is for; the moment somebody signs up, signing out means
        what it means everywhere else.
        """
        if route in OPEN_TO_STRANGERS or self._person() is not None:
            return False
        return self.require_account or self.store.anyone()

    def _home(self) -> Path:
        """The only directory this request is allowed to see."""
        return self.library.home(self._person())

    def _own_job(self, job_id: str) -> Job | None:
        """A job, but only if it belongs to whoever is asking.

        Ids are unguessable, so this is not the only thing standing between two
        people's builds — but an id is a bearer token, and one that leaks through a
        log or a shared screen should not hand over someone else's text.
        """
        job = self.library.jobs.get(job_id)
        if job is None:
            return None
        person = self._person()
        return job if job.owner == (person.id if person else None) else None

    def _host_is_ours(self) -> bool:
        # A page on another origin resolving a name to this address should not be able
        # to drive the builder, whatever else it can prove.
        return (self.headers.get("Host") or "").rsplit(":", 1)[0] in self.hosts

    def _authorised(self) -> bool:
        if not self._host_is_ours():
            return False
        query = parse_qs(urlparse(self.path).query)
        given = query.get("k", [""])[0] or (self.headers.get("X-Targum-Key") or "")
        # `self.token` guards the comparison rather than only the value. Hosted the key
        # is the empty string, and `compare_digest("", "")` is True — so without this,
        # taking the key away would authorise every anonymous request instead of none.
        if self.token and secrets.compare_digest(given, self.token):
            return True
        # A signed-in session is a stronger claim than the start-up key, and it is the
        # one thing here that survives a restart. Before this, someone who had signed in
        # still met the stale-session page every time targum was restarted, which is the
        # opposite of what signing in is for.
        return self._person() is not None

    @staticmethod
    def _policy(body: bytes) -> str:
        """The content policy for one page, naming its own inline blocks by hash."""
        import base64
        import hashlib

        hashes: list[str] = []
        for block in re.findall(rb"<(?:script|style)[^>]*>(.*?)</(?:script|style)>", body, re.S):
            digested = base64.b64encode(hashlib.sha256(block).digest()).decode("ascii")
            hashes.append(f"'sha256-{digested}'")
        allowed = " ".join(dict.fromkeys(hashes))
        return f"{POLICY}; script-src {allowed}; style-src {allowed}"

    # A reader page is around 180 kB, most of it the same stylesheet and script every
    # other page carries, and gzip takes it to a third of that. In front of the deployed
    # server Caddy already does this, so this is for the copy running on a laptop, which
    # has nothing in front of it at all. Below a packet there is nothing to win.
    COMPRESSIBLE = ("text/html", "application/json", "text/plain", "image/svg+xml")
    COMPRESS_OVER = 1400

    def _worth_zipping(self, body: bytes, kind: str) -> bool:
        return (
            len(body) >= self.COMPRESS_OVER
            and kind.startswith(self.COMPRESSIBLE)
            and "gzip" in self.headers.get("Accept-Encoding", "")
        )

    def _send(self, status: int, body: bytes, kind: str, cache: str = "no-store") -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        # Read off the page as written. The policy names this page's own inline blocks
        # by their hash, so it has to be taken before the bytes are compressed.
        policy = self._policy(body) if kind.startswith("text/html") else None
        zipped = self._worth_zipping(body, kind)
        if zipped:
            body = gzip.compress(body, 6)
        self.send_header("Content-Length", str(len(body)))
        if zipped:
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Vary", "Accept-Encoding")
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if policy is not None:
            self.send_header("Content-Security-Policy", policy)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: Any, status: int = 200) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def _go(self, where: str, cookie: str | None = None) -> None:
        """Send them on, optionally handing over or taking back the session."""
        self.send_response(303)
        self.send_header("Location", where)
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    @staticmethod
    def _session_cookie(token: str, days: int) -> str:
        # HttpOnly so a script on the page cannot read it, SameSite=Lax so another site
        # cannot make the browser use it, Path=/ so the readers carry it too.
        return (
            f"{SESSION_COOKIE}={token}; HttpOnly; SameSite=Lax; Path=/; "
            f"Max-Age={days * 24 * 60 * 60}"
        )

    # -- routes -------------------------------------------------------------

    def _robots(self) -> str:
        """What a crawler may have.

        Everything public is public on purpose; everything else needs an account and
        would answer with the door anyway. Naming the private routes here keeps crawlers
        from spending their budget on pages that will never be worth an index entry.
        """
        if not shelves_are_public():
            # Every page a crawler could reach is the holding page. Letting it in now
            # means "Coming soon" is what ranks for targum later.
            return "User-agent: *\nDisallow: /\n"
        lines = [
            "User-agent: *",
            "Allow: /$",
            "Allow: /about",
            "Allow: /library",
            "Disallow: /account/",
            "Disallow: /reader/",
            "Disallow: /readers",
            "Disallow: /progress",
            "Disallow: /job/",
            "Disallow: /glossary/",
            "Disallow: /health",
        ]
        if self.address:
            lines.append(f"Sitemap: {self.address}/sitemap.xml")
        return "\n".join(lines) + "\n"

    def _sitemap(self) -> str:
        """Every public page, generated from the catalogue rather than kept by hand.

        A hand-maintained sitemap is one that is wrong the first time somebody adds an
        entry and forgets, and being wrong here is invisible until traffic does not
        arrive.
        """
        from . import catalogue as catalogue_module

        where = self.address or ""
        paths = ["/", "/about", "/library"]
        paths += [f"/library/{entry.id}" for entry in catalogue_module.CATALOGUE]
        urls = "".join(f"<url><loc>{where}{path}</loc></url>" for path in paths)
        return (
            f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'
        )

    def _measure(self, home: Path, readers: list[dict[str, Any]]) -> None:
        """Say how much of each targum the reader already knows.

        Added in place rather than returned, and silently skipped for anyone signed out or
        any text without word-level annotation — the page shows what it showed before
        rather than a zero, because "0% known" and "not measured" are very different
        claims to make about a book.

        One vocabulary query per language, not per text: a shelf of twenty Hebrew books
        asks once and measures all twenty against the answer.
        """
        person = self._person()
        if person is None:
            return
        from . import coverage as coverage_module

        vocabulary: dict[str, dict[str, int]] = {}
        for reader in readers:
            language = str(reader.get("language") or "")
            name = str(reader.get("name") or "")
            # The folder is resolved here rather than carried in the payload: an absolute
            # path on the server is not something a browser has any business being told.
            if not language or not name:
                continue
            if language not in vocabulary:
                vocabulary[language] = self.store.marked(person, language)
            measured = coverage_module.against(home / name, vocabulary[language])
            if measured is not None:
                reader.update(measured.state())

    def _health(self) -> None:
        """Whether the process is alive and can still reach the one file that matters.

        Behind the key and the account check, because the thing asking is a monitor
        rather than a reader — and behind the host check too, or anyone who resolves a
        name here could use it to find out the box exists. It touches the store on
        purpose: a process that is running with a database it can no longer read is the
        failure worth catching, and one that only answers "yes I am a process" would
        report that as healthy.
        """
        try:
            self.store.anyone()
        except Exception:
            return self._json({"ok": False, "store": False}, 503)
        self._json({"ok": True, "store": True, "queue": len(self.library.jobs)})

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        # No key, no account, no cookie: a monitor asks this every minute from off the
        # box, and A6 is "I find out it broke before she tells me".
        if route == "/health":
            return self._health()
        # The browser asks for this on every page load without being told to, and it
        # carries no key, so it would otherwise answer the stale-session page and put a
        # failed request in the console each time. Answered before the key check and
        # served for real: the monogram is public, and a tab with no icon is the one
        # place the identity is visibly missing.
        if route == "/favicon.ico":
            return self._send(200, _icon(), "image/png")
        if route == "/robots.txt":
            return self._send(200, self._robots().encode("utf-8"), "text/plain; charset=utf-8")
        if route == "/sitemap.xml":
            if not shelves_are_public():
                return self._send(404, b"not found", "text/plain")
            return self._send(200, self._sitemap().encode("utf-8"), "application/xml")
        # A text's own page. It carries a sample rather than the whole text, so there is
        # nothing here to protect — but it stays shut with the rest until the catalogue
        # is opened, because a shop window onto an empty shop is not worth having.
        naming = PUBLIC_TEXT.match(route) if shelves_are_public() else None
        if naming is not None:
            from . import catalogue as catalogue_module

            entry = catalogue_module.by_id(naming.group(1))
            if entry is None:
                return self._send(404, b"not found", "text/plain")
            return self._send(200, text_page(entry, self.address).encode("utf-8"), HTML)
        # The shelves answer to whoever is asking. Signed out that is the public index —
        # the shop window, and the thing a search engine indexes. Signed in it is the
        # product. Same address either way, because a text somebody found on Google
        # should still be there after they sign in to read it.
        if route == "/library":
            if self._person() is None and not self._authorised():
                if not shelves_are_public():
                    return self._send(200, holding_page().encode("utf-8"), HTML)
                page = shelf_page(self.address)
                return self._send(200, page.encode("utf-8"), HTML)

        if self._needs_account(route):
            # Data routes answer as data. Anything a person could be looking at gets a
            # page rather than a 401 — and not the sign-in page either, because a door
            # shown to somebody with no key is a wall that looks like a mistake. The
            # door is one click away, in the corner.
            if route.startswith(("/readers", "/job/", "/jobs", "/glossary/", "/account/export")):
                return self._json({"error": "Sign in first.", "signIn": "/account/signin"}, 401)
            return self._send(200, holding_page().encode("utf-8"), HTML)
        # The one route that needs no key: it carries a single-use token of its own,
        # which is a stronger claim than the key it would otherwise be asked for. It
        # has to work from a mail client, hours later, possibly after a restart.
        if route == "/about":
            return self._send(200, about_page().encode("utf-8"), HTML)
        if route == "/account/signin":
            return self._send(200, signin_page().encode("utf-8"), HTML)
        if route == "/account/enter":
            # Exempt from the key, never from the host check: a page on another origin
            # that resolves a name to this address still gets nothing.
            if not self._host_is_ours():
                return self._send(404, b"not found", "text/plain")
            # A page, not a sign-in. A mail client that fetches links to preview them
            # spends nothing here; the button below posts, and that is what signs in.
            token = parse_qs(urlparse(self.path).query).get("t", [""])[0]
            person = self.store.peek_sign_in(token) if token else None
            if person is None:
                return self._send(200, signin_page(expired=True).encode("utf-8"), HTML)
            page = signin_page(landing=person.email, token=token)
            return self._send(200, page.encode("utf-8"), HTML)
        if not self._authorised():
            return self._send(403, STALE.encode("utf-8"), "text/html; charset=utf-8")
        if route.startswith("/reader/"):
            return self._serve_reader(route[len("/reader/") :])
        if route.startswith("/thumb/"):
            return self._serve_thumb(route[len("/thumb/") :])
        if route == "/":
            return self._send(200, self.page.encode("utf-8"), "text/html; charset=utf-8")
        if route == "/add":
            return self._send(200, self.adding.encode("utf-8"), "text/html; charset=utf-8")
        if route == "/progress":
            return self._send(200, self.progress.encode("utf-8"), "text/html; charset=utf-8")
        # Learn holds the top of each of these; this is the rest. `/words` was a redirect
        # to the progress page for a while, from when the word list lived there — an old
        # tab pointing here now lands on the word list itself, which is what it wanted.
        if route.lstrip("/") in self.lists:
            page = self.lists[route.lstrip("/")]
            return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        if route == "/library":
            return self._send(200, self.catalogue.encode("utf-8"), "text/html; charset=utf-8")
        if route == "/you":
            return self._send(200, self.you.encode("utf-8"), "text/html; charset=utf-8")
        if route == "/readers":
            # Not "/library": that name belongs to the page a person opens.
            home = self._home()
            mine = self.library.readers(home)
            self._measure(home, mine)
            # And the shared one, measured against this reader's words like their own.
            # The page shows it only to a reader with nothing of their own in that
            # language: it is where to start, not another row on a full shelf.
            shared = self.library.readers(self.library.shared)
            for reader in shared:
                reader["shared"] = True
            self._measure(self.library.shared, shared)
            return self._json(
                {
                    "readers": mine,
                    "shared": shared,
                    "trash": self.library.readers(home, trashed=True),
                    # Whether this deployment can draw a cover at all. A page with no
                    # image key offers nothing rather than offering and failing.
                    "covers": self.library.can_draw(),
                }
            )
        if route == "/account/me":
            return self._me()
        if route == "/account/export":
            # Everything the account holds, for somebody who wants to take it away. A
            # download rather than a page: the point of this is that it needs nobody's
            # help, and a wall of JSON in a browser tab is not a thing anybody can keep.
            person = self._person()
            if person is None:
                return self._json({"error": "Sign in first."}, 401)
            body = json.dumps(self.store.everything(person), ensure_ascii=False, indent=1).encode(
                "utf-8"
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="targum.json"')
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return None
        if route.startswith("/glossary/"):
            return self._serve_glossary(route[len("/glossary/") :])
        if route == "/jobs":
            # Every build of yours that is running, waiting, or lately finished. The id
            # of a build used to live only in the page that started it, so leaving that
            # page made the build look cancelled — it was not, but nothing could find it.
            person = self._person()
            return self._json({"jobs": self.library.mine(person.id if person else None)})
        if route.startswith("/job/"):
            job = self._own_job(route[len("/job/") :])
            return self._json(
                job.state()
                if job
                else {"error": "That build was lost when targum restarted. Start it again."}
            )
        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if not self._host_is_ours():
            return self._json({"error": "not found"}, 404)
        # Asking for a sign-in link is how somebody with an expired tab gets back in, so
        # it cannot be behind the key that expired. It is still loopback-only, it says
        # the same thing whatever address it is given, and all it can cause is one email
        # to an address the asker typed themselves.
        if route == "/account/enter":
            return self._enter(self._form().get("t", ""))
        if self._needs_account(route):
            return self._json({"error": "Sign in first.", "signIn": "/account/signin"}, 401)
        if route != "/account/sign-in" and not self._authorised():
            return self._json(
                {"error": "This page is from an earlier session. Open the Terminal link."},
                403,
            )
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            return self._json(
                {"error": f"That file is over {MAX_FILE_MB} MB. Try a single part of it."}, 413
            )
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad request"}, 400)

        if route == "/prepare":
            return self._prepare(payload)
        if route == "/build":
            return self._build(payload)
        if route == "/gloss":
            return self._gloss_word(payload)
        if route == "/chapter":
            return self._chapter(payload)
        if route == "/cover":
            return self._cover(payload)
        if route == "/jobs/watch":
            return self._watch_job(payload)
        if route == "/trash":
            return self._trash(payload)
        if route == "/restore":
            return self._restore(payload)
        if route == "/account/sign-in":
            return self._sign_in(payload)
        if route == "/account/sign-out":
            return self._sign_out()
        if route == "/account/forget":
            return self._forget()
        if route == "/sync":
            return self._sync(payload)
        if route == "/account/name":
            return self._rename(payload)
        if route == "/account/languages":
            return self._languages(payload)
        self._json({"error": "not found"}, 404)

    # -- accounts -----------------------------------------------------------

    def _me(self) -> None:
        person = self._person()
        if person is None:
            return self._json({"signedIn": False})
        answer = {
            "signedIn": True,
            "email": person.email,
            "revision": self.store.revision(person),
            "counts": self.store.counts(person),
            # Which languages this account is learning, and which it is offered a
            # translation into. The pages that offer either narrow to these; `_prepare`
            # refuses anything else whatever a picker was showing, because a picker is
            # not a boundary.
            "learning": sorted(self._learning(person)),
            "reads": sorted(self._reads(person)),
        }
        answer.update(self.store.profile(person))
        self._json(answer)

    def _rename(self, payload: dict[str, Any]) -> None:
        """What to call them. Empty clears it, and the avatar goes back to the address."""
        person = self._person()
        if person is None:
            return self._json({"signedIn": False}, 401)
        stored = self.store.rename(person, str(payload.get("name") or ""))
        answer = {"signedIn": True, "name": stored}
        answer.update(self.store.profile(person))
        self._json(answer)

    def _languages(self, payload: dict[str, Any]) -> None:
        """What they are learning and what they read into, from the profile page.

        Both lists at once, replaced whole: a form that submits a set of ticks is
        saying what the set is, not what changed. Refused whole too — a request that
        fails on one list leaves the other as it was, so the page can put its boxes
        back from the answer.
        """
        person = self._person()
        if person is None:
            return self._json({"signedIn": False}, 401)
        before = self._reads(person)
        try:
            learning = self.store.choose(person, "learning", list(payload.get("learning") or []))
            reads = self.store.choose(person, "reading", list(payload.get("reads") or []))
        except ValueError as error:
            return self._json(
                {
                    "error": str(error),
                    "learning": sorted(self._learning(person)),
                    "reads": sorted(self._reads(person)),
                },
                400,
            )
        # A reader is a file, and a language taken away only leaves one when the file is
        # written again. Adding one never needs this: a translation is only in a folder
        # if it was bought, and buying writes the reader. Off this thread, because a
        # home full of long books is seconds of work and the page is waiting.
        if before - reads:
            from .cli import rebuild_home

            home = self.library.home(person)
            threading.Thread(
                target=rebuild_home,
                args=(home,),
                kwargs={"reads": sorted(reads)},
                daemon=True,
            ).start()
        answer = {"signedIn": True, "learning": sorted(learning), "reads": sorted(reads)}
        answer.update(self.store.profile(person))
        self._json(answer)

    def _form(self) -> dict[str, str]:
        """A form post, read as a form. The landing page is a page, not an app."""
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > 8192:
            return {}
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        return {key: values[0] for key, values in parse_qs(body).items() if values}

    def _sign_in(self, payload: dict[str, Any]) -> None:
        email = str(payload.get("email") or "")
        if not plausible(email):
            return self._json({"error": "That does not look like an email address."}, 400)
        # Hosted, an address has to have been invited. Without this, standing a box up
        # on a public address with a funded key lets whoever finds it open an account and
        # start spending — held back only by a per-account rail that is $3.00 a *day*,
        # which is a rate limit and not a plan limit.
        #
        # Said plainly rather than answered with a silent "check your email". That does
        # tell an asker whether an address is on the list, and for an alpha of a handful
        # of people the confusion of a link that never arrives costs more than the
        # enumeration is worth. Revisit when the list is long enough to be worth probing.
        if self.require_account and not self.store.may_join(email):
            return self._json({"error": NOT_OPEN}, 403)
        if self.store.asking_too_often(email):
            return self._json(
                {"error": "Too many links to that address. Check your spam folder."},
                429,
            )
        token = self.store.start_sign_in(email)
        link = f"{self.address}/account/enter?t={token}"
        try:
            self.mailer.send(email, link)
        except Exception:
            # Said plainly, because a link that never arrives with a cheerful "check
            # your email" is the worst version of this failing.
            return self._json({"error": "The link could not be sent."}, 502)
        self._json({"sent": True, "message": SENT})

    def _enter(self, token: str) -> None:
        got = self.store.finish_sign_in(token) if token else None
        if got is None:
            # Not an error: a spent or stale link is what a second press looks like,
            # and the way out of it is to ask for another, which that page offers.
            return self._send(200, signin_page(expired=True).encode("utf-8"), HTML)
        _, session = got
        from .accounts import SESSION_DAYS

        where = f"/?k={self.token}&signin=welcome" if self.token else "/?signin=welcome"
        self._go(where, self._session_cookie(session, SESSION_DAYS))

    def _sign_out(self) -> None:
        self.store.sign_out(self._cookie(SESSION_COOKIE) or None)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header(
            "Set-Cookie", f"{SESSION_COOKIE}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0"
        )
        body = json.dumps({"signedIn": False}).encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _forget(self) -> None:
        person = self._person()
        if person is None:
            return self._json({"error": "Nobody is signed in."}, 401)
        self.store.forget(person)
        self._sign_out()

    def _sync(self, payload: dict[str, Any]) -> None:
        """Take what the browser has, hand back what it is missing.

        Push and pull in one call rather than two, because they are one act: a browser
        that pushed and then failed to pull is a browser showing stale data it just
        contributed to. The pull uses the revision the client came in with, so a push
        does not echo straight back at whoever made it.
        """
        person = self._person()
        if person is None:
            return self._json({"signedIn": False}, 401)
        try:
            since = int(payload.get("since") or 0)
        except (TypeError, ValueError):
            since = 0
        # An allowlist of kinds, and every row filtered down to the dicts. The list check
        # alone let `{"words": ["nonsense"]}` through to the merge, which calls .get on
        # each row and raised on a string — a signed-in reader breaking their own sync
        # rather than a hole, but a 500 where a quiet skip belongs.
        changes = {
            name: [row for row in payload[name] if isinstance(row, dict)]
            for name in ("words", "meanings", "phrases", "docs", "days")
            if isinstance(payload.get(name), list)
        }
        if changes:
            self.store.push(person, changes)
        # The counts go back with the answer because the page asked for them before it
        # pushed, and a panel that says "nothing kept yet" to somebody who has just had
        # eight hundred words claimed is worse than saying nothing at all.
        answer = {"signedIn": True, "counts": self.store.counts(person)}
        answer.update(self.store.pull(person, since))
        self._json(answer)

    def _prepare(self, payload: dict[str, Any]) -> None:
        """Price a build, and say what it will take before anything is spent."""
        from .translate.prompts import INTO, READING, language_name

        # A picker is not a boundary. The page offers three languages in and two out
        # because those are the pairs an upload has been taken end to end in; a request
        # naming anything else is refused here rather than half-built.
        wanted = str(payload.get("to") or "en")
        if wanted not in {code for code, _ in INTO}:
            offered = ", ".join(language_name(code) for code, _ in INTO)
            return self._json({"error": f"targum translates into {offered}."}, 400)
        # And of those, the ones this account reads. Buying a translation into a language
        # nobody said they read spends money on a page they cannot use — and every word
        # they keep from it carries a meaning in it into every text they own. The
        # sentence names where to change that, because it is theirs to change now.
        if wanted not in self._reads():
            return self._json({"error": f"{language_name(wanted)} is not in your profile."}, 400)
        # `from` is allowed to be empty: that means work it out from the text. A catalogue
        # text names its own language and is not somebody's upload, so it is let past.
        reading = str(payload.get("from") or "")
        known = {code for code, _ in READING}
        if reading and reading not in known and not payload.get("translations"):
            from . import catalogue as catalogue_module

            if catalogue_module.matching(str(payload.get("source") or "")) is None:
                names = ", ".join(language_name(code) for code, _ in READING)
                return self._json({"error": f"targum reads {names}."}, 400)
        # And of those, the ones this account said it is learning.
        if reading in known and reading not in self._learning():
            return self._json({"error": f"{language_name(reading)} is not in your profile."}, 400)

        try:
            source = self._source_from(payload)
            # A reader's own translation is a file like the source is, and it is written
            # down here so the price — and then the build — is worked out with it in hand.
            mine = self._translation_from(payload)
        except TargumError as error:
            return self._json({"error": error.message}, 400)
        if mine:
            payload = dict(payload, translations=mine)

        # Somebody has already translated this one, and that translation is better and
        # free. Said before anything is priced, not after it has been paid for.
        #
        # Only where there is something better to offer, though. Half the catalogue is
        # texts nobody published an English for, which targum translated once and paid for
        # once — those have no `Rendering` to point at, and offering one as an alternative
        # to itself would leave the catalogue's own button unable to build them.
        if not payload.get("translations") and not payload.get("force_machine"):
            from . import catalogue as catalogue_module

            already = catalogue_module.matching(source)
            if already is not None and already.translations:
                return self._json({"catalogue": already.state()})

        person = self._person()
        job = Job(
            id=secrets.token_hex(8),
            source=source,
            options=payload,
            owner=person.id if person else None,
            admin=bool(person and person.admin),
            home=self.library.home(person),
        )
        self.library.jobs[job.id] = job
        self.library.remember(job)
        self.library.prepare(job)
        self.library.remember(job)
        self._json(job.state())

    def _build(self, payload: dict[str, Any]) -> None:
        job = self._own_job(str(payload.get("id", "")))
        if job is None:
            return self._json(
                {
                    "error": "That build was lost when targum restarted. Start it again; "
                    "nothing is paid for twice."
                },
                404,
            )
        if job.stage in {"working", "done"}:
            return self._json(job.state())
        blocked = self.library.claim(job)
        if blocked:
            job.blocked = blocked
            job.stage = "blocked"
            return self._json(job.state(), 402)
        self.library.enqueue(job)
        self._json(job.state())

    def _cover(self, payload: dict[str, Any]) -> None:
        """Draw the covers for one text, from the key this deployment runs with.

        Priced and claimed against the same budget as everything else that costs money,
        and refused by the same sentences when there is none left. A reader is never
        shown the number — see the guidelines on what the product says about cost — but
        the ceiling is real and this is inside it.
        """
        from . import covers as covers_module

        home = self._home()
        folder = self.library.within(home, str(payload.get("name") or ""))
        if folder is None:
            return self._json({"error": "not found"}, 404)

        illustrator = covers_module.build()
        usable, detail = illustrator.available()
        if not usable:
            return self._json({"error": detail}, 400)

        entry, plan = self.library.cover_plan(folder, bool(payload.get("chapters")))
        if entry is None:
            return self._json({"error": "There is nothing here to draw."}, 400)
        if not plan:
            return self._json({"drawn": 0, "message": "Already drawn."})

        person = self._person()
        job = Job(
            id=secrets.token_hex(8),
            source=entry.source,
            title=entry.title,
            language=entry.language,
            owner=person.id if person else None,
            admin=bool(person and person.admin),
            home=home,
            options={"cover": entry.id, "plan": plan, "chapters": bool(payload.get("chapters"))},
            estimate=len(plan) * illustrator.price,
            total=len(plan),
        )
        blocked = self.library.claim(job)
        if blocked:
            return self._json({"error": blocked}, 400)
        self.library.jobs[job.id] = job
        self.library.enqueue(job)
        self._json(job.state())

    def _chapter(self, payload: dict[str, Any]) -> None:
        """Translate one chapter of a targum already on disk, and rewrite its page.

        A book is bought a chapter at a time. This is the asking — from the contents
        page, from the end of the one before, or from a reader who wants chapter nine.
        """
        home = self._home()
        folder = self.library.within(home, str(payload.get("name") or ""))
        if folder is None:
            return self._json({"error": "not found"}, 404)
        # `number` names one chapter; `all` buys every one still waiting. The second is
        # for somebody about to lose their connection, which is the one case where the
        # whole book at once is what a reader actually wants.
        whole = bool(payload.get("all"))
        try:
            number = 0 if whole else int(payload.get("number") or 0)
        except (TypeError, ValueError):
            return self._json({"error": "not found"}, 404)
        # What is already here, whichever way it was asked for. `all` had this check and
        # one chapter did not, so the reader's prefetch — which asks for the next chapter
        # at 60% of this one, every time, knowing nothing about what is on disk — bought
        # a chapter of Song of Songs that the published translation already covered.
        # A catalogue text is free and arrives complete, so every one of its chapters is
        # ready from the start and every prefetch against it was a purchase waiting to
        # happen. Readiness is derived from the artifacts by `chapters()`, so this asks
        # the only thing that can answer it.
        # Which language to buy it in. The reader asks in the one it is showing; without
        # that this fell through to English, so the second chapter of a Russian book came
        # back in English — and `run_chapter` then rebuilt the whole reader around it.
        #
        # Checked against what the folder already holds rather than taken at its word: a
        # prefetch nobody pressed must not be able to buy a language nobody asked for.
        here = self.library.targets(folder)
        wanted = str(payload.get("to") or "").strip()
        target = wanted if wanted in here else (here[0] if here else "en")
        standing = self.library.chapters(folder, target)
        waiting: list[int] = []
        if whole:
            waiting = [c["number"] for c in standing if not c["ready"]]
            if not waiting:
                return self._json({"ready": True})
        elif any(c["number"] == number and c["ready"] for c in standing):
            return self._json({"ready": True})

        person = self._person()
        job = Job(
            id=secrets.token_hex(8),
            source=str(folder),
            options={
                "chapters": waiting if whole else [number],
                "folder": folder.name,
                "to": target,
            },
            owner=person.id if person else None,
            admin=bool(person and person.admin),
            home=home,
        )
        blocked = self.library.already_over(job)
        if blocked:
            job.blocked = blocked
            job.stage = "blocked"
            return self._json(job.state(), 402)
        self.library.jobs[job.id] = job
        self.library.remember(job)
        self.library.enqueue(job)
        self._json(job.state())

    def _watch_job(self, payload: dict[str, Any]) -> None:
        """The reader put the strip away: tell them by email instead, however short the
        build. A promise made on the page is kept whatever the clock says."""
        job = self._own_job(str(payload.get("id") or ""))
        if job is None:
            return self._json({"error": "not found"}, 404)
        finished = job.stage in ("done", "failed", "blocked")
        watching = self.library.can_mail(job.owner) and not finished
        if watching:
            job.options["mail"] = True
            self.library.remember(job)
        self._json({"watching": watching})

    def _trash(self, payload: dict[str, Any]) -> None:
        name = str(payload.get("name") or "")
        if not self.library.trash(self._home(), name):
            return self._json({"error": "not found"}, 404)
        self._json({"trashed": True, "days": TRASH_DAYS})

    def _restore(self, payload: dict[str, Any]) -> None:
        name = str(payload.get("name") or "")
        if not self.library.restore(self._home(), name):
            return self._json({"error": "not found"}, 404)
        self._json({"restored": True})

    def _gloss_word(self, payload: dict[str, Any]) -> None:
        """One word, because a reader asked for it.

        A whole-text glossary is bought before anything is read and most of it never
        is. This is the other way round: nothing is looked up until you want it, and
        what you look up is cached, so the same word is free everywhere after that.
        """
        lemma = str(payload.get("lemma", "")).strip()
        source = str(payload.get("source", "")).strip()
        target = str(payload.get("target", "en")).strip() or "en"
        # The sentence it was tapped in, which is what tells עם from עם. Capped: a
        # sentence is what this is for, and a paragraph is what a page could send.
        sentence = str(payload.get("sentence", "")).strip()[:400]
        if not lemma or not source:
            return self._json({"error": "bad request"}, 400)

        from .annotate.gloss import GLOSS_MODEL, AnthropicGlosses, cached_gloss, gloss_one

        # The same model the build's own glossary was bought with. The provider's name
        # is part of the cache key, so asking here with the provider's default — Opus,
        # where a hosted build uses Sonnet — made every word the build had already paid
        # for cost a second time, on the dearer of the two, the moment a reader tapped
        # it. Bought once, free everywhere is the claim; this is what makes it true.
        provider = AnthropicGlosses(GLOSS_MODEL)
        if payload.get("free"):
            # A card opening asks this first: is the meaning already held? Answered from
            # the cache and never bought, so a page can ask for every word it shows.
            meaning = cached_gloss(lemma, source, target, provider.name)
            return self._json({"lemma": lemma, "meaning": meaning or None, "cached": bool(meaning)})
        usable, _ = provider.available()
        if not usable:
            return self._json({"error": NO_KEY}, 402)
        try:
            meaning = gloss_one(lemma, source, target, provider, context=sentence)
        except TargumError as error:
            return self._json({"error": error.message}, 502)
        except Exception:
            traceback.print_exc()
            return self._json({"error": "Could not look that word up just now."}, 502)
        return self._json({"lemma": lemma, "meaning": meaning})

    #: What a text or a translation may arrive as. An epub is a book; the rest is text.
    READABLE = frozenset({".txt", ".md", ".markdown", ".epub"})

    def _written(self, name: str, content: str) -> Path:
        """One uploaded file on disk, under a directory nothing else will land in.

        A directory of its own per upload. Two people — or one person twice — dropping
        files with the same name used to overwrite each other, because the basename was
        the whole path.
        """
        suffix = Path(name).suffix.lower()
        if suffix not in self.READABLE:
            raise TargumError(
                f"targum cannot read '{suffix}' files. Save it as plain text or "
                "markdown and drop that in instead."
            )
        uploads = self._home() / "uploads" / secrets.token_hex(8)
        uploads.mkdir(parents=True, exist_ok=True)
        # Only the file's own name, never a path it carries.
        path = uploads / Path(name).name
        path.write_bytes(base64.b64decode(content))
        return path

    def _source_from(self, payload: dict[str, Any]) -> str:
        """A dropped file is written next to the readers; anything else is a source."""
        name = payload.get("name")
        content = payload.get("content")
        if name and content:
            return str(self._written(str(name), str(content)))

        source = str(payload.get("source", "")).strip()
        if not source:
            raise TargumError("Paste a link, drop a file, or give a Gutenberg or Wikisource id.")
        return source

    def _translation_from(self, payload: dict[str, Any]) -> list[str]:
        """A translation the reader already has, written down for the aligner.

        Supplying one is what makes a build free: the pipeline pays for a machine
        translation only when nothing else was handed to it. What comes back goes into
        the job's options, where `Build` reads it — and it goes in on the way past the
        door rather than out of the request, so nothing can name a file it did not
        upload.
        """
        name = payload.get("translationName")
        content = payload.get("translationContent")
        if not (name and content):
            return []
        return [str(self._written(str(name), str(content)))]

    def _serve_glossary(self, folder: str) -> None:
        """The word meanings for one build and one target language, once they exist.

        A reader opens before these are looked up, so it asks for them afterwards and
        fills them in without a reload. Answering "not yet" is a normal reply, not an
        error: the file appears when the lookups finish.

        `?to=` names the language, and the answer says which language it is answering
        about. A reader holding two translations polls for the one it is showing, and a
        reply that arrived after the reader switched has to be fileable rather than
        guessable — a meaning is only ever right about the pair it was written for.
        """
        from .translate.prompts import INTO

        wanted = parse_qs(urlparse(self.path).query).get("to", ["en"])[0]
        # An allowlist rather than a pattern, because this decides a filename. The
        # containment check below is the second lock, not the only one.
        if wanted not in {code for code, _ in INTO}:
            return self._json({"error": "not found"}, 404)
        root = self._home().resolve()
        home = (root / unquote(folder)).resolve()
        target = glossary_path(home, wanted).resolve()
        # English before the files carried a language in the name. Nothing is renamed;
        # the old name is simply still a place a glossary can be.
        if not target.is_file() and wanted == "en":
            target = (home / "glossary.json").resolve()
        if root not in target.parents:
            return self._json({"error": "not found"}, 404)
        if not target.is_file():
            return self._json({"ready": False, "target": wanted})
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Caught mid-write. The reader is still polling; it will ask again.
            return self._json({"ready": False, "target": wanted})
        entries = data.get("entries")
        if not isinstance(entries, dict):
            return self._json({"ready": False, "target": wanted})
        self._json({"ready": True, "target": wanted, "entries": entries})

    def _serve_thumb(self, name: str) -> None:
        """The cover drawn for one text, where somebody has made one.

        Missing is the ordinary case and not an error: the library draws the text's own
        first letter until an image exists, so a library with no covers at all looks
        deliberate rather than broken. See `scripts/thumbnails.py` for where they come
        from and `catalogue.cover_prompt` for what they are asked to be.

        A chapter falls back to its book. Most chapters in this library are numbered
        rather than titled — a hundred and fifty psalms — and a number is not a subject
        anything could draw, so only chapters that name something get their own image.
        The rest show the book's, which is both free and exactly as consistent with it as
        a reader could ask for.
        """
        root = (self.library.out / "thumbs").resolve()
        wanted = unquote(name)
        if OWNED.match(wanted):
            # An upload's cover is asked for by the text's own name; the home in front
            # of it is put there below, from whoever is asking. A name that arrives
            # already carrying one is asking for another reader's, and the fact that
            # `thumbs/` is one directory for the whole box is what would answer.
            return self._send(404, b"not found", "text/plain")
        # The asker's own first, so a reader who called an upload "genesis" gets their
        # own picture rather than the catalogue's. A chapter falls back to its book, and
        # both halves of that are tried the same way round.
        mine = self._home().name
        chapterless = re.sub(r"-c\d+$", "", wanted)
        for candidate in (f"{mine}-{wanted}", wanted, f"{mine}-{chapterless}", chapterless):
            for suffix, kind in THUMBS:
                target = (root / (candidate + suffix)).resolve()
                if root not in target.parents or not target.is_file():
                    continue
                # The one thing here worth a browser keeping. Everything else this
                # server sends is somebody's reading — no-store, and rightly. A cover is
                # a picture of a book, the same picture for every reader, and refetching
                # it on every visit to the library is the whole page's weight again.
                # Private rather than public: it still travelled a signed-in connection.
                return self._send(200, target.read_bytes(), kind, cache="private, max-age=86400")
        return self._send(404, b"not found", "text/plain")

    def _serve_reader(self, relative: str) -> None:
        """This person's readers, and the shared ones — never another person's.

        Two roots, each guarded on its own: the file has to resolve to *inside* the
        root it was looked for under. The shared home is a second allowed root, not a
        relaxation of the first, and the person's own wins where a name is in both.
        """
        for root in (self._home().resolve(), self.library.shared.resolve()):
            target = (root / unquote(relative)).resolve()
            if target.is_file() and root in target.parents:
                kind = "text/html; charset=utf-8" if target.suffix == ".html" else "text/plain"
                return self._send(200, target.read_bytes(), kind)
        return self._send(404, b"not found", "text/plain")


def default_store() -> Path:
    """Where a word list lives, which is deliberately not where the readers live.

    Readers are rebuildable and take up room, so `targum-out` is a directory somebody
    will reasonably delete one day. A vocabulary is the one thing here that cannot be
    rebuilt from anything, so it sits outside, in the home directory, and survives.
    """
    return Path.home() / ".targum" / "targum.db"


def start(
    out: Path,
    port: int = 8420,
    open_browser: bool = True,
    max_cost: float = MAX_COST,
    budget: float = SESSION_BUDGET,
    store: Path | None = None,
    mailer: Mailer | None = None,
    announce: Callable[[str], None] | None = None,
    require_account: bool = False,
    public_address: str = "",
) -> str:
    """Run until interrupted. Returns the address it is listening on."""
    from .mail import from_environment
    from .render.builder import (
        LISTS,
        add_page,
        learn_page,
        library_page,
        list_page,
        progress_page,
        you_page,
    )
    from .translate.anthropic_provider import AnthropicProvider

    # The start-up key is a single-user mechanism: it proves you can read the terminal
    # this process was started from, which is the same as proving you are the person
    # sitting at the machine. Hosted there is no terminal and no such person, accounts
    # are what identify anybody, and a key in the address would only be a bearer token
    # riding in every URL — through browser history, over a shared screen, and out in a
    # Referer. So hosted has no key at all, and `_authorised()` falls to the session.
    token = "" if require_account else secrets.token_urlsafe(12)
    usable, _ = AnthropicProvider().available()
    keeping = Store(store or default_store())
    keeping.sweep()
    # The store comes first: the library reads back what the last run was doing, so a
    # build caught mid-flight stops claiming to be working and keeps its claim on the
    # budget rather than handing it back for money it had probably already spent.
    delivering = mailer or from_environment()
    public = (public_address or f"http://127.0.0.1:{port}").rstrip("/")
    library = Library(
        out,
        max_cost=max_cost,
        budget=budget,
        store=keeping,
        mailer=delivering,
        # Only where an email could reach anybody: a link with a key in it would be a
        # bearer token in a mailbox, so on a machine somebody runs themselves the
        # library is told no address and says nothing.
        address=public if require_account else "",
    )
    library.start_workers()

    handler = type(
        "TargumHandler",
        (Handler,),
        {
            "library": library,
            "require_account": require_account,
            "hosts": hosts_for(public_address),
            "token": token,
            "store": keeping,
            "mailer": delivering,
            # Where a sign-in link points. Loopback is right for a machine somebody
            # runs themselves and useless in an email: hosted, the link has to name the
            # address the reader can actually reach, not the one the server binds to.
            "address": (public_address or f"http://127.0.0.1:{port}").rstrip("/"),
            "page": learn_page(token),
            "you": you_page(token),
            "lists": {which: list_page(token, which) for which in LISTS},
            "adding": add_page(token, no_key="" if usable else NO_KEY),
            "progress": progress_page(token),
            "catalogue": library_page(token),
        },
    )
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as error:
        if error.errno not in (errno.EADDRINUSE, errno.EACCES):
            raise
        # A traceback here reads as a crash in targum. It is almost always a second
        # copy started while the first is still running, and the fix is one flag.
        raise TargumError(
            f"Port {port} is already in use.",
            f"Another targum may already be running. Stop it, or: targum serve --port {port + 1}",
        ) from error
    # Hosted, the address a reader is given is the one in the email and the one on the
    # certificate — not a loopback address with a key on it.
    address = (
        f"{public_address.rstrip('/')}/"
        if require_account
        else f"http://127.0.0.1:{port}/?k={token}"
    )
    if announce:
        announce(address)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(address)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return address
