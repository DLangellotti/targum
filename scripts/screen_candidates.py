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

Output is a TSV of survivors, ranked easiest first, carrying everything an `Entry` needs
except the blurb — which is a judgement and stays a person's job.

    uv run python scripts/screen_candidates.py candidates.txt > shortlist.tsv
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import ingest  # noqa: E402
from targum.annotate import Annotator  # noqa: E402
from targum.annotate.frequency import FrequencyBands  # noqa: E402
from targum.segment import StanzaSegmenter, segment_document  # noqa: E402

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
class Screened:
    source: str
    title: str
    words: int
    share: int
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("candidates", type=Path, help="One source per line.")
    parser.add_argument("--language", default="he")
    parser.add_argument("--min-words", type=int, default=600)
    parser.add_argument("--max-words", type=int, default=3000, help="A single sitting.")
    parser.add_argument("--min-share", type=int, default=95, help="Percent in its own script.")
    parser.add_argument("--max-difficulty", type=int, default=20)
    args = parser.parse_args()

    sources = [
        line.strip()
        for line in args.candidates.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    print(f"screening {len(sources)} candidates", file=sys.stderr, flush=True)

    # Stage one: everything decidable without Stanza.
    kept: list[tuple[str, str, str, int, int]] = []
    for n, source in enumerate(sources, 1):
        try:
            document = ingest.load(source)
        except Exception as error:  # a candidate that will not fetch is not a failure
            print(f"  {n:>4} skip  {source} — {type(error).__name__}", file=sys.stderr, flush=True)
            continue
        text = "\n".join(b.text for b in document.blocks if getattr(b, "text", None))
        words = len(text.split())
        share = language_share(text, args.language)
        why = ""
        if not args.min_words <= words <= args.max_words:
            why = f"{words}w"
        elif share < args.min_share:
            why = f"{share}% {args.language}"
        if why:
            print(f"  {n:>4} drop  {why:<12} {source}", file=sys.stderr, flush=True)
            continue
        kept.append((source, document.title or "", text, words, share))

    print(f"{len(kept)} to annotate", file=sys.stderr, flush=True)

    # Stage two: Stanza, loaded once.
    bands = FrequencyBands()
    segmenter = StanzaSegmenter()
    out: list[Screened] = []
    for n, (source, title, text, words, share) in enumerate(kept, 1):
        try:
            document = ingest.load(source)
            annotation = Annotator().annotate(segment_document(document, segmenter))
            difficulty = hard_share(annotation, args.language, bands)
        except Exception as error:
            print(f"  {n:>4} fail  {source} — {type(error).__name__}", file=sys.stderr, flush=True)
            continue
        if difficulty > args.max_difficulty:
            print(f"  {n:>4} hard  d={difficulty:<3} {source}", file=sys.stderr, flush=True)
            continue
        opening = " ".join(text.split())[:90]
        out.append(Screened(source, title, words, share, difficulty, opening))
        kept_line = f"  {n:>4} keep  d={difficulty:<3} {words:>5}w  {title[:40]}"
        print(kept_line, file=sys.stderr, flush=True)

    print("difficulty\twords\tminutes\tshare\tsource\ttitle\topening")
    for row in sorted(out, key=lambda r: (r.difficulty, r.words)):
        minutes = max(1, round(row.words / 130))
        print(
            f"{row.difficulty}\t{row.words}\t{minutes}\t{row.share}\t"
            f"{row.source}\t{row.title}\t{row.opening}"
        )
    print(f"\n{len(out)} of {len(sources)} survive", file=sys.stderr)


if __name__ == "__main__":
    main()
