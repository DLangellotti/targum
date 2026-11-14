"""French register on the card, scored against a hand-written gold (French hard spot 7).

`annotate/french_register.py` says two things of a French line: a negation said without
its *ne* (*je sais pas*), with the formal clause beside it, and an *on* the sentence shows
means "we". This scores both against `evals/french-register-gold.jsonl`: 134 sentences,
103 written on 2026-11-14 by the builder seat as ling-fr (her own read is pending),
across spoken, neutral and formal French, traps included (*un pas*, *une personne*,
*plus chaud*, *de rien*, *si jamais*, *non plus*), and 31 from the public-domain French
shelf (Perrault, Daudet, Maupassant, Allais), each verbatim from
`evals/french-said-gold.jsonl`. Every *ne* dropped is marked at the clause's first
negator with the formal clause, and every *on* is read "we" or "other".

- **nedrop_precision**, **nedrop_recall**: the negators the rule names against the gold's.
- **formal_accuracy**: of the drops it names rightly, the share whose formal clause is the
  gold's, letter for letter (case and apostrophe aside).
- **on_we_precision**, **on_we_recall**: the *on* the card calls "we" against the gold's.

The rule runs on the words alone, with no tagger: on the page the tagger's part of speech
can only refuse a negator, so the page says less than is scored here, never more.

    python scripts/eval_register.py [--record]

No key, no network, no spend.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from targum import evals  # noqa: E402
from targum.annotate import french_register  # noqa: E402

GOLD = ROOT / "evals" / "french-register-gold.jsonl"
STAGE = "register"
CORPUS = "fr-register-own"
SYSTEM = "register-rule"
VERSION = f"{SYSTEM}/1"


def _same(one: str, other: str) -> bool:
    def flat(said: str) -> str:
        return " ".join(said.lower().replace("’", "'").split())

    return flat(one) == flat(other)


def score(rows: list[dict[str, object]], *, quiet: bool = False) -> dict[str, tuple[float, int]]:
    """Each metric's score and the count it is over."""
    named = right = in_gold = formal_right = 0
    called_we = we_right = gold_we = 0
    for row in rows:
        sentence = str(row["sentence"])
        words = french_register.words_of(sentence)
        gold_drops = {(int(d[0]), int(d[1])): str(d[3]) for d in row["ne_dropped"]}  # type: ignore[attr-defined]
        in_gold += len(gold_drops)
        for found in french_register.ne_dropped(sentence, words):
            word = words[found.negator]
            named += 1
            formal = gold_drops.get((word.start, word.end))
            if formal is None:
                if not quiet:
                    print(f"  wrong drop: {word.surface} | {sentence}")
                continue
            right += 1
            if _same(found.formal, formal):
                formal_right += 1
            elif not quiet:
                print(f"  formal: {found.formal!r} for {formal!r} | {sentence}")
        found_at = {
            (words[f.negator].start, words[f.negator].end)
            for f in french_register.ne_dropped(sentence, words)
        }
        for at in gold_drops:
            if at not in found_at and not quiet:
                print(f"  missed drop: {sentence[at[0] : at[1]]} | {sentence}")
        gold_on = {(int(o[0]), int(o[1])): o[2] == "we" for o in row["on"]}  # type: ignore[attr-defined]
        gold_we += sum(gold_on.values())
        for one in french_register.ons(sentence, words):
            word = words[one.at]
            # An inverted *-on* is written with its hyphen; the gold marks the pronoun.
            start = word.start + len(word.surface) - 2
            truth = gold_on.get((start, word.end), False)
            if one.we:
                called_we += 1
                we_right += truth
                if not truth and not quiet:
                    print(f"  wrong we: {sentence}")
            elif truth and not quiet:
                print(f"  missed we: {sentence}")

    def share(top: int, bottom: int) -> float:
        return top / bottom if bottom else 0.0

    return {
        "nedrop_precision": (share(right, named), named),
        "nedrop_recall": (share(right, in_gold), in_gold),
        "formal_accuracy": (share(formal_right, right), right),
        "on_we_precision": (share(we_right, called_we), called_we),
        "on_we_recall": (share(we_right, gold_we), gold_we),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", action="store_true", help="Append the rows to the ledger.")
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    args = parser.parse_args()

    rows = [json.loads(line) for line in GOLD.read_text(encoding="utf-8").splitlines()]
    scores = score(rows)
    for metric, (value, n) in scores.items():
        print(f"{metric} {value:.4f} (n={n})")
    note = evals.pinned(
        f"sentences={len(rows)} tags=none; written as ling-fr by builder 2026-11-14",
        [GOLD, Path(french_register.__file__)],
    )
    out = [
        evals.Row(
            at=date.today().isoformat(),
            stage=STAGE,
            corpus=CORPUS,
            system=SYSTEM,
            version=VERSION,
            metric=metric,
            score=round(value, 4),
            n=n,
            note=note,
        )
        for metric, (value, n) in scores.items()
    ]
    if args.record:
        evals.append(out, args.ledger)
        print(f"appended {len(out)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
