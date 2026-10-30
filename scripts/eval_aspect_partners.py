"""Is the card's "the other aspect" line right? Scored against targum's reviewed list.

The gold is `annotate/aspect_partners.json`: ling-ru's judgement, for the 300 commonest
verbs in the built Russian texts, of each verb's true aspect partner or partners, or that
it has none (2026-10-30). This scores the line a card draws on the commonest `--top`
verbs (100 by default, 38.4% of verb tokens), weighted by how often each is met, two
ways:

- `before`: OpenRussian's partner column as the card read it until 2026-10-30 — the first
  `PARTNERS` names, exactly as shown. Needs the tables (`targum models fetch openrussian`);
  without them it is skipped.
- `after`: what the card draws now (`aspect_partners.partner_line`), the same function the
  builder calls. On the listed verbs this is the list itself, so it scores 1.0 by
  construction and is a guard: a change to the builder, the limit or the list's shape that
  stops the list winning shows here first.

Two metrics, each over verb tokens:

- `partner_precision`: of the partners a card names, the share the list calls true
  partners, over the verbs whose card names any.
- `partner_line_right`: the share whose line is right as a whole — no line where the list
  says none, and otherwise only true partners.

**The gold has not been read by David yet**; the note on each row says so until it has.
No key, no network, no spend.

    python scripts/eval_aspect_partners.py [--top 100] [--record]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import evals  # noqa: E402
from targum.annotate import aspect_partners, openrussian  # noqa: E402
from targum.render.builder import PARTNERS  # noqa: E402

STAGE = "partners"
CORPUS = "ru-built-top-verbs"


def gold(top: int) -> list[tuple[str, int, set[str]]]:
    """The commonest `top` verbs on the list: lemma, tokens, the true partners folded."""
    rows = json.loads(aspect_partners._TABLE.read_text(encoding="utf-8"))["entries"]
    rows = sorted(rows, key=lambda row: -int(row["tokens"]))[:top]
    return [
        (
            str(row["verb"]),
            int(row["tokens"]),
            {aspect_partners.fold(str(partner)) for partner in row["partners"]},
        )
        for row in rows
    ]


def score(
    verbs: list[tuple[str, int, set[str]]], shown: dict[str, list[str]]
) -> dict[str, tuple[float, int]]:
    """Token-weighted precision and whole-line accuracy, each with its token count."""
    named_tokens = 0
    precise = 0.0
    right = 0
    total = 0
    for lemma, tokens, true in verbs:
        line = [aspect_partners.fold(word) for word in shown.get(lemma, [])]
        total += tokens
        if line:
            named_tokens += tokens
            precise += tokens * sum(word in true for word in line) / len(line)
        whole = (not line and not true) or (bool(line) and all(word in true for word in line))
        right += tokens * whole
    return {
        "partner_precision": (precise / named_tokens if named_tokens else 0.0, named_tokens),
        "partner_line_right": (right / total if total else 0.0, total),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument("--record", action="store_true", help="Append the rows to the ledger.")
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    args = parser.parse_args()

    verbs = gold(args.top)
    lexicon = openrussian.lexicon()
    systems: dict[str, dict[str, list[str]]] = {}
    if lexicon is not None:
        systems[f"openrussian/{openrussian.COMMIT[:7]}"] = {
            lemma: lexicon.partners(lemma)[:PARTNERS] for lemma, _, _ in verbs
        }
    else:
        print("OpenRussian's tables are not here: the before line is skipped.")
    systems["aspect-partners/1"] = {
        lemma: aspect_partners.partner_line(lemma, lexicon, PARTNERS)[0] for lemma, _, _ in verbs
    }

    note = evals.pinned(
        f"top={args.top} verbs by token; gold ling-ru's list, not yet read by David",
        [aspect_partners._TABLE],
    )
    out = []
    for system, shown in systems.items():
        scored = score(verbs, shown)
        for metric, (value, n) in scored.items():
            print(f"{system:24} {metric:20} {value:.4f}  over {n} verb tokens")
            out.append(
                evals.Row(
                    at=date.today().isoformat(),
                    stage=STAGE,
                    corpus=CORPUS,
                    system=system,
                    version=system,
                    metric=metric,
                    score=round(value, 4),
                    n=n,
                    note=note,
                )
            )
        if system.startswith("openrussian"):
            for lemma, _, true in verbs:
                line = [aspect_partners.fold(word) for word in shown.get(lemma, [])]
                if line and not all(word in true for word in line) or (true and not line):
                    print(f"  {lemma}: shown {' · '.join(line) or '-'}, list {sorted(true)}")
    if args.record:
        evals.append(out, args.ledger)
        print(f"appended {len(out)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
