"""Does a correct line get "corrected"? targum-internal#242, acceptance criterion 2.

The contract allows **one** `~ ` line, directly under a recast that changed something,
and forbids one on a line that was already right: *"Never on a line that was right"*.
A `~ ` on a correct sentence tells a reader they made a mistake they did not make, and
the reader has no way to know it is wrong — which is the worst shape of wrong a
correction can have.

`stray_why` counts a `~ ` that belongs to *no* recast, which is criterion 3 and a
different question. This is criterion 2: a `~ ` that belongs to a recast **of a line
that was already correct**, which the parser keeps and the page shows.

**Where the correct lines come from.** The Tatoeba pool, rows a contributor who declares
Hebrew native wrote — correct by construction and written by a person rather than chosen
by me, which is what makes the number mean anything. Sent as the reader's own turn.

**It spends, and it loads no annotator.** K calls at the chat's own model; `--dry-run`
prices it and calls nothing. There is deliberately no DICTA load here: counting `~ `
lines is parsing, `eval_grading.py` is where the lemma question lives, and keeping them
apart is what lets this run on a laptop.

    .venv/bin/python scripts/eval_why.py --dry-run
    set -a && . ./.env && set +a && .venv/bin/python scripts/eval_why.py --turns 10
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from eval_grading import turns  # noqa: E402  (same directory, same call shape)

from targum import evals  # noqa: E402
from targum.chat import CHAT_MODEL, exemplars, hebrew  # noqa: E402
from targum.level import EMPTY  # noqa: E402
from targum.usage import Usage  # noqa: E402


def correct_lines(
    pool: list[exemplars.Exemplar], allowed: set[str], count: int, seed: int
) -> list[exemplars.Exemplar]:
    """Hebrew a native speaker wrote, inside the synthetic reader's words.

    Inside the list for the same reason `eval_grading.pool_openers` draws from it: a
    sentence full of words the reader does not know invites the model to rewrite it for
    level, and then a `~ ` line is arguably about the level rather than a false
    correction. Keeping it inside the list leaves only one honest reason to write one.

    Originals first — sentences written in Hebrew rather than translated into it — since
    a translation carries the source language's shape and is the likelier thing for a
    model to want to "fix".
    """
    inside = [row for row in pool if row.lemmas and row.lemmas <= allowed and row.hebrew]
    random.Random(seed).shuffle(inside)
    inside.sort(key=lambda row: not row.original)
    return inside[:count]


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--turns", type=int, default=10, help="how many correct lines to send")
    parser.add_argument("--known", type=int, default=300)
    parser.add_argument("--pool", type=Path, help="the Tatoeba pool; found in the usual places")
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--keep", type=Path, help="write every reply out, to read by hand")
    parser.add_argument("--dry-run", action="store_true", help="price it and call nothing")
    parser.add_argument("--note", default="")
    args = parser.parse_args()

    common = hebrew.common_words()
    if not common:
        sys.exit("wordfreq is not installed: uv sync --extra difficulty")
    known = common[: args.known]
    allowed = set(common) | set(known)
    pool = exemplars.load(args.pool) if args.pool else exemplars.load()
    if not pool:
        sys.exit("no exemplar pool; scripts/tatoeba_pool.py builds it")
    chosen = correct_lines(pool, allowed, args.turns, args.seed)
    if len(chosen) < args.turns:
        sys.exit(f"only {len(chosen)} pool sentences fall inside {args.known} words")

    if args.dry_run:
        print(f"{len(chosen)} correct Hebrew lines, written by a native speaker:\n")
        for row in chosen:
            mark = "original" if row.original else "translated"
            print(f"  [{mark:10}] {row.hebrew}")
        print(f"\n{len(chosen)} calls to {CHAT_MODEL}. Nothing was called.")
        print("Drop --dry-run to run it.")
        return

    import anthropic

    ledger = hebrew.ledger_block(EMPTY, known, common)
    usage = Usage()
    replies = turns(
        anthropic.Anthropic(),
        hebrew.CONTRACT,
        ledger,
        len(chosen),
        [row.hebrew for row in chosen],
        None,
        allowed,
        args.seed,
        usage,
    )

    # Every `~ ` written, not only the ones the parser drops: on a correct line the
    # contract allows none at all, so one the parser *keeps* is the failure this is
    # looking for — it is the one the reader is shown.
    written = [
        sum(1 for raw in reply.splitlines() if raw.strip().startswith(hebrew.WHY))
        for reply in replies
    ]
    strays = [hebrew.stray_why(reply) for reply in replies]
    shown = [count - stray for count, stray in zip(written, strays, strict=True)]

    print(f"{len(replies)} correct lines sent to {CHAT_MODEL}\n")
    for row, count, stray in zip(chosen, written, strays, strict=True):
        if count:
            print(f'  {count} "~ " ({stray} dropped) on: {row.hebrew}')
    print(f'"~ " lines written on a correct line: {sum(written)}')
    print(f"  of which the reader is shown:      {sum(shown)}")
    print(f"  of which dropped as stray:         {sum(strays)}")
    print(f"\nThis run cost ${usage.cost():.2f}.")

    if args.keep:
        args.keep.write_text(
            json.dumps(
                [
                    {"sent": row.hebrew, "id": row.id, "reply": reply, "why": count}
                    for row, reply, count in zip(chosen, replies, written, strict=True)
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Replies written to {args.keep}.")

    rows = [
        evals.Row(
            at=date.today().isoformat(),
            stage="chat",
            corpus="tatoeba-correct",
            metric=metric,
            score=float(score),
            n=len(replies),
            system="chat-contract",
            version=CHAT_MODEL,
            note=args.note or "correct native-written Hebrew sent as the reader's line",
        )
        for metric, score in (
            ("why_on_correct_lines", sum(written)),
            ("why_shown_on_correct_lines", sum(shown)),
        )
    ]
    print(f"\nRecorded {evals.append(rows, args.ledger)} rows.")


if __name__ == "__main__":
    main()
