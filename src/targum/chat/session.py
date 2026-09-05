"""One turn of conversation: the reader says something, the model answers, in a stream.

The loop is written out rather than taken from the SDK's tool runner, for three reasons
that are each enough: every other model call in the codebase is a plain call and the
runner is beta; the runner returns quietly on `pause_turn`, which a server-side search
produces and which has to be resumed; and the consent seam needs to look at a pending
`tool_use` before it runs, which is cleaner in a loop we own.

A turn runs on a worker thread of its own, off the request that asked for it, so the
page can leave and come back — the same reason a build does. What the worker writes is
fed to whoever is listening through a `Feed`, and written to the store as it goes, so a
tab that reconnects and a restart that lost the feed both find the same answer.
"""

from __future__ import annotations

import json
import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .. import level as level_module
from ..usage import Usage
from . import CHAT_MODEL, CHAT_WORKERS, EFFORT, MAX_STEPS, MAX_TOKENS, TURN_RESERVE, prompts
from . import tools as tools_module

if TYPE_CHECKING:
    from ..accounts import Person, Store
    from ..serve import Library


class Feed:
    """What one turn has said so far, for anyone tailing it.

    Append-only, with a condition variable so a tail can wait rather than poll. Kept
    small: text deltas, a note per tool call, and one closing event. The store holds the
    durable copy; this is the live one.
    """

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []
        self.closed = False
        self._cond = threading.Condition()

    def put(self, kind: str, payload: dict[str, Any] | str) -> None:
        data = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        with self._cond:
            self.events.append((kind, data))
            self._cond.notify_all()

    def close(self) -> None:
        with self._cond:
            self.closed = True
            self._cond.notify_all()

    def wait(self, after: int, timeout: float) -> tuple[list[tuple[int, str, str]], bool]:
        """Events past `after`, waiting up to `timeout` for one; and whether it is over."""
        with self._cond:
            if len(self.events) <= after and not self.closed:
                self._cond.wait(timeout)
            fresh = [(i, k, d) for i, (k, d) in enumerate(self.events) if i >= after]
            return fresh, self.closed

    def text(self) -> str:
        return "".join(data for kind, data in self.events if kind == "text")


def _content(reply: Any) -> list[dict[str, Any]]:
    """A reply's content blocks as plain dicts, exactly as they must be replayed.

    Verbatim rather than the text pulled out of them: tool-use and tool-result blocks
    have to go back as they came, and a thinking block passed back changed is a 400.
    """
    dump = getattr(reply, "model_dump", None)
    if callable(dump):
        blocks = dump()["content"]
        return [dict(block) for block in blocks]
    out: list[dict[str, Any]] = []
    for block in reply.content:
        out.append(dict(block) if isinstance(block, dict) else dict(vars(block)))
    return out


def _said(blocks: list[dict[str, Any]]) -> str:
    return "".join(str(block.get("text") or "") for block in blocks if block.get("type") == "text")


ClientFactory = Callable[[], Any]


def run_turn(
    client: Any,
    ctx: tools_module.Ctx,
    history: list[dict[str, Any]],
    feed: Feed,
    keep: Callable[[str, list[dict[str, Any]], str], None],
) -> Usage:
    """Answer the last user message in `history`, streaming into `feed`.

    `keep(role, content, said)` is called for every API message this turn produces, in
    order, so the store holds the conversation as the API will need to see it again.
    Returns what the turn cost.
    """
    usage = ctx.usage
    messages = list(history)
    for _ in range(MAX_STEPS):
        with client.messages.stream(
            model=CHAT_MODEL,
            max_tokens=MAX_TOKENS,
            system=[
                # The stable half first and cached; the ledger after the breakpoint, so a
                # reader marking one word does not throw the whole prefix away.
                {"type": "text", "text": prompts.SYSTEM, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": prompts.ledger(ctx.level)},
            ],
            output_config={"effort": EFFORT},
            tools=tools_module.anthropic_tools(),
            messages=messages,
        ) as stream:
            for event in stream:
                if getattr(event, "type", "") == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if getattr(delta, "type", "") == "text_delta":
                        feed.put("text", str(getattr(delta, "text", "")))
            reply = stream.get_final_message()
        got = getattr(reply, "usage", None)
        if got is not None:
            usage.add(
                CHAT_MODEL,
                int(getattr(got, "input_tokens", 0) or 0),
                int(getattr(got, "output_tokens", 0) or 0),
            )
        blocks = _content(reply)
        messages.append({"role": "assistant", "content": blocks})
        keep("assistant", blocks, _said(blocks))
        stop = getattr(reply, "stop_reason", "end_turn")
        if stop == "pause_turn":
            # A server-side tool paused the turn; sending the same conversation back
            # resumes it. Nothing for us to run.
            continue
        if stop != "tool_use":
            break
        results: list[dict[str, Any]] = []
        for block in blocks:
            if block.get("type") != "tool_use":
                continue
            name = str(block.get("name") or "")
            feed.put("tool", {"name": name})
            text, failed = tools_module.run(name, dict(block.get("input") or {}), ctx)
            if name == "quote_build" and not failed:
                # The page draws the card from the quote itself, not from what the
                # model says about it: the number of sentences, the hours, the button.
                quoted = json.loads(text).get("quote")
                if quoted:
                    feed.put("quote", quoted)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": str(block.get("id") or ""),
                    "content": text,
                    "is_error": failed,
                }
            )
        # All of them in one message. Split across several, the model learns that
        # parallel calls do not come back together and stops making them.
        messages.append({"role": "user", "content": results})
        keep("user", results, "")
    return usage


@dataclass
class Asked:
    """One turn waiting to be answered."""

    chat_id: str
    n: int
    person: Person | None
    home: Path
    admin: bool


class Chats:
    """The workers that answer turns, and the feeds their answers stream through."""

    def __init__(
        self,
        library: Library,
        store: Store | None,
        *,
        usable: bool = True,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self.library = library
        self.store = store
        #: Whether anything can be asked at all — false with no API key, and the page is
        #: told so before it tries rather than after.
        self.usable = usable
        self._client_factory = client_factory or self._anthropic
        self._client: Any = None
        self.feeds: dict[tuple[str, int], Feed] = {}
        self.queue: queue.Queue[Asked] = queue.Queue()
        self._workers: list[threading.Thread] = []
        self.lock = threading.Lock()

    @staticmethod
    def _anthropic() -> Any:
        import anthropic

        return anthropic.Anthropic()

    def client(self) -> Any:
        with self.lock:
            if self._client is None:
                self._client = self._client_factory()
            return self._client

    def start_workers(self, count: int = CHAT_WORKERS) -> None:
        for _ in range(count):
            worker = threading.Thread(target=self._drain, daemon=True)
            worker.start()
            self._workers.append(worker)

    def _drain(self) -> None:
        # A pool thread lives as long as the process, so its one store connection is
        # not the leak `Handler.finish` closes: that was a connection per dying thread.
        while True:
            asked = self.queue.get()
            try:
                self.answer(asked)
            finally:
                self.queue.task_done()

    # -- asking -----------------------------------------------------------------

    def say(
        self, person: Person | None, home: Path, chat_id: str, text: str, *, admin: bool
    ) -> Asked:
        """Write the reader's turn down and hand it to a worker. Returns at once."""
        if self.store is None:
            raise RuntimeError("a chat needs a store")
        person_id = person.id if person else None
        if not chat_id:
            chat_id = self.store.chat_open(person_id)
        n = self.store.chat_say(chat_id, "user", text, text, stage="working")
        feed = Feed()
        self.feeds[(chat_id, n)] = feed
        asked = Asked(chat_id, n, person, home, admin)
        self.queue.put(asked)
        return asked

    def feed_for(self, chat_id: str, n: int) -> Feed | None:
        return self.feeds.get((chat_id, n))

    # -- answering --------------------------------------------------------------

    def answer(self, asked: Asked) -> None:
        from ..serve import Job

        store = self.store
        feed = self.feeds.get((asked.chat_id, asked.n)) or Feed()
        if store is None:
            feed.close()
            return
        from ..translate.prompts import INTO, READING

        person_id = asked.person.id if asked.person else None
        language = next(iter(sorted(store.learning(person_id))), "he") if person_id else "he"
        level = level_module.snapshot(store, person_id, language)
        # The same sets `Handler._reads` and `_learning` compute: everything where there
        # is nobody to ask, the account's own answer where there is.
        into = {code for code, _ in INTO}
        reading = {code for code, _ in READING}
        ctx = tools_module.Ctx(
            person=asked.person,
            home=asked.home,
            library=self.library,
            store=store,
            chat_id=asked.chat_id,
            level=level,
            reads=(store.reads(person_id) & into) if asked.person else into,
            learning=(store.learning(person_id) & reading) if asked.person else reading,
            admin=asked.admin,
        )
        # The turn's place on the money rails: a job row of its own kind, claimed before
        # the first token and settled to the receipt after the last. Never enqueued —
        # `Library.queue` is the build queue.
        job = Job(
            id=f"chat-{asked.chat_id}-{asked.n}",
            source=f"chat:{asked.chat_id}",
            title="",
            estimate=TURN_RESERVE,
            stage="working",
            owner=person_id,
            home=asked.home,
            admin=asked.admin,
            kind="chat",
        )
        self.library.jobs[job.id] = job
        self.library.remember(job)
        refused = self.library.claim_turn(job)
        if refused:
            job.stage = "blocked"
            job.blocked = refused
            self.library.remember(job)
            store.chat_turn_update(asked.chat_id, asked.n, stage="failed", error=refused)
            feed.put("error", {"message": refused})
            feed.close()
            return
        # The whole conversation so far, as the API needs to see it again: the reader's
        # lines, the answers, and the tool traffic between them, in order.
        history = [
            {"role": row["role"], "content": row["content"]}
            for row in store.chat_turns(asked.chat_id)
        ]

        def keep(role: str, content: list[dict[str, Any]], said: str) -> None:
            store.chat_say(asked.chat_id, role, content, said, stage="done")

        try:
            spent = run_turn(self.client(), ctx, history, feed, keep)
            job.spent = spent.cost()
            job.stage = "done"
            self.library.settle(job)
            store.chat_turn_update(asked.chat_id, asked.n, stage="done", spent=job.spent)
            store.chat_add_spent(asked.chat_id, job.spent)
            feed.put("done", {"text": feed.text(), "spent": round(job.spent, 4)})
        except Exception as error:  # noqa: BLE001 - said to the reader, not raised at them
            job.stage = "failed"
            job.error = "The conversation could not continue. Try again."
            self.library.release(job)
            store.chat_turn_update(asked.chat_id, asked.n, stage="failed", error=job.error)
            feed.put("error", {"message": job.error, "detail": type(error).__name__})
        finally:
            self.library.remember(job)
            feed.close()
