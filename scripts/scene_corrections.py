"""Keep the scene audit's judgements as rows, not as a corrected file.

On 2026-09-22 two independent readings of the hundred hand-written scenes found 275
errors, and David settled every one of them by hand — one at a time where the letters
changed, by class where only the points did. Applying them wrote a hundred corrected
files. That is exactly the loss targum-internal#354 is about:

> a corrected file is a snapshot that a rebuild overwrites, and the judgements inside it
> are lost at the moment they are applied. Rows survive, and every row is a labelled
> example.

The scenes' own schema comment says the same thing about the table this writes to: a
row is "the only training data the company owns outright". So the corrections go in the
store, where a rebuild cannot reach them, and where #351's missing hand-marked Hebrew
set — the one that stops `vocalize` being scored against another model's output — has
somewhere to come from.

**`who` is `author`.** These are the author's own hand, which needs no `state`: the
proposed/accepted path is for a judge who is not the person who owns the text.

**It can be run twice.** A judgement already in the store is skipped rather than
written again, because a duplicate row is a second judge who does not exist, and
`Store.agreed` counts judges. That skip is now the corrections ledger's own rule
(`targum.tables.fixes.record`, targum-internal#585), which this writes through: each row
carries its kind (`nikkud` where only the points moved, `wording` where the letters
changed), what wrote the scenes where `--tool` says, and the audit as its run. Rows kept before
the ledger had those columns get them on the next `--write`.

    python3 scripts/scene_corrections.py --decisions …/decisions.json --scenes …/dialogues
    python3 scripts/scene_corrections.py --decisions … --scenes … --write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from targum.dialogue.checks import bare  # noqa: E402
from targum.tables.fixes import kind_of, record  # noqa: E402

#: What the audit was reading. One stage, because a scene's Hebrew is one thing to get
#: right; the class of error is the row's `kind`, and the audit's own words its reason.
STAGE = "scene"

#: What wrote the scenes the audit read. Not recorded anywhere this script can see, so
#: empty unless `--tool` says; Opus 5 was the auditor, not the writer.
TOOL = ""


def lines_of(scenes: Path) -> dict[str, list[dict[str, str]]]:
    """Each scene's turns, so a judgement can carry the line it was made on."""
    out: dict[str, list[dict[str, str]]] = {}
    for path in sorted(scenes.glob("*.json")):
        scene = json.loads(path.read_text(encoding="utf-8"))
        out[scene["id"]] = [
            {"he": t.get("text", ""), "en": t.get("english", "")} for t in scene["turns"]
        ]
    return out


def rows_from(
    decisions: list[dict[str, Any]], turns: dict[str, list[dict[str, str]]]
) -> list[dict[str, str]]:
    """One row per judgement that names a word in a turn.

    The cast rename is not one of these: it changed a scene's speaker, not its Hebrew,
    and a row saying `before: cast` would be a correction about nothing a reader reads.
    It is skipped and counted, rather than quietly dropped.
    """
    rows = []
    for one in decisions:
        turn, word = one.get("turn"), str(one.get("word") or "")
        if turn is None or not word or word == "cast":
            continue
        lines = turns.get(one["scene"]) or []
        line = lines[turn] if 0 <= int(turn) < len(lines) else {"he": "", "en": ""}
        why = str(one.get("why") or one.get("source") or "")
        rows.append(
            {
                "term": bare(word),
                "before": word,
                "after": str(one.get("to") or ""),
                "span": f"{one['scene']} t{turn}",
                "text": line["en"],
                "context": line["he"],
                "reason": why,
            }
        )
    return rows


def classify(keeping: Any, rows: list[dict[str, str]], tool: str, run: str) -> int:
    """Give the rows this audit kept before the ledger's columns their kind, tool and run.
    Only a row with no kind is touched, so a hand that classed one differently wins."""
    changed = 0
    with keeping.write() as db:
        for row in rows:
            changed += db.execute(
                "UPDATE correction SET kind = ?, tool = ?, run = ? WHERE stage = ? AND span = ?"
                " AND before = ? AND after = ? AND who = 'author' AND kind = ''",
                (
                    kind_of(row["before"], row["after"]),
                    tool,
                    run,
                    STAGE,
                    row["span"],
                    row["before"],
                    row["after"],
                ),
            ).rowcount
    return int(changed)


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--scenes", type=Path, required=True, help="the scenes as they were")
    parser.add_argument("--store", type=Path, default=None)
    parser.add_argument("--tool", default=TOOL, help="what wrote the scenes it read")
    parser.add_argument("--run", default="", help="which audit; default: the decisions file")
    parser.add_argument(
        "--write", action="store_true", help="write the rows; without it, say what would be"
    )
    args = parser.parse_args()

    from targum.accounts import Store
    from targum.serve import default_store

    decisions = json.loads(args.decisions.expanduser().read_text(encoding="utf-8"))
    rows = rows_from(decisions, lines_of(args.scenes.expanduser()))
    print(f"{len(decisions)} judgements, {len(rows)} of them about a word in a turn")

    keeping = Store(args.store or default_store())
    held = {
        (row.get("span"), row.get("before"), row.get("after"))
        for row in keeping.corrections(STAGE, limit=100_000)
    }
    todo = [r for r in rows if (r["span"], r["before"], r["after"]) not in held]
    print(f"{len(held)} already in the store; {len(todo)} to write")

    if not args.write:
        for row in todo[:5]:
            print(f"  {row['span']}  {row['before']} -> {row['after']}   {row['reason'][:50]}")
        print("\nNothing was written. Add --write.")
        return

    run = args.run or args.decisions.stem
    for row in todo:
        record(
            keeping,
            stage=STAGE,
            who="author",
            language="he",
            before=row["before"],
            after=row["after"],
            why=row["reason"],
            kind=kind_of(row["before"], row["after"]),
            tool=args.tool,
            unit=row["span"],
            run=run,
            term=row["term"],
            text=row["text"],
            context=row["context"],
        )
    classed = classify(keeping, rows, args.tool, run)
    print(f"\n{len(todo)} judgements written to {keeping.path}.")
    if classed:
        print(f"{classed} kept before the ledger now say their kind, tool and run.")
    print("A rebuild cannot reach them now, which is the whole point.")


if __name__ == "__main__":
    main()
