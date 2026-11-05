"""The nightly round over the open web (targum-internal#622; plan §8 D; David, 2026-11-03).

Each night Anthropic's server-side web search looks for Hebrew pages on the forty topics
of "Find me something" (`chips.CHIPS`, each with its fixed Hebrew phrase), and what it
finds is read, screened, scored and pooled as `web` finds, by the hourly news round's
rules, so Home's card and "More that fit you" can offer them. Any licence: a find is
personal reading, built as the reader's own import when they press it; one whose licence
clears the bar joins the library on open by the path every find takes (`promote`).

One round, on a timer on the box (`targum finds web`, `targum-finds-web.timer`):

1. **One search a topic.** The query is the chip's phrase and nothing else: no reader, no
   level, no word anybody typed. The model (`MODEL`, the cheapest that takes the search
   tool) is told to run it once and is shown nothing more; what is kept is the search's
   own result list, never a word the model wrote. The night starts where the last one
   stopped (`_start`), so every topic comes round, and a query a live look bought lately
   (`live.ran_lately`'s rule over `LATELY_MS`) is not bought again.
2. **The pages, direct.** Each result is fetched once straight from its site, never
   through the paid proxy, only where robots.txt allows (`robots`), never from a host
   whose last knock was refused (`Store.closed`), at most `HOST_MOST` from one host a
   night. The words are screened, scored (`score.Forms.score`) and let go: the pool keeps
   the address, title, outlet, the day the page says it was published, and the lemma
   counts (`pool.add`), never the text.

**What it costs targum, held three ways.** Each call's cost is read off the API's own
usage — the searches it ran at `SEARCH_PRICE`, the tokens at the model's price — and
written on the run as it is spent (`pool.spend`). A search starts only where the night
has room for the dearest call yet seen (`WORST_CALL_USD` at least), so a night stops
before `NIGHT_USD`, never after it; the night's allowance is also paced against the month
(`allowance`): what `TARGUM_FINDS_BUDGET_USD` has left, less `LEAVE_USD` for the other
sources, over the days left in the month.

**Off unless the box says so** (`TARGUM_FINDS_WEB`): the timer runs every night and does
nothing until then.

**Counted into the language tables as counts** (`tables.finds`): a web find goes to news,
social, video or podcasts where its host says so, and otherwise to `web`.
"""

from __future__ import annotations

import calendar
import json
import logging
import os
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from . import chips, live, news, pool, screen, steer
from . import score as score_module
from .robots import ROBOTS, Robots

if TYPE_CHECKING:
    from ..accounts import Store
    from ..chat.sources import Publisher

log = logging.getLogger(__name__)

FLAG = "TARGUM_FINDS_WEB"

#: The pool's source for what it keeps: a web find, like a live look's.
SOURCE = live.SOURCE
#: The run's own name on `find_run`, so the back office tells a night from a look.
RUN_SOURCE = "web"

#: The model that runs the search, and the tool. Haiku 4.5 is the cheapest model the
#: project prices that takes Anthropic's web search; it takes the basic tool, not the
#: dynamic-filtering one, and no `effort` (`translate.anthropic_provider`).
MODEL = "claude-haiku-4-5"
TOOL = "web_search_20250305"
MAX_TOKENS = 256

#: The night's hard cap in dollars (David, 2026-11-03: "$1 a night").
NIGHT_USD = 1.0
#: What a night leaves of the month's discovery budget for the other sources.
LEAVE_USD = 10.0
#: The least a call is assumed to cost when the gate asks whether the next one fits: one
#: search at $0.01 and up to 50k tokens of results read at Haiku's $1 a million.
WORST_CALL_USD = 0.06
#: A call dearer than the gate allowed for raises the next allowance to this times it.
WORST_HEADROOM = 1.5

#: Pages read off one search's results, and from one host in a night.
PAGES_PER_QUERY = 8
HOST_MOST = 5

#: A night stops starting searches after this long, so it is done before the YouTube
#: round at 01:00 (the timer starts it at 00:10).
DEADLINE_S = 45 * 60.0

#: A query run this lately, by a live look or a night, is not bought again. Under a day,
#: so last night's run, a minute short of twenty-four hours ago, never holds tonight's.
LATELY_MS = 20 * 60 * 60 * 1000

#: The languages a night runs for: those the scorer has a map for and the chips a phrase.
LANGUAGES = ("he", "ru")

SYSTEM = (
    "You run web searches for targum, a reading app for language learners, and say "
    "nothing else. Search once with the query you are given, exactly as written. Then "
    "answer with the single word: done."
)


def on() -> bool:
    return os.environ.get(FLAG, "").strip().lower() in {"1", "true", "yes"}


# -- the queries ---------------------------------------------------------------------


def queries(language: str) -> list[tuple[str, str]]:
    """(chip code, query) for every chip with a phrase in the language, in the chips'
    order: built from constants alone, so they carry nothing of anybody's."""
    code = score_module.code(language)
    return [(chip.code, chip.phrases[code]) for chip in chips.CHIPS if chip.phrases.get(code)]


def rotated(asked: Sequence[Any], start: int) -> list[Any]:
    if not asked:
        return []
    at = start % len(asked)
    return [*asked[at:], *asked[:at]]


def _start(store: Store, language: str = "he") -> int:
    """Where tonight's queries start: where the last night in the language stopped."""
    return pool.last_next(store, RUN_SOURCE, language)


def bought_lately(store: Store, asked: str, at: int) -> bool:
    """Whether a live look or a night ran this exact query inside `LATELY_MS`."""
    for (note,) in store.db.execute(
        "SELECT note FROM find_run WHERE source IN (?, ?) AND started > ?",
        (live.RUN_SOURCE, RUN_SOURCE, at - LATELY_MS),
    ):
        try:
            said = json.loads(note or "{}")
        except ValueError:
            continue
        if not isinstance(said, dict):
            continue
        ran = said.get("queries")
        if said.get("query") == asked or (isinstance(ran, list) and asked in ran):
            return True
    return False


# -- the money -----------------------------------------------------------------------


def spent_today(store: Store, at: int) -> float:
    """What the nights have cost since midnight UTC, a run by hand included."""
    row = store.db.execute(
        "SELECT COALESCE(SUM(spent), 0) FROM find_run WHERE source = ? AND started >= ?",
        (RUN_SOURCE, (at // pool.DAY_MS) * pool.DAY_MS),
    ).fetchone()
    return float(row[0] or 0.0)


def days_left(at: int) -> int:
    """Days left in the month (UTC), today included."""
    day = datetime.fromtimestamp(at / 1000, tz=UTC)
    return calendar.monthrange(day.year, day.month)[1] - day.day + 1


def allowance(store: Store, at: int) -> float:
    """What a night starting now may spend, in dollars: what `NIGHT_USD` has left today
    after any earlier run, or less where the month's budget, less `LEAVE_USD` for the
    other sources and shared over the days left, says so."""
    paced = max(0.0, pool.left(store, at) - LEAVE_USD) / days_left(at)
    return max(0.0, min(NIGHT_USD - spent_today(store, at), paced))


# -- the search ----------------------------------------------------------------------


@dataclass(frozen=True)
class Hit:
    url: str
    title: str
    #: The age the search gives the page, as it says it ("April 30, 2025"), or "".
    age: str = ""


@dataclass
class Searched:
    hits: list[Hit] = field(default_factory=list)
    searches: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def search(client: Any, asked: str) -> Searched:
    """One search, and what it cost by the API's own usage. Raises what the client raises."""
    reply = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM,
        messages=[{"role": "user", "content": f"Query: {asked}"}],
        tools=[
            {
                "type": TOOL,
                "name": "web_search",
                "max_uses": 1,
                # The hosts the screen refuses are refused at the source too. No
                # `user_location`: the API does not take Israel (`chat.tools`).
                "blocked_domains": sorted(screen.denied_hosts())[:64],
            }
        ],
    )
    out = Searched()
    seen: set[str] = set()
    blocks = 0
    for block in _get(reply, "content", []) or []:
        kind = _get(block, "type", "")
        if kind == "server_tool_use" and _get(block, "name") == "web_search":
            blocks += 1
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
            out.hits.append(
                Hit(url, str(_get(one, "title", "") or ""), str(_get(one, "page_age", "") or ""))
            )
    usage = _get(reply, "usage")
    used = _get(usage, "server_tool_use")
    out.searches = max(blocks, int(_get(used, "web_search_requests", 0) or 0))
    # A cache write is dearer than a plain read; counted as one and a quarter.
    out.input_tokens = (
        int(_get(usage, "input_tokens", 0) or 0)
        + int(_get(usage, "cache_read_input_tokens", 0) or 0)
        + round(1.25 * int(_get(usage, "cache_creation_input_tokens", 0) or 0))
    )
    out.output_tokens = int(_get(usage, "output_tokens", 0) or 0)
    out.cost = live.price(MODEL, out.input_tokens, out.output_tokens, out.searches)
    return out


# -- a page --------------------------------------------------------------------------

_META_DATE = re.compile(
    r"<meta[^>]+(?:property|name|itemprop)\s*=\s*[\"'](?:article:published_time|"
    r"datePublished|date|pubdate|publish-date|og:published_time|dc\.date)[\"'][^>]*>",
    re.IGNORECASE,
)
_CONTENT = re.compile(r"content\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
_LD_DATE = re.compile(r"\"datePublished\"\s*:\s*\"([^\"]+)\"")
_AGE_FORMATS = ("%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%Y-%m-%d")


def _instant(said: str) -> int:
    """An ISO date or date-time, or a search's "April 30, 2025", as ms; 0 where it is
    neither, or lies in the future."""
    said = said.strip()
    if not said:
        return 0
    when: datetime | None = None
    try:
        when = datetime.fromisoformat(said.replace("Z", "+00:00"))
    except ValueError:
        for shape in _AGE_FORMATS:
            try:
                when = datetime.strptime(said, shape)
                break
            except ValueError:
                continue
    if when is None:
        return 0
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    ms = int(when.timestamp() * 1000)
    return ms if 0 < ms <= pool.now_ms() + pool.DAY_MS else 0


def published_of(html: str) -> int:
    """The day a page says it was published, as ms, from its meta tags or JSON-LD; 0
    where it says none."""
    for tag in _META_DATE.findall(html[:200_000]):
        found = _CONTENT.search(tag)
        if found and (ms := _instant(found.group(1))):
            return ms
    found_ld = _LD_DATE.search(html[:400_000])
    return _instant(found_ld.group(1)) if found_ld else 0


def page(url: str) -> tuple[str, int]:
    """A page's words and the day it says it was published, read direct: never through
    the proxy, so never a cost."""
    from ..ingest.url import article_paragraphs, fetch

    got = fetch(url, proxy=False)
    if not got.is_html:
        return got.text, 0
    words = "\n\n".join(text for _, _, text in article_paragraphs(got.text))
    return words, published_of(got.text)


# -- one night -----------------------------------------------------------------------


@dataclass
class Night(news.Round):
    """What one night did, beside what a news round says."""

    searches: int = 0
    queries: list[str] = field(default_factory=list)
    allowance: float = 0.0
    #: What the night has read from each host so far, this round's and what it was
    #: handed (`refresh(hosts=...)`), so the next language's round counts on from it.
    hosts: Counter[str] = field(default_factory=Counter)

    def __str__(self) -> str:
        return (
            f"{len(self.queries)} queries, {self.searches} searches, "
            + super().__str__()
            + f" (tonight's allowance ${self.allowance:.2f})"
        )


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def outlets(publishers: Sequence[Publisher]) -> dict[str, Publisher]:
    """The listed publishers by the site their homepage or feed is on."""
    from ..chat.sources import site

    out: dict[str, Publisher] = {}
    for one in publishers:
        for address in (one.homepage, one.feed):
            domain = site(address) if address else ""
            if domain and domain not in out:
                out[domain] = one
    return out


def refresh(
    store: Store,
    *,
    language: str = "he",
    ask: Callable[[str], Searched] | None = None,
    read: Callable[[str], tuple[str, int]] = page,
    robots: Robots = ROBOTS,
    forms_for: Callable[[str], score_module.Forms | None] = score_module.load,
    publishers: Sequence[Publisher] | None = None,
    clock: Callable[[], float] = time.monotonic,
    lean: Mapping[str, float] | None = None,
    hosts: Mapping[str, int] | None = None,
    at: int | None = None,
) -> Night:
    """One night: a search a topic while the night's allowance lasts, and every page it
    returns read, screened, scored and pooled. Each search's cost is written as it is
    spent and each find as it is kept, so a killed night has said what it cost and kept
    what it found. `hosts` is what the night already read from a host (the wikis' round,
    `wiki.Night.hosts`), counted against `HOST_MOST`. `lean` is each topic's weight
    tonight (`steer.weights`, where `TARGUM_CHIP_COUNTS` is on): the heaviest go first,
    inside the same allowance."""
    from ..chat import sources as sources_module
    from ..chat.sources import site
    from ..weekly.feeds import link_key

    when = pool.now_ms() if at is None else at
    found = Night(hosts=Counter(dict(hosts or {})))
    code = score_module.code(language)
    forms = forms_for(code) if code in score_module.POOLED else None
    asked = queries(code)
    if forms is None or not asked:
        found.stopped = "no map for the language" if forms is None else "no phrases for it"
        return found
    pool.expire(store, when)
    listed = outlets(sources_module.load() if publishers is None else publishers)
    asker = ask or (lambda one: search(live.client(), one))
    start = _start(store, code)
    base = rotated(asked, start)
    # The topics readers ask for and the pool lacks go first (`steer`); the night's dollar
    # is the same, so the lean moves which topics it buys, never how much.
    if lean is None:
        lean = steer.weights(store, code, known=_lexicon(), at=when) if steer.on() else {}
    order = steer.leaning(base, lean)
    steered = [pair for pair in order if lean.get(pair[0], 0.0) > 0][: steer.STEER_MOST]
    after = [at for at, pair in enumerate(base) if pair not in steered]
    run = pool.start_run(store, RUN_SOURCE, when)
    found.allowance = allowance(store, when)
    begun = clock()
    shut = set(store.closed(limit=500))
    per_host = found.hosts
    tonight = 0.0
    worst = WORST_CALL_USD
    done = 0

    def dropped(link: str, why: str) -> None:
        found.dropped[why] += 1
        pool.drop(store, language=code, source=SOURCE, url=link, reason=why, host=_host(link))

    try:
        for chip, query in order:
            if clock() - begun > DEADLINE_S:
                found.stopped = f"the night's {int(DEADLINE_S // 60)} minutes"
                break
            if tonight + worst > found.allowance:
                found.stopped = f"the night's ${found.allowance:.2f}"
                break
            if pool.left(store, when) < worst:
                found.stopped = "the month's discovery budget"
                break
            done += 1
            if bought_lately(store, query, when):
                continue
            try:
                searched = asker(query)
            except Exception as error:  # noqa: BLE001 - a refused search ends the night
                log.warning("finds: the web search failed: %s", error)
                found.stopped = f"the search failed ({type(error).__name__})"
                done -= 1
                break
            pool.spend(store, run, searched.cost)
            tonight += searched.cost
            found.spent += searched.cost
            found.searches += searched.searches
            found.queries.append(query)
            worst = max(worst, searched.cost * WORST_HEADROOM)
            tags = (chips.tag(chip),)
            reading = 0
            for hit in searched.hits:
                if reading >= PAGES_PER_QUERY:
                    break
                link = link_key(hit.url)
                host = _host(link)
                if pool.known(store, link):
                    # Pooled already, by the news round, a look or an earlier night: it is
                    # about this chip too, so the pool matches it from now on.
                    live._tag(store, link, tags)
                    continue
                found.seen += 1
                why = screen.passes(host, hit.title)
                if not why and host in shut:
                    why = "closed"
                if not why and per_host[host] >= HOST_MOST:
                    continue  # not dropped: another night may read it
                if why:
                    dropped(link, why)
                    continue
                reading += 1
                per_host[host] += 1
                if not robots.allowed(link):
                    dropped(link, "robots")
                    continue
                try:
                    text, published = read(link)
                except Exception as error:  # noqa: BLE001 - one page never stops a night
                    log.info("finds: web %s not read: %s", host, error)
                    dropped(link, "unreadable")
                    continue
                found.fetched += 1
                outlet = listed.get(site(link))
                _keep(
                    store,
                    code,
                    link,
                    hit,
                    text,
                    published or _instant(hit.age),
                    outlet,
                    tags,
                    forms,
                    found,
                    dropped,
                    when,
                )
    finally:
        note: dict[str, Any] = {
            "next": _next(start, done, len(steered), after, len(asked)),
            "queries": found.queries,
            "searches": found.searches,
            "allowance": round(found.allowance, 4),
            "language": code,
        }
        if steered:
            note["steered"] = [chip for chip, _ in steered]
        if found.stopped:
            note["stopped"] = found.stopped
        pool.finish_run(
            store,
            run,
            seen=found.seen,
            kept=found.kept,
            dropped=found.dropped,
            note=note,
        )
    return found


def _next(start: int, done: int, steered: int, after: Sequence[int], every: int) -> int:
    """Where tomorrow's rotation starts: past the last topic tonight took in its turn.
    The topics the lean put first are not the rotation's, so they do not move it."""
    taken = max(0, done - steered)
    if not taken or not after:
        return start % max(1, every)
    return (start + after[min(taken, len(after)) - 1] + 1) % max(1, every)


def _lexicon() -> Any:
    from .interests import lexicon

    return lexicon()


def _keep(
    store: Store,
    language: str,
    link: str,
    hit: Hit,
    text: str,
    published: int,
    outlet: Publisher | None,
    tags: tuple[str, ...],
    forms: score_module.Forms,
    found: Night,
    dropped: Callable[[str, str], None],
    when: int,
) -> None:
    """The hourly round's rules for one page, kept as a `web` find."""
    if screen.term_in(f"{hit.title}\n{text}"):
        dropped(link, "words")
        return
    scored = forms.score(f"{hit.title}\n{text}")
    if scored.tokens < news.LEAST_WORDS:
        dropped(link, "short")
        return
    fingerprint = news.digest(text)
    if pool.known_digest(store, fingerprint):
        dropped(link, "same")
        return
    host = _host(link)
    licence = outlet.licence if outlet else ""
    added = pool.add(
        store,
        language=language,
        source=SOURCE,
        url=link,
        bag=scored.bag,
        tokens=scored.tokens,
        unresolved=scored.unresolved,
        rung=forms.rung_of(scored),
        digest=fingerprint,
        title=hit.title,
        host=host,
        publisher=(outlet.publisher or outlet.name) if outlet else host.removeprefix("www."),
        published=published,
        topics=tags,
        licence=licence,
        licence_url=(outlet.licence_url or outlet.homepage) if outlet and licence else "",
        licence_from="publisher" if licence else "",
        at=when,
    )
    if added:
        found.kept += 1
