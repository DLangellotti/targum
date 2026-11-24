"""Learn which Hebrew word each Onkelos word renders, from the verse pairs (targum-internal
G3; `annotate/onkelos_align.py` says how it is read).

Onkelos from Sefaria (the cache `scripts/count_aramaic.py` keeps), the Hebrew from Open
Scriptures, verse by verse, the five books. IBM Model 1 both ways, with a pull toward the
diagonal, `ROUNDS` rounds: no model is asked anything and nothing is bought. Writes
`src/targum/annotate/onkelos_lexicon.json`, keeping for each word the words it goes with
at `KEEP` or more of its weight.

    PYTHONPATH=src .venv/bin/python scripts/count_onkelos_alignment.py

Needs OSHB on disk (`targum models fetch scripture`) and the five books in the Aramaic
cache (`scripts/count_aramaic.py` fetches them once, free).
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from count_aramaic import DEFAULT_CACHE, fetched  # noqa: E402

from targum.annotate import oshb  # noqa: E402
from targum.annotate.onkelos_align import LEXICON, PULL, norm, words  # noqa: E402

BOOKS = {
    "Genesis": "Gen",
    "Exodus": "Exod",
    "Leviticus": "Lev",
    "Numbers": "Num",
    "Deuteronomy": "Deut",
}
ROUNDS = 8
KEEP = 0.1
#: The weight an unrendered word is given against every word of its verse.
EMPTY = 0.2

Pair = tuple[str, list[str], list[str]]


def pairs(cache: Path) -> list[Pair]:
    """(ref, Onkelos words, Hebrew words) for every verse both sides have."""
    out: list[Pair] = []
    for book, code in BOOKS.items():
        document = fetched(f"sefaria:arc:{book}", cache)
        onkelos = {
            block.ref.removeprefix("Onkelos ").removeprefix(f"{book} "): block.text
            for block in document.blocks
            if block.ref
        }
        for name, hebrew in oshb.verses(code):
            _, chapter, verse = name.split(".")
            ref = f"{chapter}:{verse}"
            if ref not in onkelos:
                continue
            out.append(
                (
                    f"{book} {ref}",
                    [norm(word) for word in words(onkelos[ref])],
                    [norm(word.text) for word in hebrew],
                )
            )
    return out


def train(verses: list[Pair], backwards: bool = False) -> dict[str, dict[str, float]]:
    """How likely each source word is to go with each target word: source → target →
    share, "" the share left unrendered."""
    weight: dict[tuple[str, str], float] = collections.defaultdict(lambda: 1.0)
    for _ in range(ROUNDS):
        counts: dict[tuple[str, str], float] = collections.defaultdict(float)
        totals: dict[str, float] = collections.defaultdict(float)
        for _ref, aramaic, hebrew in verses:
            source, target = (hebrew, aramaic) if backwards else (aramaic, hebrew)
            n, m = len(source), len(target)
            for i, word in enumerate(source):
                shares = [
                    weight[(word, other)] * math.exp(-PULL / 1.5 * abs(i / n - j / max(m, 1)))
                    for j, other in enumerate(target)
                ]
                shares.append(weight[(word, "")] * EMPTY)
                total = sum(shares)
                for other, share in zip([*target, ""], shares, strict=True):
                    counts[(word, other)] += share / total
                    totals[other] += share / total
        weight = collections.defaultdict(
            float, {pair: n / totals[pair[1]] for pair, n in counts.items()}
        )
    table: dict[str, dict[str, float]] = collections.defaultdict(dict)
    for (word, other), share in weight.items():
        if share >= KEEP:
            table[word][other] = round(share, 4)
    return dict(table)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out", type=Path, default=LEXICON)
    args = parser.parse_args()
    if not oshb.available():
        raise SystemExit("OSHB is not on disk; run `targum models fetch scripture` first")
    verses = pairs(args.cache)
    renders = train(verses)
    rendered = train(verses, backwards=True)
    args.out.write_text(
        json.dumps(
            {"verses": len(verses), "renders": renders, "rendered": rendered},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"{len(verses):,} verse pairs, {len(renders):,} Aramaic and {len(rendered):,} "
        f"Hebrew spellings -> {args.out}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
