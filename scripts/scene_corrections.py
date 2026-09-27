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
`Store.agreed` counts judges.

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

#: What the audit was reading. One stage, because a scene's Hebrew is one thing to get
#: right; the kind of error is in `reason`, where it can be read rather than filtered on.
STAGE = "scene"


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


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--scenes", type=Path, required=True, help="the scenes as they were")
    parser.add_argument("--store", type=Path, default=None)
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

    for row in todo:
        keeping.correct(STAGE, who="author", licence="targum", language="he", **row)
    print(f"\n{len(todo)} judgements written to {keeping.path}.")
    print("A rebuild cannot reach them now, which is the whole point.")


if __name__ == "__main__":
    main()
