"""Hebrew Wikipedia and Wikivoyage, each night, through the MediaWiki API (targum-internal#622;
David, 2026-11-05; design.md §12, "Hebrew Wikipedia and Wikivoyage come back through their
own API").

The open-web night (`web`) asks a paid search for pages on the forty topics. This round
asks the two wikis themselves, for nothing: each chip's fixed Hebrew phrase (`chips.CHIPS`)
goes to `list=search`, and each page it names is read as plain text through
`prop=extracts`, screened, scored and pooled as a `web` find by the night's own rules
(`web._keep`'s, and `pool.KEEP_DAYS["web"]`'s sixty days). The text is let go.

- **Polite.** Every request carries `USER_AGENT`, which names targum and its contact
  address as Wikimedia's User-Agent policy asks, and waits `PAUSE_S` after the last one.
  A page is read only where robots.txt allows its `/wiki/` address. The words come from
  the API, which is the door Wikimedia keeps for programs, so robots.txt's `/w/` line,
  written for crawlers of the HTML, is not what the API call is held to.
- **Capped.** At most `web.HOST_MOST` pages from each wiki a night, counted together with
  whatever the night's search reads there (`refresh(hosts=...)`), and at most
  `SEARCHES_MOST` searches on a wiki a night.
- **Credited.** Every row carries `LICENCE`, its deed, the page's own address and
  "Wikipedia contributors" or "Wikivoyage contributors" as the outlet, which is who
  CC BY-SA asks to be credited. A copy that joins the library says targum changed it
  (`licensing.changes_owed`).

**Off unless the box says so** (`TARGUM_FINDS_WIKI`). It costs nothing, so it writes a
run with no spend and never touches `TARGUM_FINDS_BUDGET_USD`.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from . import chips, live, news, pool, screen, web
from . import score as score_module
from .robots import ROBOTS, Robots

if TYPE_CHECKING:
    from ..accounts import Store

log = logging.getLogger(__name__)

FLAG = "TARGUM_FINDS_WIKI"

#: The run's own name on `find_run`.
RUN_SOURCE = "wiki"

#: Wikimedia asks a program to name itself and say how to reach whoever runs it
#: (meta.wikimedia.org/wiki/User-Agent_policy). targum's own address, as `voices` uses.
USER_AGENT = "targum/0.1 (+https://targum.page; hello@targum.page) finds-wiki"

#: Seconds between two requests to one wiki: the door's own `POLITE_S`.
PAUSE_S = 1.5

#: The licence both wikis state for their text, its deed, and which statement it is.
LICENCE = "CC BY-SA 4.0"
LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
LICENCE_FROM = "publisher"

#: Search results asked for at once, and the most searches on one wiki in a night.
RESULTS = 10
SEARCHES_MOST = 40


@dataclass(frozen=True)
class Wiki:
    host: str
    #: Who CC BY-SA asks to be credited, said as the find's outlet.
    credit: str
    #: The chips searched on it; empty for all forty.
    chips: tuple[str, ...] = ()

    @property
    def api(self) -> str:
        return f"https://{self.host}/w/api.php"


#: A travel guide answers few of the forty: those it does are searched there.
WIKIS: tuple[Wiki, ...] = (
    Wiki("he.wikipedia.org", "Wikipedia contributors"),
    Wiki(
        "he.wikivoyage.org",
        "Wikivoyage contributors",
        ("travel", "food", "nature", "history", "israel", "holidays"),
    ),
)


def on() -> bool:
    return os.environ.get(FLAG, "").strip().lower() in {"1", "true", "yes"}


# -- the API -------------------------------------------------------------------------

#: A GET to a wiki's API: (url) -> parsed JSON. Swapped for a fake in the tests.
Get = Callable[[str], Any]

_last: dict[str, float] = {}


def _get(url: str) -> Any:
    host = urllib.parse.urlparse(url).hostname or ""
    wait = PAUSE_S - (time.monotonic() - _last.get(host, -PAUSE_S))
    if wait > 0:
        time.sleep(wait)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - https only
            body: bytes = response.read(4_000_000)
    finally:
        _last[host] = time.monotonic()
    return json.loads(body.decode("utf-8"))


def _call(wiki: Wiki, get: Get, **params: str) -> dict[str, Any]:
    asked = {"action": "query", "format": "json", "formatversion": "2", **params}
    said = get(wiki.api + "?" + urllib.parse.urlencode(asked))
    return said if isinstance(said, dict) else {}


@dataclass(frozen=True)
class Page:
    title: str
    url: str


def search(wiki: Wiki, asked: str, get: Get) -> list[Page]:
    """The articles a phrase finds on one wiki, best first, with their addresses;
    disambiguation pages left out."""
    said = _call(
        wiki,
        get,
        generator="search",
        gsrsearch=asked,
        gsrnamespace="0",
        gsrlimit=str(RESULTS),
        prop="info|pageprops",
        inprop="url",
        ppprop="disambiguation",
    )
    rows = (said.get("query") or {}).get("pages") or []
    found: list[tuple[int, Page]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or row.get("missing") or row.get("ns", 0) != 0:
            continue
        if "disambiguation" in (row.get("pageprops") or {}):
            continue
        url = str(row.get("canonicalurl") or row.get("fullurl") or "")
        title = str(row.get("title") or "")
        if not url.startswith(f"https://{wiki.host}/wiki/") or not title:
            continue
        found.append((int(row.get("index") or 0), Page(title, url)))
    return [one for _, one in sorted(found, key=lambda pair: pair[0])]


def words(wiki: Wiki, title: str, get: Get) -> str:
    """One article's text, plain, through the API; "" where it has none."""
    said = _call(
        wiki,
        get,
        prop="extracts",
        explaintext="1",
        exsectionformat="plain",
        redirects="1",
        titles=title,
    )
    rows = (said.get("query") or {}).get("pages") or []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and not row.get("missing"):
            return str(row.get("extract") or "")
    return ""


# -- one night -----------------------------------------------------------------------


@dataclass
class Night(news.Round):
    """What one night on the wikis did, beside what a news round says."""

    searches: int = 0
    queries: list[str] = field(default_factory=list)
    #: Pages read from each wiki tonight, for the open-web night to count on.
    hosts: Counter[str] = field(default_factory=Counter)

    def __str__(self) -> str:
        return f"{self.searches} searches on the wikis, " + super().__str__()


def asked_on(wiki: Wiki, language: str) -> list[tuple[str, str]]:
    """(chip code, phrase) searched on a wiki, in the chips' order."""
    every = web.queries(language)
    return [pair for pair in every if not wiki.chips or pair[0] in wiki.chips]


def _starts(store: Store) -> dict[str, int]:
    """Where tonight starts on each wiki: where the last night stopped."""
    row = store.db.execute(
        "SELECT note FROM find_run WHERE source = ? AND finished > 0 ORDER BY id DESC LIMIT 1",
        (RUN_SOURCE,),
    ).fetchone()
    try:
        said = json.loads(row[0] or "{}") if row else {}
    except ValueError:
        said = {}
    nexts = said.get("next") if isinstance(said, dict) else None
    if not isinstance(nexts, dict):
        return {}
    return {str(host): int(at or 0) for host, at in nexts.items()}


def refresh(
    store: Store,
    *,
    language: str = "he",
    get: Get = _get,
    robots: Robots = ROBOTS,
    forms_for: Callable[[str], score_module.Forms | None] = score_module.load,
    wikis: Sequence[Wiki] = WIKIS,
    at: int | None = None,
) -> Night:
    """One night on the wikis: each chip's phrase searched on each wiki, starting where
    the last night stopped, until the wiki has given `web.HOST_MOST` pages; every page
    read, screened, scored and pooled. Each find is written as it is kept."""
    when = pool.now_ms() if at is None else at
    found = Night()
    code = score_module.code(language)
    forms = forms_for(code) if code in score_module.POOLED else None
    if forms is None or not web.queries(code):
        found.stopped = "no map for the language" if forms is None else "no phrases for it"
        return found
    pool.expire(store, when)
    run = pool.start_run(store, RUN_SOURCE, when)
    starts = _starts(store)
    nexts: dict[str, int] = {}
    shut = set(store.closed(limit=500))

    def dropped(link: str, why: str) -> None:
        found.dropped[why] += 1
        pool.drop(
            store, language=code, source=web.SOURCE, url=link, reason=why, host=web._host(link)
        )

    try:
        for wiki in wikis:
            asked = asked_on(wiki, code)
            start = starts.get(wiki.host, 0)
            done = 0
            if wiki.host in shut or screen.host_denied(wiki.host):
                nexts[wiki.host] = start % max(1, len(asked))
                continue
            for chip, query in web.rotated(asked, start)[:SEARCHES_MOST]:
                if found.hosts[wiki.host] >= web.HOST_MOST:
                    break
                try:
                    pages = search(wiki, query, get)
                except Exception as error:  # noqa: BLE001 - a wiki that fails ends its night
                    log.warning("finds: %s search failed: %s", wiki.host, error)
                    found.stopped = f"{wiki.host} search failed ({type(error).__name__})"
                    break
                done += 1
                found.searches += 1
                found.queries.append(query)
                tags = (chips.tag(chip),)
                for one in pages:
                    if found.hosts[wiki.host] >= web.HOST_MOST:
                        break
                    if _page(
                        store, wiki, one, code, tags, forms, robots, get, found, dropped, when
                    ):
                        # One page a phrase, so the night spreads over the topics.
                        break
            nexts[wiki.host] = (start + done) % max(1, len(asked))
    finally:
        pool.finish_run(
            store,
            run,
            seen=found.seen,
            kept=found.kept,
            dropped=found.dropped,
            note={
                "next": nexts,
                "queries": found.queries,
                "searches": found.searches,
                **({"stopped": found.stopped} if found.stopped else {}),
            },
        )
    return found


def _page(
    store: Store,
    wiki: Wiki,
    one: Page,
    language: str,
    tags: tuple[str, ...],
    forms: score_module.Forms,
    robots: Robots,
    get: Get,
    found: Night,
    dropped: Callable[[str, str], None],
    when: int,
) -> bool:
    """One page the search named: whether it was read (and so counts on the wiki's cap)."""
    from ..weekly.feeds import link_key

    link = link_key(one.url)
    if pool.known(store, link):
        live._tag(store, link, tags)
        return False
    found.seen += 1
    why = screen.passes(wiki.host, one.title)
    if why:
        dropped(link, why)
        return False
    if not robots.allowed(link):
        dropped(link, "robots")
        return False
    found.hosts[wiki.host] += 1
    try:
        text = words(wiki, one.title, get)
    except Exception as error:  # noqa: BLE001 - one page never stops a night
        log.info("finds: %s page not read: %s", wiki.host, error)
        dropped(link, "unreadable")
        return True
    found.fetched += 1
    keep(store, language, link, one.title, text, wiki, tags, forms, found, dropped, when)
    return True


def keep(
    store: Store,
    language: str,
    link: str,
    title: str,
    text: str,
    wiki: Wiki,
    tags: tuple[str, ...],
    forms: score_module.Forms,
    found: news.Round,
    dropped: Callable[[str, str], None],
    when: int,
) -> None:
    """The night's rules for one article, kept as a `web` find under the wiki's licence."""
    if screen.term_in(f"{title}\n{text}"):
        dropped(link, "words")
        return
    scored = forms.score(f"{title}\n{text}")
    if scored.tokens < news.LEAST_WORDS:
        dropped(link, "short")
        return
    fingerprint = news.digest(text)
    if pool.known_digest(store, fingerprint):
        dropped(link, "same")
        return
    added = pool.add(
        store,
        language=language,
        source=web.SOURCE,
        url=link,
        bag=scored.bag,
        tokens=scored.tokens,
        unresolved=scored.unresolved,
        rung=forms.rung_of(scored),
        digest=fingerprint,
        title=title,
        host=wiki.host,
        publisher=wiki.credit,
        # A wiki page states no day it was published: none is shown rather than a guess.
        published=0,
        topics=tags,
        licence=LICENCE,
        licence_url=LICENCE_URL,
        licence_from=LICENCE_FROM,
        at=when,
    )
    if added:
        found.kept += 1
