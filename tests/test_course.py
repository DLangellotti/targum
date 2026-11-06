"""A course book's lesson becomes a reader beside its own translation (targum-internal#652).

Every line here is invented for the test. A course book is in copyright, and none of its
text belongs in this repository, a fixture included.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_sefaria import _WholeBlocks

from targum import ingest
from targum.align import parallel
from targum.errors import TargumError
from targum.ingest.fetch import course
from targum.models import BlockKind
from targum.segment import segment_document


def book() -> dict:
    return {
        "title": "A Made-up Course",
        "language": "it",
        "translation": "en",
        "lessons": {
            "1": {
                "title": {
                    "it": ["LEZIONE UNO (lehtsyauneh)", "Al mercato"],
                    "en": ["LESSON ONE", "At the Market"],
                },
                "lines": {
                    "1": {
                        "it": "— Buongiorno! Vorrei due mele. (1)",
                        "en": "— Good morning! [I]'d like two apples.",
                    },
                    "2": {
                        "it": "— Ecco le mele. Altro? (2) (N.1)",
                        "en": "— Here are the apples. Anything else?",
                    },
                    "3": {"it": "— No, grazie.", "en": ""},
                },
                "notes": {
                    "1": "Vorrei is the polite way to ask for something.",
                    "2": "Ecco points at what is there.",
                },
                "pronuncia": ["bwon-djorrr-noh"],
                "exercises": {"it": {"1": "Vorrei una mela."}, "en": {"1": "I'd like an apple."}},
                "gaps": {"1": "Here it is. || ___ ."},
                "key": {"1": "Ecco"},
            },
            "2": {
                "title": {"it": ["LEZIONE DUE", "REVISIONE"], "en": ["(Revision)", "LESSON TWO"]},
                "lines": {},
                "notes": {"1": "Ecco and vorrei, once more.", "2": "Numbers: uno, due."},
            },
        },
    }


def pair_of(held: dict, number: int):
    return course.documents(held, number, "it", "en", name="made-up")


def test_a_lesson_becomes_two_sides_that_pair_line_for_line() -> None:
    italian, english = pair_of(book(), 1)
    assert italian.source == "course:it:made-up:1" and english.source == "course:en:made-up:1"
    assert italian.ingester == "course/1" and italian.language == "it" and english.language == "en"
    verses = [b for b in italian.blocks if b.kind is BlockKind.verse]
    assert [b.ref for b in verses] == ["L1:1", "L1:2", "L1:3"]
    assert parallel.parallel_key(italian) == parallel.parallel_key(english) is not None
    alignment = parallel.pair(
        segment_document(italian, _WholeBlocks()),
        segment_document(english, _WholeBlocks()),
        "lesson 1",
    )
    assert alignment.coverage() == 1.0 and alignment.aligner == parallel.NAME


def test_markers_leave_the_text_and_notes_land_on_the_translation_line() -> None:
    italian, english = pair_of(book(), 1)
    lines = [b for b in italian.blocks if b.kind is BlockKind.verse]
    assert lines[0].text == "— Buongiorno! Vorrei due mele."
    assert all("(" not in b.text for b in italian.blocks)
    assert all(not b.notes for b in italian.blocks)
    first, second, third = (b for b in english.blocks if b.kind is BlockKind.verse)
    assert first.notes and first.notes[0].mark == "1" and first.notes[0].at == len(first.text)
    assert first.notes[0].text.startswith("Vorrei is the polite")
    # (N.1) points at the revision lesson's first section, which the extract holds.
    assert [n.mark for n in second.notes or []] == ["2", "N.1"]
    assert second.notes[1].text == "Ecco and vorrei, once more."
    # A line the translation lacks keeps its place, so the next line still pairs.
    assert third.text == "—"


def test_the_heading_drops_the_respelling_and_the_shouting() -> None:
    italian, english = pair_of(book(), 1)
    assert italian.blocks[0].kind is BlockKind.heading
    assert italian.blocks[0].text == "Lezione uno — Al mercato"
    assert english.blocks[0].text == "Lesson one — At the Market"
    assert italian.title == "Lezione uno — Al mercato"


def test_what_the_reader_leaves_out_stays_out() -> None:
    italian, english = pair_of(book(), 1)
    said = " ".join(b.text for doc in (italian, english) for b in doc.blocks)
    for kept_for_later in ("bwon-djorrr-noh", "Vorrei una mela.", "I'd like an apple.", "___"):
        assert kept_for_later not in said


def test_a_revision_lesson_is_a_reader_with_its_sections_on_the_heading() -> None:
    italian, english = pair_of(book(), 2)
    assert [b.kind for b in italian.blocks] == [BlockKind.heading]
    assert english.blocks[0].text == "Revision — Lesson two"
    assert [n.mark for n in english.blocks[0].notes or []] == ["1", "2"]
    alignment = parallel.pair(
        segment_document(italian, _WholeBlocks()),
        segment_document(english, _WholeBlocks()),
        "lesson 2",
    )
    assert alignment.coverage() == 1.0


def test_a_line_misread_with_no_italian_is_refused() -> None:
    held = book()
    held["lessons"]["1"]["lines"]["2"]["it"] = ""
    with pytest.raises(TargumError):
        pair_of(held, 1)
    with pytest.raises(TargumError):
        pair_of(book(), 9)


def test_the_extract_is_read_from_the_courses_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "made-up.json").write_text(json.dumps(book(), ensure_ascii=False), "utf-8")
    monkeypatch.setenv("TARGUM_COURSES", str(tmp_path))
    italian = ingest.load("course:it:made-up:1")
    english = ingest.load("course:en:made-up:1")
    assert italian.language == "it" and english.language == "en"
    assert parallel.parallel_key(italian) == parallel.parallel_key(english)
    with pytest.raises(TargumError):
        ingest.load("course:fr:made-up:1")
    with pytest.raises(TargumError):
        ingest.load("course:it:no-such-book:1")
    # A book is a name, never a path.
    with pytest.raises(TargumError):
        ingest.load("course:it:../made-up:1")


def test_no_request_can_name_a_course() -> None:
    """A course extract is a reader's copy of a book in copyright: the Add page, the chat
    and Telegram take only what `fetchable` allows, and it never allows a course."""
    assert ingest.fetch.is_identifier("course:it:made-up:1")
    assert not ingest.fetchable("course:it:made-up:1")
    assert not ingest.fetch.addressable("course:it:made-up:1")
    assert ingest.fetchable("published:ru:Genesis")
    assert "course:" not in ingest.sources()
