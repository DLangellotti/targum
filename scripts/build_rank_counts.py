"""Build `src/targum/rank_counts.json`, the rank-to-count conversion `level.text_rung`
reads for the CEFR ladder (targum-internal#659).

A text's level is the frequency rank R covering 90% of its running words. The CEFR
thresholds are counts of known lemmas in the common bands (`level.common`). C(R) is how
many lemmas `common` can count that rank at or below R: a lemma of the language's lexicon
whose dictionary form is at Zipf 4.1 or above, the three common bands. It is a
conversion, not evidence about learners.

usage (offline, free; the lexicons are lookups and never shipped):

    PYTHONPATH=$PWD/src .venv/bin/python scripts/build_rank_counts.py \
        --morph-it /path/to/morph-it_048.txt

French reads Morphalou 3.1 and Russian OpenRussian from the model directory
(`targum models fetch morphalou` / `openrussian`). Italian reads Morph-it! 0.48, downloaded
by hand from https://docs.sslmit.unibo.it/doku.php?id=resources:morph-it and deleted after.
"""

from __future__ import annotations

import argparse
import datetime
import importlib.metadata
import json
from pathlib import Path

from wordfreq import zipf_frequency

from targum.annotate import frequency, morphalou, openrussian
from targum.annotate.difficulty import _french_sums

#: Where the table is sampled: every STEP ranks, from 0 to the frequency list's end.
STEP = 50
OUT = Path(__file__).resolve().parent.parent / "src" / "targum" / "rank_counts.json"
#: The lowest Zipf in the common bands (`frequency.CUTS`, the "moderate" cut).
COMMON_CUT = frequency.CUTS[2]

#: Morph-it! tags that are not a vocabulary word: names, punctuation, symbols.
ITALIAN_SKIP = {"NPR", "PON", "SENT", "SYM", "NE", "ABL", "SMI"}


def french() -> set[str]:
    sums = _french_sums()
    if sums is None:
        raise SystemExit("Morphalou is not in the model directory: targum models fetch morphalou")
    return set(sums)


def russian() -> set[str]:
    return set(openrussian.load().entries)


def italian(path: Path) -> set[str]:
    out: set[str] = set()
    with path.open(encoding="latin-1") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            _form, lemma, tag = parts
            if tag.split(":")[0].split("-")[0] in ITALIAN_SKIP or not lemma.isalpha():
                continue
            out.add(lemma.lower())
    return out


def curve(language: str, lemmas: set[str]) -> list[int]:
    """C(R) at R = 0, STEP, 2·STEP … up to the end of the frequency list."""
    counted = sorted(
        place
        for word, place in frequency.ranks(language).items()
        if word in lemmas and zipf_frequency(word, language) >= COMMON_CUT
    )
    points: list[int] = []
    at = 0
    for edge in range(0, frequency.RANKED + 1, STEP):
        while at < len(counted) and counted[at] <= edge:
            at += 1
        points.append(at)
    while len(points) > 1 and points[-1] == points[-2]:
        points.pop()  # past the last countable lemma C(R) is flat: keep the ceiling once
    return points


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--morph-it", type=Path, required=True)
    args = parser.parse_args()
    if not morphalou.available():
        raise SystemExit("Morphalou is not in the model directory")
    tables = {
        "fr": curve("fr", french()),
        "ru": curve("ru", russian()),
        "it": curve("it", italian(args.morph_it)),
    }
    out = {
        "about": (
            "A conversion, not evidence. C(R): how many lemmas level.common can count "
            "(dictionary form at wordfreq Zipf >= 4.1, the three common bands) rank at or "
            "below R in wordfreq's list, sampled every `step` ranks from 0; past the last "
            "point C(R) is the last value, the language's ceiling. It says nothing about "
            "learners: it puts a text's frequency rank on the same scale as the CEFR "
            "thresholds (targum-internal#659). Counts only; no word of any lexicon or of "
            "wordfreq is in this file. Built by scripts/build_rank_counts.py."
        ),
        "built": datetime.date.today().isoformat(),
        "wordfreq": importlib.metadata.version("wordfreq"),
        "lexicons": {
            "fr": "Morphalou 3.1 (ATILF/CNRS, LGPL-LR)",
            "ru": f"OpenRussian russian-dictionary {openrussian.COMMIT[:12]} (CC BY-SA 4.0)",
            "it": "Morph-it! 0.48 (Zanchetta and Baroni, CC BY-SA 2.0 / LGPL)",
        },
        "step": STEP,
        "counts": tables,
    }
    text = json.dumps(out, ensure_ascii=False, indent=1)
    for points in tables.values():  # one line a language, not one a number
        spread = json.dumps(points, indent=1).replace("\n", "\n  ")
        text = text.replace(spread, json.dumps(points, separators=(",", ":")))
    OUT.write_text(text + "\n", encoding="utf-8")
    for language, points in tables.items():
        print(language, "ceiling", points[-1], "reached by rank", (len(points) - 1) * STEP)


if __name__ == "__main__":
    main()
