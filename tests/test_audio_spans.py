"""Word timings onto sentences. Derived at every build, so re-splits cost nothing."""

from __future__ import annotations

from targum.audio.spans import spans_for
from targum.models import BlockKind, Segment
from targum.transcribe.models import Word


def line(sid: str, text: str) -> Segment:
    return Segment(
        id=sid,
        block_id="b0010001",
        block_index=10001,
        index=0,
        kind=BlockKind.paragraph,
        text=text,
    )


def said(text: str, step: float = 1.0) -> list[Word]:
    return [
        Word(text=piece, start=round(n * step, 3), end=round(n * step + 0.8, 3))
        for n, piece in enumerate(text.split())
    ]


def test_a_sentence_finds_its_first_and_last_word_after_stanza_resplits_the_paragraph() -> None:
    """The paragraph was one block; the segmenter made it two sentences. Each takes
    the clock of its own words, not the block's."""
    words = said("שלום לכם היום. טוב מאוד לראות.")
    spans = spans_for(
        [line("a", "שלום לכם היום."), line("b", "טוב מאוד לראות.")],
        words,
    )
    assert spans["a"] == [0.0, 2.8]
    assert spans["b"] == [3.0, 5.8]


def test_a_sentence_no_word_matches_gets_no_span_rather_than_the_nearest() -> None:
    """A control that plays the wrong words is worse than no control — the rule the
    recordings already follow."""
    spans = spans_for(
        [line("a", "שלום לכם."), line("b", "משהו אחר לגמרי כתוב כאן.")],
        said("שלום לכם."),
    )
    assert "a" in spans
    assert "b" not in spans


def test_unglued_spacing_does_not_move_a_span() -> None:
    """The spacing repair may split what the transcriber wrote as one word; the
    sentence still anchors on the words that match."""
    words = said("אמרהלך היום בבוקר")
    spans = spans_for([line("a", "אמר הלך היום בבוקר")], words)
    assert spans["a"][1] == words[-1].end


def test_each_written_word_carries_its_own_clock() -> None:
    """Rows of [charStart, charEnd, start, end], char offsets into the segment's own
    text — what lets the card play one word rather than the line it sits in."""
    from targum.audio.spans import word_spans_for

    words = said("אמר הלך היום")
    rows = word_spans_for([line("a", "אמר הלך היום")], words)["a"]
    assert [row[:2] for row in rows] == [[0, 3], [4, 7], [8, 12]]
    assert rows[0][2] == words[0].start and rows[0][3] == words[0].end
    assert rows[2][2] == words[2].start and rows[2][3] == words[2].end


def test_a_word_the_recording_never_said_gets_no_clock() -> None:
    """The middle word is not in the audio: its neighbours keep their rows and it has
    none — a gap the card can see past beats a clock that lies."""
    from targum.audio.spans import word_spans_for

    words = said("אמר היום")
    rows = word_spans_for([line("a", "אמר הלך היום")], words)["a"]
    assert [row[:2] for row in rows] == [[0, 3], [8, 12]]
