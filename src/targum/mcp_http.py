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
`tools/call`, `prompts/list`, `prompts/get`, `resources/list`, `resources/read`,
`resources/templates/list`, `ping`, and the notifications a client sends and expects no
answer to. `GET /mcp` is 405: there is no server-initiated stream
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
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import connector, oauth
from .chat import tools as tools_module

if TYPE_CHECKING:
    from .accounts import Person, Store
    from .serve import Library

log = logging.getLogger(__name__)

#: JSON-RPC 2.0 §5.1. The codes are the spec's; the sentences are ours, and they are read
#: by a client's log rather than by a reader — `serve` says what a *person* is shown.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
#: MCP's own code for a resource that is not there (the spec's "Resource not found").
RESOURCE_NOT_FOUND = -32002

#: What the server says it is, in the client's connector list.
SERVER_NAME = "targum"

#: What the host is told this server can do. No `logging`: claiming a capability and then
#: answering `method not found` is worse than not claiming it.
#:
#: **`resources` since 2026-10-06, for the cards.** Until then there were none to claim:
#: everything targum hands a host is a tool's answer. A card in someone else's chat
#: (design.md §12) is a page the host fetches as a resource and draws beside a tool's
#: result, which is what the MCP Apps extension asks of a server: `resources/list` and
#: `resources/read` answering for the `ui://` address a tool names. The cards are the only
#: resources there are, and a connection is listed only the cards of tools it holds
#: (`card_shapes`). No `subscribe`: a card never changes under a host that is holding it.
CAPABILITIES: dict[str, Any] = {
    "tools": {"listChanged": False},
    "prompts": {"listChanged": False},
    "resources": {"listChanged": False},
}

#: The MCP Apps extension's type for a page a host draws in a frame (SEP-1865, spec
#: 2026-01-26). Claude and ChatGPT both read it; ChatGPT's older `text/html+skybridge`
#: is not needed beside it.
CARD_TYPE = "text/html;profile=mcp-app"

#: The cards, by address: what a host lists, and the page `builder` draws for each.
#: design.md §12 allows two and both are built (2026-10-06); a third needs an entry
#: there first.
CARDS: dict[str, dict[str, str]] = {
    tools_module.BUILD_CARD: {
        "name": "build-card",
        "title": "Where a text has got to",
        "description": (
            "How far a text the reader is getting ready has got, kept current by asking "
            "check_job again, and the link to it once it is ready."
        ),
    },
    tools_module.TEXT_CARD: {
        "name": "text-card",
        "title": "Something to read",
        "description": (
            "Each text found: its title, how long it is, how much of it the reader "
            "knows, the link that opens it, and a play button where it already has a "
            "recording."
        ),
    },
}

#: Where a text card's rows say what only the card needs, in the result's `_meta` and so
#: never in what the model reads (2026-10-06): each row's door, and the short-lived
#: address of its recording where it has one (`heard`). A name of ours, prefixed with
#: our domain as MCP asks of a `_meta` key.
TEXT_CARD_META = "targum.page/texts"

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
    "quote_set return a link, and the reader confirms on targum's own page. Don't describe "
    "the page or tell them to press anything, and don't call it a quote or a price. Every "
    "link a tool returns goes on a line of its own, never inside a sentence or a list "
    "item. A cost is in credits, never money. For several "
    "texts at once, use quote_set. When a tool returns an error, tell the reader in one "
    "plain sentence what happened and what they can do, and don't retry the same call. "
    "Where check_job shows a card, the card follows the build itself: call it once and "
    "don't call it again to check. Where find_text shows cards, each card carries its "
    "text's link, so say one line rather than listing them."
)

#: The prompts a connector offers by name, which is how a reader reaches targum without
#: having to describe what they want (targum-internal#80, notes 11 and 17). Ours are
#: fixed; a reader's own are added beside them once they can write one.
#:
#: **Each is said in the reader's voice**, because a host drops it into the conversation
#: as the reader's own message, and **each names the tools its text needs**, so a
#: connection that was not granted them is not offered a prompt that sends its host to a
#: tool it does not have (`prompt_shapes`). A `scope` beside them is for a tool that
#: answers anybody but answers this prompt only with the record: `find_text` without it
#: cannot say what the reader is in the middle of (2026-10-06).
PROMPTS: tuple[dict[str, Any], ...] = (
    {
        "name": "what-next",
        "description": "Find something to read next, chosen for the words you know.",
        "arguments": [],
        "needs": ("find_text",),
        # find_text answers anybody, and "what I'm in the middle of" is the record's.
        "scope": "record",
        "says": (
            "What should I read next on targum? Call find_text, then find_text with where "
            "set to mine to see what I'm in the middle of, and offer me two or three with "
            "a sentence each about why. Give me the links."
        ),
    },
    {
        "name": "talk",
        "description": (
            "Talk in Hebrew, using the words you know, with the translation when you ask."
        ),
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
        "needs": ("find_text",),
        "says": (
            "Find {text} with find_text and read it with me a "
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
            **({"_meta": card_meta(tool.card)} if tool.card else {}),
        }
        for tool in tools
    ]


def card_meta(uri: str) -> dict[str, Any]:
    """What a tool's `_meta` says so a host draws its card (2026-10-06).

    `ui.resourceUri` is the MCP Apps extension's key and the one Claude and ChatGPT both
    read. The flat `ui/resourceUri` is the same thing in the shape the extension first
    shipped, which its own SDK still writes beside the new one for hosts that have not
    moved; it is marked for removal before the extension is final. `visibility` says the
    model may call the tool and so may the card — the card's one call is this tool, again,
    with `wait_seconds`. `openai/widgetAccessible` says the same to ChatGPT's Apps SDK,
    which asked for it separately before it read the extension's keys.
    """
    return {
        "ui": {"resourceUri": uri, "visibility": ["model", "app"]},
        "ui/resourceUri": uri,
        "openai/widgetAccessible": True,
    }


def card_shapes(tools: list[tools_module.Tool], address: str = "") -> list[dict[str, Any]]:
    """The cards as `resources/list` says them: only those of tools this caller holds.

    The same filter `prompt_shapes` applies to prompts, for the same reason. A card that
    asks for `check_job` is no use on a connection that was never granted the record, and
    listing it would be offering a page that can only fail.
    """
    held = {tool.card for tool in tools if tool.card}
    return [
        {
            "uri": uri,
            "name": card["name"],
            "title": card["title"],
            "description": card["description"],
            "mimeType": CARD_TYPE,
            "_meta": {"ui": _card_frame(uri, address)},
        }
        for uri, card in CARDS.items()
        if uri in held
    ]


def _card_frame(uri: str = tools_module.BUILD_CARD, address: str = "") -> dict[str, Any]:
    """The frame a card asks for. No border of the host's own: the card draws its own
    edge, in its own palette.

    The build card names no domain at all in its CSP: it fetches nothing (design.md
    §12), so it asks a host to open nothing. The text card names one, our own origin, in
    `resourceDomains`, which is the extension's field for media as well as images,
    scripts, styles and fonts and the only one that reaches `media-src`, because it may
    play a recording the text already has, streamed from targum.page (§12's second
    exception, 2026-10-06). It loads nothing else from there: `test_cards.py` holds the
    page to no address at all and its script to no element that loads but `<audio>`.
    Nothing in `connectDomains`: the card makes no request of its own.
    """
    origin = _origin(address)
    media = [origin] if uri == tools_module.TEXT_CARD and origin else []
    return {"csp": {"connectDomains": [], "resourceDomains": media}, "prefersBorder": False}


def _origin(address: str) -> str:
    """The scheme and host of the public address, or "" where there is none."""
    from urllib.parse import urlsplit

    parts = urlsplit(address)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""


def card_read(
    uri: str, tools: list[tools_module.Tool], language: str = "en", address: str = ""
) -> dict[str, Any]:
    """One card, whole, as `resources/read` hands it over: the page as text, its type,
    and the frame it wants.

    Refused like a tool the caller does not hold: the same answer whether the card does
    not exist or is not theirs to have.
    """
    if uri not in {shape["uri"] for shape in card_shapes(tools)}:
        raise RpcError(RESOURCE_NOT_FOUND, f"There is no resource called {uri} here.")
    from .render.builder import build_card, build_text_card

    page = build_text_card(language) if uri == tools_module.TEXT_CARD else build_card(language)
    frame = _card_frame(uri, address)
    return {"contents": [{"uri": uri, "mimeType": CARD_TYPE, "text": page, "_meta": {"ui": frame}}]}


def prompt_shapes(
    mine: list[dict[str, Any]] | None = None,
    tools: set[str] | None = None,
    scopes: str | None = None,
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
        for one in _prompts(mine, tools, scopes)
    ]


def _prompts(
    mine: list[dict[str, Any]] | None, tools: set[str] | None = None, scopes: str | None = None
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
        if (tools is None or all(need in tools for need in one.get("needs", ())))
        and (scopes is None or not one.get("scope") or oauth.granted(scopes, one["scope"]))
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
            return _result(request_id, {"prompts": prompt_shapes(mine, held, scopes)})
        return _result(
            request_id,
            _prompt(str(params.get("name") or ""), mine, held, params.get("arguments"), scopes),
        )
    if method == "resources/list":
        return _result(
            request_id,
            {"resources": card_shapes(connector.exposed(scopes, person=person), address)},
        )
    if method == "resources/templates/list":
        # Part of `resources`, so answered: there are no templates, only cards at fixed
        # addresses, and an empty list says so where `method not found` would read as a
        # broken server.
        return _result(request_id, {"resourceTemplates": []})
    if method == "resources/read":
        return _result(
            request_id,
            card_read(
                str(params.get("uri") or ""),
                connector.exposed(scopes, person=person),
                _language(store, person),
                address,
            ),
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


def _language(store: Store | None, person: Person | None) -> str:
    """The language a card's labels are drawn in: the chrome's rule for this reader
    (`strings.drawn_in`), and English for nobody in particular."""
    from .strings import SOURCE, drawn_in

    if store is None or person is None:
        return SOURCE
    return drawn_in(store.reads(person.id))


def _prompt(
    name: str,
    mine: list[dict[str, Any]] | None = None,
    tools: set[str] | None = None,
    arguments: Any = None,
    scopes: str | None = None,
) -> dict[str, Any]:
    """One prompt, as the message a host drops into its own conversation, with its
    arguments written in where it has any."""
    found = next((one for one in _prompts(mine, tools, scopes) if one["name"] == name), None)
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
    allowed = {tool.name for tool in connector.exposed(scopes, person=person, calling=True)}
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
    started = time.perf_counter()
    text, failed = tools_module.run(name, given, ctx)
    # How long each call took, so a slow tool is a line in the log rather than a guess
    # (2026-10-06: the first measurements were made by hand, from a host). The tool's
    # name, the time and whether it failed — never the arguments or the answer, which
    # are the reader's, and never who asked.
    log.info(
        "mcp tool %s took %d ms%s",
        name,
        round((time.perf_counter() - started) * 1000),
        " (failed)" if failed else "",
    )
    # Short links on the way out, so the host writes eight letters where it wrote two
    # hundred and fifty (`tools.shorten`, 2026-10-06).
    long = text
    text = tools_module.shorten(text, address)
    answered: dict[str, Any] = {"content": [{"type": "text", "text": text}], "isError": failed}
    tool = tools_module.BY_NAME.get(name)
    if tool is not None and tool.card:
        # The card's rows, in the field the MCP Apps extension hands a card. Exactly the
        # text's own JSON and nothing more (2026-10-06): some hosts read this field to
        # the model in place of the text (Claude Code does), so it has to be the same
        # floor, or a host that draws no card would be reading something new. `said` in
        # it is still the one line to pass on.
        try:
            rows = json.loads(text)
        except ValueError:
            rows = None
        if isinstance(rows, dict):
            answered["structuredContent"] = rows
            if tool.card == tools_module.TEXT_CARD and not failed and ctx is not None:
                answered["_meta"] = {TEXT_CARD_META: text_card_meta(long, ctx, address)}
    return _result(request_id, answered)


def text_card_meta(text: str, ctx: tools_module.Ctx, address: str) -> list[dict[str, Any]]:
    """What a text card needs beside each row, and the model does not (2026-10-06).

    One entry a row, in the rows' own order, read from the answer before its links were
    shortened (`text`), because a reader link is how a library row names its folder:

    - `door`: the short link that opens the text where it is built; where it is not, our
      own library page for it, where it is got ready — never a press inside the card
      (design.md §12, "A card never presses").
    - `audio`, only where the text already has a recording (`heard.recording_of`): a
      short-lived address for that one file, `ends` when it stops working (milliseconds,
      as a page's clock counts), and `credit` where the reading is somebody's.

    In `_meta`, not the rows: `structuredContent` is the text's own JSON and nothing
    more, because some hosts read it to their model in place of the text. A token handed
    to the model would be written out into the conversation, where it outlives the card
    it was made for.
    """
    from urllib.parse import quote

    from . import heard

    try:
        answer = json.loads(text)
    except ValueError:
        return []
    if not isinstance(answer, dict) or answer.get("error"):
        return []
    texts = answer.get("texts")
    rows = texts if isinstance(texts, list) else [answer]
    origin = _origin(address)
    allowed = heard.roots(ctx.home, ctx.library.shared)
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            out.append({})
            continue
        reader = str(row.get("reader") or "")
        said: dict[str, Any] = {}
        if reader:
            said["door"] = tools_module.shorten(reader, address)
        elif row.get("id") and origin:
            said["door"] = f"{origin}/library/{quote(str(row['id']))}"
        folder = _folder(row, reader, ctx)
        found = _recording(folder) if folder is not None and origin else None
        issued = heard.HEARD.issue(found.path, allowed) if found is not None else None
        if found is not None and issued is not None:
            token, ends = issued
            said["audio"] = {
                "src": f"{origin}{heard.ROUTE}?t={token}",
                "ends": int(ends * 1000),
                **({"credit": found.credit} if found.credit else {}),
            }
        out.append(said)
    return out


def _folder(row: dict[str, Any], reader: str, ctx: tools_module.Ctx) -> Path | None:
    """The built folder a row names, in the reader's home first and then the shared
    shelf — the order `Handler._serve_reader` looks in — or None for a text not built."""
    from urllib.parse import unquote, urlsplit

    name = str(row.get("name") or "")
    if not name and "/reader/" in reader:
        name = unquote(urlsplit(reader).path.removeprefix("/reader/").split("/")[0])
    if not name or "/" in name or name.startswith("."):
        return None
    for home in (ctx.home, ctx.library.shared):
        folder = home / name
        if folder.is_dir() and home.resolve() in folder.resolve().parents:
            return folder
    return None


def _recording(folder: Path) -> Any:
    """`heard.recording_of`, kept (`tools.KEPT`) until one of the files it is found from
    changes, so a find of twenty texts does not read twenty documents on every call.

    A recording shipped to the box after a text was asked about is seen after the next
    restart, which every deploy is."""
    from . import heard, remembered

    stamps = remembered.stamp(
        [folder / "audio.json", folder / "document.json", folder / "segments.json"]
    )
    key = ("heard", str(folder), *(tuple(mark) for mark in stamps))
    return tools_module.KEPT.get(key, lambda: heard.recording_of(folder))


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
        log.exception("mcp request failed", exc_info=broke)
        return _failed(
            message.get("id"), INTERNAL_ERROR, "Something went wrong on our side. Try again later."
        )


def _dump(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


__all__ = [
    "CAPABILITIES",
    "CARDS",
    "CARD_TYPE",
    "INSTRUCTIONS",
    "PROMPTS",
    "SERVER_NAME",
    "RpcError",
    "answer",
    "card_meta",
    "card_read",
    "card_shapes",
    "handle",
    "prompt_shapes",
    "tool_shapes",
]
