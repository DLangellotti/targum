"""The false friend line on the French card, scored in context (targum-internal#644, #267).

**Friend precision**: of the words the card would say "false friend: not *X*, but *Y*"
of, the share where that line is true in the sentence the reader meets the word in. The
floor is 0.97 (the card's own). A line nobody has read in its sentence counts against the
score, not for it: a new entry or a new gloss is unread until a person reads it, and the
script names each one.

The sentences are the 342 of the liaison gold (`evals/french-said-gold.jsonl`), four
public-domain texts on the French shelf, with the gold's own tags. Every place the list
flagged in them was read by ling-fr on 2026-11-05 against the line the card says there
(`evals/french-false-friends-gold.jsonl`): 88 of 91 true under the list as drafted, and
the three that were not — *spectacle*, *misérable*, *robe* — dropped or reglossed. Each
row keeps every line it was read against, true or false, so a gloss changed back is
scored as read rather than as new.

    python scripts/eval_false_friends.py [--record]

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
from targum.annotate import false_friends  # noqa: E402

SENTENCES = ROOT / "evals" / "french-said-gold.jsonl"
GOLD = ROOT / "evals" / "french-false-friends-gold.jsonl"
STAGE = "friends"
CORPUS = "pd-fr-friends"
SYSTEM = "false-friends"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", action="store_true", help="Append the rows to the ledger.")
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    args = parser.parse_args()

    rows = [json.loads(line) for line in SENTENCES.read_text(encoding="utf-8").splitlines()]
    gold = {
        (row["sentence"], row["at"][0], row["at"][1]): row
        for row in map(json.loads, GOLD.read_text(encoding="utf-8").splitlines())
    }
    flagged = right = unread = 0
    lemmas: set[str] = set()
    for row in rows:
        words = row["words"]
        for at, (start, end, surface, lemma, pos, _feats) in enumerate(words):
            after = words[at + 1][2].lower() if at + 1 < len(words) else ""
            found = false_friends.friend_of(lemma, [(pos or "", after)])
            if not found:
                continue
            flagged += 1
            lemmas.add(lemma)
            looks, means = found
            read = gold.get((row["sentence"], start, end))
            verdict = next(
                (
                    one["true"]
                    for one in (read or {}).get("read", ())
                    if one["looks_like"] == looks and one["means"] == means
                ),
                None,
            )
            if verdict is None:
                unread += 1
                print(f"  not read: {surface} ({lemma}) not {looks}, {means} | {row['sentence']}")
            elif verdict:
                right += 1
            else:
                print(f"  false: {surface} ({lemma}) not {looks}, {means} | {row['sentence']}")

    precision = right / flagged if flagged else 0.0
    print(
        f"friend precision {precision:.4f} ({right} of {flagged} flagged, "
        f"{len(lemmas)} lemmas; {unread} not read in context)"
    )
    entries = len(false_friends.table())
    note = evals.pinned(
        f"sentences={len(rows)} tags=gold entries={entries}; read in context by ling-fr 2026-11-05",
        [GOLD, false_friends._TABLE],
    )
    out = [
        evals.Row(
            at=date.today().isoformat(),
            stage=STAGE,
            corpus=CORPUS,
            system=SYSTEM,
            version=f"{SYSTEM}/{entries}",
            metric=metric,
            score=round(score, 4),
            n=n,
            note=note,
        )
        for metric, score, n in (
            ("friend_precision", precision, flagged),
            ("friend_unread", float(unread), flagged),
        )
    ]
    if args.record:
        evals.append(out, args.ledger)
        print(f"appended {len(out)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
