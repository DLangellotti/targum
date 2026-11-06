"""Score a topic run against its language's blind gold set, and say whether it passes the
pilot's gate (targum-internal#638; Hebrew's pilots were scored the same way by hand).

The gold set is the CSV `tag_topics.py --blind` wrote, labelled: `topic_1`, `topic_2`
(either may hold codes joined by commas) and `notes`. A row whose notes say "fault" (a
wrong lemma, part of speech or gloss: the tables' fault, not the tagger's) is left out, as
ling-he's were. What a note names as defensible (`topics.alternatives`) is excused in the
lenient precision only; the gate reads the strict one.

**Only rows drawn without regard to their label count.** A row kept *because* its gold
label is topic X (ling-ru's v3 marks these "phase B topic" and "phase C": she labelled
draws and kept the ones that carried a short topic) can add a hit for X but almost never
a false positive, so it pushes precision towards 1 by construction, the micro gate's as
well as each topic's (qa-claude on #1119, 2026-11-06: 0.914 with them, 0.886 without).
Such rows (`label_selected`) never reach the gate or `shown`; they are scored apart, as
a per-topic diagnostic in `gold-score.json` under `label_selected`, and nothing reads
that. Precision for a topic wants rows sampled by the *predicted* tag, labelled blind.

Each model is scored, and the agreed tags, where a row the two models share nothing on
counts as `general`: it goes into no bar, exactly as a `general` row does. The score is
written to `gold-score.json` in the run directory. `--lexicon` sets that lexicon's
`shown` to the topics the agreed tags pass one by one (`topics.shown_from`), and to none
unless the gate passes. Spends nothing.

`--sample FILE` scores a blind sample drawn by the predicted tag instead (the honest
measure of precision): a CSV with `lemma`, the stratum it was drawn for (`stratum`,
`sampled_for` or `predicted`) and the gold `topic_1`/`topic_2`. Each topic's precision
and Wilson lower bound go to `sample-score.json`, and `--lexicon` then shows the topics
with at least 15 rows sampled and precision of 90% or more (`topics.shown_from_sample`).

    .venv/bin/python scripts/score_topics.py --run ru-pilot-2026-11-06 --gold GOLD.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

from targum import topics
from targum.paths import write_atomic

#: How a gold CSV marks a row kept because of its own label, in its notes or its last
#: column: ling-ru's v3 phases "B topic" and "C" (the uniform draws are "phase A" and
#: "phase B systematic").
LABEL_SELECTED = re.compile(r"\bphase (?:B topic|C)\b", re.IGNORECASE)


def label_selected(row: dict[str, str]) -> bool:
    """Whether a gold row was kept because of its label, and so may not be scored."""
    return any(LABEL_SELECTED.search(cell or "") for cell in row.values())


def read_gold(
    file: Path,
) -> tuple[dict[str, set[str]], dict[str, set[str]], list[str], dict[str, set[str]]]:
    """The gold labels by lemma, what each row's note also allows, the rows left out as
    data faults, and apart from the rest the rows kept because of their label
    (`label_selected`), which only the diagnostic reads."""
    gold: dict[str, set[str]] = {}
    also: dict[str, set[str]] = {}
    faults: list[str] = []
    selected: dict[str, set[str]] = {}
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
            if label_selected(row):
                selected[lemma] = labels
                continue
            gold[lemma] = labels
            also[lemma] = set(topics.alternatives(notes)) - labels
    return gold, also, faults, selected


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


STRATUM_COLUMNS = ("stratum", "sampled_for", "predicted")


def read_sample(file: Path) -> list[tuple[str, set[str]]]:
    """A predicted-tag sample's rows: the stratum each was drawn for and its gold labels,
    data faults left out."""
    out: list[tuple[str, set[str]]] = []
    with file.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        column = next((c for c in STRATUM_COLUMNS if c in (reader.fieldnames or ())), None)
        if column is None:
            raise SystemExit(f"{file}: no stratum column (one of {', '.join(STRATUM_COLUMNS)})")
        for row in reader:
            if "fault" in (row.get("notes") or "").lower():
                continue
            stratum = (row[column] or "").strip()
            labels = {
                code.strip()
                for cell in (row.get("topic_1") or "", row.get("topic_2") or "")
                for code in cell.split(",")
                if code.strip()
            }
            if not stratum or not labels:
                continue
            unknown = ({stratum} | labels) - {*topics.TOPICS, topics.GENERAL}
            if unknown:
                raise SystemExit(f"Row {row.get('row')} ({row['lemma']}): no such topic {unknown}")
            out.append((stratum, labels))
    return out


def score_sample(run: Path, sample: Path, lexicon: Path | None) -> int:
    """Score a predicted-tag sample, write `sample-score.json`, and set `shown`."""
    scored = topics.sampled_precision(read_sample(sample))
    shown = topics.shown_from_sample(scored)
    body = {"sample": str(sample), "per_topic": scored, "shown": list(shown)}
    write_atomic(run / "sample-score.json", json.dumps(body, ensure_ascii=False, indent=1))
    for code, held in scored.items():
        print(
            f"{code:10} sampled {held['sampled']:3}  right {held['right']:3}"
            f"  P {held['P']}  lower {held['P_lower']}  {'shown' if held['shown'] else ''}"
        )
    if lexicon:
        held_lexicon = json.loads(lexicon.read_text(encoding="utf-8"))
        held_lexicon["shown"] = list(shown)
        held_lexicon["shown_scored_on"] = sample.name
        write_atomic(lexicon, json.dumps(held_lexicon, ensure_ascii=False, indent=1))
        print(f"Shown in {lexicon}: {list(shown) or 'none'}")
    return 0 if shown else 4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run", required=True)
    parser.add_argument("--gold", type=Path)
    parser.add_argument(
        "--sample", type=Path, help="A blind sample drawn by the predicted tag, labelled."
    )
    parser.add_argument(
        "--lexicon",
        type=Path,
        help="A lexicon file (the run's) whose `shown` is set to the topics the agreed tags"
        " pass topic by topic (`topics.shown_from`): none unless the gate passes.",
    )
    args = parser.parse_args()
    run = topics.RESEARCH / args.run
    if args.sample:
        return score_sample(run, args.sample, args.lexicon)
    if args.gold is None:
        parser.error("--gold or --sample is required")
    if not (run / "review.tsv").is_file():
        print(f"No review.tsv in {run}: the run has not finished.", file=sys.stderr)
        return 1
    gold, also, faults, selected = read_gold(args.gold)
    predicted = read_run(run)
    scores = {name: topics.score(gold, tags, also) for name, tags in predicted.items()}
    diagnostic = topics.score(selected, predicted["agreed"]) if selected else None
    out = {
        "run": args.run,
        "gold": str(args.gold),
        "gold_rows": len(gold) + len(faults) + len(selected),
        "scored_rows": len(gold),
        "excluded_data_fault": faults,
        "excluded_label_selected": sorted(selected),
        **scores,
        "label_selected": (
            None
            if diagnostic is None
            else {
                "note": "Rows kept because of their gold label: a per-topic diagnostic"
                " only, never the gate or shown.",
                "per_topic": diagnostic["per_topic"],
            }
        ),
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
    if selected:
        print(f"{len(selected)} label-selected rows left out of the gate and shown.")
    agreed = scores["agreed"]
    print(f"Gate: {agreed['gate']['rule']}: {'passes' if agreed['gate']['passes'] else 'fails'}")
    for error in agreed["errors"]:
        print(f"  {error['lemma']}: {','.join(error['predicted'])} for {','.join(error['gold'])}")
    if args.lexicon:
        held = json.loads(args.lexicon.read_text(encoding="utf-8"))
        held["shown"] = list(topics.shown_from(agreed))
        held["shown_scored_on"] = args.gold.name
        write_atomic(args.lexicon, json.dumps(held, ensure_ascii=False, indent=1))
        print(f"Shown in {args.lexicon}: {held['shown'] or 'none'}")
    return 0 if agreed["gate"]["passes"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
