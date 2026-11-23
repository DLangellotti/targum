"""The emphatic-state rule against Open Scriptures' state letter (design.md §12, 2026-10-25).

`annotate/aramaic_state.emphatic` reads the emphatic off the pointing: a qamats before the
final א, less the particles, the verbs the hand table knows and the weak-verb perfects.
Open Scriptures tags the state of every Aramaic noun, adjective and participle in Daniel
and Ezra by hand (`Ncmsd`: d is determined, which is the emphatic), so it is the gold here:
the only Aramaic with state tagged by a person.

A word is gold when any piece is a noun, adjective or participle tagged `d`. Proper names
are left out, since a name's state is not something the lens shows. Every word of every
Aramaic verse is scored, not only the nouns: the lens lights words without knowing which
are nouns, so a verb it lights is a wrong light, and precision counts it.

**Not held out.** The rule's three checks were found reading this text and Onkelos Genesis
1–3. The floor guards against it getting worse; it is not an estimate on unseen text.

    .venv/bin/python scripts/eval_aramaic_state.py

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
from targum.annotate.aramaic_state import NAME, emphatic  # noqa: E402
from targum.ingest.fetch.sefaria import BIBLICAL_ARAMAIC  # noqa: E402

STAGE = "lemma"
CORPUS = "oshb-aramaic"
SYSTEM = NAME

#: OSHB's book codes for Sefaria's names.
CODES = {"Daniel": "Dan", "Ezra": "Ezra"}


def aramaic(book: str, name: str) -> bool:
    """Whether an OSIS verse name (`Dan.3.1`) is in the Aramaic of its book."""
    _, chapter, verse = name.split(".")
    at = (int(chapter), int(verse))
    return any(first <= at <= last for first, last in BIBLICAL_ARAMAIC.get(book, ()))


def gold(word: oshb.Word) -> bool:
    """Whether Open Scriptures tagged a piece of this word as in the emphatic state."""
    for code in word.morph:
        if not code or code.startswith("Np"):
            continue
        if code[0] in "NA" and code[-1] == "d":
            return True
        # A participle: V, its stem, then r (active) or s (passive), and its state last.
        if code[0] == "V" and len(code) >= 6 and code[2] in "rs" and code[-1] == "d":
            return True
    return False


def score(book: str) -> tuple[Counter[str], Counter[str]]:
    counts: Counter[str] = Counter()
    wrong: Counter[str] = Counter()
    for name, words in oshb.verses(CODES[book]):
        if not aramaic(book, name):
            continue
        for word in words:
            marked, said = gold(word), emphatic(word.text)
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
            today, STAGE, SYSTEM, SYSTEM, "emphatic_precision", precision,
            counts["tp"] + counts["fp"], CORPUS, note,
        ),
        evals.Row(
            today, STAGE, SYSTEM, SYSTEM, "emphatic_recall", recall,
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
