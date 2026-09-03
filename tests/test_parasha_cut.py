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


# -- the shelf: the portions as one collection ---------------------------------


def test_the_portions_are_one_ordered_collection_in_cycle_order() -> None:
    """Fifty-four loose rows beside the `torah` collection is exactly the shape a
    collection exists to prevent, and the members run in the order of the year."""
    from targum.parasha import build as corpus_build

    index = Index(portions={"b": one("b", [2]), "a": one("a", [1]), "c": one("c", [3])})
    group = corpus_build.collection(index)
    assert group is not None
    assert group["id"] == "torah-portions"
    assert group["ordered"] is True
    assert group["members"] == ["parasha-a", "parasha-b", "parasha-c"]
    assert group["members"] == [f"parasha-{p.slug}" for p in index.listed()]
    assert {"id", "title", "english", "blurb", "members", "ordered"} <= set(group)


def test_a_doubled_week_stands_in_for_halves_nobody_built() -> None:
    """Matot and Masei come apart about once a decade; a corpus with neither has the
    doubled build on the shelf once, for both numbers."""
    from targum.parasha import build as corpus_build

    index = Index(portions={"a": one("a", [1]), "b-c": one("b-c", [2, 3]), "d": one("d", [4])})
    group = corpus_build.collection(index)
    assert group is not None
    assert group["members"] == ["parasha-a", "parasha-b-c", "parasha-d"]


def test_an_empty_corpus_has_no_collection() -> None:
    from targum.parasha import build as corpus_build

    assert corpus_build.collection(Index()) is None


def test_an_entry_is_filed_under_the_books_hebrew_title() -> None:
    """So a portion under its collection reads the way the book rows above it do."""
    from targum.parasha import build as corpus_build

    noach = Portion(
        slug="noach",
        name="Noach",
        hebrew="נֹחַ",
        numbers=[2],
        summary="Genesis 6:9-11:32",
        books=["Genesis"],
    )
    (entry,) = corpus_build.entries(Index(portions={"noach": noach}))
    assert entry["author"] == "בראשית"


def test_an_entry_carries_what_the_library_measures_it_by() -> None:
    """A row is drawn from the catalogue, and the catalogue is written from the index.
    A portion whose index says nothing reads on the shelf as a text with nothing in it —
    one minute long and nought per cent hard, which is how the fifty-four first landed
    there."""
    from targum.parasha import build as corpus_build

    noach = Portion(
        slug="noach",
        name="Noach",
        hebrew="נֹחַ",
        numbers=[2],
        summary="Genesis 6:9-11:32",
        books=["Genesis"],
        verses=153,
        aliyot=7,
        words=1861,
        difficulty=23,
    )
    (entry,) = corpus_build.entries(Index(portions={"noach": noach}))
    assert entry["words"] == 1861
    assert entry["difficulty"] == 23
    # Through the same parser the library draws its row with: 1,861 words is fourteen
    # minutes at the reader's 130 a minute, not the one minute nought words rounds to.
    from targum.catalogue import _entry

    row = _entry(entry)
    assert row.minutes == 14
    assert row.difficulty == 23


def test_a_blurb_counts_the_aliyot_the_reading_actually_has() -> None:
    """Seven for the fifty-four, eight where two portions are read as one — the number
    is in the index, so the sentence has no business hard-coding it."""
    from targum.parasha import build as corpus_build

    def blurb(aliyot: int) -> str:
        one = Portion(
            slug="x",
            name="X",
            hebrew="א",
            numbers=[1],
            summary="Genesis 1:1-2:3",
            books=["Genesis"],
            verses=34,
            aliyot=aliyot,
        )
        (entry,) = corpus_build.entries(Index(portions={"x": one}))
        return str(entry["blurb"])

    assert blurb(7).endswith("seven aliyot.")
    assert blurb(8).endswith("eight aliyot.")


# -- where each portion begins in its book ------------------------------------


def _start(slug: str, hebrew: str, number: int, ref: str, summary: str) -> Portion:
    book = ref.split(" ")[0]
    return Portion(
        slug=slug,
        name=slug,
        hebrew=hebrew,
        numbers=[number],
        summary=summary,
        books=[book],
        opening_ref=ref,
    )


def genesis_index() -> Index:
    """Three portions of Genesis, out of order, and the first of Exodus."""
    return Index(
        portions={
            "noach": _start("noach", "נֹחַ", 2, "Genesis 6:9", "Genesis 6:9-11:32"),
            "bereshit": _start("bereshit", "בְּרֵאשִׁית", 1, "Genesis 1:1", "Genesis 1:1-6:8"),
            "lech-lecha": _start("lech-lecha", "לֶךְ־לְךָ", 3, "Genesis 12:1", "Genesis 12:1-17:27"),
            "shemot": _start("shemot", "שְׁמוֹת", 13, "Exodus 1:1", "Exodus 1:1-6:1"),
        }
    )


def test_the_portions_of_a_book_come_in_reading_order_with_their_first_verse() -> None:
    from targum.parasha import build as corpus_build

    starts = corpus_build.portions_for("Genesis", genesis_index())
    assert [(s.slug, s.chapter, s.verse) for s in starts] == [
        ("bereshit", 1, 1),
        ("noach", 6, 9),
        ("lech-lecha", 12, 1),
    ]
    assert starts[1].hebrew == "נֹחַ"
    assert starts[1].summary == "Genesis 6:9-11:32"


def test_a_book_answers_to_any_of_its_three_names() -> None:
    """Hebcal's name, the shelf's Hebrew title, and the source the built book carries."""
    from targum.parasha import build as corpus_build

    index = genesis_index()
    by_english = corpus_build.portions_for("Genesis", index)
    assert len(by_english) == 3
    assert corpus_build.portions_for("בראשית", index) == by_english
    assert corpus_build.portions_for("sefaria:Genesis", index) == by_english


def test_a_book_with_no_portions_has_none(corpus: Path) -> None:
    """Ruth, and every one of the five on a machine with no corpus built."""
    from targum.parasha import build as corpus_build

    assert corpus_build.portions_for("Ruth", genesis_index()) == []
    assert corpus_build.portions_for("sefaria:Ruth", genesis_index()) == []
    assert corpus_build.portions_for("Genesis", Index()) == []
    # Off the disk, where the fixture corpus has no index written at all.
    assert corpus_build.portions_for("Genesis") == []


def test_a_portion_written_before_opening_ref_starts_where_its_range_line_says() -> None:
    from targum.parasha import build as corpus_build

    noach = Portion(
        slug="noach",
        name="Noach",
        hebrew="נֹחַ",
        numbers=[2],
        summary="Genesis 6:9-11:32",
        books=["Genesis"],
    )
    (start,) = corpus_build.portions_for("Genesis", Index(portions={"noach": noach}))
    assert (start.chapter, start.verse) == (6, 9)


# -- the portion before and the one after ------------------------------------


def test_the_year_wraps_from_the_last_portion_to_the_first() -> None:
    from targum.parasha.models import neighbours

    listed = [one("a", [1]), one("b", [2]), one("c", [3])]

    def around(portion: Portion) -> list[str | None]:
        return [p.slug if p else None for p in neighbours(portion, listed)]

    assert around(listed[1]) == ["a", "c"]
    assert around(listed[2]) == ["b", "a"], "after the last comes the first"
    assert around(listed[0]) == ["c", "b"]


def test_a_doubled_week_stands_between_the_portions_around_both_halves() -> None:
    from targum.parasha.models import neighbours

    listed = [one("a", [1]), one("b", [2]), one("c", [3]), one("d", [4])]
    doubled = one("b-c", [2, 3])
    assert [p.slug for p in neighbours(doubled, listed) if p] == ["a", "d"]
    # Where the halves are not built, the doubled build is on the shelf itself.
    shelf = [one("a", [1]), doubled, one("d", [4])]
    assert [p.slug for p in neighbours(listed[3], shelf) if p] == ["b-c", "a"]


def test_a_festival_has_no_place_in_the_cycle() -> None:
    from targum.parasha.models import neighbours

    listed = [one("a", [1]), one("b", [2])]
    festival = one("pesach", [], kind=cal.ReadingKind.festival)
    assert neighbours(festival, listed) == (None, None)
    assert neighbours(listed[0], []) == (None, None)
    assert neighbours(listed[0], [listed[0]]) == (None, None), "nowhere else to go"
