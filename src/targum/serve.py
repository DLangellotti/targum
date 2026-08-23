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
import errno
import json
import secrets
import threading
import traceback
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .accounts import Person, Store, plausible
from .errors import TargumError
from .mail import Mailer
from .models import SegmentedDocument, Style
from .pipeline import Build, Result

MAX_UPLOAD = 32 * 1024 * 1024
SAFE_HOSTS = ("127.0.0.1", "localhost", "[::1]")

# A base64 body is a third larger than the file inside it, so this is the real ceiling
# on what someone can drop, and the number the page quotes when it refuses one.
MAX_FILE_MB = int(MAX_UPLOAD / 1.37 / (1024 * 1024))

# Said once, in the page, rather than as a stack trace after the wait. Without a key the
# builder can still open everything already built, so this blocks a text rather than
# stopping the server.
NO_KEY = (
    "targum cannot take on anything new just now. Everything you were already reading "
    "still opens, with its vowels and your word lists. (If you are running this "
    "yourself: no Anthropic API key is set.)"
)

# A full-length novel costs real money to translate, and a page anyone on this machine
# can reach should not be able to spend it by accident. Both are estimates rather than
# billed amounts, so they are deliberately conservative.
MAX_COST = 2.00
SESSION_BUDGET = 10.00


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

    def state(self) -> dict[str, Any]:
        return {
            "blocked": self.blocked,
            "id": self.id,
            "title": self.title,
            "language": self.language,
            "segments": self.segments,
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


class Library:
    """Everything built so far, and the jobs building more."""

    def __init__(
        self, out: Path, max_cost: float = MAX_COST, budget: float = SESSION_BUDGET
    ) -> None:
        self.out = out
        self.max_cost = max_cost
        self.budget = budget
        self.committed = 0.0
        self.jobs: dict[str, Job] = {}
        self.lock = threading.Lock()

    def remaining(self) -> float:
        return max(0.0, self.budget - self.committed)

    def release(self, job: Job) -> None:
        """Give back what a failed build had claimed but never spent."""
        with self.lock:
            self.committed = max(0.0, self.committed - job.estimate)

    def why_blocked(self, estimate: float) -> str:
        """Whether this build may go ahead, in words the page can show."""
        if estimate > self.max_cost:
            # The reader pays by the month and never by the text, so what stops them is
            # a limit on the thing itself, not a sum of money they have never been shown.
            return (
                "That one is longer than we can take on in a single go. Try a chapter "
                "of it, a shorter piece, or something from the library."
            )
        if estimate > self.remaining():
            return (
                "That is as much as targum will take on in one sitting. Give it a rest "
                "and come back, or read something already waiting for you."
            )
        return ""

    def readers(self) -> list[dict[str, Any]]:
        """Everything built, newest first, with what the page needs to show progress."""
        found: list[dict[str, Any]] = []
        if not self.out.is_dir():
            return found
        for folder in self.out.iterdir():
            index = folder / "reader" / "index.html"
            if not index.is_file():
                continue
            title = folder.name
            language = ""
            content_hash = ""
            sections = len(list((folder / "reader").glob("sec-*.html"))) or 1
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
                    "built": int(index.stat().st_mtime),
                }
            )
        found.sort(key=lambda reader: reader["built"], reverse=True)
        return found

    def prepare(self, job: Job) -> None:
        """Ingest and segment, which costs nothing, then price the rest."""
        try:
            builder = self._builder(job)
            plan = builder.plan()
            job.title = plan.document.title or job.source
            job.language = plan.document.language
            job.segments = len(plan.segmented.segments) if plan.segmented else 0
            job.estimate = plan.estimated_cost
            job.total = job.segments
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
        with self.lock:
            blocked = self.why_blocked(job.estimate)
            if not blocked:
                self.committed += job.estimate
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
        try:
            job.stage = "working"
            builder = self._builder(job)
            builder.notify = lambda message: setattr(job, "message", message)

            def progress(done: int) -> None:
                job.done += done

            def ready(result: Result) -> None:
                # The page is watching for this and navigates as soon as it sees it.
                # Looking up word meanings carries on in this thread afterwards, into a
                # reader that is already open.
                job.reader = f"{result.out_dir.name}/reader/index.html"
                job.stage = "done"
                job.message = ""

            builder.run(on_progress=progress, on_ready=ready)
        except TargumError as error:
            self._blame(job, error.message)
        except Exception:
            # Whatever a library chose to say about itself is not a sentence for someone
            # who wanted to read a poem. The detail belongs in the terminal.
            traceback.print_exc()
            self._blame(
                job,
                "Something went wrong while building this one. The Terminal window has the detail.",
            )

    def _blame(self, job: Job, message: str) -> None:
        """Record a failure, unless there is already a reader to show for the work.

        Everything after the reader opens is a bonus. Failing the job at that point
        would replace a book someone is reading with an error, and the page has stopped
        watching for one anyway.
        """
        if job.stage == "done":
            job.message = message
            return
        job.error = message
        job.stage = "failed"
        # The money was committed when the build was claimed. A build that failed spent
        # little or none of it, and without this three failures in a row exhaust a
        # session budget that paid for nothing.
        self.release(job)

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
            out_root=self.out,
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
SENT = "Check your email. If that address has an account, a link is on its way."


class Handler(BaseHTTPRequestHandler):
    server_version = "targum"
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

    def _host_is_ours(self) -> bool:
        # A page on another origin resolving a name to this address should not be able
        # to drive the builder, whatever else it can prove.
        return (self.headers.get("Host") or "").rsplit(":", 1)[0] in SAFE_HOSTS

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

    def _send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
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

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        # The browser asks for this on every page load without being told to, and it
        # carries no key, so it was answering the stale-session page and putting a
        # failed request in the console each time. Nothing is disclosed by saying there
        # is no icon.
        if route == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        # The one route that needs no key: it carries a single-use token of its own,
        # which is a stronger claim than the key it would otherwise be asked for. It
        # has to work from a mail client, hours later, possibly after a restart.
        if route == "/account/enter":
            # Exempt from the key, never from the host check: a page on another origin
            # that resolves a name to this address still gets nothing.
            if not self._host_is_ours():
                return self._send(404, b"not found", "text/plain")
            return self._enter(parse_qs(urlparse(self.path).query).get("t", [""])[0])
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
            return self._json({"readers": self.library.readers()})
        if route == "/account/me":
            return self._me()
        if route.startswith("/glossary/"):
            return self._serve_glossary(route[len("/glossary/") :])
        if route.startswith("/job/"):
            job = self.library.jobs.get(route[len("/job/") :])
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
        if route != "/account/sign-in" and not self._authorised():
            return self._json(
                {
                    "error": "This page is from an earlier targum session. Open the link "
                    "printed in the Terminal window and try again."
                },
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

    def _sign_in(self, payload: dict[str, Any]) -> None:
        email = str(payload.get("email") or "")
        if not plausible(email):
            return self._json({"error": "That does not look like an email address."}, 400)
        token = self.store.start_sign_in(email)
        link = f"{self.address}/account/enter?t={token}"
        try:
            self.mailer.send(email, link)
        except Exception:
            # Said plainly, because a link that never arrives with a cheerful "check
            # your email" is the worst version of this failing.
            return self._json({"error": "The link could not be sent. Try again in a minute."}, 502)
        self._json({"sent": True, "message": SENT})

    def _enter(self, token: str) -> None:
        got = self.store.finish_sign_in(token) if token else None
        if got is None:
            # Not an error page: a spent or stale link is what a second click on the
            # same email looks like, and the way out of it is to ask for another.
            return self._go(f"/?k={self.token}&signin=expired")
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

        job = Job(id=secrets.token_hex(8), source=source, options=payload)
        self.library.jobs[job.id] = job
        self.library.prepare(job)
        self._json(job.state())

    def _build(self, payload: dict[str, Any]) -> None:
        job = self.library.jobs.get(str(payload.get("id", "")))
        if job is None:
            return self._json(
                {
                    "error": "That build was lost when targum restarted. Start it again — "
                    "anything already translated is cached."
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
        threading.Thread(target=self.library.run, args=(job,), daemon=True).start()
        self._json(job.state())

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
            uploads = self.library.out / "uploads"
            uploads.mkdir(parents=True, exist_ok=True)
            # Only the file's own name, never a path it carries.
            path = uploads / Path(str(name)).name
            path.write_bytes(base64.b64decode(str(content)))
            return str(path)

        source = str(payload.get("source", "")).strip()
        if not source:
            raise TargumError("Paste a link, drop a file, or type a Gutenberg or Wikisource id.")
        return source

    def _serve_glossary(self, folder: str) -> None:
        """The word meanings for one build, once they exist.

        A reader opens before these are looked up, so it asks for them afterwards and
        fills them in without a reload. Answering "not yet" is a normal reply, not an
        error: the file appears when the lookups finish.
        """
        root = self.library.out.resolve()
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
        """Built readers, and nothing else under the output directory."""
        root = self.library.out.resolve()
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
) -> str:
    """Run until interrupted. Returns the address it is listening on."""
    from .mail import from_environment
    from .render.builder import library_page, start_page, words_page
    from .translate.anthropic_provider import AnthropicProvider

    token = secrets.token_urlsafe(12)
    library = Library(out, max_cost=max_cost, budget=budget)
    usable, _ = AnthropicProvider().available()
    keeping = Store(store or default_store())
    keeping.sweep()

    handler = type(
        "TargumHandler",
        (Handler,),
        {
            "library": library,
            "token": token,
            "store": keeping,
            "mailer": mailer or from_environment(),
            "address": f"http://127.0.0.1:{port}",
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
