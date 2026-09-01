"""One day's learning, cut out of the texts already on the shelf.

The same trick `parasha/cut.py` plays, and for the same reason: the books and the
tractates are in the library as built texts — pointed Hebrew, a published translation
beside it, every word annotated, all of it keyed by segment id — so a day's reading is a
range inside one of them, and carrying the ids across brings the other three artifacts
with it, exactly aligned and for nothing. Nothing here fetches or translates anything.

Three differences from the portion.

**A day is a range, not seven of them.** The portion's sections are its aliyot; a day has
none, so the sections are the chapters it touches. One or two, usually.

**The range comes in three shapes.** `Kelim 28:2-3` is verses inside a chapter, `Isaiah
55` is a whole chapter, `Psalms 90-96` is a run of them. `cycles.Span` carries all three
and a verse of `None` means "the whole chapter", which is what makes them one code path.

**A day can cross from one text into the next.** `Kelim 30:4-Oholot 1:1` is the last
mishnah of one tractate and the first of the next, and it happens once at every tractate
boundary — sixty-two times a cycle. It is the analogue of a doubled portion and it is
handled the same way: both texts are loaded and the two pieces are joined in order.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..catalogue import Entry, everything
from ..ids import slug
from ..ingest.fetch.sefaria import hebrew_numeral
from ..models import Block, BlockKind, Segment
from ..parasha.cut import Book, MissingBook, Portion, assemble, book_in, library_root
from .calendar import Day
from .cycles import Span

#: What Hebcal calls a text against what the catalogue calls it. Only where they differ:
#: everything else matches on the entry's own English name, which is Sefaria's, which is
#: Hebcal's. Avot is the one tractate Sefaria files under a name of its own, and it is
#: the same exception `sefaria.is_mishnah` carries.
ALIASES = {"Avot": "Pirkei Avot", "Pirkei Avot": "Pirkei Avot"}

#: The trailing `28:2` of a segment's ref. The book's name is in front of it and is not
#: read: which text this is was decided by which folder was opened, and a ref like
#: `Mishnah Kelim 28:2` would otherwise have to be matched against a name Hebcal writes
#: as `Kelim`.
_PLACE = re.compile(r"(\d+):(\d+)\s*$")


def _by_name() -> dict[str, Entry]:
    """Every text on the shelf, by the name a cycle would call it."""
    out: dict[str, Entry] = {}
    for entry in everything():
        if entry.english:
            out.setdefault(entry.english, entry)
    return out


def entry_for(name: str) -> Entry | None:
    """The catalogue entry a cycle's book name points at, or None."""
    return _by_name().get(ALIASES.get(name, name))


def folder_for(entry: Entry, root: Path | None = None) -> Path:
    return (root or library_root()) / f"{slug(entry.title)}-he"


def load(entry: Entry, root: Path | None = None) -> Book:
    """Everything the library holds for one text, or a plain answer that it holds none."""
    return book_in(entry.english or entry.title, folder_for(entry, root))


def place_of(segment: Segment) -> tuple[int, int] | None:
    """`Mishnah Kelim 28:2` -> (28, 2). None where the segment carries no ref."""
    found = _PLACE.search(segment.ref or "")
    return (int(found.group(1)), int(found.group(2))) if found else None


def within(
    place: tuple[int, int], first: int, first_verse: int | None, last: int, last_verse: int | None
) -> bool:
    """Whether a chapter and verse fall inside the range, with `None` meaning the whole
    chapter — which is how a cycle that reads chapters at a time says so."""
    chapter, verse = place
    if chapter < first or chapter > last:
        return False
    if chapter == first and first_verse is not None and verse < first_verse:
        return False
    if chapter == last and last_verse is not None and verse > last_verse:
        return False
    return True


def pieces(span: Span) -> list[tuple[str, int, int | None, int, int | None]]:
    """The span as one range per text it touches.

    A day inside one text is one piece. A day that crosses into the next is two: the
    first runs from where it begins to the end of its text, and the second from the
    beginning of its text to where the day ends. `None` for a bound is "no bound", which
    is exactly what running to the end of a book means.
    """
    if not span.crosses:
        return [(span.book, span.chapter, span.verse, span.chapter2, span.verse2)]
    return [
        (span.book, span.chapter, span.verse, 10**6, None),
        (span.book2, 0, None, span.chapter2, span.verse2),
    ]


def cut(day: Day, root: Path | None = None) -> Portion:
    """One day's reading, as a document of its own.

    Raises rather than returning a short one: a page under today's date showing half of
    what is meant to be read is worse than a page saying it cannot show it.
    """
    if day.span is None:
        raise MissingBook(day.reference, root or library_root())

    blocks: list[Block] = []
    segments: list[Segment] = []
    books: dict[str, Book] = {}
    seen_chapters: set[tuple[str, int]] = set()

    for name, first, first_verse, last, last_verse in pieces(day.span):
        entry = entry_for(name)
        if entry is None:
            raise MissingBook(name, root or library_root())
        book = books.get(name) or load(entry, root)
        books[name] = book
        for segment in book.segmented.segments:
            if segment.kind is BlockKind.heading:
                continue
            place = place_of(segment)
            if place is None or not within(place, first, first_verse, last, last_verse):
                continue
            # A chapter heading in front of each chapter the day touches. Level 2, so
            # `render.split_sections` makes it a section — a day is small enough that its
            # chapters are the only division it has.
            if (name, place[0]) not in seen_chapters:
                seen_chapters.add((name, place[0]))
                named = book.document.title or name
                head_id = f"day-{slug(name)}-{place[0]:04d}"
                # In Hebrew numerals where the heading is Hebrew. A Latin digit inside a
                # Hebrew line is the bidi mess `isolate()` exists to paper over, and the
                # book this was cut out of numbers its own chapters the same way.
                number = (
                    hebrew_numeral(place[0])
                    if book.document.language.startswith("he")
                    else str(place[0])
                )
                label = f"{named} {number}"
                blocks.append(
                    Block(id=head_id, kind=BlockKind.heading, level=2, text=label, ref="")
                )
                segments.append(
                    Segment(
                        id=head_id,
                        block_id=head_id,
                        block_index=len(blocks) - 1,
                        index=0,
                        kind=BlockKind.heading,
                        level=2,
                        text=label,
                        ref="",
                    )
                )
            blocks.append(
                Block(
                    id=segment.block_id,
                    kind=segment.kind,
                    level=segment.level,
                    text=segment.text,
                    ref=segment.ref,
                )
            )
            segments.append(
                Segment(
                    id=segment.id,
                    block_id=segment.block_id,
                    block_index=len(blocks) - 1,
                    index=segment.index,
                    kind=segment.kind,
                    level=segment.level,
                    text=segment.text,
                    ref=segment.ref,
                )
            )

    if not segments:
        raise MissingBook(day.reference, root or library_root())
    opening = books[next(iter(books))]
    return assemble(
        blocks,
        segments,
        books,
        opening,
        # The same claim the portion makes, and for the same reasons: a day of Mishna
        # Yomi is a verse-numbered text and is drawn as one.
        source=f"sefaria:{day.reference}",
        title=day.hebrew or day.title,
        name=day.title,
        ingester="daily/1",
    )
