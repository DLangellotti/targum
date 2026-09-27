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
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .paths import write_atomic

# Statuses that count as knowing a word. The learning ladder (1-3) is deliberately not
# here: a word somebody is halfway through learning is a word the text will still cost
# them something to read.
KNOWN = 9

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
    """Every distinct dictionary form in a built targum.

    Cached beside the annotation it came from, because the annotation is large — 4.4 MB
    for Psalms — and this reduces it to about 21 KB. Written on first ask rather than at
    build time, so it works for the targums that already exist rather than only for ones
    built after today.

    Returns nothing for a targum built without word-level annotation, which is a normal
    state rather than a fault: `--words` is a flag.
    """
    annotation = folder / ANNOTATION
    if not annotation.is_file():
        return []
    # The cache is stamped with the annotation it was read from. An annotation is
    # rewritten in place when the annotator learns something — every word became a
    # token on 2026-08-28 — and a cache that outlived that would go on reporting a
    # denominator a tenth too small, for half the shelf, with nothing to say so.
    from .ingest import post as post_module

    try:
        stat = annotation.stat()
        stamp = [stat.st_mtime_ns, stat.st_size]
    except OSError:
        return []
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
        if isinstance(found, dict) and found.get("stamp") == stamp:
            return [str(lemma) for lemma in found.get("lemmas") or []]

    try:
        loaded = json.loads(annotation.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    from .annotate.base import not_vocabulary

    # A name is not a word the reader has to know, so it is not one they can fail to
    # know either: left out of the denominator, or a book of names could never be read.
    distinct = {
        str(token.get("lemma") or "")
        for sid, tokens in (loaded.get("tokens") or {}).items()
        for token in tokens
        if not not_vocabulary(token.get("pos"), token.get("entity"))
        and not (
            unwordly
            and sid in unwordly
            and post_module.inside(
                int(token.get("start") or 0), int(token.get("end") or 0), unwordly[sid]
            )
        )
    }
    distinct.discard("")
    out = sorted(distinct)

    try:
        write_atomic(cached, json.dumps({"stamp": stamp, "lemmas": out}, ensure_ascii=False))
    except OSError:
        # A read-only or full disk costs the cache, not the answer.
        pass
    return out


def against(folder: Path, marked: dict[str, int]) -> Coverage | None:
    """This text measured against what one person has marked.

    `marked` maps a dictionary form to how well they know it. None when the text carries
    no word-level annotation — the caller shows what it showed before rather than a zero,
    because "0% known" and "not measured" are very different claims to make about a book.
    """
    words = lemmas(folder)
    if not words:
        return None
    known = sum(1 for lemma in words if marked.get(lemma) == KNOWN)
    fresh = sum(1 for lemma in words if lemma not in marked)
    return Coverage(known=known / len(words), fresh=fresh, total=len(words))


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
        known = sum(1 for lemma in words if marked.get(lemma) == KNOWN)
        fresh = sum(1 for lemma in words if lemma not in marked)
        return Coverage(known=known / len(words), fresh=fresh, total=len(words))


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
    return Index(words=words, texts=texts)


def build_index(found: dict[str, list[str]]) -> Index:
    """Turn a map of entry id to its dictionary forms into the shared-table shape."""
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
    return Index(words=tuple(table), texts=texts)


def write_index(path: Path, index: Index) -> None:
    """Write the index where `read_index` will find it."""
    write_atomic(
        path,
        json.dumps(
            {
                "version": INDEX_VERSION,
                "words": list(index.words),
                "texts": {entry_id: list(at) for entry_id, at in sorted(index.texts.items())},
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
# Running words rather than distinct ones. "You knew about 7 words in 10 of what you
# read" is a claim about the page as it was read, where the commonest words come round
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
#: two months make a slope out of anything.
POINTS = 3

#: Under this many running words a month is a guess and not a point — the same floor
#: `level.known_share` keeps (its `MEASURABLE`), for the same reason.
MEASURABLE = 20


def by_month(rows: list[dict[str, int | str]]) -> list[dict[str, int | str]]:
    """The reading rows of one language, a point a month, oldest first.

    Each point is the month's running words added up and the known ones among them — so
    a long chapter counts for more than a short one, as it did on the page — and how many
    sections are behind it. Months are UTC, which is what `at` is. A month under
    `MEASURABLE` words is left out.
    """
    from datetime import UTC, datetime

    months: dict[str, dict[str, int | str]] = {}
    for row in rows:
        at = int(row.get("at") or 0)
        tokens = int(row.get("tokens") or 0)
        if at <= 0 or tokens <= 0:
            continue
        month = datetime.fromtimestamp(at / 1000, tz=UTC).strftime("%Y-%m")
        point = months.setdefault(month, {"month": month, "tokens": 0, "known": 0, "sections": 0})
        point["tokens"] = int(point["tokens"]) + tokens
        point["known"] = int(point["known"]) + int(row.get("known") or 0)
        point["sections"] = int(point["sections"]) + 1
    return [months[m] for m in sorted(months) if int(months[m]["tokens"]) >= MEASURABLE]


def monthly(rows: list[dict[str, int | str]]) -> list[dict[str, int | str]]:
    """`by_month`, as a line: nothing under `POINTS` points, so the caller says what is
    missing rather than drawing a slope out of two."""
    points = by_month(rows)
    return points if len(points) >= POINTS else []
