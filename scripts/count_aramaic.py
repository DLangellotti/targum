"""Count the Aramaic frequency list from targum's own Aramaic (targum-internal G1).

wordfreq has no Aramaic list, so every Aramaic text measured 0 and Aramaic got no ladder
(design.md, 2026-10-08). There is no outside list to buy either: nobody has written Jewish
Aramaic as a living language for a thousand years, so the only honest corpus is the one
on the shelf. This counts it: Targum Onkelos, Targum Jonathan on the Torah and the
Prophets, the Targums of the Writings, and the Aramaic chapters of Daniel and Ezra — every
public-domain Aramaic text the catalogue holds.

**Counted the way the reader files a word**, through `annotate.aramaic.tokens`, the
annotator itself. Where the hand table knows a form the count goes to its headword, so
`יתיה`, `יתהון` and `ית` are one word; everything else is counted under its own letters,
which is what a reader keeps it under. That second half overstates how many words
Aramaic has — `ארעא` and `בארעהון` are counted apart until the table grows (G2) — so a
text's measure errs hard, never easy. Names of the verse are left out: a name is not a
word to learn, which is the rule `difficulty.hard_share` applies.

**Only the words met twice or more are written**, with the total they are a share of. A
word met once is rare by any reckoning: absent from the list it is scored as met once,
which puts it in band 5 among the words a learner looks up, where a single sighting in
half a million words belongs.

    PYTHONPATH=src .venv/bin/python scripts/count_aramaic.py

Fetches each text from Sefaria once (free, no model) and caches it under `--cache`, so a
recount reads the disk. Writes `src/targum/annotate/aramaic_frequency.json` beside the
module that reads it. Nothing is re-annotated by a recount: the list feeds the difficulty
measure, and the catalogue takes its new numbers from `scripts/measure_difficulty.py`.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import ingest  # noqa: E402
from targum.annotate import aramaic  # noqa: E402
from targum.annotate.aramaic_frequency import MIN_COUNT  # noqa: E402
from targum.models import Document  # noqa: E402
from targum.paths import cache_dir  # noqa: E402
from targum.segment import HebrewSegmenter, segment_document  # noqa: E402

DEFAULT_OUT = (
    Path(__file__).resolve().parents[1] / "src" / "targum" / "annotate" / "aramaic_frequency.json"
)
DEFAULT_CACHE = cache_dir() / "aramaic-count"

#: The books whose Aramaic chapters are read as part of a Hebrew document, marked per
#: block (`sefaria.BIBLICAL_ARAMAIC`). Their Hebrew is not counted.
BIBLICAL = ("sefaria:Daniel", "sefaria:Ezra")


def sources() -> list[str]:
    """Every Aramaic row of the catalogue, then the two books with Aramaic chapters."""
    from targum.catalogue import CATALOGUE

    rows = [entry.source for entry in CATALOGUE if str(entry.language) == "arc"]
    return [*rows, *BIBLICAL]


def fetched(source: str, cache: Path) -> Document:
    path = cache / (source.replace(":", "_").replace(" ", "_") + ".json")
    if path.is_file():
        return Document.model_validate_json(path.read_text(encoding="utf-8"))
    language = None if source in BIBLICAL else "arc"
    document = ingest.load(source, language=language)
    cache.mkdir(parents=True, exist_ok=True)
    path.write_text(document.model_dump_json(), encoding="utf-8")
    return document


def count(sources: list[str], cache: Path) -> tuple[collections.Counter[str], int, int]:
    counts: collections.Counter[str] = collections.Counter()
    texts = 0
    for source in sources:
        document = fetched(source, cache)
        segmented = segment_document(document, HebrewSegmenter())
        seen = 0
        for segment in segmented.segments:
            if not aramaic.is_aramaic(segment, document.language):
                continue
            for token in aramaic.tokens(segment):
                if token.pos == "PROPN" or not token.lemma:
                    continue
                counts[token.lemma] += 1
                seen += 1
        texts += 1 if seen else 0
        print(f"{source}: {seen:,} words", file=sys.stderr)
    return counts, sum(counts.values()), texts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    counts, total, texts = count(sources(), args.cache)
    kept = {word: n for word, n in counts.most_common() if n >= MIN_COUNT}
    args.out.write_text(
        json.dumps(
            {"tokens": total, "texts": texts, "counts": kept},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"{total:,} words in {texts} texts, {len(counts):,} distinct, "
        f"{len(kept):,} met {MIN_COUNT}+ times -> {args.out}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
