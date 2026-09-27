"""Ask, once per sentence of the Hebrew library, which ulpan rung follows it (#320).

A laptop batch job with David's consent (2026-09-27), not a chat turn: it reads the built
shelf, asks Jev one passage at a time (`targum.sentence_level`), and keeps the answers
where the box can be handed them. It spends, so it keeps the three rules a run that
spends keeps here:

- **A cap.** `--cap` dollars, $5 by default, counted from what every earlier run of it
  already spent. A request is not sent unless the total, the requests still in flight
  and this one's estimate all fit under it. The estimate is the request's size times the
  worst tokens-per-byte seen so far, starting from one token a byte, which no Hebrew
  request comes near.
- **A checkpoint after every paid request.** Each answer is appended to `answers.jsonl`
  and flushed before the next is counted, and a rerun reads that file first and asks
  only what is not in it — so a killed run resumes without buying anything twice. The
  compiled `sentence-levels.json` is rewritten whole (temp file, then rename) every
  `--every` requests and at the end.
- **A sample first.** `--only` takes folder or catalogue names and `--sentences` stops
  after that many new sentences; the run prints the cost per sentence it measured and
  what the whole library would cost at that rate.

Only catalogue texts are sent: a text whose source is not a catalogue entry is somebody's
own import and never reaches a new vendor (targum-internal#309). Hebrew only. Chanting
marks are taken off before sending — they say how a verse is sung, not what it means —
and the vowels stay.

    set -a && . ./.env && set +a
    .venv/bin/python scripts/sentence_levels.py --out targum-out --only רות --sentences 200
    .venv/bin/python scripts/sentence_levels.py --out targum-out            # everything
    .venv/bin/python scripts/sentence_levels.py --compile-only              # no key, no spend

Nothing here writes into `--out`. The answers live in `~/.targum/sentence-difficulty/`,
private like the catalogue; `deploy/deploy.sh` carries the compiled file to the box.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import catalogue, jev  # noqa: E402
from targum import sentence_level as sl  # noqa: E402
from targum.vocalize.base import strip_taamim  # noqa: E402

HOME = Path.home() / ".targum" / "sentence-difficulty"

#: Kinds of block that are not sentences anybody reads for their Hebrew.
SKIP_KINDS = ("heading", "byline")


@dataclass
class Text:
    folder: Path
    title: str
    entry: str
    register: str
    blocks: list[list[str]]


def texts(out: Path, only: list[str]) -> Iterator[Text]:
    """Every built catalogue text in Hebrew under `out`, each once however many shelves
    carry a copy, in a fixed order so a rerun walks the same way."""
    entries = {catalogue._key(entry.source): entry for entry in catalogue.everything()}
    seen: set[str] = set()
    for document in sorted(out.rglob("document.json")):
        folder = document.parent
        segments = folder / "segments.json"
        if not segments.is_file():
            continue
        try:
            doc = json.loads(document.read_text(encoding="utf-8"))
            seg = json.loads(segments.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not str(seg.get("language") or doc.get("language") or "").startswith("he"):
            continue
        entry = entries.get(catalogue._key(str(doc.get("source") or "")))
        if entry is None:
            continue
        if only and not any(one in (folder.name, entry.id) for one in only):
            continue
        identity = str(doc.get("content_hash") or folder)
        if identity in seen:
            continue
        seen.add(identity)
        blocks: dict[str, list[str]] = {}
        for segment in seg.get("segments") or []:
            if segment.get("kind") in SKIP_KINDS:
                continue
            blocks.setdefault(str(segment.get("block_id")), []).append(str(segment["text"]))
        yield Text(folder, entry.title, entry.id, entry.register.value, list(blocks.values()))


def kept(answers: Path) -> tuple[dict[str, sl.Level], int, str]:
    """Everything already bought: the answers by sentence, the tokens they cost, and the
    model that gave them."""
    levels: dict[str, sl.Level] = {}
    tokens = 0
    model = jev.MODEL
    if not answers.exists():
        return levels, tokens, model
    for line in answers.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            got = json.loads(line)
        except ValueError:
            # A line cut off by a kill mid-write. What it bought is lost, and only that.
            continue
        tokens += int(got.get("tokens") or 0)
        model = str(got.get("model") or model)
        for k, answer in (got.get("answers") or {}).items():
            level = sl.answered(answer)
            if level is not None:
                levels[k] = level
    return levels, tokens, model


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("targum-out"))
    parser.add_argument("--only", nargs="*", default=[])
    parser.add_argument("--sentences", type=int, default=0, help="stop after this many new")
    parser.add_argument("--per-text", type=int, default=0, help="new sentences per text, at most")
    parser.add_argument("--cap", type=float, default=5.0, help="dollars, across every run")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--every", type=int, default=25)
    parser.add_argument("--home", type=Path, default=HOME)
    parser.add_argument("--model", default=jev.MODEL)
    parser.add_argument("--compile-only", action="store_true")
    args = parser.parse_args()

    args.home.mkdir(parents=True, exist_ok=True)
    answers_path = args.home / "answers.jsonl"
    compiled = args.home / "sentence-levels.json"
    review = args.home / "review.jsonl"
    levels, tokens, model = kept(answers_path)
    print(f"{len(levels)} sentences already answered, ${tokens * jev.PER_TOKEN:.4f} spent")
    if args.compile_only:
        sl.write(levels, compiled, model)
        print(f"wrote {compiled}")
        return

    token = jev.key()
    library = list(texts(args.out, args.only))
    everything: set[str] = set()
    for text in library:
        for block in text.blocks:
            everything.update(sl.key(sentence) for sentence in block if sentence.strip())
    left = everything - set(levels)
    print(f"{len(library)} texts, {len(everything)} sentences, {len(left)} not yet answered")
    whole = everything
    if args.only:
        # A sample's cost is only worth having beside what the whole library would cost.
        whole = {
            sl.key(sentence)
            for text in texts(args.out, [])
            for block in text.blocks
            for sentence in block
            if sentence.strip()
        }

    lock = threading.Lock()
    ratio = 1.0  # tokens per byte of request, the worst seen; one a byte to start
    inflight = 0.0
    asked = 0
    new_tokens = 0
    requests = 0
    stopped = ""

    def send(state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        return jev.ask(state, questions, model=args.model, token=token)

    with (
        answers_path.open("a", encoding="utf-8") as ledger,
        review.open("a", encoding="utf-8") as notes,
        ThreadPoolExecutor(max_workers=args.workers) as pool,
    ):
        running: dict[Future[dict[str, Any]], tuple[sl.Chunk, set[str], float, int, Text]] = {}

        def settle(done: set[Future[dict[str, Any]]]) -> None:
            nonlocal tokens, new_tokens, inflight, ratio, requests, model
            for future in done:
                chunk, asking, estimate, size, text = running.pop(future)
                inflight -= estimate
                got = future.result()
                used = jev.spent(got)
                model = str(got.get("model") or model)
                line = {
                    "model": model,
                    "tokens": used,
                    "entry": text.entry,
                    "answers": {
                        k: {
                            key: value
                            for key, value in answer.items()
                            if key in ("score", "confidence", "probabilities")
                        }
                        for k, answer in (got.get("answers") or {}).items()
                    },
                }
                with lock:
                    ledger.write(json.dumps(line, ensure_ascii=False) + "\n")
                    ledger.flush()
                    os.fsync(ledger.fileno())
                    tokens += used
                    new_tokens += used
                    requests += 1
                    ratio = max(ratio if requests > 1 else 0.0, used / max(1, size))
                    for k, sentence in zip(chunk.keys, chunk.sentences, strict=True):
                        level = sl.answered((got.get("answers") or {}).get(k) or {})
                        if level is None or k not in asking:
                            continue
                        levels[k] = level
                        notes.write(
                            json.dumps(
                                {
                                    "entry": text.entry,
                                    "register": text.register,
                                    "key": k,
                                    "text": sentence,
                                    "level": level.row(),
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                    notes.flush()
                if requests % args.every == 0:
                    sl.write(levels, compiled, model)
                    print(
                        f"{requests} requests, {len(levels)} kept, "
                        f"${tokens * jev.PER_TOKEN:.4f} spent",
                        file=sys.stderr,
                        flush=True,
                    )

        try:
            for text in library:
                if stopped:
                    break
                here = 0
                for chunk in sl.chunks(text.blocks, show=strip_taamim):
                    if args.per_text and here >= args.per_text:
                        break
                    asking = {k for k in chunk.keys if k not in levels}
                    if not asking:
                        continue
                    if args.sentences and asked >= args.sentences:
                        stopped = f"--sentences {args.sentences} reached"
                        break
                    state, questions = sl.request(chunk, asking)
                    size = len(json.dumps({"state": state, "questions": questions}).encode())
                    estimate = size * ratio * 1.1
                    while len(running) >= args.workers:
                        done, _ = wait(running, return_when=FIRST_COMPLETED)
                        settle(done)
                    if (tokens + inflight + estimate) * jev.PER_TOKEN > args.cap:
                        stopped = f"the ${args.cap:.2f} cap"
                        break
                    inflight += estimate
                    asked += len(asking)
                    here += len(asking)
                    future = pool.submit(send, state, questions)
                    running[future] = (chunk, asking, estimate, size, text)
            while running:
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                settle(done)
        finally:
            sl.write(levels, compiled, model)

    per = new_tokens * jev.PER_TOKEN / max(1, asked)
    print(f"stopped at {stopped}" if stopped else "done")
    print(
        f"asked {asked} sentences in {requests} requests: {new_tokens} tokens, "
        f"${new_tokens * jev.PER_TOKEN:.4f} (${per * 1000:.4f} per thousand sentences)"
    )
    print(f"total spent ${tokens * jev.PER_TOKEN:.4f}; {len(levels)} kept in {compiled}")
    remaining = len(whole - set(levels))
    if remaining:
        print(
            f"{remaining} of the library's {len(whole)} sentences are left; "
            f"at this rate they cost about ${remaining * per:.2f}"
        )


if __name__ == "__main__":
    main()
