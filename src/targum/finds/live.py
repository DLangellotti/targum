"""A live look on the web, when the pool has nothing that fits (targum-internal#615).

"Find me something" looks in the pool first (`button.py`). Where nothing there fits, it
may ask Anthropic's server-side web search (David, 2026-11-01: Anthropic over Brave) for
pages on the reader's topics, fetch them on the box, screen and score them exactly as the
hourly news round does (`news._keep`'s rules: the host and word screens, robots.txt, a
closed host never knocked on, too short dropped, one article pooled once), and keep what
passes **in the shared pool** as `web` finds. The button then chooses again from the pool,
so the next reader who wants the same thing gets it at once and for nothing.

**What the query says.** Topic words, a language and a level, all written by targum
(`TOPIC_WORDS`, `LEVEL_WORDS`): nothing the reader typed, no title they read, no word from
their list, no account. The model is told to run that query and is shown nothing else.
The results come back as the API's own result blocks; the model writes nothing we use.

**Who pays.** targum, inside the discovery budget (`pool.left`, `TARGUM_FINDS_BUDGET_USD`)
and written on the run's own row as it is spent (`pool.spend`), never a reader's credits
and never a `job` row. Held three ways: a search does not start unless the month has
`WORST_USD` left; a reader may start `READER_DAY_MOST` a day; the box `BOX_DAY_MOST` a
day. The same query inside `QUERY_KEEP_MS` is not run again: its pages are in the pool.

The per-reader count is kept in memory and nowhere else, so no table records which reader
looked for what; a restart forgives the day, which costs at most one day's cap.

**Off twice.** Only where the button is on (`button.on`) and the deployment also says
`TARGUM_FIND_LIVE`, so the day it starts spending is one line in `targum.env`. The privacy
notice names it since 2026-11-01 (clauses 4.2 and 5.2: Anthropic receives, for such a
search, the topics and the level of difficulty, without any identifier).

**A chip's pages stay its own.** A look made for chips (`chips.CHIPS`) tags what it pools
with them (`chips.tag`), so the next press of the same chip finds those pages in the pool
even where the lexicon has no topic for it, and the same query is not bought twice.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from . import news, pool, screen
from . import score as score_module
from .robots import ROBOTS, Robots

if TYPE_CHECKING:
    from ..accounts import Store

log = logging.getLogger(__name__)

FLAG = "TARGUM_FIND_LIVE"

#: The model that runs the search, and the tool. The model only issues the query: what
#: is kept is the search's own result blocks. Sonnet 5 is the cheapest model the project
#: already prices (`translate.anthropic_provider.PRICES`) that takes the current tool.
MODEL = "claude-sonnet-5"
TOOL = "web_search_20260209"
#: Searches one look may run: the query, and one retry where it found nothing.
MAX_USES = 2
MAX_TOKENS = 1024

#: The most a look is allowed to cost, as the budget gate reads it: two searches at
#: $0.01 and their results read as input, ~20–30k tokens at Sonnet 5's $2 a million,
#: with headroom. A look does not start unless the month has this much left.
WORST_USD = 0.15

#: Looks a reader may start in a day, and the box in a day (UTC).
READER_DAY_MOST = 3
BOX_DAY_MOST = 30

#: Pages fetched off one look's results, and side by side.
PAGES_MOST = 8
WORKERS = 6

#: A query run inside this long is not run again: what it found is in the pool.
QUERY_KEEP_MS = pool.DAY_MS

#: How long a finished look is kept for the page to read, in seconds.
KEEP_S = 600.0

SOURCE = "web"
RUN_SOURCE = "live"


def on() -> bool:
    """Whether a look on the web may run at all: the button's switch and its own."""
    from .button import on as button_on

    return button_on() and os.environ.get(FLAG, "").strip().lower() in {"1", "true", "yes"}


# -- the query ----------------------------------------------------------------------

#: What a topic is searched as, per language: plain words a page about it would carry.
#: Every topic is here so the chips can widen without a code change; only shown topics
#: are ever asked (`interests.Lexicon.shown`).
TOPIC_WORDS: dict[str, dict[str, str]] = {
    "he": {
        "everyday": "חיי היומיום",
        "family": "משפחה והורות",
        "people": "אנשים ורגשות",
        "food": "מתכונים ובישול",
        "money": "כסף וצרכנות",
        "travel": "טיולים ותחבורה",
        "work": "עבודה וקריירה",
        "school": "לימודים ובית ספר",
        "health": "בריאות וגוף",
        "culture": "תרבות ופנאי",
        "nature": "טבע ומזג אוויר",
        "politics": "פוליטיקה וממשל",
        "law": "משפט ופשיעה",
        "security": "צבא וביטחון",
        "science": "מדע וטכנולוגיה",
        "religion": "דת ומסורת",
    },
}

#: What a level adds to the query, by rung index on the language's ladder: an easy page
#: for the lower rungs, nothing for the rest.
LEVEL_WORDS: dict[str, tuple[tuple[int, str], ...]] = {
    "he": ((2, "בעברית קלה"), (99, "")),
}

#: What every query starts with: a page to read, not a shop or a video.
KIND_WORDS: dict[str, str] = {"he": "כתבה על"}

#: The topic searched where the reader skipped the chips and their reading said nothing.
ANY_TOPIC = "everyday"


def query(topics: Sequence[str], language: str, rung: int | None) -> str:
    """The words sent to the search: topic words, the language's own phrasing, the level.
    `topics` are chip codes (`chips.CHIPS`, each with its fixed phrase) or lexicon topics
    (`TOPIC_WORDS`). Built from constants alone, so it cannot carry anything of a
    reader's. Empty for a language with no words here."""
    from . import chips

    code = score_module.code(language)
    words = TOPIC_WORDS.get(code)
    if not words:
        return ""
    named = [
        chips.phrase(one, code) or words.get(one, "")
        for one in topics
        if chips.phrase(one, code) or one in words
    ][:2] or [words[ANY_TOPIC]]
    level = ""
    for top, said in LEVEL_WORDS.get(code, ()):
        if rung is None or rung <= top:
            level = said
            break
    parts = [KIND_WORDS.get(code, ""), " או ".join(named) if code == "he" else ", ".join(named)]
    if level:
        parts.append(level)
    return " ".join(part for part in parts if part)


# -- caps ---------------------------------------------------------------------------


def _day(at: int) -> int:
    return at // pool.DAY_MS


_READERS: dict[tuple[int, int], int] = {}
_READERS_LOCK = threading.Lock()


def reader_looks(person: int, at: int | None = None) -> int:
    when = pool.now_ms() if at is None else at
    with _READERS_LOCK:
        return _READERS.get((person, _day(when)), 0)


def _count_reader(person: int, at: int) -> None:
    with _READERS_LOCK:
        today = _day(at)
        for key in [key for key in _READERS if key[1] != today]:
            del _READERS[key]
        _READERS[(person, today)] = _READERS.get((person, today), 0) + 1


def box_looks(store: Store, at: int | None = None) -> int:
    when = pool.now_ms() if at is None else at
    row = store.db.execute(
        "SELECT COUNT(*) FROM find_run WHERE source = ? AND started >= ?",
        (RUN_SOURCE, _day(when) * pool.DAY_MS),
    ).fetchone()
    return int(row[0] or 0)


def ran_lately(store: Store, asked: str, at: int | None = None) -> bool:
    """Whether this exact query was run inside `QUERY_KEEP_MS`."""
    when = pool.now_ms() if at is None else at
    for (note,) in store.db.execute(
        "SELECT note FROM find_run WHERE source = ? AND started > ?",
        (RUN_SOURCE, when - QUERY_KEEP_MS),
    ):
        try:
            said = json.loads(note or "{}")
        except ValueError:
            continue
        if isinstance(said, dict) and said.get("query") == asked:
            return True
    return False


def refused(store: Store, person: int, asked: str, at: int | None = None) -> str:
    """Why a look may not start now, or "": `off`, `language` (no words for it), `reader`
    (this reader's day), `box` (the box's day), `budget` (the month), `lately` (the same
    query ran inside a day, and its pages are already in the pool)."""
    if not on():
        return "off"
    if not asked:
        return "language"
    when = pool.now_ms() if at is None else at
    if reader_looks(person, when) >= READER_DAY_MOST:
        return "reader"
    if box_looks(store, when) >= BOX_DAY_MOST:
        return "box"
    if pool.left(store, when) < WORST_USD:
        return "budget"
    if ran_lately(store, asked, when):
        return "lately"
    return ""


# -- the search ---------------------------------------------------------------------

SYSTEM = (
    "You run one web search for targum, a reading app for language learners, and say "
    "nothing else. Search with exactly the query you are given. Only if it returns "
    "nothing written in {language}, search once more with the same words shortened. Then "
    "answer with the single word: done."
)

LANGUAGE_NAMES = {"he": "Hebrew"}


@dataclass(frozen=True)
class Result:
    url: str
    title: str


@dataclass
class Searched:
    results: list[Result] = field(default_factory=list)
    searches: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def price(model: str, input_tokens: int, output_tokens: int, searches: int) -> float:
    from ..translate.anthropic_provider import DEFAULT_MODEL, PRICES, SEARCH_PRICE

    in_price, out_price = PRICES.get(model, PRICES[DEFAULT_MODEL])
    return input_tokens * in_price / 1e6 + output_tokens * out_price / 1e6 + searches * SEARCH_PRICE


def search(client: Any, asked: str, language: str) -> Searched:
    """One look: the query to the API's web search, and the pages it returned, with what
    the call cost. Raises what the client raises."""
    code = score_module.code(language)
    reply = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM.format(language=LANGUAGE_NAMES.get(code, code)),
        messages=[{"role": "user", "content": f"Query: {asked}"}],
        tools=[
            {
                "type": TOOL,
                "name": "web_search",
                "max_uses": MAX_USES,
                # The hosts the screen refuses are refused at the source too. No
                # `user_location`: the API does not take Israel (`chat.tools`).
                "blocked_domains": sorted(screen.denied_hosts())[:64],
            }
        ],
        output_config={"effort": "low"},
    )
    out = Searched()
    seen: set[str] = set()
    for block in _get(reply, "content", []) or []:
        kind = _get(block, "type", "")
        if kind == "server_tool_use" and _get(block, "name") == "web_search":
            out.searches += 1
        if kind != "web_search_tool_result":
            continue
        found = _get(block, "content", [])
        if not isinstance(found, list):  # an error is an object, not a list
            continue
        for one in found:
            url = str(_get(one, "url", "") or "")
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            seen.add(url)
            out.results.append(Result(url, str(_get(one, "title", "") or "")))
    usage = _get(reply, "usage")
    out.input_tokens = int(_get(usage, "input_tokens", 0) or 0) + int(
        _get(usage, "cache_read_input_tokens", 0) or 0
    )
    out.output_tokens = int(_get(usage, "output_tokens", 0) or 0)
    out.cost = price(MODEL, out.input_tokens, out.output_tokens, out.searches)
    return out


def client() -> Any:
    import anthropic

    return anthropic.Anthropic()


# -- one look, end to end -----------------------------------------------------------


@dataclass
class Look:
    """One look on the web, as the page polls it."""

    id: str
    person: int
    language: str
    asked: str
    #: What the pages it pools carry in their `topics`: the chips it was made for.
    tags: tuple[str, ...] = ()
    #: `searching`, `reading`, `checking`, then `done` or `failed`.
    stage: str = "searching"
    #: Pages being read, once the search has answered.
    pages: int = 0
    #: Finds this look added to the pool.
    added: list[int] = field(default_factory=list)
    #: The card's row, once chosen; None where nothing it found fits.
    pick: dict[str, Any] | None = None
    more: int = 0
    started: float = 0.0
    finished: float = 0.0
    spent: float = 0.0

    def state(self) -> dict[str, Any]:
        out: dict[str, Any] = {"search": self.id, "stage": self.stage, "pages": self.pages}
        if self.stage == "done":
            out["pick"] = self.pick
            out["more"] = self.more
        return out


def top_up(
    store: Store,
    look: Look,
    *,
    ask: Callable[[str, str], Searched],
    read: Callable[..., tuple[str, float]] = news.article,
    robots: Robots = ROBOTS,
    forms_for: Callable[[str], score_module.Forms | None] = score_module.load,
    at: int | None = None,
) -> list[int]:
    """Search, then read, screen, score and pool what came back. The ids it added."""
    when = pool.now_ms() if at is None else at
    code = score_module.code(look.language)
    forms = forms_for(code) if code in score_module.POOLED else None
    run = pool.start_run(store, RUN_SOURCE, when)
    found = news.Round()
    note: dict[str, Any] = {"query": look.asked}
    try:
        searched = ask(look.asked, code)
        pool.spend(store, run, searched.cost)
        found.spent += searched.cost
        look.spent += searched.cost
        note["searches"] = searched.searches
        if forms is None:
            note["stopped"] = "no map for the language"
            return []
        shut = set(store.closed(limit=500))
        todo: list[news.Item] = []
        from ..weekly.feeds import link_key

        for result in searched.results:
            link = link_key(result.url)
            if pool.known(store, link):
                # Already pooled, by the news round or another look: it is about this
                # chip too, so the pool matches it from now on.
                _tag(store, link, look.tags)
                continue
            item = news.Item(
                link=link,
                title=result.title,
                language=code,
                publisher=_host(link),
                published=when,
                full_text="",
                topics=look.tags,
            )
            found.seen += 1
            why = screen.passes(_host(link), result.title)
            if not why and _host(link) in shut:
                why = "closed"
            if why:
                _drop(store, item, why, found, when)
                continue
            todo.append(item)
            if len(todo) >= PAGES_MOST:
                break
        look.stage = "reading"
        look.pages = len(todo)

        def one(item: news.Item) -> tuple[news.Item, str, float, str]:
            try:
                if not robots.allowed(item.link):
                    return item, "", 0.0, "robots"
                text, cost = read(item.link, proxy=pool.left(store, when) > WORST_USD)
                return item, text, cost, ""
            except Exception as error:  # noqa: BLE001 - one page never stops a look
                log.info("finds: live %s not read: %s", _host(item.link), error)
                return item, "", 0.0, "unreadable"
            finally:
                store.close()

        with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="find-live") as workers:
            read_back = list(workers.map(one, todo))
        look.stage = "checking"
        added: list[int] = []
        for item, text, cost, why in read_back:
            if cost:
                found.spent += cost
                look.spent += cost
                pool.spend(store, run, cost)
            if why:
                _drop(store, item, why, found, when)
                continue
            found.fetched += 1
            kept = _keep(store, item, text, forms, found, when)
            if kept:
                added.append(kept)
        return added
    finally:
        pool.finish_run(
            store,
            run,
            seen=found.seen,
            kept=found.kept,
            dropped=found.dropped,
            note=note,
            at=pool.now_ms() if at is None else at,
        )


def _tag(store: Store, link: str, tags: Sequence[str]) -> None:
    if not tags:
        return
    row = store.db.execute(
        "SELECT topics FROM find WHERE url = ? AND screen = ?", (link, pool.KEPT)
    ).fetchone()
    if row is None:
        return
    held = [one for one in str(row[0] or "").split(",") if one]
    more = [one for one in tags if one not in held]
    if more:
        with store.write() as db:
            db.execute("UPDATE find SET topics = ? WHERE url = ?", (",".join(held + more), link))


def _drop(store: Store, item: news.Item, why: str, found: news.Round, when: int) -> None:
    found.dropped[why] += 1
    pool.drop(
        store,
        language=item.language,
        source=SOURCE,
        url=item.link,
        reason=why,
        host=_host(item.link),
        at=when,
    )


def _keep(
    store: Store,
    item: news.Item,
    text: str,
    forms: score_module.Forms,
    found: news.Round,
    when: int,
) -> int:
    """The hourly round's rules for one page, kept as a `web` find. Its id, or 0."""
    if screen.term_in(f"{item.title}\n{text}"):
        _drop(store, item, "words", found, when)
        return 0
    scored = forms.score(f"{item.title}\n{text}")
    if scored.tokens < news.LEAST_WORDS:
        _drop(store, item, "short", found, when)
        return 0
    fingerprint = news.digest(text)
    if pool.known_digest(store, fingerprint):
        _drop(store, item, "same", found, when)
        return 0
    added = pool.add(
        store,
        language=item.language,
        source=SOURCE,
        url=item.link,
        bag=scored.bag,
        tokens=scored.tokens,
        unresolved=scored.unresolved,
        rung=forms.rung_of(scored),
        digest=fingerprint,
        title=item.title,
        host=_host(item.link),
        publisher=item.publisher,
        published=item.published,
        topics=item.topics,
        at=when,
    )
    if added:
        found.kept += 1
    return added


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


# -- the looks in flight ------------------------------------------------------------


class Looks:
    """The looks running and lately finished, for the page to poll. In memory: a look
    is a few seconds of one reader's visit, and a restart ends it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._held: dict[str, Look] = {}

    def start(
        self,
        store: Store,
        person: int,
        language: str,
        asked: str,
        choose: Callable[[], Sequence[dict[str, Any]]],
        *,
        ask: Callable[[str, str], Searched] | None = None,
        clock: Callable[[], float] | None = None,
        wait: bool = False,
        tags: Sequence[str] = (),
        **more: Any,
    ) -> Look:
        """Start one look in a thread of its own; `choose` is the button's ranking for
        this reader, run again once the pool has the new pages. Counted against the
        reader's day as it starts."""
        import time

        now = (clock or time.monotonic)()
        look = Look(
            id=secrets.token_hex(8),
            person=person,
            language=language,
            asked=asked,
            tags=tuple(tags),
            started=now,
        )
        _count_reader(person, pool.now_ms())
        with self._lock:
            for key in [
                k for k, v in self._held.items() if v.finished and now - v.finished > KEEP_S
            ]:
                del self._held[key]
            self._held[look.id] = look
        asker = ask or (lambda q, lang: search(client(), q, lang))

        def run() -> None:
            try:
                look.added = top_up(store, look, ask=asker, **more)
                rows = list(choose())
                from .button import fits

                look.pick = rows[0] if fits(rows) else None
                look.more = max(0, len(rows) - 1) if look.pick else 0
                look.stage = "done"
            except Exception:  # noqa: BLE001 - a failed look is a sentence, not a crash
                log.exception("finds: a live look failed")
                look.stage = "failed"
            finally:
                look.finished = (clock or time.monotonic)()
                if not wait:
                    store.close()

        if wait:
            run()
        else:
            threading.Thread(target=run, name="find-live", daemon=True).start()
        return look

    def get(self, look_id: str, person: int) -> Look | None:
        """A look, only for the reader who started it."""
        with self._lock:
            look = self._held.get(look_id)
        return look if look is not None and look.person == person else None


LOOKS = Looks()


def forget() -> None:
    """Drop the day's per-reader counts (tests)."""
    with _READERS_LOCK:
        _READERS.clear()
