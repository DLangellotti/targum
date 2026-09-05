"""targum's tools for Claude Desktop or Claude Code, over stdio (targum-internal#80, #216).

The chat runs on one registry — `chat/tools.py` — declared as data: a name, a description,
a JSON schema, a function. This serves that same list to a client the server does not own,
so a reader who already talks to Claude somewhere else can ask it about their shelf.

**Read-only, plus a quote.** What is exposed is every tool that spends nothing:
the library measured against the reader's words, their shelf, their ledger, a suggestion,
a build's state, a link described, the publishers' feeds, and a text priced. A quote over
MCP is information — the press that starts a build stays on the page where the card is,
because a client whose consent UI targum does not control would otherwise be a way round
`Library.claim`. `quote_conversation` is not here: it needs a conversation on the page, and
over MCP there is none.

**The local machine's own reader.** This runs beside the reader's own `targum serve`,
against the same output directory and the same store, as the machine's single signed-out
person — the same footing the command line stands on. A remote server with OAuth, for a
box with accounts, is the version #80 describes and is not this one: it needs a token
that names a person, and that is a separate piece of work.

The `mcp` SDK is an optional extra (`uv sync --extra mcp`), so a plain install carries
nothing for it and this module imports it only when asked.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import level as level_module
from .chat import tools as tools_module
from .errors import TargumError

if TYPE_CHECKING:
    from .accounts import Store
    from .serve import Library

#: Tools that need a conversation on the page, and so have nothing to stand on here.
NOT_OVER_MCP = frozenset({"quote_conversation"})

#: What a JSON schema type is called in Python, for the signature the SDK reads.
_TYPES: dict[str, type] = {"string": str, "integer": int, "number": float, "boolean": bool}


def exposed() -> list[tools_module.Tool]:
    """The registry, minus anything that spends or needs the page."""
    return [
        tool
        for tool in tools_module.REGISTRY
        if not tool.spends and not tool.needs_consent and tool.name not in NOT_OVER_MCP
    ]


def context(library: Library, store: Store | None) -> tools_module.Ctx:
    """The machine's own reader: nobody signed in, every language offered."""
    from .translate.prompts import INTO, READING

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
