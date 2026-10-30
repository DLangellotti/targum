"""Where each sentence sits in its part's audio, worked out from word timings.

Derived at every build rather than stored against segment ids: the segmenter may
re-split a paragraph and an edited transcript changes every id after it, but the words
and their clocks do not move. Matching is done on normalised tokens with difflib, so
the spacing repair and a re-split cost nothing.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from collections.abc import Sequence

from ..ids import audio_block_id
from ..models import Segment
from ..transcribe.models import RefinedParagraph, Word

#: Nikkud, taamim and every other combining mark a transcript or a text may carry.
_MARKS = re.compile(r"[֑-ׇ]")
_DROP = re.compile(r"[^\wא-ת]+", re.UNICODE)


def normalise(token: str) -> str:
    """One word, as both sides of the match will spell it."""
    bare = _MARKS.sub("", unicodedata.normalize("NFC", token))
    return _DROP.sub("", bare).lower()


def _tokens(text: str) -> list[str]:
    return [kept for piece in text.split() if (kept := normalise(piece))]


def word_spans_for(segments: list[Segment], words: list[Word]) -> dict[str, list[list[float]]]:
    """Each written word's clock: rows of [charStart, charEnd, start, end] per segment.

    The char offsets are into the segment's own text, the coordinate system the
    reader's tokens already live in, so the card can find the clock under a tapped
    word by overlap alone. A word the matcher could not pair gets no row — the same
    rule `spans_for` follows, one word down: a gap beats a clock that lies.
    """
    kept: list[tuple[int, str]] = []
    for index, word in enumerate(words):
        for piece in word.text.split():
            token = normalise(piece)
            if token:
                kept.append((index, token))
    matcher = difflib.SequenceMatcher(a=[token for _, token in kept], autojunk=False)

    # Each written token with where it sits in its segment's own text.
    placed: list[tuple[Segment, int, int]] = []
    written: list[str] = []
    for segment in segments:
        for found in re.finditer(r"\S+", segment.text):
            token = normalise(found.group())
            if token:
                placed.append((segment, found.start(), found.end()))
                written.append(token)

    matcher.set_seq2(written)
    out: dict[str, list[list[float]]] = {}
    for a, b, size in matcher.get_matching_blocks():
        for offset in range(size):
            segment, char_start, char_end = placed[b + offset]
            clock = words[kept[a + offset][0]]
            if clock.end > clock.start:
                out.setdefault(segment.id, []).append(
                    [char_start, char_end, round(clock.start, 3), round(clock.end, 3)]
                )
    for rows in out.values():
        rows.sort()
    return out


def spans_for(segments: list[Segment], words: list[Word]) -> dict[str, list[float]]:
    """Each segment's [start, end] in seconds, into its part's own file.

    A segment none of whose words match gets no span rather than the nearest one — the
    same rule the rest of the build follows: a gap a reader can see past beats a
    control that lies.
    """
    # One timed word is usually one token, but a subtitle cue rides as a single
    # timed "word" holding a sentence — so each word's text is tokenised, and every
    # token points back at the clock it came from.
    kept: list[tuple[int, str]] = []
    for index, word in enumerate(words):
        for piece in word.text.split():
            token = normalise(piece)
            if token:
                kept.append((index, token))
    matcher = difflib.SequenceMatcher(a=[token for _, token in kept], autojunk=False)

    # Where each segment's tokens sit in the block's own stream.
    ranges: list[tuple[Segment, int, int]] = []
    at = 0
    written: list[str] = []
    for segment in segments:
        mine = _tokens(segment.text)
        ranges.append((segment, at, at + len(mine)))
        written.extend(mine)
        at += len(mine)

    matcher.set_seq2(written)
    #: written-token index -> word index, for every token the matcher paired.
    paired: dict[int, int] = {}
    for a, b, size in matcher.get_matching_blocks():
        for offset in range(size):
            paired[b + offset] = kept[a + offset][0]

    out: dict[str, list[float]] = {}
    for segment, first, last in ranges:
        hits = [paired[n] for n in range(first, last) if n in paired]
        if not hits:
            continue
        start = words[min(hits)].start
        end = words[max(hits)].end
        if end > start:
            out[segment.id] = [round(start, 3), round(end, 3)]
    return out


def part_timings(
    segments: Sequence[Segment], number: int, paragraphs: Sequence[RefinedParagraph]
) -> tuple[dict[str, list[float]], dict[str, list[list[float]]], dict[str, str]]:
    """One part's spans, word clocks and speakers, by segment id: what the manifest keeps
    for it. Paragraph n of part p is the text's block `audio_block_id(p, n)`, and its
    segments are matched to the paragraph's timed words. Shared by the build and by
    `subtitle_words`, which re-times a part on the laptop and has to write the same."""
    prefix = f"part {number}:"
    by_block: dict[str, list[Segment]] = {}
    for segment in segments:
        if segment.ref.startswith(prefix) and not segment.ref.endswith(":waiting"):
            by_block.setdefault(segment.block_id, []).append(segment)
    spans: dict[str, list[float]] = {}
    words: dict[str, list[list[float]]] = {}
    speakers: dict[str, str] = {}
    for n, paragraph in enumerate(paragraphs, start=1):
        lines = by_block.get(audio_block_id(number, n), [])
        if not lines:
            continue
        spans |= spans_for(lines, paragraph.words)
        words |= word_spans_for(lines, paragraph.words)
        if paragraph.speaker:
            for line in lines:
                speakers[line.id] = paragraph.speaker
    return spans, words, speakers
