"""The Sentences tab: dictation and fill the gap, in lines the reader has read.

design.md §12, "Sentences: dictation and fill the gap" (2026-10-27, targum-internal#534).
Both draw only on sections the reader finished, which is what "read" means everywhere
else ("Met" means a section you finished, 2026-09-28), and both are drawn afresh on every
visit: nothing here is kept, so there is nothing to fall behind on.

- **Dictation** is a line with a clock in a recording the text already has: the one the
  reader's own build plays (`builder.on_disk` asks `builder.speech`'s question), so an
  import's recording, a voice the reader already paid for on Hear, a scene's voicing, or
  the reading attached to the source. A line with no clock is never offered, and nothing
  is ever voiced for this page. The file is handed over as a `/heard` token (`heard`),
  which opens that one file for twenty minutes and names no path.
- **Fill the gap** is a word still being learned taken out of a line it was met in: the
  words Practise these draws on, a line drawn at random from the texts each was met in.

**Nothing here spends and nothing here writes.** The answers are compared in the browser
(`sentences.js`) and never sent; a word's stage moves only when the reader presses it.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from . import meetings
from .occurrences import FolderFor

if TYPE_CHECKING:
    from .models import Document, Segment

#: How many lines a visit offers of each.
LINES = 5

#: A line short enough to hold in the ear and long enough to be a sentence: in words, and
#: in seconds of the recording.
WORDS = (3, 14)
SECONDS = 12.0

#: How many finished texts are opened to find lines with a clock, latest first. A text
#: with a recording has many; a reader with fifty texts and none recorded is answered
#: "no recording" without opening all fifty.
TEXTS = 12

#: Enough to draw five from without opening every finished text.
ENOUGH = 40


@dataclass(frozen=True)
class Heard:
    """One line with a clock: the text it is in, its section and segment, the file it is
    said in and where."""

    document: str
    folder: Path
    section: int
    segment: str
    text: str
    path: Path
    start: float
    end: float


def _document(folder: Path) -> Document | None:
    """The text's `Document`, as `speech` needs it: its source, title and language."""
    from .models import Document

    try:
        facts = json.loads((folder / "document.json").read_text(encoding="utf-8"))
        return Document(
            source=str(facts.get("source") or ""),
            title=facts.get("title"),
            language=str(facts.get("language") or ""),
        )
    except (OSError, ValueError, AttributeError):
        return None


def heard_lines(
    finished: Iterable[tuple[str, str, int]],
    folder_for: FolderFor,
    language: str,
    *,
    most: int = LINES,
    rng: random.Random | None = None,
) -> list[Heard]:
    """Up to `most` lines from finished sections that a recording already says, drawn at
    random. None where no text the reader finished has one."""
    from .models import BlockKind, SegmentedDocument, read_artifact
    from .occurrences import _sections
    from .render.builder import on_disk

    found: list[Heard] = []
    for opened, (document, sections, folder) in enumerate(
        meetings._finished_folders(finished, folder_for, language)
    ):
        if opened >= TEXTS or len(found) >= ENOUGH:
            break
        facts = _document(folder)
        segmented = read_artifact(SegmentedDocument, folder / "segments.json")
        if facts is None or segmented is None:
            continue
        section_of = _sections(folder, segmented)
        by_section: dict[int, list[Segment]] = {}
        for segment in segmented.segments:
            number = section_of.get(segment.id, 1)
            if number in sections and segment.kind is not BlockKind.heading:
                by_section.setdefault(number, []).append(segment)
        for number, segments in sorted(by_section.items()):
            try:
                spoken = on_disk(facts, segments, folder)
            except Exception:  # noqa: BLE001 - a recording that will not read says nothing
                continue
            if not spoken.audio:
                continue
            for segment in segments:
                span = spoken.spans.get(segment.id) or []
                if len(span) < 2 or not 0 < span[1] - span[0] <= SECONDS:
                    continue
                if not WORDS[0] <= len(segment.text.split()) <= WORDS[1]:
                    continue
                found.append(
                    Heard(
                        document,
                        folder,
                        number,
                        segment.id,
                        segment.text,
                        Path(spoken.audio),
                        float(span[0]),
                        float(span[1]),
                    )
                )
    rng = rng or random.Random()
    return rng.sample(found, min(most, len(found)))


def _facts(folder: Path) -> dict[str, object]:
    try:
        loaded = json.loads((folder / "document.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def dictation_item(heard: Heard, into: str, src: str) -> dict[str, object]:
    """What the page says about one line to write down: where it is from, the address it
    plays from and where in it, the line as the reader shows it, and its translation,
    which the page holds back until the line is checked."""
    from .vocalize.base import strip_taamim

    pointed = meetings._pointed(heard.folder, heard.segment)
    facts = _facts(heard.folder)
    sections = len(list((heard.folder / "reader").glob("sec-*.html")))
    return {
        "key": f"{heard.document}:{heard.segment}",
        "line": strip_taamim(pointed or heard.text),
        "src": src,
        "start": round(heard.start, 3),
        "end": round(heard.end, 3),
        "translation": meetings._translation(heard.folder, into).get(heard.segment, ""),
        "title": str(facts.get("title") or ""),
        "chapter": heard.section if sections > 1 else 0,
        "name": heard.folder.name,
        "language": str(facts.get("language") or ""),
    }


def gap_items(
    learning: list[str],
    finished: list[tuple[str, str, int]],
    folder_for: FolderFor,
    language: str,
    into: str,
    *,
    most: int = LINES,
    rng: random.Random | None = None,
) -> list[dict[str, object]]:
    """Up to `most` lines with a word still being learned taken out: the words in a random
    order, each in a line drawn from the texts it was met in. The card's own fields
    (`meetings.card_line`), so the gap is exactly the word the card would mark."""
    rng = rng or random.Random()
    words = list(learning)
    rng.shuffle(words)
    out: list[dict[str, object]] = []
    for lemma in words:
        if len(out) >= most:
            break
        lines, _ = meetings.texts_lines(lemma, finished, folder_for, language)
        if not lines:
            continue
        said = meetings.card_line(rng.choice(lines), into)
        if said and str(said.get("word") or "").strip():
            out.append(said)
    return out


__all__ = ["LINES", "Heard", "dictation_item", "gap_items", "heard_lines"]
