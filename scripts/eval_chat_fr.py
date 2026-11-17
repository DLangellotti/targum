"""Does the French chat say a right line back and fix a wrong one? (targum-internal#644)

French Beta asks for chat evals in the language, with floors (design.md, "A badge is a
promise, checked"). The recast is the line of record, so this is the set that matters
most: forty learner lines, hand-written by ling-fr (`evals/chat-fr-cases.jsonl`), sent
one each as the reader's turn to the French contract (`chat/hebrew.py`,
`french_contract`), each reply read back by the contract's own parser and scored by the
rubric in `chat/rubric.py`. No model judges anything.

- 15 **correct** lines: no `~ ` line shown, the line said back as written, and a
  woman's agreement (*je suis allée*, *contente*) kept.
- 5 **register** lines, spoken French that is right (*je sais pas*, *on va au cinéma*):
  no `~ ` line, because register is not an error (D5, 2026-11-05).
- 20 **error** lines of the kinds the contract names: fixed in the recast, with a `~ `
  line under it.

Rows go to `evals/ledger.jsonl` as stage `chat`, corpus `fr-cases` (`fr-cases-ru` for a
reader who reads Russian, `--gloss Russian`), system `chat-contract/fr<version>`, the
French contract's own version (`hebrew.FRENCH_CONTRACT_VERSION`). `stages` counts
French's chat evals as present once every floor on `fr-cases` has a row that holds it.

**It spends, and only when told to.** One call a case at the chat's own model; nothing
is cached, because the question is what the model does today. Run bare, it prices the
run from the prompt it would send and calls nothing; `--spend` is what calls the model
(qa on #1287). `--dry-run` is accepted and is the same as running it bare.

    .venv/bin/python scripts/eval_chat_fr.py
    op run --env-file op.env -- .venv/bin/python scripts/eval_chat_fr.py --spend --keep replies.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import evals  # noqa: E402
from targum.chat import CHAT_MODEL, hebrew, prompts, rubric  # noqa: E402
from targum.level import EMPTY  # noqa: E402
from targum.usage import Usage  # noqa: E402

#: The reply ceiling `eval_grading.turns` sends, and what a short reply runs to: the
#: contract's recast, its gloss, a `~ ` line, and one or two French sentences with theirs.
MAX_REPLY = 600
TYPICAL_REPLY = 250

#: Characters to a token, for pricing a prompt without sending it. French and a word list
#: run nearer three than four; three keeps the estimate on the high side.
CHARACTERS_PER_TOKEN = 3.0


#: The system a run is recorded under: the French contract at its version, so a run of a
#: contract since changed is history and is held to no floor.
SYSTEM = f"chat-contract/fr{hebrew.FRENCH_CONTRACT_VERSION}"


def corpus_for(gloss: str) -> str:
    return "fr-cases" if gloss == "English" else f"fr-cases-{gloss[:2].lower()}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--cases", type=Path, default=rubric.FRENCH_CASES)
    parser.add_argument("--known", type=int, default=300)
    parser.add_argument("--gloss", default="English", choices=("English", "Russian"))
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    parser.add_argument("--keep", type=Path, help="write every reply out, to read by hand")
    parser.add_argument(
        "--spend", action="store_true", help="call the model and record the run; it costs"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="price it and call nothing (the default)"
    )
    parser.add_argument("--note", default="")
    args = parser.parse_args(argv)
    if args.spend and args.dry_run:
        sys.exit("--spend and --dry-run ask for opposite things; name one")

    cases = rubric.load(args.cases)
    common = hebrew.common_words(language="fr")
    if not common:
        sys.exit("wordfreq is not installed: uv sync --extra difficulty")
    known = common[: args.known]
    ledger = hebrew.ledger_block(replace(EMPTY, language="fr"), known, common)
    contract = hebrew.contract_for("fr", args.gloss)
    system = prompts.SYSTEM + "\n\n" + contract

    if not args.spend:
        counts = {kind: sum(1 for one in cases if one.kind == kind) for kind in rubric.KINDS}
        sent = sum(len(one.sent) for one in cases)
        prompt = round((len(system) + len(ledger)) / CHARACTERS_PER_TOKEN)
        inputs = prompt * len(cases) + round(sent / CHARACTERS_PER_TOKEN)
        typical, ceiling = Usage(), Usage()
        typical.add(CHAT_MODEL, inputs, TYPICAL_REPLY * len(cases))
        ceiling.add(CHAT_MODEL, inputs, MAX_REPLY * len(cases))
        print(
            f"{len(cases)} cases: {counts['correct']} correct, {counts['register']} register, "
            f"{counts['error']} error, into {args.gloss} ({corpus_for(args.gloss)})."
        )
        print(f"{len(cases)} calls to {CHAT_MODEL}, no judge, nothing cached.")
        print(f"About {prompt:,} input tokens a call; {inputs:,} in all.")
        print(
            f"Estimate: ${typical.cost():.2f} at {TYPICAL_REPLY} output tokens a reply, "
            f"${ceiling.cost():.2f} if every reply ran to the {MAX_REPLY}-token ceiling."
        )
        print("Nothing was called. --spend runs it.")
        return

    import anthropic
    from eval_grading import turns

    usage = Usage()
    replies = turns(
        anthropic.Anthropic(),
        contract,
        ledger,
        len(cases),
        [one.sent for one in cases],
        None,
        None,
        1,
        usage,
    )
    verdicts = [rubric.score(one, reply) for one, reply in zip(cases, replies, strict=True)]
    summary = rubric.summarise(verdicts)

    print(f"{len(replies)} learner lines sent to {CHAT_MODEL}\n")
    for one in verdicts:
        wrong = (
            (one.case.kind != "error" and one.why_shown)
            or (one.case.kind == "error" and not (one.fixed and one.why_shown))
            or one.gender_changed
        )
        if wrong:
            print(f"  {one.case.id} [{one.case.kind}] {one.case.sent}\n      > {one.recast}")
    for metric, score in summary.scores.items():
        print(f"{metric}: {score} (over {summary.over[metric]})")
    print(f"\nThis run cost ${usage.cost():.2f}.")

    if args.keep:
        args.keep.write_text(
            json.dumps(
                [
                    {"id": one.case.id, "sent": one.case.sent, "reply": reply}
                    for one, reply in zip(verdicts, replies, strict=True)
                ],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Replies written to {args.keep}.")

    note = evals.pinned(
        args.note or f"ling-fr's learner lines sent as the reader's turn, into {args.gloss}",
        [args.cases],
    )
    rows = [
        evals.Row(
            at=date.today().isoformat(),
            stage="chat",
            corpus=corpus_for(args.gloss),
            metric=metric,
            score=float(score),
            n=summary.over[metric],
            system=SYSTEM,
            version=CHAT_MODEL,
            note=note,
        )
        for metric, score in summary.scores.items()
    ]
    print(f"\nRecorded {evals.append(rows, args.ledger)} rows.")


if __name__ == "__main__":
    main()
