"""How much of a text somebody already knows.

The one number that answers "what should I read next?", and it was already being computed
and thrown away. The reader works it out for the section in front of you —
`"38% known here · 214 you have not marked yet"` — from the lemmas embedded in that one
page, and its own comment says what it is for: *the reason to know it is choosing what to
read next.* But it is never persisted, never synced, and invisible to every other page,
so the choosing happens somewhere it cannot be seen.

It needs no new tracking to recover. Every build writes an annotation carrying a lemma for
every word, and the account already holds the reader's whole vocabulary keyed by lemma.
The intersection is the answer.

**What it is not.** This is vocabulary, not position: nothing anywhere records how far
through a text somebody has read, and this must never be dressed up as if it did. A high
number means a text will be comfortable, not that it has been finished.
"""

from __future__ import annotations

import json
from array import array
from bisect import bisect_left
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import tzinfo
from functools import cached_property, lru_cache
from pathlib import Path

from .paths import write_atomic

# Statuses that count as knowing a word. The learning ladder (1-3) is deliberately not
# here: a word somebody is halfway through learning is a word the text will still cost
# them something to read.
KNOWN = 9

#: The status a word set aside as not vocabulary carries: a name, a numeral, a word from
#: another language. Neither known nor waiting, so it comes out of a text's total rather
#: than counting against the reader, as the reader's own figure takes it out
#: (`reader.js`, `renderStats`; known-issues 1.18).
IGNORED = 0

ANNOTATION = "annotation.json"
LEMMAS = "lemmas.json"


@dataclass(frozen=True)
class Coverage:
    """What one reader already knows of one text."""

    known: float
    fresh: int
    total: int

    def state(self) -> dict[str, float | int]:
        return {"known": round(self.known, 4), "fresh": self.fresh, "words": self.total}


def lemmas(folder: Path) -> list[str]:
    """Every distinct dictionary form in a built targum (`_lemmas_and_counts`)."""
    return list(_lemmas_and_counts(folder, counted=False)[0])


def tally(folder: Path) -> dict[str, int]:
    """How often each dictionary form comes round in a built targum, running words, read
    as `lemmas` reads the forms (names, numbers and a post's tags out). Empty for a targum
    built without word-level annotation."""
    return _lemmas_and_counts(folder, counted=True)[1]


def _lemmas_and_counts(folder: Path, *, counted: bool) -> tuple[list[str], dict[str, int]]:
    """Every distinct dictionary form in a built targum, and each one's running count.

    Cached beside the annotation it came from, because the annotation is large — 4.4 MB
    for Psalms — and this reduces it to about 21 KB. Written on first ask rather than at
    build time, so it works for the targums that already exist rather than only for ones
    built after today.

    Returns nothing for a targum built without word-level annotation, which is a normal
    state rather than a fault: `--words` is a flag.
    """
    annotation = folder / ANNOTATION
    if not annotation.is_file():
        return [], {}
    # The cache is stamped with the annotation it was read from. An annotation is
    # rewritten in place when the annotator learns something — every word became a
    # token on 2026-08-28 — and a cache that outlived that would go on reporting a
    # denominator a tenth too small, for half the shelf, with nothing to say so.
    from .ingest import post as post_module

    try:
        stat = annotation.stat()
        stamp = [stat.st_mtime_ns, stat.st_size]
    except OSError:
        return [], {}
    # A post's hashtags, mentions and addresses are names, not words (design.md §12, "A
    # post keeps its shape"), and are left out here as the page leaves them out. The
    # stamp says so, because a count cached before the post's manifest was there counted
    # them.
    unwordly = post_module.left_out(folder)
    if unwordly is not None:
        stamp.append(1)
    cached = folder / LEMMAS
    if cached.is_file():
        try:
            found = json.loads(cached.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            found = None
        # A cache written before the counts were kept (2026-11-01, targum-internal#613)
        # still answers for the forms; asked for counts, it is read again once.
        if (
            isinstance(found, dict)
            and found.get("stamp") == stamp
            and (not counted or isinstance(found.get("counts"), dict))
        ):
            kept = found.get("counts") if isinstance(found.get("counts"), dict) else {}
            return (
                [str(lemma) for lemma in found.get("lemmas") or []],
                {str(lemma): int(n) for lemma, n in (kept or {}).items()},
            )

    try:
        loaded = json.loads(annotation.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], {}

    from .annotate.base import not_vocabulary

    # A name is not a word the reader has to know, so it is not one they can fail to
    # know either: left out of the denominator, or a book of names could never be read.
    counts: dict[str, int] = {}
    for sid, tokens in (loaded.get("tokens") or {}).items():
        for token in tokens:
            lemma = str(token.get("lemma") or "")
            if not lemma or not_vocabulary(token.get("pos"), token.get("entity")):
                continue
            if (
                unwordly
                and sid in unwordly
                and post_module.inside(
                    int(token.get("start") or 0), int(token.get("end") or 0), unwordly[sid]
                )
            ):
                continue
            counts[lemma] = counts.get(lemma, 0) + 1
    out = sorted(counts)

    try:
        write_atomic(
            cached,
            json.dumps({"stamp": stamp, "lemmas": out, "counts": counts}, ensure_ascii=False),
        )
    except OSError:
        # A read-only or full disk costs the cache, not the answer.
        pass
    return out, counts


def against(folder: Path, marked: dict[str, int]) -> Coverage | None:
    """This text measured against what one person has marked.

    `marked` maps a dictionary form to how well they know it. None when the text carries
    no word-level annotation — the caller shows what it showed before rather than a zero,
    because "0% known" and "not measured" are very different claims to make about a book.
    """
    words = lemmas(folder)
    if not words:
        return None
    return measure(words, marked)


def running_against(folder: Path, marked: Mapping[str, int]) -> Coverage | None:
    """A built text's running words measured against one person's marks, as
    `Index.running` measures a catalogue entry (design.md §12, "The Library's bands count
    running words", 2026-11-01): each word weighs as often as it comes round, one-letter
    clitics and the words the reader ignored are out of the total. None where the text
    carries no word-level annotation."""
    counts = tally(folder)
    if not counts:
        return None
    return measure_running(counts, marked)


def measure_running(counts: Mapping[str, int], marked: Mapping[str, int]) -> Coverage:
    """Running counts measured against marks: `known` the share of running words marked
    known, `fresh` the distinct forms not on the list, `total` running words."""
    from .touchstones import a_word

    known = scored = fresh = 0
    for lemma, n in counts.items():
        if not a_word(lemma):
            continue
        status = marked.get(lemma)
        if status == IGNORED:
            continue
        scored += n
        if status == KNOWN:
            known += n
        elif status is None:
            fresh += 1
    return Coverage(known=known / scored if scored else 0.0, fresh=fresh, total=scored)


def measure(words: list[str], marked: dict[str, int]) -> Coverage:
    """A text's distinct dictionary forms measured against one person's marks, as the
    reader measures the page in front of them: the words they ignored are left out of the
    total, so the share the shelf, the Library and the contents page show is the one the
    reader's bar shows (design.md §12, "Known means marked, everywhere a share is shown").
    A text whose every word is ignored has nothing to measure, and its total is nought."""
    known = sum(1 for lemma in words if marked.get(lemma) == KNOWN)
    fresh = sum(1 for lemma in words if lemma not in marked)
    scored = sum(1 for lemma in words if marked.get(lemma) != IGNORED)
    return Coverage(known=known / scored if scored else 0.0, fresh=fresh, total=scored)


# -- the catalogue's own lemmas (targum-internal#293) ---------------------------------
#
# Everything above answers the question for a text this reader has *built*. The library
# asks it about 900 rows, nearly all of which they have not, and the front door sells the
# answer: "The library is sorted by the words you already know, so there's always a video,
# a story or a chapter within reach."
#
# The gap was never a measurement problem. Every catalogue text has an annotation
# somewhere — a build on this box, or one `scripts/measure_difficulty.py` makes to weigh
# it — and `lemmas()` above already reduces one to the ~21 KB that matters. What was
# missing is a place to keep the answer where the library can reach it without a build.
#
# So: one index beside the catalogue, mapping an entry id to ids into a shared table of
# dictionary forms. It rides beside `catalogue.json` and not in the repo, for the reason
# the catalogue does — the library's contents are not public — and it is read server-side
# only. The browser never sees it: what crosses the wire is the one number per row that
# `serve._measure` already puts there for a built text.

#: The file's shape, so an index written by an older targum can be refused rather than
#: misread. Bumped when the encoding changes, which is not the same as the catalogue
#: changing — a rebuilt index keeps this number.
INDEX_VERSION = 1


@dataclass(frozen=True)
class Index:
    """Every catalogue text's dictionary forms, in one table.

    `words` is the shared table and `texts` maps an entry id to sorted positions in it.
    Sorted because it makes the intersection below a walk rather than a hash lookup per
    lemma, and because a sorted list of small integers compresses.
    """

    words: tuple[str, ...]
    texts: dict[str, tuple[int, ...]]
    #: How often each of an entry's dictionary forms comes round in it, running words,
    #: aligned with its `texts` positions (targum-internal#95, #96). An `array` rather
    #: than a tuple because this doubles the index's width and the server holds it whole:
    #: four bytes a count instead of a pointer to an int. Missing for an entry counted by
    #: an older targum, which answers "not counted" — the field was added without a
    #: version bump because an older reader ignores it and a newer one reads an older
    #: file as uncounted, so neither misreads the other.
    counts: dict[str, array[int]] = field(default_factory=dict)

    def _position(self, lemma: str) -> int | None:
        """Where a dictionary form sits in the shared table, which is sorted."""
        at = bisect_left(self.words, lemma)
        return at if at < len(self.words) and self.words[at] == lemma else None

    def count_in(self, entry_id: str, lemma: str) -> int | None:
        """How many times a dictionary form comes round in one catalogue entry.

        None where the entry was not counted — not in the index, or indexed before counts
        were — and 0 where it was counted and the word is not in it: "not counted" and
        "never there" are different claims, as "not measured" and 0% are above.
        """
        counts = self.counts.get(entry_id)
        if counts is None:
            return None
        at = self._position(lemma)
        if at is None:
            return 0
        positions = self.texts.get(entry_id, ())
        found = bisect_left(positions, at)
        if found < len(positions) and positions[found] == at and found < len(counts):
            return int(counts[found])
        return 0

    def count_across(self, lemma: str, entry_ids: Iterable[str] | None = None) -> tuple[int, int]:
        """How many times a dictionary form comes round across the counted entries, and
        in how many of them: the whole library, or only `entry_ids` (a register, a
        collection). An entry that was never counted adds nothing to either number."""
        wanted = self.counts.keys() if entry_ids is None else entry_ids
        total = texts = 0
        for entry_id in wanted:
            found = self.count_in(entry_id, lemma)
            if found:
                total += found
                texts += 1
        return total, texts

    def lemmas_for(self, entry_id: str) -> list[str]:
        """The dictionary forms of one entry, or nothing where it is not in the index."""
        return [self.words[at] for at in self.texts.get(entry_id, ()) if at < len(self.words)]

    def against(self, entry_id: str, marked: dict[str, int]) -> Coverage | None:
        """One catalogue entry measured against what this reader has marked.

        None where the entry is not in the index, which is the same "not measured" the
        built path returns and is shown the same way: nothing, rather than 0%.
        """
        words = self.lemmas_for(entry_id)
        if not words:
            return None
        return measure(words, marked)

    # -- running words (design.md §12, "What to read next is chosen on running words",
    # 2026-10-31; targum-internal#612) ------------------------------------------------
    #
    # `against` counts a text's distinct forms, so a word met once weighs what a word met
    # on every line weighs. The research the chooser follows (ling-he, 2026-10-31) states
    # every threshold in running words, and measured the two kinds 8–26 points apart on
    # the same texts: a text at 90% of its running words is at 70–83% of its distinct
    # forms. `counts` has carried each form's running count since #95; this reads it.

    @cached_property
    def _not_words(self) -> frozenset[int]:
        """Positions of the forms that are never a word to learn: a one-letter clitic
        DICTA split off (`touchstones.a_word`). Left out of a running count whole, or
        ו־ and ה־ alone would be a fifth of every Hebrew text and a reader could never
        reach the floor without marking a prefix letter."""
        from .touchstones import a_word

        return frozenset(at for at, word in enumerate(self.words) if not a_word(word))

    def statuses(self, marked: Mapping[str, int]) -> dict[int, int]:
        """A reader's marks by position in the shared table: worked out once for a list
        of entries, so `running` over the whole catalogue is a walk of small integers
        rather than a string lookup per word per text."""
        out: dict[int, int] = {}
        for lemma, status in marked.items():
            at = self._position(lemma)
            if at is not None:
                out[at] = status
        return out

    def running(
        self,
        entry_id: str,
        marked: Mapping[str, int],
        statuses: Mapping[int, int] | None = None,
    ) -> Coverage | None:
        """One catalogue entry's running words measured against this reader's marks: of
        every word in it, names, numbers and one-letter clitics left out and the words
        the reader ignored taken out of the total, the share they have marked known.

        `total` is running words and `fresh` distinct forms not yet on the reader's list.
        Marks only (design.md §12, "Known means marked"). None where the entry was not
        counted, which is "not measured", as `against` says it.
        """
        tally = self.counts.get(entry_id)
        positions = self.texts.get(entry_id)
        if tally is None or not positions:
            return None
        held = self.statuses(marked) if statuses is None else statuses
        skip = self._not_words
        known = scored = fresh = 0
        for at, n in zip(positions, tally, strict=False):
            if at in skip:
                continue
            status = held.get(at)
            if status == IGNORED:
                continue
            scored += n
            if status == KNOWN:
                known += n
            elif status is None:
                fresh += 1
        return Coverage(known=known / scored if scored else 0.0, fresh=fresh, total=scored)

    def expected(
        self,
        entry_id: str,
        statuses: Mapping[int, int],
        chances: Sequence[float],
    ) -> float | None:
        """The share of an entry's running words a reader is *estimated* to know: the
        chooser's number (design.md §12, "The chooser estimates the words you have not
        marked", 2026-11-01; targum-internal#613), never a page's.

        Counted as `running` counts, except that a word with no mark counts as its chance
        of being known (`estimate.Estimate.chances`, by position in the shared table)
        rather than as unknown. A mark still wins: known is 1, learning 0, ignored out.
        None where the entry was not counted.
        """
        tally = self.counts.get(entry_id)
        positions = self.texts.get(entry_id)
        if tally is None or not positions:
            return None
        skip = self._not_words
        known = 0.0
        scored = 0
        last = len(chances)
        for at, n in zip(positions, tally, strict=False):
            if at in skip:
                continue
            status = statuses.get(at)
            if status == IGNORED:
                continue
            scored += n
            if status == KNOWN:
                known += n
            elif status is None and at < last:
                known += n * chances[at]
        return known / scored if scored else 0.0


EMPTY = Index(words=(), texts={})


@lru_cache(maxsize=4)
def _read_index(path: Path, stamp: tuple[int, int]) -> Index:
    """The parse itself, kept for as long as the file it came from has not changed.

    `stamp` is not read here: it is in the signature so that a rewritten index is a
    different cache key and the next ask re-reads it. Without this the whole file was
    parsed on every `/readers`, which for a full catalogue is megabytes of JSON on a
    request that is already the slowest page in the product.
    """
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return EMPTY
    return _index_from(loaded)


def read_index(path: Path | None) -> Index:
    """The index beside the catalogue, or an empty one.

    Empty is a working state and not a fault: a box with no index measures what it can
    from built folders and says nothing about the rest, which is exactly what it did
    before the index existed.
    """
    if path is None or not path.is_file():
        return EMPTY
    try:
        stat = path.stat()
    except OSError:
        return EMPTY
    return _read_index(path, (stat.st_mtime_ns, stat.st_size))


def _index_from(loaded: object) -> Index:
    """One parsed file, checked and turned into an `Index`."""
    if not isinstance(loaded, dict) or loaded.get("version") != INDEX_VERSION:
        return EMPTY
    words = tuple(str(word) for word in loaded.get("words") or ())
    texts: dict[str, tuple[int, ...]] = {}
    for entry_id, positions in (loaded.get("texts") or {}).items():
        if isinstance(positions, list):
            texts[str(entry_id)] = tuple(int(at) for at in positions)
    counts: dict[str, array[int]] = {}
    for entry_id, tally in (loaded.get("counts") or {}).items():
        # A row of counts that does not line up with its row of words is dropped whole:
        # every number in it would be some other word's.
        if isinstance(tally, list) and len(tally) == len(texts.get(str(entry_id), ())):
            try:
                counts[str(entry_id)] = array("I", (int(n) for n in tally))
            except (OverflowError, TypeError, ValueError):
                continue
    return Index(words=words, texts=texts, counts=counts)


def build_index(
    found: dict[str, list[str]], tallies: dict[str, dict[str, int]] | None = None
) -> Index:
    """Turn a map of entry id to its dictionary forms into the shared-table shape.

    `tallies`, where given, is each entry's running count of each form
    (`occurrences.Occurrences.totals`); an entry with no tally is indexed uncounted. A
    form in `found` that the tally does not have counts 0 — the two are read off the
    same annotation, so that is a word neither filter kept, not a word nobody counted.
    """
    table = sorted({lemma for lemmas_ in found.values() for lemma in lemmas_ if lemma})
    at = {lemma: n for n, lemma in enumerate(table)}
    texts: dict[str, tuple[int, ...]] = {}
    for entry_id, lemmas_ in found.items():
        # After mapping, not before: a text whose only word is the empty string is a
        # truthy list and an empty row, and a row that means nothing is worse in an index
        # than no row — `against` would return None for it either way, so it would sit
        # there claiming to be measured and answering that it is not.
        positions = tuple(sorted(at[lemma] for lemma in set(lemmas_) if lemma))
        if positions:
            texts[entry_id] = positions
    counts: dict[str, array[int]] = {}
    for entry_id, tally in (tallies or {}).items():
        if entry_id in texts:
            counts[entry_id] = array("I", (int(tally.get(table[at], 0)) for at in texts[entry_id]))
    return Index(words=tuple(table), texts=texts, counts=counts)


def write_index(path: Path, index: Index) -> None:
    """Write the index where `read_index` will find it."""
    write_atomic(
        path,
        json.dumps(
            {
                "version": INDEX_VERSION,
                "words": list(index.words),
                "texts": {entry_id: list(at) for entry_id, at in sorted(index.texts.items())},
                **(
                    {
                        "counts": {
                            entry_id: list(tally)
                            for entry_id, tally in sorted(index.counts.items())
                        }
                    }
                    if index.counts
                    else {}
                ),
            },
            ensure_ascii=False,
        ),
    )


# -- what a reader knew of what they read (targum-internal#291) -----------------------
#
# Everything above asks how much of a *text* somebody knows, which is a question about
# choosing. This asks it about a section they have finished, at the moment they finish
# it, and keeps the answer: one row a section, never recomputed. A row is a fact about a
# day. Recomputed against today's ledger, the whole history would rise every time a word
# was marked, and the line drawn from it would be a second copy of the known count rather
# than a record of what reading was like.
#
# Running words rather than distinct ones. "You knew 72% of the words you read" is a
# claim about the page as it was read, where the commonest words come round
# again and again; a share of distinct forms would weigh a word met once the same as one
# met on every line, and read as harder than the page was.


@dataclass(frozen=True)
class Reading:
    """One finished section measured against the ledger as it stood: how many running
    words it had, names and numbers left out, and how many of them were known."""

    tokens: int
    known: int


def section_lemmas(folder: Path, number: int) -> list[str] | None:
    """The dictionary form of every running word in one section of a built text.

    The section is the one the reader's page names (`data.section`, the `sec-NNNN.html`
    it was written to), found the way the build found it. A text rendered whole is one
    section of everything. None where there is no annotation or no such section: not
    measured, which is a different claim from a section of no words.
    """
    from .annotate.base import not_vocabulary
    from .ingest import post as post_module
    from .models import SegmentedDocument, read_artifact
    from .render.builder import split_sections

    annotation = folder / ANNOTATION
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    if segmented is None or not annotation.is_file():
        return None
    parts = split_sections(segmented)
    written = len(list((folder / "reader").glob("sec-*.html")))
    # A text rendered whole (`build(whole=True)`) writes one page, not the split the
    # headings would give it, and its one section is every segment.
    if written <= 1 and number == 1:
        wanted = {segment.id for segment in segmented.segments}
    else:
        found = next((part for part in parts if part.number == number), None)
        if found is None:
            return None
        wanted = set(found.segment_ids)
    try:
        loaded = json.loads(annotation.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    unwordly = post_module.left_out(folder) or {}
    out: list[str] = []
    for sid, tokens in (loaded.get("tokens") or {}).items():
        if sid not in wanted:
            continue
        for token in tokens:
            lemma = str(token.get("lemma") or "")
            if not lemma or not_vocabulary(token.get("pos"), token.get("entity")):
                continue
            if sid in unwordly and post_module.inside(
                int(token.get("start") or 0), int(token.get("end") or 0), unwordly[sid]
            ):
                continue
            out.append(lemma)
    return out


def sections_lemmas(folder: Path) -> dict[int, tuple[str, ...]]:
    """`section_lemmas` for every section of a text at once, by section number: the
    annotation read once, not once a row — a Torah book is fifty sections over 9 MB of
    annotation. Kept while the annotation and the segments are unchanged, so a contents
    page asked for again reads nothing (design.md §12, "A contents page is a page of its
    own", 2026-10-09). Empty where there is no annotation: not measured."""
    stamps = []
    for name in (ANNOTATION, "segments.json"):
        try:
            found = (folder / name).stat()
        except OSError:
            return {}
        stamps.append((found.st_mtime_ns, found.st_size))
    return _sections_lemmas(folder, tuple(stamps))


@lru_cache(maxsize=16)
def _sections_lemmas(
    folder: Path, stamps: tuple[tuple[int, int], ...]
) -> dict[int, tuple[str, ...]]:
    from .annotate.base import not_vocabulary
    from .ingest import post as post_module
    from .models import SegmentedDocument, read_artifact
    from .render.builder import split_sections

    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    if segmented is None:
        return {}
    try:
        loaded = json.loads((folder / ANNOTATION).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    # The same sections the pages were written as: a text rendered whole is one.
    written = len(list((folder / "reader").glob("sec-*.html")))
    if written <= 1:
        where = {segment.id: 1 for segment in segmented.segments}
    else:
        where = {sid: part.number for part in split_sections(segmented) for sid in part.segment_ids}
    unwordly = post_module.left_out(folder) or {}
    out: dict[int, list[str]] = {}
    for sid, tokens in (loaded.get("tokens") or {}).items():
        number = where.get(sid)
        if number is None:
            continue
        kept = out.setdefault(number, [])
        for token in tokens:
            lemma = str(token.get("lemma") or "")
            if not lemma or not_vocabulary(token.get("pos"), token.get("entity")):
                continue
            if sid in unwordly and post_module.inside(
                int(token.get("start") or 0), int(token.get("end") or 0), unwordly[sid]
            ):
                continue
            kept.append(lemma)
    return {number: tuple(lemmas) for number, lemmas in out.items()}


def section_reading(folder: Path, number: int, marked: dict[str, int]) -> Reading | None:
    """One section measured against what one person has marked, now.

    None where the section cannot be measured or has no words in it: a row of nothing
    would be a point on the line at zero, and "knew none of it" is not what happened.
    """
    words = section_lemmas(folder, number)
    if not words:
        return None
    return Reading(tokens=len(words), known=sum(1 for w in words if marked.get(w) == KNOWN))


#: Under this many points the line is not drawn, and the page says what would draw it:
#: one month is a dot, not a line (two since 2026-10-09: the board draws from two).
POINTS = 2

#: Under this many running words a month is a guess and not a point — the same floor
#: `level.known_share` keeps (its `MEASURABLE`), for the same reason.
MEASURABLE = 20


def zone_named(name: str) -> tzinfo:
    """The time zone a browser names (`Intl…timeZone`, "Asia/Jerusalem"), or UTC for a
    name that is empty or not one. Read per request and kept nowhere."""
    from datetime import UTC
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    name = (name or "").strip()
    if not name or len(name) > 64 or ".." in name or name.startswith("/"):
        return UTC
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return UTC


def by_day(
    rows: list[dict[str, int | str]], zone: tzinfo | None = None
) -> list[dict[str, int | str]]:
    """The reading rows of one language, a bucket a day in the reader's time zone, oldest
    first (design.md §12, "Your level, v3", 2026-10-29), so a section finished at 23:30 in
    Tel Aviv is that day's and not the next one's.

    Each bucket is the day's running words, the known ones among them and how many
    sections are behind it, and every day with a section is sent however short: the page
    sums weeks and months from these, words and never shares, so a day left out would
    take its words out of its week. The page leaves a point under `MEASURABLE` words off
    its line.
    """
    from datetime import UTC, datetime

    days: dict[str, dict[str, int | str]] = {}
    for row in rows:
        at = int(row.get("at") or 0)
        tokens = int(row.get("tokens") or 0)
        if at <= 0 or tokens <= 0:
            continue
        day = datetime.fromtimestamp(at / 1000, tz=zone or UTC).strftime("%Y-%m-%d")
        bucket = days.setdefault(day, {"day": day, "tokens": 0, "known": 0, "sections": 0})
        bucket["tokens"] = int(bucket["tokens"]) + tokens
        bucket["known"] = int(bucket["known"]) + int(row.get("known") or 0)
        bucket["sections"] = int(bucket["sections"]) + 1
    return [days[d] for d in sorted(days)]


def by_month(
    rows: list[dict[str, int | str]], zone: tzinfo | None = None
) -> list[dict[str, int | str]]:
    """The reading rows of one language, a point a month, oldest first.

    Each point is the month's running words added up and the known ones among them — so
    a long chapter counts for more than a short one, as it did on the page — and how many
    sections are behind it. Months are in `zone`, the reader's, and UTC where none is
    named. A month under `MEASURABLE` words is left out.
    """
    from datetime import UTC, datetime

    months: dict[str, dict[str, int | str]] = {}
    for row in rows:
        at = int(row.get("at") or 0)
        tokens = int(row.get("tokens") or 0)
        if at <= 0 or tokens <= 0:
            continue
        month = datetime.fromtimestamp(at / 1000, tz=zone or UTC).strftime("%Y-%m")
        point = months.setdefault(month, {"month": month, "tokens": 0, "known": 0, "sections": 0})
        point["tokens"] = int(point["tokens"]) + tokens
        point["known"] = int(point["known"]) + int(row.get("known") or 0)
        point["sections"] = int(point["sections"]) + 1
    return [months[m] for m in sorted(months) if int(months[m]["tokens"]) >= MEASURABLE]


def monthly(
    rows: list[dict[str, int | str]], zone: tzinfo | None = None
) -> list[dict[str, int | str]]:
    """`by_month`, as a line: nothing under `POINTS` points, so the caller says what is
    missing rather than drawing a slope out of two."""
    points = by_month(rows, zone)
    return points if len(points) >= POINTS else []


# -- the Tanakh map (targum-internal#144) ---------------------------------------------
#
# The same question once more, asked of every chapter of the Tanakh at once: 929 numbers,
# one a square, each the share of that chapter's running words the reader knows. Running
# words and not distinct ones, for the reason `Reading` gives — the commonest words come
# round on every line, and a chapter is as readable as its lines are.
#
# Nothing here reads a build. The chapters are counted once from the Open Scriptures
# tagging (`scripts/tanakh_map.py`) and the file ships in the package beside
# `annotate/tanakh.json`, public for the reason that one is: every lemma in it is the hand
# tagging's, filed by `headword_of`, which is the key a reader's marks on scripture are
# kept under.
#
# **A chapter's language is data.** The Aramaic of Daniel and Ezra is counted apart, and a
# chapter carries whichever language most of it is in. Asked about Hebrew, an Aramaic
# chapter answers None — not measured, never 0% — and the Aramaic words inside a Hebrew
# chapter (Jeremiah 10:11) are out of its Hebrew count. Asked about `arc`, the same file
# shades those chapters from an Aramaic list, and the Hebrew ones answer None.

#: The chapter file's shape, as `scripts/tanakh_map.py` writes it (`VERSION` there).
MAP_VERSION = 1
MAP = Path(__file__).parent / "annotate" / "tanakh_chapters.json"


@dataclass(frozen=True)
class Part:
    """One language's share of one chapter: its running words, the same words by
    frequency band, and each dictionary form's position in that language's ranked table
    with how often it comes round."""

    tokens: int
    bands: tuple[int, ...]
    positions: tuple[int, ...]
    counts: tuple[int, ...]


@dataclass(frozen=True)
class Chapter:
    ref: str
    verses: int
    language: str
    parts: dict[str, Part]


@dataclass(frozen=True)
class TanakhMap:
    """Every chapter of the Tanakh, counted.

    `words` is each language's dictionary forms, commonest first, so a position is also a
    frequency rank and `cuts` turns it into a band. `books` is `(name, part, chapters)` in
    the Hebrew order; `chapters` is keyed `"Genesis 1"` and ordered the same way.
    """

    words: dict[str, tuple[str, ...]]
    cuts: tuple[int, ...]
    books: tuple[tuple[str, str, int], ...]
    chapters: dict[str, Chapter]
    #: Each language's table the other way round: dictionary form to position.
    at: dict[str, dict[str, int]]

    def positions(self, known: set[str], language: str) -> frozenset[int]:
        """The reader's known words as positions in one language's table."""
        at = self.at.get(language, {})
        return frozenset(at[word] for word in known if word in at)


EMPTY_MAP = TanakhMap(words={}, cuts=(), books=(), chapters={}, at={})


def _map_from(loaded: object) -> TanakhMap:
    if not isinstance(loaded, dict) or loaded.get("version") != MAP_VERSION:
        return EMPTY_MAP
    words = {
        str(language): tuple(str(word) for word in table)
        for language, table in (loaded.get("words") or {}).items()
    }
    chapters: dict[str, Chapter] = {}
    for ref, entry in (loaded.get("chapters") or {}).items():
        parts: dict[str, Part] = {}
        for language in words:
            part = entry.get(language)
            if not isinstance(part, dict):
                continue
            flat = [int(n) for n in part.get("words") or ()]
            parts[language] = Part(
                tokens=int(part.get("tokens") or 0),
                bands=tuple(int(n) for n in part.get("bands") or ()),
                positions=tuple(flat[0::2]),
                counts=tuple(flat[1::2]),
            )
        chapters[str(ref)] = Chapter(
            ref=str(ref),
            verses=int(entry.get("verses") or 0),
            language=str(entry.get("language") or "he"),
            parts=parts,
        )
    return TanakhMap(
        words=words,
        cuts=tuple(int(n) for n in loaded.get("cuts") or ()),
        books=tuple((str(b[0]), str(b[1]), int(b[2])) for b in loaded.get("books") or ()),
        chapters=chapters,
        at={
            language: {word: n for n, word in enumerate(table)} for language, table in words.items()
        },
    )


@lru_cache(maxsize=2)
def _read_map(path: Path, stamp: tuple[int, int]) -> TanakhMap:
    """The parse, kept while the file is unchanged; `stamp` is the cache key only."""
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return EMPTY_MAP
    return _map_from(loaded)


def read_map(path: Path | None = None) -> TanakhMap:
    """The chapter file, or an empty map where there is none or it is not this shape.

    Empty answers every chapter with nothing, which is what a page should draw when it
    cannot measure: unshaded, never 0%.
    """
    where = path or MAP
    try:
        stat = where.stat()
    except OSError:
        return EMPTY_MAP
    return _read_map(where, (stat.st_mtime_ns, stat.st_size))


def chapter_map(
    known: set[str], language: str = "he", path: Path | None = None
) -> dict[str, float | None]:
    """Every chapter's share of running words whose dictionary form is in `known`.

    `known` is the reader's list as known — the lemmas they marked `KNOWN`, not the ones
    they are learning, for the reason `KNOWN` gives. Keyed `"Genesis 1"`, in the Hebrew
    order. None for a chapter in another language, or with no running words in this one:
    the map leaves it unshaded rather than calling it unknown.
    """
    chapters = read_map(path)
    have = chapters.positions(known, language)
    out: dict[str, float | None] = {}
    for ref, chapter in chapters.chapters.items():
        part = chapter.parts.get(language)
        if chapter.language != language or part is None or not part.tokens:
            out[ref] = None
            continue
        hit = sum(
            count for at, count in zip(part.positions, part.counts, strict=True) if at in have
        )
        out[ref] = hit / part.tokens
    return out


def chapter_estimate(
    knowledge: list[float], language: str = "he", path: Path | None = None
) -> dict[str, float | None]:
    """Every chapter's share of running words a reader probably knows, from a profile.

    `knowledge` is the share of each frequency band the reader knows, commonest band
    first — what the test measures, corrected for guessing. A chapter is its running
    words in each band weighted by that band's share, so a reader who knows the common
    words and none of the rare ones is shaded as such. A shorter profile counts the bands
    it leaves out as unknown. None where `chapter_map` would say None.
    """
    chapters = read_map(path)
    out: dict[str, float | None] = {}
    for ref, chapter in chapters.chapters.items():
        part = chapter.parts.get(language)
        if chapter.language != language or part is None or not part.tokens:
            out[ref] = None
            continue
        weighed = sum(
            count * min(max(share, 0.0), 1.0)
            for count, share in zip(part.bands, knowledge, strict=False)
        )
        out[ref] = weighed / part.tokens
    return out


#: Where the map's leaf ramp turns, as whole percentages of a chapter's running words
#: (design.md §12, 2026-09-28). Under the first a chapter is measured and plainly not
#: yet within reach; the last is the share at which reading goes on without stopping.
#: Running words climb fast — the commonest hundred dictionary forms are about half of
#: any chapter — so the steps are packed at the top, where one more word known is a
#: chapter changing hands.
MAP_STEPS = (50, 75, 90, 95)


def map_percent(share: float) -> int:
    """A share as the whole percentage the map says, rounded down: a chapter at 94.6%
    is not yet at 95%, and the square and the card must not disagree about it."""
    return int(min(max(share, 0.0), 1.0) * 100)


def map_step(percent: int) -> int:
    """Which of the ramp's steps a percentage stands on: 0 below the first turn, 4 at
    the last. `tanakh.js` counts the same way off the page's own copy of the turns."""
    return sum(1 for turn in MAP_STEPS if percent >= turn)
