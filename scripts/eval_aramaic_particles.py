"""The ד־ rule against Open Scriptures' דִּי (design.md §12, "Aramaic's lenses", 2026-10-25).

`annotate/aramaic_particles.particle` says ד־ where the Aramaic annotator found a word with
ד taken off the front, or the word דִּי. Open Scriptures files דִּי under one lexeme, 1768,
whatever it does in the sentence: "which", "of", "that", "because". So a word is gold when
any piece is that lexeme, and every word of every Aramaic verse of Daniel and Ezra is
scored, each read the way the build reads it (`annotate.aramaic.tokens`).

Biblical Aramaic mostly writes the particle apart, so this measures דִּי far more than the
prefix: a guard, not an estimate on Onkelos.

    .venv/bin/python scripts/eval_aramaic_particles.py

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
from targum.annotate.aramaic import tokens  # noqa: E402
from targum.annotate.aramaic_particles import DALET, NAME, particle  # noqa: E402
from targum.ingest.fetch.sefaria import BIBLICAL_ARAMAIC  # noqa: E402
from targum.models import Segment  # noqa: E402

STAGE = "lemma"
CORPUS = "oshb-aramaic"
SYSTEM = NAME

CODES = {"Daniel": "Dan", "Ezra": "Ezra"}

#: Strong's number for דִּי.
DI = "1768"


def aramaic(book: str, name: str) -> bool:
    _, chapter, verse = name.split(".")
    at = (int(chapter), int(verse))
    return any(first <= at <= last for first, last in BIBLICAL_ARAMAIC.get(book, ()))


def said(text: str) -> bool:
    """Whether the build would light this one word for ד־."""
    segment = Segment(id="w", block_id="w", block_index=0, index=0, text=text, language="arc")
    return any(particle(token) == DALET for token in tokens(segment))


def score(book: str) -> tuple[Counter[str], Counter[str]]:
    counts: Counter[str] = Counter()
    wrong: Counter[str] = Counter()
    for name, words in oshb.verses(CODES[book]):
        if not aramaic(book, name):
            continue
        for word in words:
            marked = any(lexeme.strip().rstrip(" abcdefgh") == DI for lexeme in word.lexemes)
            lit = said(word.text)
            if marked and lit:
                counts["tp"] += 1
            elif lit:
                counts["fp"] += 1
                wrong[f"+ {oshb.bare(word.text)} {'/'.join(word.lexemes)}"] += 1
            elif marked:
                counts["fn"] += 1
                wrong[f"- {oshb.bare(word.text)} {'/'.join(word.lexemes)}"] += 1
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
    counts: Counter[str] = Counter()
    wrong: Counter[str] = Counter()
    for book in BIBLICAL_ARAMAIC:
        each, missed = score(book)
        print(f"({book}: precision {rates(each)[0]}, recall {rates(each)[1]})")
        counts += each
        wrong += missed
    precision, recall = rates(counts)
    for line, n in wrong.most_common(12):
        print(f"  {n:3} {line}")
    note = evals.pinned(
        f"books={len(BIBLICAL_ARAMAIC)} tp={counts['tp']} fp={counts['fp']} fn={counts['fn']}",
        [oshb.root() / f"{CODES[book]}.json" for book in BIBLICAL_ARAMAIC],
    )
    today = date.today().isoformat()
    rows = [
        evals.Row(
            today, STAGE, SYSTEM, SYSTEM, "dalet_precision", precision,
            counts["tp"] + counts["fp"], CORPUS, note,
        ),
        evals.Row(
            today, STAGE, SYSTEM, SYSTEM, "dalet_recall", recall,
            counts["tp"] + counts["fn"], CORPUS, note,
        ),
    ]  # fmt: skip
    for row in rows:
        print(f"{row.metric:20} {row.score:.4f}  n={row.n}  {row.system}", flush=True)
    if not args.dry:
        evals.append(rows, args.ledger)
        print(f"appended {len(rows)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
