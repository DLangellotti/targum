"""Hint the commonest modern sense where a topic run's gloss gives a rarer one first
(targum-internal#605).

Pilot 3's misses were mostly glosses that lead with a rare sense (עצב "to be sad; nerve",
מטען "cargo; load"): the tagger sees only the gloss and follows it. This pass asks one
model, for each lemma of a run, the commonest modern sense in a few words and whether the
gloss leads with it (`topics.hint_system_prompt`). It never sees a topic. Where the gloss
does not lead with it, the lemma carries that sense, and any other sense the gloss cache
holds under the lemma's other keys, as its hint (`topics.hinted`).

The result is a new run directory whose `lemmas.json` holds only the lemmas whose gloss
changed, ready for `scripts/tag_topics.py --run <out>` to tag again, and `hints.json`
beside it with every answer, its usage and its cost. `--cap` is hard, checked against
the worst case of every request before the first is sent; `--dry-run` quotes.

    op run --env-file op.env -- .venv/bin/python scripts/topic_hints.py \\
        --from-run pilot3-2026-10-31 --out pilot3-hints-2026-10-31 --cap 1 --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from typing import Any

from targum import topics
from targum.paths import write_atomic

MODEL = "claude-opus-5-5"
PER_REQUEST = 100
MAX_TOKENS = 8000
EFFORT = "low"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--from-run", required=True, help="The run whose lemmas to read.")
    parser.add_argument("--out", required=True, help="The new run directory's name.")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--cap", type=float, required=True, help="Dollars, never passed.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    source = json.loads((topics.RESEARCH / args.from_run / "lemmas.json").read_text("utf-8"))
    lemmas = [topics.Lemma(**row) for row in source["lemmas"]]
    chunks = [
        list(range(start, min(start + PER_REQUEST, len(lemmas))))
        for start in range(0, len(lemmas), PER_REQUEST)
    ]
    system = topics.hint_system_prompt()
    worst = sum(
        topics.worst_case(
            args.model,
            len(system) + len(topics.user_message([lemmas[i] for i in chunk], chunk[0])),
            MAX_TOKENS,
            batch=False,
        )
        for chunk in chunks
    )
    print(f"{len(lemmas)} lemmas in {len(chunks)} requests; at most ${worst:.2f} on {args.model}.")
    if worst > args.cap:
        print(f"Refused: the worst case passes the ${args.cap:.2f} cap. Nothing sent.")
        return 3
    if args.dry_run:
        print("Dry run: nothing sent.")
        return 0
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        print("No Anthropic key: run under `op run --env-file op.env`.", file=sys.stderr)
        return 1
    import anthropic

    client = anthropic.Anthropic()
    out = topics.RESEARCH / args.out
    out.mkdir(parents=True, exist_ok=True)
    answers: dict[int, tuple[str, bool]] = {}
    usage = topics.Usage()
    raw: list[dict[str, Any]] = []
    for chunk in chunks:
        message = client.messages.create(
            model=args.model,
            max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[
                {
                    "role": "user",
                    "content": topics.user_message([lemmas[i] for i in chunk], chunk[0]),
                }
            ],
            output_config={
                "effort": EFFORT,
                "format": {"type": "json_schema", "schema": topics.hint_schema()},
            },
        )
        text = "".join(b.text for b in message.content if b.type == "text")
        answers.update(topics.parse_hints(text, chunk))
        got = message.usage
        usage.add(
            topics.Usage(
                input_tokens=got.input_tokens,
                cache_write_tokens=got.cache_creation_input_tokens or 0,
                cache_read_tokens=got.cache_read_input_tokens or 0,
                output_tokens=got.output_tokens,
                requests=1,
            )
        )
        raw.append({"chunk": chunk[0], "text": text, "usage": got.model_dump()})
        # Checkpoint after every paid request.
        write_atomic(out / "hints-raw.json", json.dumps(raw, ensure_ascii=False, indent=1))

    changed: list[topics.Lemma] = []
    rows = []
    for i, one in enumerate(lemmas):
        if i not in answers:
            continue
        sense, first = answers[i]
        others = topics.other_senses(one.lemma, one.pos, one.gloss)
        new = topics.hinted(one, sense, first, others)
        rows.append(
            {
                "lemma": one.lemma,
                "gloss": one.gloss,
                "sense": sense,
                "first": first,
                "others": others,
                "hint": new.hint,
            }
        )
        if new.hint:
            changed.append(new)
    spent = topics.cost(args.model, usage, batch=False)
    write_atomic(
        out / "hints.json",
        json.dumps(
            {
                "version": topics.HINT_VERSION,
                "from_run": args.from_run,
                "model": args.model,
                "usage": asdict(usage),
                "cost_usd": round(spent, 4),
                "answered": len(answers),
                "changed": len(changed),
                "rows": rows,
            },
            ensure_ascii=False,
            indent=1,
        ),
    )
    write_atomic(
        out / "lemmas.json",
        json.dumps(
            {
                "registers": source.get("registers", []),
                "prompt": topics.PROMPT_VERSION,
                "hint": topics.HINT_VERSION,
                "from_run": args.from_run,
                "lemmas": [asdict(one) for one in changed],
                "dropped": [],
                "no_gloss": [],
            },
            ensure_ascii=False,
            indent=1,
        ),
    )
    print(
        f"{len(answers)} of {len(lemmas)} answered; {len(changed)} glosses changed;"
        f" ${spent:.4f} spent. Tag them: scripts/tag_topics.py --run {args.out} --cap ..."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
