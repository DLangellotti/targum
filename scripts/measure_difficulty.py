"""How hard each catalogue text is, measured off the text itself.

The library filters on difficulty, and a filter is only worth having if the number
behind it is true. So this counts rather than judges.

**What it counts:** the share of running words whose dictionary form is uncommon in the
language as it is written today — bands 4 to 6 of the reader's own six-band scale, which
is where a learner starts looking things up. Psalms comes out at 35%, Genesis at 23%,
Esther at 17%, and those are in the order any Hebrew reader would put them.

**One ruler for everything.** A Tanakh is banded against the Tanakh when it is read —
that is the honest question for someone reading scripture, and `annotate/biblical.py`
explains why. It is the wrong ruler here: a library that mixes Samuel with a news
article cannot rank them by two different scales and call the result a difficulty. So
this re-bands every text against modern frequency, and the library's register filter is
what says which Hebrew a text is in.

**Two things it does not measure.** Sentence length and syntax, both of which make
Brenner harder than his vocabulary suggests. The number is about words, and the library
says so.

Run when the catalogue changes; write what it prints into `catalogue.py`. Kept out of
the package because it is minutes of Stanza over a hundred thousand words, and no reader
should ever wait for it.

    uv run python scripts/measure_difficulty.py [--out targum-out] [--only <id>]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import ingest  # noqa: E402
from targum.annotate import Annotator  # noqa: E402
from targum.annotate.base import NOT_VOCABULARY  # noqa: E402
from targum.annotate.frequency import FrequencyBands  # noqa: E402
from targum.catalogue import CATALOGUE, Entry  # noqa: E402
from targum.models import Annotation, read_artifact  # noqa: E402
from targum.segment import StanzaSegmenter, segment_document  # noqa: E402

#: Where a word stops being one a reader knows and starts being one they look up.
LOOKED_UP = 4

_bands = FrequencyBands()


@lru_cache(maxsize=200_000)
def _band(lemma: str, language: str) -> int:
    return _bands.band(lemma, language)


def hard_share(annotation: Annotation, language: str) -> int:
    """The percentage of running words a learner would have to look up."""
    counts: Counter[int] = Counter()
    for tokens in annotation.tokens.values():
        for token in tokens:
            # The same rule the server applies to an upload: a name is a token the
            # reader can tap, not a word they have to learn.
            if token.pos in NOT_VOCABULARY:
                continue
            counts[_band(token.lemma, language)] += 1
    total = sum(counts.values())
    if not total:
        return 0
    return round(sum(n for band, n in counts.items() if band >= LOOKED_UP) / total * 100)


def on_disk(root: Path, source: str) -> Annotation | None:
    """An annotation a build already wrote, which is the same lemmas for free.

    The bands in it may have been counted against the Tanakh; only the lemmas are read
    here, and they are re-banded against one ruler above.
    """
    for document in root.glob("*/*/document.json"):
        try:
            if json.loads(document.read_text(encoding="utf-8")).get("source") != source:
                continue
        except (OSError, json.JSONDecodeError):
            continue
        annotation = read_artifact(Annotation, document.parent / "annotation.json")
        if annotation is not None:
            return annotation
    return None


def measured(entry: Entry, root: Path) -> tuple[int, str]:
    annotation = on_disk(root, entry.source)
    if annotation is not None:
        return hard_share(annotation, entry.language), "on disk"
    # Nothing built yet: fetch it and read it here. Free — the network and Stanza, and no
    # model is asked for anything.
    document = ingest.load(entry.source)
    segmented = segment_document(document, StanzaSegmenter())
    annotation = Annotator().annotate(segmented)
    return hard_share(annotation, entry.language), "measured now"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("targum-out"))
    parser.add_argument("--only", default="", help="One entry id, for a quick check.")
    args = parser.parse_args()

    for entry in CATALOGUE:
        if args.only and entry.id != args.only:
            continue
        try:
            share, how = measured(entry, args.out)
        except Exception as error:  # a catalogue entry that will not fetch is not fatal
            print(f"{entry.id:22} — {error}", flush=True)
            continue
        print(f"{entry.id:22} difficulty={share:3}  ({how}, was {entry.difficulty})", flush=True)


if __name__ == "__main__":
    main()
