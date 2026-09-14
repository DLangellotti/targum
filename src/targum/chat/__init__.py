"""A conversation with targum, over the same rooms the pages already open onto.

The chat is a door, not a new house. Every tool it can call wraps a function the
product already has — the catalogue, a reader's shelf, their ledger, a build's state —
and nothing it does spends money except through the quote-then-consent seam that
`serve.Library.prepare` and `Library.claim` already hold. It is the first thing in the
codebase to need streaming, tool use and conversation state, which is why it is a package
rather than a route.
"""

from __future__ import annotations

#: The model the chat speaks with. A constant, never taken from a request: a model that
#: arrived in a payload would be a way to spend somebody else's money, which is the same
#: reason `Build._builder` refuses one.
CHAT_MODEL = "claude-opus-5"

#: How hard the model thinks on a routing turn. Low: most turns are a lookup and a
#: sentence, and the pages a tool reads are the expensive part, not the reasoning.
EFFORT = "low"

#: How many model round trips one turn may take before it is cut off. A turn that has
#: called tools eight times is a loop, not a conversation.
MAX_STEPS = 8

#: How long one turn may run, all its round trips and tools together, before it is ended
#: and the reader told. Nothing ended a turn: on 2026-09-14 a reader could not tell a slow
#: one from a dead one (targum-internal#271). A search-and-describe turn takes about two
#: minutes, so four is room for a slow one and not a wait anybody sits through. The page
#: stops waiting a little after this (`GIVE_UP_MS` in `chat.js`).
TURN_DEADLINE_S = 240.0

#: What the reader is told about a turn that ran out of time.
TURN_TOO_LONG = "We took too long to answer that. Try again."

#: Threads answering turns. Their own pool rather than `Library.queue`: a turn behind a
#: novel is a broken chat, and a novel behind a turn is a broken build. Capped, because
#: `ThreadingHTTPServer` spawns request threads without limit and a turn holds one of
#: these for tens of seconds.
CHAT_WORKERS = 4

#: What one turn reserves from the money rails before it runs, settled to the real
#: figure afterwards. Generous on purpose — the estimate has to be made before a token
#: is bought, and the ledger holds the receipt within the minute.
TURN_RESERVE = 0.05

#: Room for an answer. A chat line is short; a tool result is what makes a turn long,
#: and those ride in the input.
MAX_TOKENS = 4096
