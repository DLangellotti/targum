"""Can the chat stay inside a reader's words? Measured, before any page says it can.

The Hebrew mode (`chat/hebrew.py`) hands the model a list — the reader's known lemmas and
a floor of the commonest words — and asks it to write inside them, one new word a
sentence at most. Whether a model can hold to a list is unproven and models are bad at
it, so the claim "graded to your level" is not made anywhere until this says what share
of what it writes falls outside the list. targum-internal#213's gate reads the number.

**What it does.** Builds a word list the way the mode does (a synthetic ledger of N
common words plus the floor), asks the model for K turns of conversation under the same
contract against fixed prompts, segments each turn with the Hebrew rules, annotates it
with the same DICTA annotator every text on the shelf is read with, and counts the share
of content lemmas — names and numbers left out, as the ledger leaves them out — that are
not in the list. Appended as rows to `evals/ledger.jsonl` (stage `grading`), so the next
model or the next prompt can be compared with this one.

**What it costs.** K model calls at the chat's own model and effort, and one DICTA load.
Nothing is cached by design: the question is what the model does today.

    set -a && . ./.env && set +a && .venv/bin/python scripts/eval_grading.py --turns 20
"""

from __future__ import annotations

import argparse
import random
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import evals  # noqa: E402
from targum.annotate import Annotator  # noqa: E402
from targum.annotate.base import NOT_VOCABULARY  # noqa: E402
from targum.chat import CHAT_MODEL, EFFORT, exemplars, hebrew, prompts  # noqa: E402
from targum.level import EMPTY  # noqa: E402
from targum.models import Block, BlockKind, Document  # noqa: E402
from targum.segment import segment_document  # noqa: E402
from targum.translate.anthropic_provider import output_config  # noqa: E402
from targum.usage import Usage  # noqa: E402

#: What a reader might say, in the two languages a reader says things in. Fixed, so two
#: runs measure the model and not the prompts.
OPENERS = (
    "שלום, מה שלומך היום?",
    "I went to the market this morning and bought bread.",
    "אני לומד עברית כבר שנה.",
    "What is your favourite book?",
    "היום יום שישי ואני עייף.",
    "Tell me about the weather in Jerusalem.",
    "אני אוהב לקרוא ספרים בערב.",
    "My family is coming to visit next week.",
    "מה אתה חושב על החדשות?",
    "I do not understand this word.",
)


def word_list(known: int) -> list[str]:
    common = hebrew.common_words()
    return common[: known + len(common)]


def pool_openers(
    pool: list[exemplars.Exemplar], allowed: set[str], count: int, seed: int
) -> tuple[list[str], set[int]]:
    """Openers a reader at this list could have written (targum-internal#220): Tatoeba
    sentences whose content lemmas all fall inside the list, the Hebrew of one and the
    English of the next, so the fixed ten are replaced by openers graded to `--known`.
    Returns them and the ids used, which the exemplars then leave out."""
    inside = [row for row in pool if row.lemmas and row.lemmas <= allowed and row.english]
    random.Random(seed).shuffle(inside)
    chosen = inside[:count]
    openers = [row.hebrew if n % 2 == 0 else row.english for n, row in enumerate(chosen)]
    return openers, {row.id for row in chosen}


def turns(
    client: object,
    contract: str,
    ledger: str,
    count: int,
    openers: Sequence[str] = OPENERS,
    pool: list[exemplars.Exemplar] | None = None,
    allowed: set[str] | None = None,
    seed: int = 1,
    usage: Usage | None = None,
) -> list[str]:
    out: list[str] = []
    for n in range(count):
        opener = openers[n % len(openers)]
        block = ledger
        if pool and allowed is not None:
            picked = exemplars.pick(pool, allowed, seed=seed * 1000 + n)
            if picked:
                block = ledger + "\n\n" + exemplars.block(picked)
        reply = client.messages.create(  # type: ignore[attr-defined]
            model=CHAT_MODEL,
            max_tokens=600,
            system=[
                {"type": "text", "text": prompts.SYSTEM + "\n\n" + contract},
                {"type": "text", "text": block},
            ],
            messages=[{"role": "user", "content": opener}],
            **output_config(CHAT_MODEL, EFFORT),
        )
        if usage is not None:
            usage.add(CHAT_MODEL, reply.usage.input_tokens, reply.usage.output_tokens)
        out.append("".join(getattr(block, "text", "") for block in reply.content))
    return out


def outside_share(hebrew_lines: list[str], allowed: set[str]) -> tuple[float, int]:
    """The share of content lemmas not in the list, and how many lemmas were counted."""
    document = Document(
        source="eval:grading",
        title="grading",
        language="he",
        blocks=[
            Block(id=f"b{n:04d}", kind=BlockKind.paragraph, text=line)
            for n, line in enumerate(hebrew_lines)
        ],
        ingester="eval",
    )
    segmented = segment_document(document)
    annotation = Annotator().annotate(segmented)
    counted = outside = 0
    for tokens in annotation.tokens.values():
        for token in tokens:
            if token.pos in NOT_VOCABULARY or not token.lemma:
                continue
            counted += 1
            if token.lemma not in allowed:
                outside += 1
    return (outside / counted if counted else 0.0), counted


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--turns", type=int, default=20)
    parser.add_argument(
        "--known", type=int, default=300, help="how many words the synthetic reader knows"
    )
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    parser.add_argument(
        "--pool", type=Path, help="the Tatoeba pool: openers graded to --known (#220)"
    )
    parser.add_argument(
        "--exemplars", action="store_true", help="ride the pool's sentences as exemplars (#218)"
    )
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    import anthropic

    common = hebrew.common_words()
    if not common:
        sys.exit("wordfreq is not installed: uv sync --extra difficulty")
    known = common[: args.known]
    allowed = set(common) | set(known)
    ledger = hebrew.ledger_block(EMPTY, known, common)
    openers: Sequence[str] = OPENERS
    pool = exemplars.load(args.pool) if args.pool else []
    if args.pool:
        openers, used = pool_openers(pool, allowed, args.turns, args.seed)
        if not openers:
            sys.exit("no pool sentence falls inside the list; build more of the pool first")
        pool = [row for row in pool if row.id not in used]
    usage = Usage()
    replies = turns(
        anthropic.Anthropic(),
        hebrew.CONTRACT,
        ledger,
        args.turns,
        openers,
        pool if args.exemplars else None,
        allowed,
        args.seed,
        usage,
    )

    kept = [pair.hebrew for reply in replies for pair in hebrew.pairs(reply)]
    unpaired = sum(1 for reply in replies for pair in hebrew.pairs(reply) if not pair.english)
    share, counted = outside_share(kept, allowed)
    print(f"{args.turns} turns, {len(kept)} Hebrew lines, {counted} content lemmas")
    print(f"outside the list: {share:.1%}   lines without their English: {unpaired}")
    print(f"spent ${usage.cost():.2f} over {usage.calls} calls")

    today = date.today().isoformat()
    note = f"known={args.known} turns={args.turns}"
    if args.pool:
        note += f" openers=tatoeba seed={args.seed}"
    if args.exemplars:
        note += " exemplars=on"
    rows = [
        evals.Row(
            today,
            "grading",
            "chat",
            CHAT_MODEL,
            "outside_share",
            round(share, 4),
            counted,
            note=note,
        ),
        evals.Row(
            today, "grading", "chat", CHAT_MODEL, "unpaired_lines", float(unpaired), len(kept)
        ),
    ]
    evals.append(rows, args.ledger)
    print(f"appended {len(rows)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
