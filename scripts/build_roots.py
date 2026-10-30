"""Build a root lexicon, Hebrew or Russian, on two models through the Batches API
(targum-internal#592, #596).

David approved the spend on 2026-10-30: a pilot of about $1 a language first, and a full
run of at most $30 a language only once a blind gold set passes. The open half (prompts,
answer shapes, checks, scores) is `targum.root_lexicon`.

**What is sent.** For each lemma: the lemma, its pointed form (Hebrew, where the gloss
cache has one) or stressed form (Russian, from OpenRussian), its part of speech and its
cached English gloss. Never a sentence. The lemmas come only from the language tables
(`Store.top`), which only public texts reach; never from `word` rows or the gloss cache,
which hold private imports. Hebrew reads the corpus ledger (`TARGUM_LEDGER`); Russian is
not folded there, so `--sweep LIBRARY` folds the library's public Russian texts into a
store of its own first (`root_lexicon.russian_store`), behind the same guard.

**What it costs.** `--dry-run` quotes and spends nothing. `--cap` is hard: before a batch
is sent, what has been spent plus the most every request in it could cost must fit, or
nothing is sent. Prices are `targum.topics.PRICES`.

**Checkpoints.** Everything lands in `~/.targum/research/roots/<run>/`, written whole or
not at all: `lemmas.json` before anything is spent, a batch's id the moment it is created
(so a crash resumes it rather than paying twice), and every raw answer with its usage as
soon as a batch ends. Run it again to resume. Then `review.tsv`, `summary.json` (with the
checks and the two models' agreement) and the agreed rows as a lexicon at
`~/.targum/roots-<language>-<run>.json`.

**The blind set.** `--blind N --blind-out FILE` writes N of the run's lemmas, stratified
by frequency, with no model answers, for the language's reviewer; the models' answers for
the same rows go to `blind-answers.csv` in the run directory. `--score FILE` scores the
run against the reviewer's filled-in copy and spends nothing.

    op run --env-file op.env -- .venv/bin/python scripts/build_roots.py \\
        --language he --run pilot-he-2026-10-31 --lemmas 450 --bible 50 --cap 1.5 --dry-run
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import random
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

from targum import root_lexicon as rl
from targum import topics
from targum.paths import write_atomic
from targum.topics import Lemma

EFFORT = "low"
#: Up to this many thinking tokens a request at `low`, for a quote before a pilot has
#: measured it; `--thinking` replaces it.
THINKING_PER_REQUEST = 2000
POLL_SECONDS = 30


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--language", choices=rl.LANGUAGES, required=True)
    parser.add_argument("--run", required=True, help="A name for the run's directory.")
    parser.add_argument("--lemmas", type=int, default=500, help="Modern lemmas to analyse.")
    parser.add_argument("--bible", type=int, default=0, help="Bible lemmas to add (Hebrew).")
    parser.add_argument("--registers", help="Registers to draw from, comma-separated.")
    parser.add_argument("--models", default=",".join(topics.MODELS))
    parser.add_argument("--per-request", type=int)
    parser.add_argument("--cap", type=float, help="Dollars, never passed. Needed to spend.")
    parser.add_argument("--dry-run", action="store_true", help="Quote, and spend nothing.")
    parser.add_argument("--retries", type=int, default=1, help="Re-sends of failed rows.")
    parser.add_argument("--thinking", type=int, default=THINKING_PER_REQUEST)
    parser.add_argument("--requote", type=int, default=20000, help="Lemmas to re-quote for.")
    parser.add_argument("--sweep", type=Path, help="Russian: fold this library's public texts.")
    parser.add_argument("--tables", type=Path, help="A store file to draw from instead.")
    parser.add_argument("--blind", type=int, default=0, help="Rows for the blind gold set.")
    parser.add_argument("--blind-out", type=Path)
    parser.add_argument("--score", type=Path, help="A filled-in blind set to score against.")
    args = parser.parse_args()

    language = args.language
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    for model in models:
        if model not in topics.PRICES:
            print(f"No price for {model}; known: {', '.join(topics.PRICES)}", file=sys.stderr)
            return 2
    run = rl.RESEARCH / args.run
    run.mkdir(parents=True, exist_ok=True)
    per_request = args.per_request or rl.PER_REQUEST[language]

    registers = [r.strip() for r in (args.registers or "").split(",") if r.strip()]
    lemmas = _lemmas(run, language, args, registers)
    if not lemmas:
        print("No lemmas: the tables hold none for these registers.")
        return 1
    chunks = [
        list(range(start, min(start + per_request, len(lemmas))))
        for start in range(0, len(lemmas), per_request)
    ]
    state = _load(run)

    if args.score:
        return _score(run, state, language, models, chunks, args.score)

    client = _client()
    system = rl.system_prompt(language)
    system_tokens = _count(client, models[0], system) if client else len(system) // 3
    _quote(language, models, lemmas, chunks, system_tokens, args.thinking, state)
    if args.dry_run:
        print("Dry run: nothing sent.")
        return 0
    if args.cap is None:
        print("--cap is needed to spend.", file=sys.stderr)
        return 2
    if client is None:
        print("No Anthropic key in the environment: run under `op run --env-file op.env`.")
        return 1

    for attempt in range(args.retries + 1):
        for model in models:
            pending = [
                i for i, chunk in enumerate(chunks) if not _done(state, language, model, chunk)
            ]
            if pending and not _submit(
                client,
                run,
                state,
                language,
                model,
                lemmas,
                chunks,
                pending,
                system,
                system_tokens,
                args.cap,
            ):
                return 3
        for model in models:
            _collect(client, run, state, model, chunks)
        if all(_done(state, language, m, c) for m in models for c in chunks):
            break
        if attempt < args.retries:
            print(f"Some rows failed; re-sending ({attempt + 1} of {args.retries}).")

    _measure_thinking(client, run, state, models)
    summary = _summarise(run, state, language, models, lemmas, chunks, system_tokens, args.requote)
    print(json.dumps(_brief(summary), indent=2, ensure_ascii=False))
    if args.blind:
        if args.blind_out is None:
            print("--blind needs --blind-out.", file=sys.stderr)
            return 2
        answers = {model: _answers(state, language, model, chunks) for model in models}
        _blind(run, language, answers, lemmas, args.blind, args.blind_out)
    return 0


# --- State ------------------------------------------------------------------------------


def _lemmas(
    run: Path, language: str, args: argparse.Namespace, registers: list[str]
) -> list[Lemma]:
    """The run's lemma list: read back where it was written, so a resumed run asks about
    exactly the rows it paid for; otherwise drawn from the tables and screened."""
    file = run / "lemmas.json"
    if file.is_file():
        held = json.loads(file.read_text(encoding="utf-8"))
        if held.get("language") != language:
            raise SystemExit(f"{run} is a {held.get('language')} run.")
        return [Lemma(**row) for row in held["lemmas"]]
    from targum.tables import Store

    store: Store | None
    if args.tables:
        store = Store(args.tables)
    elif language == "ru":
        if args.sweep:
            store, result = rl.russian_store(args.sweep)
            print(f"Folded the public Russian texts: {result}")
        else:
            store = Store(rl.RUSSIAN_TABLES)
    else:
        store = Store.from_env()
    if store is None or not store.file.is_file():
        print("No tables: set TARGUM_LEDGER (Hebrew) or pass --sweep LIBRARY (Russian).")
        return []
    chosen = registers or list(rl.REGISTERS[language])
    lemmas, dropped, missing = rl.universe(
        store, language, modern=args.lemmas, bible=args.bible, registers=chosen
    )
    body = {
        "language": language,
        "version": rl.VERSION[language],
        "prompt": rl.PROMPT_VERSION,
        "registers": chosen,
        "tables": str(store.file),
        "lemmas": [asdict(one) for one in lemmas],
        "dropped": dropped,
        "no_gloss": missing,
    }
    write_atomic(file, json.dumps(body, ensure_ascii=False, indent=1))
    reasons = Counter(one["why"] for one in dropped)
    shown = sum(1 for one in lemmas if one.pointed)
    print(
        f"{len(lemmas)} lemmas ({shown} with a {'pointed' if language == 'he' else 'stressed'}"
        f" form); {len(dropped)} screened out ({dict(reasons)}); {len(missing)} left out for"
        " want of a gloss."
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


def _done(state: dict[str, Any], language: str, model: str, chunk: list[int]) -> bool:
    answer = state["answers"].get(model, {}).get(str(chunk[0]))
    if not answer or answer.get("type") != "succeeded":
        return False
    return len(rl.parse(language, answer.get("text", ""), chunk)) == len(chunk)


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


def _spent(state: dict[str, Any]) -> float:
    """Every answer paid for, the failed ones included: a re-send pays again."""
    total = 0.0
    for model, answers in state["answers"].items():
        for answer in answers.values():
            total += topics.cost(model, _usage(answer), batch=True)
        for answer in state.get("replaced", {}).get(model, []):
            total += topics.cost(model, _usage(answer), batch=True)
    return total


# --- The API ----------------------------------------------------------------------------


def _client() -> Any:
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


def _params(language: str, model: str, system: str, lemmas: list[Lemma], chunk: list[int]) -> Any:
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming

    return MessageCreateParamsNonStreaming(
        model=model,
        max_tokens=rl.MAX_TOKENS[language],
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[
            {
                "role": "user",
                "content": rl.user_message(language, [lemmas[i] for i in chunk], chunk[0]),
            }
        ],
        output_config={
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": rl.schema(language)},
        },
    )


def _submit(
    client: Any,
    run: Path,
    state: dict[str, Any],
    language: str,
    model: str,
    lemmas: list[Lemma],
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
    if open_batch is not None:
        return True
    worst = 0.0
    for i in pending:
        # The counted system prompt, and the rows at a token a character, which no line
        # reaches: a ceiling, not an estimate.
        rows = rl.user_message(language, [lemmas[j] for j in chunks[i]], chunks[i][0])
        worst += topics.worst_case(
            model, system_tokens + len(rows), rl.MAX_TOKENS[language], batch=True
        )
    spent = _spent(state)
    owed = sum(b["worst"] for b in state["batches"] if b["status"] != "ended")
    if spent + owed + worst > cap:
        print(
            f"Refused: {model} could cost up to ${worst:.2f} on top of ${spent:.2f}"
            f" spent and ${owed:.2f} still open, past the ${cap:.2f} cap. Nothing sent."
        )
        return False
    requests = [
        Request(
            custom_id=_custom_id(model, i),
            params=_params(language, model, system, lemmas, chunks[i]),
        )
        for i in pending
    ]
    batch = client.messages.batches.create(requests=requests)
    state["batches"].append(
        {
            "id": batch.id,
            "model": model,
            "chunks": pending,
            "status": batch.processing_status,
            "worst": round(worst, 4),
        }
    )
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
        if key in answers and answers[key].get("usage"):
            # A re-send replaces an answer that was paid for: keep its cost counted.
            state.setdefault("replaced", {}).setdefault(model, []).append(
                {"usage": answers[key]["usage"]}
            )
        if result.result.type == "succeeded":
            message = result.result.message
            text = "".join(b.text for b in message.content if b.type == "text")
            answers[key] = {
                "type": "succeeded",
                "text": text,
                "stop_reason": message.stop_reason,
                "usage": message.usage.model_dump(),
            }
        else:
            error = getattr(result.result, "error", None)
            answers[key] = {"type": result.result.type, "usage": {}, "error": str(error or "")}
    open_batch["status"] = "ended"
    _save(run, state)


def _measure_thinking(client: Any, run: Path, state: dict[str, Any], models: list[str]) -> None:
    """How much of each answer's output was thinking: output tokens less the answer's own
    text, counted (free). Written back so a summary never asks twice."""
    if client is None:
        return
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


def _expected(
    language: str, model: str, lemmas: int, requests: int, system_tokens: int, thinking: int
) -> float:
    usage = topics.Usage(
        input_tokens=lemmas * rl.IN_PER_LEMMA[language],
        cache_write_tokens=system_tokens,
        cache_read_tokens=system_tokens * max(0, requests - 1),
        output_tokens=lemmas * rl.OUT_PER_LEMMA[language] + requests * thinking,
    )
    return topics.cost(model, usage, batch=True)


def _quote(
    language: str,
    models: list[str],
    lemmas: list[Lemma],
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
        expected = _expected(language, model, len(lemmas), len(chunks), system_tokens, thinking)
        total += expected
        print(f"  {model}: about ${expected:.2f} (Batches API)")
    print(f"  both: about ${total:.2f}; spent so far ${_spent(state):.4f}")


def _answers(
    state: dict[str, Any], language: str, model: str, chunks: list[list[int]]
) -> dict[int, rl.Answer]:
    out: dict[int, rl.Answer] = {}
    for chunk in chunks:
        answer = state["answers"].get(model, {}).get(str(chunk[0]))
        if answer and answer.get("type") == "succeeded":
            out.update(rl.parse(language, answer.get("text", ""), chunk))
    return out


def _checks(language: str, lemmas: list[Lemma], answers: dict[int, rl.Answer]) -> dict[str, Any]:
    if language == "he":
        return rl.check_he(
            lemmas, {i: a for i, a in answers.items() if isinstance(a, rl.HebrewRoot)}
        )
    return rl.check_ru(lemmas, {i: a for i, a in answers.items() if isinstance(a, rl.RussianRoot)})


def _summarise(
    run: Path,
    state: dict[str, Any],
    language: str,
    models: list[str],
    lemmas: list[Lemma],
    chunks: list[list[int]],
    system_tokens: int,
    requote: int,
) -> dict[str, Any]:
    answers = {model: _answers(state, language, model, chunks) for model in models}
    per_model: dict[str, Any] = {}
    thinking_mean: dict[str, float] = {}
    for model in models:
        usage = topics.Usage()
        for answer in state["answers"].get(model, {}).values():
            usage.add(_usage(answer))
        for answer in state.get("replaced", {}).get(model, []):
            usage.add(_usage(answer))
        thinking_mean[model] = usage.thinking_tokens / usage.requests if usage.requests else 0.0
        per_model[model] = {
            **asdict(usage),
            "cost_usd": round(topics.cost(model, usage, batch=True), 4),
            "checks": _checks(language, lemmas, answers[model]),
        }

    agreement: dict[str, Any] = {}
    lexicon: dict[str, Any] = {}
    review = io.StringIO()
    writer = csv.writer(review, delimiter="\t", lineterminator="\n")
    fields = list(rl.cells(_example(language)).keys())
    writer.writerow(
        ["id", "lemma", "shown", "pos", "gloss", "count", "register"]
        + [f"{m.removeprefix('claude-')}_{f}" for m in models for f in fields]
        + ["agreed", "decision", "who", "at", "why"]
    )
    if len(models) == 2:
        agreement = rl.agreement(language, answers[models[0]], answers[models[1]])
    for i, one in enumerate(lemmas):
        row = [i, one.lemma, one.pointed, one.pos, one.gloss, one.count, one.register]
        for model in models:
            got = rl.cells(answers[model].get(i))
            row += [got.get(f, "") for f in fields]
        settled = (
            rl.agreed(answers[models[0]].get(i), answers[models[1]].get(i))
            if len(models) == 2
            else None
        )
        if settled is not None:
            lexicon[one.lemma] = settled
        writer.writerow(row + ["yes" if settled is not None else "", "", "", "", ""])
    write_atomic(run / "review.tsv", review.getvalue())

    lexicon_file = rl.lexicon_file(language, run.name)
    write_atomic(
        lexicon_file,
        json.dumps(
            {
                "version": f"{rl.VERSION[language]}+{rl.PROMPT_VERSION}-{run.name}",
                "language": language,
                "lemmas": lexicon,
            },
            ensure_ascii=False,
            indent=1,
        ),
    )

    per_lemma = len(lemmas) / max(1, len(chunks))
    requests = math.ceil(requote / per_lemma) if per_lemma else 0
    requoted: dict[str, float] = {}
    for model in models:
        answered = max(1, len(answers[model]))
        measured_in = per_model[model]["input_tokens"] / answered
        visible = sum(
            int(a.get("visible_tokens") or 0)
            for a in state["answers"].get(model, {}).values()
            if a.get("type") == "succeeded"
        )
        out_per_lemma = visible / answered if visible else rl.OUT_PER_LEMMA[language]
        usage = topics.Usage(
            input_tokens=int(requote * measured_in),
            cache_write_tokens=system_tokens,
            cache_read_tokens=system_tokens * max(0, requests - 1),
            output_tokens=int(requote * out_per_lemma + requests * thinking_mean[model]),
        )
        requoted[model] = round(topics.cost(model, usage, batch=True), 2)
    summary = {
        "run": run.name,
        "language": language,
        "version": rl.VERSION[language],
        "prompt": rl.PROMPT_VERSION,
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


def _example(language: str) -> rl.Answer:
    if language == "he":
        return rl.HebrewRoot("", "", False, "", "", "", "high")
    return rl.RussianRoot((rl.Morph("x"),), (), (), "", False, "high")


def _brief(summary: dict[str, Any]) -> dict[str, Any]:
    """The summary without the checks' miss lists, for the terminal."""
    out = json.loads(json.dumps(summary))
    for model in out["models"].values():
        for check in model["checks"].values():
            if isinstance(check, dict):
                check.pop("misses", None)
    return dict(out)


def _blind(
    run: Path,
    language: str,
    answers: dict[str, dict[int, rl.Answer]],
    lemmas: list[Lemma],
    size: int,
    out: Path,
) -> None:
    """`size` rows, stratified over four frequency bands of the run, in a fixed shuffled
    order, with nothing a model said; the models' answers go to the run directory apart."""
    bands = 4
    edges = [round(len(lemmas) * b / bands) for b in range(bands + 1)]
    picker = random.Random(f"roots-blind-{run.name}")
    chosen: list[int] = []
    for b in range(bands):
        pool = list(range(edges[b], edges[b + 1]))
        want = size // bands + (1 if b < size % bands else 0)
        chosen += picker.sample(pool, min(want, len(pool)))
    picker.shuffle(chosen)

    blind = io.StringIO()
    writer = csv.writer(blind, lineterminator="\n")
    columns = rl.GOLD_COLUMNS[language]
    writer.writerow(columns)
    for row, i in enumerate(chosen, start=1):
        one = lemmas[i]
        given = [str(row), one.lemma, one.pointed, one.pos, one.gloss]
        writer.writerow(given + [""] * (len(columns) - len(given)))
    out.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(out, blind.getvalue())

    hidden = io.StringIO()
    writer = csv.writer(hidden, lineterminator="\n")
    models = list(answers)
    fields = list(rl.cells(_example(language)).keys())
    writer.writerow(
        ["row", "id", "lemma"]
        + [f"{m.removeprefix('claude-')}_{f}" for m in models for f in fields]
    )
    for row, i in enumerate(chosen, start=1):
        cells = [rl.cells(answers[m].get(i)) for m in models]
        writer.writerow([row, i, lemmas[i].lemma] + [c.get(f, "") for c in cells for f in fields])
    write_atomic(run / "blind-answers.csv", hidden.getvalue())
    write_atomic(run / "blind-rows.json", json.dumps({str(r): i for r, i in enumerate(chosen, 1)}))
    print(f"Blind set: {len(chosen)} rows to {out}.")
    print(f"Model answers for those rows, kept apart: {run / 'blind-answers.csv'}")


def _score(
    run: Path,
    state: dict[str, Any],
    language: str,
    models: list[str],
    chunks: list[list[int]],
    gold: Path,
) -> int:
    rows_file = run / "blind-rows.json"
    if not rows_file.is_file():
        print(f"No blind set was drawn for {run.name}.", file=sys.stderr)
        return 2
    rows = {int(k): int(v) for k, v in json.loads(rows_file.read_text()).items()}
    scores = {
        model: rl.score(language, gold, _answers(state, language, model, chunks), rows)
        for model in models
    }
    write_atomic(run / "gold-score.json", json.dumps(scores, ensure_ascii=False, indent=1))
    for model, result in scores.items():
        line = ", ".join(
            f"{name} {part['rate']} ({part['agreed']}/{part['asked']})"
            for name, part in result.items()
        )
        print(f"{model}: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
