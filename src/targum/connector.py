"""targum's tools for a client targum does not own (targum-internal#80, #216).

The chat runs on one registry — `chat/tools.py` — declared as data: a name, a
description, a JSON schema, four flags and a function. This shapes that same list for
somebody else's model, so a reader who already talks to Claude or ChatGPT can ask it
about their shelf.

**Two halves, and this module is the part they share.** `targum mcp` serves the registry
over stdio to a client on this machine, as the machine's single signed-out person — the
same footing the command line stands on. `mcp_http.py` serves it over HTTP to a client
on the internet, as whoever a token names. What is common is here: which tools a caller
may see (`exposed`), and the `Ctx` they answer from (`context`).

**Ownership is built, never argued.** `context` reads the home, the ladder, the languages
and `admin` from the store, off a person a token named. Nothing a client sends reaches
any of them. That rule is `chat/tools.py`'s and it is what makes the registry safe to
hand to a client whose behaviour targum cannot see.

**A quote is information; a scope is a press that lasts.** The press that starts a build
stays on a targum page — a quote comes back with a link to one. Spending without a press
per job is allowed for exactly one scope, granted by the reader on targum's approval
page, and design.md §12 (2026-09-22) is where that is written down. Until a tool sets
`spends`, the filter here refuses everything that would.

The `mcp` SDK is an optional extra (`uv sync --extra mcp`) and only the stdio half needs
it, so a plain install carries nothing for it and this module imports it only when asked.
The remote half speaks JSON-RPC over the server targum already has and needs no SDK at
all — which is also why the box does not install one.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import level as level_module
from . import oauth
from .chat import tools as tools_module
from .errors import TargumError

if TYPE_CHECKING:
    from .accounts import Person, Store
    from .serve import Library

#: Tools that need a conversation on the page, and so have nothing to stand on here.
NOT_OVER_MCP = frozenset({"quote_conversation"})

#: What a JSON schema type is called in Python, for the signature the SDK reads.
_TYPES: dict[str, type] = {"string": str, "integer": int, "number": float, "boolean": bool}


def exposed(scopes: str | None = None, *, person: Person | None = None) -> list[tools_module.Tool]:
    """What this caller may see of the registry.

    Three filters, and which apply depends on who is asking.

    Always: nothing that needs the page (`quote_conversation` has no conversation to read
    back), and nothing that spends unless the scope consenting to it was granted. That
    second clause is design.md §12, "A scope is a press that lasts" — before 2026-09-22 it
    read "nothing that spends, full stop", and the whole of what changed is that one
    scope can now say otherwise.

    `scopes` is the token's scope string, or `None` for a caller that has no token —
    stdio, and the Anthropic SDK. None means the whole registry, because the reader there
    is whoever started the process; it is emphatically not "no scopes", which would be an
    empty list of tools.

    `needs_account` drops what can only answer emptily to nobody. Over stdio `Ctx.person`
    is None by design, and a tool offered there that cannot work is worse than one that
    is not offered.
    """
    out = []
    for tool in tools_module.REGISTRY:
        if tool.needs_consent or tool.name in NOT_OVER_MCP:
            continue
        if tool.needs_account and person is None and scopes is None:
            continue
        if scopes is not None:
            if tool.scope and not oauth.granted(scopes, tool.scope):
                continue
            if tool.spends and not oauth.granted(scopes, oauth.SPENDING_SCOPE):
                continue
        elif tool.spends:
            # No token, so nobody has consented to anything: the stdio connector keeps
            # the posture it shipped with.
            continue
        out.append(tool)
    return out


def context(
    library: Library,
    store: Store | None,
    person: Person | None = None,
    press_at: str = "",
    ask: Callable[[], Any] | None = None,
    sees_record: bool = True,
) -> tools_module.Ctx:
    """Who the tools are answering, built by the server and never from an argument.

    With no person this is the machine's own reader — nobody signed in, every language
    offered — which is what `targum mcp` serves over stdio and what the command line
    stands on.

    With one, it is that account: their home, their ladder, the languages they said they
    read and are learning, and whether the per-account rails apply. Every one of those is
    read here, from the store, off a token that named them. `admin` especially: it waives
    the spend rails, and a request that could carry it would be a request that could
    waive them.
    """
    from .translate.prompts import INTO, READING

    if person is None:
        return tools_module.Ctx(
            person=None,
            home=library.home(None),
            library=library,
            store=store,
            chat_id="",
            level=level_module.EMPTY,
            reads={code for code, _ in INTO},
            learning={code for code, _ in READING},
        )
    reads = store.reads(person.id) if store is not None else set()
    learning = store.learning(person.id) if store is not None else set()
    return tools_module.Ctx(
        person=person,
        home=library.home(person),
        library=library,
        store=store,
        chat_id="",
        # The ladder is per language and a reader may be on several. Hebrew is the one
        # every reader has, so it is what a tool that names no language is measured
        # against; `my_progress` takes one and re-reads it for whichever it is given.
        level=(
            level_module.snapshot(store, person.id, "he")
            if store is not None
            else level_module.EMPTY
        ),
        reads=reads or {code for code, _ in INTO},
        learning=learning or {code for code, _ in READING},
        admin=store.is_admin(person.email) if store is not None else False,
        # What they *said* they read, which is not `reads` — that answers "everything"
        # for somebody who has said nothing, and a rule picking one language out of it
        # lands on Russian. `session.py` reads it the same way.
        said_reads=reads if store is not None else None,
        # Set only by the remote connector, which has no page of ours to draw a card on.
        press_at=press_at,
        # And how to reach targum's own model, for the one tool that spends. The chat
        # never sets this: a turn there has a client already.
        ask=ask,
        sees_record=sees_record,
    )


def callable_for(tool: tools_module.Tool, ctx: tools_module.Ctx) -> Callable[..., str]:
    """One registry tool as a Python function whose signature says what its schema says.

    The SDK derives a tool's input schema from the function it is given, so the schema
    the chat declares is turned into a signature: every property a keyword parameter with
    its type, required ones without a default. What comes back is the tool's own JSON,
    as text, the way the chat's model sees it.
    """
    properties: dict[str, Any] = dict(tool.schema.get("properties") or {})
    required = set(tool.schema.get("required") or [])
    parameters = []
    annotations: dict[str, Any] = {}
    for name, spec in properties.items():
        kind = _TYPES.get(str(spec.get("type") or "string"), str)
        annotations[name] = kind if name in required else kind | None
        parameters.append(
            inspect.Parameter(
                name,
                inspect.Parameter.KEYWORD_ONLY,
                default=inspect.Parameter.empty if name in required else None,
                annotation=annotations[name],
            )
        )
    annotations["return"] = str

    def call(**arguments: Any) -> str:
        given = {key: value for key, value in arguments.items() if value is not None}
        text, _failed = tools_module.run(tool.name, given, ctx)
        return text

    call.__name__ = tool.name
    call.__doc__ = tool.description
    call.__signature__ = inspect.Signature(parameters, return_annotation=str)  # type: ignore[attr-defined]
    call.__annotations__ = annotations
    return call


def build(library: Library, store: Store | None) -> Any:
    """An MCP server carrying the exposed tools, ready to run over any transport."""
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as error:
        raise TargumError(
            "The connector needs the mcp package.", "Install it: uv sync --extra mcp"
        ) from error
    ctx = context(library, store)
    server = MCPServer(
        "targum",
        instructions=(
            "targum is a reading app for people learning Hebrew. These tools read the "
            "reader's own shelf and ledger and the library; none of them spends money. A "
            "quote is information — the reader starts a build on targum's own page."
        ),
    )
    for tool in exposed():
        server.add_tool(callable_for(tool, ctx), name=tool.name, description=tool.description)
    return server


def serve(out: Path, store_path: Path | None = None) -> None:
    """Run over stdio until the client hangs up — what `targum mcp` does."""
    from .accounts import Store
    from .serve import Library, default_store

    keeping = Store(store_path or default_store())
    library = Library(out, store=keeping)
    build(library, keeping).run("stdio")


def describe() -> str:
    """The exposed tools, one line each — for `targum mcp --list`."""
    return "\n".join(f"{tool.name}: {tool.description}" for tool in exposed())


__all__ = ["build", "callable_for", "context", "describe", "exposed", "serve"]

# Kept importable without the SDK: nothing above this line imports `mcp`.
_ = json
