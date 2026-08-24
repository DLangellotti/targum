"""Paying for a book a chapter at a time.

targum used to translate a whole text before anyone read a word of it, which assumes the
reader finishes what they open. Most people do not finish books, and a 97k-word novel is
$7.58 against $0.38 a chapter. These are the properties that make chapter-at-a-time work:
partial payment survives, and what one person paid for is reused only where the text is
public.
"""

from __future__ import annotations

from pathlib import Path

from targum.cache import Cache
from targum.models import BlockKind, Segment, SegmentedDocument, Style
from targum.pipeline import Build


def text(count: int, start: int = 0) -> SegmentedDocument:
    return SegmentedDocument(
        document_hash="book",
        language="he",
        segmenter="t/1",
        segments=[
            Segment(
                id=f"{n:04d}",
                block_id="b",
                block_index=0,
                index=n,
                text=f"שורה {n}",
                kind=BlockKind.paragraph,
            )
            for n in range(start, start + count)
        ],
    )


class Counting:
    """A provider that says how much it was asked to translate."""

    name = "counting"
    needs_key = False

    def __init__(self) -> None:
        self.asked: list[int] = []

    def available(self) -> tuple[bool, str]:
        return True, "counting"

    def translate(self, segments, source, target, style, on_progress=None):  # type: ignore[no-untyped-def]
        self.asked.append(len(segments))
        return {s.id: f"translated {s.text}" for s in segments}


def builder(tmp_path: Path, source: str, provider: Counting, owner: str = "") -> Build:
    """One build, with its own output directory and the machine's shared cache.

    The output directory is per person, the way homes are on a real box — sharing one
    would let a second person read the first one's `translation.json` off disk and never
    reach the cache at all, which is the thing being tested.
    """
    home = tmp_path / "out" / (owner or "local")
    made = Build(
        source,
        target_language="en",
        style=Style.natural,
        out_root=home,
        owner=owner,
        difficulty=False,
        gloss=False,
    )
    made.provider = provider  # type: ignore[assignment]
    made.provider_name = "counting"
    made.cache = Cache(tmp_path / "cache")
    made._resolved_out = home / "book"
    made._resolved_out.mkdir(parents=True, exist_ok=True)
    return made


def test_a_chapter_is_paid_for_once(tmp_path: Path) -> None:
    book = text(60)
    chapters = [book.segments[0:20], book.segments[20:40], book.segments[40:60]]
    provider = Counting()
    build = builder(tmp_path, "gutenberg:1342", provider)

    build.translate(book, only=chapters[0])
    assert provider.asked == [20], "the first chapter, and nothing else"

    build.translate(book, only=chapters[1])
    assert provider.asked == [20, 20], "the second, without redoing the first"

    # Reaching for the first again costs nothing.
    build.translate(book, only=chapters[0])
    assert provider.asked == [20, 20], "a chapter already paid for is not paid for twice"


def test_a_book_stopped_partway_keeps_what_it_paid_for(tmp_path: Path) -> None:
    """Keyed on the whole document, as it was, this cached under a key nothing would
    ever ask for again — the money was simply gone."""
    book = text(60)
    first = Counting()
    builder(tmp_path, "gutenberg:1342", first).translate(book, only=book.segments[0:20])
    assert first.asked == [20]

    # A different sitting, a different build, the same cache.
    second = Counting()
    builder(tmp_path, "gutenberg:1342", second).translate(book, only=book.segments[0:20])
    assert second.asked == [], "the chapter was already bought"


def test_the_second_reader_of_a_public_book_pays_nothing(tmp_path: Path) -> None:
    """One cache per machine, so a novel is bought once between every subscriber."""
    book = text(20)
    alice = Counting()
    builder(tmp_path, "gutenberg:1342", alice, owner="p1").translate(book)
    assert alice.asked == [20]

    bob = Counting()
    builder(tmp_path, "gutenberg:1342", bob, owner="p2").translate(book)
    assert bob.asked == [], "the same public text should not be paid for twice"


def test_one_persons_upload_is_never_served_to_another(tmp_path: Path) -> None:
    """A7. Not a leak — the second person had to have the identical file — but it is
    targum storing a translation of somebody's text and handing it to someone else, and
    the answer is that it does not."""
    book = text(20)
    alice = Counting()
    builder(tmp_path, "/uploads/abc/book.epub", alice, owner="p1").translate(book)
    assert alice.asked == [20]

    bob = Counting()
    builder(tmp_path, "/uploads/xyz/book.epub", bob, owner="p2").translate(book)
    assert bob.asked == [20], "an upload must be paid for again by a different person"

    # The same person, though, keeps their own work.
    again = Counting()
    builder(tmp_path, "/uploads/abc/book.epub", again, owner="p1").translate(book)
    assert again.asked == []


def test_which_sources_count_as_public(tmp_path: Path) -> None:
    provider = Counting()
    for source, shared in (
        ("gutenberg:1342", True),
        ("wikisource:he:x", True),
        ("https://example.com/a", True),
        ("http://example.com/a", True),
        ("catalogue:il-declaration", True),
        ("/uploads/abc/mine.epub", False),
        ("book.epub", False),
    ):
        assert builder(tmp_path, source, provider).shared_source() is shared, source
