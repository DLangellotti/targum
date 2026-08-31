"""SRT and VTT, read for the two things they hold: the words, and their clocks.

A subtitle file is a transcript somebody already timed, which makes it the cheapest
kind there is: nothing to transcribe, nothing to align. Cues become paragraphs at the
same pauses a refiner would break on, and each cue rides along as one timed word, so
the span machinery treats both sources identically.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from ..errors import TargumError
from ..models import BlockKind, Document
from ..transcribe.models import Refined, RefinedParagraph, Word
from ..transcribe.refine.rules import PARAGRAPH_PAUSE_S
from .base import Paragraph, build_document, normalize, with_front_matter

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
    """The cue's words and who says them, with every styling tag gone."""
    voice = _VOICE.search(text)
    speaker = voice.group("name").strip() if voice else ""
    bare = _VOICE.sub("", text)
    bare = _TAGS.sub("", bare).replace("</v>", "")
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
        raise TargumError(f"No subtitles found in {path.name}.")
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
    and inventing per-word ones would be precision the file never claimed.
    """
    paragraphs = [
        RefinedParagraph(
            text=" ".join(cue.text for cue in group),
            speaker=group[0].speaker,
            words=[
                Word(
                    text=cue.text,
                    start=round(max(0.0, cue.start - offset), 3),
                    end=round(max(0.0, cue.end - offset), 3),
                    speaker=cue.speaker,
                )
                for cue in group
            ],
        )
        for group in paragraphs_from(cues)
    ]
    return Refined(
        refiner="subtitles/1", provider="subtitles", language=language, paragraphs=paragraphs
    )


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
            title=title,
        )
