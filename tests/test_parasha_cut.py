"""Cutting a reading out of the books, and what the corpus does with it.

The books are built with a handful of real verses rather than the whole Torah: the
question here is whether a verse range comes out as the right verses with the right
things hanging off them, and that does not need Genesis to be 1,533 segments long.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from targum.models import (
    Annotation,
    Block,
    BlockKind,
    Document,
    Glossary,
    Segment,
    SegmentedDocument,
    Token,
    Translation,
    Vocalization,
)
from targum.parasha import calendar as cal
from targum.parasha import cut as cutmod
from targum.parasha.models import Index, Portion
from targum.vocalize import has_taamim

FIXTURES = Path(__file__).parent / "fixtures" / "parasha"

# A pointed and accented verse, so the tests assert against real Masoretic text rather
# than something shaped like it.
ACCENTED = "אַתֶּ֨ם נִצָּבִ֤ים הַיּוֹם֙ כֻּלְּכֶ֔ם"

# Every verse gets one of these in front, so no two verses of the fixture are the same
# string. A book whose verses are all identical hides exactly the bugs the hero's column
# can have — a line repeated, or the wrong line taken.
OPENERS = ("וַיְהִ֗י", "בִּימֵי֙", "שְׁפֹ֣ט", "הַשֹּׁפְטִ֔ים", "וַיְהִ֥י", "רָעָ֖ב", "בָּאָ֑רֶץ")


def verse_text(chapter: int, verse: int) -> str:
    return f"{OPENERS[(chapter * 7 + verse) % len(OPENERS)]} {ACCENTED}"


def a_book(folder: Path, name: str, hebrew: str, chapters: dict[int, int]) -> None:
    """A built book with `chapters` mapping chapter number to how many verses it has."""
    blocks: list[Block] = []
    segments: list[Segment] = []
    pointed: dict[str, str] = {}
    english: dict[str, str] = {}
    tokens: dict[str, list[Token]] = {}
    for chapter, count in sorted(chapters.items()):
        head = f"h{chapter}"
        blocks.append(Block(id=head, kind=BlockKind.heading, level=2, text=f"{hebrew} {chapter}"))
        segments.append(
            Segment(
                id=head,
                block_id=head,
                block_index=len(blocks) - 1,
                index=0,
                kind=BlockKind.heading,
                level=2,
                text=f"{hebrew} {chapter}",
            )
        )
        for verse in range(1, count + 1):
            sid = f"{name}-{chapter:02d}-{verse:02d}"
            ref = f"{name} {chapter}:{verse}"
            text = verse_text(chapter, verse)
            blocks.append(Block(id=sid, kind=BlockKind.verse, text=text, ref=ref))
            segments.append(
                Segment(
                    id=sid,
                    block_id=sid,
                    block_index=len(blocks) - 1,
                    index=0,
                    kind=BlockKind.verse,
                    text=text,
                    ref=ref,
                )
            )
            pointed[sid] = text
            english[sid] = f"{name} {chapter} verse {verse}"
            tokens[sid] = [Token(start=0, end=5, surface="אַתֶּ֨ם", lemma="אתם", band=2)]

    document = Document(source=f"sefaria:{name}", title=hebrew, language="he", blocks=blocks)
    document.content_hash = document.recompute_hash()
    folder.mkdir(parents=True, exist_ok=True)
    document.write(folder / "document.json")
    SegmentedDocument(
        document_hash=document.content_hash,
        language="he",
        segmenter="test/1",
        segments=segments,
    ).write(folder / "segments.json")
    (folder / "translations").mkdir(exist_ok=True)
    Translation(
        name=name,
        document_hash=document.content_hash,
        source_language="he",
        target_language="en",
        provider="aligned",
        segments=english,
    ).write(folder / "translations" / f"aligned.{name.lower()}.en.json")
    Annotation(
        document_hash=document.content_hash,
        language="he",
        annotator="test/1",
        method="curated:tanakh",
        method_note="",
        tokens=tokens,
    ).write(folder / "annotation.json")
    Vocalization(
        document_hash=document.content_hash,
        language="he",
        vocalizer="source",
        segments=pointed,
    ).write(folder / "vocalization.json")
    Glossary(
        source_language="he",
        target_language="en",
        provider="test",
        entries={"אתם": "you"},
    ).write(folder / "glossary.en.json")


@pytest.fixture
def library(tmp_path: Path) -> Path:
    root = tmp_path / "library"
    a_book(root / "דברים-he", "Deuteronomy", "דברים", {29: 29, 30: 20, 31: 30})
    return root


@pytest.fixture
def corpus(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TARGUM_PARASHA_DIR", str(tmp_path / "parasha"))
    (tmp_path / "parasha" / "calendar").mkdir(parents=True)
    for one in FIXTURES.glob("*.json"):
        shutil.copy(one, tmp_path / "parasha" / "calendar" / one.name)
    return tmp_path / "parasha"


def a_reading(corpus: Path) -> cal.Reading:
    from datetime import date

    reading = cal.for_shabbat(date(2026, 9, 5), cal.Schedule.diaspora)
    assert reading is not None
    return reading


def test_refs_parse_into_book_chapter_and_verse() -> None:
    assert cutmod.parse_ref("Genesis 1:1") == ("Genesis", cutmod.Verse(1, 1))
    assert cutmod.parse_ref("I Samuel 3:4") == ("I Samuel", cutmod.Verse(3, 4))
    assert cutmod.parse_ref("Genesis 1") is None
    assert cutmod.parse_ref("") is None


def test_verses_sort_by_chapter_then_verse() -> None:
    assert cutmod.Verse(1, 2) < cutmod.Verse(2, 1)
    assert cutmod.Verse(2, 9) < cutmod.Verse(2, 10)
    assert cutmod.Verse(3, 1) <= cutmod.Verse(3, 1)


def test_the_cut_takes_exactly_the_verses_the_aliyot_name(corpus: Path, library: Path) -> None:
    reading = a_reading(corpus)
    portion = cutmod.cut(reading, cutmod.books_for(reading, library))
    assert portion.verses == sum(one.verses for one in reading.aliyot)
    refs = [s.ref for s in portion.segmented.segments if s.kind is BlockKind.verse]
    assert refs[0] == "Deuteronomy 29:9"
    assert refs[-1] == "Deuteronomy 31:30"
    assert len(refs) == len(set(refs)), "no verse is read twice"


def test_each_aliyah_becomes_a_section(corpus: Path, library: Path) -> None:
    """`split_sections` breaks at a level-2 heading, so the seven aliyot are the seven
    sections a reader can jump between."""
    from targum.render import split_sections

    reading = a_reading(corpus)
    portion = cutmod.cut(reading, cutmod.books_for(reading, library))
    sections = split_sections(portion.segmented)
    assert [one.title for one in sections] == list(cutmod.ALIYOT)


def test_a_chapter_turning_is_a_line_not_a_section(corpus: Path, library: Path) -> None:
    """It says a chapter changed without also cutting the page in half."""
    reading = a_reading(corpus)
    portion = cutmod.cut(reading, cutmod.books_for(reading, library))
    chapters = [b for b in portion.document.blocks if b.kind is BlockKind.heading and b.level == 3]
    assert chapters, "a reading spanning three chapters should say where they turn"
    assert all(one.level == 3 for one in chapters)


def test_everything_keyed_to_a_segment_comes_with_it(corpus: Path, library: Path) -> None:
    """Ids are carried across from the book, which is what makes the translation, the
    annotation and the vowels arrive already aligned and free."""
    reading = a_reading(corpus)
    portion = cutmod.cut(reading, cutmod.books_for(reading, library))
    verses = {s.id for s in portion.segmented.segments if s.kind is BlockKind.verse}
    assert portion.translations[0].segments.keys() == verses
    assert portion.annotation is not None
    assert portion.annotation.tokens.keys() == verses
    assert portion.vocalization is not None
    assert portion.vocalization.segments.keys() == verses
    assert portion.glossaries["en"].entries


def test_the_portion_declares_itself_scripture(corpus: Path, library: Path) -> None:
    """`is_biblical` reads the source, and it decides the face the page carries and that
    a verse is a row rather than a paragraph."""
    from targum.models import is_biblical

    reading = a_reading(corpus)
    portion = cutmod.cut(reading, cutmod.books_for(reading, library))
    assert is_biblical(portion.document.source)
    assert portion.document.title == reading.hebrew


def test_the_opening_words_are_the_first_verse(corpus: Path, library: Path) -> None:
    reading = a_reading(corpus)
    portion = cutmod.cut(reading, cutmod.books_for(reading, library))
    opening, ref = portion.opening()
    assert ref == "Deuteronomy 29:9"
    assert has_taamim(opening), "the hero sets the accents, so they have to survive"
    assert len(opening.split()) == 4


def test_a_book_that_is_not_built_is_named(corpus: Path, tmp_path: Path) -> None:
    reading = a_reading(corpus)
    with pytest.raises(cutmod.MissingBook) as gone:
        cutmod.books_for(reading, tmp_path / "empty")
    assert gone.value.book == "Deuteronomy"


# -- what the library lists --------------------------------------------------


def one(slug: str, numbers: list[int], kind: cal.ReadingKind = cal.ReadingKind.parasha) -> Portion:
    return Portion(slug=slug, name=slug, hebrew=slug, kind=kind, numbers=numbers, summary="x")


def test_the_shelf_shows_the_cycle_once() -> None:
    index = Index(portions={"a": one("a", [1]), "b": one("b", [2])})
    assert [p.slug for p in index.listed()] == ["a", "b"]


def test_a_doubled_week_is_hidden_where_its_halves_are_on_the_shelf() -> None:
    """Otherwise the same chapters are on the shelf three times."""
    index = Index(
        portions={
            "a": one("a", [1]),
            "b": one("b", [2]),
            "a-b": one("a-b", [1, 2]),
        }
    )
    assert [p.slug for p in index.listed()] == ["a", "b"]


def test_a_doubled_week_is_shown_where_neither_half_is() -> None:
    """Matot and Masei come apart about once a decade, so a corpus built from the next
    two years has neither — and without this the shelf would be missing the end of
    Numbers entirely."""
    index = Index(portions={"a-b": one("a-b", [1, 2]), "c": one("c", [3])})
    assert [p.slug for p in index.listed()] == ["a-b", "c"]


def test_a_festival_belongs_to_a_date_rather_than_to_the_shelf() -> None:
    index = Index(
        portions={
            "a": one("a", [1]),
            "pesach": one("pesach", [], cal.ReadingKind.festival),
        }
    )
    assert [p.slug for p in index.listed()] == ["a"]


def test_the_pointer_answers_per_schedule() -> None:
    from targum.parasha.models import Week

    index = Index(
        portions={"a": one("a", [1]), "b": one("b", [2])},
        weeks=[
            Week(day="2026-05-30", schedule=cal.Schedule.diaspora, slug="a"),
            Week(day="2026-05-30", schedule=cal.Schedule.israel, slug="b"),
        ],
    )
    assert index.on("2026-05-30", cal.Schedule.diaspora) is not None
    assert index.on("2026-05-30", cal.Schedule.diaspora).slug == "a"
    assert index.on("2026-05-30", cal.Schedule.israel).slug == "b"
    assert index.on("2026-06-06", cal.Schedule.diaspora) is None


def test_catalogue_entries_are_shaped_like_the_shelf(corpus: Path) -> None:
    """They go into the reader's own catalogue file, so they have to read like the
    entries already in it."""
    from targum.parasha import build as corpus_build

    index = Index(portions={"bereshit": one("bereshit", [1])})
    entries = corpus_build.entries(index)
    assert len(entries) == 1
    entry = entries[0]
    assert entry["id"] == "parasha-bereshit"
    assert entry["tags"] == ["tanakh"]
    assert entry["register"] == "biblical"
    assert entry["language"] == "he"
    assert str(entry["source"]).startswith("sefaria:")
    # Every key the catalogue reader needs, so a merged entry is not half an entry.
    assert {"id", "title", "author", "language", "source", "blurb", "kind"} <= set(entry)
