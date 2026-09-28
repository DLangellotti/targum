"""What a recording is.

Two kinds of text are read aloud here, and each is addressed by the one thing the
recording and the text will still agree on in a year. Scripture is addressed by ref —
"Ruth 1:1" — never by position: the segmenter may change, the edition may be re-fetched,
the ids are hashes of the words, but the verse number holds, which is why the ref was
put on the block at ingest rather than worked out here. Prose has no refs, so a prose
recording keeps what does not move instead: each part's word timings, from one forced
alignment paid for (in time, not money — it is local) when the recording was attached.
Spans are then derived at every build by matching words, the same way the imported-audio
manifest derives its own, so a re-split costs nothing and breaks nothing.

Scripture keeps its word timings too, since 2026-09-28 (targum-internal#329): by ref, one
clock per word in the order the verse writes them. A verse's span is read off its words,
and so is a word's and a trope phrase's.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field


class Part(BaseModel):
    """One file of a recording, and where the text is inside it.

    A file per chapter rather than per book or per verse. Per book is unplayable in a
    reader that fetches nothing — a chapter of Genesis would carry ninety megabytes of
    Exodus with it. Per verse is a folder of a thousand files and a fetch for each, which
    is the same rule broken from the other end.
    """

    #: What this part covers, as a person would say it: "Ruth 1", or a chapter's own
    #: heading for prose.
    ref: str
    #: The audio file, named relative to the recording's own folder, so the folder can be
    #: copied between machines without rewriting anything.
    audio: str
    #: Verse ref to [start, end] in seconds, into this part's own file. Scripture only;
    #: a prose part carries `words` instead. Written from `clocks` where there are any,
    #: and still written, so a manifest reads the same to code that knows only verses.
    spans: dict[str, list[float]] = Field(default_factory=dict)
    #: Scripture's word timings: verse ref to one [start, end] per word the aligner was
    #: given, in the order the verse writes them, as `spoken_words` counts them. Inline
    #: rather than a file beside the audio, as prose keeps them, because a verse's words
    #: are addressed by ref and the ref is already here. Empty in a manifest attached
    #: before 2026-09-28, which collapsed them to `spans` and reads exactly as it did.
    clocks: dict[str, list[list[float]]] = Field(default_factory=dict)
    #: A prose part's word timings: a JSON file beside the audio, rows of
    #: [word, start, end, score] in seconds into this part's own file. Empty for
    #: scripture, which keeps its own in `clocks`.
    words: str = ""
    #: The part's video cut, named like `audio`, or "" for a recording that is sound
    #: alone — which is every recording in the library today. Here so that whether a
    #: catalogue text has video is asked of the disk the way `spoken.py` asks about
    #: audio, and never written into the catalogue by hand.
    video: str = ""
    #: Which blocks of the document this part reads: [first, last] block index,
    #: inclusive. How a section finds its part when there is no ref to ask by. Block
    #: indexes hold as long as the source text does — and these sources are snapshots —
    #: while a source that does change leaves the section silent rather than wrong,
    #: which is the same rule a missing span follows.
    blocks: list[int] = Field(default_factory=list)

    def word_clocks(self, ref: str, text: str) -> list[list[float]]:
        """A verse's words as the card's ear wants them: [charStart, charEnd, start, end].

        The char offsets are into the verse's bare text, the one the page's words carry
        in `data-bare`, so the card finds the clock under a tapped word by overlap alone —
        the same rows `audio.spans.word_spans_for` makes for prose. Empty where the text
        no longer counts as many words as were timed: the edition moved under the
        recording, and a gap beats a clock on the wrong word.
        """
        from ..vocalize import js_span, strip_nikkud

        rows = self.clocks.get(ref, [])
        places = spoken_words(text)
        if not rows or len(rows) != len(places):
            return []
        bare, to_bare = strip_nikkud(text)
        out: list[list[float]] = []
        for (first, last), (start, end) in zip(places, rows, strict=True):
            if end > start:
                out.append([*js_span(bare, to_bare[first], to_bare[last]), start, end])
        return out

    def phrase_spans(self, ref: str, text: str) -> list[list[float]]:
        """Each trope phrase of a verse as [start, end], in the order they are chanted.

        What "hear the phrase" plays, read off the word clocks and the marks
        (`vocalize.trope`) at build time rather than stored: the grouping is in the text,
        and a manifest that kept it would be a second copy that could disagree. Empty
        where the words were not timed, where the counts disagree, and for a verse in
        the poetic books, whose accents are another system.
        """
        from ..vocalize.trope import PoeticAccents, read

        rows = self.clocks.get(ref, [])
        if not rows or len(rows) != len(spoken_words(text)):
            return []
        try:
            verse = read(text, ref)
        except PoeticAccents:
            return []
        # Which timed word each whitespace token is. A token that is all accent was never
        # said and has no number; a paseq standing alone and a section mark were timed,
        # and fall in no phrase because the trope reading skips them.
        numbered: dict[int, int] = {}
        for token, word in enumerate(text.split()):
            if _spoken(word):
                numbered[token] = len(numbered)
        out: list[list[float]] = []
        for phrase in verse.phrases:
            held = sorted(
                numbered[verse.words[index].token]
                for index in phrase.words
                if verse.words[index].token in numbered
            )
            if held:
                out.append([rows[held[0]][0], rows[held[-1]][1]])
        return out


class Recording(BaseModel):
    """Somebody's reading of a text, aligned to it once."""

    #: The document this belongs to, as the document names itself: "sefaria:Ruth".
    source: str
    #: Who read it. Not optional: every recording the library can use is used under a
    #: licence that requires the reader be named, and a credit that lives only in a
    #: spreadsheet is a credit the person listening never sees. A public domain reading
    #: requires nothing — and is credited anyway, for the same reason.
    credit: str
    #: The licence, as it is written — "CC BY-SA 4.0".
    licence: str
    #: Where the licence itself can be read. Shown as a link, so it is left empty rather
    #: than guessed: a wrong licence link is worse than none.
    licence_url: str = ""
    parts: list[Part] = Field(default_factory=list)

    def part_for(self, refs: list[str]) -> Part | None:
        """The part that holds these verses, or None if no part holds any of them.

        By what the spans actually contain rather than by the order the parts are in. A
        reader may be built for one chapter, for a range, or for a whole book, and the
        section it is asking about is not reliably the nth part of anything.
        """
        wanted = [ref for ref in refs if ref]
        if not wanted:
            return None
        for part in self.parts:
            if any(ref in part.spans for ref in wanted):
                return part
        return None

    def part_reading(self, block_indexes: list[int]) -> Part | None:
        """The prose part that reads these blocks, or None.

        By block coverage, the prose counterpart of `part_for` — the part holding the
        most of what was asked for, earliest on a tie. Parts are cut per section, so
        this is normally exact; where a shared block leaves a section touching two
        parts, the page keeps the part with its prose on it, and the few lines that
        live in the other part go without a control rather than pointing at sound the
        page is not carrying.
        """
        wanted = [index for index in block_indexes if index >= 0]
        if not wanted:
            return None
        best: Part | None = None
        held = 0
        for part in self.parts:
            if len(part.blocks) != 2:
                continue
            mine = sum(1 for index in wanted if part.blocks[0] <= index <= part.blocks[1])
            if mine > held:
                best, held = part, mine
        return best


def _spoken(token: str) -> bool:
    from ..vocalize import strip_taamim

    return bool(strip_taamim(token))


def spoken_words(text: str) -> list[tuple[int, int]]:
    """Where each word the aligner is given sits in a verse, as (start, end) offsets.

    The aligner hears `strip_taamim(text).split()`, and taking the marks off never splits
    a token, so word n is the nth whitespace token with anything left once the marks are
    gone. Counted here, once, so the attach that numbers the clocks and the build that
    puts them under the page's words cannot count differently.
    """
    return [
        (found.start(), found.end())
        for found in re.finditer(r"\S+", text)
        if _spoken(found.group())
    ]


def verse_spans(clocks: dict[str, list[list[float]]]) -> dict[str, list[float]]:
    """Each verse's [start, end]: its first word's start and its last word's end."""
    return {ref: [rows[0][0], rows[-1][1]] for ref, rows in clocks.items() if rows}


#: One aligned word as the manifest stores it: [word, start, end, score].
Row = list[str | float]


def trimmed(rows: list[Row]) -> list[Row]:
    """A part's words with its badly-scored edges cut off.

    Only the edges: a poorly scored word in the middle is still between two good
    neighbours and its clock is still roughly right, but a poorly scored run at an edge
    is the reader saying words the text never had — "this is a LibriVox recording",
    "end of section". Here rather than beside the attach tool that calls it, because
    the attach tool makes content and stays out of the repository, and the build that
    reads these rows back needs the same trim from a module it is allowed to import.
    """
    from ..audio.align import SCORE_FLOOR

    first, last = 0, len(rows)
    while first < last and float(rows[first][3]) < SCORE_FLOOR:
        first += 1
    while last > first and float(rows[last - 1][3]) < SCORE_FLOOR:
        last -= 1
    return rows[first:last]
