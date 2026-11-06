"""Score a topic run against its language's blind gold set, and say whether it passes the
pilot's gate (targum-internal#638; Hebrew's pilots were scored the same way by hand).

The gold set is the CSV `tag_topics.py --blind` wrote, labelled: `topic_1`, `topic_2`
(either may hold codes joined by commas) and `notes`. A row whose notes say "fault" (a
wrong lemma, part of speech or gloss: the tables' fault, not the tagger's) is left out, as
ling-he's were. What a note names as defensible (`topics.alternatives`) is excused in the
lenient precision only; the gate reads the strict one.

Each model is scored, and the agreed tags, where a row the two models share nothing on
counts as `general`: it goes into no bar, exactly as a `general` row does. The score is
written to `gold-score.json` in the run directory. Spends nothing.

    .venv/bin/python scripts/score_topics.py --run ru-pilot-2026-11-06 --gold GOLD.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from targum import topics
from targum.paths import write_atomic


def read_gold(file: Path) -> tuple[dict[str, set[str]], dict[str, set[str]], list[str]]:
    """The gold labels by lemma, what each row's note also allows, and the rows left out
    as data faults."""
    gold: dict[str, set[str]] = {}
    also: dict[str, set[str]] = {}
    faults: list[str] = []
    with file.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            lemma = row["lemma"].strip()
            notes = row.get("notes") or ""
            if "fault" in notes.lower():
                faults.append(lemma)
                continue
            labels = {
                code.strip()
                for cell in (row.get("topic_1") or "", row.get("topic_2") or "")
                for code in cell.split(",")
                if code.strip()
            }
            if not labels:
                continue
            unknown = labels - {*topics.TOPICS, topics.GENERAL}
            if unknown:
                raise SystemExit(f"Row {row.get('row')} ({lemma}): no such topic {unknown}")
            gold[lemma] = labels
            also[lemma] = set(topics.alternatives(notes)) - labels
    return gold, also, faults


def read_run(run: Path) -> dict[str, dict[str, set[str]]]:
    """Each model's tags and the agreed ones, by lemma, from the run's `review.tsv`."""
    with (run / "review.tsv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    models = [c for c in rows[0] if c.startswith(("sonnet-", "opus-", "haiku-"))]
    models = [c for c in models if not c.endswith("_confidence")]
    out: dict[str, dict[str, set[str]]] = {m: {} for m in models}
    out["agreed"] = {}
    for row in rows:
        for model in models:
            if row[model]:
                out[model][row["lemma"]] = {c for c in row[model].split(",") if c}
        if all(row[m] for m in models):
            out["agreed"][row["lemma"]] = {c for c in row["agreed"].split(",") if c} or {
                topics.GENERAL
            }
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run", required=True)
    parser.add_argument("--gold", type=Path, required=True)
    args = parser.parse_args()
    run = topics.RESEARCH / args.run
    if not (run / "review.tsv").is_file():
        print(f"No review.tsv in {run}: the run has not finished.", file=sys.stderr)
        return 1
    gold, also, faults = read_gold(args.gold)
    predicted = read_run(run)
    scores = {name: topics.score(gold, tags, also) for name, tags in predicted.items()}
    out = {
        "run": args.run,
        "gold": str(args.gold),
        "gold_rows": len(gold) + len(faults),
        "excluded_data_fault": faults,
        **scores,
    }
    write_atomic(run / "gold-score.json", json.dumps(out, ensure_ascii=False, indent=1))
    for name, held in scores.items():
        interval = held["precision_interval"] or ["-", "-"]
        print(
            f"{name:18} scored {held['scored']:3}  exact {held['exact']:3}"
            f"  P {held['precision']} [{interval[0]}, {interval[1]}]"
            f"  P lenient {held['precision_lenient']}  R {held['recall']}"
            f"  general P {held['general_precision']}"
        )
    agreed = scores["agreed"]
    print(f"Gate: {agreed['gate']['rule']}: {'passes' if agreed['gate']['passes'] else 'fails'}")
    for error in agreed["errors"]:
        print(f"  {error['lemma']}: {','.join(error['predicted'])} for {','.join(error['gold'])}")
    return 0 if agreed["gate"]["passes"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
