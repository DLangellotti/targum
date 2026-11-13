"""Merge the Hebrew topic runs and ling-he's decisions into one lexicon (targum-internal#606).

Free: it reads files and the tables' counts, and runs no model.

- The full run's agreed rows (its lexicon, `--base`, with any fixes made to it since) are
  the start.
- ling-he's decisions (`--decisions`) settle the rows of the full run's top 5,000 that
  the two models disagreed on or either called low-confidence.
- Below the top 5,000 a disagreement resolves by the card's rule: the topic the two
  models share, otherwise `general`. A row the models settled already keeps what they
  shared, so the rule writes `general` on each row that is left.
- An incremental run over the lemmas the lexicon missed (`--gap`, `scripts/tag_topics.py
  --only`) adds its agreed rows. Its disagreements are filed `general` for now and
  listed, with its low-confidence rows, for ling-he (`--for-review`).
- ling-he's decisions keyed by lemma (`--lemma-decisions`) tag the lemmas no run's review
  file holds a row for, such as the ones a run left untagged for want of a gloss. They
  never replace a review row's decision or a lemma the lexicon holds already: those are
  decided in review.tsv.

Every decision, by id or by lemma, is checked against the closed list (`topics.TOPICS`
or `general` alone, at most `topics.MOST`), and a file with one outside it is refused.

Every decision is written into its run's review.tsv (decision, who, at, why), after a
backup copy, and a decision a person made there is never overwritten: the next merge
reads it back and it outranks the decisions file and the rule. Only a decision `who` is
`rule` is the rule's to rewrite.

The lexicon is written as `topics/1` to `--out` (`~/.targum/topics.json`) only when every
modern yardstick that can be measured holds at least 95% of its top 5,000
(`topics.coverage`, as `targum topics check` counts it); otherwise to `--candidate`, and
the numbers are printed. Nothing is deployed.

    .venv/bin/python scripts/merge_topics.py \\
        --decisions ~/targum-team/ling-he/keep/topics-606-decisions-2026-11-09.json \\
        --gap 2026-11-09-gap --tables ~/.targum/corpus.db --yardsticks DIR \\
        --for-review ~/targum-team/ling-he/keep/topics-606-gap-review-2026-11-09.json \\
        --lemma-decisions ~/targum-team/ling-he/keep/topics-606-untagged-decisions-2026-11-13.json
"""

from __future__ import annotations

import argparse
import csv
import datetime
import io
import json
import shutil
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from targum import topics
from targum.paths import write_atomic

#: The full run's rows ling-he decides; below them the card's rule decides.
TOP = 5_000
RULE = "rule"
DECISION = ("decision", "who", "at", "why")
WHY_BELOW = "below the top 5k with no shared topic: general, by the card's rule"
WHY_GAP = "the two models disagreed: general for now, listed for ling-he"
#: The one seat whose decisions keyed by lemma the merge takes.
LEMMA_WHO = "ling-he"


@dataclass
class Merged:
    """What one merge settles: the lexicon, both runs' rows with their decisions filled,
    and what is left for ling-he."""

    lemmas: dict[str, list[str]]
    full: list[dict[str, str]]
    gap: list[dict[str, str]]
    for_review: list[dict[str, Any]] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


def _codes(cell: str) -> list[str]:
    return [one for one in (cell or "").split(",") if one]


def _decided_by_a_person(row: Mapping[str, str]) -> bool:
    return bool(row.get("decision")) and (row.get("who") or "") != RULE


def _model_columns(row: Mapping[str, str]) -> list[str]:
    """The two models' tag columns of a review row, in file order."""
    return [
        name
        for name in row
        if name not in {"id", "lemma", "glossed_as", "pos", "gloss", "count", "register"}
        and name not in {"agreed", *DECISION}
        and not name.endswith("_confidence")
    ]


def _low(row: Mapping[str, str]) -> bool:
    return any(row.get(f"{name}_confidence") == "low" for name in _model_columns(row))


def checked(lemma: str, codes: Sequence[str]) -> list[str]:
    """A decision's topics, if they are on the closed list: one to `topics.MOST` of
    `topics.TOPICS`, or `general` alone. Anything else is refused."""
    got = [str(one) for one in codes]
    if (
        not got
        or len(got) > topics.MOST
        or len(set(got)) != len(got)
        or any(one not in topics.TOPICS and one != topics.GENERAL for one in got)
        or (topics.GENERAL in got and len(got) > 1)
    ):
        raise ValueError(f"{lemma}: {got} is not a decision on the topic list")
    return got


def merge(
    base: Mapping[str, Sequence[str]],
    full: Iterable[Mapping[str, str]],
    decisions: Iterable[Mapping[str, Any]],
    gap: Iterable[Mapping[str, str]] = (),
    by_lemma: Iterable[Mapping[str, Any]] = (),
    *,
    who: str = "ling-he",
    at: str = "",
    top: int = TOP,
) -> Merged:
    """The merge, on rows as the review files hold them (strings), the decisions as
    ling-he's file lists them (`id`, `lemma`, `topics`, `confidence`, `note`), and her
    decisions keyed by lemma for lemmas no review row holds (`lemma`, `topics`)."""
    lemmas = {str(k): list(v) for k, v in base.items()}
    full_rows = [dict(row) for row in full]
    gap_rows = [dict(row) for row in gap]
    counts = {
        "decided_kept": 0,
        "decided_new": 0,
        "decision_mismatch": 0,
        "rule_below_top": 0,
        "undecided_in_top": 0,
        "gap_agreed": 0,
        "gap_disagreed": 0,
        "gap_low": 0,
        "gap_unanswered": 0,
        "gap_already_held": 0,
        "lemma_decided": 0,
        "lemma_has_review_row": 0,
        "lemma_already_held": 0,
    }
    by_lemma = list(by_lemma)
    seen: set[str] = set()
    for one in by_lemma:
        lemma = str(one["lemma"])
        if lemma in seen:
            raise ValueError(f"{lemma}: decided twice in the lemma decisions")
        seen.add(lemma)
        checked(lemma, one["topics"])

    by_id = {row["id"]: row for row in full_rows}
    for one in decisions:
        row = by_id.get(str(one["id"]))
        if row is None or row["lemma"] != one["lemma"]:
            counts["decision_mismatch"] += 1
            continue
        codes = checked(row["lemma"], one["topics"])
        if _decided_by_a_person(row):
            # Already decided in review.tsv: that stands, whatever the file says now.
            counts["decided_kept"] += 1
            continue
        note = str(one.get("note") or "")
        if one.get("confidence") == "low":
            note = f"unsure: {note}" if note else "unsure"
        row.update(
            decision=",".join(codes),
            who=str(one.get("who") or who),
            at=str(one.get("at") or at),
            why=note,
        )
        counts["decided_new"] += 1

    for row in full_rows:
        if _decided_by_a_person(row):
            lemmas[row["lemma"]] = _codes(row["decision"])
            continue
        if row.get("agreed"):
            # What the models shared is the rule's answer already; the base keeps it,
            # with any fix made to the base file since.
            lemmas.setdefault(row["lemma"], _codes(row["agreed"]))
            continue
        if int(row["id"]) < top:
            counts["undecided_in_top"] += 1
            continue
        row.update(decision=topics.GENERAL, who=RULE, at=at, why=WHY_BELOW)
        lemmas[row["lemma"]] = [topics.GENERAL]
        counts["rule_below_top"] += 1

    review: list[dict[str, Any]] = []
    for row in gap_rows:
        models = _model_columns(row)
        answered = all(row.get(name) for name in models)
        listed = {
            "id": int(row["id"]),
            "lemma": row["lemma"],
            "pos": row.get("pos", ""),
            "gloss": row.get("gloss", ""),
            **{name: row.get(name, "") for name in models},
            **{f"{name}_confidence": row.get(f"{name}_confidence", "") for name in models},
        }
        if _decided_by_a_person(row):
            lemmas[row["lemma"]] = _codes(row["decision"])
            continue
        if row["lemma"] in lemmas:
            # Held already, by the base or a decision: the gap run never replaces it.
            counts["gap_already_held"] += 1
            continue
        if row.get("agreed"):
            lemmas[row["lemma"]] = _codes(row["agreed"])
            counts["gap_agreed"] += 1
            if _low(row):
                counts["gap_low"] += 1
                review.append({**listed, "kind": "low-confidence", "filed": row["agreed"]})
            continue
        if not answered:
            counts["gap_unanswered"] += 1
            continue
        row.update(decision=topics.GENERAL, who=RULE, at=at, why=WHY_GAP)
        lemmas[row["lemma"]] = [topics.GENERAL]
        counts["gap_disagreed"] += 1
        review.append({**listed, "kind": "disagreement", "filed": topics.GENERAL})

    in_review = {row["lemma"] for row in (*full_rows, *gap_rows)}
    for one in by_lemma:
        lemma = str(one["lemma"])
        if lemma in in_review:
            # A review row's lemma is decided in its review.tsv, never here.
            counts["lemma_has_review_row"] += 1
        elif lemma in lemmas:
            counts["lemma_already_held"] += 1
        else:
            lemmas[lemma] = checked(lemma, one["topics"])
            counts["lemma_decided"] += 1
    return Merged(lemmas, full_rows, gap_rows, review, counts)


# --- Files ------------------------------------------------------------------------------


def read_review(file: Path) -> tuple[list[str], list[dict[str, str]]]:
    with file.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = [dict(row) for row in reader]
        return list(reader.fieldnames or []), rows


def read_lemma_decisions(file: Path) -> list[dict[str, Any]]:
    """ling-he's decisions keyed by lemma: the file's rows, refused unless the file is
    hers."""
    held = json.loads(file.read_text(encoding="utf-8"))
    if held.get("who") != LEMMA_WHO:
        raise ValueError(f"{file}: lemma decisions are {LEMMA_WHO}'s, not {held.get('who')!r}")
    return [dict(one) for one in held["rows"]]


def write_review(file: Path, header: Sequence[str], rows: Sequence[Mapping[str, str]]) -> None:
    """review.tsv with its decisions filled, after a backup copy of the file as it was."""
    backup = file.with_name(f"{file.name}.bak-{datetime.date.today().isoformat()}")
    if not backup.exists():
        shutil.copy2(file, backup)
    out = io.StringIO()
    writer = csv.DictWriter(
        out, fieldnames=list(header), delimiter="\t", lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({name: row.get(name) or "" for name in header})
    write_atomic(file, out.getvalue())


def measure(
    lemmas: Iterable[str], tables: Path | None, yardsticks: Path | None
) -> dict[str, float | None]:
    """Each modern yardstick's share of its top 5,000 the lexicon holds, as `targum topics
    check` counts it; None where there is no yardstick to measure."""
    from targum.tables import Store, yardstick

    store = Store(tables) if tables else Store.from_env()
    left_out = topics.screen_names(store) if store is not None else None
    keys = list(lemmas)
    out: dict[str, float | None] = {}
    for register in topics.MODERN:
        stick = yardstick.load(register, yardsticks)
        if stick is None:
            out[register] = None
            continue
        got = topics.coverage(keys, register, stick.version, stick.weights, left_out=left_out)
        out[register] = got.share
    return out


def passes(measured: Mapping[str, float | None], least: float = topics.CHECK_LEAST) -> bool:
    """Every yardstick that can be measured holds `least`, and at least one can be."""
    shares = [share for share in measured.values() if share is not None]
    return bool(shares) and all(share >= least for share in shares)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", type=Path, default=topics.run_lexicon("he", "2026-10-31"))
    parser.add_argument("--full", default="full-2026-10-31", help="The full run's directory.")
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--gap", help="The incremental run's directory name.")
    parser.add_argument("--out", type=Path, default=topics.LEXICON)
    parser.add_argument(
        "--candidate", type=Path, default=topics.LEXICON.with_name("topics.candidate.json")
    )
    parser.add_argument("--tables", type=Path, help="The tables to screen against.")
    parser.add_argument("--yardsticks", type=Path, help="Where the yardsticks are.")
    parser.add_argument("--for-review", type=Path, help="Where to list the gap run's rows.")
    parser.add_argument(
        "--lemma-decisions",
        type=Path,
        help="ling-he's decisions keyed by lemma, for lemmas no review file holds.",
    )
    parser.add_argument("--at", default=datetime.date.today().isoformat())
    args = parser.parse_args()

    base_file = json.loads(args.base.read_text(encoding="utf-8"))
    held = json.loads(args.decisions.read_text(encoding="utf-8"))
    decisions = [
        {**one, "who": one.get("who") or held.get("who"), "at": one.get("at") or held.get("at")}
        for one in held["rows"]
    ]
    by_lemma = read_lemma_decisions(args.lemma_decisions) if args.lemma_decisions else []
    full_file = topics.RESEARCH / args.full / "review.tsv"
    full_header, full_rows = read_review(full_file)
    gap_header: list[str] = []
    gap_rows: list[dict[str, str]] = []
    gap_file = topics.RESEARCH / args.gap / "review.tsv" if args.gap else None
    if gap_file is not None:
        gap_header, gap_rows = read_review(gap_file)

    before = merge(base_file["lemmas"], full_rows, decisions, at=args.at)
    merged = merge(base_file["lemmas"], full_rows, decisions, gap_rows, by_lemma, at=args.at)
    print(json.dumps(merged.counts, indent=1))

    measured_before = measure(before.lemmas, args.tables, args.yardsticks)
    measured = measure(merged.lemmas, args.tables, args.yardsticks)
    for register in topics.MODERN:
        was, now = measured_before[register], measured[register]
        if now is None:
            print(f"  {register}: no yardstick here, not measured")
        else:
            print(
                f"  {register}: {was:.2%} without the gap run or lemma decisions,"
                f" {now:.2%} with them"
            )

    write_review(full_file, full_header, merged.full)
    if gap_file is not None:
        write_review(gap_file, gap_header, merged.gap)
    if args.for_review is not None:
        args.for_review.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(
            args.for_review,
            json.dumps(
                {
                    "card": "targum-internal#606",
                    "at": args.at,
                    "run": args.gap,
                    "what": "The gap run's rows for ling-he: disagreements (filed general for"
                    " now) and low-confidence agreed rows (filed as agreed). Decide in the"
                    " run's review.tsv (decision, who, at, why); a re-merge keeps it.",
                    "counts": {
                        "disagreement": merged.counts["gap_disagreed"],
                        "low_confidence": merged.counts["gap_low"],
                    },
                    "rows": merged.for_review,
                },
                ensure_ascii=False,
                indent=1,
            ),
        )

    body = {
        key: value
        for key, value in base_file.items()
        if key not in {"version", "run", "lemmas", "merged"}
    }
    lexicon = {
        "version": topics.VERSION,
        **body,
        "run": [args.full, *([args.gap] if args.gap else [])],
        "merged": {
            "at": args.at,
            "base": str(args.base),
            "decisions": str(args.decisions),
            **({"lemma_decisions": str(args.lemma_decisions)} if args.lemma_decisions else {}),
            "coverage": {k: None if v is None else round(v, 4) for k, v in measured.items()},
            **merged.counts,
        },
        "lemmas": merged.lemmas,
    }
    target = args.out if passes(measured) else args.candidate
    write_atomic(target, json.dumps(lexicon, ensure_ascii=False, indent=1))
    print(f"{len(merged.lemmas):,} lemmas to {target}")
    if target != args.out:
        print(
            f"Under {topics.CHECK_LEAST:.0%} on a yardstick, or none measured: not written to"
            f" {args.out}.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
