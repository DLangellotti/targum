"""The daily learning cycles: which day, which range, and cut out of what.

The calendar is not exercised against the network here — `parse` is given Hebcal's own
answer and asked what it made of it, the same way `test_parasha_calendar` does. What is
defended is the part that would be wrong quietly: a reference read as the wrong verses
puts the wrong text on the page under today's date, and nothing about the page would look
broken.
"""

from __future__ import annotations

from datetime import date

import pytest

from targum.daily import calendar as cal
from targum.daily.cut import pieces, place_of, within
from targum.daily.cycles import ABSENT, BY_SLUG, CYCLES, parse_reference, reference_of
from targum.models import BlockKind, Segment


def item(**extra: object) -> dict[str, object]:
    row = {
        "title": "Kelim 28:2-3",
        "hebrew": "כלים 28:2-3",
        "date": "2026-09-01",
        "hdate": "19 Elul 5786",
        "category": "mishnayomi",
    }
    row.update(extra)
    return row


# -- reading a reference ------------------------------------------------------


@pytest.mark.parametrize(
    ("said", "expected"),
    [
        # Two mishnayot inside one chapter. The bare 3 is a verse, not a chapter — this
        # is the one that was wrong first, and it is every second day of the cycle.
        ("Kelim 28:2-3", ("Kelim", 28, 2, "Kelim", 28, 3)),
        # And across a chapter, where the right side names both.
        ("Kelim 28:10-29:1", ("Kelim", 28, 10, "Kelim", 29, 1)),
        # A whole chapter: no verses either side, which is what Nach Yomi reads.
        ("Isaiah 55", ("Isaiah", 55, None, "Isaiah", 55, None)),
        # A run of whole chapters. The left side names no verse, so the bare numbers are
        # chapters — the opposite reading of the same shape as `Kelim 28:2-3`.
        ("Psalms 90-96", ("Psalms", 90, None, "Psalms", 96, None)),
        # A book whose name carries a numeral of its own.
        ("I Chronicles 1:1-4:9", ("I Chronicles", 1, 1, "I Chronicles", 4, 9)),
    ],
)
def test_a_reference_is_read_as_what_it_says(said: str, expected: tuple[object, ...]) -> None:
    span = parse_reference(said)
    assert span is not None
    assert (span.book, span.chapter, span.verse, span.book2, span.chapter2, span.verse2) == expected


def test_a_day_can_cross_from_one_text_into_the_next() -> None:
    """The last mishnah of one tractate and the first of the next, which happens at
    every tractate boundary — sixty-two times a cycle."""
    span = parse_reference("Kelim 30:4-Oholot 1:1")
    assert span is not None and span.crosses
    first, second = pieces(span)
    assert first[0] == "Kelim" and (first[1], first[2]) == (30, 4)
    assert second[0] == "Oholot" and (second[3], second[4]) == (1, 1)
    # The first piece runs to the end of its text and the second from the beginning of
    # its own: an unbounded end is what "to the end of the tractate" means.
    assert first[4] is None
    assert second[1] == 0


def test_a_shape_this_does_not_know_is_refused_rather_than_guessed() -> None:
    """A guessed range is the wrong text under today's date, and nothing on the page
    would look wrong."""
    assert parse_reference("") is None
    assert parse_reference("Some Tractate") is None


def test_tanakh_yomi_points_somewhere_its_title_does_not() -> None:
    """Its title is the seder's name and the verses are in the memo. Reading the title
    would look up a book called "Ezra and Nehemiah Seder"."""
    assert reference_of(item(title="Ezra and Nehemiah Seder 10", memo="Nehemiah 12:27-13:31")) == (
        "Nehemiah 12:27-13:31"
    )
    assert reference_of(item(title="Isaiah 55")) == "Isaiah 55"


# -- reading Hebcal's answer --------------------------------------------------


def test_a_day_carries_what_the_page_shows() -> None:
    days = cal.parse({"items": [item()]})
    assert len(days) == 1
    day = days[0]
    assert day.cycle == "mishna-yomi"
    assert day.day == date(2026, 9, 1)
    assert day.hdate == "19 Elul 5786"
    assert day.span is not None
    assert day.slug == "2026-09-01"


def test_a_cycle_this_shelf_does_not_carry_is_dropped() -> None:
    """The request asks for four and a fifth would be noise — and Daf Yomi's text is not
    on this shelf at all, so a day of it could not be cut."""
    days = cal.parse({"items": [item(category="dafyomi", title="Chullin 124"), item()]})
    assert [one.cycle for one in days] == ["mishna-yomi"]


def test_every_cycle_offered_is_one_the_page_can_answer_for() -> None:
    for cycle in CYCLES:
        assert BY_SLUG[cycle.slug] is cycle
        assert cycle.name and cycle.hebrew and cycle.blurb and cycle.rhythm


def test_what_is_missing_is_named_rather_than_left_out() -> None:
    """Somebody looking for Daf Yomi is owed an answer, and silence is not one."""
    assert "Daf Yomi" in ABSENT
    assert "ShareAlike" in ABSENT["Daf Yomi"]


# -- taking the range out of a text -------------------------------------------


def segment(ref: str) -> Segment:
    return Segment(
        id=ref, block_id=ref, block_index=0, index=0, kind=BlockKind.verse, text="x", ref=ref
    )


def test_a_place_is_read_off_the_segments_own_ref() -> None:
    """Not off the book's name: which text this is was decided by which folder was
    opened, and `Mishnah Kelim 28:2` would otherwise be matched against `Kelim`."""
    assert place_of(segment("Mishnah Kelim 28:2")) == (28, 2)
    assert place_of(segment("I Chronicles 4:9")) == (4, 9)
    assert place_of(segment("")) is None


def test_a_range_with_no_verses_is_the_whole_chapter() -> None:
    """Which is how a cycle that reads chapters at a time says so."""
    assert within((55, 1), 55, None, 55, None)
    assert within((55, 22), 55, None, 55, None)
    assert not within((56, 1), 55, None, 55, None)


def test_a_range_with_verses_stops_where_it_says() -> None:
    assert within((28, 2), 28, 2, 28, 3)
    assert within((28, 3), 28, 2, 28, 3)
    assert not within((28, 1), 28, 2, 28, 3)
    assert not within((28, 4), 28, 2, 28, 3)
