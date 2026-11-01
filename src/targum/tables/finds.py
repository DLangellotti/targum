"""Public finds counted into the language tables (David, 2026-11-01; design.md §12,
"Public finds count into the yardsticks, as counts").

The discovery pool (`finds.pool`) keeps, for every page and video targum found on the
open web, a bag of lemma counts and never the words. Each night `targum tables sweep
--store` folds those bags into the `words` table as public contributions, filed under the
register the find belongs to:

- a YouTube video find (`youtube`) is `video`, and a podcast find `podcasts`;
- a news find (`news`, read off the feeds the service follows) is `news`;
- a web find (`web`, from a live search) is sorted by its host exactly as what readers
  bring is (`tables.imports.sort`): news, social, video or podcasts, and where its host
  says none of these it is not counted at all.

The rules:

- **A find is public web material targum found itself**, not a reader's. The guard is
  `public_text`'s, by the same means: `fold_finds` takes only a `PublicFind`, and only
  `public_finds` makes one, from the pool's kept rows and nothing else. It never reads a
  reader's home, so what a reader built from a find (Watch or Read builds it as their own
  import) reaches the tables only through the imports pool's floor of ten readers, as
  anything else they bring does.
- **Counts only.** The pool holds no text to count, so none is stored here either: a
  contribution's unit is `finds:` and a hash of the find's address, its source names the
  kind (`finds:youtube`, `finds:news`, `finds:web`) and its licence says
  `LICENCE`. A bag holds lemmas, not their order, so only `words` is written: no phrase
  and no root is counted from a find.
- **A part of speech is borrowed.** The scorer files a page's words by lemma alone, so
  each lemma takes the variant the tables already count it under most often (DICTA's,
  from the shelf), so the closed classes stay out of a weighting as they do for a text.
  A lemma the tables have never seen has none.
- **Counted once.** A find's unit carries the same hash as the nightly news count's unit
  for the same address (`tables.news.unit_of`), so an item the feeds count is never
  counted again as a find, and a find counted before the feeds reached its item is
  retired the night they do. The feed's count is the better one: DICTA read it, phrases
  and roots too.
- **The counts outlive the find.** A find expires from the pool after a week, thirty days
  or two months; its contribution stays, as a news item's stays after it leaves its feed
  and a corpus's after it is put away. A list measures the language as it was written.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .registers import IMPORTS, NEWS, PODCASTS, VIDEO
from .store import Contribution, Store
from .words import LANGUAGES, WORDS

if TYPE_CHECKING:
    from ..accounts import Store as AccountStore

#: Every unit here starts with this; the rest is the news count's hash of the address.
PREFIX = "finds:"

#: The version of the folding rule below.
RULE = "finds/1"

#: The tool a bag was counted with: the cheap scorer's map (`finds.score.VERSION`). Named
#: here rather than imported, so the sweep, which refuses to load a model, never imports
#: the scorer's modules to name it.
TOOL = "forms/1"

#: The licence line on every row (David, 2026-11-01).
LICENCE = "counts only; text never stored"

#: The register a find's kind files it under, where the kind alone says. A `web` find is
#: sorted by its host instead (`register_for`).
KINDS = {"youtube": VIDEO, "podcast": PODCASTS, "news": NEWS}

#: Only `public_finds` holds this, so only it can make a `PublicFind` `fold_finds` takes.
_SEAL = object()


@dataclass(frozen=True)
class PublicFind:
    """One kept find of the discovery pool, as the tables may count it."""

    unit: str
    #: The pool's source: `youtube`, `news`, `web` or `podcast`.
    kind: str
    register: str
    bag: Mapping[str, int] = field(repr=False)
    _seal: object = field(default=None, repr=False, compare=False)

    @property
    def sealed(self) -> bool:
        return self._seal is _SEAL

    @property
    def feed_unit(self) -> str:
        """The unit the nightly news count gives the same address."""
        from .news import PREFIX as FEED

        return FEED + self.unit[len(PREFIX) :]


def unit_of(url: str) -> str:
    """A find's unit: the news count's hash of its address, under `PREFIX`. "" where the
    address is empty."""
    from .news import PREFIX as FEED
    from .news import unit_of as feed_unit_of

    held = feed_unit_of(url)
    return PREFIX + held[len(FEED) :] if held else ""


def register_for(kind: str, url: str, news: Collection[str] = ()) -> str | None:
    """The register one find counts into, or None where it counts into none."""
    if kind in KINDS:
        return KINDS[kind]
    if kind != "web":
        return None
    from .imports import sort

    register = sort(url, "", news)
    return None if register == IMPORTS else register


def public_finds(
    accounts: AccountStore,
    *,
    news: Collection[str] = (),
    languages: Sequence[str] = LANGUAGES,
) -> list[PublicFind]:
    """Every kept find in the pool the tables may count, with its bag: a find in a
    language the tables fold, of a kind with a register, and holding counts. A dropped
    row holds only its address and is never one. `news` is the news publishers' domains
    (`imports.news_hosts`), which a web find's host must be on to be news."""
    try:
        rows = accounts.db.execute(
            "SELECT id, language, source, url FROM find WHERE screen = 'kept' ORDER BY id"
        ).fetchall()
    except Exception:  # noqa: BLE001 - a database from before the pool has no finds
        return []
    wanted: dict[int, tuple[str, str, str]] = {}
    for find_id, language, kind, url in rows:
        language = str(language or "")
        if not any(language == one or language.startswith(f"{one}-") for one in languages):
            continue
        register = register_for(str(kind), str(url), news)
        unit = unit_of(str(url))
        if register is None or not unit:
            continue
        wanted[int(find_id)] = (str(kind), register, unit)
    bags: dict[int, dict[str, int]] = {find_id: {} for find_id in wanted}
    ids = list(wanted)
    for start in range(0, len(ids), 500):
        chunk = ids[start : start + 500]
        marks = ",".join("?" * len(chunk))
        for find_id, lemma, n in accounts.db.execute(
            f"SELECT find, lemma, n FROM find_lemma WHERE find IN ({marks})",  # noqa: S608 - marks only
            chunk,
        ):
            if int(n) > 0:
                bags[int(find_id)][str(lemma)] = int(n)
    out: list[PublicFind] = []
    seen: set[str] = set()
    for find_id, (kind, register, unit) in wanted.items():
        if not bags[find_id] or unit in seen:
            continue
        seen.add(unit)
        out.append(
            PublicFind(unit=unit, kind=kind, register=register, bag=bags[find_id], _seal=_SEAL)
        )
    return out


@dataclass
class FindsResult:
    """What one night's fold did. Counts only: never which find."""

    counted: int = 0
    #: Already counted on an earlier night.
    held: int = 0
    #: Left out because the nightly news count holds the same address.
    in_feeds: int = 0
    #: Counted on an earlier night and retired tonight, because the feeds now hold it.
    retired: int = 0
    by_register: dict[str, int] = field(default_factory=dict)


def contribution_for(find: PublicFind) -> Contribution:
    """What one find is filed as."""
    return Contribution(
        table=WORDS,
        register=find.register,
        unit=find.unit,
        source=PREFIX + find.kind,
        licence=LICENCE,
        tool=TOOL,
        rule=RULE,
    )


def _variant(variants: Mapping[str, int]) -> str:
    if not variants:
        return ""
    return min(variants.items(), key=lambda item: (-item[1], item[0]))[0]


def fold_finds(store: Store, finds: Iterable[PublicFind]) -> FindsResult:
    """Count the finds not counted yet into `words`, and retire any counted before whose
    address the news count now holds. Reads rows and writes rows; runs no model."""
    held = list(finds)
    for find in held:
        if not isinstance(find, PublicFind) or not find.sealed:
            raise TypeError("fold_finds takes finds from tables.finds.public_finds alone")
    from .news import PREFIX as FEED

    result = FindsResult()
    mine = store.current_prefixed(WORDS, PREFIX)
    fed = store.current_units(WORDS, [FEED + unit[len(PREFIX) :] for unit in mine])
    shadowed = [unit for unit in mine if FEED + unit[len(PREFIX) :] in fed]
    result.retired = store.retire(WORDS, shadowed)
    in_feeds = store.current_units(WORDS, [find.feed_unit for find in held])
    fresh: list[PublicFind] = []
    for find in held:
        if find.feed_unit in in_feeds:
            result.in_feeds += 1
        elif find.unit in mine:
            result.held += 1
        else:
            fresh.append(find)
    if not fresh:
        return result
    known = store.variants(WORDS, {lemma for find in fresh for lemma in find.bag})
    for find in fresh:
        counts = {(lemma, _variant(known.get(lemma, {}))): n for lemma, n in find.bag.items()}
        if store.write(contribution_for(find), counts):
            result.counted += 1
            result.by_register[find.register] = result.by_register.get(find.register, 0) + 1
        else:
            result.held += 1
    return result
