"""SRT and VTT, read for the two things they hold: the words, and their clocks.

A subtitle file is a transcript somebody already timed, which makes it the cheapest
kind there is: nothing to transcribe, nothing to align. Cues become paragraphs at the
same pauses a refiner would break on, and each cue rides along as one timed word, so
the span machinery treats both sources identically.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from pydantic import BaseModel

from ..errors import TargumError
from ..models import BlockKind, Document
from ..transcribe.models import Refined, RefinedParagraph, Word
from ..transcribe.refine.punctuate import CLOSERS, ENDS, Punctuator, needs_punctuation, sparse
from ..transcribe.refine.rules import PARAGRAPH_PAUSE_S
from .base import Paragraph, build_document, named_language, normalize, with_front_matter

#: 00:01:02,345 or 01:02.345 — SRT writes a comma and always hours; VTT writes a dot
#: and lets the hours go missing.
_CLOCK = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")
_ARROW = re.compile(
    r"(?P<a>(?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*(?P<b>(?:\d+:)?\d{1,2}:\d{2}[.,]\d{1,3})"
)
#: <i>, <b>, <c.classname>, <00:01:02.000> word timestamps — styling, not words.
_TAGS = re.compile(r"</?[^v>][^>]*>|<\d[^>]*>")
_VOICE = re.compile(r"<v(?:\.[^ >]*)?\s+(?P<name>[^>]*)>")


class Cue(BaseModel):
    start: float
    end: float
    text: str
    speaker: str = ""


def _seconds(clock: str) -> float:
    found = _CLOCK.fullmatch(clock.strip())
    if not found:
        return 0.0
    hours, minutes, seconds, fraction = found.groups()
    return (
        int(hours or 0) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(fraction.ljust(3, "0")) / 1000
    )


def _unstyled(text: str) -> tuple[str, str]:
    """The cue's words and who says them, with every styling tag gone.

    Entities are decoded after the tags go, so an escaped `&lt;i&gt;` stays a word
    rather than becoming a tag. `&nbsp;` is the one that mattered: left in, it welded
    the end of one sentence to the start of the next — 736 of them across ten Italian
    tracks. Decoded, it is U+00A0, which `split` counts as the space it stood for.
    """
    voice = _VOICE.search(text)
    speaker = html.unescape(voice.group("name")).strip() if voice else ""
    bare = _VOICE.sub("", text)
    bare = html.unescape(_TAGS.sub("", bare).replace("</v>", ""))
    return " ".join(bare.split()), speaker


def parse(text: str) -> list[Cue]:
    """Every cue, sorted and repaired: clamped, merged where they overlap, blanks gone.

    One parser for both formats — a VTT is an SRT with a header, dots for commas and
    settings after the arrow, and matching on the arrow line skips NOTE, STYLE and
    REGION blocks without naming them.
    """
    cues: list[Cue] = []
    block: list[str] = []
    when: tuple[float, float] | None = None

    def close() -> None:
        nonlocal when
        if when is not None and block:
            words, speaker = _unstyled(" ".join(block))
            if words and when[1] > when[0]:
                cues.append(Cue(start=when[0], end=when[1], text=words, speaker=speaker))
        when = None
        block.clear()

    for line in text.splitlines():
        arrow = _ARROW.search(line)
        if arrow:
            close()
            when = (_seconds(arrow.group("a")), _seconds(arrow.group("b")))
            continue
        if not line.strip():
            close()
            continue
        if when is not None:
            block.append(line)
    close()

    cues.sort(key=lambda cue: (cue.start, cue.end))
    repaired: list[Cue] = []
    for cue in cues:
        if repaired and cue.start < repaired[-1].end:
            last = repaired[-1]
            if cue.speaker == last.speaker:
                # Overlap is a timing mistake, not two voices at once. One cue.
                last.end = max(last.end, cue.end)
                last.text = f"{last.text} {cue.text}"
                continue
            cue.start = last.end
            if cue.end <= cue.start:
                continue
        repaired.append(cue)
    return repaired


def load_cues(path: Path) -> list[Cue]:
    cues = parse(normalize(path.read_text(encoding="utf-8", errors="replace")))
    if not cues:
        raise TargumError(f"We couldn't find any subtitles in {path.name}.")
    return cues


def paragraphs_from(cues: list[Cue]) -> list[list[Cue]]:
    """Cues gathered into paragraphs, broken where the voice broke."""
    grouped: list[list[Cue]] = []
    for cue in cues:
        fresh = not grouped or (
            cue.start - grouped[-1][-1].end >= PARAGRAPH_PAUSE_S
            or cue.speaker != grouped[-1][-1].speaker
        )
        if fresh:
            grouped.append([])
        grouped[-1].append(cue)
    return grouped


def refined_from(cues: list[Cue], *, language: str, offset: float = 0.0) -> Refined:
    """These cues as a refinement, timed against a file that starts at `offset`.

    Each cue becomes one timed word: the clocks a subtitle file states are per cue,
    and inventing per-word ones would be precision the file never claimed — except
    where a sentence ends inside a cue, which `drawn` cuts there to close a paragraph.
    """
    paragraphs = drawn(
        [
            Word(
                text=cue.text,
                start=round(max(0.0, cue.start - offset), 3),
                end=round(max(0.0, cue.end - offset), 3),
                speaker=cue.speaker,
            )
            for cue in cues
        ]
    )
    return Refined(
        refiner="subtitles/1", provider="subtitles", language=language, paragraphs=paragraphs
    )


#: A punctuated track is gathered into paragraphs of about this many words: each one
#: closes at the first sentence end after it, so no paragraph stops mid-sentence.
PARAGRAPH_WORDS = 60

#: Where nothing ends a sentence — the model's answer was refused — a paragraph is still
#: closed at a cue after this many words, so the page is never one wall.
WALL_WORDS = 120


def owes_punctuation(refined: Refined) -> bool:
    """Whether a written track came without the marks a reader needs, and has not had
    them bought already (a part the model could not mark is not asked twice)."""
    if "punctuate/" in refined.refiner:
        return False
    return needs_punctuation([word for p in refined.paragraphs for word in p.words])


def punctuated(refined: Refined, punctuator: Punctuator) -> Refined:
    """A written track that never stops, with its full stops put back and its paragraphs
    drawn at them (targum-internal, 2026-11-14).

    A person typed the words, but plenty of tracks are typed the way they are heard: the
    Doña Gracia video's creator uploaded 2,873 words with one full stop and one comma, and
    its cues follow one another without a breath, so it read as two paragraphs of 1,343
    and 1,240 words — six "sentences" in 25 minutes. Its words are the transcript's own,
    so the punctuator's rule holds here too: marks are added, no word changes.

    A cue is one timed word, and a sentence often ends inside one. Such a cue is split at
    the sentence end so a paragraph can close there, its clock shared between the halves
    by their letters — an estimate inside the cue's own span, never outside it. A part the
    aligner re-timed has a clock per word and is never split.
    """
    words = [word for paragraph in refined.paragraphs for word in paragraph.words]
    restored, opens = punctuator.restore(words, refined.language)
    return Refined(
        refiner=f"{refined.refiner}+{punctuator.name}",
        provider=refined.provider,
        language=refined.language,
        paragraphs=drawn(restored, opens),
    )


def drawn(words: list[Word], opens: set[int] | None = None) -> list[RefinedParagraph]:
    """Timed cues drawn into paragraphs a learner can read.

    A track's cues follow one another without a breath, so a pause alone drew the
    Doña Gracia video as paragraphs of 1,343 and 1,240 words, and a punctuated track
    on the box as one paragraph per twelve-minute part. A paragraph closes at a voice
    changing; at a pause, where a sentence has ended (or where the track has no
    sentence ends to wait for); where the model began one (`opens`, word indices); and
    at the first sentence end once it is `PARAGRAPH_WORDS` long. A cue a paragraph closes
    inside is cut there, so no paragraph stops mid-sentence; every other cue stays whole.
    """
    opens = opens or set()
    marked = not sparse(words)
    pieces = [
        (index, piece) for index, word in enumerate(words) for piece in _at_sentence_ends(word)
    ]
    paragraphs: list[list[tuple[int, Word]]] = []
    wanted = False
    seen: set[int] = set()
    for at, (index, piece) in enumerate(pieces):
        if index in opens and index not in seen:
            wanted = True
        seen.add(index)
        if paragraphs:
            last = paragraphs[-1][-1][1]
            ended = _ends(last.text)
            count = sum(len(word.text.split()) for _, word in paragraphs[-1])
            fresh = (
                (bool(piece.speaker or last.speaker) and piece.speaker != last.speaker)
                or (ended and (wanted or count >= PARAGRAPH_WORDS))
                or ((ended or not marked) and piece.start - last.end >= PARAGRAPH_PAUSE_S)
                or (count >= WALL_WORDS and pieces[at - 1][0] != index)
            )
        else:
            fresh = True
        if fresh:
            paragraphs.append([])
            wanted = False
        paragraphs[-1].append((index, piece))
    out: list[RefinedParagraph] = []
    for group in paragraphs:
        # The halves of a cue that stayed in one paragraph are that cue again, its own
        # clock and all: a cue is cut only where a paragraph closes inside it.
        joined: list[tuple[int, Word]] = []
        for index, piece in group:
            if joined and joined[-1][0] == index:
                before = joined[-1][1]
                joined[-1] = (
                    index,
                    before.model_copy(
                        update={"text": f"{before.text} {piece.text}", "end": piece.end}
                    ),
                )
            else:
                joined.append((index, piece))
        cues = [word for _, word in joined]
        out.append(
            RefinedParagraph(
                text=" ".join(word.text for word in cues), speaker=cues[0].speaker, words=cues
            )
        )
    return out


def _ends(text: str) -> bool:
    return text.rstrip(CLOSERS).endswith(ENDS)


def _at_sentence_ends(word: Word) -> list[Word]:
    """One cue, cut after each sentence end inside it, the clock shared by letters."""
    tokens = word.text.split()
    groups: list[list[str]] = [[]]
    for n, token in enumerate(tokens):
        groups[-1].append(token)
        if _ends(token) and n < len(tokens) - 1:
            groups.append([])
    if len(groups) == 1:
        return [word]
    letters = [sum(len(token) for token in group) for group in groups]
    total = sum(letters) or 1
    out: list[Word] = []
    clock = word.start
    for n, (group, size) in enumerate(zip(groups, letters, strict=True)):
        end = word.end if n == len(groups) - 1 else clock + (word.end - word.start) * size / total
        out.append(
            word.model_copy(
                update={"text": " ".join(group), "start": round(clock, 3), "end": round(end, 3)}
            )
        )
        clock = end
    return out


class SubtitleIngester:
    """An SRT or VTT dropped on its own: the words become an ordinary text."""

    name = "subtitles/1"

    def load(self, source: str) -> Document:
        path = Path(source)
        cues = load_cues(path)
        flowing: list[Paragraph] = [
            (BlockKind.paragraph, None, " ".join(cue.text for cue in group))
            for group in paragraphs_from(cues)
        ]
        title = path.stem.replace("-", " ").replace("_", " ")
        from .base import blocks_from_paragraphs

        return build_document(
            str(path),
            blocks_from_paragraphs(with_front_matter(flowing, title, None)),
            ingester=self.name,
            # `talk.it.vtt` says it is Italian; the script alone would call it English.
            language=named_language(path) or None,
            title=title,
        )
