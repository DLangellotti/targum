"""What an edition sets apart, kept beside its words (design.md §12, "A text keeps the shape
its edition gives it", 2026-11-04): Torat Emet's small-printed citations, Rashi's bold
catchwords, Glazer's footnotes.

The test that matters most is the first. Every artifact a text has — its segments, its
words, its meanings, its translation — is keyed to a hash of its text, so a mark that
moved one character of it would re-buy the whole text. The hashes below were taken from
`sefaria/5` before a line of this was written; they must not move.
"""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from typing import Any

import pytest

from targum import marks as marks_module
from targum.align import to_translation
from targum.errors import TargumError
from targum.ingest.fetch import sefaria
from targum.models import (
    Alignment,
    Block,
    BlockKind,
    Document,
    Link,
    Mark,
    Note,
    Segment,
    SegmentedDocument,
    Translation,
)
from targum.render import render
from targum.segment import HebrewSegmenter, segment_document

FIXTURES = Path(__file__).parent / "fixtures" / "sefaria"

#: Each fixture's document hash as `sefaria/5` read it, before marks existed.
BEFORE = {
    (
        "ruth.he.json",
        "Ruth",
        "he",
    ): "bed612b15ca41eac98f6ee9d507afd09859a739f81f0ccec14191ba9c9dbe382",
    (
        "ruth.en.json",
        "Ruth",
        "en",
    ): "e5ad2338c25d8dc5c7c0b73b5c50dcdb3c77cdf4f0ef335efd05b0aaa3ac5924",
    (
        "genesis-1-2.he.json",
        "Genesis 1-2",
        "he",
    ): "078e643821cc703fdd5268295f673e837d45f4de72848c7d575441d889e7ba14",
    (
        "rashi-genesis-1.he.json",
        "Rashi on Genesis 1",
        "he",
    ): "e49c0e0b11ca7cd5b05ad3e21be58af03d58688b869b694b151d2785188ac7be",
    (
        "onkelos-genesis-1-2.arc.json",
        "Onkelos Genesis 1-2",
        "arc",
    ): "38559139af2d75a690b6a2ce74a31fe08731c08ef0a7e38f1c3cf3ccbe2b0670",
    (
        "mishneh-torah-foundations-2.he.json",
        "Mishneh Torah, Foundations of the Torah 2",
        "he",
    ): "56327bb15aeab148064fba9006a8746160c1e04389d17ce1ceff82c6376b3fbe",
    (
        "mishneh-torah-foundations-2.en.json",
        "Mishneh Torah, Foundations of the Torah 2",
        "en",
    ): "726f6dfc75d36d2bb907d49b428184dfe80497a79080da0918fcd8a0ad8ae37e",
}

MT = "Mishneh Torah, Foundations of the Torah 2"


def read(name: str, ref: str, language: str) -> Document:
    body = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return sefaria.document_from_payload(
        {"edition": body["versions"][0], "body": body}, ref, language
    )


@pytest.mark.parametrize(("case", "hashed"), list(BEFORE.items()), ids=[c[0] for c in BEFORE])
def test_marks_leave_the_text_and_its_hash_exactly_as_they_were(
    case: tuple[str, str, str], hashed: str
) -> None:
    document = read(*case)
    assert document.content_hash == hashed
    assert document.recompute_hash() == hashed
    # And the body every stage reads is the blocks' text alone, marks or none.
    stripped = document.model_copy(
        update={
            "blocks": [b.model_copy(update={"marks": None, "notes": None}) for b in document.blocks]
        }
    )
    assert stripped.body() == document.body()


def test_the_ingester_says_it_reads_marks_now() -> None:
    assert sefaria.SefariaFetcher.name == "sefaria/6"


def test_torat_emets_small_citations_are_marked_where_they_stand() -> None:
    document = read("mishneh-torah-foundations-2.he.json", MT, "he")
    first = next(b for b in document.blocks if b.kind is BlockKind.verse)
    cited = [first.text[m.start : m.end] for m in first.marks or [] if m.kind == "cite"]
    assert cited == ["(דברים ו ה)", "(דברים ו יג)"]
    # All eleven of the chapter's, and nothing that is not one.
    every = [b.text[m.start : m.end] for b in document.blocks for m in b.marks or []]
    assert len(every) == 11
    assert all(re.fullmatch(r"\([^()]+\)", one) for one in every)


def test_a_small_letter_inside_a_word_is_no_citation() -> None:
    """The Tanakh prints a few letters small — the ה of בְּהִבָּֽרְאָם — and that is a
    letter, not a reference."""
    found = sefaria.marked("אֵלֶּה תוֹלְדוֹת הַשָּׁמַיִם וְהָאָרֶץ בְּ<small>הִ</small>בָּֽרְאָם", False)
    assert found.cites == ()


def test_glazers_footnotes_are_kept_with_their_place_in_the_line() -> None:
    document = read("mishneh-torah-foundations-2.en.json", MT, "en")
    notes = [(b.id, n) for b in document.blocks for n in b.notes or []]
    assert [n.mark for _, n in notes] == ["1", "2", "3", "4"]
    block = next(b for b in document.blocks if b.id == notes[0][0])
    first = notes[0][1]
    assert block.text[: first.at].endswith("wonderful creatures,")
    assert first.text == "But he must make thorough study. C."
    # The note's words are not in the line, as they never were.
    assert "thorough study" not in block.text


def test_rashis_bold_catchword_is_marked() -> None:
    document = read("rashi-genesis-1.he.json", "Rashi on Genesis 1", "he")
    verse = next(b for b in document.blocks if b.kind is BlockKind.verse)
    catches = [verse.text[m.start : m.end] for m in verse.marks or [] if m.kind == "catch"]
    assert catches[0] == "בראשית."
    # Bold means a catchword only in a commentary.
    assert sefaria.marked("<b>בראשית</b> ברא", False).catches == ()


def test_the_projected_translation_carries_its_notes_to_the_line() -> None:
    english = read("mishneh-torah-foundations-2.en.json", MT, "en")
    target = segment_document(english, HebrewSegmenter())
    verses = [s for s in target.segments if s.kind is BlockKind.verse]
    links = [Link(source=[f"src{i}"], target=[s.id], confidence=1.0) for i, s in enumerate(verses)]
    alignment = Alignment(
        name="Glazer",
        document_hash="h",
        translation_hash="t",
        source_language="he",
        target_language="en",
        aligner="parallel/1",
        links=links,
    )
    projected = to_translation(alignment, target, document=english)
    assert set(projected.notes) == {"src1", "src6", "src11"}
    line = projected.segments["src1"]
    first = projected.notes["src1"][0]
    assert line[: first.at].endswith("wonderful creatures,")
    # Without the document the projection is what it always was.
    assert to_translation(alignment, target).notes == {}


def _page(tmp_path: Path, document: Document, english: Translation, *beside: Translation) -> str:
    segmented = segment_document(document, HebrewSegmenter())
    pages = render(document, segmented, [english, *beside], tmp_path / "reader")
    return pages[0].read_text(encoding="utf-8")


def _verse_doc(text: str, cite: str) -> Document:
    at = text.index(cite)
    block = Block(
        id="b0001",
        kind=BlockKind.verse,
        text=text,
        ref="Mishneh Torah 2:1",
        marks=[Mark(start=at, end=at + len(cite), kind="cite")],
    )
    document = Document(
        source="sefaria:Mishneh Torah",
        title="משנה תורה",
        language="he",
        blocks=[Block(id="b0000", kind=BlockKind.heading, level=2, text="משנה תורה ב׳"), block],
        ingester="sefaria/6",
    )
    document.content_hash = document.recompute_hash()
    return document


def test_a_citation_is_drawn_quiet_and_its_line_is_whole(tmp_path: Path) -> None:
    text = "מִצְוָה לְאָהֳבוֹ שֶׁנֶּאֱמַר (דברים ו ה) וְאָהַבְתָּ"
    document = _verse_doc(text, "(דברים ו ה)")
    segmented = segment_document(document, HebrewSegmenter())
    sid = next(s.id for s in segmented.segments if s.kind is BlockKind.verse)
    english = Translation(
        name="Glazer",
        document_hash=segmented.document_hash,
        source_language="he",
        target_language="en",
        provider="aligned",
        kind="aligned",
        segments={sid: 'It is mandatory to love, for it is said: "Love" (Deut. 6,5).'},
        notes={sid: [Note(at=len("It is mandatory to love,"), mark="1", text="A note. G.")]},
    )
    html = _page(tmp_path, document, english)
    row = re.search(rf'data-id="{re.escape(sid)}".*?</div>', html, re.S)
    assert row is not None
    cell = re.search(r'<p class="src plain"[^>]*>(.*?)</p>', row.group(0), re.S)
    assert cell is not None and '<span class="cite">(דברים ו ה)</span>' in cell.group(1)
    from targum.vocalize import strip_nikkud

    assert unescape(re.sub(r"<[^>]+>", "", cell.group(1))) == strip_nikkud(text)[0]
    # The English: its reference quiet, its note a raised numeral and a line under it.
    assert '<span class="cite">(Deut. 6,5)</span>' in row.group(0)
    assert 'love,<sup class="note-mark">1</sup>' in row.group(0)
    assert '<span class="tr-note"><sup>1</sup> A note. G.</span>' in row.group(0)


def test_a_commentarys_catchword_is_drawn_bold_beside_the_verse(tmp_path: Path) -> None:
    text = "בְּרֵאשִׁית בָּרָא אֱלֹהִים"
    block = Block(id="b0001", kind=BlockKind.verse, text=text, ref="Genesis 1:1")
    document = Document(
        source="sefaria:Genesis",
        title="בראשית",
        language="he",
        blocks=[Block(id="b0000", kind=BlockKind.heading, level=2, text="בראשית א׳"), block],
    )
    document.content_hash = document.recompute_hash()
    segmented = segment_document(document, HebrewSegmenter())
    sid = next(s.id for s in segmented.segments if s.kind is BlockKind.verse)
    english = Translation(
        name="Genesis",
        document_hash=segmented.document_hash,
        source_language="he",
        target_language="en",
        provider="aligned",
        kind="aligned",
        segments={sid: "In the beginning"},
    )
    rashi_line = "בראשית. אמר רבי יצחק"
    rashi = Translation(
        name="Rashi on Genesis",
        document_hash=segmented.document_hash,
        source_language="he",
        target_language="he",
        provider="aligned",
        kind="aligned",
        segments={sid: rashi_line},
        marks={sid: [Mark(start=0, end=len("בראשית."), kind="catch")]},
    )
    html = _page(tmp_path, document, english, rashi)
    assert '<span class="catch">בראשית.</span> אמר רבי יצחק' in html


# --- giving texts already built their marks -----------------------------------------


def _built(folder: Path, document: Document) -> Path:
    folder.mkdir(parents=True)
    document.write(folder / "document.json")
    return folder


def test_a_built_text_gets_its_marks_and_nothing_else(tmp_path: Path) -> None:
    fresh = read("mishneh-torah-foundations-2.he.json", MT, "he")
    held = fresh.model_copy(
        update={
            "ingester": "sefaria/5",
            "blocks": [b.model_copy(update={"marks": None, "notes": None}) for b in fresh.blocks],
        }
    )
    folder = _built(tmp_path / "shared" / "mt-he", held)
    what, _ = marks_module.give(folder, lambda source: fresh)
    assert what == "written"
    after = Document.model_validate_json((folder / "document.json").read_text(encoding="utf-8"))
    assert after.content_hash == held.content_hash == fresh.content_hash
    assert after.ingester == "sefaria/6"
    assert sum(len(b.marks or []) for b in after.blocks) == 11


def test_a_text_whose_words_came_back_different_is_left_exactly_as_it_was(
    tmp_path: Path,
) -> None:
    fresh = read("mishneh-torah-foundations-2.he.json", MT, "he")
    held = fresh.model_copy(
        update={
            "ingester": "sefaria/5",
            "blocks": [
                b.model_copy(update={"marks": None, "text": b.text + (" ׃" if i == 3 else "")})
                for i, b in enumerate(fresh.blocks)
            ],
        }
    )
    held.content_hash = held.recompute_hash()
    folder = _built(tmp_path / "shared" / "mt-he", held)
    before = (folder / "document.json").read_bytes()
    what, why = marks_module.give(folder, lambda source: fresh)
    assert what == "refused" and "different" in why
    assert (folder / "document.json").read_bytes() == before


def test_a_text_sefaria_no_longer_offers_is_left_alone_and_the_run_goes_on(
    tmp_path: Path,
) -> None:
    fresh = read("mishneh-torah-foundations-2.he.json", MT, "he")
    held = fresh.model_copy(
        update={
            "ingester": "sefaria/5",
            "blocks": [b.model_copy(update={"marks": None, "notes": None}) for b in fresh.blocks],
        }
    )
    gone = _built(tmp_path / "shared" / "gone", held)
    kept = _built(tmp_path / "shared" / "kept", held)
    before = (gone / "document.json").read_bytes()
    asked: list[str] = []

    def load(source: str) -> Document:
        asked.append(source)
        if len(asked) == 1:
            raise TargumError("Sefaria has no 'Vocalized Edition' of it.")
        return fresh

    done = marks_module.give_all([gone, kept], load)
    assert done.written == ["shared/kept"]
    assert done.refused[0][0] == "shared/gone" and "Vocalized Edition" in done.refused[0][1]
    assert (gone / "document.json").read_bytes() == before


def test_a_text_from_anywhere_else_is_not_read_again(tmp_path: Path) -> None:
    document = Document(source="dialogue:01", title="x", language="he", blocks=[])
    folder = _built(tmp_path / "shared" / "scene", document)

    def never(source: str) -> Any:
        raise AssertionError("fetched")

    assert marks_module.give(folder, never)[0] == "unchanged"


def test_segment_ids_do_not_depend_on_marks() -> None:
    """A segment is keyed by its text, and its id is what every artifact is filed under."""
    fresh = read("mishneh-torah-foundations-2.he.json", MT, "he")
    bare = fresh.model_copy(
        update={"blocks": [b.model_copy(update={"marks": None}) for b in fresh.blocks]}
    )
    one: list[Segment] = segment_document(fresh, HebrewSegmenter()).segments
    two: list[Segment] = segment_document(bare, HebrewSegmenter()).segments
    assert [s.id for s in one] == [s.id for s in two]
    assert SegmentedDocument  # imported for the type above
