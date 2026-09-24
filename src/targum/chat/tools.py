"""The tools the chat may call, declared once.

Each tool is a name, a description, a JSON schema, four flags and a function. The same
list is handed to the Anthropic SDK, served over stdio to a client on this machine, and
mounted on the remote connector (targum-internal #80) — so nothing here knows which of
the three is asking.

Two rules hold the whole surface up.

**Ownership comes from `Ctx`, never from an argument.** Every tool reads whose shelf,
whose words and whose builds from the context the server built out of the session; an
argument naming an owner is not a thing that exists. That is what makes the registry
safe to expose to a client the server does not control.

**Only a person spends, and the chat holds nothing that does.** `anthropic_tools` —
the list this conversation's model is given — leaves out anything with `spends` set, so
the rule below is unchanged for the surface it was written for. One tool in the registry
does spend (`record_turn`, for a conversation held somewhere else), and it is reachable
only through a connector whose reader granted the scope that consented to it: design.md
§12, "A scope is a press that lasts", 2026-09-22.

`quote_build` prices a text for
nothing — `Library.prepare` is the free half of the quote-then-consent seam — and hands
the page a card; the card's button posts to `/build`, the same route the Add page's
button posts to, and `Handler._build` is then the only path to `Library.claim`. The
model never holds a tool that could press. `spends` and `needs_consent` stay on `Tool`
for a surface where that is not so (a client the server does not control), so the seam
is drawn before the first tool needs it.

**And a scope decides what a connector may even see.** `scope` says which of
`oauth.SCOPES` a remote client must have been granted before a tool is listed to it at
all: the library's by default, `record` for anything that reads the reader's own words,
`chat` for the one that prices a text. Over the Anthropic SDK and over stdio there is
no token and no scope, and the whole registry stands — the reader is the person who
started the process. See `connector.exposed`.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import wait as wait_for
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, unquote, urlparse

from .. import catalogue as catalogue_module
from .. import coverage as coverage_module
from .. import level as level_module
from ..level import Level
from ..translate.prompts import INTO, language_name
from ..usage import Usage
from . import check as check_module
from . import hebrew as hebrew_module
from . import sources as sources_module

if TYPE_CHECKING:
    from ..accounts import Person, Store
    from ..serve import Library


#: What every build the chat starts asks for, on top of where the text comes from and
#: what it is translated into.
#:
#: `words` is the whole of it, and it was missing. `serve._prepare` reads
#: `difficulty=bool(options.get("words"))` and `Pipeline.annotate` opens with
#: `if not self.difficulty: return None` — so a build quoted here wrote no
#: `annotation.json`, and the reader that came back had no word a reader could tap and no
#: control to govern them. Silently: the job reported `done`, nothing was logged, and the
#: page simply had no marks on it.
#:
#: The Add page has always sent it, and says why in a comment this borrows:
#: "Being able to tap a word is most of what this is for, and a checkbox asking whether
#: you want that is a question nobody should have to answer."
#:
#: A constant rather than a literal at each door because there are two — a link or a
#: catalogue id through `quote_build`, and a conversation read back through
#: `save_conversation` — and both had forgotten. A third would have too, and did: the
#: part and chapter doors in `serve` write their own options and never carried it, so
#: buying a recording's second part rebuilt the reader without a word to tap. Since
#: then `_builder` reads `options.get("words", True)`, so a door that says nothing
#: gets words; this constant stays as the chat's way of saying so out loud.
#:
#: `gloss` is deliberately not here. It is about half of what a build costs and most of
#: it is never read; a word is bought from the card when somebody actually wants it.
BUILD_OPTIONS: dict[str, Any] = {"words": True}


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
    #: What this reader *said* they read, or `None` where nobody is signed in. Not the
    #: same thing as `reads`, which answers "everything" for a visitor because it is a
    #: permission rather than a preference — feeding that to a rule which picks one
    #: language makes a signed-out conversation Russian, `INTO` holding exactly English
    #: and Russian (targum-internal#286, item 1).
    said_reads: set[str] | None = None
    #: How to reach targum's own model, for the one tool that spends (#80). A callable
    #: rather than a client, so nothing here decides when one is made and a test can
    #: hand over a script. `None` where there is no model to reach — the command line,
    #: a box with no key — and `record_turn` says so rather than failing inside.
    #:
    #: The chat does not set it: a turn there already has a client and buys its own
    #: reply. This is for a surface where the conversation is somebody else's and only
    #: the judgement is ours.
    ask: Callable[[], Any] | None = None
    #: Where a press lives, for a caller that has no page of ours to draw a card on.
    #: Empty in the chat, which draws the card itself and posts `/build` from it; the
    #: public address over the connector, where the quote has to come back carrying a
    #: link to the page the button is on (targum-internal#80). Either way the press is
    #: the reader's own, on targum, and the model cannot make it.
    press_at: str = ""
    #: Whether this caller may read the reader's record — their words and their slips.
    #: Always, in the chat and over stdio; over the connector, only where the token was
    #: granted `record`. Read by the one tool that is offered without that scope and
    #: carries the record when it has it (`how_to_talk`).
    sees_record: bool = True

    @property
    def person_id(self) -> int | None:
        return self.person.id if self.person else None

    @property
    def language(self) -> str:
        """The language this conversation is written to the reader in — its meanings, its
        `= ` lines, and the name a build made from it is given. One rule with the chrome's
        (`strings.reading_language`), which it disagreed with until 2026-09-22."""
        from ..strings import reading_language

        return reading_language(self.said_reads)


Run = Callable[[Ctx, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict[str, Any]
    run: Run
    spends: bool = False
    needs_consent: bool = False
    #: Whether this tool has anything to say to nobody. Everything that reads the
    #: reader's own shelf, ledger or builds does not: over stdio, where `Ctx.person` is
    #: None because the machine has one signed-out reader, listing it would be offering
    #: a tool that can only answer emptily. Remote, the token names a person and this is
    #: always satisfied — see `connector.exposed`.
    needs_account: bool = False
    #: Which scope a connector must have been granted to see this at all
    #: (targum-internal#80). Empty means the library's, which is what a tool that asks
    #: nothing of the reader's record needs. The one tool that spends carries
    #: `oauth.SPENDING_SCOPE`, and that pairing is the whole of what design.md §12's
    #: "A scope is a press that lasts" allows.
    scope: str = ""
    #: For a conversation held somewhere else, where the host writes the replies
    #: (targum-internal#80). Never offered to targum's own chat, which already holds its
    #: conversation to the contract and recasts every line itself — see `anthropic_tools`.
    elsewhere: bool = False
    #: What a host shows a person in place of the name (MCP's `title`). Claude prints a
    #: tool's name in its own interface, and "Quote build" or "My hours" is this
    #: registry's vocabulary said to a reader. The name stays, because hosts already
    #: connected call tools by it; the title is what somebody reads.
    title: str = ""
    #: Whether calling it changes anything the reader has: a playlist, a job waiting on
    #: their press, a line kept. Everything else only reads (MCP's `readOnlyHint`).
    writes: bool = False
    #: Whether it reaches past targum to the web (MCP's `openWorldHint`).
    open_world: bool = False
    #: Whether calling it twice with the same arguments does no more than once
    #: (MCP's `idempotentHint`, which only means something for a tool that writes).
    idempotent: bool = False

    def hints(self) -> dict[str, bool]:
        """The tool's MCP annotations. None of them deletes or overwrites anything."""
        said = {
            "readOnlyHint": not self.writes,
            "destructiveHint": False,
            "openWorldHint": self.open_world,
        }
        if self.writes:
            said["idempotentHint"] = self.idempotent
        return said


def _schema(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def reader_url(name: str, at: str = "") -> str:
    """Where a built text opens. The same shape `Library.tell` mails out.

    `at` is the public address, and it is the whole difference between a link and a piece
    of text. targum's own chat draws these into its own page, where a path is right and
    an origin would be noise. A host is not on targum: Claude was handed
    `/reader/%D7%A9.../reader/index.html` and printed it as words, because a relative path
    resolves against *its* origin and no client will guess ours (2026-09-23). So over the
    connector it carries the scheme and host, which is what makes it clickable — and
    clicking it is the only way anything targum offers gets opened.
    """
    return f"{at.rstrip('/')}/reader/{quote(name)}/reader/index.html"


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
        row["reader"] = reader_url(str(row["name"]), ctx.press_at)
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


#: What a search in one language also finds. Aramaic sits on the Hebrew shelf — Onkelos
#: beside its verse, the Gemara beside its Mishnah — and nobody learning Hebrew searching
#: for either means "not that one".
_FAMILY: dict[str, set[str]] = {"he": {"he", "arc"}}


def _language_asked(ctx: Ctx, args: dict[str, Any]) -> str:
    """The language a search is held to: the one named, or the conversation's own; ""
    for "all"."""
    said = str(args.get("language") or "").strip()
    if said.lower() in ("all", "any", "*"):
        return ""
    return (language_code(said) or ctx.level.language or "he").split("-")[0].lower()


def search_library(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "")
    register = str(args.get("register") or "")
    kind = str(args.get("kind") or "")
    ceiling = args.get("max_looked_up_percent")
    if ceiling is None:
        # The reader's own ceiling when the model names none (targum-internal#244):
        # by the rung the ledger reaches, from `level.LOOKED_UP_CEILING`.
        ceiling = level_module.ceiling_for(ctx.level)
    minutes = args.get("max_minutes")
    limit = max(1, min(int(args.get("limit") or 10), 20))
    # The conversation's language unless another is named (2026-09-24: an Italian talk
    # came back for a Hebrew reader). "all" is every language.
    language = _language_asked(ctx, args)
    mine, shared = _shelf(ctx)
    built = _by_source([*mine, *shared])
    found: list[dict[str, Any]] = []
    for entry in catalogue_module.everything():
        if language and entry.language.split("-")[0].lower() not in _FAMILY.get(
            language, {language}
        ):
            continue
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
    if not found and query and ctx.store is not None:
        # What the shelf could not answer is what the operator most wants to know.
        ctx.store.want(query, "")
    out: dict[str, Any] = {
        "count": len(found),
        "language": language or "all",
        "texts": found[:limit],
    }
    if ceiling is not None and args.get("max_looked_up_percent") is None:
        out["ceiling_applied"] = int(ceiling)
    return out


def _not_ready_yet(ctx: Ctx, entry_id: str) -> str:
    """How to get a library text that is not on the reader's shelf yet.

    Conditional on what the caller holds, because `quote_build` is offered only where the
    chat scope was granted and this tool is offered to every connector: telling a host
    with the library alone to call a tool it does not have is a dead end.
    """
    page = f"{ctx.press_at.rstrip('/')}/library/{quote(entry_id)}"
    return (
        f"Not on the reader's shelf yet. If quote_build is among your tools, call it with "
        f"this id; otherwise send them this library link, on a line of its own: {page}"
    )


def _too_many_playlists(ctx: Ctx) -> str:
    from ..accounts import MOST_PLAYLISTS

    return (
        f"The reader has {MOST_PLAYLISTS} playlists, the most we keep. Ask them to delete one "
        "on targum first."
    )


def open_library_text(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    entry = catalogue_module.by_id(str(args.get("id") or ""))
    if entry is None:
        return {"error": "No text in the library has that id."}
    mine, shared = _shelf(ctx)
    built = _by_source([*mine, *shared]).get(catalogue_module._key(entry.source))
    row = _entry_row(entry, built)
    row["blurb"] = entry.blurb
    row["how_to_open"] = (
        "Give the reader the link in `reader`." if built else _not_ready_yet(ctx, entry.id)
    )
    return row


def _when(clock: int) -> str:
    """A page's millisecond clock as a date and time the model can read and count from."""
    return datetime.fromtimestamp(clock / 1000, tz=UTC).isoformat(timespec="minutes")


#: How many sentences `sentences_with` hands back, and how long one may be.
SENTENCES_WITH = 5
SENTENCE_CHARS = 300


def _json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _lemma(token: object) -> str:
    return str(token.get("lemma") or "").lower() if isinstance(token, dict) else ""


def sentences_with(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    """Sentences from the reader's own shelf, and the shared one, where a word appears.

    For the contrast a Russian aspect question wants (targum-internal#259): aspect is
    decided by context far more often than by rule, so the useful answer to "why сказал
    and not говорил?" sets a sentence with one beside a sentence with the other — from
    texts the reader has, which the model cannot otherwise see into. Read off each text's
    own annotation, by dictionary form, so every inflected form is found. Spends nothing.
    """
    lemma = str(args.get("lemma") or "").strip().lower().replace("\u0301", "")
    language = str(args.get("language") or "")
    if not lemma:
        return {"error": "Name the word by its dictionary form."}
    mine, shared = _shelf(ctx)
    found: list[dict[str, str]] = []
    for home, rows in ((ctx.home, mine), (ctx.library.shared, shared)):
        for row in rows:
            if len(found) >= SENTENCES_WITH:
                break
            if language and str(row.get("language") or "") != language:
                continue
            folder = home / str(row.get("name") or "")
            tokens = _json(folder / "annotation.json").get("tokens") or {}
            wanted = {
                sid: sorted({str(t.get("surface") or "") for t in words if _lemma(t) == lemma})
                for sid, words in tokens.items()
                if isinstance(words, list) and any(_lemma(t) == lemma for t in words)
            }
            if not wanted:
                continue
            segments = _json(folder / "segments.json").get("segments") or []
            for segment in segments:
                if len(found) >= SENTENCES_WITH:
                    break
                sid = str(segment.get("id") or "")
                if sid not in wanted:
                    continue
                found.append(
                    {
                        "sentence": str(segment.get("text") or "")[:SENTENCE_CHARS],
                        "as": " ".join(form for form in wanted[sid] if form),
                        "title": str(row.get("title") or ""),
                        "reader": str(row.get("reader") or ""),
                    }
                )
    return {"lemma": lemma, "count": len(found), "sentences": found}


def search_my_shelf(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    query = str(args.get("query") or "").lower()
    # A language named holds both halves to it. None named: the reader's own texts are
    # all theirs and all listed, and the shared shelf is held to the conversation's
    # language, which is where an Italian talk reached a Hebrew reader.
    named = str(args.get("language") or "").strip()
    language = _language_asked(ctx, args) if named else ""
    starter = _language_asked(ctx, args)
    mine, shared = _shelf(ctx)
    # When each text was last opened and finished, from the reader's own sync. The
    # model answered "what was the last targum I read?" with "the list does not keep
    # times" (2026-09-08) — the store always had, and the tool left them out. Newest
    # opened first, so the answer to that question is the first row.
    times = ctx.store.read_times(ctx.person.id) if ctx.store and ctx.person else {}
    now = int(datetime.now(tz=UTC).timestamp() * 1000)
    rows = []
    ordered = sorted(
        [*mine, *shared],
        key=lambda row: -times.get(str(row.get("document") or ""), {}).get("opened", 0),
    )
    for row in ordered:
        written = str(row.get("language") or "").split("-")[0].lower()
        if language and written != language:
            continue
        if (
            row.get("shared")
            and starter
            and written
            and written not in _FAMILY.get(starter, {starter})
        ):
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
                **_read_when(times.get(str(row.get("document") or "")), now),
            }
        )
    return {"count": len(rows), "now": _when(now), "texts": rows}


def _read_when(clocks: dict[str, int] | None, now: int) -> dict[str, Any]:
    """`last_opened`, `days_since_opened` and `finished` for one row; a text never
    opened on any device says so rather than dating itself."""
    if not clocks or not clocks.get("opened"):
        return {"last_opened": "", "days_since_opened": None, "finished": ""}
    opened = clocks["opened"]
    return {
        "last_opened": _when(opened),
        "days_since_opened": max(0, (now - opened) // 86_400_000),
        "finished": _when(clocks["finished"]) if clocks.get("finished") else "",
    }


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
            {
                "lemma": lemma,
                "status": _STATUS.get(-1 if status is None else status, "learning"),
                "band": band,
            }
            for lemma, status, band, _ in recent
            if band not in ("name", "number")
        ],
    }


#: A word's status as a word rather than the store's number: 9 known, 1 to 3 learning,
#: 0 ignored. A host handed "status": 2 guesses what it means, and says the guess.
_STATUS: dict[int, str] = {9: "known", 1: "learning", 2: "learning", 3: "learning", 0: "ignored"}


def my_progress(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    """Real counts, and nothing a model could say back as a placement or a streak.

    `Level.state()` carries the current streak and the rung the ledger reaches, for the
    page's own use. Neither goes to a model: the current streak is refused outright
    (design.md §12, "The streak is the longest one, and the current one is refused"),
    and a rung handed to a host is a level said to a reader — which is the one thing
    every contract forbids, on a surface where nothing of ours can stop it being said.
    """
    state = ctx.level.state()
    return {
        "language": state["language"],
        "known": state["known"],
        "learning": state["learning"],
        "days": state["days"],
        "longest_run_of_days": state["longest"],
        "sections": state["sections"],
        "texts": state["texts"],
        "ladder": {"name": state["ladder"]["name"], "note": state["ladder"]["note"]},
    }


def suggest_next(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    language = str(args.get("language") or ctx.level.language)
    register = str(args.get("register") or "")
    minutes = args.get("max_minutes")
    limit = max(1, min(int(args.get("limit") or 5), 10))
    # Catalogue ids to leave out — what the page says the reader has finished, which
    # only the browser knows (2026-09-11: the top ten were all finished scenes, and
    # skipping after the cut left nothing). Applied before the cut, so the next one
    # that fits is always in reach.
    skip = {str(one) for one in (args.get("skip") or []) if str(one)}
    mine, shared = _shelf(ctx)
    own = _by_source(mine)
    built = _by_source([*mine, *shared])
    # The reader's interests, as far as the shelf says them: the registers of the
    # texts they brought in themselves. A text in one of those is ranked a little ahead
    # of an equal text in another (2026-09-11: "a text that fits your level and
    # interests, without needing to chat").
    liked = {str(row.get("register") or "") for row in mine if row.get("register")}
    candidates: list[tuple[tuple[float, float], dict[str, Any]]] = []
    for entry in catalogue_module.everything():
        key = catalogue_module._key(entry.source)
        if entry.language.split("-")[0] != language.split("-")[0]:
            continue
        if key in own or entry.id in skip:
            continue
        if register and entry.register.value != register:
            continue
        if minutes is not None and entry.minutes > int(minutes):
            continue
        row = _entry_row(entry, built.get(key))
        known = row.get("known_share")
        tilt = 1.0 if entry.register.value in liked else 0.0
        if known is not None:
            row["known_line"] = level_module.words_in_ten(float(known))
            # Said the way the card says it, because a host repeats `because` and the rule
            # is never a percentage (prompts.py). `reason` keeps the number for the page's
            # own line, which `because_in` draws.
            row["because"] = (
                row["known_line"] or f"You know {round(float(known) * 100)}% of its words."
            )
            row["reason"] = {"key": "suggest.known", "share": round(float(known) * 100)}
            rank = (0.0, -(float(known) + 0.1 * tilt))
        elif entry.difficulty:
            # Which Hebrew only for Hebrew: every other language's catalogue rows carry
            # the modern register too, and "modern Hebrew" was said of an Italian talk
            # (2026-09-15). No minutes: the card already says them beside this line.
            which = ""
            if language.split("-")[0] == "he" and entry.register.value in ("modern", "biblical"):
                which = f" {entry.register.value.capitalize()} Hebrew."
            row["because"] = f"A learner looks up {entry.difficulty}% of its words.{which}"
            row["reason"] = {
                "key": "suggest.looked-up",
                "share": entry.difficulty,
                "register": which.strip() and entry.register.value,
            }
            rank = (1.0, float(entry.difficulty) - 10.0 * tilt)
        else:
            row["because"] = "Not measured yet."
            row["reason"] = {"key": "suggest.unmeasured"}
            rank = (2.0, 0.0)
        candidates.append((rank, row))
    candidates.sort(key=lambda pair: pair[0])
    return {"suggestions": [row for _, row in candidates[:limit]]}


def because_in(row: dict[str, Any], language: str) -> str:
    """A suggestion's reason in `language`, for the reader (targum-internal#287). The
    English `because` stays on the row for the model, which reads the tool's output."""
    from ..serve import said_in

    reason = row.get("reason") or {}
    key = str(reason.get("key") or "")
    if key == "suggest.known":
        return said_in(
            language, "suggest.known", "You know {share}% of its words.", share=reason["share"]
        )
    if key == "suggest.looked-up":
        said = said_in(
            language,
            "suggest.looked-up",
            "A learner looks up {share}% of its words.",
            share=reason["share"],
        )
        register = str(reason.get("register") or "")
        if register == "modern":
            said += " " + said_in(language, "suggest.modern-hebrew", "Modern Hebrew.")
        elif register == "biblical":
            said += " " + said_in(language, "suggest.biblical-hebrew", "Biblical Hebrew.")
        return said
    if key == "suggest.unmeasured":
        return said_in(language, "suggest.unmeasured", "Not measured yet.")
    return str(row.get("because") or "")


def language_code(value: str) -> str:
    """The code for a language the model named, however it named it.

    The model sends what the refusal said back to it: "English", then "english", then
    "en". Each refusal was a whole model round trip on a turn the reader was waiting on
    (targum-internal#270, a "tech news" turn on 2026-09-14), so a name, a code in any
    case and a regional tag all mean the code. Anything else comes back as it was, and
    the refusal still names what is offered.
    """
    said = value.strip()
    if not said:
        return ""
    code = said.replace("_", "-").split("-")[0].lower()
    if language_name(code) != code:
        return code
    by_name = {language_name(tag).lower(): tag for tag, _ in INTO}
    return by_name.get(said.lower(), said)


#: The fields of `Job.state()` that are dollars. The page never draws them as money, and
#: a host would: it paraphrases whatever it is handed, and "there is no money anywhere
#: inside the product" (design.md §12, "A cost is credits") covers what a host says on
#: targum's behalf. So they stay on the in-app card's state and never leave for a host.
DOLLAR_FIELDS = ("estimate", "meanings", "translation", "transcription")


def _for_host(state: dict[str, Any]) -> dict[str, Any]:
    """A job's state as a host may have it: no dollars, and the credits it uses."""
    out = {key: value for key, value in state.items() if key not in DOLLAR_FIELDS}
    out["credits"] = credits_for(float(state.get("seconds") or 0)) if state.get("audio") else 0
    return out


def quote_build(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    """Price a text for nothing, and leave a job the reader can press to start.

    The same door `/prepare` opens for the Add page, with the same refusals in the same
    words: the pair of languages has to be one an upload has been taken end to end in,
    and one this account said it reads. What comes back is `Job.state()` verbatim —
    the page draws its card from that, and the card's button posts `/build`.
    """
    from ..serve import Job

    offered = {code for code, _ in INTO}
    reads = (ctx.reads & offered) or offered
    wanted = language_code(str(args.get("to") or "")) or (
        "en" if "en" in reads else sorted(reads)[0]
    )
    if wanted not in offered:
        names = ", ".join(f"{language_name(code)} ({code})" for code in sorted(offered))
        return {"error": f"targum translates into {names}."}
    if wanted not in reads:
        return {"error": f"{language_name(wanted)} is not in the reader's profile."}

    payload: dict[str, Any] = {**BUILD_OPTIONS, "to": wanted}
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
                "note": "It is on their shelf already. Give the reader the link in `reader`.",
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
        # A link or a fetcher's identifier (`gutenberg:…`, `wikisource:…`). Anything else
        # would be read as a file on the server — including a path with a colon in it,
        # which the looser check this replaced let through. `ingest.fetchable` is the
        # one rule the Add page's door keeps too.
        from ..ingest import fetchable

        if not fetchable(source) and catalogue_module.matching(source) is None:
            if urlparse(source).scheme in ("http", "https"):
                return {"error": "That link has no address in it."}
            return {"error": "Give a link, or a library text's id."}
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
    if ctx.press_at:
        # No page of ours to draw a card on, so the press comes back as a link to one
        # (targum-internal#80). The seam is unchanged: `/build/<id>` shows the quote and
        # one button, `Handler._build` is still the only path to `Library.claim`, and
        # what the model holds is a URL rather than a way to spend.
        state = _for_host(state)
        state["open"] = f"{ctx.press_at}/build/{job.id}"
        return {
            "quote": state,
            "note": (
                "Give the reader the link in `open`, on a line of its own, and say in ONE "
                "sentence what the text is. If `credits` is more than 0, say it uses that "
                "many credits; never say money. They confirm it on targum's own page, and "
                "you cannot. Don't describe the page, don't tell them to press anything, "
                "and don't call this a quote, a price or a build."
                if state["stage"] == "ready"
                else "We can't get this text ready now. Tell the reader why in one plain "
                "sentence, from `error` or `blocked`."
            ),
        }
    return {
        "quote": state,
        # One sentence, because the card says the rest (targum-internal#236). Asked to say
        # what the text is and how long it takes, the model narrated the card beside it —
        # its length, the share the reader knows, "press it" — and a reply that handed
        # over a text ran to three sentences and 58 Hebrew words on 2026-09-15.
        "note": (
            "The page shows the reader a card from this with a button; pressing it gets "
            "the text ready, and you cannot press it. The card already shows how long it "
            "is and how much of it the reader knows. Introduce it in ONE sentence — what "
            "the text is, in their time if you say how long, never in money, never as a "
            "build — and stop: do not repeat the card or tell them to press it. One card "
            "in a reply."
            if state["stage"] == "ready"
            else (
                "This cannot be made ready now; the card says why. Tell the reader plainly, "
                "in one sentence."
            )
        ),
    }


#: How many texts one set may hold: design.md §12's cap, and the playlist's own.
MOST_IN_SET = 20


def _folder_of(reader: str) -> str:
    """A reader's folder name from its address, `/reader/<name>/reader/index.html`."""
    return unquote(reader.removeprefix("/reader/").split("/")[0])


def quote_set(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    """Price a named set of texts as one, and leave one press for all of them (#365).

    design.md §12, "A playlist is swiped, and one press takes the set": each item is an
    ordinary quote — `quote_build`, with its refusals in its words — and the set is a
    playlist holding their jobs. The press is `/set/<id>` on a page of ours, and it claims
    every text or none. A playlist or channel *address* is still refused item by item by
    its door's own guard; a set is a list somebody wrote out, never somebody else's list.
    """
    if ctx.person is None or ctx.store is None:
        return {"error": "A set needs an account."}
    items = args.get("items") or []
    if not isinstance(items, list) or not items:
        return {"error": "Give the texts for the set: a link or a library id each."}
    if len(items) > MOST_IN_SET:
        return {"error": f"A set holds at most {MOST_IN_SET} texts. Send fewer."}
    name = " ".join(str(args.get("name") or "").split()) or "Playlist"
    # Each item quoted as the chat quotes one, with no press link of its own: the set's
    # is the only press.
    alone = replace(ctx, press_at="")
    held: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    for raw in items:
        item = raw if isinstance(raw, dict) else {"source": str(raw)}
        asked = {key: item[key] for key in ("source", "catalogue_id", "to") if item.get(key)}
        said = quote_build(alone, asked)
        if "in_library" in said:
            # A published translation beats a machine one; quote that instead.
            said = quote_build(alone, {**asked, "catalogue_id": said["in_library"]["id"]})
        title = " ".join(str(item.get("title") or "").split())
        if said.get("already_built"):
            reader = str(said.get("reader") or "")
            held.append({"title": title or _folder_of(reader), "reader": _folder_of(reader)})
            continue
        quote = said.get("quote")
        if not quote or quote.get("stage") != "ready":
            why = said.get("error") or (quote or {}).get("error") or (quote or {}).get("blocked")
            refused.append(
                {"source": asked.get("source") or asked.get("catalogue_id") or "", "why": why}
            )
            continue
        credits = round(float(quote.get("seconds") or 0) / 60) if quote.get("audio") else 0
        held.append(
            {
                "title": title or str(quote.get("title") or ""),
                "job": str(quote["id"]),
                "known_line": quote.get("known_line") or "",
                "seconds": quote.get("seconds") or 0,
                "audio": bool(quote.get("audio")),
                "credits": credits,
            }
        )
    if not held:
        return {"error": "Nothing in that set can be made now.", "refused": refused}
    made = ctx.store.make_playlist(
        ctx.person.id, name, made_by="connector" if ctx.press_at else "chat"
    )
    if made is None:
        return {"error": _too_many_playlists(ctx)}
    for one in held:
        ctx.store.add_to_playlist(
            ctx.person.id,
            int(made["id"]),
            one["title"],
            reader=one.get("reader"),
            job=one.get("job"),
        )
    link = f"{ctx.press_at}/set/{made['id']}"
    return {
        "set": {
            "id": made["id"],
            "name": made["name"],
            "items": held,
            "credits": sum(int(one.get("credits") or 0) for one in held),
            "refused": refused,
        },
        "open": link,
        "note": (
            "Give the reader the link in `open`, on a line of its own, and say in ONE "
            "sentence what the set is. They press it on targum's own page, where every "
            "text is listed and they can untick any; you cannot press it. Name anything "
            "in `refused` in one short sentence, with its reason."
        ),
    }


def quote_conversation(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    """Write this conversation down and price reading it back — the same card as a build.

    Always this conversation, from `ctx`, never one named in an argument. The file lands
    in the reader's own home under `chats/`, addressed by path so its cache key carries
    the owner (`chat/transcript.py` says why that matters), and the quote is `Library.
    prepare` on it like any other text: the English is carried, so nothing is bought
    for translation; the words are glossed like any text's. The reader presses.
    """
    from ..serve import Job
    from . import transcript

    if ctx.store is None:
        return {"error": "No store to read the conversation from."}
    reader = "you"
    if ctx.person is not None:
        reader = str(ctx.store.profile(ctx.person).get("name") or "") or "you"
    # In the conversation's own language (targum-internal#280): `ctx.level` is read in the
    # language the conversation was opened in (`Chats.context`).
    held_in = (ctx.level.language or "he").split("-")[0].lower()
    into = ctx.language
    path, kept, dropped = transcript.write(ctx.store, ctx.home, ctx.chat_id, reader, held_in, into)
    if kept < 2:
        return {
            "error": f"Nothing to read back yet. Talk a little first, in {language_name(held_in)}.",
            "lines": kept,
        }
    job = Job(
        id=secrets.token_hex(8),
        source=str(path),
        # Into the language the reader reads (targum-internal#243): the "= " lines
        # were written in it, and the pipeline carries them whole.
        options={
            **BUILD_OPTIONS,
            "to": into,
            "from": held_in,
        },
        owner=ctx.person_id,
        admin=ctx.admin,
        home=ctx.home,
    )
    ctx.library.jobs[job.id] = job
    ctx.library.remember(job)
    ctx.library.prepare(job)
    ctx.library.remember(job)
    ctx.store.chat_saved(ctx.chat_id, job.id)
    state = job.state()
    note = (
        f"The page shows the reader a card for {kept} lines; the reader presses it, and the "
        "conversation opens on their shelf as a text with every word tappable. Say so in "
        "ONE sentence, in their time, never in money, and stop: the card says the rest."
    )
    if dropped:
        note += (
            f" {dropped} of their turns had no {language_name(held_in)} recast and are not in "
            "the record; "
            "say so plainly."
        )
    return {"quote": state, "lines": kept, "dropped": dropped, "note": note}


def credits_for(seconds: float) -> int:
    """Seconds of audio or video in the unit the reader is told: a credit is a minute
    (design.md §12, "A cost is credits, and a credit is a minute")."""
    from ..serve import SECONDS_A_CREDIT

    return round(max(0.0, float(seconds or 0)) / SECONDS_A_CREDIT)


#: What a balance is said beside, wherever one is: the rate, so a credit is never a
#: number somebody has to convert from memory.
CREDIT_RATE = (
    "One credit is one minute of audio or video: {month} credits a month is {hours} hours. "
    "Chatting and reading text are included."
)


def my_hours(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    """The month's credits, in the only unit a reader is ever told about.

    Named `my_hours` because hosts already connected call it by that name; what it says
    is credits (design.md §12, 2026-09-23), and its title says so too.
    """
    allowed = ctx.library.upload_seconds
    used = (
        ctx.store.hours_used(ctx.person_id, ctx.library._month_from())
        if ctx.store is not None
        else 0.0
    )
    month = None if allowed is None else credits_for(allowed)
    return {
        "credits_used": credits_for(used),
        "credits_a_month": month,
        "credits_left": None if allowed is None else credits_for(max(0.0, allowed - used)),
        "month_ends": ctx.library._month_ends(),
        "note": (
            "No monthly limit on this account."
            if allowed is None
            else CREDIT_RATE.format(month=month, hours=f"{allowed / 3600:g}")
        )
        + " Say it in credits, never in money.",
    }


# -- playlists (targum-internal#364) ---------------------------------------------------


def _playlist_link(ctx: Ctx, playlist_id: int, items: list[dict[str, Any]]) -> str:
    """Where a playlist opens: its first ready text, carrying the list and its place in
    it so the reader swipes on to the next (`playlists.js`'s `listed`), or the playlists
    page while nothing in it is ready. Absolute over the connector, like every link."""
    first = next((one for one in items if one.get("reader") and not one.get("failed")), None)
    if first is None:
        return f"{ctx.press_at.rstrip('/')}/playlists"
    at = reader_url(str(first["reader"]), ctx.press_at)
    return f"{at}?list={playlist_id}&at={int(first.get('position') or 0)}"


def my_playlists(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    """The reader's playlists, and what is in each, in order, each with its own link."""
    if ctx.store is None or ctx.person is None:
        return {"error": "This needs an account."}
    out = []
    for row in ctx.store.playlists(ctx.person.id):
        found = ctx.store.playlist(ctx.person.id, int(row["id"])) or {}
        items = list(found.get("items") or [])
        out.append(
            {
                "name": row["name"],
                "open": _playlist_link(ctx, int(row["id"]), items),
                "texts": [
                    {
                        "title": item["title"],
                        "reader": (
                            reader_url(str(item["reader"]), ctx.press_at)
                            if item.get("reader")
                            else None
                        ),
                        "ready": bool(item.get("reader")) and not item.get("failed"),
                    }
                    for item in items
                ],
            }
        )
    return {"count": len(out), "playlists": out}


def add_to_playlist(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    """Put a text already on the reader's shelf into one of their playlists, making the
    playlist if there is none by that name. Nothing is got ready or spent, and a text
    that is not on the shelf is refused: `quote_set` is the door for one that isn't."""
    if ctx.store is None or ctx.person is None:
        return {"error": "This needs an account."}
    wanted = " ".join(str(args.get("playlist") or "").split())
    text = str(args.get("text") or "").strip()
    if not wanted or not text:
        return {"error": "Name the playlist and the text."}
    mine, shared = _shelf(ctx)
    # Only what is on this reader's shelf, by the name search_my_shelf gave it: the
    # model cannot put an address or somebody else's text into a list by naming it.
    row = next((one for one in [*mine, *shared] if str(one["name"]) == text), None)
    if row is None:
        return {
            "error": "That text isn't on the reader's shelf. Find it with search_my_shelf, "
            "or use quote_set for one that isn't ready yet."
        }
    person = ctx.person.id
    existing = next(
        (one for one in ctx.store.playlists(person) if one["name"].lower() == wanted.lower()),
        None,
    )
    if existing is None:
        existing = ctx.store.make_playlist(
            person, wanted, made_by="connector" if ctx.press_at else "chat"
        )
        if existing is None:
            return {"error": _too_many_playlists(ctx)}
    added = ctx.store.add_to_playlist(
        person, int(existing["id"]), str(row.get("title") or text), reader=text
    )
    if added is None:
        from ..accounts import MOST_IN_PLAYLIST

        return {
            "error": f"That playlist holds {MOST_IN_PLAYLIST} texts, the most it can. "
            "Start another."
        }
    found = ctx.store.playlist(person, int(existing["id"])) or {}
    return {
        "playlist": existing["name"],
        "added": str(row.get("title") or text),
        "open": _playlist_link(ctx, int(existing["id"]), list(found.get("items") or [])),
    }


# -- finding things out there -----------------------------------------------------------

#: Hebrew letters, for saying how much of a page is Hebrew before anybody pays to read it.
_HEBREW = frozenset(chr(code) for code in range(0x05D0, 0x05EB))

#: How many searches one turn may make. Three was "a question answered; more is
#: browsing", and it was also what a reader called stingy (2026-09-08): a Hebrew question
#: on the whole web is often two searches to find the ground and two more to find the
#: text. Six is a cent apiece at most, inside the turn's own meter.
WEB_SEARCH_USES = 6

#: Where the search would stand if it could, and it cannot.
#:
#: The search wants to look from Israel: an unlocalised search run from a server in
#: Germany answers a Hebrew question with the English-language coverage of Israel rather
#: than with Israeli writing about the thing asked about. `user_location` is the API's
#: setting for exactly that, and **it does not take Israel.** Measured against the live
#: endpoint on 2026-09-08:
#:
#:     IL  400  Country code IL is not supported.
#:     CY  400  Country code CY is not supported.
#:     EG  400  Country code EG is not supported.
#:     US  200      GB  200      DE  200      (none)  200
#:
#: So this is not a value to correct, it is a door that is shut. Sending `IL` is a 400 on
#: *every* turn — the whole conversation, not the search — because the tool block is
#: rejected before the model is reached, and the reader is told the conversation could
#: not continue. Naming another country would be worse than nothing: standing in Germany
#: is the exact failure the paragraph above describes, and standing in the United States
#: is that failure with more confidence.
#:
#: Nothing is lost that was ever had. What keeps the search on Hebrew is what always kept
#: it there: the Hebrew the model searches in, and the share of Hebrew letters
#: `describe_source` counts before a source is offered. Localising on top of those was
#: the improvement; it is unavailable, and the floor is unchanged.
#:
#: Kept as a name rather than deleted so that re-adding it means reading this first.
#: `test_the_search_carries_no_country_the_api_refuses` fails if it goes back into a tool
#: block (targum-internal#126).
SEARCH_UNAVAILABLE_FROM = {"city": "Tel Aviv", "country": "IL", "timezone": "Asia/Jerusalem"}


def _known_share(ctx: Ctx | None, text: str) -> float | None:
    """`level.known_share` against this reader's known forms and the commonest words;
    None where there is nobody to measure for."""
    if ctx is None or ctx.store is None or ctx.person is None:
        return None
    forms = ctx.store.known_forms(ctx.person.id, "he") | set(hebrew_module.common_words())
    return level_module.known_share(text, forms)


def _hebrew_share(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for ch in letters if ch in _HEBREW) / len(letters)


def _licence_row(licence: str) -> dict[str, Any]:
    """The licence as stated, and what it means — recorded, never a refusal here."""
    from ..licensing import verdict

    call = verdict(licence)
    return {
        "licence": licence,
        "licence_standing": call.standing.value,
        "standing": call.standing.value,
        "corpus_exportable": call.exportable,
        "licence_note": (
            "Fine for the reader's own shelf; whether it may ever join the library is a "
            "separate question, decided at promotion and never here."
        ),
    }


def refused(ctx: Ctx | None, host: str, error: Any) -> dict[str, Any] | None:
    """Record what a failed fetch says about `host`; the answer to give if it is shut.

    Called from every place `_describe` knocks, because the first knock is not always
    the article fetch: an address is offered to the podcast reader before it is read as
    a page, and a host that refuses the box refuses that knock first. Returning `None`
    means the host is fine and it was the page that was missing.
    """
    from ..ingest import url as url_module

    shut = url_module.shut(error)
    challenge = bool(getattr(error, "challenge", False))
    via = str(getattr(error, "via", "direct"))
    if ctx is not None and ctx.store is not None:
        why = "bot check" if challenge else str(error.status or "no answer")
        ctx.store.reach(host, not shut, why, egress=via)
    if not shut:
        return None
    if challenge:
        # Not a host that did not answer: one that answered with a check a browser
        # passes and this door did not. Said as what it is, because the reader's own
        # browser will open it and "does not answer" would be false.
        return {
            "error": f"{host} runs a bot check that targum could not pass, so the page "
            "cannot be read or built here. It opens in the reader's own browser.",
            "host_shut": True,
            "challenge": True,
            "advice": "Offer something else rather than this, and say plainly that the "
            "site checks for a browser and targum is not one.",
        }
    return {
        "error": f"{host} does not answer targum. It may open in the reader's own browser; "
        "it will not open here, so nothing can be built from it.",
        "host_shut": True,
        "advice": "Offer something else rather than this, and say plainly that targum "
        "cannot reach it.",
    }


def describe_source(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    described = _describe(ctx, args)
    if "error" not in described and ctx.store is not None and described.get("kind") != "fetcher":
        # A link a reader looked at is a text the shelf did not have. Counted, with the
        # standing its licence has, so the back office can see what is one email away.
        ctx.store.want("", str(args.get("url") or ""), str(described.get("standing") or ""))
    return described


def _describe(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    """What is at the other end of a link, before anything is priced or fetched whole.

    Metadata only: a video is asked what yt-dlp knows without fetching it, a podcast
    page is read for its episode, an article is read once through the same door with
    the same size cap and SSRF guard every fetch here passes. The licence is recorded
    and the screen's flags are advice in the quote — neither refuses a reader their own
    import (targum-internal#126). What refuses is the fetch door itself: a private
    address, a page over the cap, a source the ingester does not read.
    """
    from ..audio import episode as episode_module
    from ..errors import TargumError, Unreachable, UnsupportedSource
    from ..ingest import fetch as fetchers
    from ..ingest import url as url_module
    from ..video import youtube as youtube_module

    url = str(args.get("url") or "").strip()
    if not url:
        return {"error": "Give a link."}
    if fetchers.is_identifier(url):
        scheme = url.partition(":")[0].lower()
        return {
            "kind": "fetcher",
            "scheme": scheme,
            "note": f"A {scheme} identifier — a public-domain source targum reads directly. "
            "Quote it as it is.",
            "quote_with": url,
        }
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return {"error": "That is not a link targum can follow."}

    if youtube_module.is_youtube(url):
        from .. import screen as screen_module

        try:
            info = youtube_module.describe(url)
        except TargumError as error:
            return {"kind": "video", "error": error.message}
        media = screen_module.from_ytdlp(info)
        heard = media.audio[0] if media.audio else ""
        subtitled = any(screen_module.same_language(tag, "he") for tag in media.subtitles)
        advice: list[str] = []
        if not subtitled:
            advice.append(
                "No written Hebrew subtitles, so the recording would be transcribed: it "
                f"uses about {credits_for(media.duration)} credits."
            )
        else:
            advice.append("Has Hebrew subtitles somebody wrote, so nothing is transcribed.")
        if media.audio and not any(screen_module.same_language(t, "he") for t in media.audio):
            advice.append(f"The audio track is tagged {heard}, not Hebrew.")
        elif not media.audio:
            advice.append("The audio track carries no language tag.")
        return {
            "kind": "video",
            "title": media.title,
            "seconds": round(media.duration),
            "credits": credits_for(media.duration),
            "audio_language": heard,
            "hebrew_subtitles": subtitled,
            "advice": advice,
            "quote_with": youtube_module.watch_url(url) or url,
            **_licence_row(media.licence),
        }

    from ..video import hosts as hosts_module
    from ..video import instagram as instagram_module

    try:
        reel = instagram_module.is_reel(url)
    except TargumError as error:
        return {"kind": "video", "error": error.message}
    post = instagram_module.backup(url) if instagram_module.is_post(url) else None
    if post is not None and not post.video:
        # A post of pictures: its caption is the text, free to read, and its pictures
        # are the reader's to ask for on the card — never read on the model's say.
        return {
            "kind": "post",
            "title": post.title,
            "author": f"@{post.author}" if post.author else "",
            "caption_words": len(post.caption.split()),
            "pictures": len(post.pictures),
            "advice": [
                "An Instagram post: the caption becomes the text. Its pictures are read "
                "only if the reader presses for them on the card."
            ],
            "quote_with": url,
        }
    if reel:
        from .. import screen as screen_module

        try:
            info = instagram_module.describe(url)
        except TargumError as error:
            return {"kind": "video", "error": f"{error.message} {error.hint or ''}".strip()}
        media = screen_module.from_ytdlp(info)
        said = [
            "An Instagram reel: it has no subtitles, so the recording would be transcribed. "
            f"It uses about {credits_for(media.duration or instagram_module.GUESS_S)} credits."
        ]
        if not media.duration:
            said.append(
                "Instagram did not say how long it runs, so that is counted as "
                f"{round(instagram_module.GUESS_S / 60)} minutes."
            )
        return {
            "kind": "video",
            "title": media.title.strip(),
            "seconds": round(media.duration or instagram_module.GUESS_S),
            "credits": credits_for(media.duration or instagram_module.GUESS_S),
            "audio_language": "",
            "hebrew_subtitles": False,
            "advice": said,
            "quote_with": instagram_module.home_url(url) or url,
            **_licence_row(media.licence),
        }
    from ..video import tiktok as tiktok_module

    try:
        tok = tiktok_module.is_tiktok(url)
    except TargumError as error:
        return {"kind": "video", "error": error.message}
    if tok:
        from .. import screen as screen_module

        try:
            info = tiktok_module.describe(url)
        except TargumError as error:
            return {"kind": "video", "error": f"{error.message} {error.hint or ''}".strip()}
        media = screen_module.from_ytdlp(info)
        return {
            "kind": "video",
            "title": media.title.strip(),
            "seconds": round(media.duration),
            "credits": credits_for(media.duration),
            "audio_language": "",
            "hebrew_subtitles": False,
            "advice": [
                "A TikTok: the recording would be transcribed. It uses about "
                f"{credits_for(media.duration)} credits."
            ],
            "quote_with": tiktok_module.home_url(str(info.get("webpage_url") or url)) or url,
            **_licence_row(media.licence),
        }
    named = hosts_module.host_for(url)
    if named is not None:
        # Named, and not fetched from: said as the way in that works, so the model can
        # pass it on instead of reading the login wall as an article.
        return {
            "kind": "video",
            "error": f"{named.name} doesn't let us fetch its videos. Download it and add "
            "the file on targum.",
        }

    host = (parsed.hostname or "").lower()

    # A direct link to a file, before anything reads it as a page (targum-internal#256).
    # `episode.find` fetches an address it cannot name from its suffix, and `.mp4` is one
    # — so a reader's link to a video was pulled whole, twice, and then described as
    # "file". Named here from the address, timed from its front, and never pulled.
    from ..video import is_video as is_video_file

    path = unquote(parsed.path)
    if episode_module.sounds_like_audio(url) or is_video_file(path):
        watching = is_video_file(path)
        try:
            front = url_module.opening(url)
        except Unreachable as error:
            shut = refused(ctx, host, error)
            return shut if shut is not None else {"error": error.message}
        except TargumError as error:
            return {"error": error.message}
        if ctx is not None and ctx.store is not None:
            ctx.store.reach(host, True, egress="direct")
        from ..audio.probe import timed

        seconds = timed(front.head, front.length)
        said = [
            "A video: only its sound is read, unless the pictures are kept."
            if watching
            else "A recording.",
            f"It would be transcribed, and uses about {credits_for(seconds)} credits."
            if seconds
            else "It would be transcribed, and uses a credit a minute.",
        ]
        if not seconds:
            # Said rather than guessed. The length is read for certain when the file is
            # fetched, and the quote is made from that.
            said.append("How long it runs could not be read from the link; the quote will say.")
        return {
            "kind": "recording",
            "title": Path(path).stem,
            "medium": "video" if watching else "audio",
            "content_type": front.content_type,
            "seconds": round(seconds),
            "credits": credits_for(seconds) if seconds else None,
            "megabytes": round(front.length / (1024 * 1024), 1) if front.length else None,
            "has_transcript": False,
            "advice": said,
            "quote_with": url,
            **_licence_row(""),
        }

    try:
        found = episode_module.find(url)
    except UnsupportedSource as refusal:
        return {"error": f"{refusal.message} {refusal.hint or ''}".strip()}
    except Unreachable as error:
        shut = refused(ctx, host, error)
        return shut if shut is not None else {"error": error.message}
    except TargumError as error:
        return {"error": error.message}
    if found is not None:
        return {
            "kind": "recording",
            "title": found.title,
            "seconds": round(found.seconds),
            "credits": credits_for(found.seconds) if found.seconds else None,
            "has_transcript": bool(found.transcript_url),
            "advice": [
                "Its own transcript comes with it, so nothing is transcribed."
                if found.transcript_url
                else "It would be transcribed, and uses about "
                f"{credits_for(found.seconds)} credits."
                if found.seconds
                else "It would be transcribed, and uses a credit a minute."
            ],
            "quote_with": url,
            **_licence_row(""),
        }

    try:
        got = url_module.fetch(url)
    except Unreachable as error:
        # A door that will be shut next time is worth remembering; a page that is not
        # there is not. Every host is still knocked on — the record informs what the
        # model *offers*, never what a reader may bring (targum-internal#126).
        shut = refused(ctx, host, error)
        return shut if shut is not None else {"error": error.message}
    except TargumError as error:
        return {"error": error.message}
    if ctx is not None and ctx.store is not None:
        ctx.store.reach(host, True, egress=getattr(got, "via", "direct"))
    if not got.is_html:
        return {
            "kind": "file",
            "content_type": got.content_type,
            "note": "Not a page. If it is a text or a recording, quote the link and the "
            "ingester will say whether it reads it.",
            "quote_with": url,
        }
    from ..ingest.htmltext import paragraphs_from_html

    # A paragraph here is `(kind, level, text)`, the ingester's own shape.
    body = "\n".join(text for _, _, text in paragraphs_from_html(got.text))
    words = len(body.split())
    title_match = re.search(r"<title[^>]*>(.*?)</title>", got.text, re.S | re.I)
    title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""
    share = _hebrew_share(body)
    advice = []
    if share < 0.5:
        advice.append(f"Only {round(share * 100)}% of the letters on the page are Hebrew.")
    if words < 80:
        advice.append("Very little text was found on the page.")
    # How much of it this reader already has, cheaply, before it is quoted
    # (targum-internal#244): the number for the model, the words for the reader.
    known = _known_share(ctx, body) if share >= 0.5 else None
    return {
        "kind": "article",
        "title": title,
        "words": words,
        "minutes": max(1, round(words / 130)),
        "hebrew_share": round(share, 2),
        "known_share": None if known is None else round(known, 2),
        "known_line": level_module.words_in_ten(known),
        "advice": advice,
        "quote_with": url,
        **_licence_row(""),
    }


#: How long one search waits on the publishers' feeds, all of them together. They were
#: pulled one after another, each allowed the fetch door's thirty seconds: a "tech news"
#: turn on 2026-09-14 spent 21 s in this one tool and found nothing, and nineteen feeds
#: could have held a turn for nine minutes (targum-internal#272). A feed that misses it
#: is named as late and keeps coming in behind, into the shelf below.
FEEDS_BUDGET_S = 8.0

#: How long a pulled feed is taken as what the publisher has out. A feed changes by the
#: hour, and a conversation asks again within the minute.
FEED_FRESH_S = 300.0

#: How long a feed that would not answer is left alone before it is knocked on again.
#: Short, because a host comes back; long enough that one turn's searches do not each
#: wait on the same dead one. Not `store.closed()`: a host is only marked open again by
#: a knock, so skipping the hosts on that list would keep them there for good.
FEED_FAILED_S = 120.0


class Feeds:
    """The publishers' feeds, pulled side by side and kept a few minutes.

    One per process, shared by every turn: two turns that ask at once share one pull of
    each feed rather than making two, and a feed that came in after one search gave up
    on it is there for the next.
    """

    def __init__(self, workers: int = 24) -> None:
        self.workers = workers
        self._lock = threading.Lock()
        #: url -> (monotonic time it goes stale, its items or None for a failure)
        self._kept: dict[str, tuple[float, list[Any] | None]] = {}
        self._pending: dict[str, Future[list[Any] | None]] = {}
        self._pool: ThreadPoolExecutor | None = None

    def clear(self) -> None:
        with self._lock:
            self._kept.clear()
            self._pending.clear()

    def pull(self, urls: list[str], budget: float) -> dict[str, list[Any] | None]:
        """Each feed's items, or None where it would not answer; waiting at most
        `budget` seconds for all of them. A url missing from the answer is late."""
        out: dict[str, list[Any] | None] = {}
        waiting: dict[str, Future[list[Any] | None]] = {}
        with self._lock:
            now = time.monotonic()
            for url in dict.fromkeys(urls):
                kept = self._kept.get(url)
                if kept is not None and now < kept[0]:
                    out[url] = kept[1]
                    continue
                future = self._pending.get(url)
                if future is None:
                    if self._pool is None:
                        self._pool = ThreadPoolExecutor(
                            max_workers=self.workers, thread_name_prefix="feeds"
                        )
                    future = self._pool.submit(self._fetch, url)
                    self._pending[url] = future
                waiting[url] = future
        if waiting:
            wait_for(list(waiting.values()), timeout=budget)
        for url, future in waiting.items():
            if future.done():
                out[url] = future.result()
        return out

    def _fetch(self, url: str) -> list[Any] | None:
        from ..errors import TargumError
        from ..weekly import feeds

        try:
            try:
                items: list[Any] | None = feeds.pull(url, limit=15)
                fresh_for = FEED_FRESH_S
            except TargumError:
                items, fresh_for = None, FEED_FAILED_S
            with self._lock:
                self._kept[url] = (time.monotonic() + fresh_for, items)
            return items
        finally:
            with self._lock:
                self._pending.pop(url, None)


FEEDS = Feeds()


def search_sources(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    """What the publishers this box knows have published lately, matched to a query.

    Feeds are pulled through the one outbound door and read by `weekly/feeds.py`; a
    feed that will not answer is noted and skipped rather than failing the search.
    """
    query = str(args.get("query") or "").lower().split()
    kind = str(args.get("kind") or "")
    limit = max(1, min(int(args.get("limit") or 10), 30))
    publishers = [
        one for one in sources_module.load() if one.feed and (not kind or one.kind == kind)
    ]
    if not publishers:
        return {
            "count": 0,
            "items": [],
            "note": "We don't follow any publishers yet.",
        }
    items: list[dict[str, Any]] = []
    skipped: list[str] = []
    late: list[str] = []
    pulled_by_feed = FEEDS.pull([publisher.feed for publisher in publishers], FEEDS_BUDGET_S)
    for publisher in publishers:
        if publisher.feed not in pulled_by_feed:
            late.append(publisher.key)
            continue
        pulled = pulled_by_feed[publisher.feed]
        if pulled is None:
            skipped.append(publisher.key)
            continue
        for item in pulled:
            haystack = f"{item.title} {item.summary}".lower()
            if query and not all(word in haystack for word in query):
                continue
            # What the reader would already know of it, from the hook the feed gives:
            # a title and up to four hundred characters of summary. Not the article —
            # nothing here has been fetched — so it is an estimate off an estimate, and
            # `known_share` answers None below twenty tokens rather than guessing at a
            # headline. Enough to tell two of the same day's stories apart, which is all
            # it is asked to do.
            known = _known_share(ctx, f"{item.title}\n{item.summary}")
            items.append(
                {
                    "title": item.title,
                    "link": item.link,
                    "publisher": publisher.publisher or publisher.name,
                    "kind": publisher.kind,
                    "published": item.published.isoformat() if item.published else "",
                    "seconds": round(item.seconds) if item.seconds else 0,
                    "has_transcript": bool(item.transcript),
                    "licence": publisher.licence,
                    "known_share": None if known is None else round(known, 2),
                }
            )
    # Newest first, and within a day the one this reader would get furthest into
    # (targum-internal#244, change 4b). The day is the window on purpose: news is worth
    # reading because it is today's, so a story the reader knows more of does not climb
    # over a fresher one — it only wins against the others published alongside it. An
    # entry too short to measure sorts as if it were average rather than as nothing,
    # since a headline that says little about its Hebrew is not evidence of hard Hebrew.
    items.sort(
        key=lambda row: (
            str(row["published"])[:10],
            0.5 if row["known_share"] is None else row["known_share"],
        ),
        reverse=True,
    )
    out: dict[str, Any] = {"count": len(items), "items": items[:limit]}
    if skipped:
        out["unreachable"] = skipped
    if late:
        # Still being pulled: the next search a minute from now will have them.
        out["late"] = late
    return out


def check_job(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    job = ctx.library.jobs.get(str(args.get("id") or ""))
    if job is None or job.owner != ctx.person_id:
        return {"error": "None of the reader's texts has that id."}
    # Read by a model on either surface and drawn by no page, so it never carries money.
    state = _for_host(job.state())
    if state.get("reader"):
        folder = str(state["reader"]).removesuffix("/reader/index.html")
        state["open"] = reader_url(folder, ctx.press_at)
    return state


REGISTERS = [register.value for register in catalogue_module.Register]
KINDS = [kind.value for kind in catalogue_module.Kind]


def record_turn(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    """Check one line the reader wrote elsewhere, and keep what they got wrong.

    **The one tool that spends** (design.md §12, "A scope is a press that lasts"). It
    takes what the reader wrote and never the host's correction: targum recasts it on its
    own model against its own contract, so the record has one judge whichever surface a
    line came from. See `chat/check.py` for why that is worth paying for.

    Claimed and settled like a turn of conversation, on the same rails and the same eight
    hours, because it is one — narrowed to the reader's own line, with no reply's worth
    added, because the host wrote the reply and targum did not.
    """
    wrote = str(args.get("wrote") or "").strip()
    language = str(args.get("language") or "he").split("-")[0].lower()
    if not wrote:
        return {"error": "Give the line the reader wrote."}
    if ctx.person is None or ctx.store is None:
        return {"error": "This needs an account."}
    if language not in hebrew_module.TALKED:
        return {"error": _not_yet(language)}
    if not hebrew_module.written_in(wrote, language):
        # Nothing to judge, so nothing is claimed: a question in English, a link, a line
        # of numbers. design.md §12: only a line in the language is recast.
        return {
            "checked": False,
            "note": (
                f"That line isn't in {language_name(language)}, so there was nothing to "
                "check and nothing was used. Answer it as the contract says, with the "
                "recast written yourself."
            ),
        }
    if hebrew_module.words_in(wrote) > check_module.MOST_WORDS:
        return {
            "error": (
                f"That is more than {check_module.MOST_WORDS} words. Send one line at a "
                "time — a paragraph recast as a sentence teaches nothing."
            )
        }
    if ctx.ask is None:
        return {"error": "We can't check lines right now. Carry on without the check."}
    from ..serve import Job

    job = Job(
        id=f"check-{ctx.person.id}-{secrets.token_urlsafe(8)}",
        source=f"check:{language}",
        title="",
        estimate=check_module.MOST_PER_LINE,
        # The reader's own words and nothing else. An in-app turn adds a reply's worth
        # because targum writes the reply; here the host wrote it.
        seconds=hebrew_module.seconds_for(hebrew_module.words_in(wrote)),
        stage="working",
        owner=ctx.person.id,
        home=ctx.home,
        admin=ctx.admin,
        kind="chat",
    )
    ctx.library.jobs[job.id] = job
    ctx.library.remember(job)
    refused = ctx.library.claim_turn(job)
    if refused:
        return {"error": refused}
    try:
        said = check_module.recast(ctx, language, wrote, ctx.ask())
    except Exception:  # noqa: BLE001 - the model reads this, and a host repeats it
        ctx.library.release(job)
        return {"error": "We couldn't check that line. Nothing was used. Carry on without it."}
    job.spent = ctx.usage.cost()
    ctx.library.settle(job)
    if said is None:
        return {"error": "We couldn't read that line back, so nothing was kept."}
    kept = check_module.keep(ctx, language, wrote, said, "connector")
    # And the language goes on, if it was not already (2026-09-23). This is the first
    # moment anything of the reader's is written in it, and it happens under `chat` —
    # the one scope whose words on the approval page say it keeps what they write. Asking
    # to practise wrote nothing and needed no scope; writing a line does both.
    turned_on = ctx.store.also_learning(ctx.person.id, language)
    return {
        "checked": True,
        "recast": said.hebrew,
        "meaning": said.english,
        "why": said.why,
        "changed": bool(kept),
        "learning": turned_on,
        "note": (
            "Show the reader this recast and the reason, in their own conversation. "
            "We'll remember it and bring it back on targum."
            if kept
            else "That line was already right. Say so briefly and carry on."
        ),
    }


def _not_yet(language: str) -> str:
    """The refusal for a language targum does not talk in, naming the ones it does."""
    talks = sorted(language_name(one) for one in hebrew_module.TALKED)
    said = ", ".join(talks[:-1]) + f" and {talks[-1]}" if len(talks) > 1 else talks[0]
    return f"We talk in {said}, not yet in {language_name(language)}."


def elsewhere(language: str = "he", gloss: str = "English") -> str:
    """What a host is told on top of the contract, because there the host writes the
    replies and targum does not (design.md §12, "The connector talks by the contract",
    2026-09-23). Three things differ from targum's own page and nothing else does.

    In the conversation's own language, and quoting the contract's own rule word for
    word: it said Hebrew to an Italian conversation, and named a rule ("never a Hebrew
    line without its line") that no contract says in those words.
    """
    named = language_name(language)
    article = "an" if named[:1] in "AEIOU" else "a"
    return f"""You are holding this conversation for targum, inside another app. The contract
below is the one targum's own chat is held to, and you keep to it, with three changes,
because here you write the replies and there is no targum page to draw them:

- The meaning lines. On targum's page every "= " line is folded under its {named} and a
  tap opens it; you cannot fold, so the tap here is the reader asking. Write the {named}
  lines, and the "= " line only when the reader asks what something means or asks for
  the translation — for the lines they asked about, or for every line from then on if
  that is what they asked for, until they say otherwise. A new word you bring in still
  gets its meaning, on one "= " line after the reply naming only the new words. In your
  first reply, say once, in one short {named} line with its meaning, that they can ask
  for the translation at any time. This overrides this rule below, and nothing else:
  "Never {article} {named} line without its {gloss} line."
- The reader's own line. When record_turn is among your tools, call it with every line
  the reader writes in {named}, exactly as they wrote it, before you answer, and make
  the recast it returns your "> " line and its why your "~ " line — targum's judgement,
  not yours, because that is the one we remember and bring back to them on targum.
  Never send it your own correction. A line they wrote in another language you say in
  {named} yourself, as the contract says, and nothing is kept. Without record_turn,
  write the recast yourself.
- Doors. Where the contract speaks of a path the page draws as a door, give the link
  the tool returned, on a line of its own.

Everything else holds: the vocabulary below, the length, the recast, never a level."""


#: The Hebrew one, which is the one most hosts are handed.
ELSEWHERE = elsewhere("he")


def how_to_talk(ctx: Ctx, args: dict[str, Any]) -> dict[str, Any]:
    """targum's own talk contract and this reader's ledger, for a host to hold to.

    Free and read-only. It is the system prompt targum's chat is given
    (`session.py`, `contract_for` and `ledger_block`), handed to a model that is not
    targum's so a conversation held in Claude or ChatGPT is held to the same standard:
    one contract, both surfaces (design.md §12, 2026-09-23). No exemplars, which are
    drawn per turn and would be stale by the second one.
    """
    language = str(args.get("language") or "he").split("-")[0].lower()
    if language not in hebrew_module.TALKED:
        return {"error": _not_yet(language)}
    # What the reader is *already* learning does not gate this (2026-09-23). It did, and
    # an account set to Hebrew alone met "je veux pratiquer mon français" with a refusal
    # naming its own configuration — turning the plainest possible statement of what
    # somebody is learning into the reason they could not. Talking costs nothing and
    # writes nothing, so there is nothing here to protect: the ledger comes back empty in
    # a language they have no words in yet, which is true and is the point.
    store, person_id = ctx.store, ctx.person_id
    # The contract is offered to every connector, the words only to one granted
    # `record`: a reader who shared only the library still gets the conversation in
    # Hebrew, graded to the commonest words rather than their own.
    shared = store is not None and person_id is not None and ctx.sees_record
    returning: hebrew_module.Returning | None = None
    if store is not None and person_id is not None and shared:
        level = level_module.snapshot(store, person_id, language)
        # The ledger holds whatever a reader tapped, and "and", "the", digits and single
        # letters are in it; a host told these are the words they know writes with them.
        known = hebrew_module.for_host(
            hebrew_module.known_words(store, person_id, language), language
        )
        # One slice of the ledger a day, so a conversation that asks twice is told the
        # same words both times.
        seed = int(time.time() // 86400)
        back = hebrew_module.bring_back(store, person_id, language, seed=seed)
        returning = hebrew_module.Returning(
            new=hebrew_module.for_host(back.new, language),
            learning=hebrew_module.for_host(back.learning, language),
            nearly=hebrew_module.for_host(back.nearly, language),
            known=hebrew_module.for_host(back.known, language),
            phrases=back.phrases,
        )
        rules = hebrew_module.recurring(
            store.slips(person_id, language=language, limit=hebrew_module.SLIPS_READ)
        )
    else:
        level, known, rules = replace(level_module.EMPTY, language=language), [], []
    common = hebrew_module.for_host(hebrew_module.common_words(language=language), language)
    gloss = language_name(ctx.language)
    return {
        "language": language,
        "contract": "\n\n".join(
            [
                elsewhere(language, gloss),
                hebrew_module.contract_for(language, gloss),
                hebrew_module.ledger_block(level, known, common, returning, rules, shared=shared),
            ]
        ),
    }


#: The language a search is held to, as a schema property: the conversation's own
#: unless another is named.
_LANGUAGE_FILTER = {
    "type": "string",
    "description": 'A language code, or "all". Leave it out for the language the reader '
    "is learning here.",
}

#: The language to translate into, as quote_build and each item of quote_set take it.
_TRANSLATE_INTO = {
    "type": "string",
    "enum": [code for code, _ in INTO],
    "description": "The code of the language to translate into: "
    + ", ".join(f"{code} for {language_name(code)}" for code, _ in INTO)
    + ". Leave it out for the language the reader reads.",
}

REGISTRY: tuple[Tool, ...] = (
    Tool(
        "search_library",
        "Search targum's public library: texts with published translations, in the "
        "language the reader is learning here unless you name another. Filter by register "
        "(which Hebrew), kind, how much a learner looks up, or reading time. Each result "
        "says whether it is already on the reader's shelf and, if so, gives its link and "
        "how much of it they know. Read only.",
        _schema(
            {
                "query": {
                    "type": "string",
                    "description": "Words to match in title, author, blurb.",
                },
                "language": _LANGUAGE_FILTER,
                "register": {"type": "string", "enum": REGISTERS},
                "kind": {"type": "string", "enum": KINDS},
                "max_looked_up_percent": {"type": "integer", "minimum": 0, "maximum": 100},
                "max_minutes": {"type": "integer", "minimum": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            }
        ),
        search_library,
        title="Search the library",
    ),
    Tool(
        "open_library_text",
        "One library text by id: what it is, whether it is on the reader's shelf, the "
        "link to open it if it is, and how to get it if it isn't. Read only.",
        _schema({"id": {"type": "string"}}, ("id",)),
        open_library_text,
        title="Look at a library text",
    ),
    Tool(
        "search_my_shelf",
        "The reader's own texts and the shared starter shelf, newest opened first, each "
        "with its link, which languages it opens in, chapters ready, how much of it they "
        "know, when they last opened it and when they finished it. The starter shelf is "
        "held to the language the reader is learning here unless you name one. Read only.",
        _schema({"query": {"type": "string"}, "language": _LANGUAGE_FILTER}),
        search_my_shelf,
        scope="record",
        title="Search my texts",
    ),
    Tool(
        "sentences_with",
        "Up to five sentences from the texts on the reader's shelf, and the shared one, in "
        "which a word appears, found by its dictionary form so every inflected form counts; "
        "each with the form it takes there and the text it is from. For setting two uses "
        "side by side — a Russian verb beside its aspect partner — from what the reader "
        "has. Read only.",
        _schema({"lemma": {"type": "string"}, "language": {"type": "string"}}, ("lemma",)),
        sentences_with,
        scope="record",
        title="Sentences with a word",
    ),
    Tool(
        "my_vocabulary",
        "The reader's word list in one language: how many words they know, how many they "
        "are still learning, and the ones they marked most recently, each as known, "
        "learning or ignored. Read only.",
        _schema(
            {
                "language": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            }
        ),
        my_vocabulary,
        scope="record",
        title="My words",
    ),
    Tool(
        "my_progress",
        "Real counts of what the reader has done: words known, days read, their longest "
        "run of days, sections finished. Say these counts; never say a level or a rung, "
        "and never a streak in progress. Read only.",
        _schema({}),
        my_progress,
        scope="record",
        title="My progress",
    ),
    Tool(
        "suggest_next",
        "Library texts to read next, in the language the reader is learning, leaving out "
        "the texts they brought in themselves. Some are on the shared shelf and open "
        "straight away (`on_shelf`, with a `reader` link); the rest need getting ready "
        "first. Ranked gentlest first, by how much of each they know where that is "
        "measured and by how much a learner looks up otherwise, each with one reason you "
        "can say as it is. Read only.",
        _schema(
            {
                "language": {"type": "string"},
                "register": {"type": "string", "enum": REGISTERS},
                "max_minutes": {"type": "integer", "minimum": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 10},
            }
        ),
        suggest_next,
        scope="record",
        title="What to read next",
    ),
    Tool(
        "quote_build",
        "For one text: a link (article, podcast episode, YouTube, Instagram or TikTok "
        "video, Gutenberg or Wikisource id) or a library id. Free. Returns its length, how "
        "much of it the reader knows, the credits it uses, and a link the reader opens to "
        "confirm; you cannot confirm it. For two or more texts use quote_set. A playlist, "
        "channel or profile address is refused; give single items.",
        _schema(
            {
                "source": {"type": "string", "description": "A link or fetcher id."},
                "catalogue_id": {"type": "string", "description": "A library text's id."},
                "to": _TRANSLATE_INTO,
            }
        ),
        quote_build,
        scope="chat",
        title="Get a text ready",
        writes=True,
        open_world=True,
    ),
    Tool(
        "describe_source",
        "What is at a link before you offer it: a YouTube, Instagram or TikTok video "
        "(length, the credits it uses, whether it has Hebrew subtitles somebody wrote), a "
        "podcast episode (length, credits, whether a transcript comes with it), or an "
        "article (words, minutes, how much is Hebrew). Metadata only; nothing is fetched "
        "whole and nothing is used.",
        _schema({"url": {"type": "string"}}, ("url",)),
        describe_source,
        title="Look at a link",
        open_world=True,
    ),
    Tool(
        "search_sources",
        "What the Hebrew publishers targum follows have put out lately, matched to words "
        "in the title or summary. News, podcasts and videos, newest first, each with its "
        "link to look at or offer. Read only.",
        _schema(
            {
                "query": {"type": "string"},
                "kind": {"type": "string", "enum": list(sources_module.KINDS)},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30},
            }
        ),
        search_sources,
        title="What publishers put out",
        open_world=True,
    ),
    Tool(
        "quote_conversation",
        "Write this conversation down as a Hebrew text with its English and estimate "
        "reading it back, free to call. The page shows a card; the reader presses it and "
        "the conversation opens on their shelf with every word tappable and on their ledger.",
        _schema({}),
        quote_conversation,
        title="Keep this conversation",
        writes=True,
    ),
    Tool(
        "quote_set",
        "For two or more texts at once, as one playlist the reader swipes through: give "
        "it a name and up to 20 items, each a link or a library id. Free. Use it whenever "
        'the reader wants several texts ("find me some reels", "make me a playlist"); use '
        "quote_build for one. Returns every text with the credits it uses, the total, "
        "what could not be got ready and why, and one link the reader opens to confirm "
        "them all together; you cannot confirm it.",
        _schema(
            {
                "name": {"type": "string", "description": "What to call the playlist."},
                "items": {
                    "type": "array",
                    "maxItems": MOST_IN_SET,
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string", "description": "A link or fetcher id."},
                            "catalogue_id": {"type": "string"},
                            "title": {"type": "string", "description": "A short title."},
                            "to": _TRANSLATE_INTO,
                        },
                        "additionalProperties": False,
                    },
                },
            },
            ("name", "items"),
        ),
        quote_set,
        needs_account=True,
        scope="chat",
        title="Get a playlist ready",
        writes=True,
        open_world=True,
    ),
    Tool(
        "my_playlists",
        "The reader's playlists and the texts in each, with a link to open each one. Read only.",
        _schema({}),
        my_playlists,
        needs_account=True,
        scope="record",
        title="My playlists",
    ),
    Tool(
        "add_to_playlist",
        "Add a text that is already on the reader's shelf (its name from search_my_shelf) "
        "to one of their playlists, making the playlist if needed. Free. For a link that "
        "isn't ready yet, use quote_set.",
        _schema(
            {
                "playlist": {"type": "string", "description": "The playlist's name."},
                "text": {
                    "type": "string",
                    "description": "The text's name, exactly as search_my_shelf gave it.",
                },
            },
            ("playlist", "text"),
        ),
        add_to_playlist,
        needs_account=True,
        # A write, so the scope that says it writes: `record` is read-only on the approval
        # page, and a list the reader did not make is more than they agreed to there.
        scope="chat",
        title="Add to a playlist",
        writes=True,
        idempotent=True,
    ),
    Tool(
        "my_hours",
        "How many credits the reader has left this month, how many they get, and when "
        "they come back. One credit is one minute of audio or video; chatting and reading "
        "text are included. Say credits, never money. Read only.",
        _schema({}),
        my_hours,
        scope="record",
        title="My credits",
    ),
    Tool(
        "record_turn",
        "Check one line the reader wrote in the language they are practising, exactly as "
        "they wrote it, and remember what they got wrong. Send what the READER wrote, never "
        "your own correction of it: targum checks it itself. Returns targum's recast, its "
        "meaning and one line of why — show them that. A line that was already right keeps "
        "nothing, and a line in another language is not checked. Chatting is included in "
        "the reader's plan.",
        _schema(
            {
                "wrote": {
                    "type": "string",
                    "description": "The line the reader wrote, exactly as they wrote it.",
                },
                "language": {
                    "type": "string",
                    "description": "The code of the language they were writing in.",
                },
            },
            ("wrote",),
        ),
        record_turn,
        spends=True,
        needs_account=True,
        scope="chat",
        elsewhere=True,
        title="Check what I wrote",
        writes=True,
    ),
    Tool(
        "how_to_talk",
        "Call this first whenever the reader wants to talk, chat or practise in the "
        "language they are learning. Returns targum's own conversation rules and, where "
        "the reader shared them, their words: talk to them in that language, graded to "
        "what they know, with the translation when they ask for it. Hold to it for the "
        "rest of the conversation. Free and read only.",
        _schema(
            {
                "language": {
                    "type": "string",
                    "description": "The code of the language to talk in; Hebrew if not given.",
                },
            }
        ),
        how_to_talk,
        scope="",
        elsewhere=True,
        title="How to talk with me",
    ),
    Tool(
        "check_job",
        "Where a text the reader is getting ready has got to, by the id quote_build "
        "returned, with its link once it is ready. Read only.",
        _schema({"id": {"type": "string"}}, ("id",)),
        check_job,
        scope="record",
        title="Where a text has got to",
    ),
)

BY_NAME: dict[str, Tool] = {tool.name: tool for tool in REGISTRY}


def anthropic_tools(*, web_search: bool = False) -> list[dict[str, Any]]:
    """The registry in the shape the Messages API takes.

    With `web_search`, Anthropic's server-side search rides along, over the whole web.
    The model does not run it and neither do we: the API does, and what it finds comes
    back as blocks in the reply. Anything it surfaces is still described and quoted
    through the same doors as a pasted link.

    Until 2026-09-08 the search was held to `sources.allowed_domains()`, with a card a
    reader could press to widen one turn. The list's failure was never emptiness but
    substitution: a Hebrew Wikipedia article asked for and four newspapers handed back,
    because Wikipedia was not on the list and ynet was, and neither the model nor the
    reader could see why. The card fixed that at the price of a second turn every time,
    and a reader called it stingy. What keeps the search on Hebrew is the Hebrew the
    model searches in and the Hebrew share `describe_source` counts before anything is
    offered; the list added a failure mode and not a floor.

    **Nothing that spends is offered here**, and the chat is the surface that rule was
    written for: a tool that spends on a model's decision makes the pricing page a lie.
    `record_turn` exists for a conversation held somewhere else, where the host wrote the
    reply and only the judgement is ours. In *this* conversation targum already recasts
    every line in its own contract and writes the slip itself (`chat/record.py`), so
    offering it here would record the same mistake twice and charge for it twice.
    """
    tools: list[dict[str, Any]] = [
        {"name": tool.name, "description": tool.description, "input_schema": tool.schema}
        for tool in REGISTRY
        if not tool.spends and not tool.elsewhere
    ]
    if web_search:
        tools.append(
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": WEB_SEARCH_USES,
                # No `user_location`: the API does not take Israel, and a block carrying
                # one it refuses fails the turn rather than the search. See
                # `SEARCH_UNAVAILABLE_FROM`. No `allowed_domains` either; see above.
            }
        )
    return tools


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
    except Exception:  # noqa: BLE001 - the model reads this, and a host repeats it
        # Never the exception itself: over the connector a host says it to the reader,
        # and "KeyError: 'reader'" is not a sentence. The log has the traceback.
        import logging

        logging.getLogger(__name__).exception("tool %s failed", name)
        return json.dumps({"error": "Something went wrong on our side. Try again later."}), True
    return json.dumps(out, ensure_ascii=False), "error" in out
