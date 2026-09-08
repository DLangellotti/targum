"""Does the chat answer a question about the text correctly? Measured against a person's
answer, before any page trusts it.

Ask on the word card sends the model a note of where the reader is — the text, the
sentence, the word — and their question, and the reply is English about the text
(`chat/prompts.py`; `session.framed` is what composes the note). Nothing measured
whether the answer was right. HeQ (`chat/heq.py`) is 30,147 human questions over
paragraphs of modern Hebrew, each with the span that answers it, so the same paragraph
can be put on a stubbed page, the same question asked, and the reply set against the
span (targum-internal#223).

**Two scores.** Whether any accepted span appears in the reply, verbatim once the
points and the punctuation are stripped — `span_found_share`, the number that says the
chat put the answer in front of the reader. And token F1 between the reply's Hebrew
words and the best-matching span, SQuAD's own measure loosened to the Hebrew script,
because an English reply quotes the Hebrew where it helps and the English around it is
not the answer. Both are appended to `evals/ledger.jsonl` as stage `ask`, corpus `heq`.

**What it costs.** N chat turns at the chat's model and effort. Nothing is cached by
design: the question is what the model does today.

    targum models fetch heq
    set -a && . ./.env && set +a && \\
      .venv/bin/python scripts/eval_ask.py --questions 200 --save out.jsonl
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import evals  # noqa: E402
from targum.chat import CHAT_MODEL, EFFORT, heq, prompts  # noqa: E402
from targum.chat.session import framed  # noqa: E402
from targum.translate.anthropic_provider import output_config  # noqa: E402
from targum.usage import Usage  # noqa: E402
from targum.vocalize.base import strip_nikkud  # noqa: E402

#: A run of Hebrew letters, which is what a span is made of once the points are gone.
#: A maqaf, geresh or gershayim *between* letters is part of the word, since HeQ's spans
#: keep רשב"י as one; the same mark after the last letter is the sentence's quotation
#: mark and is not.
HEBREW_WORD = re.compile(r"[א-ת](?:[׳״־\"']?[א-ת])*")


def plain(text: str) -> str:
    """The text with its points gone and its punctuation reduced to spaces, so a span
    quoted with different quotation marks or a final stop is still the same span."""
    bare = strip_nikkud(text)[0]
    return " ".join(HEBREW_WORD.findall(bare))


def hebrew_tokens(text: str) -> list[str]:
    return plain(text).split()


def span_found(reply: str, answers: tuple[str, ...]) -> bool:
    """Whether the reply carries an accepted span verbatim, points and punctuation aside."""
    said = f" {plain(reply)} "
    return any(f" {plain(span)} " in said for span in answers if plain(span))


def token_f1(reply: str, answers: tuple[str, ...]) -> float:
    """SQuAD's F1, over the Hebrew words of the reply and the best-matching span."""
    got = hebrew_tokens(reply)
    best = 0.0
    for span in answers:
        want = hebrew_tokens(span)
        if not got or not want:
            continue
        counts: dict[str, int] = {}
        for word in want:
            counts[word] = counts.get(word, 0) + 1
        shared = 0
        for word in got:
            if counts.get(word, 0) > 0:
                counts[word] -= 1
                shared += 1
        if not shared:
            continue
        precision, recall = shared / len(got), shared / len(want)
        best = max(best, 2 * precision * recall / (precision + recall))
    return best


def sample(questions: list[heq.Question], count: int, seed: int) -> list[heq.Question]:
    drawn = list(questions)
    random.Random(seed).shuffle(drawn)
    return drawn[:count]


def ask(client: object, system: list[dict[str, str]], one: heq.Question, usage: Usage) -> str:
    """One Ask turn, composed the way the page composes it: the paragraph is the
    sentence on the reader's screen, the article is the text, and the question is theirs."""
    content = framed(one.question, {"document": one.title, "sentence": one.context})
    reply = client.messages.create(  # type: ignore[attr-defined]
        model=CHAT_MODEL,
        max_tokens=600,
        system=system,
        messages=[{"role": "user", "content": content}],
        **output_config(CHAT_MODEL, EFFORT),
    )
    usage.add(CHAT_MODEL, reply.usage.input_tokens, reply.usage.output_tokens)
    return "".join(getattr(block, "text", "") for block in reply.content).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--questions", type=int, default=200)
    parser.add_argument("--split", choices=heq.SPLITS, default=heq.DEFAULT_SPLIT)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    parser.add_argument("--show", type=int, default=8, help="how many misses to print")
    parser.add_argument("--save", type=Path, help="write every question, reply and score here")
    args = parser.parse_args()

    import anthropic

    chosen = sample(heq.load(args.split), args.questions, args.seed)
    if not chosen:
        sys.exit("no HeQ questions; run targum models fetch heq first")

    client = anthropic.Anthropic()
    usage = Usage()
    system = [{"type": "text", "text": prompts.SYSTEM}]
    # Every reply is written to --save the moment it exists, and a run that starts with
    # that file already there reuses them, the way the recast eval does.
    earlier: dict[str, str] = {}
    if args.save and args.save.is_file():
        for line in args.save.read_text(encoding="utf-8").splitlines():
            if line.strip():
                kept = json.loads(line)
                if kept.get("got"):
                    earlier[str(kept["id"])] = str(kept["got"])
    if earlier:
        print(f"  {len(earlier)} replies kept from an earlier run", flush=True)
    replies: list[str] = []
    for n, one in enumerate(chosen):
        if one.id in earlier:
            replies.append(earlier[one.id])
            continue
        replies.append(ask(client, system, one, usage))
        if args.save:
            args.save.parent.mkdir(parents=True, exist_ok=True)
            with args.save.open("a", encoding="utf-8") as out:
                out.write(json.dumps({"id": one.id, "got": replies[-1]}, ensure_ascii=False) + "\n")
        if (n + 1) % 20 == 0:
            print(f"  {n + 1}/{len(chosen)} asked", flush=True)

    found = [span_found(reply, one.answers) for one, reply in zip(chosen, replies, strict=True)]
    scores = [token_f1(reply, one.answers) for one, reply in zip(chosen, replies, strict=True)]
    unanswered = sum(1 for reply in replies if not reply)
    found_share = sum(found) / len(chosen)
    f1 = sum(scores) / len(chosen)

    if args.save:
        with args.save.open("w", encoding="utf-8") as out:
            for one, reply, hit, score in zip(chosen, replies, found, scores, strict=True):
                out.write(
                    json.dumps(
                        {
                            "id": one.id,
                            "source": one.source,
                            "question": one.question,
                            "answers": list(one.answers),
                            "got": reply,
                            "span_found": hit,
                            "token_f1": round(score, 3),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    by_source: dict[str, list[bool]] = {}
    for one, hit in zip(chosen, found, strict=True):
        by_source.setdefault(one.source, []).append(hit)
    print(f"{len(chosen)} questions from HeQ {args.split}, seed={args.seed}")
    print(
        f"span found: {found_share:.1%}   token F1: {f1:.3f}   no reply: {unanswered}   "
        + "   ".join(
            f"{source}: {sum(hits) / len(hits):.0%} of {len(hits)}"
            for source, hits in sorted(by_source.items())
        )
    )
    print(f"spent ${usage.cost():.2f} over {usage.calls} calls")
    shown = 0
    for one, reply, hit in zip(chosen, replies, found, strict=True):
        if hit or shown >= args.show:
            continue
        shown += 1
        print(f"\n  {one.question}\n  want: {' | '.join(one.answers)}\n  got:  {reply[:240]}")

    today = date.today().isoformat()
    note = f"split={args.split} questions={len(chosen)} seed={args.seed} effort={EFFORT}"
    rows_out = [
        evals.Row(
            today,
            "ask",
            "chat",
            CHAT_MODEL,
            "span_found_share",
            round(found_share, 4),
            len(chosen),
            corpus="heq",
            note=note,
        ),
        evals.Row(
            today,
            "ask",
            "chat",
            CHAT_MODEL,
            "token_f1",
            round(f1, 4),
            len(chosen),
            corpus="heq",
            note=note,
        ),
        evals.Row(
            today,
            "ask",
            "chat",
            CHAT_MODEL,
            "unanswered",
            float(unanswered),
            len(chosen),
            corpus="heq",
            note=note,
        ),
    ]
    evals.append(rows_out, args.ledger)
    print(f"\nappended {len(rows_out)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
