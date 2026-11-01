"""What a text would teach one reader: new words that come back (design.md §12, "What to
read next teaches words that come back", 2026-11-01; targum-internal#614, Phase 2 of the
comprehensible-input epic #617).

ling-he's research (2026-10-31, recommendation 3): words are learned from reading only
when they come back. One graded reader leaves about one new word in 25 after three
months, and none met fewer than eight times. So among the texts a reader can read, the
better one is the one whose new words return: inside it, in everyday Hebrew, and in what
they will read next.

**The score** is the expected number of such words per hundred running words, for one
reader and one text. Every word in the text that is not marked known or ignored adds

    P(not known) · useful · repeat · (1 + recur)

- **P(not known)** is 1 for a word on the list at steps 1–3, and 1 − the estimate's chance
  for a word with no mark (`estimate.py`). A word marked known adds nothing.
- **repeat** is 0 for a word met once in the text, ½ for twice and 1 from three times: a
  word that comes round inside the text gets a second meeting at once.
- **useful** is how common the word is in everyday Hebrew, 0 to 1: its share of the
  conversation and news yardsticks (`tables.yardstick`), log-damped, so the 100th word is
  near 1 and the 10,000th about a third. A word on neither list is not common enough to
  be worth the reader's effort and adds nothing. Where no yardstick is on the machine its
  place in the frequency list stands in.
- **recur** is whether the word will come back in what the reader reads next: 1 where it
  is in the next texts of the text's collection, or where the reader has met it already in
  a section they finished (it keeps coming back, and this is one more meeting); ½ where it
  belongs to one of the text's own topics or the reader's (`topics.py`), whose words come
  round together; otherwise 0.

The sum is divided by the text's running words and multiplied by a hundred, so a long book
is not preferred for being long.

**Narrow reading** (the research's §5.2, "continuing items"): a text that is the next
unread one in a collection the reader has started is worth `CONTINUING` times as much,
because its words are the ones they have just been meeting and the ones they will meet
next.

**Per-text topics** (`text_topics`): each catalogue text's share of running words in each
shown topic of the topic lexicon, worked out once per index and lexicon, so the shelf can
be matched to what the reader likes as a web find already is (`finds.interests`) and
Something else can change topic.

Everything here reads the reader's own record and the library's own counts, on the box.
Nothing is stored and nothing is asked.
"""

from __future__ import annotations

import math
import threading
from array import array
from bisect import bisect_left
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .coverage import IGNORED, KNOWN

if TYPE_CHECKING:
    from .coverage import Index
    from .finds.interests import Lexicon

#: The yardsticks "common in everyday Hebrew" is read from: what people say, and what
#: the news writes. Their weights are averaged where both are on the machine.
EVERYDAY = ("conversation", "news")

#: The rate, per million running words, at which a word counts as fully useful: about
#: the hundredth commonest content word.
USEFUL_AT = 1_000.0

#: In the fallback with no yardstick, the frequency list's place stands in for a rate by
#: Zipf's law, rate ≈ 1,000,000 / (place × ZIPF).
ZIPF = 12.0

#: How much a word the reader may meet again counts on top of its first meeting.
RECUR_NEXT = 1.0
RECUR_TOPIC = 0.5

#: How many of a collection's following texts count as the reader's next items.
NEXT_ITEMS = 3

#: How much more a text that continues a collection the reader has started is worth.
CONTINUING = 1.5

#: A topic is one of a text's own when its words are at least this share of its running
#: words: the same line a web find is held to (`finds.interests.ABOUT_LEAST`).
ABOUT_LEAST = 0.03


def repeat(n: int) -> float:
    """How much a word's meetings inside one text count: none for once, half for twice,
    whole from three times."""
    return 0.0 if n < 2 else min(1.0, (n - 1) / 2)


def useful_from_rate(per_million: float) -> float:
    """A rate per million running words as usefulness between 0 and 1, log-damped."""
    if per_million <= 0:
        return 0.0
    return min(1.0, math.log1p(per_million) / math.log1p(USEFUL_AT))


def _mixed(loaded: Sequence[Any]) -> Mapping[str, float]:
    """Several yardsticks' weights averaged, by bare lemma."""
    if len(loaded) == 1:
        return dict(loaded[0].weights)
    mixed: dict[str, float] = {}
    for one in loaded:
        for lemma, weight in one.weights.items():
            mixed[lemma] = mixed.get(lemma, 0.0) + weight / len(loaded)
    return mixed


@dataclass(frozen=True)
class Usefulness:
    """How useful each word is to learn: a yardstick's weights, or the frequency list."""

    language: str
    weights: Mapping[str, float] | None = field(default=None, repr=False)

    def of(self, lemma: str) -> float:
        from .annotate import frequency

        bare = frequency._POINTS.sub("", lemma).strip()
        if self.weights is not None:
            return useful_from_rate(self.weights.get(bare, 0.0) * 1_000_000)
        place = frequency.ranks(self.language).get(bare)
        return useful_from_rate(1_000_000 / (place * ZIPF)) if place else 0.0


_LOCK = threading.Lock()
_USEFUL: dict[str, tuple[Any, Usefulness]] = {}


def usefulness(language: str) -> Usefulness:
    """The usefulness of this language's words: Hebrew's from the everyday yardsticks
    where they are on the machine, any language's from its frequency list otherwise. Read
    again when a yardstick changes."""
    from .tables import yardstick

    code = (language or "he").split("-")[0].lower()
    loaded = (
        [one for one in (yardstick.load(name) for name in EVERYDAY) if one is not None]
        if code == "he"
        else []
    )
    stamp = tuple((one.register, one.version, one.digest) for one in loaded)
    with _LOCK:
        held = _USEFUL.get(code)
        if held is not None and held[0] == stamp:
            return held[1]
    made = Usefulness(code, _mixed(loaded) if loaded else None)
    with _LOCK:
        _USEFUL[code] = (stamp, made)
    return made


_TABLES: dict[tuple[int, str, int], tuple[tuple[str, ...], Any]] = {}


def _per_index(index: Index, name: str, salt: int, make: Callable[[], Any]) -> Any:
    """Something worked out once for every word of an index's shared table, kept while
    the index is the same one. One index at a time is all a box ever reads."""
    key = (id(index.words), name, salt)
    with _LOCK:
        held = _TABLES.get(key)
        if held is not None and held[0] is index.words:
            return held[1]
    made = make()
    with _LOCK:
        for stale in [one for one in _TABLES if one[0] != key[0]]:
            del _TABLES[stale]
        _TABLES[key] = (index.words, made)
    return made


def useful_table(index: Index, useful: Usefulness) -> array[float]:
    """`Usefulness.of` for every word in the index's table, by position."""
    return _per_index(  # type: ignore[no-any-return]
        index,
        f"useful:{useful.language}",
        id(useful),
        lambda: array("d", (useful.of(word) for word in index.words)),
    )


def topic_table(index: Index, lexicon: Lexicon) -> tuple[tuple[str, ...], ...]:
    """Each word's shown topics in the lexicon, by position in the index's table."""
    shown = set(lexicon.shown)

    def make() -> tuple[tuple[str, ...], ...]:
        return tuple(
            tuple(code for code in lexicon.lemmas.get(word, ()) if code in shown)
            for word in index.words
        )

    return _per_index(index, "topics", id(lexicon), make)  # type: ignore[no-any-return]


_TEXT_TOPICS: dict[tuple[int, int], dict[str, dict[str, float]]] = {}


def text_topics(index: Index, entry_id: str, lexicon: Lexicon | None) -> dict[str, float]:
    """One catalogue text's topics: each shown topic's share of its running words, from
    the index's counts, the topics under `ABOUT_LEAST` left out. Nothing where there is no
    lexicon or the text was not counted. Worked out once a text, index and lexicon."""
    if lexicon is None:
        return {}
    key = (id(index.words), id(lexicon))
    with _LOCK:
        kept = _TEXT_TOPICS.get(key)
        if kept is None:
            _TEXT_TOPICS.clear()
            kept = _TEXT_TOPICS[key] = {}
        if entry_id in kept:
            return kept[entry_id]
    tally = index.counts.get(entry_id)
    positions = index.texts.get(entry_id)
    found: dict[str, float] = {}
    if tally is not None and positions:
        table = topic_table(index, lexicon)
        skip = index._not_words
        counts: dict[str, int] = {}
        total = 0
        for at, n in zip(positions, tally, strict=False):
            if at in skip:
                continue
            total += n
            for code in table[at] if at < len(table) else ():
                counts[code] = counts.get(code, 0) + n
        if total:
            found = {
                code: round(n / total, 4) for code, n in counts.items() if n / total >= ABOUT_LEAST
            }
    with _LOCK:
        kept[entry_id] = found
    return found


def main_topic(topics: Mapping[str, float]) -> str:
    """A text's strongest topic, or "" where it has none."""
    return max(sorted(topics), key=lambda code: topics[code]) if topics else ""


@dataclass(frozen=True)
class Reader:
    """What the score needs of one reader, worked out once per choice."""

    #: Their marks by position in the index's table (`Index.statuses`).
    statuses: Mapping[int, int]
    #: The estimate's chance for every word by position (`Estimate.chances`); None reads
    #: every unmarked word as unknown, as marks alone say.
    chances: Sequence[float] | None = None
    #: Positions of the words they met in a section they finished.
    met: frozenset[int] = frozenset()
    #: The topics their reading suggests (`finds.interests.inferred`).
    liked: tuple[str, ...] = ()


def reader(
    index: Index,
    statuses: Mapping[int, int],
    chances: Sequence[float] | None,
    met: Iterable[str] = (),
    liked: Iterable[str] = (),
) -> Reader:
    """A `Reader` from the words they met, as lemmas, put in the index's positions."""
    at = (index._position(lemma) for lemma in met)
    return Reader(
        statuses=statuses,
        chances=chances,
        met=frozenset(one for one in at if one is not None),
        liked=tuple(liked),
    )


def _holds(positions: Sequence[int], at: int) -> bool:
    found = bisect_left(positions, at)
    return found < len(positions) and positions[found] == at


def value(
    index: Index,
    entry_id: str,
    who: Reader,
    useful: Sequence[float],
    *,
    following: Sequence[str] = (),
    topics: Iterable[str] = (),
    lexicon: Lexicon | None = None,
    continuing: bool = False,
) -> float | None:
    """The text's learning value for this reader: the expected new words per hundred
    running words that come back (module docstring). None where the text was not counted.

    `following` is the catalogue ids of the reader's next items in its collection, and
    `topics` the text's own (`text_topics`); a word of one of those or of the reader's
    liked topics may come back. `continuing` is whether it continues a collection the
    reader has started.
    """
    tally = index.counts.get(entry_id)
    positions = index.texts.get(entry_id)
    if tally is None or not positions:
        return None
    skip = index._not_words
    statuses = who.statuses
    chances = who.chances
    last_chance = len(chances) if chances is not None else 0
    last_useful = len(useful)
    nexts = [index.texts.get(one, ()) for one in following]
    nexts = [one for one in nexts if one]
    wanted = set(topics) | set(who.liked)
    table = topic_table(index, lexicon) if lexicon is not None and wanted else None
    total = 0.0
    scored = 0
    for at, n in zip(positions, tally, strict=False):
        if at in skip:
            continue
        status = statuses.get(at)
        if status == IGNORED:
            continue
        scored += n
        if status == KNOWN or n < 2:
            continue
        worth = useful[at] if at < last_useful else 0.0
        if worth <= 0:
            continue
        if status is not None:
            unknown = 1.0
        elif chances is not None and at < last_chance:
            unknown = 1.0 - chances[at]
        else:
            unknown = 1.0
        if unknown <= 0:
            continue
        if at in who.met or any(_holds(one, at) for one in nexts):
            recur = RECUR_NEXT
        elif table is not None and at < len(table) and wanted.intersection(table[at]):
            recur = RECUR_TOPIC
        else:
            recur = 0.0
        total += unknown * worth * repeat(n) * (1.0 + recur)
    if not scored:
        return 0.0
    out = 100.0 * total / scored
    return out * CONTINUING if continuing else out


def bag_value(
    bag: Mapping[str, int],
    tokens: int,
    p_known: Callable[[str], float | None],
    useful: Usefulness,
    *,
    met: Iterable[str] = (),
    liked: Iterable[str] = (),
    lexicon: Lexicon | None = None,
) -> float:
    """`value` for a page known only as lemma counts (a web find, `finds.pool.Find.bag`),
    with no collection: a word comes back where the reader met it before or where it is
    of a topic they like."""
    if tokens <= 0:
        return 0.0
    seen = set(met)
    wanted = set(liked)
    total = 0.0
    for lemma, n in bag.items():
        if n < 2:
            continue
        chance = p_known(lemma)
        if chance is None or chance >= 1.0:
            continue
        worth = useful.of(lemma)
        if worth <= 0:
            continue
        if lemma in seen:
            recur = RECUR_NEXT
        elif lexicon is not None and wanted.intersection(lexicon.lemmas.get(lemma, ())):
            recur = RECUR_TOPIC
        else:
            recur = 0.0
        total += (1.0 - chance) * worth * repeat(n) * (1.0 + recur)
    return 100.0 * total / tokens


@dataclass(frozen=True)
class Narrow:
    """Where each text stands in the collections, for narrow reading."""

    #: Catalogue id → the ids of the reader's next items after it in its collection.
    following: Mapping[str, tuple[str, ...]]
    #: The ids that continue a collection the reader has started.
    continuing: frozenset[str]


def narrow(collections: Iterable[tuple[Sequence[str], bool]], read: Iterable[str]) -> Narrow:
    """For each collection (its members in order, and whether the order is a reading
    order), each member's next `NEXT_ITEMS` unread members, and which members continue a
    collection the reader has started: in an ordered one, the first unread member after
    the furthest they have read; in an unordered one, every unread member."""
    done = set(read)
    following: dict[str, tuple[str, ...]] = {}
    continuing: set[str] = set()
    for members, ordered in collections:
        members = list(members)
        if len(members) < 2:
            continue
        for at, member in enumerate(members):
            after = [one for one in members[at + 1 :] if one not in done]
            if not ordered:
                after += [one for one in members[:at] if one not in done]
            following[member] = tuple(after[:NEXT_ITEMS])
        reached = [at for at, member in enumerate(members) if member in done]
        if not reached:
            continue
        if ordered:
            nxt = next((one for one in members[max(reached) + 1 :] if one not in done), None)
            if nxt is not None:
                continuing.add(nxt)
        else:
            continuing.update(one for one in members if one not in done)
    return Narrow(following=following, continuing=frozenset(continuing))


def forget() -> None:
    """Drop everything kept (tests)."""
    with _LOCK:
        _USEFUL.clear()
        _TABLES.clear()
        _TEXT_TOPICS.clear()
