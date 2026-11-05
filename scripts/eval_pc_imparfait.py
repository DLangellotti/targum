"""The passé composé against the imparfait, as the French card names them (targum-internal#644).

French's third hard spot (`stages.HARD_SPOTS["fr"]`). The card reads each verb's tense off
the tagger (`model_lemma`, prompt 3 on, which tells the imparfait from the passé simple)
and names a compound by its auxiliary (`reader.js`, `compoundLine`): *a mangé* is the
passé composé, *avait mangé* the pluperfect, *est venu* the passé composé and *est
guéri* the passive. This scores that name against ling-fr's hand-read gold:

- **`pc_imp_accuracy`**: of the 102 verbs the gold calls passé composé (45) or imparfait
  (57), the share the card names that tense.
- **`trap_false_alarm`**: of the 45 the gold calls neither — pluperfect, passé simple,
  present (*il est guéri*, *tu as*), conditional, subjunctive — the share the card calls
  one of the two. An upper bound.

The gold is `evals/french-pc-imparfait-gold.jsonl`: 62 sentences from 14 public-domain
texts on the French shelf, each with its catalogue id, Wikisource edition and licence,
read and labelled by ling-fr on 2026-11-05 (`evals/SOURCES.md`). Only the verbs it lists
are scored.

The tags are the tagger's own, from the cache where a shelf text has already bought the
sentence and bought here where not (a few cents of Haiku for the whole set; load the keys
with `op run --env-file op.env --`).

    python scripts/eval_pc_imparfait.py [--record]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import evals  # noqa: E402
from targum.models import Segment, Token  # noqa: E402

GOLD = Path(__file__).resolve().parents[1] / "evals" / "french-pc-imparfait-gold.jsonl"
STAGE = "lemma"
CORPUS = "pd-fr-pc-imp"
SYSTEM = "model-lemma"
SCORED = {"PC", "IMP"}

#: `reader.js`'s tables, ported: the auxiliaries, the verbs that take *être*, the
#: reflexive pronouns, and how far back an auxiliary is looked for.
AUXILIARIES = {"avoir", "être"}
ETRE_VERBS = set(
    (
        "aller venir arriver partir entrer sortir monter descendre naître mourir rester "
        "tomber retourner devenir revenir rentrer parvenir intervenir survenir décéder "
        "redescendre remonter repartir ressortir retomber advenir"
    ).split()
)
REFLEXIVES = {"se", "me", "te", "s'", "m'", "t'"}
AUXILIARY_REACH = 4
_STOP = re.compile(r"[.,;:!?—]")


def feat(token: Token, name: str) -> str:
    for part in (token.feats or "").split("|"):
        key, _, value = part.partition("=")
        if key == name:
            return value
    return ""


def auxiliary_before(text: str, tokens: list[Token], at: int) -> tuple[Token, bool] | None:
    """`reader.js`'s `auxiliaryBefore`: the nearest *avoir* or *être* before the word in
    its own clause, and whether a reflexive pronoun stands before that."""
    end = tokens[at].start
    for k in range(at - 1, max(-1, at - 1 - AUXILIARY_REACH), -1):
        if _STOP.search(text[tokens[k].end : end]):
            return None
        end = tokens[k].start
        if (tokens[k].lemma or "").lower() not in AUXILIARIES:
            continue
        reflexive = any(
            (tokens[j].lemma or "").lower() in REFLEXIVES or tokens[j].surface.lower() in REFLEXIVES
            for j in range(k - 1, max(-1, k - 3), -1)
        )
        return tokens[k], reflexive
    return None


def compound(auxiliary: Token) -> str:
    """`reader.js`'s `compoundName`, as a label (prompt 3: the tenses are apart)."""
    if feat(auxiliary, "VerbForm") in {"Inf", "Part"}:
        return "OTHER"
    mood = feat(auxiliary, "Mood")
    if mood == "Cnd":
        return "COND"
    if mood == "Sub":
        return "OTHER"
    return {"Pres": "PC", "Imp": "PQP", "Past": "PA", "Fut": "FUTP"}.get(
        feat(auxiliary, "Tense"), "OTHER"
    )


def named(text: str, tokens: list[Token], at: int) -> str:
    """What the card calls the verb ending at `tokens[at]`."""
    token = tokens[at]
    form = feat(token, "VerbForm")
    if form == "Part":
        found = auxiliary_before(text, tokens, at)
        if found is None:
            return "PART"
        auxiliary, reflexive = found
        lemma = (auxiliary.lemma or "").lower()
        if lemma == "être" and not reflexive and (token.lemma or "").lower() not in ETRE_VERBS:
            return "PASSIVE"
        return compound(auxiliary)
    if form == "Inf":
        return "OTHER"
    mood = feat(token, "Mood")
    if mood == "Cnd":
        return "COND"
    if mood in {"Sub", "Imp"}:
        return "OTHER"
    return {"Past": "PS", "Imp": "IMP", "Pres": "PRES", "Fut": "FUT"}.get(
        feat(token, "Tense"), "OTHER"
    )


def card_says(text: str, tokens: list[Token], start: int, end: int) -> str:
    """What the card calls the verb the gold spans from `start` to `end`: the compound its
    last word makes with an auxiliary, where it makes one, and otherwise what it calls
    the finite verb the span opens on (*n'était pas mort*: *était*, an imparfait, before
    *mort* the adjective)."""
    last = next((n for n, token in enumerate(tokens) if token.start < end <= token.end), None)
    first = next((n for n, token in enumerate(tokens) if token.start <= start < token.end), None)
    if last is None or first is None:
        return "NONE"
    if feat(tokens[last], "VerbForm") == "Part" and auxiliary_before(text, tokens, last):
        return named(text, tokens, last)
    return named(text, tokens, first)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", type=Path, default=GOLD)
    parser.add_argument("--record", action="store_true", help="Append the rows to the ledger.")
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    args = parser.parse_args()

    from targum.annotate import model_lemma

    rows = [json.loads(line) for line in args.gold.read_text(encoding="utf-8").splitlines()]
    segments = [
        Segment(id=f"{n:04d}", block_id=f"b{n}", block_index=n, index=n, text=row["sentence"])
        for n, row in enumerate(rows)
    ]
    reader = model_lemma.ModelLemmatizer(buy=True)
    found = reader.lemmas(segments, "fr")
    print(f"tagger: {reader.name}; spent: {reader.spent}")

    scored = right = traps = alarms = 0
    confusion: Counter[tuple[str, str]] = Counter()
    for segment, row in zip(segments, rows, strict=True):
        tokens = found.get(segment.id, [])
        text = row["sentence"]
        for verb in row["verbs"]:
            said = card_says(text, tokens, verb["at"][0], verb["at"][1])
            gold = verb["tense"]
            confusion[(gold, said)] += 1
            if gold in SCORED:
                scored += 1
                right += said == gold
            else:
                traps += 1
                alarms += said in SCORED
            if said != gold:
                print(f"  {verb['form']}: gold {gold}, card {said} | {text[:90]}")

    accuracy = right / scored if scored else 0.0
    false_alarm = alarms / traps if traps else 0.0
    print(f"\npc_imp_accuracy {accuracy:.4f} ({right} of {scored} PC + IMP verbs)")
    print(f"trap_false_alarm {false_alarm:.4f} ({alarms} of {traps} traps called PC or IMP)")
    for (gold, said), count in sorted(confusion.items()):
        print(f"  gold {gold:5} card {said:7} {count}")

    note = evals.pinned(
        f"sentences={len(rows)} tags=tagger spent=${reader.spent.cost():.3f}; "
        "gold read by ling-fr 2026-11-05",
        [args.gold],
    )
    out = [
        evals.Row(
            at=date.today().isoformat(),
            stage=STAGE,
            corpus=CORPUS,
            system=SYSTEM,
            version=reader.name,
            metric=metric,
            score=round(score, 4),
            n=n,
            note=note,
        )
        for metric, score, n in (
            ("pc_imp_accuracy", accuracy, scored),
            ("trap_false_alarm", false_alarm, traps),
        )
    ]
    if args.record:
        evals.append(out, args.ledger)
        print(f"appended {len(out)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
