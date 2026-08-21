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
import json
import secrets
import threading
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from .errors import TargumError
from .models import SegmentedDocument, Style
from .pipeline import Build

MAX_UPLOAD = 32 * 1024 * 1024
SAFE_HOSTS = ("127.0.0.1", "localhost", "[::1]")

# A full-length novel costs real money to translate, and a page anyone on this machine
# can reach should not be able to spend it by accident. Both are estimates rather than
# billed amounts, so they are deliberately conservative.
MAX_COST = 2.00
SESSION_BUDGET = 10.00


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

    def why_blocked(self, estimate: float) -> str:
        """Whether this build may go ahead, in words the page can show."""
        if estimate > self.max_cost:
            return (
                f"This one would cost about ${estimate:.2f}, over the ${self.max_cost:.2f} "
                f"limit for a single text. Start targum with --max-cost to raise it, or "
                f"give it a shorter piece."
            )
        if estimate > self.remaining():
            return (
                f"This would cost about ${estimate:.2f} and only ${self.remaining():.2f} "
                f"is left of this session's ${self.budget:.2f} budget. Restart targum, or "
                f"start it with --budget to raise it."
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
            job.blocked = self.why_blocked(job.estimate)
            if not job.blocked and builder.gloss and plan.segmented is not None:
                # Glossing is priced from the real count of distinct dictionary forms,
                # which means lemmatizing first. Only worth the wait once the
                # translation itself has cleared the cap.
                job.stage = "looking up words"
                job.estimate += self._gloss_cost(builder, plan.segmented)
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
    def _gloss_cost(builder: Build, segmented: SegmentedDocument) -> float:
        from .annotate.gloss import estimate, unique_lemmas

        annotation = builder.annotate(segmented)
        if annotation is None:
            return 0.0
        return estimate(len(unique_lemmas(annotation)), builder.model or "")

    def run(self, job: Job) -> None:
        try:
            job.stage = "working"
            builder = self._builder(job)
            builder.notify = lambda message: setattr(job, "message", message)

            def progress(done: int) -> None:
                job.done += done

            result = builder.run(on_progress=progress)
            job.reader = f"{result.out_dir.name}/reader/index.html"
            job.stage = "done"
            job.message = ""
        except TargumError as error:
            job.error = f"{error.message} {error.hint or ''}".strip()
            job.stage = "failed"
        except Exception as error:
            job.error = str(error)
            job.stage = "failed"

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
        )


class Handler(BaseHTTPRequestHandler):
    server_version = "targum"
    library: Library
    token: str
    page: str

    def log_message(self, format: str, *args: Any) -> None:
        return  # the console belongs to the build output

    # -- plumbing -----------------------------------------------------------

    def _authorised(self) -> bool:
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        if host not in SAFE_HOSTS:
            # A page on another origin resolving a name to this address should not be
            # able to drive the builder.
            return False
        query = parse_qs(urlparse(self.path).query)
        given = query.get("k", [""])[0] or (self.headers.get("X-Targum-Key") or "")
        return secrets.compare_digest(given, self.token)

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

    # -- routes -------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if not self._authorised():
            return self._send(403, b"targum: wrong or missing key", "text/plain")
        if route.startswith("/reader/"):
            return self._serve_reader(route[len("/reader/") :])
        if route == "/":
            return self._send(200, self.page.encode("utf-8"), "text/html; charset=utf-8")
        if route == "/library":
            return self._json({"readers": self.library.readers()})
        if route.startswith("/job/"):
            job = self.library.jobs.get(route[len("/job/") :])
            return self._json(job.state() if job else {"error": "no such job"})
        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorised():
            return self._json({"error": "wrong or missing key"}, 403)
        route = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            return self._json({"error": "that file is too large"}, 413)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad request"}, 400)

        if route == "/prepare":
            return self._prepare(payload)
        if route == "/build":
            return self._build(payload)
        self._json({"error": "not found"}, 404)

    def _prepare(self, payload: dict[str, Any]) -> None:
        try:
            source = self._source_from(payload)
        except TargumError as error:
            return self._json({"error": error.message}, 400)

        job = Job(id=secrets.token_hex(8), source=source, options=payload)
        self.library.jobs[job.id] = job
        self.library.prepare(job)
        self._json(job.state())

    def _build(self, payload: dict[str, Any]) -> None:
        job = self.library.jobs.get(str(payload.get("id", "")))
        if job is None:
            return self._json({"error": "no such job"}, 404)
        if job.stage in {"working", "done"}:
            return self._json(job.state())
        blocked = self.library.claim(job)
        if blocked:
            job.blocked = blocked
            job.stage = "blocked"
            return self._json(job.state(), 402)
        threading.Thread(target=self.library.run, args=(job,), daemon=True).start()
        self._json(job.state())

    def _source_from(self, payload: dict[str, Any]) -> str:
        """A dropped file is written next to the readers; anything else is a source."""
        name = payload.get("name")
        content = payload.get("content")
        if name and content:
            suffix = Path(str(name)).suffix.lower()
            if suffix not in {".txt", ".md", ".markdown", ".epub"}:
                raise TargumError(f"targum does not read '{suffix}' files.")
            uploads = self.library.out / "uploads"
            uploads.mkdir(parents=True, exist_ok=True)
            # Only the file's own name, never a path it carries.
            path = uploads / Path(str(name)).name
            path.write_bytes(base64.b64decode(str(content)))
            return str(path)

        source = str(payload.get("source", "")).strip()
        if not source:
            raise TargumError("Give a link, an identifier, or a file.")
        return source

    def _serve_reader(self, relative: str) -> None:
        """Built readers, and nothing else under the output directory."""
        root = self.library.out.resolve()
        target = (root / unquote(relative)).resolve()
        if not target.is_file() or root not in target.parents:
            return self._send(404, b"not found", "text/plain")
        kind = "text/html; charset=utf-8" if target.suffix == ".html" else "text/plain"
        self._send(200, target.read_bytes(), kind)


def start(
    out: Path,
    port: int = 8420,
    open_browser: bool = True,
    max_cost: float = MAX_COST,
    budget: float = SESSION_BUDGET,
    announce: Callable[[str], None] | None = None,
) -> str:
    """Run until interrupted. Returns the address it is listening on."""
    from .render.builder import start_page

    token = secrets.token_urlsafe(12)
    library = Library(out, max_cost=max_cost, budget=budget)

    handler = type(
        "TargumHandler",
        (Handler,),
        {"library": library, "token": token, "page": start_page(token, library.max_cost)},
    )
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
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
