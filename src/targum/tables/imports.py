"""What learners bring, pooled (David, 2026-11-01; design.md §12, "What learners bring is
counted in the tables, never kept"): every reader's own material counted into the
language tables, sorted by its source into a register, as counts and nothing else.

A reader's home (`p<id>`) holds what they brought: links pasted, files uploaded, pages
photographed and read, a channel subscribed to. Each night this reads those homes'
`annotation.json` files, the same files a fold reads, and writes one contribution per
table and register, `words`, `phrases` and `roots`, each register filed apart from the
public counts of the same name (`registers.pooled`). The rules:

- **Sorted by its source** (`sort`), from what is already written beside the text: the
  source's address and the ingester that read it. A link to a news publisher is news; an
  Instagram, TikTok, Facebook or X post is social; YouTube and the other video hosts are
  video; a podcast episode or feed is podcasts; a photo or an uploaded document is
  everyday. Anything else, or anything in doubt, is `imports`, "What learners bring".
  Nothing new is stored to sort it.

- **Ten readers a key, in each register.** A row (a key in a variant) is written only
  once the material of at least `FLOOR` distinct readers holds it in that register.
  Below that it was only ever in memory.
- **A reader can say no.** A reader who has turned counting off on the account page
  (`accounts.Store.counts_material`) is never read, nor an operator, an admin or a test
  account, nor a home with no account behind it. The pool is made again from nothing
  every night, so a reader who turns it off, or leaves, is out of it by the next morning.
- **Nothing leads back.** A contribution's unit is the pool itself, `imports:pool`,
  never a document: the corpus ledger already holds a private text's home and its tokens
  (`ledger.text_homes`, the mirrored `tokens`), so a count filed by document, or by any
  hash of one, or a per-text bag of lemmas, could be matched to its reader. Who brought
  what is worked out in memory, one reader at a time, and only the floor's verdict
  leaves: no reader id, no count of readers, no document hash and no text is written,
  and the night before's pool is deleted, not superseded (`Store.replace_pool`).
- **Their text never.** A tally holds lemmas, runs of lemmas, roots, parts of speech and
  counts, as every table does.
- **Not what a model wrote.** A rewrite, a chat's speech, a scene and the weekly sit in a
  home too, and none of them is something a reader brought.

A text two readers brought is counted once, and both stand behind its keys. The whole
pool is off unless `TARGUM_IMPORT_COUNTS=1`: turning it on and publishing the privacy
notice's sentence about it are one decision (`on`), and with it off the pool is deleted.
No lemma below the floor is ever handed to anything, a model included, because none is
ever written down or returned.
"""

from __future__ import annotations

import json
import logging
import os
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import ledger as ledger_module
from . import roots
from .registers import EVERYDAY, IMPORTS, NEWS, PODCASTS, SOCIAL, SORTED, VIDEO, pooled
from .store import Contribution, Store
from .words import LANGUAGES, PHRASES, RULE, WORDS, count

log = logging.getLogger(__name__)

#: The switch, in the deployment's environment.
ENV = "TARGUM_IMPORT_COUNTS"

#: How many distinct readers' material must hold a key before it is written: the
#: privacy notice's "at least ten Data Subjects".
FLOOR = 10

#: The pooling rule's version, the pool's `tool`: a change to who is read or how a row
#: passes is a new number.
POOL_RULE = f"imports/1+floor{FLOOR}"

#: The pool's one unit: never a document.
UNIT = "imports:pool"
SOURCE = "readers' material"
LICENCE = "the readers' own material: counts only, no text, no reader, ten readers a row"

#: Every table the pool writes: the tables a fold writes, so what readers bring is
#: counted exactly as the shelf is.
TABLES = (WORDS, PHRASES, roots.ROOTS)

#: Sources a model wrote, which may sit in a home but no reader brought.
MODEL_WRITTEN = ("dialogue:", "weekly:", "chat:")


def on() -> bool:
    """Whether what readers bring is counted on this deployment.

    Off unless the deployment says so, as `TARGUM_EVENTS` was: the privacy notice names a
    legal basis for every category of processing, and publishing the sentence that
    covers this and switching it on are one decision, not a merge.
    """
    return os.environ.get(ENV, "").strip().lower() in {"1", "true", "yes"}


@dataclass
class PoolResult:
    """What one night's pool did. Counts of homes and texts only: never which."""

    #: Homes read: readers counted tonight.
    readers: int = 0
    #: Homes passed over: counting turned off, an operator, an admin, a test account, or
    #: no account at all.
    left_out: int = 0
    texts: int = 0
    #: Texts in a home that a model wrote (a rewrite, a chat's speech, a scene).
    model_written: int = 0
    unreadable: int = 0
    #: Texts read, by the register they were sorted into.
    by_register: dict[str, int] = field(default_factory=dict)
    #: Rows written, by table.
    rows: dict[str, int] = field(default_factory=dict)
    #: Rows held in memory and dropped for being under the floor, by table.
    under_floor: dict[str, int] = field(default_factory=dict)


def _contribution(table: str, register: str = IMPORTS) -> Contribution:
    rule = roots.rule() if table == roots.ROOTS else RULE
    return Contribution(
        table=table,
        register=pooled(register),
        # One unit a register, since one (table, unit) is current at a time; still the
        # pool's, never a document's.
        unit=UNIT if register == IMPORTS else f"{UNIT}:{register}",
        source=SOURCE,
        licence=LICENCE,
        tool=POOL_RULE,
        rule=rule,
    )


#: Hosts whose pages are podcasts, where a reader pastes the show's page rather than the
#: episode's audio.
PODCAST_HOSTS = frozenset(
    {
        "podcasts.apple.com",
        "open.spotify.com",
        "spotify.com",
        "anchor.fm",
        "podbean.com",
        "buzzsprout.com",
        "simplecast.com",
        "soundcloud.com",
        "omny.fm",
        "transistor.fm",
        "castbox.fm",
        "pca.st",
    }
)

#: The video hosts that are social media rather than online video (`video.hosts`).
SOCIAL_VIDEO = frozenset({"Instagram", "TikTok", "Facebook"})

#: Ingesters that read a photo or an uploaded document: everyday, where the source is a
#: file the reader brought rather than an address.
EVERYDAY_INGESTERS = ("picture/", "pages/", "pdf/", "docx/", "text/", "markdown/")

#: Audio files, the address a podcast episode is read from once its feed is followed.
_AUDIO = (".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav")


def site(address: str) -> str:
    """The domain an address is on, as the publisher list names it."""
    from ..chat.sources import site as site_of

    return site_of(address)


def news_hosts(accounts: Any = None) -> frozenset[str]:
    """The news publishers' domains: every `news` publisher in `sources.json`, and every
    host the finds pool has pooled an article from, where the account database is given.
    Read each night; nothing is kept."""
    from ..chat import sources

    found = {
        site(address)
        for publisher in sources.load()
        if publisher.kind == "news"
        for address in (publisher.homepage, publisher.feed)
    }
    if accounts is not None:
        try:
            rows = accounts.db.execute(
                "SELECT DISTINCT host FROM find WHERE medium = 'text' AND host != ''"
            ).fetchall()
        except Exception:  # noqa: BLE001 - a database without the finds pool has none
            rows = []
        found.update(site(f"https://{row[0]}/") for row in rows)
    return frozenset(one for one in found if one)


def _host(address: str) -> str:
    from urllib.parse import urlparse

    host = (urlparse(address).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def sort(source: str, ingester: str, news: Collection[str] = ()) -> str:
    """The register one brought text is counted under, from its source and its ingester
    alone: one of `registers.SORTED`, or `IMPORTS` where neither says plainly."""
    from ..ingest import x as x_module
    from ..video import hosts as video_hosts

    address = source.strip()
    web = address.lower().startswith(("http://", "https://"))
    if web:
        domain = site(address)
        if domain and domain in news:
            return NEWS
        if x_module.home_url(address):
            return SOCIAL
        host = video_hosts.host_for(address)
        if host is not None:
            return SOCIAL if host.name in SOCIAL_VIDEO else VIDEO
        if domain in PODCAST_HOSTS or _host(address) in PODCAST_HOSTS:
            return PODCASTS
        if ingester.startswith("audio/") or address.lower().split("?")[0].endswith(_AUDIO):
            return PODCASTS
        return IMPORTS
    if address and ingester.startswith(EVERYDAY_INGESTERS):
        return EVERYDAY
    return IMPORTS


def homes(library: Path) -> dict[int, list[Path]]:
    """Each reader's home under `library` with its built texts, by person id. `local`,
    the laptop's home, belongs to no account and is never read."""
    found: dict[int, list[Path]] = {}
    for folder in ledger_module.text_folders(library):
        home = ledger_module.home_of(folder, library)
        if home is None or not home.startswith("p"):
            continue
        try:
            person = int(home[1:])
        except ValueError:
            continue
        found.setdefault(person, []).append(folder)
    return found


def _document(folder: Path) -> dict[str, Any]:
    try:
        document = json.loads((folder / "document.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return document if isinstance(document, dict) else {}


def _model_written(folder: Path, document: Mapping[str, Any]) -> bool:
    from ..rewrite import made_from

    if made_from(folder) is not None:
        return True
    return str(document.get("source") or "").startswith(MODEL_WRITTEN)


def _tallies(
    annotation: Mapping[str, Any], languages: Sequence[str]
) -> dict[str, Counter[tuple[str, str]]] | None:
    language = str(annotation.get("language") or "")
    if not any(language == one or language.startswith(f"{one}-") for one in languages):
        return None
    tokens = annotation.get("tokens")
    if not isinstance(tokens, Mapping):
        raise ValueError("the annotation has no tokens")
    return {**count(tokens), roots.ROOTS: roots.count(tokens, language)}


def pool(
    library: Path,
    store: Store,
    counted: Collection[int],
    *,
    news: Collection[str] = (),
    floor: int = FLOOR,
    languages: Sequence[str] = LANGUAGES,
) -> PoolResult:
    """Make tonight's imports pool from the homes under `library` and put it in place of
    last night's. `counted` is the person ids whose material may be counted
    (`accounts.Store.counted_readers`); every other home is passed over unread. `news`
    is the news publishers' domains (`news_hosts`), which a link must be on to be news.

    Reads files and writes the tables; runs no annotator and spends nothing.
    """
    result = PoolResult()
    registers = (*SORTED, IMPORTS)
    cells = [(register, table) for register in registers for table in TABLES]
    #: (register, table) -> key -> how many readers' material holds it. In memory only.
    readers: dict[tuple[str, str], Counter[tuple[str, str]]] = {cell: Counter() for cell in cells}
    totals: dict[tuple[str, str], Counter[tuple[str, str]]] = {cell: Counter() for cell in cells}
    seen: set[str] = set()
    for person, folders in sorted(homes(library).items()):
        if person not in counted:
            result.left_out += 1
            continue
        result.readers += 1
        mine: dict[tuple[str, str], set[tuple[str, str]]] = {cell: set() for cell in cells}
        for folder in folders:
            file = folder / "annotation.json"
            if not file.is_file() or ledger_module._escapes(file, library):
                continue
            document = _document(folder)
            try:
                if _model_written(folder, document):
                    result.model_written += 1
                    continue
                annotation = json.loads(file.read_text(encoding="utf-8"))
                if not isinstance(annotation, dict):
                    raise ValueError("not an annotation")
                tallies = _tallies(annotation, languages)
            except (OSError, ValueError, TypeError, AttributeError) as error:
                log.warning("tables: a reader's text was not pooled: %s", type(error).__name__)
                result.unreadable += 1
                continue
            if tallies is None:
                continue
            register = sort(
                str(document.get("source") or ""), str(document.get("ingester") or ""), news
            )
            result.texts += 1
            result.by_register[register] = result.by_register.get(register, 0) + 1
            hashed = str(annotation.get("document_hash") or "")
            first = not hashed or hashed not in seen
            if hashed:
                seen.add(hashed)
            for table in TABLES:
                mine[(register, table)].update(tallies[table])
                if first:
                    totals[(register, table)].update(tallies[table])
        for cell in cells:
            readers[cell].update(mine[cell])
    made: list[Contribution] = []
    passed: dict[str, dict[tuple[str, str], int]] = {}
    for register, table in cells:
        cell = (register, table)
        kept = {key: n for key, n in totals[cell].items() if n > 0 and readers[cell][key] >= floor}
        one = _contribution(table, register)
        made.append(one)
        passed[one.id] = kept
        result.rows[table] = result.rows.get(table, 0) + len(kept)
        result.under_floor[table] = result.under_floor.get(table, 0) + len(totals[cell]) - len(kept)
    store.replace_pool(made, passed)
    return result
