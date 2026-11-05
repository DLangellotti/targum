"""The news yardstick's counts, from the feeds themselves (targum-internal#582).

David, 2026-10-30, on the language tables' question 1: news is counted on the box at
night, from what the followed feeds carry and nothing else. An item's words are the
feed's own full text where the feed carries one (`weekly.feeds.Item.full_text`), and
otherwise its title and summary. No page is fetched. The words are read by the service's
own DICTA, inside the service, so no second copy of the model is ever loaded beside it
(memory: box OOM was DICTA batching). `serve.start` runs `keep_counting` on a thread;
the nightly `targum-tables` unit, which refuses to load a model at all, takes the counts
into its snapshot an hour later.

Only counts are kept. The text lives inside one call to `count_news` and is let go:
a contribution's unit is a hash of the item's address, its source names the outlet
(`feed:<key>` from `sources.json`), its licence is the outlet's with "counts only", and
its tallies hold lemmas and numbers. No log line names a title.

Russian is counted the same way since targum-internal#637, from the Russian outlets
`sources.json` lists, read by the local Russian reader (`annotate.russian`, nothing bought)
and filed under `ru:news` (`registers.in_language`), so neither language's yardstick ever
reads the other's words. Each language has its own night: its own caps, its own turn.

The guard is `public_text`'s, by the same means: `count_news` takes only a `FeedItem`,
and only `feed_items` makes one, from the feeds `sources.json` lists as news in Hebrew
or Russian.
A reader's import, a subscription's feed, a chat turn or a web find cannot reach it by
any path. A find's lemma bag is folded by `tables.finds`, under a unit carrying the same
hash as an item's here, so one address is never counted twice.

An item is counted once: its unit is the address, so the same story in two of one
outlet's feeds, or still in the feed the next night, is passed over. A night counts at
most `NIGHT_ITEMS` items and `NIGHT_WORDS` words, outlet by outlet in turn, newest first.
"""

from __future__ import annotations

import hashlib
import logging
import sys
import threading
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from . import roots
from .corpus import lines_of, tally
from .registers import NEWS, in_language
from .store import Contribution, Store
from .words import PHRASES, RULE, WORDS

if TYPE_CHECKING:
    from ..chat.sources import Publisher

log = logging.getLogger(__name__)

#: The kinds of publisher whose items are counted as news.
KINDS = frozenset({"news"})

#: The languages counted, each by the reader a build of that language uses: DICTA for
#: Hebrew, the local Russian reader for Russian. Neither is bought. French lemmas are, and
#: French news waits for its own decision (targum-internal#637).
LANGUAGES = ("he", "ru")

#: The most words one night hands the model, in each language: about forty full
#: articles' worth, which is what David's "up to ~40 articles" was sized on. Most items
#: are a headline and a summary, about sixty words, so forty of those would be 2,500
#: words a night and news would take three weeks to reach the yardstick's floor
#: (design.md §12, 2026-11-01).
NIGHT_WORDS = 20_000

#: The most items one night counts in each language, whatever their length.
NIGHT_ITEMS = 400

#: When the night's round runs, UTC: an hour before `targum-tables.timer` (02:30), so the
#: snapshot sees what it counted, and clear of the 04:00 backup and every other timer.
AT_UTC = (1, 30)

#: How often the thread looks at the clock, in seconds.
CHECK_S = 600.0

#: How long after start the thread first looks, for the feeds the server keeps warm to
#: have come in.
FIRST_S = 180.0

#: Every unit and every source here starts with this.
PREFIX = "feed:"

#: What every row's licence ends with.
COUNTS_ONLY = "counts only; the text is never stored"

#: An outlet whose entry states no licence is taken as reserving every right.
RESERVED = "all rights reserved"

#: The tables one item is counted into, as a built text's are.
TABLES = (WORDS, PHRASES, roots.ROOTS)

#: Only `feed_items` holds this, so only it can make a `FeedItem` that `count_news` takes.
_SEAL = object()


@dataclass(frozen=True)
class FeedItem:
    """One item of a followed news feed, with the words the feed itself carries."""

    unit: str
    #: The publisher's key in `sources.json`.
    outlet: str
    licence: str
    published: float
    #: Whether the words are the feed's full text rather than a title and a summary.
    full: bool
    #: The words. Never written, never logged.
    text: str = field(repr=False)
    #: The outlet's language, one of `LANGUAGES`.
    language: str = "he"
    _seal: object = field(default=None, repr=False, compare=False)

    @property
    def sealed(self) -> bool:
        return self._seal is _SEAL

    @property
    def words(self) -> int:
        return len(self.text.split())


def unit_of(link: str, guid: str = "") -> str:
    """An item's unit: a hash of its address (as a server sees it), else of its guid, so
    the same item read again is the same unit and the row holds no address."""
    from ..weekly.feeds import link_key

    raw = link_key(link) if link.strip() else guid.strip()
    if not raw:
        return ""
    return PREFIX + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def licence_of(publisher: Publisher) -> str:
    """The licence line on an outlet's rows: its own, or every right reserved."""
    stated = " ".join(str(publisher.licence or "").split())
    return f"{stated or RESERVED}; {COUNTS_ONLY}"


def feed_items(
    kept: Mapping[str, Iterable[Any]],
    publishers: Iterable[Publisher],
    languages: Iterable[str] = LANGUAGES,
) -> list[FeedItem]:
    """The items `kept` holds for the followed news feeds in `languages`, one per unit,
    and nothing from any other feed: `kept` may hold whatever else a server pulls."""
    wanted = frozenset(languages)
    out: list[FeedItem] = []
    seen: set[str] = set()
    for publisher in publishers:
        if not publisher.feed or publisher.kind not in KINDS:
            continue
        language = (publisher.language or "he").split("-")[0].lower()
        if language not in wanted:
            continue
        licence = licence_of(publisher)
        for item in kept.get(publisher.feed) or ():
            unit = unit_of(str(getattr(item, "link", "") or ""), str(getattr(item, "guid", "")))
            if not unit or unit in seen:
                continue
            whole = str(getattr(item, "full_text", "") or "").strip()
            title = str(getattr(item, "title", "") or "").strip()
            summary = str(getattr(item, "summary", "") or "").strip()
            text = whole or "\n".join(one for one in (title, summary) if one)
            if not text:
                continue
            when = getattr(item, "published", None)
            seen.add(unit)
            out.append(
                FeedItem(
                    unit=unit,
                    outlet=publisher.key,
                    licence=licence,
                    published=when.timestamp() if isinstance(when, datetime) else 0.0,
                    full=bool(whole),
                    text=text,
                    language=language,
                    _seal=_SEAL,
                )
            )
    return out


def in_turn(items: Iterable[FeedItem]) -> list[FeedItem]:
    """Outlet by outlet in turn, each one's newest first, so one busy feed, or one that
    carries whole articles, never takes the whole night."""
    by_outlet: dict[str, list[FeedItem]] = {}
    for item in items:
        by_outlet.setdefault(item.outlet, []).append(item)
    queues = [sorted(run, key=lambda one: -one.published) for run in by_outlet.values()]
    out: list[FeedItem] = []
    for at in range(max((len(run) for run in queues), default=0)):
        out.extend(run[at] for run in queues if at < len(run))
    return out


def contributions(item: FeedItem, tool: str) -> dict[str, Contribution]:
    """What one item is filed as, table by table: under news in its own language."""
    return {
        table: Contribution(
            table=table,
            register=in_language(NEWS, item.language),
            unit=item.unit,
            source=PREFIX + item.outlet,
            licence=item.licence,
            tool=tool,
            rule=roots.rule() if table == roots.ROOTS else RULE,
        )
        for table in TABLES
    }


@dataclass
class NewsResult:
    """What one round did. Counts and outlet keys only."""

    counted: int = 0
    #: Already counted, on an earlier night or under another annotator.
    held: int = 0
    #: New, and left for the next night by the caps.
    left: int = 0
    #: Words handed to the model, as spaces split them.
    words: int = 0
    #: Words the words table counted.
    tokens: int = 0
    full: int = 0
    outlets: Counter[str] = field(default_factory=Counter)
    #: Items counted, by language.
    languages: Counter[str] = field(default_factory=Counter)
    failed: int = 0
    stopped: str = ""
    #: The process's memory, in MB: before the round, after it, and its high-water mark.
    memory: dict[str, float] = field(default_factory=dict)

    def __str__(self) -> str:
        memory = ", ".join(f"{key} {value:.0f} MB" for key, value in self.memory.items())
        by_language = ", ".join(f"{key} {n}" for key, n in sorted(self.languages.items()))
        return (
            f"{self.counted} items counted ({self.full} full texts) from"
            f" {len(self.outlets)} outlets"
            + (f" ({by_language})" if by_language else "")
            + f", {self.tokens} words; {self.held} held,"
            f" {self.left} left"
            + (f", {self.failed} failed" if self.failed else "")
            + (f"; stopped: {self.stopped}" if self.stopped else "")
            + (f"; memory {memory}" if memory else "")
        )


def default_annotator(language: str = "he") -> Any:
    """The annotator a build reads the language with, or None where this machine cannot
    read it without buying. In the service it shares the weights the service already holds
    (`annotate.dicta._LOADED`, `annotate.russian._LOADED`) and waits its turn on their
    lock, so it never loads a second copy and never runs beside a build's call.

    Russian is the local reader or nothing: never the model, which a Russian build falls
    back to where the `russian` extra is missing (`model_lemma.reads`), because a count
    never spends."""
    if language == "ru":
        from ..annotate import Annotator, russian

        if not russian.available():
            return None
        return Annotator(lemmatizer=russian.RussianLemmatizer())
    from .corpus import default_annotator as corpus_annotator

    return corpus_annotator()


def count_news(
    store: Store,
    items: Iterable[FeedItem],
    *,
    annotator: Any = None,
    words: int = NIGHT_WORDS,
    most: int = NIGHT_ITEMS,
    pause: Callable[[], None] | None = None,
) -> NewsResult:
    """Count the items not counted yet, up to `most` items and `words` words in each
    language.

    `annotator` is one annotator for every language (a test's stand-in), a mapping from a
    language to its annotator, or None for each language's own (`default_annotator`). A
    language this machine cannot read for free is left for a night that can, and named in
    `stopped`. One item is one call to the annotator, so a reader's build waits at most
    one item's reading for the model's lock. `pause` is called between items.
    """
    held = list(items)
    for item in held:
        if not isinstance(item, FeedItem) or not item.sealed:
            raise TypeError("count_news takes items from tables.news.feed_items, and nothing else")
    result = NewsResult()
    result.memory["before"] = memory_mb()[0]
    done = store.current_units(WORDS, (item.unit for item in held))
    fresh = []
    for item in held:
        if item.unit in done:
            result.held += 1
        else:
            fresh.append(item)
    order = _order(fresh)
    stops: list[str] = []
    for language in order:
        mine = [item for item in fresh if item.language == language]
        reader = _reader(annotator, language)
        if reader is None:
            result.left += len(mine)
            stops.append(f"no free {language} reader here")
            continue
        stop = _count_language(store, mine, reader, result, words=words, most=most, pause=pause)
        if stop:
            stops.append(stop if len(order) == 1 else f"{language}: {stop}")
    result.stopped = "; ".join(stops)
    _settle(result)
    return result


def _order(items: Iterable[FeedItem]) -> list[str]:
    """The languages `items` hold, in the order a night counts them."""
    present = {item.language for item in items}
    return [one for one in LANGUAGES if one in present] + sorted(present - set(LANGUAGES))


def nights(
    fresh: Iterable[FeedItem], *, words: int = NIGHT_WORDS, most: int = NIGHT_ITEMS
) -> dict[str, list[FeedItem]]:
    """What a night would count of `fresh`, language by language, each under its own
    caps as `count_news` applies them, for `targum tables news` to preview. Reads
    nothing: an item a night fails to read still counts against its caps here."""
    fresh = list(fresh)
    out: dict[str, list[FeedItem]] = {}
    for language in _order(fresh):
        night: list[FeedItem] = []
        read = 0
        for item in in_turn(one for one in fresh if one.language == language):
            if len(night) >= most or (night and read + item.words > words):
                break
            night.append(item)
            read += item.words
        out[language] = night
    return out


def _reader(annotator: Any, language: str) -> Any:
    if annotator is None:
        return default_annotator(language)
    if isinstance(annotator, Mapping):
        return annotator.get(language)
    return annotator


def _count_language(
    store: Store,
    fresh: list[FeedItem],
    annotator: Any,
    result: NewsResult,
    *,
    words: int,
    most: int,
    pause: Callable[[], None] | None,
) -> str:
    """Count one language's new items under its own caps; why it stopped early, or ""."""
    tool = str(annotator.name)
    counted = read = 0
    for at, item in enumerate(in_turn(fresh)):
        stopped = ""
        if counted >= most:
            stopped = f"the night's {most} items"
        elif read + item.words > words and counted:
            stopped = f"the night's {words} words"
        if stopped:
            result.left += len(fresh) - at
            return stopped
        try:
            tallies = tally(
                list(lines_of(item.text.splitlines())),
                annotator,
                item.unit,
                floor=1,
                language=item.language,
            )
        except Exception as error:  # noqa: BLE001 - one item never stops a night
            # The error's type only: a message can quote the words it choked on.
            log.warning("tables: a %s item was not counted: %s", item.outlet, type(error).__name__)
            result.failed += 1
            continue
        for table, one in contributions(item, tool).items():
            store.write(one, tallies[table])
        counted += 1
        read += item.words
        result.counted += 1
        result.full += int(item.full)
        result.words += item.words
        result.tokens += sum(tallies[WORDS].values())
        result.outlets[item.outlet] += 1
        result.languages[item.language] += 1
        if pause is not None:
            pause()
    return ""


def _settle(result: NewsResult) -> None:
    now, peak = memory_mb()
    result.memory["after"] = now
    if peak:
        result.memory["peak"] = peak


def memory_mb() -> tuple[float, float]:
    """This process's resident memory now and its high-water mark, in MB (0 where the
    system will not say). On the box, from /proc; elsewhere the mark alone."""
    now = peak = 0.0
    try:
        with open("/proc/self/status", encoding="ascii") as status:
            for line in status:
                if line.startswith("VmRSS:"):
                    now = int(line.split()[1]) / 1024
                elif line.startswith("VmHWM:"):
                    peak = int(line.split()[1]) / 1024
    except OSError:
        import resource

        mark = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # Bytes on macOS, kilobytes everywhere else.
        peak = mark / (1024 * 1024) if sys.platform == "darwin" else mark / 1024
    return now, peak


def last_round(store: Store) -> str:
    """When the newest news count was written (ISO, UTC), or ""."""
    if not store.file.is_file():
        return ""
    with closing(store._connect()) as db:
        row = db.execute(
            "SELECT MAX(written_at) FROM contribution WHERE tbl = ?"
            f" AND register IN ({', '.join('?' for _ in LANGUAGES)})"  # noqa: S608 - marks only
            " AND unit LIKE ?",
            (WORDS, *(in_language(NEWS, one) for one in LANGUAGES), PREFIX + "%"),
        ).fetchone()
    return str(row[0] or "")


def due(last: str, now: datetime) -> bool:
    """Whether tonight's round is owed: it is past `AT_UTC` today and nothing was counted
    since then."""
    hour, minute = AT_UTC
    since = now.astimezone(UTC).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now.astimezone(UTC) < since:
        return False
    return not last or last < since.isoformat(timespec="seconds")


def run_round(store: Store, annotator: Any = None) -> NewsResult:
    """One night: the items the server's feeds hold now (`chat.tools.FEEDS`, kept warm
    for `search_sources`), with no pull of its own."""
    from ..chat import sources as sources_module
    from ..chat import tools as tools_module

    items = feed_items(tools_module.FEEDS.kept(), sources_module.load())
    return count_news(store, items, annotator=annotator)


def keep_counting(stop: threading.Event | None = None) -> None:
    """The service's nightly round, on a thread of its own (`serve.start`). Returns at
    once where the corpus ledger is off. A round that fails is logged and not retried
    before the next night."""
    store = Store.from_env()
    if store is None:
        return
    stop = stop or threading.Event()
    if stop.wait(FIRST_S):
        return
    try:
        last = last_round(store)
    except Exception as error:  # noqa: BLE001 - never takes the server down
        log.warning("tables: the news counts could not be read: %s", error)
        last = ""
    while not stop.is_set():
        now = datetime.now(UTC)
        if due(last, now):
            last = now.isoformat(timespec="seconds")
            started = time.monotonic()
            try:
                result = run_round(store)
                log.info("tables: news %s in %.0f s", result, time.monotonic() - started)
            except Exception as error:  # noqa: BLE001 - never takes the server down
                log.warning("tables: the news round failed: %s", type(error).__name__)
        stop.wait(CHECK_S)
