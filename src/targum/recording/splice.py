"""A section's own reading, cut out of a recording made a chapter at a time.

A portion's sections are aliyot and a book's recordings are chapters, and the two divide
the text in different places: Bereshit's first aliyah is all of Genesis 1 and the first
three verses of Genesis 2. So the section's verses are cut out of each chapter they fall
in and joined into one file, and the page plays that file the way it plays a chanted
aliyah — one clock, one bar, verse spans into it.

Cut rather than carried whole. Carried whole, an aliyah's bar was two chapters long, and
playing it through ran on past its last verse into the next reader's.

The cut is made once and kept in the cache, keyed by what it was cut from: a portion is
rebuilt every week, and the same verses of the same files make the same file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ..audio import PAD, tools
from ..errors import TargumError
from ..paths import cache_dir
from .models import Part

#: Bumped when the way a cut is made changes, so a kept file is never the old cut.
VERSION = 1


def plan(part: Part, refs: list[str]) -> tuple[float, float] | None:
    """Where in this part's file the wanted verses are, with a breath either side.

    Never into a verse the section does not hold: the margin stops at the neighbour's
    edge, so an aliyah that begins mid-chapter does not open on the last word of the
    aliyah before it.
    """
    wanted = [part.spans[ref] for ref in refs if ref in part.spans]
    if not wanted:
        return None
    first = min(span[0] for span in wanted)
    last = max(span[1] for span in wanted)
    mine = set(refs)
    before = [span[1] for ref, span in part.spans.items() if ref not in mine and span[1] <= first]
    after = [span[0] for ref, span in part.spans.items() if ref not in mine and span[0] >= last]
    start = max([first - PAD, 0.0, *before])
    end = min([last + PAD, *after])
    return start, end


def splice(pieces: list[tuple[Path, Part]], refs: list[str]) -> tuple[Path, dict[str, list[float]]]:
    """These verses out of these parts as one file, and each verse's span inside it.

    `pieces` is each part with the folder its audio is named relative to, in reading
    order. Raises `TargumError` where a file will not read or ffmpeg is not there; the
    caller decides what a section without a cut does.
    """
    cuts: list[tuple[Path, float, float]] = []
    spans: dict[str, list[float]] = {}
    at = 0.0
    for home, part in pieces:
        window = plan(part, refs)
        if window is None:
            continue
        source = home / part.audio
        if not source.is_file():
            raise TargumError(tools.UNREADABLE)
        start, end = window
        # The last verse's margin can run past the end of the file, and the cut then
        # stops at the file's end. What comes after it begins where the cut really ended.
        end = min(end, tools.duration(source))
        for ref in refs:
            if ref in part.spans:
                verse = part.spans[ref]
                spans[ref] = [round(at + verse[0] - start, 3), round(at + verse[1] - start, 3)]
        cuts.append((source, start, end))
        at += end - start
    if not cuts:
        raise TargumError(tools.UNREADABLE)
    into = _kept(cuts)
    if not into.is_file():
        passing = into.with_name(into.stem + ".part.mp3")
        tools.splice(cuts, passing)
        passing.replace(into)
    return into, spans


def _kept(cuts: list[tuple[Path, float, float]]) -> Path:
    """Where a cut of these files at these seconds is kept.

    By each file's size and modification time as well as its name: a chapter
    re-recorded under the same name is a different cut.
    """
    said = [
        [str(source.resolve()), source.stat().st_size, source.stat().st_mtime_ns, start, end]
        for source, start, end in cuts
    ]
    key = hashlib.sha256(json.dumps([VERSION, said]).encode("utf-8")).hexdigest()[:24]
    return cache_dir() / "spliced" / f"{key}.mp3"
