"""Word clocks for a transcript that came from a subtitle file (targum-internal#572).

A subtitle file times cues, not words, so `ingest.subtitles.refined_from` gives every
word of a cue the cue's clock, and since targum#990 such a video lights the line being
said and no word. The words are already right — a person wrote them — so what is missing
is only where each one sits, and that is what the forced aligner (`align.CtcAligner`)
answers: local, unpaid, and on the laptop, because the box has no torchaudio (David,
2026-10-29: "Align on the laptop").

Each part is aligned against its own cut, so every clock is in that file's seconds, the
same frame the cues were. A word keeps the aligner's clock only where the aligner was
sure of it: its letters scored at or above `WORD_FLOOR`, and it landed inside its own
cue give or take `CUE_SLACK_S`. Any other word is written with no length, which
`spans.word_spans_for` keeps no row for, so the page lights nothing there rather than
the wrong word; it stands at the last clock before it, so the line's span still starts
and ends where the voice does. A part whose words match their recording worse than
`align.MATCH_FLOOR` overall is left as its cues.

The transcript's text is never touched: one timed word per written word, so every
segment id stays where it was and the annotation still fits. What changes is the part's
refinement in `audio/refined/` and its spans and word clocks in the manifest, which is
all a rebuild reads.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..errors import TargumError
from ..models import SegmentedDocument, read_artifact
from ..transcribe.models import Refined, RefinedParagraph, Word
from ..transcribe.models import load as load_model
from ..transcribe.models import write as write_model
from . import manifest as manifest_module
from .align import MATCH_FLOOR, match_score
from .spans import part_timings

#: The mean log-probability of a word's letters under which its clock is not kept. On
#: the Touring Israel interview (2026-10-29) the scores are a heap at nought — the median
#: word -0.08, three in four above -0.6 — and a thin tail of what the path could not hear:
#: the filler «א» at -8 to -10, words under crosstalk. Between -1.5 and -4 the share kept
#: climbs about a point per half, with no gap to cut at, so the line is where the clocks
#: still read right by ear-and-eye against their cues: -3 keeps 90% of part 1.
WORD_FLOOR = -3.0
#: How far outside its own cue an aligned word may land and still be believed. A cue's
#: edges are a person's, set by ear, and run a little early or late; a word seconds away
#: from its cue is the path having lost its place, whatever it scored.
CUE_SLACK_S = 1.0
#: The provider a transcript taken from a subtitle file carries.
SUBTITLES = "subtitles"


class Aligner(Protocol):
    name: str

    def align(
        self, audio: Path, words: list[str], language: str
    ) -> list[tuple[float, float, float]]: ...


@dataclass
class PartReport:
    number: int
    words: int = 0
    kept: int = 0
    match: float | None = None
    #: Why the part was left as it was, or "" where it was re-timed.
    skipped: str = ""
    seconds: float = 0.0


@dataclass
class FolderReport:
    parts: list[PartReport] = field(default_factory=list)

    @property
    def words(self) -> int:
        return sum(part.words for part in self.parts)

    @property
    def kept(self) -> int:
        return sum(part.kept for part in self.parts)


def tokens(refined: Refined) -> list[str]:
    """The part's written words, in order, as the aligner is handed them."""
    return [piece for paragraph in refined.paragraphs for piece in paragraph.text.split()]


def aligned_name(aligner_name: str) -> str:
    """The refiner a re-timed part carries: the subtitles it came from and the aligner
    that placed its words, so a second run knows the part is done."""
    return f"subtitles/1+{aligner_name}"


def retimed(
    refined: Refined, timed: Sequence[tuple[float, float, float]], aligner_name: str
) -> tuple[Refined, int]:
    """`refined` with one timed word per written word, from the aligner's `timed` rows
    (one per `tokens(refined)`), and how many kept a clock.

    Raises where the cues' words are not the paragraph's, which is the one shape this
    cannot re-time without moving the text."""
    cued: list[list[tuple[Word, str]]] = []
    for paragraph in refined.paragraphs:
        pieces = [(cue, piece) for cue in paragraph.words for piece in cue.text.split()]
        if [piece for _, piece in pieces] != paragraph.text.split():
            raise TargumError("A paragraph's cues do not spell its text.")
        cued.append(pieces)
    flat = [pair for pieces in cued for pair in pieces]
    if len(flat) != len(timed):
        raise TargumError("The aligner answered for a different number of words.")
    sure = [
        score >= WORD_FLOOR
        and end > start
        and start >= cue.start - CUE_SLACK_S
        and end <= cue.end + CUE_SLACK_S
        for (cue, _), (start, end, score) in zip(flat, timed, strict=True)
    ]
    # Where the next sure word starts, looking ahead from each word.
    ahead: list[float | None] = [None] * len(flat)
    following: float | None = None
    for n in range(len(flat) - 1, -1, -1):
        ahead[n] = following
        if sure[n]:
            following = timed[n][0]
    paragraphs: list[RefinedParagraph] = []
    kept = 0
    at = 0
    clock: float | None = None
    for paragraph, pieces in zip(refined.paragraphs, cued, strict=True):
        words: list[Word] = []
        for cue, piece in pieces:
            start, end, score = timed[at]
            if sure[at]:
                clock = end
                kept += 1
            else:
                # No length, and between the sure words either side of it: at the last
                # clock before it, or its own cue's start where there is none, and never
                # past the next sure word. A cue's edge alone is not enough — a sure
                # word may land up to `CUE_SLACK_S` outside its cue, and a placeholder
                # past it would stretch its line's span over the next line.
                place = clock if clock is not None else cue.start
                after = ahead[at]
                if after is not None:
                    place = min(place, after)
                start = end = place
            at += 1
            words.append(
                Word(
                    text=piece,
                    start=round(start, 3),
                    end=round(end, 3),
                    confidence=round(score, 3),
                    speaker=cue.speaker,
                )
            )
        paragraphs.append(
            RefinedParagraph(text=paragraph.text, speaker=paragraph.speaker, words=words)
        )
    return (
        Refined(
            refiner=aligned_name(aligner_name),
            provider=refined.provider,
            language=refined.language,
            paragraphs=paragraphs,
        ),
        kept,
    )


def kept_lines(
    segmented: SegmentedDocument,
    cued: dict[str, list[float]],
    aligned: dict[str, list[float]],
) -> dict[str, list[float]]:
    """The aligned spans, plus one for each line that had a span from its cues but none
    of whose words the aligner was sure of: a lone «כן.» said over the other voice, six
    lines in the first three parts of the Touring Israel interview. It keeps
    the stretch of its cues that its aligned neighbours leave, so it can still be played
    and lit and overlaps nothing; where they leave nothing it has no span.

    Written into the manifest only, which is what a rebuild reads. A build from scratch
    derives spans from the refinement again and leaves such a line without one."""
    out: dict[str, list[float]] = {}
    ids = [segment.id for segment in segmented.segments if segment.id in cued]
    for n, line in enumerate(ids):
        if line in aligned:
            out[line] = aligned[line]
            continue
        before = [out[i][1] for i in ids[:n] if i in out]
        after = [aligned[i][0] for i in ids[n + 1 :] if i in aligned]
        start = max([cued[line][0], *before[-1:]])
        end = min([cued[line][1], *after[:1]])
        if end > start:
            out[line] = [round(start, 3), round(end, 3)]
    # A line the cues never placed, which the aligner did.
    for line, span in aligned.items():
        out.setdefault(line, span)
    return out


def retime_folder(
    folder: Path,
    aligner: Aligner,
    *,
    parts: Sequence[int] | None = None,
    notify: Callable[[str], None] = lambda message: None,
    clock: Callable[[], float] | None = None,
) -> FolderReport:
    """Re-time every subtitle-timed part of the targum in `folder` that is not re-timed
    already (or the `parts` named), writing each part's refinement and the manifest as
    it goes, so a run stopped halfway keeps what it did."""
    import time

    now = clock or time.monotonic
    manifest = manifest_module.load(folder)
    segmented = read_artifact(SegmentedDocument, folder / "segments.json")
    if manifest is None or segmented is None:
        raise TargumError(f"{folder} has no recording and text to re-time.")
    report = FolderReport()
    language = manifest.language
    for entry in manifest.parts:
        if parts is not None and entry.number not in parts:
            continue
        part = PartReport(entry.number)
        report.parts.append(part)
        path = folder / "audio" / "refined" / f"part-{entry.number:03d}.json"
        refined = load_model(Refined, path)
        audio = folder / entry.audio if entry.audio else None
        if refined is None or audio is None or not audio.exists():
            part.skipped = "no transcript or no cut"
            continue
        if refined.provider != SUBTITLES:
            part.skipped = f"timed by {refined.provider or 'a hearing'}, not subtitles"
            continue
        if refined.refiner == aligned_name(aligner.name):
            part.skipped = "already re-timed"
            continue
        written = tokens(refined)
        part.words = len(written)
        notify(f"Part {entry.number}: aligning {len(written)} words…")
        began = now()
        timed = aligner.align(audio, written, language)
        part.seconds = now() - began
        part.match = match_score(written, [row[2] for row in timed], language)
        if part.match is not None and part.match < MATCH_FLOOR:
            part.skipped = f"matched its recording at {part.match:.2f}, under {MATCH_FLOOR}"
            continue
        fresh, part.kept = retimed(refined, timed, aligner.name)
        write_model(path, fresh)
        spans, entry.words, entry.speakers = part_timings(
            segmented.segments, entry.number, fresh.paragraphs
        )
        entry.spans = kept_lines(segmented, entry.spans, spans)
        entry.refiner = fresh.refiner
        manifest_module.write(folder, manifest)
    return report
