"""How the connector feels from inside somebody else's chat: fast, short and on contract.

Approved by David on 2026-10-06. Until then everything known about the connector's
latency and manners was measured by hand, in Claude, one conversation at a time — the
250-character reader links, `how_to_talk` read twice, a host polling `check_job` beside
a card that already followed the build. This puts a stand-in host in front of `/mcp`
and measures what a reader waits for and what they are told.

**A host simulator, not the box.** The host is the Messages API, handed what Claude or
ChatGPT is handed: a short generic system prompt with `mcp_http.INSTRUCTIONS` under it,
and `mcp_http.tool_shapes(connector.exposed(scopes))` as its tools. Every tool call it
makes is answered by `mcp_http.handle` with a JSON-RPC `tools/call`, exactly as `/mcp`
answers one, against a world built here in a temporary folder: a fixture catalogue, a
reader who knows three hundred common words and is learning twenty, three texts on the
shelf and a build halfway through. No production data, no live box, and no network but
the API's — `describe_source` and `quote_build` are handed a page and a priced job
instead of fetching (`stubbed`).

**What is measured, per scenario.** Wall time; time to the first streamed token and to
the first Hebrew letter of a reply, from the moment the reader's line was sent; the tool
calls, by name, with each result's size in bytes and how long it took; tokens and
dollars from the API's own `usage`; and the contract, checked by rule rather than by a
judge (`check_*`): Hebrew present and pointed, links alone on their lines and short,
no money and no "quote", `how_to_talk` before the first Hebrew line, length.

**What it costs.** About a dollar a run at Sonnet's prices, never more than
`--max-dollars` (5 by default): before every call the worst case — everything sent at
the uncached price, plus `max_tokens` written — is added to what has been spent, and a
call that could cross the line is not made. Never in CI; `--dry-run` is what the tests
run, with a scripted host and no key.

    op run --env-file op.env -- .venv/bin/python scripts/eval_connector.py
    .venv/bin/python scripts/eval_connector.py --dry-run

Each scenario is written to `evals/connector/<stamp>.jsonl` as it finishes (gitignored),
so a run stopped by the cap or by Ctrl-C keeps what it paid for.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

#: The fixture catalogue, which is public; the real one is not, and is read only when
#: named with `--catalogue`.
FIXTURE_CATALOGUE = ROOT / "tests" / "fixtures" / "catalogue.json"


def _catalogue_named(argv: list[str]) -> Path:
    """`--catalogue` read before anything of targum's is imported, because
    `catalogue.CATALOGUE` is built once, at import, from whatever TARGUM_CATALOGUE says
    then — and on a laptop with `~/.targum/catalogue.json` that is the private one."""
    for n, one in enumerate(argv):
        if one == "--catalogue" and n + 1 < len(argv):
            return Path(argv[n + 1]).expanduser()
        if one.startswith("--catalogue="):
            return Path(one.split("=", 1)[1]).expanduser()
    return FIXTURE_CATALOGUE


if __name__ == "__main__":
    os.environ["TARGUM_CATALOGUE"] = str(_catalogue_named(sys.argv[1:]))
    # And the weekly's issues, which `catalogue.everything()` joins on from
    # `./targum-out/weekly` or wherever this says; see `isolated`.
    os.environ["TARGUM_WEEKLY_DIR"] = tempfile.mkdtemp(prefix="eval-connector-weekly-")

from targum import catalogue as catalogue_module  # noqa: E402
from targum import connector, mcp_http  # noqa: E402
from targum.accounts import Person, Store  # noqa: E402

#: The host's model. Sonnet, because the hosts readers use answer most turns with a
#: model of that size, and because ten scenarios at Opus would cost twice as much.
MODEL = "claude-sonnet-5-5"

#: Dollars per million tokens: input, output, cache read, cache write (five minutes).
#: A model not in it is refused, because a run whose price is unknown is a run whose cap
#: cannot be kept. Where each figure came from, as of 2026-10-06:
#:
#: - Input and output, every row: the model table in Anthropic's `claude-api` skill
#:   (cached 2026-09-25), which mirrors https://platform.claude.com/docs/en/about-claude/pricing
#:   — that page was not fetched for this. Sonnet 5, Opus 5 and Haiku 4.5 agree with
#:   `translate/anthropic_provider.PRICES` in this repo.
#: - Cache reads: $0.20 for Sonnet 5.5 and Opus 5.5 is stated in the same skill. The
#:   other three are the usual tenth of the input price, NOT confirmed from a source.
#: - Cache writes: 1.25 times input, the five-minute rate the skill gives in general
#:   terms; not confirmed per model.
#:
#: Check the pricing page before trusting a cost from any of them.
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.50),
    "claude-sonnet-5": (2.0, 10.0, 0.20, 2.50),
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.00),
    "claude-opus-5": (5.0, 25.0, 0.50, 6.25),
    "claude-haiku-4-5": (1.0, 5.0, 0.10, 1.25),
}

#: The cap a run keeps unless told otherwise, as David approved it.
MAX_DOLLARS = 5.0

#: Room for one reply. A host's replies here are a few lines; the rest is for thinking,
#: and every call is costed at this ceiling before it is made.
MAX_TOKENS = 8000

#: Round trips one reader turn may take before it is called a loop.
MAX_STEPS = 8

#: Where the links point, so `tools.shorten` rewrites them as the box does.
ADDRESS = "https://targum.page"

#: The grant a reader who ticked everything on the approval page gave.
SCOPES = "library record chat"

#: Where runs are kept. Gitignored: a run is a measurement of the day, not a fixture.
OUT = ROOT / "evals" / "connector"

#: What a host says about itself before the connector's own instructions. Generic on
#: purpose: neither Claude's nor ChatGPT's, and nothing about targum a host would not
#: know without being told.
HOST_PROMPT = (
    "You are a helpful assistant inside a chat app. The person has connected some apps, "
    "and their tools are available to you. Use a tool when it helps answer them. "
    "Each app's own instructions follow."
)

#: The job the build scenario asks about, and how long after the question it finishes,
#: so a host that holds with `wait_seconds` sees it move.
JOB_ID = "eval-build-0001"
JOB_FINISHES_AFTER = 4.0

#: Where the build the reader asks about came from.
JOB_LINK = "https://www.example.org/he/2026/09/kotel-tunnels"

#: The link the make-ready scenario pastes. Never fetched: `stubbed` answers for it.
LINK = "https://www.example.org/he/2026/10/shuk-mahane-yehuda"


# --- the world ------------------------------------------------------------------


@dataclass
class World:
    """Everything a tool call is answered from, in one temporary folder."""

    library: Any
    store: Store
    person: Person
    home: Path
    scopes: str = SCOPES
    address: str = ADDRESS


def _built(home: Path, name: str, source: str, title: str, lemmas: list[str]) -> None:
    """Enough of a targum on disk for the shelf to list it and coverage to measure it —
    the same files `tests/test_chat_tools.py` writes."""
    folder = home / name
    (folder / "reader").mkdir(parents=True, exist_ok=True)
    (folder / "reader" / "index.html").write_text("<html></html>", encoding="utf-8")
    (folder / "document.json").write_text(
        json.dumps(
            {
                "title": title,
                "language": "he",
                "source": source,
                "content_hash": "h",
                "blocks": [{"text": " ".join(lemmas)}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (folder / "annotation.json").write_text(
        json.dumps(
            {"tokens": {"0001.001-a": [{"lemma": lemma, "pos": "NOUN"} for lemma in lemmas]}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def build_world(root: Path, known: int = 300, learning: int = 20) -> World:
    """A reader with `known` of the commonest words marked known and the next `learning`
    marked learning, three texts on the shelf, and a build halfway through.

    The commonest words, as `scripts/eval_suggest.py` takes them: what a reader at this
    size actually knows. Not drawn from the texts, which would flatter every coverage
    number the host is handed.
    """
    from targum.chat import hebrew
    from targum.serve import Job, Library

    store = Store(root / "targum.db")
    signed = store.finish_sign_in(store.start_sign_in("eval@targum.page"))
    if signed is None:
        raise RuntimeError("could not make an account to measure with")
    person = signed[0]
    common = hebrew.common_words(language="he")
    if len(common) < known + learning:
        raise RuntimeError("wordfreq is not installed: uv sync --extra difficulty")
    words = [
        {
            "language": "he",
            "lemma": word,
            "status": 9 if n < known else 2,
            "band": "easy" if n < known else "moderate",
            "at": n + 1,
            "seen": n + 1,
        }
        for n, word in enumerate(common[: known + learning])
    ]
    store.push(person, {"words": words})
    out = root / "out"
    out.mkdir(parents=True, exist_ok=True)
    library = Library(out, store=store)
    home = library.home(person)
    everyday = list(common[:40]) + list(common[known : known + 10])
    _built(home, "רות", "test:ruth", "רות", everyday[:30] + ["גואל", "שדה", "קציר"])
    _built(library.shared, "אסתר", "test:esther", "אסתר", everyday[10:45] + ["מגילה"])
    _built(library.shared, "סיפור-ראשון", "test:story-a", "סיפור ראשון", everyday)
    # The build the reader asks about: started a minute ago, forty of sixty sentences
    # in, and finished by `finish_build` once the scenario has asked.
    job = Job(
        id=JOB_ID,
        source=JOB_LINK,
        title="מנהרות הכותל",
        language="he",
        owner=person.id,
        stage="working",
        done=40,
        total=60,
        home=home,
    )
    job.started = int(time.time() * 1000) - 60_000
    library.jobs[job.id] = job
    return World(library=library, store=store, person=person, home=home)


def finish_build(world: World, after: float = JOB_FINISHES_AFTER) -> threading.Timer:
    """Finish the build `after` seconds from now, as a worker thread would."""
    job = world.library.jobs[JOB_ID]
    job.stage, job.done = "working", 40
    job.reader = ""

    def done() -> None:
        _built(world.home, "מנהרות-הכותל", JOB_LINK, "מנהרות הכותל", ["כותל", "מנהרה", "אבן"])
        job.done = job.total
        job.reader = "מנהרות-הכותל/reader/index.html"
        job.stage = "done"

    timer = threading.Timer(after, done)
    timer.daemon = True
    timer.start()
    return timer


#: The page `describe_source` is handed for `LINK`: Hebrew, a few hundred words.
PAGE = (
    "<html><head><title>שוק מחנה יהודה בבוקר</title></head><body><article>"
    + "".join(
        f"<p>{line}</p>"
        for line in [
            "בבוקר השוק עוד שקט, והמוכרים מסדרים את הפירות והירקות על הדוכנים.",
            "אנשים באים לקנות לחם טרי, גבינה וזיתים לפני העבודה.",
            "בצהריים השוק מלא, ויש תור ארוך בכל מסעדה קטנה.",
            "בערב הדוכנים נסגרים, והבארים נפתחים, ומוזיקה עולה מהסמטאות.",
        ]
        * 12
    )
    + "</article></body></html>"
)


@contextlib.contextmanager
def stubbed() -> Iterator[None]:
    """The two doors that would leave the machine, answered here instead.

    `describe_source` asks `episode.find` whether the link is a recording and then reads
    the page through `ingest.url.fetch`; `quote_build` hands its job to
    `Library.prepare`, which fetches and segments. All three are stood in for, so the
    host is answered what a real page would have answered and nothing is fetched. The
    priced job carries a nine-minute recording, so the quote has credits to say.
    """
    from targum.ingest.url import Fetched
    from targum.serve import Library

    def prepare(self: Any, job: Any) -> None:
        job.title = "שוק מחנה יהודה בבוקר"
        job.language = "he"
        job.segments = job.total = 48
        job.estimate = 0.0
        job.audio = True
        job.seconds = 540.0
        job.stage = "ready"

    with contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch("targum.audio.episode.find", lambda url: None))
        stack.enter_context(
            mock.patch(
                "targum.ingest.url.fetch",
                lambda url, params=None: Fetched(text=PAGE, content_type="text/html"),
            )
        )
        stack.enter_context(mock.patch.object(Library, "prepare", prepare))
        yield


@contextlib.contextmanager
def isolated(root: Path) -> Iterator[None]:
    """The environment a run reads, pointed at the temporary folder.

    The same things `tests/conftest.py` shuts for the suite: the cache, the corpus
    ledger, the public shelves, and the publishers' feeds (which would make
    `search_sources` fetch live); and the recordings, dialogues, videos and portions,
    which are otherwise read from wherever the run was started. The per-sentence levels
    too, unless the catalogue is the real one they were measured against. The catalogue
    itself is chosen before import (`_catalogue_named`). Restored on the way out.
    """
    said = {
        "TARGUM_CACHE_DIR": str(root / "cache"),
        "TARGUM_SOURCES": str(root / "no-sources.json"),
        # The shelves read relative to the working directory (2026-10-06). Run from the
        # main checkout, `spoken.sources` walked its real `targum-out` — 171 recordings,
        # the dialogues and the videos — on the first `find_text`, which the eval timed
        # at 1,069 ms on a 24-entry fixture, and a real recording could have marked a
        # fixture text as spoken.
        "TARGUM_RECORDING_DIR": str(root / "recordings"),
        "TARGUM_DIALOGUE_DIR": str(root / "dialogues"),
        "TARGUM_VIDEO_DIR": str(root / "videos"),
        "TARGUM_PARASHA_DIR": str(root / "parasha"),
    }
    if on_fixture():
        said["TARGUM_SENTENCE_LEVELS"] = str(root / "no-sentence-levels.json")
    gone = ("TARGUM_LEDGER", "TARGUM_PUBLIC_SHELVES")
    before = {key: os.environ.get(key) for key in (*said, *gone)}
    os.environ.update(said)
    for key in gone:
        os.environ.pop(key, None)
    try:
        yield
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def on_fixture() -> bool:
    """Whether the catalogue this process loaded is the public fixture."""
    path = catalogue_module.catalogue_path()
    return path is not None and path.resolve() == FIXTURE_CATALOGUE.resolve()


def catalogue_said() -> str:
    """Which catalogue a row was measured against, so a run on the fixture's fifty rows
    is never read beside one on the real nine hundred as if they were the same."""
    named = "fixture" if on_fixture() else str(catalogue_module.catalogue_path())
    return f"{named} ({len(catalogue_module.CATALOGUE)} entries)"


# --- the host -------------------------------------------------------------------


def host_tools(world: World) -> list[dict[str, Any]]:
    """What `tools/list` says, in the shape the Messages API takes: `inputSchema` back to
    `input_schema`, and the title, annotations and `_meta` a host reads for itself left
    out, because the model is never shown them."""
    return [
        {
            "name": shape["name"],
            "description": shape["description"],
            "input_schema": shape["inputSchema"],
        }
        for shape in mcp_http.tool_shapes(connector.exposed(world.scopes, person=world.person))
    ]


def host_system() -> str:
    """A host's own prompt, then the connector's instructions as a host surfaces them."""
    return f'{HOST_PROMPT}\n\n<app name="targum">\n{mcp_http.INSTRUCTIONS}\n</app>'


def call_tool(world: World, at: int, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
    """One tool call, through `mcp_http.handle` exactly as `/mcp` makes it."""
    try:
        answered = mcp_http.handle(
            {
                "jsonrpc": "2.0",
                "id": at,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            library=world.library,
            store=world.store,
            person=world.person,
            scopes=world.scopes,
            address=world.address,
        )
    except mcp_http.RpcError as refused:
        # What a host is handed for a tool it does not hold: a JSON-RPC error, which it
        # reports to the model as a failed call.
        return refused.message, True
    assert answered is not None
    result = answered["result"]
    return str(result["content"][0]["text"]), bool(result["isError"])


# --- money ------------------------------------------------------------------------


class SpendCapReached(Exception):
    """The next call could take the run over `--max-dollars`, so it was not made."""


@dataclass
class Meter:
    """What a run has spent, and whether it may spend more."""

    model: str
    cap: float
    spent: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0

    def __post_init__(self) -> None:
        if self.model not in PRICES:
            raise SystemExit(f"No price for {self.model}; add it to PRICES with a date first.")

    def cost(self, usage: Any) -> float:
        given, written, read, wrote = PRICES[self.model]
        return (
            int(getattr(usage, "input_tokens", 0) or 0) * given
            + int(getattr(usage, "output_tokens", 0) or 0) * written
            + int(getattr(usage, "cache_read_input_tokens", 0) or 0) * read
            + int(getattr(usage, "cache_creation_input_tokens", 0) or 0) * wrote
        ) / 1_000_000

    def worst(self, request: dict[str, Any]) -> float:
        """The most the next call could cost: everything sent at the uncached-write price,
        counted at two characters a token (Hebrew and JSON run denser than English's
        four), and `max_tokens` written."""
        given, written, _, wrote = PRICES[self.model]
        sent = len(json.dumps(_plain(request), ensure_ascii=False)) / 2
        return (sent * max(given, wrote) + int(request["max_tokens"]) * written) / 1_000_000

    def allow(self, request: dict[str, Any]) -> None:
        if self.spent + self.worst(request) > self.cap:
            raise SpendCapReached(
                f"stopped before a call that could cost ${self.worst(request):.3f} "
                f"with ${self.spent:.3f} of ${self.cap:.2f} spent"
            )

    def add(self, usage: Any) -> float:
        cost = self.cost(usage)
        self.spent += cost
        self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        self.cache_read += int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        self.cache_write += int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        return cost


def _plain(value: Any) -> Any:
    """A request or a block as JSON: SDK objects dumped, everything else as it is."""
    if hasattr(value, "model_dump"):
        return value.model_dump(exclude_none=True)
    if isinstance(value, SimpleNamespace):
        return {key: _plain(one) for key, one in vars(value).items()}
    if isinstance(value, dict):
        return {key: _plain(one) for key, one in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(one) for one in value]
    return value


# --- one scenario -----------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    """A short conversation and the rules its replies are held to."""

    name: str
    turns: tuple[str, ...]
    checks: Callable[[list[dict[str, Any]]], dict[str, bool]]
    #: Run before the first turn, against the world: the build scenario starts its clock.
    setup: Callable[[World], Any] | None = None


@dataclass
class Turn:
    user: str
    reply: str = ""
    wall_s: float = 0.0
    first_token_s: float | None = None
    first_hebrew_s: float | None = None
    steps: int = 0
    stop_reason: str = ""
    tools: list[dict[str, Any]] = field(default_factory=list)
    #: The order things happened in: ("text", has_hebrew) and ("tool", name), so a rule
    #: can ask what came before the first Hebrew line.
    events: list[tuple[str, Any]] = field(default_factory=list)


HEBREW = re.compile(r"[א-ת]")


def stream_step(client: Any, request: dict[str, Any], turn: Turn, began: float) -> Any:
    """One round trip, streamed, timing the first token and the first Hebrew letter."""
    with client.messages.stream(**request) as stream:
        for event in stream:
            if getattr(event, "type", "") != "content_block_delta":
                continue
            delta = getattr(event, "delta", None)
            if getattr(delta, "type", "") != "text_delta":
                continue
            text = str(getattr(delta, "text", ""))
            now = time.perf_counter() - began
            if turn.first_token_s is None and text:
                turn.first_token_s = round(now, 3)
            if turn.first_hebrew_s is None and HEBREW.search(text):
                turn.first_hebrew_s = round(now, 3)
        return stream.get_final_message()


def run_scenario(
    scenario: Scenario,
    world: World,
    client: Any,
    meter: Meter,
    model: str,
    effort: str = "",
) -> dict[str, Any]:
    """Hold one conversation and measure it. A cap reached mid-way ends it, recorded."""
    tools = host_tools(world)
    system = host_system()
    messages: list[dict[str, Any]] = []
    turns: list[Turn] = []
    stopped = ""
    spent_before = meter.spent
    calls = 0
    if scenario.setup is not None:
        scenario.setup(world)
    started = time.perf_counter()
    try:
        for said in scenario.turns:
            turn = Turn(user=said)
            turns.append(turn)
            messages.append({"role": "user", "content": said})
            began = time.perf_counter()
            for _ in range(MAX_STEPS):
                request: dict[str, Any] = {
                    "model": model,
                    "max_tokens": MAX_TOKENS,
                    "system": system,
                    "tools": tools,
                    "messages": messages,
                    # Cached as a host would cache it: the tools and the instructions are
                    # the same on every call, and the history grows at the end.
                    "cache_control": {"type": "ephemeral"},
                    **({"output_config": {"effort": effort}} if effort else {}),
                }
                meter.allow(request)
                reply = stream_step(client, request, turn, began)
                meter.add(reply.usage)
                turn.steps += 1
                turn.stop_reason = str(reply.stop_reason)
                messages.append({"role": "assistant", "content": reply.content})
                text = "".join(str(block.text) for block in reply.content if block.type == "text")
                if text.strip():
                    turn.events.append(("text", bool(HEBREW.search(text))))
                uses = [block for block in reply.content if block.type == "tool_use"]
                if reply.stop_reason != "tool_use" or not uses:
                    turn.reply = text.strip()
                    break
                results = []
                for block in uses:
                    calls += 1
                    timed = time.perf_counter()
                    answer, failed = call_tool(world, calls, block.name, dict(block.input))
                    turn.events.append(("tool", block.name))
                    turn.tools.append(
                        {
                            "name": block.name,
                            "arguments": dict(block.input),
                            "bytes": len(answer.encode("utf-8")),
                            "ms": round((time.perf_counter() - timed) * 1000),
                            "failed": failed,
                            "result": answer,
                        }
                    )
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": answer,
                            **({"is_error": True} if failed else {}),
                        }
                    )
                # Every result of one reply in one message, as a host returns them.
                messages.append({"role": "user", "content": results})
            turn.wall_s = round(time.perf_counter() - began, 3)
    except SpendCapReached as cap:
        stopped = str(cap)
    shaped = [_turn_row(turn) for turn in turns]
    checks = scenario.checks(shaped) if not stopped else {}
    every = [tool for turn in turns for tool in turn.tools]
    return {
        "scenario": scenario.name,
        "model": model,
        "stopped": stopped,
        "wall_s": round(time.perf_counter() - started, 3),
        "first_hebrew_s": shaped[0]["first_hebrew_s"] if shaped else None,
        "tool_calls": len(every),
        "tool_names": [tool["name"] for tool in every],
        "result_bytes": sum(tool["bytes"] for tool in every),
        "largest_result": max((tool["bytes"] for tool in every), default=0),
        "dollars": round(meter.spent - spent_before, 4),
        "checks": checks,
        "passed": bool(checks) and all(checks.values()),
        "turns": shaped,
    }


def _turn_row(turn: Turn) -> dict[str, Any]:
    """A turn as it is written down: the results' sizes and a look at each, not whole."""
    return {
        "user": turn.user,
        "reply": turn.reply,
        "wall_s": turn.wall_s,
        "first_token_s": turn.first_token_s,
        "first_hebrew_s": turn.first_hebrew_s,
        "steps": turn.steps,
        "stop_reason": turn.stop_reason,
        "events": [list(one) for one in turn.events],
        "tools": [
            {**{k: v for k, v in tool.items() if k != "result"}, "said": tool["result"][:400]}
            for tool in turn.tools
        ],
        # Whole, for the rules; dropped before the row is written.
        "_results": [(tool["name"], tool["result"]) for tool in turn.tools],
    }


# --- the rules ----------------------------------------------------------------------

POINTS = re.compile(r"[ְ-ׇּׁׂ]")
HEBREW_WORD = re.compile(r"[א-ת][א-ת֑-ׇ׳״]*")
URL = re.compile(r"https?://[^\s<>()\[\]]+")


def urls(text: str) -> list[str]:
    return [found.rstrip(".,;:!?*_'\"") for found in URL.findall(text)]


def nikkud_ratio(text: str) -> float | None:
    """The share of Hebrew words carrying at least one vowel point, links left out."""
    words = [word for word in HEBREW_WORD.findall(URL.sub(" ", text)) if len(word) > 1]
    if not words:
        return None
    return sum(1 for word in words if POINTS.search(word)) / len(words)


def links_alone(text: str) -> bool:
    """Every link on a line of its own: the line is the link, or a list item or
    markdown link that is nothing but the link."""
    for line in text.splitlines():
        found = urls(line)
        if not found:
            continue
        if len(found) > 1:
            return False
        bare = line.strip().lstrip("-*•· ").strip().strip("*_")
        link = found[0]
        if bare in (link, f"<{link}>") or re.fullmatch(
            r"\[[^\]]*\]\(" + re.escape(link) + r"\)", bare
        ):
            continue
        return False
    return True


MONEY = re.compile(r"\$|₪|€|\bdollars?\b|\bpric(?:e|es|ed|ing)\b|\bquot(?:e|es|ed|ing)\b", re.I)
PRESS = re.compile(r"\b(?:press|click|tap|button)\b", re.I)


def money_words(text: str) -> list[str]:
    return MONEY.findall(text)


def lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def meaning_lines(text: str) -> int:
    """How many "= " lines, the meaning lines a host writes only when asked."""
    return sum(1 for line in lines(text) if line.strip().startswith("="))


def hebrew_words_said(text: str) -> int:
    """Hebrew words in the host's own lines: not the reader's "> " line, not the "= "
    meanings and not the "~ " note, which the contract's forty-word ceiling leaves out."""
    own = [line for line in lines(text) if not line.strip().startswith((">", "=", "~"))]
    return len(HEBREW_WORD.findall(URL.sub(" ", "\n".join(own))))


def said_before_hebrew(turn: dict[str, Any], tool: str) -> bool:
    """Whether `tool` was called before the first reply text carrying Hebrew."""
    for kind, what in turn["events"]:
        if kind == "tool" and what == tool:
            return True
        if kind == "text" and what:
            return False
    return False


def _calls(turns: list[dict[str, Any]], *names: str) -> list[dict[str, Any]]:
    return [tool for turn in turns for tool in turn["tools"] if tool["name"] in names]


def _results(turns: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    out = []
    for turn in turns:
        for called, text in turn["_results"]:
            if called == name:
                with contextlib.suppress(ValueError):
                    out.append(json.loads(text))
    return out


def _talk_reply(reply: str) -> dict[str, bool]:
    ratio = nikkud_ratio(reply)
    return {
        "hebrew": bool(HEBREW.search(reply)),
        "pointed": ratio is not None and ratio >= 0.8,
        "at_most_40_hebrew_words": hebrew_words_said(reply) <= 40,
        "meaning_lines_at_most_2": meaning_lines(reply) <= 2,
        "at_most_8_lines": len(lines(reply)) <= 8,
        "no_money": not money_words(reply),
    }


def check_talk(turns: list[dict[str, Any]]) -> dict[str, bool]:
    """Talk: the contract fetched before the first Hebrew line and once only, then short,
    pointed Hebrew with no translation under every line (the reader did not ask)."""
    first, *rest = turns
    out = {"how_to_talk_first": said_before_hebrew(first, "how_to_talk")}
    out.update({f"1_{key}": value for key, value in _talk_reply(first["reply"]).items()})
    for n, turn in enumerate(rest, start=2):
        out.update({f"{n}_{key}": value for key, value in _talk_reply(turn["reply"]).items()})
        out[f"{n}_opens_with_their_line"] = lines(turn["reply"])[:1] != [] and lines(turn["reply"])[
            0
        ].lstrip().startswith(">")
    out["how_to_talk_once"] = len(_calls(turns, "how_to_talk")) == 1
    return out


#: Any of the doors to the shelf. `find_text` stands for the other three over the
#: connector once #596 is in (they stay callable but are not listed), so a run counts
#: whichever the host was handed, before that change and after it.
SEARCHES = ("find_text", "suggest_next", "search_library", "search_my_shelf")


def check_next(turns: list[dict[str, Any]]) -> dict[str, bool]:
    """What next: one search, links alone on their lines, short links only."""
    reply = turns[-1]["reply"]
    found = urls(reply)
    return {
        "one_search": len(_calls(turns, *SEARCHES)) == 1,
        "gives_links": bool(found),
        "links_alone": links_alone(reply),
        "short_links": bool(found) and all("/reader/" not in link for link in found),
        "at_most_12_lines": len(lines(reply)) <= 12,
        "no_money": not money_words(reply),
    }


def check_done(turns: list[dict[str, Any]]) -> dict[str, bool]:
    """Is it done: check_job held with wait_seconds, asked at most twice, and its `said`
    line passed on as it was given."""
    reply = turns[-1]["reply"]
    asked = _calls(turns, "check_job")
    answers = _results(turns, "check_job")
    said = str(answers[-1].get("said") or "") if answers else ""
    flat = " ".join(reply.split())
    out = {
        "check_job_called": bool(asked),
        "waited": any(float(call["arguments"].get("wait_seconds") or 0) > 0 for call in asked),
        "asked_at_most_twice": len(asked) <= 2,
        "says_said": bool(said) and " ".join(said.split()) in flat,
        "links_alone": links_alone(reply),
        "no_money": not money_words(reply),
    }
    if answers and answers[-1].get("open"):
        out["gives_short_link"] = any("/r/" in link for link in urls(reply))
    return out


def check_ready(turns: list[dict[str, Any]]) -> dict[str, bool]:
    """Make it ready: priced through quote_build, its link alone on a line, never a
    quote or a price, credits said when there are any, and nothing to press."""
    reply = turns[-1]["reply"]
    quoted = [one.get("quote") or {} for one in _results(turns, "quote_build")]
    link = str(quoted[-1].get("open") or "") if quoted else ""
    credits = int(quoted[-1].get("credits") or 0) if quoted else 0
    out = {
        "quote_build_called": bool(quoted),
        "gives_the_link": bool(link) and link in urls(reply),
        "links_alone": links_alone(reply),
        "no_money_or_quote": not money_words(reply),
        "nothing_to_press": not PRESS.search(reply),
        "at_most_6_lines": len(lines(reply)) <= 6,
    }
    if credits:
        out["says_credits"] = bool(re.search(r"credit|קרדיט", reply, re.I))
    return out


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("talk", ("Talk with me in Hebrew.", "אתמול הלכתי לשוק וקניתי פירות"), check_talk),
    Scenario("next", ("What should I read next?",), check_next),
    Scenario(
        "done",
        (f"Is my text ready yet? The job id is {JOB_ID}.",),
        check_done,
        setup=finish_build,
    ),
    Scenario("ready", (f"Make this text ready for me: {LINK}",), check_ready),
)


# --- the run ------------------------------------------------------------------------


def checkpoint(path: Path, row: dict[str, Any]) -> None:
    """One scenario's row, appended and flushed to disk before the next is asked: what
    was paid for is kept even if the run stops on the next call."""
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {
        **row,
        "turns": [{k: v for k, v in t.items() if k != "_results"} for t in row["turns"]],
    }
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(clean, ensure_ascii=False) + "\n")
        out.flush()
        os.fsync(out.fileno())


def run(
    client: Any,
    *,
    model: str = MODEL,
    cap: float = MAX_DOLLARS,
    only: tuple[str, ...] = (),
    into: Path | None = None,
    effort: str = "",
) -> tuple[Path, list[dict[str, Any]]]:
    """Every scenario (or `only` those), each written down as it ends. Stops at the cap."""
    chosen = [one for one in SCENARIOS if not only or one.name in only]
    unknown = set(only) - {one.name for one in SCENARIOS}
    if unknown:
        raise SystemExit(f"No scenario called {', '.join(sorted(unknown))}.")
    stamp = datetime.now().strftime("%Y-%m-%dT%H%M%S")
    path = (into or OUT) / f"{stamp}.jsonl"
    meter = Meter(model=model, cap=cap)
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as where, isolated(Path(where)), stubbed():
        world = build_world(Path(where))
        for scenario in chosen:
            row = run_scenario(scenario, world, client, meter, model, effort)
            row["catalogue"] = catalogue_said()
            rows.append(row)
            checkpoint(path, row)
            if row["stopped"]:
                break
    return path, rows


def summary(rows: list[dict[str, Any]], path: Path, dry: bool = False) -> str:
    """One screen: a row a scenario, then the failed rules by name."""
    head = f"{'scenario':<8} {'wall':>6} {'1st he':>7} {'tools':>5} {'bytes':>7} {'$':>7}  result"
    out = [head, "-" * len(head)]
    for row in rows:
        first = row["first_hebrew_s"]
        verdict = "stopped" if row["stopped"] else ("pass" if row["passed"] else "FAIL")
        out.append(
            f"{row['scenario']:<8} {row['wall_s']:>5.1f}s "
            f"{('—' if first is None else f'{first:.1f}s'):>7} {row['tool_calls']:>5} "
            f"{row['result_bytes']:>7} {row['dollars']:>7.4f}  {verdict}"
            + (f"  [{', '.join(row['tool_names'])}]" if row["tool_names"] else "")
        )
        failed = [name for name, ok in row["checks"].items() if not ok]
        if failed:
            out.append(f"{'':<8} failed: {', '.join(failed)}")
        if row["stopped"]:
            out.append(f"{'':<8} {row['stopped']}")
    total = sum(row["dollars"] for row in rows)
    against = rows[0]["catalogue"] if rows else catalogue_said()
    spent = (
        f"nothing spent (dry run; ${total:.4f} is what its made-up usage would cost)"
        if dry
        else f"${total:.4f} spent"
    )
    out.append(f"\n{spent}, against the {against} catalogue; written to {path}")
    return "\n".join(out)


# --- the scripted host ----------------------------------------------------------------


class DryHost:
    """A host with no model behind it, for `--dry-run` and the tests: it calls the tool
    each scenario expects and answers from what the tool really returned, so every
    result still comes through `mcp_http.handle`. Its replies keep the contract; it is
    there to prove the plumbing, not to be measured."""

    def __init__(self) -> None:
        self.messages = self
        self.calls = 0

    def stream(self, **request: Any) -> _DryStream:
        self.calls += 1
        return _DryStream(self._answer(request["messages"]), request)

    def _answer(self, messages: list[dict[str, Any]]) -> list[SimpleNamespace]:
        last = messages[-1]["content"]
        if isinstance(last, str):
            return self._first(last, len(messages))
        asked = {
            block.id: block
            for block in messages[-2]["content"]
            if getattr(block, "type", "") == "tool_use"
        }
        result = last[0]
        name = asked[result["tool_use_id"]].name
        return [_text(self._reply(name, json.loads(result["content"])))]

    def _first(self, said: str, at: int) -> list[SimpleNamespace]:
        if said.startswith("Talk"):
            return [_tool("how_to_talk", {"language": "he"}, at)]
        if HEBREW.search(said):
            return [_text("> אֶתְמוֹל הָלַכְתִּי לַשּׁוּק וְקָנִיתִי פֵּרוֹת.\nאֵילוּ פֵּרוֹת קָנִיתָ?")]
        if "next" in said:
            return [_tool("suggest_next", {"language": "he", "limit": 3}, at)]
        if JOB_ID in said:
            return [_tool("check_job", {"id": JOB_ID, "wait_seconds": 10}, at)]
        return [_tool("quote_build", {"source": LINK}, at)]

    def _reply(self, name: str, got: dict[str, Any]) -> str:
        if name == "how_to_talk":
            return (
                "שָׁלוֹם! עַל מָה נְדַבֵּר הַיּוֹם?\n"
                "אֶפְשָׁר לְבַקֵּשׁ תִּרְגּוּם בְּכָל רֶגַע.\n"
                "= You can ask for the translation at any time."
            )
        if name == "suggest_next":
            rows = got.get("suggestions") or []
            said = []
            for row in rows[:2]:
                said.append(f"{row.get('title')}: {row.get('because')}")
                link = row.get("reader") or row.get("open") or ""
                if link:
                    said.append(str(link))
            return "\n".join(said) or "Nothing to suggest yet."
        if name == "check_job":
            return "\n".join(filter(None, [str(got.get("said") or ""), str(got.get("open") or "")]))
        quoted = got.get("quote") or {}
        return (
            f"{quoted.get('title')} is a short article about the market, and it uses "
            f"{quoted.get('credits')} credits.\n{quoted.get('open')}"
        )


class _DryStream:
    """The part of the SDK's `MessageStream` this file reads."""

    def __init__(self, content: list[SimpleNamespace], request: dict[str, Any]) -> None:
        self.content = content
        self.request = request

    def __enter__(self) -> _DryStream:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def __iter__(self) -> Iterator[SimpleNamespace]:
        for block in self.content:
            if block.type == "text":
                for piece in re.findall(r".{1,12}", block.text, re.S):
                    yield SimpleNamespace(
                        type="content_block_delta",
                        delta=SimpleNamespace(type="text_delta", text=piece),
                    )

    def get_final_message(self) -> SimpleNamespace:
        sent = len(json.dumps(_plain(self.request), ensure_ascii=False)) // 4
        wrote = sum(len(getattr(block, "text", "") or "") for block in self.content) // 4
        uses = any(block.type == "tool_use" for block in self.content)
        return SimpleNamespace(
            content=self.content,
            stop_reason="tool_use" if uses else "end_turn",
            usage=SimpleNamespace(input_tokens=sent, output_tokens=wrote + 20),
        )


def _text(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def _tool(name: str, arguments: dict[str, Any], at: int) -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=f"toolu_dry_{at}_{name}", name=name, input=arguments)


# --- command line ---------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--model", default=MODEL, help=f"the host's model (default {MODEL})")
    parser.add_argument("--max-dollars", type=float, default=MAX_DOLLARS)
    parser.add_argument(
        "--only", default="", help=f"comma-separated: {','.join(s.name for s in SCENARIOS)}"
    )
    parser.add_argument(
        "--effort", default="", help="output_config.effort; the model's default if unset"
    )
    parser.add_argument(
        "--catalogue",
        type=Path,
        default=FIXTURE_CATALOGUE,
        help="the catalogue the world reads (default: the public test fixture)",
    )
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument(
        "--dry-run", action="store_true", help="a scripted host: no key, no network, no cost"
    )
    args = parser.parse_args(argv)
    if args.dry_run:
        client: Any = DryHost()
    else:
        import anthropic

        client = anthropic.Anthropic()
    only = tuple(one.strip() for one in args.only.split(",") if one.strip())
    path, rows = run(
        client,
        model=args.model,
        cap=args.max_dollars,
        only=only,
        into=args.out,
        effort=args.effort,
    )
    print(summary(rows, path, dry=args.dry_run))
    return 0 if rows and all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
