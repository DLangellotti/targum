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
measure of precision): a CSV with `lemma`, `stratum` (the agreed tag it was drawn for),
`predicted` (the lemma's agreed tags when it was drawn), `lexicon_version` (the version
of the lexicon it was drawn from) and the gold `topic_1`/`topic_2`. It is refused unless
it was drawn from the lexicon `--lexicon` names (or the run's own) as that lexicon is
now: the lexicon's `run` is the run's name exactly, every row names the lexicon's
version, each lemma is drawn at most once for a topic, and every row's tags are the
lexicon's, with its stratum among them, so a sample of one round's tags never sets another's
`shown`. Each topic's precision and Wilson lower bound go to `sample-score.json`, with a
sha256 of the lexicon's tags, and `--lexicon` then shows the topics whose sample proves
90%: a Wilson 95% lower bound of 90% or more (David, 2026-11-06), so 35 rows or more;
and none unless the whole sample's topic precision is 90% or more and its `general` 85%
(`topics.shown_from_sample`).

    .venv/bin/python scripts/score_topics.py --run ru-pilot-2026-11-06 --gold GOLD.csv
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from targum import topics
from targum.paths import write_atomic

#: The draws a gold CSV may mark as uniform, in its notes or its last column: ling-ru's
#: v3 "phase A" and "phase B systematic". A row is scored only when every phase any of
#: its cells names is one of these, each ending there (at the cell's end or at `;`, `,`,
#: `.` or `)`), and no cell says "B topic" or "label-selected". Anything else was kept
#: for its label, or is marked in a way this does not know, and is never scored: the
#: check fails closed. A row naming no phase at all (v1 and v2) is scored.
UNIFORM_PHASE = re.compile(r"phase (?:A|B systematic)(?=\s*(?:$|[;,.)]))", re.IGNORECASE)
PHASE = re.compile(r"\bphase\b", re.IGNORECASE)
SELECTED_MARK = re.compile(r"\bB[- ]topic\b|label[- ]selected", re.IGNORECASE)


def label_selected(row: dict[str, str]) -> bool:
    """Whether a gold row may not be scored: one of its cells names a phase that is not
    a uniform one, or marks the row as selected."""
    for cell in row.values():
        if not cell:
            continue
        if SELECTED_MARK.search(cell):
            return True
        for mention in PHASE.finditer(cell):
            if not UNIFORM_PHASE.match(cell, mention.start()):
                return True
    return False


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


SAMPLE_COLUMNS = ("lemma", "stratum", "predicted", "lexicon_version", "topic_1")


def _codes(cell: str) -> set[str]:
    return {code for code in cell.replace(" ", ",").split(",") if code}


def read_sample(file: Path) -> tuple[list[dict[str, Any]], set[str]]:
    """A predicted-tag sample's rows (lemma, stratum, the tags it was drawn with, and its
    gold labels), data faults left out, and the lexicon versions it names."""
    rows: list[dict[str, Any]] = []
    versions: set[str] = set()
    with file.open(encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in SAMPLE_COLUMNS if c not in (reader.fieldnames or ())]
        if missing:
            raise SystemExit(f"{file}: no {', '.join(missing)} column")
        for row in reader:
            versions.add((row["lexicon_version"] or "").strip())
            if "fault" in (row.get("notes") or "").lower():
                continue
            stratum = (row["stratum"] or "").strip()
            labels = _codes(row.get("topic_1") or "") | _codes(row.get("topic_2") or "")
            if not stratum or not labels:
                continue
            unknown = ({stratum} | labels) - {*topics.TOPICS, topics.GENERAL}
            if unknown:
                raise SystemExit(f"Row {row.get('row')} ({row['lemma']}): no such topic {unknown}")
            rows.append(
                {
                    "lemma": row["lemma"].strip(),
                    "stratum": stratum,
                    "predicted": _codes(row["predicted"] or ""),
                    "labels": labels,
                }
            )
    return rows, versions


def tags_digest(lemmas: dict[str, list[str]]) -> str:
    """A sha256 of a lexicon's tags, so a score names exactly the tags it read."""
    body = json.dumps(lemmas, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def sample_refusal(
    run: str, held: dict[str, Any], rows: list[dict[str, Any]], versions: set[str]
) -> str | None:
    """Why a sample may not set this lexicon's `shown`, or None: it must be drawn from
    this run's lexicon, as it is now."""
    version = str(held.get("version") or "")
    if held.get("run") != run:
        return f"the lexicon is run {held.get('run')!r}'s, not {run}'s"
    if versions != {version}:
        return f"the sample was drawn from {sorted(versions)}, not {version!r}"
    drawn = Counter((row["lemma"], row["stratum"]) for row in rows)
    twice = sorted(f"{lemma} ({stratum})" for (lemma, stratum), n in drawn.items() if n > 1)
    if twice:
        # One word counted twice for a topic would be two rows of evidence from one word.
        return f"{', '.join(twice)} drawn more than once for the same topic"
    lemmas = held.get("lemmas") or {}
    for row in rows:
        now = set(lemmas.get(row["lemma"], ()))
        if row["predicted"] != now:
            drawn = sorted(row["predicted"])
            return f"{row['lemma']} was drawn as {drawn}, the lexicon has {sorted(now)}"
        if row["stratum"] not in now:
            return (
                f"{row['lemma']} was drawn for {row['stratum']}, which the lexicon does not give it"
            )
    return None


def score_sample(run: Path, sample: Path, lexicon: Path | None) -> int:
    """Score a predicted-tag sample, write `sample-score.json`, and set `shown`: 0 when a
    topic is shown, 4 when none is, 5 when the sample is not this lexicon's."""
    rows, versions = read_sample(sample)
    write = lexicon is not None
    lexicon = lexicon or topics.run_lexicon(_language(run), run.name)
    held = json.loads(lexicon.read_text(encoding="utf-8"))
    refused = sample_refusal(run.name, held, rows, versions)
    if refused:
        print(f"Refused: {refused}. Nothing written.", file=sys.stderr)
        return 5
    scored = topics.sampled_precision((row["stratum"], row["labels"]) for row in rows)
    gate = topics.sample_gate(scored)
    shown = topics.shown_from_sample(scored)
    digest = tags_digest(held.get("lemmas") or {})
    body = {
        "sample": str(sample),
        "lexicon": str(lexicon),
        "lexicon_version": held.get("version"),
        "tags_sha256": digest,
        "gate": gate,
        "per_topic": scored,
        "shown": list(shown),
        "rule": topics.SAMPLE_SHOWN_RULE,
    }
    write_atomic(run / "sample-score.json", json.dumps(body, ensure_ascii=False, indent=1))
    for code, one in scored.items():
        print(
            f"{code:10} sampled {one['sampled']:3}  right {one['right']:3}"
            f"  P {one['P']}  lower {one['P_lower']}  {'passes' if one['shown'] else ''}"
        )
    print(f"Sample gate: topic P {gate['precision']}: {'passes' if gate['passes'] else 'fails'}")
    if write:
        held["shown"] = list(shown)
        held["shown_rule"] = topics.SAMPLE_SHOWN_RULE
        held["shown_scored_on"] = sample.name
        held["shown_tags_sha256"] = digest
        write_atomic(lexicon, json.dumps(held, ensure_ascii=False, indent=1))
        print(f"Shown in {lexicon}: {list(shown) or 'none'}")
    return 0 if shown else 4


def _language(run: Path) -> str:
    held = json.loads((run / "lemmas.json").read_text(encoding="utf-8"))
    return str(held.get("language", "he"))


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
        if held.get("run") != args.run:
            print(f"Refused: {args.lexicon} is not run {args.run}'s lexicon.", file=sys.stderr)
            return 5
        held["shown"] = list(topics.shown_from(agreed))
        held["shown_rule"] = topics.shown_rule(str(held.get("language") or "he"))
        held["shown_scored_on"] = args.gold.name
        held["shown_tags_sha256"] = tags_digest(held.get("lemmas") or {})
        write_atomic(args.lexicon, json.dumps(held, ensure_ascii=False, indent=1))
        print(f"Shown in {args.lexicon}: {held['shown'] or 'none'}")
    return 0 if agreed["gate"]["passes"] else 4


if __name__ == "__main__":
    raise SystemExit(main())
