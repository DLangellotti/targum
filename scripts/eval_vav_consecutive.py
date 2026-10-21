"""The vav-consecutive rule against Open Scriptures' own tagging (targum-internal#449).

`annotate/vav_consecutive.consecutive` reads the narrative vav off the pointing: וַ with the
prefix letter doubled after it, וַיְ, and וָא. Open Scriptures marks the same form by hand,
the aspect letter `w` in a verb's code (`Vqw3ms`), so it is the gold here. Scoring
`annotate/scripture.py` against it would be scoring OSHB against itself, since that path
reads the code; the rule reads only the pointed word, which is what a text has where the
tagging does not line up, and what the build reads for every Biblical text.

**Held out.** The rule was written from the grammar and checked on Genesis 1 before it was
scored, and was not changed after. The rows are every word outside the Torah, the Prophets
and the Writings; the Torah is printed for the reader and never written. A word is gold
when any of its pieces is a verb tagged `w`, so וישלחהו, with its suffix, counts once.

    .venv/bin/python scripts/eval_vav_consecutive.py

No key and no network; OSHB must be on disk (`targum models fetch scripture`).
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from targum import evals  # noqa: E402
from targum.annotate import oshb  # noqa: E402
from targum.annotate.vav_consecutive import consecutive  # noqa: E402

STAGE = "lemma"
CORPUS = "oshb-wlc"
SYSTEM = "vav-rule/1"

#: Where the rule was written and checked, and so not scored.
TORAH = ("Gen", "Exod", "Lev", "Num", "Deut")

#: Every book OSHB tags, in the Bible's order: the Torah, the Prophets, the Writings.
BOOKS = (
    *TORAH,
    "Josh", "Judg", "1Sam", "2Sam", "1Kgs", "2Kgs", "Isa", "Jer", "Ezek", "Hos", "Joel",
    "Amos", "Obad", "Jonah", "Mic", "Nah", "Hab", "Zeph", "Hag", "Zech", "Mal", "Ps",
    "Prov", "Job", "Song", "Ruth", "Lam", "Eccl", "Esth", "Dan", "Ezra", "Neh", "1Chr",
    "2Chr",
)  # fmt: skip


def gold(word: oshb.Word) -> bool:
    """Whether Open Scriptures tagged a piece of this word as the vav-consecutive."""
    return any(code.startswith("V") and len(code) > 2 and code[2] == "w" for code in word.morph)


def score(books: tuple[str, ...]) -> tuple[Counter[str], Counter[str]]:
    """True and false positives and negatives over the books, and the misses by word."""
    counts: Counter[str] = Counter()
    wrong: Counter[str] = Counter()
    for book in books:
        for _, words in oshb.verses(book):
            for word in words:
                marked, said = gold(word), consecutive(word.text)
                if marked and said:
                    counts["tp"] += 1
                elif said:
                    counts["fp"] += 1
                    wrong[f"+ {oshb.bare(word.text)} {'/'.join(word.morph)}"] += 1
                elif marked:
                    counts["fn"] += 1
                    wrong[f"- {oshb.bare(word.text)} {'/'.join(word.morph)}"] += 1
    return counts, wrong


def rates(counts: Counter[str]) -> tuple[float, float]:
    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    return round(tp / max(1, tp + fp), 4), round(tp / max(1, tp + fn), 4)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args(argv)

    if not oshb.available():
        raise SystemExit("OSHB is not on disk; run `targum models fetch scripture` first")
    held = tuple(book for book in BOOKS if book not in TORAH)

    seen, _ = score(TORAH)
    precision, recall = rates(seen)
    print(f"(the Torah, where the rule was checked: precision {precision}, recall {recall})")

    counts, wrong = score(held)
    precision, recall = rates(counts)
    for line, n in wrong.most_common(12):
        print(f"  {n:3} {line}")
    note = evals.pinned(
        f"books={len(held)} tp={counts['tp']} fp={counts['fp']} fn={counts['fn']}",
        [oshb.root() / f"{book}.json" for book in held],
    )
    today = date.today().isoformat()
    rows = [
        evals.Row(
            today,
            STAGE,
            SYSTEM,
            SYSTEM,
            "vav_precision",
            precision,
            counts["tp"] + counts["fp"],
            CORPUS,
            note,
        ),
        evals.Row(
            today,
            STAGE,
            SYSTEM,
            SYSTEM,
            "vav_recall",
            recall,
            counts["tp"] + counts["fn"],
            CORPUS,
            note,
        ),
    ]
    for row in rows:
        print(f"{row.metric:16} {row.score:.4f}  n={row.n}  {row.system}", flush=True)
    if not args.dry:
        evals.append(rows, args.ledger)
        print(f"appended {len(rows)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
