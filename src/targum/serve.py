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
import json
import queue
import re
import secrets
import shutil
import threading
import traceback
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .accounts import Person, Store, now, plausible
from .errors import TargumError
from .mail import Mailer
from .models import SegmentedDocument, Style
from .pipeline import Build, Result
from .render.builder import about_page, holding_page, signin_page

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

# Hosted, everyone signs in first. Signed out, every home would be the same `local`
# directory, so one visitor would be reading another's library — and there is nowhere
# to put a build that belongs to nobody. On a machine somebody runs themselves the
# opposite is true: there is one person, they are the only one who can reach it, and
# making them make an account to read their own files would be absurd. So it is a
# switch, off by default, and the hosted deployment is what turns it on.
OPEN_TO_STRANGERS = frozenset(
    {"/about", "/account/signin", "/account/enter", "/account/sign-in", "/account/me", "/health"}
)

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
    # What it really cost, once the API has said. Zero until it has.
    spent: float = 0.0
    # How many chapters the text has. One means it is not a book.
    chapters: int = 1
    made: int = field(default_factory=now)

    def state(self) -> dict[str, Any]:
        return {
            "blocked": self.blocked,
            "id": self.id,
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


class Library:
    """Everything built so far, and the jobs building more."""

    def __init__(
        self,
        out: Path,
        max_cost: float = MAX_COST,
        budget: float = SESSION_BUDGET,
        store: Store | None = None,
        account_budget: float | None = ACCOUNT_BUDGET,
    ) -> None:
        self.out = out
        self.max_cost = max_cost
        self.budget = budget
        self.account_budget = account_budget
        self.store = store
        self.adopt()
        self.empty_trash()
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

    def _out_of(self, whose: str) -> str:
        """Which ceiling stopped this, and when it lifts.

        A refusal that does not say which limit was hit, or when it stops applying, is
        indistinguishable from the product being broken.
        """
        when = f"in {BUDGET_HOURS} hours"
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

    @staticmethod
    def chapters(folder: Path) -> list[dict[str, Any]]:
        """Every chapter of a targum, and whether it has been translated.

        Derived from the artifacts rather than recorded anywhere: a chapter is ready when
        every one of its segments has a translation. A second place saying so would drift
        from the truth the first time a build died between writing them.
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
            if translation is not None:
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
            sections = len(list((folder / "reader").glob("sec-*.html"))) or 1
            chapters = self.chapters(folder)
            document = folder / "document.json"
            if document.is_file():
                try:
                    data = json.loads(document.read_text(encoding="utf-8"))
                    title = data.get("title") or title
                    language = data.get("language", "")
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
                    "document": content_hash,
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
                cost, job.lemmas = self._gloss_cost(builder, plan.segmented)
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
            refused = self.store.claim(
                job.id,
                job.estimate,
                self.budget,
                self._since(),
                owner=job.owner,
                per_account=self.account_budget,
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
    def _gloss_cost(builder: Build, segmented: SegmentedDocument) -> tuple[float, int]:
        """What the word meanings will cost, and how many there are.

        The count is worth returning rather than discarding: it is what lets the page
        say how long they will keep arriving for after the reader opens.
        """
        from .annotate.gloss import estimate, unique_lemmas

        annotation = builder.annotate(segmented)
        if annotation is None:
            return 0.0, 0
        lemmas = len(unique_lemmas(annotation))
        return estimate(lemmas, builder.model or ""), lemmas

    def run(self, job: Job) -> None:
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

    def run_chapter(self, job: Job) -> None:
        """Buy one more chapter of a book already on disk.

        Nothing is ingested or segmented again — those are done, they are free, and they
        are sitting in the folder. This translates one chapter and rewrites the reader
        around it, which is the whole of what asking for a chapter costs.
        """
        from .models import Annotation, Document, Glossary, SegmentedDocument, Vocalization
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
            pages = render_reader(
                document,
                segmented,
                [translation],
                folder / "reader",
                annotation=read(Annotation, folder / "annotation.json"),
                glossary=read(Glossary, folder / "glossary.json"),
                vocalization=read(Vocalization, folder / "vocalization.json"),
                clean=False,
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
            model=HOSTED_MODEL,
            # Whose build this is, which scopes the cache for anything that is not a
            # public text. Without it one person's uploaded book would be translated
            # once and served to everyone who happened to upload the same file.
            owner=f"p{job.owner}" if job.owner else "",
            out_root=job.home or self.out,
            gloss=bool(options.get("gloss")),
            difficulty=bool(options.get("words")),
            # A catalogue text arrives with a translation somebody already made, so
            # nothing is asked of a model and nothing is spent.
            translations=[str(t) for t in options.get("translations") or []],
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
    words: str
    shelf: str
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
        if secrets.compare_digest(given, self.token):
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

    def _send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if kind.startswith("text/html"):
            self.send_header("Content-Security-Policy", self._policy(body))
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
        if self._needs_account(route):
            # Data routes answer as data. Anything a person could be looking at gets a
            # page rather than a 401 — and not the sign-in page either, because a door
            # shown to somebody with no key is a wall that looks like a mistake. The
            # door is one click away, in the corner.
            if route.startswith(("/readers", "/job/", "/glossary/")):
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
        if route == "/":
            return self._send(200, self.page.encode("utf-8"), "text/html; charset=utf-8")
        if route == "/words":
            return self._send(200, self.words.encode("utf-8"), "text/html; charset=utf-8")
        if route == "/library":
            return self._send(200, self.shelf.encode("utf-8"), "text/html; charset=utf-8")
        if route == "/readers":
            # Not "/library": that name belongs to the page a person opens.
            home = self._home()
            return self._json(
                {
                    "readers": self.library.readers(home),
                    "trash": self.library.readers(home, trashed=True),
                }
            )
        if route == "/account/me":
            return self._me()
        if route.startswith("/glossary/"):
            return self._serve_glossary(route[len("/glossary/") :])
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
        self._json({"error": "not found"}, 404)

    # -- accounts -----------------------------------------------------------

    def _me(self) -> None:
        person = self._person()
        if person is None:
            return self._json({"signedIn": False})
        self._json(
            {
                "signedIn": True,
                "email": person.email,
                "revision": self.store.revision(person),
                "counts": self.store.counts(person),
            }
        )

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

        self._go(f"/?k={self.token}&signin=welcome", self._session_cookie(session, SESSION_DAYS))

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
        changes = {
            name: list(payload.get(name) or [])
            for name in ("words", "phrases", "docs")
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
        try:
            source = self._source_from(payload)
        except TargumError as error:
            return self._json({"error": error.message}, 400)

        # Somebody has already translated this one, and that translation is better and
        # free. Said before anything is priced, not after it has been paid for.
        if not payload.get("translations") and not payload.get("force_machine"):
            from . import catalogue as catalogue_module

            already = catalogue_module.matching(source)
            if already is not None:
                return self._json({"catalogue": already.state()})

        person = self._person()
        job = Job(
            id=secrets.token_hex(8),
            source=source,
            options=payload,
            owner=person.id if person else None,
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
        waiting: list[int] = []
        if whole:
            waiting = [c["number"] for c in self.library.chapters(folder) if not c["ready"]]
            if not waiting:
                return self._json({"ready": True})

        person = self._person()
        job = Job(
            id=secrets.token_hex(8),
            source=str(folder),
            options={"chapters": waiting if whole else [number], "folder": folder.name},
            owner=person.id if person else None,
            home=home,
        )
        self.library.jobs[job.id] = job
        self.library.remember(job)
        self.library.enqueue(job)
        self._json(job.state())

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
        if not lemma or not source:
            return self._json({"error": "bad request"}, 400)

        from .annotate.gloss import AnthropicGlosses, gloss_one

        provider = AnthropicGlosses()
        usable, _ = provider.available()
        if not usable:
            return self._json({"error": NO_KEY}, 402)
        try:
            meaning = gloss_one(lemma, source, target, provider)
        except TargumError as error:
            return self._json({"error": error.message}, 502)
        except Exception:
            traceback.print_exc()
            return self._json({"error": "Could not look that word up just now."}, 502)
        return self._json({"lemma": lemma, "meaning": meaning})

    def _source_from(self, payload: dict[str, Any]) -> str:
        """A dropped file is written next to the readers; anything else is a source."""
        name = payload.get("name")
        content = payload.get("content")
        if name and content:
            suffix = Path(str(name)).suffix.lower()
            if suffix not in {".txt", ".md", ".markdown", ".epub"}:
                raise TargumError(
                    f"targum cannot read '{suffix}' files. Save it as plain text or "
                    "markdown and drop that in instead."
                )
            # A directory of its own per upload. Two people — or one person twice —
            # dropping files with the same name used to overwrite each other, because
            # the basename was the whole path.
            uploads = self._home() / "uploads" / secrets.token_hex(8)
            uploads.mkdir(parents=True, exist_ok=True)
            # Only the file's own name, never a path it carries.
            path = uploads / Path(str(name)).name
            path.write_bytes(base64.b64decode(str(content)))
            return str(path)

        source = str(payload.get("source", "")).strip()
        if not source:
            raise TargumError("Paste a link, drop a file, or give a Gutenberg or Wikisource id.")
        return source

    def _serve_glossary(self, folder: str) -> None:
        """The word meanings for one build, once they exist.

        A reader opens before these are looked up, so it asks for them afterwards and
        fills them in without a reload. Answering "not yet" is a normal reply, not an
        error: the file appears when the lookups finish.
        """
        root = self._home().resolve()
        target = (root / unquote(folder) / "glossary.json").resolve()
        if root not in target.parents:
            return self._json({"error": "not found"}, 404)
        if not target.is_file():
            return self._json({"ready": False})
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            # Caught mid-write. The reader is still polling; it will ask again.
            return self._json({"ready": False})
        entries = data.get("entries")
        if not isinstance(entries, dict):
            return self._json({"ready": False})
        self._json({"ready": True, "entries": entries})

    def _serve_reader(self, relative: str) -> None:
        """This person's readers, and nothing else — not even another person's."""
        root = self._home().resolve()
        target = (root / unquote(relative)).resolve()
        if not target.is_file() or root not in target.parents:
            return self._send(404, b"not found", "text/plain")
        kind = "text/html; charset=utf-8" if target.suffix == ".html" else "text/plain"
        self._send(200, target.read_bytes(), kind)


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
    from .render.builder import library_page, start_page, words_page
    from .translate.anthropic_provider import AnthropicProvider

    token = secrets.token_urlsafe(12)
    usable, _ = AnthropicProvider().available()
    keeping = Store(store or default_store())
    keeping.sweep()
    # The store comes first: the library reads back what the last run was doing, so a
    # build caught mid-flight stops claiming to be working and keeps its claim on the
    # budget rather than handing it back for money it had probably already spent.
    library = Library(out, max_cost=max_cost, budget=budget, store=keeping)
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
            "mailer": mailer or from_environment(),
            # Where a sign-in link points. Loopback is right for a machine somebody
            # runs themselves and useless in an email: hosted, the link has to name the
            # address the reader can actually reach, not the one the server binds to.
            "address": (public_address or f"http://127.0.0.1:{port}").rstrip("/"),
            "page": start_page(
                token, library.max_cost, library.budget, no_key="" if usable else NO_KEY
            ),
            "words": words_page(token),
            "shelf": library_page(token),
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
    address = f"http://127.0.0.1:{port}/?k={token}"
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
