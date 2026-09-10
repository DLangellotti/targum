"""How long the chat's replies run, off the conversations this machine has stored.

The contract caps a reply at `hebrew.MOST_SENTENCES` Hebrew sentences since 2026-09-10
(targum-internal#236); before that it said "a few", and this is the script that said what
a few was: a median of 36 Hebrew words over five lines, ten with their English, on the 35
turns stored here. Run it again after a prompt change and the number says whether the
change reached the page. Nothing is spent and nothing is sent: it reads `chat_turn` in
the local store and counts.

    .venv/bin/python scripts/measure_reply_length.py
    .venv/bin/python scripts/measure_reply_length.py --store ~/.targum/targum.db

The reproducible measure — the one the floor in `evals/floors.json` reads — is
`scripts/eval_grading.py`, which asks the model fresh and appends `hebrew_words_median`
to the ledger; this one is the look at what real readers got.
"""

from __future__ import annotations

import argparse
import sqlite3
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum.chat import hebrew  # noqa: E402


def lengths(store: Path) -> list[int]:
    """Hebrew words per assistant turn that said anything, oldest first."""
    with sqlite3.connect(store) as db:
        rows = db.execute(
            "SELECT said FROM chat_turn WHERE role = 'assistant' AND said != '' ORDER BY made"
        ).fetchall()
    return [hebrew.length(said) for (said,) in rows if hebrew.length(said)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--store", type=Path, default=Path.home() / ".targum" / "targum.db")
    args = parser.parse_args()
    if not args.store.exists():
        sys.exit(f"no store at {args.store}")
    counted = lengths(args.store)
    if not counted:
        sys.exit("no assistant turns with Hebrew in them")
    print(f"{len(counted)} replies with Hebrew in them")
    print(f"median {statistics.median(counted):g} Hebrew words, max {max(counted)}")
    print(f"the contract's cap is {hebrew.MOST_SENTENCES} sentences (targum-internal#236)")
    over = sum(1 for n in counted if n > 50)
    print(f"{over} over 50 words")


if __name__ == "__main__":
    main()
