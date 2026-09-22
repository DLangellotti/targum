"""The connector over HTTP: JSON-RPC 2.0 at `/mcp` (targum-internal#80).

**Why this is hand-written and not the SDK's transport.** `serve.py` is a
`BaseHTTPRequestHandler` behind a `ThreadingHTTPServer`, and the MCP SDK's
streamable-HTTP transport is an ASGI application. Mounting one on the other means a
second process, a second install on a box that carries no `mcp` extra, a second thing to
keep alive and a second place a token would have to be checked. What it would buy is
about two hundred lines. The spec allows a plain `application/json` reply to a POST
instead of an SSE stream, and twelve short tools have nothing to stream — so this speaks
the protocol directly, on the server targum already runs, behind the auth targum already
has.

**What is implemented.** `initialize` with version negotiation, `tools/list`,
`tools/call`, `prompts/list`, `prompts/get`, `ping`, and the notifications a client
sends and expects no answer to. `GET /mcp` is 405: there is no server-initiated stream
here, and saying so plainly is better than holding a socket open that will never carry
anything.

**Sessions are deliberately not implemented.** The spec's `Mcp-Session-Id` exists for
servers holding per-connection state, and this one holds none: every call is answered
out of a `Ctx` built from the token on that request. A stateless server is one that can
be restarted mid-conversation without a client noticing, which is what a box that
deploys by restarting wants.

**A failed tool is not a failed request.** JSON-RPC errors are for a request that was
malformed or named something that does not exist; a tool that raised is a 200 whose
result carries `isError`, because the model is supposed to read it and try something
else. `tools.run` already returns exactly that pair, and this is the first caller that
does not throw the second half away.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from . import connector, oauth
from .chat import tools as tools_module

if TYPE_CHECKING:
    from .accounts import Person, Store
    from .serve import Library

#: JSON-RPC 2.0 §5.1. The codes are the spec's; the sentences are ours, and they are read
#: by a client's log rather than by a reader — `serve` says what a *person* is shown.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

#: What the server says it is, in the client's connector list.
SERVER_NAME = "targum"

#: What the host is told this server can do. No `resources` and no `logging`: claiming a
#: capability and then answering `method not found` is worse than not claiming it.
CAPABILITIES: dict[str, Any] = {"tools": {"listChanged": False}, "prompts": {"listChanged": False}}

#: How a client is told what this is for, once, at `initialize`. The same job the chat's
#: system prompt does, in the space a connector gets.
INSTRUCTIONS = (
    "targum is a reading app for people learning Hebrew. These tools read the reader's "
    "own shelf and ledger and the public library. A quote is information: the reader "
    "starts a build by pressing the link a quote comes back with, on targum's own page, "
    "and you cannot press it for them. Hand them the link rather than describing it."
)

#: The prompts a connector offers by name, which is how a reader reaches targum without
#: having to describe what they want (targum-internal#80, notes 11 and 17). Ours are
#: fixed; a reader's own are added beside them once they can write one.
PROMPTS: tuple[dict[str, Any], ...] = (
    {
        "name": "what-next",
        "description": "Find something to read next, chosen for the words you know.",
        "arguments": [],
        "says": (
            "Ask targum what this reader should read next. Call suggest_next, then "
            "search_my_shelf to see what they are already in the middle of, and offer "
            "two or three with a sentence each about why. Hand over the links."
        ),
    },
    {
        "name": "drill",
        "description": "Work on the words you marked and have not come back to.",
        "arguments": [],
        "says": (
            "Call my_vocabulary for the words this reader is still learning, then "
            "sentences_with for one or two of them, and practise those words in the "
            "sentences they actually met them in. Never set a test, never keep score."
        ),
    },
    {
        "name": "read-with-me",
        "description": "Read a text line by line, with the grammar explained as you go.",
        "arguments": [{"name": "text", "description": "What to read", "required": False}],
        "says": (
            "Find this text with search_my_shelf or search_library and read it with the "
            "reader a few lines at a time: the Hebrew, what it means, and what is worth "
            "noticing in the grammar. Let them set the pace."
        ),
    },
)


class RpcError(Exception):
    """A request JSON-RPC itself refuses, as opposed to a tool that failed."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _result(request_id: Any, payload: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}


def _failed(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def tool_shapes(tools: list[tools_module.Tool]) -> list[dict[str, Any]]:
    """The registry in the shape `tools/list` takes.

    `inputSchema`, not `input_schema`: the same dictionaries the Anthropic API is handed
    under a different key, which is most of what the two protocols disagree about.
    """
    return [
        {"name": tool.name, "description": tool.description, "inputSchema": tool.schema}
        for tool in tools
    ]


def prompt_shapes(mine: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The prompts as `prompts/list` says them — everything but what they actually say.

    targum's set, then the reader's own beneath it (note 17). A reader's own name can
    never take one of ours: `_prompts` puts ours first and drops a later collision, so
    somebody who writes a `drill` of their own gets ours and is not quietly given a
    different thing under a name they recognise.
    """
    return [
        {key: one[key] for key in ("name", "description", "arguments") if key in one}
        for one in _prompts(mine)
    ]


def _prompts(mine: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Ours and theirs, ours first, one name each.

    A reader's own prompt is one sentence saying what they want, so it is both the
    description a host lists and the message it sends — there is no second field to
    write and nothing gained by asking for one.
    """
    out = list(PROMPTS)
    taken = {one["name"] for one in out}
    for one in mine or []:
        name = str(one.get("name") or "")
        if not name or name in taken:
            continue
        taken.add(name)
        says = str(one.get("says") or "")
        out.append({"name": name, "description": says[:200], "arguments": [], "says": says})
    return out


def handle(
    message: dict[str, Any],
    *,
    library: Library,
    store: Store | None,
    person: Person | None,
    scopes: str | None,
    address: str = "",
    ask: Any = None,
) -> dict[str, Any] | None:
    """Answer one JSON-RPC message, or None where the protocol says to answer nothing.

    A notification — a message with no `id` — gets no reply, which is the one place where
    returning nothing is correct rather than a bug. `notifications/initialized` is the
    common one and arrives on every connection.
    """
    if message.get("jsonrpc") != "2.0":
        raise RpcError(INVALID_REQUEST, "This server speaks JSON-RPC 2.0.")
    method = message.get("method")
    if not isinstance(method, str):
        raise RpcError(INVALID_REQUEST, "A request names a method.")
    request_id = message.get("id")
    params = message.get("params")
    params = params if isinstance(params, dict) else {}

    if request_id is None:
        # A notification. Nothing here needs to act on one, and a client that sends an
        # unknown one is not doing anything wrong — the spec says to ignore it.
        return None

    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": oauth.protocol_version(params.get("protocolVersion")),
                "capabilities": CAPABILITIES,
                "serverInfo": {"name": SERVER_NAME, "title": "targum", "version": _version()},
                "instructions": INSTRUCTIONS,
            },
        )
    if method == "ping":
        return _result(request_id, {})
    if method == "tools/list":
        return _result(request_id, {"tools": tool_shapes(connector.exposed(scopes, person=person))})
    mine = store.prompts(person.id) if store is not None and person is not None else []
    if method == "prompts/list":
        return _result(request_id, {"prompts": prompt_shapes(mine)})
    if method == "prompts/get":
        return _result(request_id, _prompt(str(params.get("name") or ""), mine))
    if method == "tools/call":
        return _call(
            request_id,
            params,
            library=library,
            store=store,
            person=person,
            scopes=scopes,
            address=address,
            ask=ask,
        )
    raise RpcError(METHOD_NOT_FOUND, f"This server has no {method}.")


def _prompt(name: str, mine: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """One prompt, as the message a host drops into its own conversation."""
    found = next((one for one in _prompts(mine) if one["name"] == name), None)
    if found is None:
        raise RpcError(INVALID_PARAMS, f"There is no prompt called {name}.")
    return {
        "description": found["description"],
        "messages": [
            {"role": "user", "content": {"type": "text", "text": str(found["says"])}},
        ],
    }


def _call(
    request_id: Any,
    params: dict[str, Any],
    *,
    library: Library,
    store: Store | None,
    person: Person | None,
    scopes: str | None,
    address: str = "",
    ask: Any = None,
) -> dict[str, Any]:
    """Run one tool, for whoever the token named.

    The allowed list is rebuilt from the scopes on every call rather than trusted from
    the last `tools/list`: a client that remembers a tool from before a scope was revoked
    would otherwise still be able to call it.
    """
    name = str(params.get("name") or "")
    allowed = {tool.name for tool in connector.exposed(scopes, person=person)}
    if name not in allowed:
        # Deliberately the same answer whether the tool does not exist or is not this
        # caller's to have: the difference is not a client's business.
        raise RpcError(INVALID_PARAMS, f"There is no tool called {name} here.")
    given = params.get("arguments")
    given = given if isinstance(given, dict) else {}
    ctx = connector.context(library, store, person, press_at=address, ask=ask)
    text, failed = tools_module.run(name, given, ctx)
    return _result(
        request_id,
        {"content": [{"type": "text", "text": text}], "isError": failed},
    )


def _version() -> str:
    """What the wheel says it is, or nothing much. A connector list shows this."""
    try:
        from importlib.metadata import version

        return version("targum")
    except Exception:  # noqa: BLE001 - a source checkout has no installed metadata
        return "0"


def answer(
    body: bytes,
    *,
    library: Library,
    store: Store | None,
    person: Person | None,
    scopes: str | None,
    address: str = "",
    ask: Any = None,
) -> tuple[int, bytes]:
    """One POST to `/mcp`, in and out.

    Returns the status and the body, so the caller does the HTTP and this does the
    protocol. `202` with an empty body is the spec's answer to a notification, and it is
    what a client waits for before it considers itself connected.

    A batch — a JSON array — is answered as one, because a client is allowed to send one
    and a server that refused would be refusing a conformant client. Notifications inside
    a batch drop out of the reply, and a batch that is nothing but notifications is
    answered `202` like a single one.
    """
    try:
        message = json.loads(body or b"")
    except json.JSONDecodeError:
        return 400, _dump(_failed(None, PARSE_ERROR, "That was not JSON."))

    asked = {
        "library": library,
        "store": store,
        "person": person,
        "scopes": scopes,
        "address": address,
        "ask": ask,
    }
    if isinstance(message, list):
        if not message:
            return 400, _dump(_failed(None, INVALID_REQUEST, "An empty batch is not a request."))
        answers = [one for one in (_one(each, asked) for each in message) if one is not None]
        return (200, _dump(answers)) if answers else (202, b"")
    if not isinstance(message, dict):
        return 400, _dump(_failed(None, INVALID_REQUEST, "A request is an object."))
    answered = _one(message, asked)
    return (200, _dump(answered)) if answered is not None else (202, b"")


def _one(message: Any, asked: dict[str, Any]) -> dict[str, Any] | None:
    """One message of a batch, with its failures turned into answers rather than raised."""
    if not isinstance(message, dict):
        return _failed(None, INVALID_REQUEST, "A request is an object.")
    try:
        return handle(message, **asked)
    except RpcError as refused:
        return _failed(message.get("id"), refused.code, refused.message)
    except Exception as broke:  # noqa: BLE001 - a client reads this, a reader never does
        # A traceback out of one tool should not take the connection down: the reader is
        # in the middle of a conversation somewhere else, and one broken call is a line
        # in it rather than the end of it. Same reasoning as `tools.run`'s own catch.
        return _failed(message.get("id"), INTERNAL_ERROR, f"{type(broke).__name__}: {broke}")


def _dump(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


__all__ = [
    "CAPABILITIES",
    "INSTRUCTIONS",
    "PROMPTS",
    "SERVER_NAME",
    "RpcError",
    "answer",
    "handle",
    "prompt_shapes",
    "tool_shapes",
]
