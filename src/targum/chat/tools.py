"""The tools the chat may call, declared once.

Each tool is a name, a description, a JSON schema, two flags and a function. The same
list is handed to the Anthropic SDK today and will be mounted on a remote MCP server
later (targum-internal #80), so nothing here knows which of the two is asking.

Two rules hold the whole surface up.

**Ownership comes from `Ctx`, never from an argument.** Every tool reads whose shelf,
whose words and whose builds from the context the server built out of the session; an
argument naming an owner is not a thing that exists. That is what makes the registry
safe to expose to a client the server does not control.

**Only a person spends.** No tool here spends money. `quote_build` prices a text for
nothing — `Library.prepare` is the free half of the quote-then-consent seam — and hands
the page a card; the card's button posts to `/build`, the same route the Add page's
button posts to, and `Handler._build` is then the only path to `Library.claim`. The
model never holds a tool that could press. `spends` and `needs_consent` stay on `Tool`
for a surface where that is not so (a client the server does not control), so the seam
is drawn before the first tool needs it.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urlparse

from .. import catalogue as catalogue_module
from .. import coverage as coverage_module
from ..level import Level
from ..usage import Usage

if TYPE_CHECKING:
    from ..accounts import Person, Store
    from ..serve import Library


@dataclass
class Ctx:
    """Who is asking, and what the server knows about them."""

    person: Person | None
    home: Path
    library: Library
    store: Store | None
    chat_id: str
    level: Level
    usage: Usage = field(default_factory=Usage)
    #: Which languages this account reads into and is learning — the same sets
    #: `Handler._reads` and `_learning` hand `/prepare`, so a quote made here is refused
    #: on exactly the grounds the Add page would refuse it.
    reads: set[str] = field(default_factory=set)
    learning: set[str] = field(default_factory=set)
    #: Whether the per-account rails apply. Read once from the session, carried on the
    #: job the quote makes, never taken from an argument.
    admin: bool = False

    @property
    def person_id(self) -> int | None:
        return self.person.id if self.person else None


Run = Callable[[Ctx, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    run: Run
    spends: bool = False
    needs_consent: bool = False


def _schema(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def reader_url(name: str) -> str:
    """Where a built text opens. The same shape `Library.tell` mails out."""
    return f"/reader/{quote(name)}/reader/index.html"


# -- the shelf, measured -----------------------------------------------------------


def _marked(ctx: Ctx, language: str, cache: dict[str, dict[str, int]]) -> dict[str, int]:
    if ctx.store is None or ctx.person is None:
        return {}
    if language not in cache:
        cache[language] = ctx.store.marked(ctx.person, language)
    return cache[language]


def _measure(ctx: Ctx, home: Path, rows: list[dict[str, Any]]) -> None:
    """Say how much of each built text the reader already knows — `Handler._measure`'s
    rule, applied to a list a tool is about to return."""
    cache: dict[str, dict[str, int]] = {}
    for row in rows:
        language = str(row.get("language") or "")
        name = str(row.get("name") or "")
        if not language or not name:
            continue
        measured = coverage_module.against(home / name, _marked(ctx, language, cache))
        if measured is not None:
            row.update(measured.state())


def _sourced(home: Path, rows: list[dict[str, Any]]) -> None:
    """Put each text's source on its row, read here rather than from `Library.readers`.

    The shelf's own rows leave it out on purpose — an upload's source can be a path on
    the server, which a browser has no business being told — and this list never
    leaves the server: it is what lets a catalogue entry be matched to the folder that
    already holds it.
    """
    for row in rows:
        document = home / str(row.get("name") or "") / "document.json"
        try:
            row["source"] = str(
                json.loads(document.read_text(encoding="utf-8")).get("source") or ""
            )
        except (OSError, json.JSONDecodeError, AttributeError):
            row["source"] = ""


def _shelf(ctx: Ctx) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The reader's own texts and the shared starter shelf, each with a reader link."""
    mine = ctx.library.readers(ctx.home)
    _sourced(ctx.home, mine)
    _measure(ctx, ctx.home, mine)
    shared = ctx.library.readers(ctx.library.shared)
    _sourced(ctx.library.shared, shared)
    for row in shared:
        row["shared"] = True
    _measure(ctx, ctx.library.shared, shared)
    for row in [*mine, *shared]:
        row["reader"] = reader_url(str(row["name"]))
    return mine, shared


def _by_source(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {catalogue_module._key(str(row.get("source") or "")): row for row in rows}


def _entry_row(entry: catalogue_module.Entry, built: dict[str, Any] | None) -> dict[str, Any]:
    collection = catalogue_module.collection_of(entry.id)
    row: dict[str, Any] = {
        "id": entry.id,
        "title": entry.title,
        "english": entry.english,
        "author": entry.author,
        "kind": entry.kind.value,
        "register": entry.register.value,
        # Named for what it measures on the library page — how much of it a learner
        # looks up — rather than "difficulty", which promises more than it counts.
        "looked_up_percent": entry.difficulty,
        "minutes": entry.minutes,
        "words": entry.words,
        "has_published_translation": bool(entry.translations),
        "collection": collection.title if collection else "",
        "on_shelf": built is not None,
        "reader": str(built["reader"]) if built else "",
    }
    if built is not None and "known" in built:
        row["known_share"] = built["known"]
        row["words_not_met"] = built["fresh"]
    return row


def _matches(entry: catalogue_module.Entry, query: str) -> bool:
    if not query:
        return True
    haystack = " ".join(
        (
            entry.title,
            entry.english,
            entry.author,
            entry.blurb,
            entry.kind.value,
            entry.register.value,
        )
    ).lower()
    return all(word in haystack for word in query.lower().split())


# -- the tools ---------------------------------------------------------------------


def search_library(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "")
    register = str(args.get("register") or "")
    kind = str(args.get("kind") or "")
    ceiling = args.get("max_looked_up_percent")
    minutes = args.get("max_minutes")
    limit = max(1, min(int(args.get("limit") or 10), 20))
    mine, shared = _shelf(ctx)
    built = _by_source([*mine, *shared])
    found: list[dict[str, Any]] = []
    for entry in catalogue_module.everything():
        if register and entry.register.value != register:
            continue
        if kind and entry.kind.value != kind:
            continue
        if ceiling is not None and entry.difficulty and entry.difficulty > int(ceiling):
            continue
        if minutes is not None and entry.minutes > int(minutes):
            continue
        if not _matches(entry, query):
            continue
        found.append(_entry_row(entry, built.get(catalogue_module._key(entry.source))))
    # Gentlest first, which is the order the register ramp is meant to be climbed in;
    # unmeasured texts sort after measured ones rather than pretending to be easy.
    found.sort(key=lambda row: (row["looked_up_percent"] or 999, row["minutes"]))
    return {"count": len(found), "texts": found[:limit]}


def open_library_text(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    entry = catalogue_module.by_id(str(args.get("id") or ""))
    if entry is None:
        return {"error": "No text in the library has that id."}
    mine, shared = _shelf(ctx)
    built = _by_source([*mine, *shared]).get(catalogue_module._key(entry.source))
    row = _entry_row(entry, built)
    row["blurb"] = entry.blurb
    row["how_to_open"] = (
        "Give the reader the link in `reader`."
        if built
        else "Not built for this reader yet. Call quote_build with this id: the page shows "
        "a card with a button, and the reader presses it. You cannot start one."
    )
    return row


def search_my_shelf(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").lower()
    language = str(args.get("language") or "")
    mine, shared = _shelf(ctx)
    rows = []
    for row in [*mine, *shared]:
        if language and str(row.get("language") or "") != language:
            continue
        text = " ".join(str(row.get(k) or "") for k in ("title", "author", "name")).lower()
        if query and not all(word in text for word in query.split()):
            continue
        rows.append(
            {
                "name": row["name"],
                "title": row["title"],
                "author": row.get("author", ""),
                "language": row.get("language", ""),
                "reads_into": row.get("targets", []),
                "reader": row["reader"],
                "shared": bool(row.get("shared")),
                "chapters_ready": row.get("readyChapters", 0),
                "chapters": len(row.get("chapters") or []),
                "known_share": row.get("known"),
                "words_not_met": row.get("fresh"),
                "words": row.get("words", 0),
            }
        )
    return {"count": len(rows), "texts": rows}


def my_vocabulary(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    language = str(args.get("language") or ctx.level.language)
    limit = max(1, min(int(args.get("limit") or 20), 50))
    if ctx.store is None or ctx.person is None:
        return {"language": language, "known": 0, "learning": 0, "recent": []}
    words = ctx.store.words_with_bands(ctx.person.id, language)
    by_status: dict[str, int] = {"known": 0, "learning": 0, "ignored": 0}
    for _, status, band, _ in words:
        if band in ("name", "number"):
            continue
        if status == 9:
            by_status["known"] += 1
        elif status in (1, 2, 3):
            by_status["learning"] += 1
        elif status == 0:
            by_status["ignored"] += 1
    recent = sorted(words, key=lambda w: w[3], reverse=True)[:limit]
    return {
        "language": language,
        **by_status,
        "recent": [
            {"lemma": lemma, "status": status, "band": band} for lemma, status, band, _ in recent
        ],
    }


def my_progress(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    return ctx.level.state()


def suggest_next(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    language = str(args.get("language") or ctx.level.language)
    register = str(args.get("register") or "")
    minutes = args.get("max_minutes")
    limit = max(1, min(int(args.get("limit") or 5), 10))
    mine, shared = _shelf(ctx)
    own = _by_source(mine)
    built = _by_source([*mine, *shared])
    candidates: list[tuple[tuple[float, float], dict[str, Any]]] = []
    for entry in catalogue_module.everything():
        key = catalogue_module._key(entry.source)
        if entry.language.split("-")[0] != language.split("-")[0]:
            continue
        if key in own:
            continue
        if register and entry.register.value != register:
            continue
        if minutes is not None and entry.minutes > int(minutes):
            continue
        row = _entry_row(entry, built.get(key))
        known = row.get("known_share")
        if known is not None:
            row["because"] = f"{round(float(known) * 100)}% of its words are ones you know."
            rank = (0.0, -float(known))
        elif entry.difficulty:
            row["because"] = (
                f"{entry.difficulty}% of its words are ones a learner looks up; "
                f"{entry.register.value} Hebrew, about {entry.minutes} minutes."
            )
            rank = (1.0, float(entry.difficulty))
        else:
            row["because"] = "Not measured yet."
            rank = (2.0, 0.0)
        candidates.append((rank, row))
    candidates.sort(key=lambda pair: pair[0])
    return {"suggestions": [row for _, row in candidates[:limit]]}


def quote_build(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    """Price a text for nothing, and leave a job the reader can press to start.

    The same door `/prepare` opens for the Add page, with the same refusals in the same
    words: the pair of languages has to be one an upload has been taken end to end in,
    and one this account said it reads. What comes back is `Job.state()` verbatim —
    the page draws its card from that, and the card's button posts `/build`.
    """
    from ..serve import Job
    from ..translate.prompts import INTO, language_name

    offered = {code for code, _ in INTO}
    reads = (ctx.reads & offered) or offered
    wanted = str(args.get("to") or ("en" if "en" in reads else sorted(reads)[0]))
    if wanted not in offered:
        names = ", ".join(language_name(code) for code in sorted(offered))
        return {"error": f"targum translates into {names}."}
    if wanted not in reads:
        return {"error": f"{language_name(wanted)} is not in the reader's profile."}

    payload: dict[str, Any] = {"to": wanted}
    catalogue_id = str(args.get("catalogue_id") or "").strip()
    source = str(args.get("source") or "").strip()
    if catalogue_id:
        entry = catalogue_module.by_id(catalogue_id)
        if entry is None:
            return {"error": "No text in the library has that id."}
        mine, shared = _shelf(ctx)
        built = _by_source([*mine, *shared]).get(catalogue_module._key(entry.source))
        if built is not None:
            return {
                "already_built": True,
                "reader": built["reader"],
                "note": "Nothing to build. Give the reader the link.",
            }
        source = entry.source
        payload.update(
            {
                "source": source,
                "from": entry.language,
                "translations": [rendering.source for rendering in entry.translations],
            }
        )
    elif source:
        # A link or a fetcher's identifier (`gutenberg:…`, `wikisource:…`). A bare word
        # is neither, and would be read as a file on the server.
        if "://" not in source and ":" not in source:
            return {"error": "Give a link, or a library text's id."}
        if urlparse(source).scheme in ("http", "https") and not urlparse(source).hostname:
            return {"error": "That link has no address in it."}
        already = catalogue_module.matching(source)
        if already is not None and already.translations:
            mine, shared = _shelf(ctx)
            built = _by_source([*mine, *shared]).get(catalogue_module._key(already.source))
            row = _entry_row(already, built)
            row["note"] = (
                "In the library already, with a translation somebody published — better "
                "than a machine one. Quote it by catalogue_id instead."
            )
            return {"in_library": row}
        payload["source"] = source
    else:
        return {"error": "Say what to build: a link, or a library text's id."}

    job = Job(
        id=secrets.token_hex(8),
        source=source,
        options=payload,
        owner=ctx.person_id,
        admin=ctx.admin,
        home=ctx.home,
    )
    ctx.library.jobs[job.id] = job
    ctx.library.remember(job)
    ctx.library.prepare(job)
    ctx.library.remember(job)
    state = job.state()
    return {
        "quote": state,
        "note": (
            "The page shows the reader a card from this with a button that starts the "
            "build; you cannot press it. Say what the text is and how long it will take "
            "in their time — sentences, chapters, minutes, hours of audio — never in money."
            if state["stage"] == "ready"
            else "This cannot be built now; the card says why. Tell the reader plainly."
        ),
    }


def my_hours(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    """The audio allowance, in the only unit a reader is ever told about."""
    allowed = ctx.library.upload_seconds
    used = (
        ctx.store.hours_used(ctx.person_id, ctx.library._month_from())
        if ctx.store is not None
        else 0.0
    )
    return {
        "used_hours": round(used / 3600, 2),
        "allowed_hours": None if allowed is None else round(allowed / 3600, 2),
        "left_hours": None if allowed is None else round(max(0.0, allowed - used) / 3600, 2),
        "month_ends": ctx.library._month_ends(),
        "note": "Hours, never money. Text is unlimited; only recordings and video count.",
    }


def check_job(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    job = ctx.library.jobs.get(str(args.get("id") or ""))
    if job is None or job.owner != ctx.person_id:
        return {"error": "No build of yours has that id."}
    state = job.state()
    if state.get("reader"):
        state["open"] = f"/reader/{state['reader']}"
    return state


REGISTERS = [register.value for register in catalogue_module.Register]
KINDS = [kind.value for kind in catalogue_module.Kind]

REGISTRY: tuple[Tool, ...] = (
    Tool(
        "search_library",
        "Search the public library of texts with published translations. Filter by "
        "register (which Hebrew), kind, how much a learner looks up, or reading time. "
        "Returns whether each text is already on the reader's shelf and, if so, its link "
        "and how much of it they know.",
        _schema(
            {
                "query": {
                    "type": "string",
                    "description": "Words to match in title, author, blurb.",
                },
                "register": {"type": "string", "enum": REGISTERS},
                "kind": {"type": "string", "enum": KINDS},
                "max_looked_up_percent": {"type": "integer", "minimum": 0, "maximum": 100},
                "max_minutes": {"type": "integer", "minimum": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            }
        ),
        search_library,
    ),
    Tool(
        "open_library_text",
        "One library text by id: its blurb, whether it is built for this reader, and the "
        "link to open it if it is.",
        _schema({"id": {"type": "string"}}, ("id",)),
        open_library_text,
    ),
    Tool(
        "search_my_shelf",
        "The reader's own built texts and the shared starter shelf, each with its link, "
        "which languages it opens in, chapters ready, and how much of it they know.",
        _schema({"query": {"type": "string"}, "language": {"type": "string"}}),
        search_my_shelf,
    ),
    Tool(
        "my_vocabulary",
        "The reader's ledger of words in one language: how many known, how many still "
        "being learned, and the most recently marked.",
        _schema(
            {
                "language": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            }
        ),
        my_vocabulary,
    ),
    Tool(
        "my_progress",
        "Real counts of what the reader has done: words known, days read, streak, "
        "sections finished. Never a placement.",
        _schema({}),
        my_progress,
    ),
    Tool(
        "suggest_next",
        "Library texts the reader has not built yet, ranked gentlest first by how much of "
        "each they already know where that is measured, and by how much a learner looks "
        "up otherwise. Each comes with one reason.",
        _schema(
            {
                "language": {"type": "string"},
                "register": {"type": "string", "enum": REGISTERS},
                "max_minutes": {"type": "integer", "minimum": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            }
        ),
        suggest_next,
    ),
    Tool(
        "quote_build",
        "Price a text for the reader, for nothing: a link (an article, a podcast episode, "
        "a YouTube address, a Gutenberg or Wikisource id) or a library text by id. Returns "
        "the quote the page draws a card from — title, language, sentences or chapters, "
        "audio length — or why it cannot be built. The reader presses the card to start it; "
        "you cannot.",
        _schema(
            {
                "source": {"type": "string", "description": "A link or fetcher id."},
                "catalogue_id": {"type": "string", "description": "A library text's id."},
                "to": {"type": "string", "description": "Language to translate into."},
            }
        ),
        quote_build,
    ),
    Tool(
        "my_hours",
        "How much of this month's audio allowance the reader has used, in hours, and when "
        "it returns. Never money.",
        _schema({}),
        my_hours,
    ),
    Tool(
        "check_job",
        "Where one of the reader's own builds has got to, by id.",
        _schema({"id": {"type": "string"}}, ("id",)),
        check_job,
    ),
)

BY_NAME: dict[str, Tool] = {tool.name: tool for tool in REGISTRY}


def anthropic_tools() -> list[dict[str, Any]]:
    """The registry in the shape the Messages API takes."""
    return [
        {"name": tool.name, "description": tool.description, "input_schema": tool.schema}
        for tool in REGISTRY
    ]


def run(name: str, args: dict[str, Any], ctx: Ctx) -> tuple[str, bool]:
    """Run one tool and return its result as text for a `tool_result`, with `is_error`.

    A tool that raises answers as an error the model can read rather than a traceback
    that ends the turn: the conversation is the reader's, and a broken lookup is one
    line in it, not the end of it.
    """
    tool = BY_NAME.get(name)
    if tool is None:
        return json.dumps({"error": f"No tool called {name}."}), True
    if tool.needs_consent:
        return json.dumps({"error": "This needs the reader's own press, and has none."}), True
    try:
        out = tool.run(ctx, args or {})
    except Exception as error:  # noqa: BLE001 - the model reads this, a reader does not
        return json.dumps({"error": f"{type(error).__name__}: {error}"}), True
    return json.dumps(out, ensure_ascii=False), "error" in out
