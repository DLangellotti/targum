"""One reading, cut out of the books already on the shelf.

Nothing here fetches or translates anything. The five books of the Torah are in the
library as built texts — Hebrew with its vowels and accents, a published translation
beside it, every word annotated, all of it keyed by segment id — and a portion is a
range of verses inside one of them. So a portion is that range, carried across with the
four artifacts that hang off it, and the only thing invented is the headings.

**The seven, as sections.** The aliyot are what the reading is divided into, so they are
what the reader's sections are: `render.split_sections` breaks at a level-2 heading, and
one goes in front of each. The chapter headings the book came with drop to level 3, where
they still say a chapter turned without also cutting the page. That way "ראשון" is a
section a reader can jump to and "בראשית ב׳" is a line inside it, which is the way the
reading is actually referred to.

**Ids are kept.** A segment brings its id from the book it came out of, because the
translation, the annotation and the vocalization are all keyed by it and carrying the id
across is what makes them come too, for free and exactly aligned. The headings are the
only new ids, and they are named for the aliyah so they cannot collide with a book's.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..models import (
    Annotation,
    Block,
    BlockKind,
    Document,
    Glossary,
    Segment,
    SegmentedDocument,
    Translation,
    Vocalization,
    glossaries_in,
    read_artifact,
)
from .calendar import Reading

#: What each aliyah is called, in order. The seventh is the last on an ordinary Shabbat;
#: a festival reading can be shorter, and then the names simply run out where it stops.
ALIYOT = ("ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שביעי")

#: The Hebrew title each book is filed under in the library, by the English name Hebcal
#: uses. The library is keyed by the Hebrew title — the build folder is `בראשית-he` —
#: and Hebcal says "Genesis", so something has to hold the two together.
BOOKS = {
    "Genesis": "בראשית",
    "Exodus": "שמות",
    "Leviticus": "ויקרא",
    "Numbers": "במדבר",
    "Deuteronomy": "דברים",
}

_REF = re.compile(r"^(?P<book>.+?)\s+(?P<chapter>\d+):(?P<verse>\d+)$")


class MissingBook(Exception):
    """A book the reading needs is not built in the library."""

    def __init__(self, book: str, looked_in: Path) -> None:
        super().__init__(book)
        self.book = book
        self.looked_in = looked_in


@dataclass(frozen=True, slots=True)
class Verse:
    """A chapter and verse, as a pair that sorts."""

    chapter: int
    verse: int

    def __le__(self, other: Verse) -> bool:
        return (self.chapter, self.verse) <= (other.chapter, other.verse)

    def __lt__(self, other: Verse) -> bool:
        return (self.chapter, self.verse) < (other.chapter, other.verse)


def parse_ref(ref: str) -> tuple[str, Verse] | None:
    """ "Genesis 1:1" as its book and its place in it.

    Refs are written in English whatever the text's language — `ingest/fetch/sefaria.py`
    puts them there — so this parses the English and the caller matches it against
    Hebcal's English, which is the one thing the two agree on.
    """
    found = _REF.match(ref.strip())
    if not found:
        return None
    return found["book"], Verse(int(found["chapter"]), int(found["verse"]))


def parse_place(place: str) -> Verse | None:
    """Hebcal's "29:9" as a verse."""
    parts = place.strip().split(":")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        return None
    return Verse(int(parts[0]), int(parts[1]))


@dataclass(slots=True)
class Book:
    """One book of the Torah, as it sits in the library."""

    name: str
    folder: Path
    document: Document
    segmented: SegmentedDocument
    translations: list[Translation]
    annotation: Annotation | None
    vocalization: Vocalization | None
    glossaries: dict[str, Glossary]


def library_root() -> Path:
    """Where the built books are. The same default the pipeline writes to."""
    return Path.cwd() / "targum-out" / "library"


def load_book(name: str, root: Path | None = None) -> Book:
    """Everything the library holds for one book of the Torah."""
    root = root or library_root()
    hebrew = BOOKS.get(name)
    if hebrew is None:
        raise MissingBook(name, root)
    return book_in(name, root / f"{hebrew}-he")


def book_in(name: str, folder: Path) -> Book:
    """One built text, read off the disk. Shared with `daily/cut.py`, which finds its
    folder a different way — off the catalogue rather than off a table of five books —
    and wants everything after that to be the same."""
    document = read_artifact(Document, folder / "document.json")
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    if document is None or segmented is None:
        raise MissingBook(name, folder)
    translations = []
    for path in sorted((folder / "translations").glob("*.json")):
        one = read_artifact(Translation, path)
        if one is not None:
            translations.append(one)
    if not translations:
        raise MissingBook(name, folder / "translations")
    return Book(
        name=name,
        folder=folder,
        document=document,
        segmented=segmented,
        translations=translations,
        annotation=read_artifact(Annotation, folder / "annotation.json"),
        vocalization=read_artifact(Vocalization, folder / "vocalization.json"),
        glossaries=glossaries_in(folder),
    )


@dataclass(slots=True)
class Portion:
    """One reading, ready to render."""

    #: The Shabbat reading this came out of, where it is one. A day of a learning cycle
    #: is cut the same way and has no portion behind it.
    reading: Reading | None
    document: Document
    segmented: SegmentedDocument
    translations: list[Translation]
    annotation: Annotation | None
    vocalization: Vocalization | None
    glossaries: dict[str, Glossary]

    @property
    def verses(self) -> int:
        return sum(1 for s in self.segmented.segments if s.kind is BlockKind.verse)

    def opening(self, words: int = 4) -> tuple[str, str]:
        """The first few words of the reading, and where they are.

        A portion is named for its opening words — בְּרֵאשִׁית, וַיֵּרָא, דְּבָרִים —
        so these are the one thing that can stand at the top of the page as an image of
        what this week is without being a picture of anything.
        """
        for segment in self.segmented.segments:
            if segment.kind is not BlockKind.verse:
                continue
            return " ".join(segment.text.split()[:words]), segment.ref
        return "", ""


def _within(segment: Segment, book: str, first: Verse, last: Verse) -> bool:
    parsed = parse_ref(segment.ref)
    if parsed is None:
        return False
    where, place = parsed
    return where == book and first <= place <= last


def cut(reading: Reading, books: dict[str, Book]) -> Portion:
    """The reading, as a document of its own.

    The aliyot are walked in order and each contributes a heading and the verses in its
    range. A verse that two aliyot both claim — which happens where an aliyah begins
    mid-verse in some traditions — is taken by the first, so no verse is ever read twice.
    """
    blocks: list[Block] = []
    segments: list[Segment] = []
    taken: set[str] = set()
    seen_chapters: set[tuple[str, int]] = set()

    for aliyah in reading.aliyot:
        book = books.get(aliyah.book)
        if book is None:
            raise MissingBook(aliyah.book, library_root())
        first, last = parse_place(aliyah.begin), parse_place(aliyah.end)
        if first is None or last is None:
            continue

        name = ALIYOT[aliyah.number - 1] if aliyah.number <= len(ALIYOT) else str(aliyah.number)
        head_id = f"aliyah-{aliyah.number:02d}"
        blocks.append(
            Block(
                id=head_id,
                kind=BlockKind.heading,
                level=2,
                text=name,
                ref="",
            )
        )
        segments.append(
            Segment(
                id=head_id,
                block_id=head_id,
                block_index=len(blocks) - 1,
                index=0,
                kind=BlockKind.heading,
                level=2,
                text=name,
                ref="",
            )
        )

        for segment in book.segmented.segments:
            if segment.id in taken:
                continue
            if segment.kind is BlockKind.heading:
                continue
            if not _within(segment, aliyah.book, first, last):
                continue
            parsed = parse_ref(segment.ref)
            # Where a chapter turns inside the reading, say so — but at level 3, so the
            # aliyah above stays the section and this is a line inside it.
            if parsed is not None and (aliyah.book, parsed[1].chapter) not in seen_chapters:
                seen_chapters.add((aliyah.book, parsed[1].chapter))
                if parsed[1].verse != 1 or len(seen_chapters) > 1:
                    chapter_id = f"chapter-{aliyah.book[:3].lower()}-{parsed[1].chapter:03d}"
                    named = books[aliyah.book].document.title or aliyah.book
                    label = f"{named} {parsed[1].chapter}"
                    blocks.append(
                        Block(id=chapter_id, kind=BlockKind.heading, level=3, text=label, ref="")
                    )
                    segments.append(
                        Segment(
                            id=chapter_id,
                            block_id=chapter_id,
                            block_index=len(blocks) - 1,
                            index=0,
                            kind=BlockKind.heading,
                            level=3,
                            text=label,
                            ref="",
                        )
                    )
            taken.add(segment.id)
            blocks.append(
                Block(
                    id=segment.block_id,
                    kind=segment.kind,
                    level=segment.level,
                    text=segment.text,
                    ref=segment.ref,
                    language=segment.language,
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
                    language=segment.language,
                )
            )

    first_book = books[reading.aliyot[0].book] if reading.aliyot else next(iter(books.values()))
    return assemble(
        blocks,
        segments,
        books,
        first_book,
        # `sefaria:` is what `is_biblical` reads, and it decides the face the page carries
        # and that a verse is a row rather than a paragraph. A portion is scripture; it
        # says so.
        source=f"sefaria:{reading.summary or reading.name}",
        title=reading.hebrew or reading.name,
        name=reading.name,
        ingester="parasha/1",
        reading=reading,
    )


def assemble(
    blocks: list[Block],
    segments: list[Segment],
    books: dict[str, Book],
    first_book: Book,
    *,
    source: str,
    title: str,
    name: str,
    ingester: str,
    reading: Reading | None = None,
) -> Portion:
    """A cut run of segments, with the four artifacts that hang off it carried across.

    Shared with `daily/cut.py`. What differs between a portion and a day is which
    segments are taken and what the result is called; everything after that — the
    document, the translations narrowed to what was kept, the annotation, the vowels and
    the glossaries — is the same work, and was the same work written twice until this.
    """
    document = Document(
        source=source,
        title=title,
        author=first_book.document.author,
        language=first_book.document.language,
        blocks=blocks,
        ingester=ingester,
    )
    document.content_hash = document.recompute_hash()
    segmented = SegmentedDocument(
        document_hash=document.content_hash,
        language=first_book.segmented.language,
        segmenter=first_book.segmented.segmenter,
        segments=segments,
    )

    kept = {segment.id for segment in segments}
    return Portion(
        reading=reading,
        document=document,
        segmented=segmented,
        translations=_translations(name, books, kept, document.content_hash),
        annotation=_annotation(books, kept, document.content_hash),
        vocalization=_vocalization(books, kept, document.content_hash),
        glossaries=_glossaries(books),
    )


def _translations(
    name: str, books: dict[str, Book], kept: set[str], document_hash: str
) -> list[Translation]:
    """One translation per language, carrying only the segments this portion holds."""
    by_language: dict[str, Translation] = {}
    for book in books.values():
        for one in book.translations:
            merged = by_language.get(one.target_language)
            if merged is None:
                merged = one.model_copy(
                    update={
                        "name": name,
                        "document_hash": document_hash,
                        "segments": {},
                        "coarse": [],
                        "confidence": {},
                    }
                )
                by_language[one.target_language] = merged
            merged.segments.update({k: v for k, v in one.segments.items() if k in kept})
            merged.coarse.extend([c for c in one.coarse if c in kept])
            merged.confidence.update({k: v for k, v in one.confidence.items() if k in kept})
    return list(by_language.values())


def _annotation(books: dict[str, Book], kept: set[str], document_hash: str) -> Annotation | None:
    source = next((b.annotation for b in books.values() if b.annotation is not None), None)
    if source is None:
        return None
    tokens = {}
    for book in books.values():
        if book.annotation is None:
            continue
        tokens.update({k: v for k, v in book.annotation.tokens.items() if k in kept})
    return source.model_copy(update={"document_hash": document_hash, "tokens": tokens})


def _vocalization(
    books: dict[str, Book], kept: set[str], document_hash: str
) -> Vocalization | None:
    source = next((b.vocalization for b in books.values() if b.vocalization is not None), None)
    if source is None:
        return None
    pointed: dict[str, str] = {}
    machine: list[str] = []
    for book in books.values():
        if book.vocalization is None:
            continue
        pointed.update({k: v for k, v in book.vocalization.segments.items() if k in kept})
        machine.extend([m for m in book.vocalization.machine if m in kept])
    return source.model_copy(
        update={"document_hash": document_hash, "segments": pointed, "machine": machine}
    )


def _glossaries(books: dict[str, Book]) -> dict[str, Glossary]:
    """Every meaning the books carry, merged. Cheap: a glossary is per lemma, not per
    text, and a portion's words are a subset of its book's."""
    out: dict[str, Glossary] = {}
    for book in books.values():
        for language, glossary in book.glossaries.items():
            merged = out.get(language)
            if merged is None:
                out[language] = glossary.model_copy(deep=True)
                continue
            merged.entries.update(glossary.entries)
            merged.parts_of_speech.update(glossary.parts_of_speech)
            merged.citations.update(glossary.citations)
            merged.plurals.update(glossary.plurals)
    return out


def books_for(reading: Reading, root: Path | None = None) -> dict[str, Book]:
    """Load every book one reading touches, once each."""
    return {name: load_book(name, root) for name in reading.books}
