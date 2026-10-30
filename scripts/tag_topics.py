"""Tag Hebrew lemmas with topics, on two models through the Batches API (targum-internal#605).

The plan is `~/targum-team/ling-he/keep/topic-tagging-2026-10-30.md`; David approved the
list, the spend and the gate on 2026-10-30. A $2-capped pilot of 500 lemmas comes first,
and the full run (cap $30, targum-internal#606) waits until ling-he's blind gold set
passes: precision of 90% or more and recall of 80% or more on every topic.

**What is sent.** For each lemma: the lemma, its pointed citation form where the gloss
has one, its part of speech and its cached English gloss. Never a sentence. The lemmas
come only from the language tables (`targum.topics.universe`, over `Store.top`), which
only public texts reach; never from `word` rows or the gloss cache, which hold private
imports. A lemma the gloss cache has no gloss for is left out and listed, and so is every
lemma `targum.topics.screen` passes over (a function word, a number, a name, a
lemmatisation error), with its reason, in `lemmas.json`. `--from-run` asks again about
another run's lemmas, screened afresh, so a second pilot compares like with like.

**What it costs.** `--dry-run` quotes and spends nothing. `--cap` is hard: before a batch
is sent, what has been spent plus the most every request in it could cost (every input
token written to the cache, every output token up to `max_tokens`) must fit, or nothing
is sent. Prices are `targum.topics.PRICES`.

**Checkpoints.** Everything lands in `~/.targum/research/topics/<run>/`, written whole or
not at all: `lemmas.json` before anything is spent, a batch's id the moment it is created
(so a crash resumes it rather than paying for it twice), and every raw answer with its
usage as soon as a batch ends. Run it again to resume. Then `review.tsv`, `summary.json`
and the agreed tags as a lexicon at `~/.targum/topics-<run>.json`.

**The blind set.** `--blind N --blind-out FILE` writes N of the run's lemmas, stratified
by frequency, with no model tags, for ling-he to label; the models' tags for the same
rows go to `blind-tags.csv` in the run directory, which ling-he does not open.

    op run --env-file op.env -- .venv/bin/python scripts/tag_topics.py \\
        --run pilot-2026-10-30 --lemmas 500 --cap 2 --dry-run
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import random
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from targum import topics
from targum.paths import write_atomic

#: Lemmas per request. Big enough that the cached system prompt is a small share of each
#: request, small enough that one bad answer re-sends little.
PER_REQUEST = 100
#: Output tokens a request may spend: the JSON (about 20 a lemma) and the thinking.
MAX_TOKENS = 8000
EFFORT = "low"

#: For a quote before anything is measured, per the plan: about 30 input tokens a lemma
#: and 20 output, and up to 2,000 of thinking a request at `low`. `--thinking` replaces
#: the last with what a pilot measured.
IN_PER_LEMMA = 30
OUT_PER_LEMMA = 20
THINKING_PER_REQUEST = 2000
POLL_SECONDS = 30


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--run", required=True, help="A name for the run's directory.")
    parser.add_argument("--lemmas", type=int, default=500, help="Modern lemmas to tag.")
    parser.add_argument("--bible", type=int, default=0, help="Bible lemmas to add.")
    parser.add_argument(
        "--registers",
        default=",".join(topics.MODERN),
        help="The registers the modern lemmas are drawn from, all public by construction.",
    )
    parser.add_argument("--models", default=",".join(topics.MODELS))
    parser.add_argument("--per-request", type=int, default=PER_REQUEST)
    parser.add_argument("--cap", type=float, required=True, help="Dollars, never passed.")
    parser.add_argument("--dry-run", action="store_true", help="Quote, and spend nothing.")
    parser.add_argument("--retries", type=int, default=1, help="Re-sends of failed rows.")
    parser.add_argument("--thinking", type=int, default=THINKING_PER_REQUEST)
    parser.add_argument("--requote", type=int, default=12000, help="Lemmas to re-quote for.")
    parser.add_argument("--blind", type=int, default=0, help="Rows for the blind gold set.")
    parser.add_argument("--blind-out", type=Path)
    parser.add_argument(
        "--from-run", help="Reuse another run's lemma list (screened again) instead of drawing."
    )
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    for model in models:
        if model not in topics.PRICES:
            print(f"No price for {model}; known: {', '.join(topics.PRICES)}", file=sys.stderr)
            return 2
    run = topics.RESEARCH / args.run
    run.mkdir(parents=True, exist_ok=True)

    registers = [r.strip() for r in args.registers.split(",") if r.strip()]
    lemmas = _lemmas(run, args.lemmas, args.bible, registers, args.from_run)
    if not lemmas:
        print("No lemmas: the language tables are empty. Run `targum tables sweep`.")
        return 1
    chunks = [
        list(range(start, min(start + args.per_request, len(lemmas))))
        for start in range(0, len(lemmas), args.per_request)
    ]
    state = _load(run)
    client = _client()
    system = topics.system_prompt()
    system_tokens = _count(client, models[0], system) if client else len(system) // 3

    _quote(models, lemmas, chunks, system_tokens, args.thinking, state)
    if args.dry_run:
        print("Dry run: nothing sent.")
        return 0
    if client is None:
        print("No Anthropic key in the environment: run under `op run --env-file op.env`.")
        return 1

    for attempt in range(args.retries + 1):
        # Every model's batch goes out before any is waited on, so they run together.
        for model in models:
            pending = [i for i, chunk in enumerate(chunks) if not _done(state, model, chunk)]
            if pending and not _submit(
                client, run, state, model, lemmas, chunks, pending, system, system_tokens, args.cap
            ):
                return 3
        for model in models:
            _collect(client, run, state, model, chunks)
        if all(_done(state, m, c) for m in models for c in chunks):
            break
        print(f"Some rows failed; re-sending ({attempt + 1} of {args.retries}).")

    _measure_thinking(client, run, state, models)
    summary = _summarise(run, state, models, lemmas, chunks, system_tokens, args.requote)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.blind:
        if args.blind_out is None:
            print("--blind needs --blind-out.", file=sys.stderr)
            return 2
        tags = {model: _tags(state, model, chunks) for model in models}
        _blind(run, tags, lemmas, args.blind, args.blind_out)
    return 0


# --- State ------------------------------------------------------------------------------


def _lemmas(
    run: Path, modern: int, bible: int, registers: list[str], from_run: str | None = None
) -> list[topics.Lemma]:
    """The run's lemma list: read back where it was written, so a resumed run asks about
    exactly the rows it paid for; otherwise another run's, or drawn from the tables, and
    screened either way."""
    file = run / "lemmas.json"
    if file.is_file():
        held = json.loads(file.read_text(encoding="utf-8"))
        return [topics.Lemma(**row) for row in held["lemmas"]]
    from targum.tables import Store

    store = Store.from_env()
    if store is None:
        print("TARGUM_LEDGER is not set: the lemma list comes only from the tables.")
        return []
    if from_run:
        source = json.loads(
            (topics.RESEARCH / from_run / "lemmas.json").read_text(encoding="utf-8")
        )
        drawn = [topics.Lemma(**row) for row in source["lemmas"]]
        registers, missing = source.get("registers", registers), source.get("no_gloss", [])
    else:
        drawn, missing = topics.universe(store, modern=modern, bible=bible, registers=registers)
    lemmas, dropped = topics.screen(store, drawn)
    body = {
        "registers": registers,
        "prompt": topics.PROMPT_VERSION,
        "from_run": from_run,
        "lemmas": [asdict(one) for one in lemmas],
        "dropped": dropped,
        "no_gloss": missing,
    }
    write_atomic(file, json.dumps(body, ensure_ascii=False, indent=1))
    reasons = Counter(one["why"] for one in dropped)
    print(
        f"{len(lemmas)} lemmas to tag; {len(dropped)} screened out ({dict(reasons)});"
        f" {len(missing)} left out for want of a gloss."
    )
    return lemmas


def _load(run: Path) -> dict[str, Any]:
    file = run / "state.json"
    if file.is_file():
        held: dict[str, Any] = json.loads(file.read_text(encoding="utf-8"))
        return held
    return {"batches": [], "answers": {}}


def _save(run: Path, state: dict[str, Any]) -> None:
    write_atomic(run / "state.json", json.dumps(state, ensure_ascii=False, indent=1))


def _custom_id(model: str, chunk: int) -> str:
    return f"{model.removeprefix('claude-')}-{chunk:04d}"


def _done(state: dict[str, Any], model: str, chunk: list[int]) -> bool:
    answer = state["answers"].get(model, {}).get(str(chunk[0]))
    if not answer or answer.get("type") != "succeeded":
        return False
    tags = topics.parse(answer.get("text", ""), chunk)
    return len(tags) == len(chunk)


def _spent(state: dict[str, Any]) -> float:
    total = 0.0
    for model, answers in state["answers"].items():
        for answer in answers.values():
            total += topics.cost(model, _usage(answer), batch=True)
    return total


def _usage(answer: dict[str, Any]) -> topics.Usage:
    usage = answer.get("usage") or {}
    return topics.Usage(
        input_tokens=int(usage.get("input_tokens") or 0),
        cache_write_tokens=int(usage.get("cache_creation_input_tokens") or 0),
        cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        thinking_tokens=int(answer.get("thinking_tokens") or 0),
        requests=1,
    )


# --- The API ----------------------------------------------------------------------------


def _client() -> Any:
    import os

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return None
    import anthropic

    return anthropic.Anthropic()


def _count(client: Any, model: str, text: str) -> int:
    """Tokens in `text` as a user turn, less a one-character turn's: free to ask."""

    def ask(content: str) -> int:
        result = client.messages.count_tokens(
            model=model, messages=[{"role": "user", "content": content}]
        )
        return int(result.input_tokens)

    return max(0, ask(text) - ask("x"))


def _params(model: str, system: str, lemmas: list[topics.Lemma], chunk: list[int]) -> Any:
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming

    return MessageCreateParamsNonStreaming(
        model=model,
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
            "format": {"type": "json_schema", "schema": topics.schema()},
        },
    )


def _submit(
    client: Any,
    run: Path,
    state: dict[str, Any],
    model: str,
    lemmas: list[topics.Lemma],
    chunks: list[list[int]],
    pending: list[int],
    system: str,
    system_tokens: int,
    cap: float,
) -> bool:
    """One batch for one model, unless one is open already: checked against the cap with
    what is spent and what every open batch could still cost, then created, and its id
    written before anything else."""
    from anthropic.types.messages.batch_create_params import Request

    open_batch = next(
        (b for b in state["batches"] if b["model"] == model and b["status"] != "ended"), None
    )
    if open_batch is None:
        requests = [
            Request(
                custom_id=_custom_id(model, i), params=_params(model, system, lemmas, chunks[i])
            )
            for i in pending
        ]
        worst = 0.0
        for i in pending:
            # The counted system prompt, and the rows at a token a character, which
            # no Hebrew line reaches: a ceiling, not an estimate.
            rows = topics.user_message([lemmas[j] for j in chunks[i]], chunks[i][0])
            input_tokens = system_tokens + len(rows)
            worst += topics.worst_case(model, input_tokens, MAX_TOKENS, batch=True)
        spent = _spent(state)
        owed = sum(b["worst"] for b in state["batches"] if b["status"] != "ended")
        if spent + owed + worst > cap:
            print(
                f"Refused: {model} could cost up to ${worst:.2f} on top of ${spent:.2f}"
                f" spent and ${owed:.2f} still open, past the ${cap:.2f} cap. Nothing sent."
            )
            return False
        batch = client.messages.batches.create(requests=requests)
        open_batch = {
            "id": batch.id,
            "model": model,
            "chunks": pending,
            "status": batch.processing_status,
            "worst": round(worst, 4),
        }
        state["batches"].append(open_batch)
        _save(run, state)
        print(f"{model}: batch {batch.id}, {len(requests)} requests, at most ${worst:.2f}.")
    return True


def _collect(
    client: Any, run: Path, state: dict[str, Any], model: str, chunks: list[list[int]]
) -> None:
    """Wait for one model's open batch to end and write every answer it gave."""
    open_batch = next(
        (b for b in state["batches"] if b["model"] == model and b["status"] != "ended"), None
    )
    if open_batch is None:
        return
    while True:
        batch = client.messages.batches.retrieve(open_batch["id"])
        if batch.processing_status == "ended":
            break
        counts = batch.request_counts
        print(f"{model}: {counts.processing} processing, {counts.succeeded} done")
        time.sleep(POLL_SECONDS)

    by_id = {_custom_id(model, i): i for i in open_batch["chunks"]}
    answers = state["answers"].setdefault(model, {})
    for result in client.messages.batches.results(open_batch["id"]):
        index = by_id.get(result.custom_id)
        if index is None:
            continue
        key = str(chunks[index][0])
        if result.result.type == "succeeded":
            message = result.result.message
            text = "".join(b.text for b in message.content if b.type == "text")
            answers[key] = {
                "type": "succeeded",
                "text": text,
                "stop_reason": message.stop_reason,
                "usage": message.usage.model_dump(),
            }
        elif answers.get(key, {}).get("type") != "succeeded":
            answers[key] = {"type": result.result.type, "usage": {}}
    open_batch["status"] = "ended"
    _save(run, state)


def _measure_thinking(client: Any, run: Path, state: dict[str, Any], models: list[str]) -> None:
    """How much of each answer's output was thinking: output tokens less the answer's own
    text, counted (free). Written back so a summary never asks twice."""
    changed = False
    for model in models:
        for answer in state["answers"].get(model, {}).values():
            if answer.get("type") != "succeeded" or "thinking_tokens" in answer:
                continue
            visible = _count(client, model, answer.get("text", "")) if answer.get("text") else 0
            output = int((answer.get("usage") or {}).get("output_tokens") or 0)
            answer["visible_tokens"] = visible
            answer["thinking_tokens"] = max(0, output - visible)
            changed = True
    if changed:
        _save(run, state)


# --- Quotes and results -----------------------------------------------------------------


def _expected(model: str, lemmas: int, requests: int, system_tokens: int, thinking: int) -> float:
    """What a run should cost through the Batches API: the system prompt written to the
    cache once and read on every other request, the rows, the JSON and the thinking."""
    usage = topics.Usage(
        input_tokens=lemmas * IN_PER_LEMMA,
        cache_write_tokens=system_tokens,
        cache_read_tokens=system_tokens * max(0, requests - 1),
        output_tokens=lemmas * OUT_PER_LEMMA + requests * thinking,
    )
    return topics.cost(model, usage, batch=True)


def _quote(
    models: list[str],
    lemmas: list[topics.Lemma],
    chunks: list[list[int]],
    system_tokens: int,
    thinking: int,
    state: dict[str, Any],
) -> None:
    print(
        f"{len(lemmas)} lemmas in {len(chunks)} requests a model;"
        f" system prompt {system_tokens} tokens."
    )
    total = 0.0
    for model in models:
        expected = _expected(model, len(lemmas), len(chunks), system_tokens, thinking)
        total += expected
        print(f"  {model}: about ${expected:.2f} (Batches API)")
    print(f"  both: about ${total:.2f}; spent so far ${_spent(state):.4f}")


def _tags(state: dict[str, Any], model: str, chunks: list[list[int]]) -> dict[int, topics.Tag]:
    out: dict[int, topics.Tag] = {}
    for chunk in chunks:
        answer = state["answers"].get(model, {}).get(str(chunk[0]))
        if answer and answer.get("type") == "succeeded":
            out.update(topics.parse(answer.get("text", ""), chunk))
    return out


def _kappa(first: dict[int, topics.Tag], second: dict[int, topics.Tag], code: str) -> float | None:
    """Cohen's kappa on whether each row carries `code`, over rows both answered."""
    rows = [i for i in first if i in second]
    if not rows:
        return None
    a = [code in first[i].topics for i in rows]
    b = [code in second[i].topics for i in rows]
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / len(rows)
    pa, pb = sum(a) / len(rows), sum(b) / len(rows)
    chance = pa * pb + (1 - pa) * (1 - pb)
    if chance >= 1:
        return None
    return (observed - chance) / (1 - chance)


def _summarise(
    run: Path,
    state: dict[str, Any],
    models: list[str],
    lemmas: list[topics.Lemma],
    chunks: list[list[int]],
    system_tokens: int,
    requote: int,
) -> dict[str, Any]:
    per_model: dict[str, Any] = {}
    thinking_mean: dict[str, float] = {}
    tags = {model: _tags(state, model, chunks) for model in models}
    for model in models:
        usage = topics.Usage()
        for answer in state["answers"].get(model, {}).values():
            if answer.get("type") == "succeeded":
                usage.add(_usage(answer))
        thinking_mean[model] = usage.thinking_tokens / usage.requests if usage.requests else 0.0
        per_model[model] = {
            **asdict(usage),
            "cost_usd": round(topics.cost(model, usage, batch=True), 4),
            "tagged": len(tags[model]),
            "general_share": round(
                sum(t.topics == (topics.GENERAL,) for t in tags[model].values())
                / max(1, len(tags[model])),
                3,
            ),
        }

    agreement: dict[str, Any] = {}
    lexicon: dict[str, list[str]] = {}
    review = io.StringIO()
    writer = csv.writer(review, delimiter="\t", lineterminator="\n")
    writer.writerow(
        ["id", "lemma", "glossed_as", "pos", "gloss", "count", "register"]
        + [f"{m.removeprefix('claude-')}{s}" for m in models for s in ("", "_confidence")]
        + ["agreed", "decision", "who", "at", "why"]
    )
    if len(models) == 2:
        first, second = tags[models[0]], tags[models[1]]
        both = [i for i in first if i in second]
        exact = sum(set(first[i].topics) == set(second[i].topics) for i in both)
        shared = sum(topics.agreed(first[i], second[i]) is not None for i in both)
        agreement = {
            "rows_both_answered": len(both),
            "exact": exact,
            "exact_rate": round(exact / max(1, len(both)), 3),
            "share_a_topic": shared,
            "share_a_topic_rate": round(shared / max(1, len(both)), 3),
            "kappa": {
                code: (None if k is None else round(k, 3))
                for code in [*topics.TOPICS, topics.GENERAL]
                for k in [_kappa(first, second, code)]
            },
        }
    for i, one in enumerate(lemmas):
        cells = []
        for model in models:
            tag = tags[model].get(i)
            cells += [",".join(tag.topics) if tag else "", tag.confidence if tag else ""]
        settled = None
        if len(models) == 2:
            settled = topics.agreed(tags[models[0]].get(i), tags[models[1]].get(i))
        if settled:
            lexicon[one.lemma] = list(settled)
        writer.writerow(
            [i, one.lemma, one.glossed_as, one.pos, one.gloss, one.count, one.register]
            + cells
            + [",".join(settled) if settled else "", "", "", "", ""]
        )
    write_atomic(run / "review.tsv", review.getvalue())

    lexicon_file = topics.LEXICON.with_name(f"topics-{run.name}.json")
    write_atomic(
        lexicon_file,
        json.dumps(
            {
                "version": f"{topics.VERSION}+{topics.PROMPT_VERSION}-{run.name}",
                "topics": list(topics.TOPICS),
                "lemmas": lexicon,
            },
            ensure_ascii=False,
            indent=1,
        ),
    )

    per_lemma = len(lemmas) / max(1, len(chunks))
    requests = math.ceil(requote / per_lemma) if per_lemma else 0
    measured_in = {
        model: (
            per_model[model]["input_tokens"] / max(1, len(tags[model]))
            if per_model[model]["tagged"]
            else IN_PER_LEMMA
        )
        for model in models
    }
    requoted = {}
    for model in models:
        visible = sum(
            int(a.get("visible_tokens") or 0)
            for a in state["answers"].get(model, {}).values()
            if a.get("type") == "succeeded"
        )
        out_per_lemma = visible / max(1, len(tags[model])) if visible else OUT_PER_LEMMA
        usage = topics.Usage(
            input_tokens=int(requote * measured_in[model]),
            cache_write_tokens=system_tokens,
            cache_read_tokens=system_tokens * max(0, requests - 1),
            output_tokens=int(requote * out_per_lemma + requests * thinking_mean[model]),
        )
        requoted[model] = round(topics.cost(model, usage, batch=True), 2)
    summary = {
        "run": run.name,
        "version": topics.VERSION,
        "prompt": topics.PROMPT_VERSION,
        "lemmas": len(lemmas),
        "requests_per_model": len(chunks),
        "system_prompt_tokens": system_tokens,
        "models": per_model,
        "total_cost_usd": round(sum(m["cost_usd"] for m in per_model.values()), 4),
        "agreement": agreement,
        "lexicon": str(lexicon_file),
        "lexicon_lemmas": len(lexicon),
        "requote": {
            "lemmas": requote,
            "requests": requests,
            "usd": requoted,
            "both_usd": round(sum(requoted.values()), 2),
        },
    }
    write_atomic(run / "summary.json", json.dumps(summary, ensure_ascii=False, indent=1))
    return summary


def _blind(
    run: Path,
    tags: dict[str, dict[int, topics.Tag]],
    lemmas: list[topics.Lemma],
    size: int,
    out: Path,
) -> None:
    """`size` rows, stratified over four frequency bands of the run, in a fixed shuffled
    order, with nothing a model said; the models' tags go to the run directory apart."""
    bands = 4
    edges = [round(len(lemmas) * b / bands) for b in range(bands + 1)]
    picker = random.Random(f"topics-blind-{run.name}")
    chosen: list[int] = []
    for b in range(bands):
        pool = list(range(edges[b], edges[b + 1]))
        want = size // bands + (1 if b < size % bands else 0)
        chosen += picker.sample(pool, min(want, len(pool)))
    picker.shuffle(chosen)

    blind = io.StringIO()
    writer = csv.writer(blind, lineterminator="\n")
    writer.writerow(["row", "lemma", "pointed", "pos", "gloss", "topic_1", "topic_2", "notes"])
    for row, i in enumerate(chosen, start=1):
        one = lemmas[i]
        writer.writerow([row, one.lemma, one.pointed, one.pos, one.gloss, "", "", ""])
    out.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(out, blind.getvalue())

    hidden = io.StringIO()
    writer = csv.writer(hidden, lineterminator="\n")
    models = list(tags)
    writer.writerow(["row", "id", "lemma"] + [m.removeprefix("claude-") for m in models])
    for row, i in enumerate(chosen, start=1):
        writer.writerow(
            [row, i, lemmas[i].lemma]
            + [",".join(tags[m][i].topics) if i in tags[m] else "" for m in models]
        )
    write_atomic(run / "blind-tags.csv", hidden.getvalue())
    bands_count = Counter(min(bands - 1, i * bands // len(lemmas)) for i in chosen)
    print(f"Blind set: {len(chosen)} rows to {out}; bands {dict(sorted(bands_count.items()))}.")
    print(f"Model tags for those rows, kept apart: {run / 'blind-tags.csv'}")


if __name__ == "__main__":
    raise SystemExit(main())
