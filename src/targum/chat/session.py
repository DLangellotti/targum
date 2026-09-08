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
import os
import queue
import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .. import level as level_module
from ..usage import Usage
from . import CHAT_MODEL, CHAT_WORKERS, EFFORT, MAX_STEPS, MAX_TOKENS, TURN_RESERVE, prompts
from . import exemplars as exemplars_module
from . import hebrew as hebrew_module
from . import tools as tools_module
from .record import Recorder, outside_share

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


#: What the API takes back for each kind of block it sent. The SDK's objects carry more —
#: `parsed_output` on a text block, `citations: None` — and a block replayed with a field
#: the API does not know is a 400 on the second turn of every conversation, which is
#: exactly how the first one was found.
_REPLAYABLE: dict[str, tuple[str, ...]] = {
    "text": ("type", "text", "citations"),
    "thinking": ("type", "thinking", "signature"),
    "redacted_thinking": ("type", "data"),
    "tool_use": ("type", "id", "name", "input"),
    "server_tool_use": ("type", "id", "name", "input"),
}


def replayable(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Content blocks trimmed to what the API accepts back, and nothing set to null."""
    out: list[dict[str, Any]] = []
    for block in blocks:
        kind = str(block.get("type") or "")
        keep = _REPLAYABLE.get(kind)
        kept = {
            key: value
            for key, value in block.items()
            if value is not None and (keep is None or key in keep)
        }
        out.append(kept)
    return out


#: A byte-level tokenizer can emit a byte that is not a character, and the API hands it
#: back decoded as U+FFFD. It happens rarely and it happened in pointed Hebrew: one turn
#: on 2026-09-07 wrote מָסָךְ שֶ�ל, the shin dot dropped and a black diamond left in its
#: place. Nothing downstream survives it — the annotator lemmatised the word as `[unk]`
#: and banded it 6, so it entered the reader's ledger as a word nobody knows, and the
#: transcript would have carried the diamond into any targum built from the conversation.
#: The mark is dropped rather than guessed: `שֶל` is a real word missing a point, and
#: putting the point back would be inventing what the model did not write.
BROKEN = "�"


def written(text: str) -> str:
    """Model-written text, with what is not a character taken out."""
    return text.replace(BROKEN, "") if BROKEN in text else text


def _content(reply: Any) -> list[dict[str, Any]]:
    """A reply's content blocks as plain dicts, exactly as they must be replayed.

    Verbatim in what matters — tool-use blocks have to go back as they came, and a
    thinking block passed back changed is a 400 — and trimmed of what the SDK adds for
    its own use, which the API refuses.
    """
    dump = getattr(reply, "model_dump", None)
    if callable(dump):
        blocks = replayable([dict(block) for block in dump()["content"]])
    else:
        out: list[dict[str, Any]] = []
        for block in reply.content:
            out.append(dict(block) if isinstance(block, dict) else dict(vars(block)))
        blocks = replayable(out)
    for block in blocks:
        # Only a text block. A thinking block is signed and a tool-use block is replayed
        # as it came; neither is ours to touch.
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            block["text"] = written(block["text"])
    return blocks


def _said(blocks: list[dict[str, Any]]) -> str:
    return "".join(str(block.get("text") or "") for block in blocks if block.get("type") == "text")


ClientFactory = Callable[[], Any]


def run_turn(
    client: Any,
    ctx: tools_module.Ctx,
    history: list[dict[str, Any]],
    feed: Feed,
    keep: Callable[[str, list[dict[str, Any]], str], None],
    *,
    web_search: bool = False,
    contract: str = "",
    ledger: str = "",
) -> Usage:
    """Answer the last user message in `history`, streaming into `feed`.

    `keep(role, content, said)` is called for every API message this turn produces, in
    order, so the store holds the conversation as the API will need to see it again.
    `contract` is a stable block added to the system prompt (the Hebrew mode's rules);
    `ledger` is the per-reader block, or the plain one where none is given. Returns
    what the turn cost.
    """
    usage = ctx.usage
    messages = list(history)
    stable = prompts.SYSTEM + ("\n\n" + contract if contract else "")
    for _ in range(MAX_STEPS):
        with client.messages.stream(
            model=CHAT_MODEL,
            max_tokens=MAX_TOKENS,
            system=[
                # The stable half first and cached; the ledger after the breakpoint, so a
                # reader marking one word does not throw the whole prefix away.
                {"type": "text", "text": stable, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": ledger or prompts.ledger(ctx.level)},
            ],
            output_config={"effort": EFFORT},
            tools=tools_module.anthropic_tools(web_search=web_search),
            messages=messages,
        ) as stream:
            for event in stream:
                if getattr(event, "type", "") == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if getattr(delta, "type", "") == "text_delta":
                        feed.put("text", written(str(getattr(delta, "text", ""))))
            reply = stream.get_final_message()
        got = getattr(reply, "usage", None)
        if got is not None:
            usage.add(
                CHAT_MODEL,
                int(getattr(got, "input_tokens", 0) or 0),
                int(getattr(got, "output_tokens", 0) or 0),
            )
        blocks = _content(reply)
        # A search the API ran on the turn's behalf is billed per search, not per token,
        # so it is counted on its own axis and priced with the rest of the receipt.
        for block in blocks:
            if block.get("type") == "server_tool_use" and block.get("name") == "web_search":
                usage.add_search()
                feed.put("tool", {"name": "web_search"})
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
            if name in ("quote_build", "quote_conversation") and not failed:
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
    #: Seconds of the reader's own voice this turn came from, already metered by the
    #: request that heard it. Zero for a typed line.
    heard_seconds: float = 0.0


def framed(text: str, about: dict[str, str] | None, brought: dict[str, Any] | None = None) -> str:
    """The reader's line as the model sees it: their note of where they are, or of
    what they have just brought, then what they asked. The page shows only what they
    asked (`said`); this is `content`."""
    if brought:
        return "\n".join([*brought_note(brought), "Their line:", text])
    if not about:
        return text
    where = []
    if about.get("document"):
        where.append(f"the text {about['document']}")
    if about.get("section"):
        where.append(f"section {about['section']}")
    lines = [
        "The reader is reading " + ", ".join(where) + "." if where else "The reader is reading."
    ]
    if about.get("surface"):
        word = f"They tapped the word {about['surface']}"
        if about.get("lemma") and about["lemma"] != about["surface"]:
            word += f" (dictionary form {about['lemma']})"
        lines.append(word + ".")
    if about.get("sentence"):
        lines.append(f"The sentence: {about['sentence']}")
    lines.append("Their question:")
    lines.append(text)
    return "\n".join(lines)


def what_was_sent(brought: dict[str, Any]) -> str:
    """The thing the reader sent, named as what it was — so the model, which was told
    it had been given words, stops telling a reader who sent a screenshot that no
    picture arrived (2026-09-07)."""
    pages = int(brought.get("pages") or 0)
    kind = str(brought.get("from") or "text")
    if kind == "pictures":
        if brought.get("conversation"):
            return (
                "a screenshot of a messaging conversation, read into its messages with "
                "the names the app shows"
            )
        count = f"{pages} pictures" if pages > 1 else "a picture"
        return f"{count} (a screenshot or a photograph), read into words before it reached you"
    if kind == "pdf":
        return "a PDF, its text read off its pages"
    if kind == "recording":
        return "a recording, to be written down"
    if kind == "link":
        return "a link"
    return "a text"


def brought_note(brought: dict[str, Any]) -> list[str]:
    """What the reader sent with their line, said to the model as a fact it can use:
    what it was, its name, its size, its first lines, and whether it is already
    building — so it never asks for a file it has been given (2026-09-07)."""
    title = str(brought.get("title") or "a text")
    facts = []
    if brought.get("pages") and brought.get("from") not in ("pictures",):
        facts.append(f"{brought['pages']} pages")
    if brought.get("segments"):
        facts.append(f"{brought['segments']} sentences")
    lines = [
        f"The reader has just sent {what_was_sent(brought)} through the box with this "
        f"line. It is called: {title}" + (f" ({', '.join(facts)})" if facts else "") + "."
    ]
    excerpt = [str(line) for line in brought.get("excerpt") or [] if str(line).strip()]
    if excerpt:
        lines.append("Its first lines, as read: " + " / ".join(excerpt))
    doubtful = int(brought.get("doubtful") or 0)
    if doubtful:
        lines.append(f"{doubtful} lines could not be read clearly and are marked in the text.")
    stage = str(brought.get("stage") or "")
    if stage in ("working", "done"):
        lines.append(
            "It is being built now and will open from the strip at the top of their page "
            "when it is ready. They do not need to send it again, and you cannot open it."
        )
    elif brought.get("blocked") or brought.get("error"):
        lines.append(
            "It could not be built: " + str(brought.get("blocked") or brought.get("error"))
        )
    else:
        lines.append("Its card is in the thread, waiting on their press.")
    return lines


def _conversing_in(learning: set[str]) -> str:
    """Which of a reader's languages the conversation is held in.

    Hebrew wherever it is one of them, because that is what the chat is for: the contract
    is Hebrew, the record is Hebrew, and the ledger it grades against is the reader's
    Hebrew. Anything else is a fallback for a reader who is not learning Hebrew at all.

    This was `sorted(...)[0]`, which is alphabetical and therefore arbitrary. Since the
    scripture path learned to read Daniel and Ezra, a reader who opens either is learning
    `arc` as well as `he` — and `arc` sorts first. Their conversations were held in
    Aramaic: banded against a frequency table that does not exist, which raised inside the
    worker rather than being answered (targum-internal#228).
    """
    if not learning:
        return "he"
    return "he" if "he" in learning else sorted(learning)[0]


class Chats:
    """The workers that answer turns, and the feeds their answers stream through."""

    def __init__(
        self,
        library: Library,
        store: Store | None,
        *,
        usable: bool = True,
        client_factory: ClientFactory | None = None,
        web_search: bool | None = None,
        recorder: Recorder | None = None,
        exemplars: list[exemplars_module.Exemplar] | None = None,
    ) -> None:
        self.library = library
        self.store = store
        #: What reads a turn's Hebrew as a text is read, so the page can draw the record
        #: as it forms (`chat/record.py`). Its model is warmed when the workers start.
        self.recorder = recorder or Recorder()
        #: Sentences a Hebrew speaker wrote, for the idiom (`chat/exemplars.py`). Read
        #: once from the pool on the box; a box without one has none.
        self.exemplars = exemplars if exemplars is not None else exemplars_module.load()
        #: Whether the server-side search rides along. On unless the box says not
        #: (`TARGUM_WEB_SEARCH=0`): a reader who asks for something online and is told
        #: the box cannot look is being told the product is smaller than it is
        #: (2026-09-06). What it may look at is still the publishers' hosts and the
        #: public ones (`chat/sources.py`), three searches a turn at most, each counted
        #: (`Usage.searches`) and inside the same rails every turn is.
        self.web_search = (
            web_search
            if web_search is not None
            else os.environ.get("TARGUM_WEB_SEARCH", "").strip().lower()
            not in ("0", "false", "no", "off")
        )
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

    def context(
        self, person: Person | None, home: Path, chat_id: str, admin: bool
    ) -> tools_module.Ctx:
        """Who is asking and what the server knows about them — the same `Ctx` a turn
        runs its tools against, for anything else that reads a conversation as its
        owner (the save door, for one)."""
        if self.store is None:
            raise RuntimeError("a chat needs a store")
        from ..translate.prompts import INTO, READING

        store = self.store
        person_id = person.id if person else None
        language = _conversing_in(store.learning(person_id)) if person_id else "he"
        # The same sets `Handler._reads` and `_learning` compute: everything where there
        # is nobody to ask, the account's own answer where there is.
        into = {code for code, _ in INTO}
        reading = {code for code, _ in READING}
        return tools_module.Ctx(
            person=person,
            home=home,
            library=self.library,
            store=store,
            chat_id=chat_id,
            level=level_module.snapshot(store, person_id, language),
            reads=(store.reads(person_id) & into) if person else into,
            learning=(store.learning(person_id) & reading) if person else reading,
            admin=admin,
        )

    def start_workers(self, count: int = CHAT_WORKERS) -> None:
        for _ in range(count):
            worker = threading.Thread(target=self._drain, daemon=True)
            worker.start()
            self._workers.append(worker)
        # The record's model, loaded now rather than under the first reader's turn.
        threading.Thread(target=self.recorder.warm, daemon=True).start()

    def _drain(self) -> None:
        # A pool thread lives as long as the process, so its one store connection is
        # not the leak `Handler.finish` closes: that was a connection per dying thread.
        while True:
            asked = self.queue.get()
            try:
                self.answer(asked)
            except Exception as error:  # noqa: BLE001 - a worker outlives the turn it lost
                # `answer` guards the model call and nothing before it, so anything the
                # ledger block raises arrives here — and here used to be nowhere. The
                # thread died, the turn stayed `working` for ever with no error against
                # it, and the reader watched three dots that were never going to stop.
                # Worse, the pool is four threads: four such turns and the chat is gone
                # for everybody until the service restarts. That is what a conversation
                # in Aramaic did on 2026-09-08 (targum-internal#228).
                self._collapsed(asked, error)
            finally:
                self.queue.task_done()

    def _collapsed(self, asked: Asked, error: Exception) -> None:
        """A turn that failed where `answer` was not watching.

        Says the same sentence to the reader that `answer` says, marks the turn failed so
        the page stops waiting, and writes the traceback where the operator will find it.
        Every step is guarded: this runs because something already went wrong, and a
        handler that raises takes the worker with it after all.
        """
        traceback.print_exc()
        said = "The conversation could not continue. Try again."
        try:
            if self.store is not None:
                self.store.chat_turn_update(asked.chat_id, asked.n, stage="failed", error=said)
        except Exception:  # noqa: BLE001 - the store is the thing that may be broken
            pass
        try:
            if (incidents := getattr(self.library, "incidents", None)) is not None:
                from .. import incidents as incidents_module

                incidents_module.record(incidents, "chat:turn", error)
        except Exception:  # noqa: BLE001
            pass
        try:
            if (feed := self.feeds.get((asked.chat_id, asked.n))) is not None:
                feed.put("error", {"message": said, "detail": type(error).__name__})
                feed.close()
        except Exception:  # noqa: BLE001
            pass

    # -- asking -----------------------------------------------------------------

    def say(
        self,
        person: Person | None,
        home: Path,
        chat_id: str,
        text: str,
        *,
        admin: bool,
        heard_seconds: float = 0.0,
        about: dict[str, str] | None = None,
        brought: dict[str, Any] | None = None,
    ) -> Asked:
        """Write the reader's turn down and hand it to a worker. Returns at once.

        `about` is where the reader is when the line came from a word's card — the
        text, the section, the sentence, the word. It rides in the turn the model sees
        and not in what the page shows back, and it opens the conversation in English:
        a question about a form is answered about the form, whatever the reader's shelf.
        `brought` is the text the reader sent with the line, from its own job: it rides
        the same way, and the conversation keeps its language.
        """
        if self.store is None:
            raise RuntimeError("a chat needs a store")
        person_id = person.id if person else None
        if not chat_id:
            # One conversation, in Hebrew, for a reader with modern Hebrew to hold it in;
            # a scripture-only reader is answered in English, about the text. The same
            # question the page asks (`talk` on `/chat/list`), answered the same way.
            # A question from a word's card is about the text, in English, for everyone.
            mode = "talk" if self.library.talks(home, person_id) and not about else "find"
            chat_id = self.store.chat_open(person_id, mode=mode)
        n = self.store.chat_say(
            chat_id, "user", framed(text, about, brought), text, stage="working"
        )
        feed = Feed()
        self.feeds[(chat_id, n)] = feed
        asked = Asked(chat_id, n, person, home, admin, heard_seconds)
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
        person_id = asked.person.id if asked.person else None
        ctx = self.context(asked.person, asked.home, asked.chat_id, asked.admin)
        level = ctx.level
        language = level.language
        asked_text = next(
            (str(row["said"]) for row in store.chat_turns(asked.chat_id) if row["n"] == asked.n),
            "",
        )
        # The turn's place on the rails: a job row of its own kind, claimed before the
        # first token and settled to the receipt after the last. Never enqueued —
        # `Library.queue` is the build queue. Its seconds are the words asked plus a
        # reply's worth at the conversational rate, settled to the words said: the same
        # allowance a recording's hour comes out of, in the same sum.
        job = Job(
            id=f"chat-{asked.chat_id}-{asked.n}",
            source=f"chat:{asked.chat_id}",
            title="",
            estimate=TURN_RESERVE,
            # A spoken line was metered by the request that heard it, so a turn that
            # came from the microphone counts the reply alone.
            seconds=hebrew_module.seconds_for(
                (0 if asked.heard_seconds else hebrew_module.words_in(asked_text))
                + hebrew_module.ASSUMED_REPLY_WORDS
            ),
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
        # Trimmed on the way out as well as on the way in, so a conversation written
        # down before the trim existed still replays.
        history = [
            {
                "role": row["role"],
                "content": replayable(row["content"])
                if isinstance(row["content"], list)
                else row["content"],
            }
            for row in store.chat_turns(asked.chat_id)
        ]

        def keep(role: str, content: list[dict[str, Any]], said: str) -> None:
            store.chat_say(asked.chat_id, role, content, said, stage="done")

        # Every conversation is in Hebrew, whatever the reader writes in (decided
        # 2026-09-06: a reader who asked in English was answered in English, and a
        # conversation that is not in Hebrew leaves no record worth keeping). The
        # contract rides in the cached block, the reader's own words after it. The one
        # exception, decided the same day: a reader whose every text is scripture is
        # not written Hebrew at — the conversation was opened as "find", and it stays in
        # English, about the text (`Library.talks`).
        opened = store.chat_owned(person_id, asked.chat_id) or {}
        contract = "" if opened.get("mode") == "find" else hebrew_module.CONTRACT
        known = hebrew_module.known_words(store, person_id, language)
        common = hebrew_module.common_words(language=language)
        # The reader's own words come back into a conversation in Hebrew, and only
        # there: a question about a text is answered about the text. By status, and a
        # different slice of the ledger on every turn.
        returning = (
            hebrew_module.bring_back(store, person_id, language, turn=asked.n) if contract else None
        )
        ledger = hebrew_module.ledger_block(level, known, common, returning)
        if contract and self.exemplars:
            # A few sentences a Hebrew speaker wrote inside this reader's words, after
            # the breakpoint with the ledger: the idiom to write in, drawn afresh each
            # turn. Only where the conversation is in Hebrew.
            picked = exemplars_module.pick(
                self.exemplars,
                set(known) | set(common),
                returning.words() if returning else (),
                seed=exemplars_module.turn_seed(asked.chat_id, asked.n),
            )
            if picked:
                ledger = ledger + "\n\n" + exemplars_module.block(picked)
        # Where the fetch door was refused. After the breakpoint with the ledger, because
        # it changes as the box knocks, and a changing block before the breakpoint would
        # throw the cached prefix away every time it learned something.
        shut = prompts.shut_hosts(store.closed())
        if shut:
            ledger = ledger + "\n\n" + shut
        try:
            spent = run_turn(
                self.client(),
                ctx,
                history,
                feed,
                keep,
                web_search=self.web_search,
                contract=contract,
                ledger=ledger,
            )
            job.spent = spent.cost()
            job.seconds = hebrew_module.seconds_for(
                hebrew_module.words_in(feed.text())
                if asked.heard_seconds
                else hebrew_module.words_in(asked_text, feed.text())
            )
            job.stage = "done"
            self.library.settle(job)
            store.chat_turn_update(asked.chat_id, asked.n, stage="done", spent=job.spent)
            store.chat_add_spent(asked.chat_id, job.spent)
            if contract:
                # The record forming: the reply's Hebrew read as a text is read, before
                # the page is told the turn is done, so the words land with the lines.
                self._record(
                    asked,
                    feed,
                    language,
                    set(known) | set(common) | set(returning.words() if returning else []),
                )
            feed.put(
                "done",
                {
                    "text": feed.text(),
                    "spent": round(job.spent, 4),
                    # How long this conversation has run, in the seconds it is metered
                    # in — the clock the page shows at the foot.
                    "seconds": round(store.chat_seconds(asked.chat_id), 1),
                },
            )
        except Exception as error:  # noqa: BLE001 - said to the reader, not raised at them
            # The reader gets one sentence; the operator gets the traceback, in the
            # terminal, the way a build's failure is printed. Swallowing it silently is
            # how a 400 on every second turn looked like a shrug.
            traceback.print_exc()
            job.stage = "failed"
            job.error = "The conversation could not continue. Try again."
            self.library.release(job)
            store.chat_turn_update(asked.chat_id, asked.n, stage="failed", error=job.error)
            feed.put("error", {"message": job.error, "detail": type(error).__name__})
        finally:
            self.library.remember(job)
            feed.close()

    def _record(self, asked: Asked, feed: Feed, language: str, allowed: set[str]) -> None:
        """Read the answer's Hebrew lines and hand the page their words.

        Kept on the reader's turn, as the words of its answer, and put on the feed as
        its own event. A failure here is the operator's to read and costs the reader
        nothing but the states: the turn is already done and the lines already drawn.
        """
        if self.store is None:
            return
        try:
            said = hebrew_module.pairs(feed.text())
            lines = [pair.hebrew for pair in said]
            words = self.recorder.annotate(lines, language)
            payload = {
                "lines": [{"he": he, "words": read} for he, read in zip(lines, words, strict=True)],
                "outside": round(outside_share(words, allowed), 3),
            }
            self.store.chat_turn_update(
                asked.chat_id, asked.n, words=json.dumps(payload, ensure_ascii=False)
            )
            feed.put("words", payload)
        except Exception:  # noqa: BLE001 - the states are a courtesy; the turn stands
            traceback.print_exc()
