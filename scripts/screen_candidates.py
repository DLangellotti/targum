"""Sift a pile of candidate sources down to the ones worth reading.

The catalogue's rule is that nothing goes in until it has been fetched and checked, and
`measure_difficulty.py` is what checks it. That works one text at a time and is the wrong
shape for building a shelf: it loads Stanza on every invocation, so screening forty texts
by calling it forty times spends thirty-odd seconds per text loading a model and five
seconds using it. This loads Stanza once and keeps it.

**Two stages, cheap one first.** Fetching a text costs half a second and annotating it
costs five, so everything that can disqualify a text on its raw text alone is decided
before Stanza is asked anything: too short to be a sitting, too long to finish in one,
or not actually in the language it claims.

**The language share is the check that was missing**, and it is here rather than in
`measure_difficulty.py` because that script trusts the catalogue and this one does not.
A source that quotes its sources in the original — translated journalism especially —
comes back as a Hebrew document with a third of its letters in Spanish, and nothing in a
word count shows it. Left in, the reader taps a Spanish word and is handed a Hebrew
lemma, and the difficulty comes out nonsense because Spanish is being banded against
Hebrew frequency.

**A media candidate is screened on its recording before its words.** A YouTube address,
or a local recording with a subtitle file beside it, passes three more stage-one checks
that `targum.screen` explains: the audio track's own language tag, how much of the
recording the subtitle track covers, and words per minute as a flag. Twelve Khan Academy
videos passed the text screen and one of them carried another video's subtitles
(targum-internal#139); the coverage gate is what catches that, and it catches it before
anybody has watched anything. Nothing is downloaded but metadata and the subtitle file.

**Two licence flags, computed and not typed.** `reader_publishable` and
`corpus_exportable` come off `licensing.py`'s one verdict, because ivrit.ai and
NonCommercial audio answer the two questions in opposite ways and no single boolean
holds both.

Output is a TSV of survivors, ranked so the band the shelf is thinnest in comes first
and easiest within it, carrying everything an `Entry` needs except the blurb — which is
a judgement and stays a person's job.

    uv run python scripts/screen_candidates.py candidates.txt > shortlist.tsv

A candidate line is a source, optionally followed by a tab, a subtitle file, a tab and a
licence string. A YouTube address needs neither: its Hebrew track is fetched and its
licence is what the uploader set. A local recording needs the subtitle file.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import ingest, screen  # noqa: E402
from targum.annotate import Annotator  # noqa: E402
from targum.annotate.frequency import FrequencyBands  # noqa: E402
from targum.audio import is_audio, tools  # noqa: E402
from targum.ingest.subtitles import load_cues  # noqa: E402
from targum.segment import HebrewSegmenter, segment_document  # noqa: E402
from targum.video import is_video  # noqa: E402
from targum.video.youtube import describe, fetch_subtitles, is_youtube  # noqa: E402

#: Where a word stops being one a reader knows and starts being one they look up. The same
#: cut `measure_difficulty.py` uses, and it has to stay the same or two texts measured by
#: different scripts are not comparable.
LOOKED_UP = 4

SCRIPTS = {
    "he": re.compile(r"[֐-׿]"),
    "ar": re.compile(r"[؀-ۿ]"),
    "ru": re.compile(r"[Ѐ-ӿ]"),
}
LATIN = re.compile(r"[A-Za-z]")


@dataclass
class Candidate:
    """One line of the candidates file, and what stage one learned about it."""

    source: str
    subtitles: str = ""
    licence: str = ""
    #: What stage two reads: the source itself for a text, the subtitle file for media.
    text_source: str = ""
    title: str = ""
    text: str = ""
    words: int = 0
    share: int = 0
    gate: screen.Gate | None = None
    flags: list[str] = field(default_factory=list)


@dataclass
class Screened:
    candidate: Candidate
    difficulty: int
    opening: str


def language_share(text: str, language: str) -> int:
    """What percentage of the letters are in the script this text claims.

    Counted over letters rather than words because a quoted block is what this is looking
    for, and a block of Spanish inside a Hebrew paragraph is invisible to anything that
    counts whitespace.
    """
    own = SCRIPTS.get(language.split("-")[0].lower(), LATIN)
    mine = len(own.findall(text))
    other = sum(len(rx.findall(text)) for key, rx in SCRIPTS.items() if rx is not own)
    other += 0 if own is LATIN else len(LATIN.findall(text))
    total = mine + other
    return round(100 * mine / total) if total else 0


def hard_share(annotation: object, language: str, bands: FrequencyBands) -> int:
    counts: dict[int, int] = {}
    for tokens in annotation.tokens.values():  # type: ignore[attr-defined]
        for token in tokens:
            band = bands.band(token.lemma, language)
            counts[band] = counts.get(band, 0) + 1
    total = sum(counts.values())
    if not total:
        return 0
    return round(sum(n for band, n in counts.items() if band >= LOOKED_UP) / total * 100)


def is_media(source: str) -> bool:
    return is_youtube(source) or is_audio(source) or is_video(source)


def read_candidates(path: Path) -> list[Candidate]:
    out: list[Candidate] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cells = [cell.strip() for cell in line.split("\t")]
        out.append(Candidate(*cells[:3]))
    return out


def pregate(candidate: Candidate, scratch: Path, language: str) -> None:
    """The media gates, run before the words are read. Sets `gate` and `text_source`."""
    if is_youtube(candidate.source):
        media = screen.from_ytdlp(describe(candidate.source))
        if not candidate.licence:
            candidate.licence = media.licence
        track = fetch_subtitles(candidate.source, scratch / re.sub(r"\W", "_", candidate.source))
        candidate.subtitles = str(track)
    else:
        if not candidate.subtitles:
            raise ValueError("a local recording needs a subtitle file after a tab")
        media = screen.from_ffprobe(
            tools.ffprobe_json(Path(candidate.source)),
            Path(candidate.source),
            licence=candidate.licence,
        )
    candidate.title = media.title
    candidate.gate = screen.gate(media, load_cues(Path(candidate.subtitles)), language=language)
    candidate.flags.extend(candidate.gate.flags)
    candidate.text_source = candidate.subtitles


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidates", type=Path, help="One source per line.")
    parser.add_argument("--language", default="he")
    parser.add_argument("--min-words", type=int, default=600)
    parser.add_argument("--max-words", type=int, default=3000, help="A single sitting.")
    parser.add_argument("--min-share", type=int, default=95, help="Percent in its own script.")
    parser.add_argument("--max-difficulty", type=int, default=20)
    parser.add_argument(
        "--min-coverage",
        type=int,
        default=screen.COVERAGE_MIN,
        help="Percent of a recording its subtitle track must reach.",
    )
    args = parser.parse_args()

    candidates = read_candidates(args.candidates)
    print(f"screening {len(candidates)} candidates", file=sys.stderr, flush=True)
    scratch = Path(tempfile.mkdtemp(prefix="screen-"))

    # Stage one: everything decidable without Stanza.
    kept: list[Candidate] = []
    for n, candidate in enumerate(candidates, 1):
        source = candidate.source
        try:
            if is_media(source):
                pregate(candidate, scratch, args.language)
                if candidate.gate is not None and not candidate.gate.passed:
                    why = candidate.gate.reason
                    print(f"  {n:>4} drop  {why:<12} {source}", file=sys.stderr, flush=True)
                    continue
            else:
                candidate.text_source = source
            document = ingest.load(candidate.text_source)
        except Exception as error:  # a candidate that will not fetch is not a failure
            print(f"  {n:>4} skip  {source} — {type(error).__name__}", file=sys.stderr, flush=True)
            continue
        candidate.title = candidate.title or document.title or ""
        text = "\n".join(b.text for b in document.blocks if getattr(b, "text", None))
        candidate.text = text
        candidate.words = len(text.split())
        candidate.share = language_share(text, args.language)
        why = ""
        if not args.min_words <= candidate.words <= args.max_words:
            why = f"{candidate.words}w"
        elif candidate.share < args.min_share:
            why = f"{candidate.share}% {args.language}"
        if why:
            print(f"  {n:>4} drop  {why:<12} {source}", file=sys.stderr, flush=True)
            continue
        kept.append(candidate)

    print(f"{len(kept)} to annotate", file=sys.stderr, flush=True)

    # Stage two: the annotator (DICTA for Hebrew) and the segmenter, built once.
    bands = FrequencyBands()
    segmenter = HebrewSegmenter()
    out: list[Screened] = []
    for n, candidate in enumerate(kept, 1):
        source = candidate.source
        try:
            document = ingest.load(candidate.text_source)
            annotation = Annotator().annotate(segment_document(document, segmenter))
            difficulty = hard_share(annotation, args.language, bands)
        except Exception as error:
            print(f"  {n:>4} fail  {source} — {type(error).__name__}", file=sys.stderr, flush=True)
            continue
        if difficulty > args.max_difficulty:
            print(f"  {n:>4} hard  d={difficulty:<3} {source}", file=sys.stderr, flush=True)
            continue
        opening = " ".join(candidate.text.split())[:90]
        out.append(Screened(candidate, difficulty, opening))
        kept_line = (
            f"  {n:>4} keep  d={difficulty:<3} {candidate.words:>5}w  {candidate.title[:40]}"
        )
        print(kept_line, file=sys.stderr, flush=True)

    # Ranked against the shelf: the band it is thinnest in first, then easiest. The
    # catalogue is imported here and not at the top because it reads a file on import
    # and a screen of somebody else's texts should not need one (targum-internal#131
    # measures the entries that still say 0, and until then the counts are partial).
    from targum.catalogue import CATALOGUE  # noqa: E402

    shelf = screen.shelf_bands(entry.difficulty for entry in CATALOGUE)
    print(f"shelf: {shelf}", file=sys.stderr)

    print(
        "difficulty\tband\twords\tminutes\tshare\tcoverage\twpm\taudio\t"
        "reader_publishable\tcorpus_exportable\tlicence\tflags\tsource\ttitle\topening"
    )
    for row in sorted(
        out, key=lambda r: (shelf[screen.band(r.difficulty)], r.difficulty, r.candidate.words)
    ):
        c = row.candidate
        minutes = max(1, round(c.words / 130))
        gate = c.gate
        flags = screen.licence_flags(c.licence)
        print(
            f"{row.difficulty}\t{screen.band(row.difficulty)}\t{c.words}\t{minutes}\t{c.share}\t"
            f"{gate.coverage if gate else ''}\t{gate.wpm if gate else ''}\t"
            f"{gate.audio if gate else ''}\t"
            f"{flags.reader_publishable}\t{flags.corpus_exportable}\t{c.licence}\t"
            f"{'; '.join(c.flags)}\t{c.source}\t{c.title}\t{row.opening}"
        )
    print(f"\n{len(out)} of {len(candidates)} survive", file=sys.stderr)


if __name__ == "__main__":
    main()
