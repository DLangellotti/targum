"""Is the recast right? Measured against a native speaker's Hebrew, before any page trusts it.

The Hebrew contract (`chat/hebrew.py`) opens every reply with the reader's own line
recast into Hebrew, and that line is the line of record: a wrong recast is what the
reader saves. Nothing measured it. Tatoeba's links give English sentences with a Hebrew
rendering written by a native speaker — the pool `scripts/tatoeba_pool.py` builds,
rows marked `from_english` — so the same sentence can be sent as a reader's English turn
and the `> ` line read back and set against a human's (targum-internal#219).

**Two scores.** Content-lemma overlap with the reference (Jaccard, both sides through
the build lemmatizer with the points stripped): a cheap number that rewards saying it
with the same words and punishes an English rendering that drifted. And a judge — the
chat model, asked whether the candidate is a correct and idiomatic Hebrew rendering of
the English, given the reference — because a right recast can use different words.
Both are appended to `evals/ledger.jsonl` as stage `recast`, so the next model or
prompt is compared with this one.

**With and without exemplars.** `--exemplars` rides the Tatoeba sentences inside the
synthetic reader's words (`chat/exemplars.py`) the way a live turn does; run both, and
the difference is #218's number. The sentences sent as turns are never among the
exemplars: `pick` is handed the pool with the eval's own rows removed.

**What it costs.** N chat turns and N judge calls at the chat's model. Nothing is cached
by design: the question is what the model does today.

    set -a && . ./.env && set +a && \\
      .venv/bin/python scripts/eval_recast.py --pool ~/.targum/exemplars.jsonl --pairs 200
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import evals  # noqa: E402
from targum.annotate import lemma  # noqa: E402
from targum.annotate.base import NOT_VOCABULARY  # noqa: E402
from targum.chat import CHAT_MODEL, EFFORT, exemplars, hebrew, prompts  # noqa: E402
from targum.level import EMPTY  # noqa: E402
from targum.models import Segment  # noqa: E402
from targum.translate.anthropic_provider import output_config  # noqa: E402
from targum.usage import Usage  # noqa: E402
from targum.vocalize.base import strip_nikkud  # noqa: E402

#: A reference longer than this is a paragraph, and a recast eval is about sentences.
MAX_WORDS = 12

#: Who scores the recast. Not the writer: a model grading its own Hebrew prefers its own
#: Hebrew, and the first pilot had Opus judging Opus. Decided 2026-09-07: Sonnet 5 judges,
#: and `--judge` names another.
JUDGE_MODEL = "claude-sonnet-5"

JUDGE = """You are checking one line of Hebrew written by a language app for a learner.

The learner wrote, in English:
{english}

A native Hebrew speaker rendered the same sentence as:
{reference}

The app wrote:
{candidate}

Is the app's line a correct and idiomatic Hebrew rendering of the English — what a Hebrew
speaker would actually say, with the same meaning? Different words from the native
rendering are fine; a calque, an English word order, a wrong form, or a changed meaning is
not. Ignore the vowel points. Answer YES or NO on the first line, then one short sentence
saying why."""


def pool_rows(path: Path) -> list[dict[str, Any]]:
    """English originals with a native Hebrew rendering, at sentence length. Streamed
    and filtered on the way in: the whole pool as Python objects is what tipped an
    8 GB laptop into killing the run."""
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as lines:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            if (
                raw.get("from_english")
                and raw.get("en")
                and len(str(raw["he"]).split()) <= MAX_WORDS
            ):
                rows.append(raw)
    return rows


def sample(rows: list[dict[str, Any]], count: int, seed: int) -> list[dict[str, Any]]:
    fit = list(rows)
    draw = random.Random(seed)
    draw.shuffle(fit)
    return fit[:count]


def content_lemmas(reader: lemma.Lemmatizer, lines: list[str]) -> list[set[str]]:
    segments = [
        Segment(id=f"s{n}", block_id="eval", block_index=0, index=n, text=strip_nikkud(line)[0])
        for n, line in enumerate(lines)
    ]
    read = reader.lemmas(segments, "he") if any(line.strip() for line in lines) else {}
    return [
        {
            token.lemma
            for token in read.get(f"s{n}", [])
            if token.lemma and (token.pos or "") not in NOT_VOCABULARY
        }
        for n in range(len(lines))
    ]


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def recast(client: object, system: list[dict[str, str]], english: str, usage: Usage) -> str:
    reply = client.messages.create(  # type: ignore[attr-defined]
        model=CHAT_MODEL,
        max_tokens=600,
        system=system,
        messages=[{"role": "user", "content": english}],
        **output_config(CHAT_MODEL, EFFORT),
    )
    usage.add(CHAT_MODEL, reply.usage.input_tokens, reply.usage.output_tokens)
    text = "".join(getattr(block, "text", "") for block in reply.content)
    for pair in hebrew.pairs(text):
        if pair.recast:
            return pair.hebrew
    return ""


def judge(
    client: object,
    english: str,
    reference: str,
    candidate: str,
    usage: Usage,
    model: str = JUDGE_MODEL,
) -> tuple[str, str]:
    """ "yes", "no", or "none" where the judge wrote nothing — counted apart, never as a
    no: the first run counted empty replies as wrong and the number could not be read."""
    reply = client.messages.create(  # type: ignore[attr-defined]
        model=model,
        max_tokens=400,
        messages=[
            {
                "role": "user",
                "content": JUDGE.format(english=english, reference=reference, candidate=candidate),
            }
        ],
        **output_config(model, EFFORT),
    )
    usage.add(model, reply.usage.input_tokens, reply.usage.output_tokens)
    text = "".join(getattr(block, "text", "") for block in reply.content).strip()
    if not text:
        return "none", ""
    first = text.splitlines()[0].strip().upper()
    return ("yes" if first.startswith("YES") else "no"), text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--pairs", type=int, default=200)
    parser.add_argument("--known", type=int, default=300)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--exemplars", action="store_true", help="ride the Tatoeba exemplars")
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    parser.add_argument("--show", type=int, default=8, help="how many judged-wrong to print")
    parser.add_argument(
        "--save", type=Path, help="write every pair, recast and verdict here, JSONL"
    )
    parser.add_argument("--judge", default=JUDGE_MODEL, help="the model that scores the recast")
    args = parser.parse_args()

    import anthropic

    common = hebrew.common_words()
    if not common:
        sys.exit("wordfreq is not installed: uv sync --extra difficulty")
    known = common[: args.known]
    allowed = set(common) | set(known)
    ledger = hebrew.ledger_block(EMPTY, known, common)

    rows = pool_rows(args.pool)
    chosen = sample(rows, args.pairs, args.seed)
    if not chosen:
        sys.exit("no English-original rows in the pool; build it with --limit first")
    held_out = {int(row["id"]) for row in chosen}
    pool = [row for row in exemplars.load(args.pool) if row.id not in held_out]

    client = anthropic.Anthropic()
    usage = Usage()
    # Every recast is written to --save the moment it exists, and a run that starts
    # with that file already there reuses them: a run that died at 180 of 200 (the API
    # account ran out of credit, 2026-09-07) had bought the recasts and kept none.
    earlier: dict[int, str] = {}
    if args.save and args.save.is_file():
        for line in args.save.read_text(encoding="utf-8").splitlines():
            if line.strip():
                kept = json.loads(line)
                if kept.get("got"):
                    earlier[int(kept["id"])] = str(kept["got"])
    if earlier:
        print(f"  {len(earlier)} recasts kept from an earlier run", flush=True)
    candidates: list[str] = []
    for n, row in enumerate(chosen):
        if int(row["id"]) in earlier:
            candidates.append(earlier[int(row["id"])])
            continue
        block = ledger
        if args.exemplars:
            picked = exemplars.pick(pool, allowed, seed=args.seed * 1000 + n)
            if picked:
                block = ledger + "\n\n" + exemplars.block(picked)
        system = [
            {"type": "text", "text": prompts.SYSTEM + "\n\n" + hebrew.CONTRACT},
            {"type": "text", "text": block},
        ]
        candidates.append(recast(client, system, str(row["en"]), usage))
        if args.save:
            args.save.parent.mkdir(parents=True, exist_ok=True)
            with args.save.open("a", encoding="utf-8") as out:
                out.write(
                    json.dumps(
                        {"id": row["id"], "en": row["en"], "ref": row["he"], "got": candidates[-1]},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        if (n + 1) % 20 == 0:
            print(f"  {n + 1}/{len(chosen)} recast", flush=True)

    references = [str(row["he"]) for row in chosen]
    # The lemmatizer is loaded after the turns and dropped before the judging, so the
    # model is not held in memory through four hundred API calls.
    reader = lemma.for_source("chat:eval")
    got = content_lemmas(reader, candidates)
    want = content_lemmas(reader, references)
    del reader
    overlaps = [jaccard(a, b) for a, b in zip(got, want, strict=True)]
    unpaired = sum(1 for line in candidates if not line)

    verdicts: list[tuple[str, str]] = []
    for n, (row, candidate) in enumerate(zip(chosen, candidates, strict=True)):
        if not candidate:
            verdicts.append(("no", "no recast line"))
            continue
        verdicts.append(judge(client, str(row["en"]), str(row["he"]), candidate, usage, args.judge))
        if (n + 1) % 20 == 0:
            print(f"  {n + 1}/{len(chosen)} judged", flush=True)
    unjudged = sum(1 for verdict, _ in verdicts if verdict == "none")
    judged = len(verdicts) - unjudged
    ok_share = (sum(1 for verdict, _ in verdicts if verdict == "yes") / judged) if judged else 0.0
    overlap = sum(overlaps) / len(overlaps)
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        with args.save.open("w", encoding="utf-8") as out:
            for row, candidate, (verdict, why), score in zip(
                chosen, candidates, verdicts, overlaps, strict=True
            ):
                out.write(
                    json.dumps(
                        {
                            "id": row["id"],
                            "en": row["en"],
                            "ref": row["he"],
                            "got": candidate,
                            "verdict": verdict,
                            "why": why,
                            "overlap": round(score, 3),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    print(f"{len(chosen)} pairs, exemplars {'on' if args.exemplars else 'off'}, known={args.known}")
    print(
        f"judge says right: {ok_share:.1%} of {judged} judged   lemma overlap: {overlap:.3f}   "
        f"no recast: {unpaired}   judge wrote nothing: {unjudged}"
    )
    print(f"spent ${usage.cost():.2f} over {usage.calls} calls")
    shown = 0
    for row, candidate, (verdict, why) in zip(chosen, candidates, verdicts, strict=True):
        if verdict != "no" or shown >= args.show:
            continue
        shown += 1
        reason = why.splitlines()[-1] if why else "(no reason given)"
        print(f"\n  {row['en']}\n  ref: {row['he']}\n  got: {candidate}\n  {reason}")

    today = date.today().isoformat()
    riding = "on" if args.exemplars else "off"
    note = (
        f"known={args.known} pairs={len(chosen)} seed={args.seed} exemplars={riding} "
        f"unjudged={unjudged} judge={args.judge}"
    )
    rows_out = [
        evals.Row(
            today,
            "recast",
            "chat",
            CHAT_MODEL,
            "judge_ok_share",
            round(ok_share, 4),
            len(chosen),
            corpus="tatoeba",
            note=note,
        ),
        evals.Row(
            today,
            "recast",
            "chat",
            CHAT_MODEL,
            "lemma_overlap",
            round(overlap, 4),
            len(chosen),
            corpus="tatoeba",
            note=note,
        ),
        evals.Row(
            today,
            "recast",
            "chat",
            CHAT_MODEL,
            "unpaired",
            float(unpaired),
            len(chosen),
            corpus="tatoeba",
            note=note,
        ),
    ]
    evals.append(rows_out, args.ledger)
    print(f"\nappended {len(rows_out)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
