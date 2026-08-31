"""How a recording divides into parts a one-file reader can carry.

A file per part rather than per book or per line — the recording package's rule, taken
on for the same reason: per book is unplayable in a reader that fetches nothing, per
sentence is a folder of a thousand files. Chapter marks decide where they exist; long
pauses decide everywhere else, found once and written down, so the boundaries never
move under work already paid for.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, Field

from ..paths import write_atomic
from . import DEFAULT_LANGUAGE, tools
from .probe import Probe

PLANNER = "parts/1"
PARTS = "parts.json"

#: Twelve minutes of speech is around five megabytes cut mono at 48k — a page a phone
#: can carry. Shorter than four minutes is a part for every ad break; longer than
#: twenty is a page that outweighs its own text.
TARGET_S = 720.0
MIN_PART_S = 240.0
MAX_PART_S = 1200.0

#: How far either side of a nominal cut the longest pause is looked for. Half of it is
#: under half of TARGET_S, so two windows can never overlap and every edge settles
#: independently — which is what makes the plan deterministic.
WINDOW_S = 150.0


class PartSpan(BaseModel):
    number: int
    title: str = ""
    start: float
    end: float
    #: Whether the start still wants moving to the nearest long pause. A boundary a
    #: chapter mark stated is a fact; a boundary arithmetic invented is a guess.
    snap_start: bool = False


class Parts(BaseModel):
    planner: str = PLANNER
    duration: float
    language: str = DEFAULT_LANGUAGE
    #: Where the boundaries came from: "marks", "pauses" or "cues".
    origin: str = "pauses"
    #: Once true, no boundary ever moves again — spans and transcripts hang off them.
    settled: bool = False
    parts: list[PartSpan] = Field(default_factory=list)


def hms(seconds: float) -> str:
    whole = int(round(seconds))
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


#: The word a part calls itself by, in the text's own language. A closed map with a
#: Latin fallback: the heading is part of the text, translated like any heading, so a
#: language missing here still comes out right in the translation column.
WORD_FOR_PART = {
    "he": "חלק",
    "yi": "טייל",
    "arc": "חלק",
    "ru": "Часть",
    "ar": "جزء",
    "en": "Part",
}


def heading_for(part: PartSpan, language: str = "") -> str:
    """What the contents page calls this part.

    The mark's own title where the file names its chapters; otherwise the part's
    number leading and its clock following — a bare time range reads as data, and a
    chapter deserves a name.
    """
    if part.title:
        return part.title
    word = WORD_FOR_PART.get(language.split("-")[0].lower(), "Part")
    return f"{word} {part.number} · {hms(part.start)}–{hms(part.end)}"


def _nominal(duration: float, start: float = 0.0) -> list[PartSpan]:
    """Evenly spaced parts over one span, every internal edge still wanting a pause."""
    length = duration - start
    count = max(1, round(length / TARGET_S))
    edges = [start + length * n / count for n in range(count + 1)]
    return [
        PartSpan(number=0, start=a, end=b, snap_start=(n > 0))
        for n, (a, b) in enumerate(zip(edges[:-1], edges[1:], strict=True))
    ]


def plan(probe: Probe, *, language: str = "") -> Parts:
    """The part plan, from the file's own marks where it has them.

    Short marks are merged forward — an audiobook's ten-second announcements are not
    chapters — and a mark longer than a page can carry is split at nominal points that
    `settle` will move to real pauses.
    """
    spans: list[PartSpan] = []
    origin = "pauses"
    marks = [m for m in probe.chapters if m.end - m.start > 0]
    if marks:
        origin = "marks"
        merged: list[tuple[float, float, str]] = []
        carry: tuple[float, str] | None = None
        for mark in marks:
            start = carry[0] if carry is not None else mark.start
            # Forward: a ten-second announcement joins the chapter it introduces, and
            # the chapter keeps its own name — the runt's only where the chapter has
            # none.
            title = mark.title or (carry[1] if carry is not None else "")
            if mark.end - start < MIN_PART_S:
                carry = (start, title)
                continue
            merged.append((start, mark.end, title))
            carry = None
        if carry is not None:
            # A trailing runt has nothing after it to join, so it joins what came
            # before — or stands alone, short, in a recording that is nothing else.
            if merged:
                start, _, title = merged[-1]
                merged[-1] = (start, marks[-1].end, title)
            else:
                merged.append((carry[0], marks[-1].end, carry[1]))
        for start, end, title in merged:
            if end - start > MAX_PART_S:
                pieces = _nominal(end, start)
                for offset, piece in enumerate(pieces):
                    piece.title = f"{title} · {offset + 1}" if title else ""
                    if offset == 0:
                        piece.snap_start = False
                spans.extend(pieces)
            else:
                spans.append(PartSpan(number=0, title=title, start=start, end=end))
    else:
        spans = _nominal(probe.duration)

    for index, span in enumerate(spans):
        span.number = index + 1
    return Parts(
        duration=probe.duration,
        language=language or DEFAULT_LANGUAGE,
        origin=origin,
        settled=not any(span.snap_start for span in spans),
        parts=spans,
    )


def settle(
    audio: Path,
    drafted: Parts,
    notify: Callable[[str], None] | None = None,
) -> Parts:
    """Move every guessed boundary to the midpoint of the longest pause near it.

    Runs once, in the worker rather than the request — a scan of ten hours of audio is
    minutes — and what it decides is final: every transcript and span after this hangs
    off these numbers.
    """
    if drafted.settled:
        return drafted
    pending = [n for n, span in enumerate(drafted.parts) if span.snap_start]
    for done, index in enumerate(pending):
        if notify:
            notify(f"Finding the pauses… {done + 1} of {len(pending)}")
        span = drafted.parts[index]
        before = drafted.parts[index - 1]
        low = max(before.start, span.start - WINDOW_S)
        high = min(span.end, span.start + WINDOW_S)
        pauses = tools.silences(audio, low, high - low)
        inside = [(a, b) for a, b in pauses if low <= a and b <= high]
        if inside:
            a, b = max(inside, key=lambda pair: pair[1] - pair[0])
            seam = round((a + b) / 2, 3)
            before.end = seam
            span.start = seam
        span.snap_start = False
    drafted.settled = True
    return drafted


def write(workspace: Path, parts: Parts) -> None:
    write_atomic(workspace / PARTS, parts.model_dump_json(indent=2) + "\n")


def load(workspace: Path) -> Parts | None:
    path = workspace / PARTS
    if not path.exists():
        return None
    try:
        return Parts.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - a malformed plan reads as absent, and is redone
        return None
