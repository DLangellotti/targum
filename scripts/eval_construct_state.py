"""The Biblical construct state against Open Scriptures' own state letter
(targum-internal#454, `oshb/7`).

A stored Biblical token says `Definite=Cons` where `scripture.word_features` reads a
construct off the word's content piece (`Ncmpc`, the `c` at index 4) and no pronoun is
suffixed after it. The gold here is read off the word's pieces independently: some noun or
adjective piece (not a proper noun) carries state `c`, and no suffix piece (`S…`) follows
it. So the score checks the piece the build chooses and the suffix exclusion, not a copy
of the letter.

**Held out.** The rule was checked on the Torah; the rows are every Hebrew word outside it,
the Aramaic chapters of Daniel and Ezra left out as `eval_pronoun_suffixes.py` leaves them.

    .venv/bin/python scripts/eval_construct_state.py

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
sys.path.insert(0, str(ROOT / "scripts"))

from eval_pronoun_suffixes import BOOKS, CORPUS, STAGE, TORAH, aramaic  # noqa: E402

from targum import evals  # noqa: E402
from targum.annotate import oshb, scripture  # noqa: E402

SYSTEM = "oshb-state/1"


def gold(word: oshb.Word) -> bool:
    """Whether Open Scriptures tags a bare construct noun or adjective in this word."""
    for at, code in enumerate(word.morph):
        if code[:1] in ("N", "A") and code[:2] != "Np" and len(code) > 4 and code[4] == "c":
            if not any(piece.startswith("S") for piece in word.morph[at + 1 :]):
                return True
    return False


def ours(word: oshb.Word) -> bool:
    """Whether the token the build stores for this word says it is a construct."""
    return "Definite=Cons" in (scripture.word_features(word) or "")


def score(books: tuple[str, ...]) -> tuple[Counter[str], Counter[str]]:
    counts: Counter[str] = Counter()
    wrong: Counter[str] = Counter()
    for book in books:
        for ref, words in oshb.verses(book):
            if aramaic(ref):
                continue
            for word in words:
                want, said = gold(word), ours(word)
                if want and said:
                    counts["tp"] += 1
                    continue
                if said:
                    counts["fp"] += 1
                if want:
                    counts["fn"] += 1
                if said or want:
                    wrong[
                        f"{'+' if said else '-'}/{'+' if want else '-'} {'/'.join(word.morph)}"
                    ] += 1
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

    seen, _ = score(TORAH)
    precision, recall = rates(seen)
    print(f"(the Torah, where the rule was checked: precision {precision}, recall {recall})")

    held = tuple(book for book in BOOKS if book not in TORAH)
    counts, wrong = score(held)
    precision, recall = rates(counts)
    for line, n in wrong.most_common(12):
        print(f"  {n:4} {line}")
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
            "construct_precision",
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
            "construct_recall",
            recall,
            counts["tp"] + counts["fn"],
            CORPUS,
            note,
        ),
    ]
    for row in rows:
        print(f"{row.metric:20} {row.score:.4f}  n={row.n}  {row.system}", flush=True)
    if not args.dry:
        evals.append(rows, args.ledger)
        print(f"appended {len(rows)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
