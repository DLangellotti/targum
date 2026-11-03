"""A chapter of a numbered text says "פרק א׳", and the work is named once (David,
2026-11-03; design.md §12, "A chapter says "פרק א׳", and the work is named once").

Sefaria heads every chapter with the work's whole name and the chapter's numeral. Those
headings were the parts' titles, so the contents page said the work on every row and the
English read like a volume number. The part's title is now the chapter's label; the
heading in the text is untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from targum.models import BlockKind, Document, Segment, SegmentedDocument, Translation
from targum.render.builder import split_sections

WORK = "משנה תורה, הלכות יסודי התורה"


def numbered(
    headings: list[str], refs: list[str], *, language: str = "he", lines: int = 2
) -> SegmentedDocument:
    """A text shaped the way the Sefaria ingester writes one: a heading, then verses that
    carry their refs. `refs` is each chapter's address stem, "Ruth 1" for chapter one."""
    segments: list[Segment] = []
    for chapter, (heading, stem) in enumerate(zip(headings, refs, strict=True), start=1):
        segments.append(
            Segment(
                id=f"h{chapter}",
                block_id=f"b{chapter}",
                block_index=len(segments),
                index=len(segments),
                text=heading,
                kind=BlockKind.heading,
                level=2,
            )
        )
        for verse in range(1, lines + 1):
            segments.append(
                Segment(
                    id=f"s{chapter}-{verse}",
                    block_id=f"v{chapter}-{verse}",
                    block_index=len(segments),
                    index=len(segments),
                    text=f"שורה {verse}",
                    kind=BlockKind.verse,
                    ref=f"{stem}:{verse}" if stem else "",
                )
            )
    return SegmentedDocument(
        document_hash="doc", language=language, segmenter="t/1", segments=segments
    )


def test_a_hebrew_chapter_is_titled_by_its_chapter() -> None:
    segmented = numbered(
        [f"{WORK} א׳", f"{WORK} ב׳", f"{WORK} ט״ו"],
        ["Mishneh Torah, Foundations of the Torah 1", "x 2", "x 15"],
    )
    sections = split_sections(segmented)
    assert [s.title for s in sections] == ["פרק א׳", "פרק ב׳", "פרק ט״ו"]
    assert all(s.chapter for s in sections)
    # Only the label: the heading in the text is what Sefaria wrote.
    assert segmented.segments[0].text == f"{WORK} א׳"


def test_a_numeral_without_its_mark_is_the_same_chapter() -> None:
    sections = split_sections(numbered(["רות א", "רות ב"], ["Ruth 1", "Ruth 2"]))
    assert [s.title for s in sections] == ["פרק א׳", "פרק ב׳"]


def test_english_and_russian_chapters_say_it_in_their_own_language() -> None:
    english = numbered(["Ruth 1", "Ruth 2"], ["Ruth 1", "Ruth 2"], language="en")
    assert [s.title for s in split_sections(english)] == ["Chapter 1", "Chapter 2"]
    russian = numbered(["Руфь 1", "Руфь 2"], ["Ruth 1", "Ruth 2"], language="ru")
    assert [s.title for s in split_sections(russian)] == ["Глава 1", "Глава 2"]


@pytest.mark.parametrize(
    ("headings", "refs"),
    [
        # A heading whose numeral is not the chapter its verses are in.
        (["רות ג׳", "רות ד׳"], ["Ruth 1", "Ruth 2"]),
        # A daf: its refs are not chapter and verse.
        (["ברכות ב.", "ברכות ב:"], ["Berakhot 2a", "Berakhot 2b"]),
        # Verses with no refs at all, as any book that is not numbered.
        (["פתיחה א׳", "המשך ב׳"], ["", ""]),
    ],
)
def test_a_part_that_is_not_a_chapter_keeps_its_title(headings: list[str], refs: list[str]) -> None:
    sections = split_sections(numbered(headings, refs))
    assert [s.title for s in sections] == headings
    assert not any(s.chapter for s in sections)


def built(tmp_path: Path) -> Path:
    """Two chapters of the Mishneh Torah, rendered."""
    from targum.render import render

    segmented = numbered([f"{WORK} א׳", f"{WORK} ב׳"], ["MT 1", "MT 2"])
    translation = Translation(
        name="English",
        document_hash="doc",
        source_language="he",
        target_language="en",
        provider="null",
        segments={s.id: "line" for s in segmented.segments},
    )
    document = Document(source="m", title=WORK, language="he", blocks=[], content_hash="doc")
    reader = tmp_path / "mt-he" / "reader"
    render(document, segmented, [translation], reader)
    return reader


def test_the_reader_names_the_chapter_beside_the_work(tmp_path: Path) -> None:
    reader = built(tmp_path)
    first = (reader / "sec-0001.html").read_text(encoding="utf-8")
    assert '<span class="bar-part" lang="he" dir="rtl">פרק א׳</span>' in first
    assert "— פרק א׳</title>" in first
    # The heading in the text still names the work.
    assert f"{WORK} א׳" in first
