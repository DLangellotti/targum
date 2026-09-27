"""Checking one line the reader wrote somewhere else (targum-internal#80).

A reader practises in Claude or ChatGPT, where the host's model holds the conversation
and targum pays for none of it. What the host cannot do is remember them: `slip` — what
a reader got wrong — is written when a model recasts a line, and a conversation held
somewhere else writes nothing. So the record fills here instead.

**targum is the only judge.** `record_turn` takes what the reader *wrote*, never the
host's correction, and recasts it on targum's own model against targum's own contract.
Two surfaces, one table, one standard. Trusting a recast from a model we do not run and
whose prompt we cannot see would put two kinds of row in the same table and quietly make
the moat harder to reason about — which is the whole reason this costs anything at all.

**It is the one tool that spends**, and design.md §12 ("A scope is a press that lasts",
2026-09-22) is where that is written down. The press is not per call: it is the reader
ticking the `check` scope on targum's own approval page, where what it costs is said in
hours before it is granted, and where it is revoked. What keeps that safe is not the
grant but the two ceilings it sits inside — `CHAT_BUDGET` and the eight hours, both
unchanged — and the rate limit on the token.

**What it costs is the reader's own line and nothing else.** An in-app turn is metered at
the words asked plus a reply's worth, because targum wrote the reply. Here the host wrote
the conversation and targum judged one line, so the line alone is what comes out of the
hours. Ten words is five seconds. Saying otherwise would charge for a reply nobody bought.

A line that was already right writes no row. That is what keeps `slip` a record of
mistakes rather than a log of turns, and it is `record.rewritten`'s rule, unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import CHAT_MODEL, MAX_TOKENS
from . import hebrew as hebrew_module
from . import record as record_module

if TYPE_CHECKING:
    from .tools import Ctx

#: What one checked line may cost before it is refused outright. A recast of a sentence
#: is cents of a cent; anything near this is a line that is not a line.
MOST_PER_LINE = 0.05

#: The longest line this will look at. A reader writing more than this in one go is
#: writing a paragraph, and a paragraph recast as one sentence teaches nothing.
MOST_WORDS = 60

#: What the model is told, beside the language's own contract. Deliberately not the
#: chat's system prompt: there is no conversation here, nothing to find, no tools and
#: nobody to be warm at. One line in, one recast out.
ASK = """You are checking one line a learner wrote, and nothing else.

Answer with exactly the recast, in the contract's shape, and nothing before or after it:
a "{recast}" line with their sentence — as they wrote it if it was right, corrected if it
was not — then a "{english}" line with its {gloss}, then, only if you changed something
they wrote, one "{why}" line saying what changed and the rule.

No greeting, no comment, no question, no second sentence. You are not having a
conversation with this person and must not start one."""


def _asked(ctx: Ctx, language: str, wrote: str) -> tuple[str, list[dict[str, Any]]]:
    """The system prompt and the one message: the contract, then the line."""
    gloss = hebrew_module.gloss_language(ctx.said_reads)
    contract = hebrew_module.contract_for(language, gloss)
    said = ASK.format(
        recast=hebrew_module.RECAST,
        english=hebrew_module.ENGLISH,
        why=hebrew_module.WHY,
        gloss=gloss,
    )
    return f"{contract}\n\n{said}", [{"role": "user", "content": wrote}]


def _text(reply: Any) -> str:
    """The words out of a reply, however the SDK shaped it."""
    out = []
    for block in getattr(reply, "content", None) or []:
        if getattr(block, "type", "") == "text" or hasattr(block, "text"):
            out.append(str(getattr(block, "text", "")))
    return "\n".join(part for part in out if part)


def recast(ctx: Ctx, language: str, wrote: str, client: Any) -> hebrew_module.Pair | None:
    """Ask targum's own model to say the reader's line back, correctly. None if it would not.

    One round trip, no tools, no streaming: there is nothing to stream and nothing for a
    model to look up. What comes back is read by the contract's own reader (`hebrew.pairs`)
    rather than by a second parser, so a recast is shaped like every other recast in the
    record.
    """
    system, messages = _asked(ctx, language, wrote)
    reply = client.messages.create(
        model=CHAT_MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=messages,
    )
    ctx.usage.add(
        CHAT_MODEL,
        int(getattr(getattr(reply, "usage", None), "input_tokens", 0) or 0),
        int(getattr(getattr(reply, "usage", None), "output_tokens", 0) or 0),
    )
    said = hebrew_module.pairs(_text(reply), language)
    return next((one for one in said if one.recast), None)


def keep(ctx: Ctx, language: str, wrote: str, said: hebrew_module.Pair, source: str) -> int:
    """Write the row, where there is one to write. Returns its id, or 0.

    `rewritten` decides, not the model: a line that came back the same writes nothing,
    and that is what keeps the table a record of mistakes rather than a log of turns.
    """
    if ctx.store is None or ctx.person is None:
        return 0
    if not record_module.rewritten(wrote, said.hebrew):
        return 0
    return ctx.store.slip(
        ctx.person.id,
        wrote=wrote,
        recast=said.hebrew,
        changed=record_module.changed_words(wrote, said.hebrew),
        language=language,
        why=said.why,
        source=source,
    )


__all__ = ["ASK", "MOST_PER_LINE", "MOST_WORDS", "keep", "recast"]
