"""The hourly round over the news (targum-internal#619; plan §1.1).

It adds no pull to the feeds: it reads the items `chat.tools.FEEDS` already holds for
`search_sources`, which the server keeps warm every few minutes. For each item in a
language the scorer has a map for, and not in the pool yet:

1. the host and the headline are screened (`screen`);
2. the article's words are the feed's own full text where the feed carries it
   (`weekly.feeds.Item.full_text`), and otherwise the page, fetched once through the one
   door (`ingest.url.fetch`) and read the way a paste reads it
   (`ingest.url.article_paragraphs`) — after robots.txt says yes (`robots`) and never
   from a host whose last knock was refused (`Store.closed`);
3. the opening is screened again, the words are scored (`score.Forms.score`) and let go;
4. the find is kept with its counts, or dropped with its reason.

The page is never kept: not the text, not the page memory a paste uses
(`ingest.url.PAGES`), only what `pool.add` writes. A fetch through the residential proxy,
which the door makes only after a direct knock was refused, is targum's spend, counted on
the run at the exit's $1 a gigabyte; once the month's discovery budget is gone, the door
is asked for the direct knock alone.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from . import pool, screen
from . import score as score_module
from .robots import ROBOTS, Robots

if TYPE_CHECKING:
    from ..accounts import Store
    from ..chat.sources import Publisher

log = logging.getLogger(__name__)

#: How often the server runs a round, in seconds (plan §3: hourly in practice).
EVERY_S = 3600.0

#: The most pages one round fetches, all hosts together, and from any one host: a round
#: that cannot finish leaves the rest for the next, which sees them as new.
ROUND_MOST = 400
HOST_MOST = 30

#: The most news rows a day, kept or dropped: the source's daily cap (plan §4).
DAY_MOST = 3000

#: Hosts fetched side by side; within one host, one page at a time (`POLITE_S`).
WORKERS = 6

#: An article shorter than this many running words is a headline, not something to read.
LEAST_WORDS = 80

#: What a gigabyte through the residential proxy costs (memory: DataImpulse $1/GB).
PROXY_USD_PER_GB = 1.0

#: The kinds of publisher whose items are articles.
ARTICLES = frozenset({"news", "magazine", "blog"})

_SPACE = re.compile(r"\s+")


@dataclass
class Round:
    """What one round did."""

    seen: int = 0
    kept: int = 0
    fetched: int = 0
    dropped: Counter[str] = field(default_factory=Counter)
    spent: float = 0.0
    stopped: str = ""

    def __str__(self) -> str:
        drops = ", ".join(f"{n} {why}" for why, n in sorted(self.dropped.items()))
        return (
            f"{self.seen} new, {self.kept} kept, {self.fetched} fetched"
            + (f", dropped {drops}" if drops else "")
            + (f", ${self.spent:.4f}" if self.spent else "")
            + (f", stopped: {self.stopped}" if self.stopped else "")
        )


def digest(text: str) -> str:
    """The words' fingerprint, so one article at two addresses is pooled once."""
    return hashlib.sha256(_SPACE.sub(" ", text).strip().encode("utf-8")).hexdigest()[:24]


def article(url: str, *, proxy: bool) -> tuple[str, float]:
    """An article's words off its page, and what reading it cost targum in dollars."""
    from ..ingest.url import article_paragraphs, fetch

    got = fetch(url, proxy=proxy)
    cost = 0.0
    if got.via == "proxy":
        size = len(got.raw) if got.raw else len(got.text.encode("utf-8"))
        cost = size / 1e9 * PROXY_USD_PER_GB
    if not got.is_html:
        return got.text, cost
    return "\n\n".join(text for _, _, text in article_paragraphs(got.text)), cost


@dataclass(frozen=True)
class Item:
    """One feed item, with what the round needs from its publisher."""

    link: str
    title: str
    language: str
    publisher: str
    published: int
    full_text: str
    topics: tuple[str, ...]


def items_from(kept: Mapping[str, list[Any]], publishers: Iterable[Publisher]) -> list[Item]:
    """The feeds' held items as the round reads them, newest first."""
    from ..chat.tools import _item_topics
    from ..weekly.feeds import link_key

    out: list[Item] = []
    for publisher in publishers:
        if not publisher.feed or publisher.kind not in ARTICLES:
            continue
        for item in kept.get(publisher.feed) or ():
            link = str(getattr(item, "link", "") or "")
            if not link.startswith(("http://", "https://")):
                continue
            when = getattr(item, "published", None)
            out.append(
                Item(
                    link=link_key(link),
                    title=str(getattr(item, "title", "") or ""),
                    language=score_module.code(publisher.language or "he"),
                    publisher=publisher.publisher or publisher.name,
                    published=int(when.timestamp() * 1000) if when else 0,
                    full_text=str(getattr(item, "full_text", "") or ""),
                    topics=tuple(_item_topics(publisher, item)),
                )
            )
    out.sort(key=lambda one: -one.published)
    return out


def refresh(
    store: Store,
    kept: Mapping[str, list[Any]] | None = None,
    publishers: Iterable[Publisher] | None = None,
    *,
    read: Callable[..., tuple[str, float]] = article,
    robots: Robots = ROBOTS,
    forms_for: Callable[[str], score_module.Forms | None] = score_module.load,
    at: int | None = None,
) -> Round:
    """One round: every new item of the followed feeds, screened, scored and pooled.
    Expired finds go first. Fetches nothing for a language with no map."""
    from ..chat import sources as sources_module
    from ..chat import tools as tools_module

    when = pool.now_ms() if at is None else at
    pool.expire(store, when)
    held = tools_module.FEEDS.kept() if kept is None else kept
    following = sources_module.load() if publishers is None else list(publishers)
    found = Round()
    maps: dict[str, score_module.Forms | None] = {}
    fresh: list[Item] = []
    for item in items_from(held, following):
        if item.language not in maps:
            pooled = item.language in score_module.POOLED
            maps[item.language] = forms_for(item.language) if pooled else None
        if maps[item.language] is None or pool.known(store, item.link):
            continue
        fresh.append(item)
    if not fresh:
        return found
    run = pool.start_run(store, "news", when)
    shut = set(store.closed(limit=500))
    day_left = max(0, DAY_MOST - _today(store, when))

    def dropped(item: Item, why: str) -> None:
        found.dropped[why] += 1
        pool.drop(
            store,
            language=item.language,
            source="news",
            url=item.link,
            reason=why,
            host=_host(item.link),
            at=when,
        )

    # Everything that needs no fetch first, in this thread; what is left is grouped by
    # host for the workers.
    by_host: dict[str, list[Item]] = {}
    for item in fresh:
        if found.seen >= day_left:
            found.stopped = f"the day's {DAY_MOST} news rows"
            break
        found.seen += 1
        host = _host(item.link)
        why = screen.passes(host, item.title)
        if why:
            dropped(item, why)
            continue
        if item.full_text:
            _keep(store, item, item.full_text, maps[item.language], found, dropped, when)
            continue
        if host in shut:
            dropped(item, "closed")
            continue
        queue = by_host.setdefault(host, [])
        if len(queue) < HOST_MOST:
            queue.append(item)
    order = sorted(by_host.items(), key=lambda pair: -len(pair[1]))
    budget_left = [ROUND_MOST]

    def walk(items: list[Item]) -> None:
        try:
            _walk(items)
        finally:
            # A worker's own connection, which a thread-local never gives back by itself
            # (`accounts.Store`).
            store.close()

    def _walk(items: list[Item]) -> None:
        for item in items:
            if budget_left[0] <= 0:
                return
            budget_left[0] -= 1
            if not robots.allowed(item.link):
                dropped(item, "robots")
                continue
            proxy = pool.left(store, when) > 0
            try:
                text, cost = read(item.link, proxy=proxy)
            except Exception as error:  # noqa: BLE001 - one page never stops a round
                log.info("finds: %s not read: %s", _host(item.link), error)
                dropped(item, "unreadable")
                continue
            found.fetched += 1
            if cost:
                found.spent += cost
                pool.spend(store, run, cost)
            _keep(store, item, text, maps[item.language], found, dropped, when)

    with ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="finds") as workers:
        for result in [workers.submit(walk, items) for _, items in order]:
            try:
                result.result()
            except Exception as error:  # noqa: BLE001 - one host never stops the rest
                log.warning("finds: a host's round failed: %s", error)
    if budget_left[0] <= 0 and not found.stopped:
        found.stopped = f"the round's {ROUND_MOST} pages"
    pool.finish_run(
        store,
        run,
        seen=found.seen,
        kept=found.kept,
        dropped=found.dropped,
        note={"stopped": found.stopped} if found.stopped else "",
    )
    return found


def _keep(
    store: Store,
    item: Item,
    text: str,
    forms: score_module.Forms | None,
    found: Round,
    dropped: Callable[[Item, str], None],
    when: int,
) -> None:
    if forms is None:
        return
    if screen.term_in(f"{item.title}\n{text}"):
        dropped(item, "words")
        return
    scored = forms.score(f"{item.title}\n{text}")
    if scored.tokens < LEAST_WORDS:
        dropped(item, "short")
        return
    fingerprint = digest(text)
    if pool.known_digest(store, fingerprint):
        dropped(item, "same")
        return
    added = pool.add(
        store,
        language=item.language,
        source="news",
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


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _today(store: Store, when: int) -> int:
    row = store.db.execute(
        "SELECT COUNT(*) FROM find WHERE source = 'news' AND found > ?", (when - pool.DAY_MS,)
    ).fetchone()
    return int(row[0] or 0)
