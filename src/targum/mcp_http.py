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
#:
#: **It says how to talk, not only what the tools are** (2026-09-23). Until then a reader
#: who asked Claude for Hebrew was answered in English about Hebrew, because nothing here
#: said otherwise; `how_to_talk` carries targum's own contract, and this is what sends a
#: host to it. design.md §12, "The connector talks by the contract".
INSTRUCTIONS = (
    "targum is a reading app for people learning Hebrew. These tools search the public "
    "library and, where the reader allowed it, their texts and word list. When the reader "
    "wants to talk or practise in a language they're learning, call how_to_talk first and "
    "keep to what it returns for the whole conversation, translation included: only when "
    "they ask. Nothing you call gets a text ready or charges the reader: quote_build and "
    "quote_set return a link, and the reader confirms on targum's own page. Give them the "
    "link on its own line; don't describe the page or tell them to press anything, and "
    "don't call it a quote or a price. A cost is in credits, never money. For several "
    "texts at once, use quote_set. When a tool returns an error, tell the reader in one "
    "plain sentence what happened and what they can do, and don't retry the same call."
)

#: The prompts a connector offers by name, which is how a reader reaches targum without
#: having to describe what they want (targum-internal#80, notes 11 and 17). Ours are
#: fixed; a reader's own are added beside them once they can write one.
#:
#: **Each is said in the reader's voice**, because a host drops it into the conversation
#: as the reader's own message, and **each names the tools its text needs**, so a
#: connection that was not granted them is not offered a prompt that sends its host to a
#: tool it does not have (`prompt_shapes`).
PROMPTS: tuple[dict[str, Any], ...] = (
    {
        "name": "what-next",
        "description": "Find something to read next, chosen for the words you know.",
        "arguments": [],
        "needs": ("suggest_next", "search_my_shelf"),
        "says": (
            "What should I read next on targum? Call suggest_next, then search_my_shelf "
            "to see what I'm in the middle of, and offer me two or three with a sentence "
            "each about why. Give me the links."
        ),
    },
    {
        "name": "talk",
        "description": "Talk in Hebrew, at your own words, with the translation when you ask.",
        "arguments": [],
        "needs": ("how_to_talk",),
        "says": (
            "Talk with me in Hebrew. Call how_to_talk first and hold to what it returns "
            "for the whole conversation, then open with one short line."
        ),
    },
    {
        "name": "drill",
        "description": "Practise the words you're still learning, in sentences you've read.",
        "arguments": [],
        "needs": ("my_vocabulary", "sentences_with"),
        "says": (
            "Call my_vocabulary and pick one or two of my words marked learning, then "
            "sentences_with for them, and help me practise those words in the sentences "
            "I actually met them in. Never set me a test, never keep score."
        ),
    },
    {
        "name": "read-with-me",
        "description": "Read a text line by line, with the grammar explained as you go.",
        "arguments": [{"name": "text", "description": "What to read", "required": False}],
        "needs": ("search_library",),
        "says": (
            "Find {text} with search_my_shelf or search_library and read it with me a "
            "few lines at a time: the Hebrew, what it means, and what is worth noticing "
            "in the grammar. Let me set the pace."
        ),
        "unnamed": "a text I'd like",
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

    Each carries a `title`, which is what a host shows a person, and its annotations —
    so Claude says "Get a text ready" rather than "Quote build".
    """
    return [
        {
            "name": tool.name,
            "title": tool.title or tool.name,
            "description": tool.description,
            "inputSchema": tool.schema,
            "annotations": {"title": tool.title or tool.name, **tool.hints()},
        }
        for tool in tools
    ]


def prompt_shapes(
    mine: list[dict[str, Any]] | None = None, tools: set[str] | None = None
) -> list[dict[str, Any]]:
    """The prompts as `prompts/list` says them — everything but what they actually say.

    targum's set, then the reader's own beneath it (note 17). A reader's own name can
    never take one of ours: `_prompts` puts ours first and drops a later collision, so
    somebody who writes a `drill` of their own gets ours and is not quietly given a
    different thing under a name they recognise.

    Only those whose tools the caller holds, when `tools` is given: `drill` sends a host
    to my_vocabulary, and a connection without the record would be offering a prompt that
    ends in "there is no tool called my_vocabulary here".
    """
    return [
        {key: one[key] for key in ("name", "description", "arguments") if key in one}
        for one in _prompts(mine, tools)
    ]


def _prompts(
    mine: list[dict[str, Any]] | None, tools: set[str] | None = None
) -> list[dict[str, Any]]:
    """Ours and theirs, ours first, one name each.

    A reader's own prompt is one sentence saying what they want, so it is both the
    description a host lists and the message it sends — there is no second field to
    write and nothing gained by asking for one.
    """
    # A name is taken whether or not it is offered, so a reader's own `drill` never
    # stands in for ours on a connection that was not granted ours.
    taken = {one["name"] for one in PROMPTS}
    out = [
        one
        for one in PROMPTS
        if tools is None or all(need in tools for need in one.get("needs", ()))
    ]
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
    if method in ("prompts/list", "prompts/get"):
        held = {tool.name for tool in connector.exposed(scopes, person=person)}
        if method == "prompts/list":
            return _result(request_id, {"prompts": prompt_shapes(mine, held)})
        return _result(
            request_id,
            _prompt(str(params.get("name") or ""), mine, held, params.get("arguments")),
        )
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


def _prompt(
    name: str,
    mine: list[dict[str, Any]] | None = None,
    tools: set[str] | None = None,
    arguments: Any = None,
) -> dict[str, Any]:
    """One prompt, as the message a host drops into its own conversation, with its
    arguments written in where it has any."""
    found = next((one for one in _prompts(mine, tools) if one["name"] == name), None)
    if found is None:
        raise RpcError(INVALID_PARAMS, f"There is no prompt called {name}.")
    says = str(found["says"])
    given = arguments if isinstance(arguments, dict) else {}
    for argument in found.get("arguments") or []:
        key = str(argument["name"])
        value = " ".join(str(given.get(key) or "").split())[:200]
        if f"{{{key}}}" in says:
            said = f'"{value}"' if value else str(found.get("unnamed") or "it")
            says = says.replace(f"{{{key}}}", said)
    return {
        "description": found["description"],
        "messages": [
            {"role": "user", "content": {"type": "text", "text": says}},
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
    ctx = connector.context(
        library,
        store,
        person,
        press_at=address,
        ask=ask,
        sees_record=scopes is None or oauth.granted(scopes, "record"),
    )
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
        # Never the exception's own words: a host says what it is handed, and a class name
        # and a message are not a sentence for a reader. The log has the traceback.
        import logging

        logging.getLogger(__name__).exception("mcp request failed", exc_info=broke)
        return _failed(
            message.get("id"), INTERNAL_ERROR, "Something went wrong on our side. Try again later."
        )


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
