"""Whether scripture reads harder, or only reads older (targum-internal#320).

The library was scored per sentence in the `situations` wording, and scripture came out
high: the passage pointer fires only from dalet up. Two things would put it there. A verse
may really want more Hebrew than a line of news, or the top rungs, which name "archaic",
"classical" and "rabbinic" words, may pull anything that reads old towards them whatever
its words. This separates the two on a sample:

1. **draw** (free). Every sentence of the built catalogue texts, with its running words'
   dictionary forms off the annotation, names and numbers left out as `coverage.py`
   leaves them out. Each is measured as `coverage.Reading` measures a section — the share
   of running words a reader knows — for a reader who knows the language's commonest N
   words, N being each ulpan rung's figure (`level.ULPAN`). Sentences are put in strata
   by that share at `MATCH_AT` (gimel) and by length, and the same number of biblical and
   modern sentences is drawn from every stratum both have, spread across texts. So the
   two groups carry the same words-a-reader-knows and the same length; what is left to
   differ is how old they read.
2. **score** (spends, under `--cap`). Each sampled sentence is asked in both wordings
   (`sentence_level.PROMPTS`), against the same passage the library run asked it
   against, only the sampled sentences asked. Every paid request is appended to the
   ledger before the next is sent, and a rerun asks only what is missing.
3. **report** (free). The rung each group lands on in each wording, the gap between the
   groups, and whether the new wording keeps the texts in the same order (Spearman's rho
   over per-text means).

    .venv/bin/python scripts/sentence_bias.py draw --out targum-out --dir DIR
    op run --env-file op.env -- .venv/bin/python scripts/sentence_bias.py score --dir DIR
    .venv/bin/python scripts/sentence_bias.py report --dir DIR

Nothing here writes into `--out` or into the library's own answers; it reads the compiled
`sentence-levels.json` only to set the library's score beside the sample's.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import re
import sys
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import coverage, jev  # noqa: E402
from targum import sentence_level as sl  # noqa: E402
from targum.annotate.base import not_vocabulary  # noqa: E402
from targum.level import ULPAN  # noqa: E402

#: The registers each side is drawn from. Modern only: revival Hebrew is early literary
#: prose with its own old words, and would muddy the side meant to read new.
GROUPS: dict[str, frozenset[str]] = {
    "biblical": frozenset({"biblical"}),
    "modern": frozenset({"modern"}),
}

#: The rung whose coverage the groups are matched on: gimel, the middle of the ladder,
#: and below dalet, where the pointer starts firing for scripture today.
MATCH_AT = 4
#: Edges of the coverage strata, as shares of running words known at `MATCH_AT`.
COVERAGE_EDGES = (0.5, 0.6, 0.7, 0.8, 0.9, 0.95)
#: Edges of the length strata, in running words.
LENGTH_EDGES = (7, 13, 21)

PER_GROUP = 200
SEED = 320
#: A text needs this many sampled sentences for its mean to be ranked.
PER_TEXT = 3

SKIP_KINDS = ("heading", "byline")

#: Vowels and marks, which the frequency list is not written with (`frequency.rank`).
POINTS = re.compile("[\u0591-\u05c7]")


@dataclass(frozen=True)
class Sentence:
    key: str
    entry: str
    register: str
    text: str
    folder: str
    #: Dictionary form of every running word, names and numbers left out.
    words: tuple[str, ...]


# -- measuring ------------------------------------------------------------------------


def running_words(tokens: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    """A sentence's running words as `coverage.section_lemmas` counts them."""
    out: list[str] = []
    for token in tokens:
        lemma = str(token.get("lemma") or "")
        if lemma and not not_vocabulary(token.get("pos"), token.get("entity")):
            out.append(lemma)
    return tuple(out)


def reading_at(words: Iterable[str], ranks: dict[str, int], at: int) -> coverage.Reading:
    """What a reader who knows the language's `at` commonest words knows of these: the
    ledger such a reader would have, laid against the words as `section_reading` lays a
    real one. A form the frequency list does not reach is a form they do not know."""
    listed = list(words)
    marked = {w: coverage.KNOWN for w in listed if ranks.get(POINTS.sub("", w), at + 1) <= at}
    return coverage.Reading(
        tokens=len(listed), known=sum(1 for w in listed if marked.get(w) == coverage.KNOWN)
    )


def share_at(words: Iterable[str], ranks: dict[str, int], rung: int) -> float:
    """The share of running words known at ulpan rung `rung` (an index into `ULPAN`)."""
    reading = reading_at(words, ranks, ULPAN[rung].at)
    return reading.known / reading.tokens if reading.tokens else 0.0


def profile(words: Iterable[str], ranks: dict[str, int]) -> list[float]:
    listed = list(words)
    return [share_at(listed, ranks, rung) for rung in range(len(ULPAN))]


def stratum(sentence: Sentence, ranks: dict[str, int]) -> tuple[int, int]:
    """(coverage stratum at `MATCH_AT`, length stratum)."""
    return (
        bisect_right(COVERAGE_EDGES, share_at(sentence.words, ranks, MATCH_AT)),
        bisect_right(LENGTH_EDGES, len(sentence.words)),
    )


def group_of(register: str) -> str | None:
    return next((name for name, held in GROUPS.items() if register in held), None)


# -- drawing --------------------------------------------------------------------------


def spread(rows: list[Sentence], n: int, rng: random.Random) -> list[Sentence]:
    """`n` of `rows`, a text at a time in turn, so one long book cannot fill a stratum.
    The texts' order and each text's sentences are shuffled by `rng`."""
    by_text: dict[str, list[Sentence]] = defaultdict(list)
    for row in rows:
        by_text[row.entry].append(row)
    queues = [by_text[entry] for entry in sorted(by_text)]
    rng.shuffle(queues)
    for queue in queues:
        rng.shuffle(queue)
    out: list[Sentence] = []
    while len(out) < n and any(queues):
        for queue in queues:
            if queue and len(out) < n:
                out.append(queue.pop())
    return out


def allot(capacity: dict[Any, int], total: int) -> dict[Any, int]:
    """`total` split across strata in proportion to what each can give, never more than
    it has: largest remainders first, then whatever is left to strata with room."""
    have = sum(capacity.values())
    if not have:
        return {}
    total = min(total, have)
    exact = {s: total * c / have for s, c in capacity.items()}
    given = {s: min(capacity[s], int(x)) for s, x in exact.items()}
    order = sorted(capacity, key=lambda s: (-(exact[s] - int(exact[s])), s))
    while sum(given.values()) < total:
        moved = False
        for s in order:
            if sum(given.values()) >= total:
                break
            if given[s] < capacity[s]:
                given[s] += 1
                moved = True
        if not moved:
            break
    return {s: n for s, n in given.items() if n}


def draw(
    sentences: Iterable[Sentence],
    ranks: dict[str, int],
    per_group: int = PER_GROUP,
    seed: int = SEED,
) -> list[Sentence]:
    """The matched sample: the same number of sentences from each group in every
    stratum both groups reach, about `per_group` a side. Strata only one group reaches
    are left out — they are where the groups differ in words, which is not the question.
    Deterministic for a seed."""
    rng = random.Random(seed)
    strata: dict[tuple[int, int], dict[str, list[Sentence]]] = defaultdict(
        lambda: {name: [] for name in GROUPS}
    )
    for sentence in sentences:
        name = group_of(sentence.register)
        if name is None or not sentence.words:
            continue
        strata[stratum(sentence, ranks)][name].append(sentence)
    capacity = {
        s: min(len(rows) for rows in held.values())
        for s, held in strata.items()
        if all(held.values())
    }
    out: list[Sentence] = []
    for s, n in sorted(allot(capacity, per_group).items()):
        for name in GROUPS:
            out.extend(spread(strata[s][name], n, rng))
    return out


# -- reading the shelf ----------------------------------------------------------------


def from_folder(folder: Path, entry: str, register: str) -> Iterator[Sentence]:
    """Every sentence of one built text that has running words, keyed as the library
    run keyed it."""
    try:
        segments = json.loads((folder / "segments.json").read_text(encoding="utf-8"))
        annotation = json.loads((folder / "annotation.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    tokens = annotation.get("tokens") or {}
    for segment in segments.get("segments") or []:
        if segment.get("kind") in SKIP_KINDS:
            continue
        text = str(segment.get("text") or "")
        words = running_words(tokens.get(segment.get("id")) or [])
        if text.strip() and words:
            yield Sentence(sl.key(text), entry, register, text, str(folder), words)


def blocks_of(folder: Path) -> list[list[str]]:
    """A built text's paragraphs as the library run read them."""
    segments = json.loads((folder / "segments.json").read_text(encoding="utf-8"))
    blocks: dict[str, list[str]] = {}
    for segment in segments.get("segments") or []:
        if segment.get("kind") in SKIP_KINDS:
            continue
        blocks.setdefault(str(segment.get("block_id")), []).append(str(segment["text"]))
    return list(blocks.values())


def library_texts(out: Path) -> Iterator[Any]:
    """The catalogue texts the library run read, through its own walk, so nothing that is
    somebody's import is ever sent."""
    where = Path(__file__).resolve().parent / "sentence_levels.py"
    spec = importlib.util.spec_from_file_location("sentence_levels", where)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield from module.texts(out, [])


# -- the numbers ----------------------------------------------------------------------


def ranked(values: list[float]) -> list[float]:
    """Ranks from 1, ties sharing their mean rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            out[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return out


def spearman(xs: list[float], ys: list[float]) -> float:
    """Spearman's rho: Pearson's r over the ranks, which stays right with ties."""
    if len(xs) != len(ys) or len(xs) < 2:
        return float("nan")
    rx, ry = ranked(xs), ranked(ys)
    mx, my = mean(rx), mean(ry)
    top = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    bottom = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return top / bottom if bottom else float("nan")


def distribution(rungs: Iterable[int]) -> list[int]:
    """How many answers landed on each rung, aleph to beyond."""
    out = [0] * (sl.BEYOND + 1)
    for rung in rungs:
        out[rung] += 1
    return out


# -- phases ---------------------------------------------------------------------------


def do_draw(args: argparse.Namespace) -> None:
    from targum.annotate.frequency import ranks as frequency_ranks

    ranks = frequency_ranks("he")
    seen: set[str] = set()
    every: list[Sentence] = []
    for text in library_texts(args.out):
        if group_of(text.register) is None:
            continue
        for sentence in from_folder(text.folder, text.entry, text.register):
            if sentence.key not in seen:
                seen.add(sentence.key)
                every.append(sentence)
    sample = draw(every, ranks, args.per_group, args.seed)
    args.dir.mkdir(parents=True, exist_ok=True)
    with (args.dir / "sample.jsonl").open("w", encoding="utf-8") as out:
        for sentence in sample:
            row = asdict(sentence)
            row["stratum"] = list(stratum(sentence, ranks))
            row["profile"] = [round(p, 4) for p in profile(sentence.words, ranks)]
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    pool = defaultdict(int)
    for sentence in every:
        pool[group_of(sentence.register)] += 1
    print(f"pool: {dict(pool)}; drew {len(sample)} into {args.dir / 'sample.jsonl'}")
    for name in GROUPS:
        rows = [s for s in sample if group_of(s.register) == name]
        shares = [profile(s.words, ranks) for s in rows]
        print(
            f"{name}: {len(rows)} sentences from {len({s.entry for s in rows})} texts, "
            f"{mean(len(s.words) for s in rows):.1f} words, known at each rung "
            + " ".join(f"{mean(p[r] for p in shares):.2f}" for r in range(len(ULPAN)))
        )


def read_sample(where: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (where / "sample.jsonl").read_text("utf-8").splitlines()]


def answers(where: Path, prompt: str) -> tuple[dict[str, sl.Level], int]:
    """What one wording has bought for the sample so far, and the tokens it cost."""
    path = where / f"answers-{prompt}.jsonl"
    levels: dict[str, sl.Level] = {}
    tokens = 0
    if not path.exists():
        return levels, tokens
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            got = json.loads(line)
        except ValueError:
            continue
        tokens += int(got.get("tokens") or 0)
        for k, answer in (got.get("answers") or {}).items():
            level = sl.answered(answer)
            if level is not None:
                levels[k] = level
    return levels, tokens


def asks(sample: list[dict[str, Any]], have: set[str]) -> Iterator[tuple[str, sl.Chunk, set[str]]]:
    """Each passage that holds a sampled sentence not yet answered, and which of its
    sentences to ask: the chunks the library run sent, so the context is the same."""
    from targum.vocalize.base import strip_taamim

    wanted: dict[str, set[str]] = defaultdict(set)
    for row in sample:
        if row["key"] not in have:
            wanted[row["folder"]].add(row["key"])
    for folder, keys in sorted(wanted.items()):
        for chunk in sl.chunks(blocks_of(Path(folder)), show=strip_taamim):
            asking = keys & set(chunk.keys)
            if asking:
                yield folder, chunk, asking
                keys -= asking


def do_score(args: argparse.Namespace) -> None:
    sample = read_sample(args.dir)
    entry_of = {row["key"]: row["entry"] for row in sample}
    token = jev.key()
    spent = sum(answers(args.dir, prompt)[1] for prompt in sl.PROMPTS)
    print(f"${spent * jev.PER_TOKEN:.4f} spent on this sample before this run")
    for prompt in sl.PROMPTS:
        have, _ = answers(args.dir, prompt)
        todo = list(asks(sample, set(have)))
        with (args.dir / f"answers-{prompt}.jsonl").open("a", encoding="utf-8") as ledger:
            for start in range(0, len(todo), args.workers):
                batch = todo[start : start + args.workers]
                bodies = [sl.request(chunk, asking, prompt) for _, chunk, asking in batch]
                # One token a byte is more than any Hebrew request comes to.
                estimate = sum(len(json.dumps(b, ensure_ascii=False).encode()) for b in bodies)
                if (spent + estimate) * jev.PER_TOKEN > args.cap:
                    print(f"stopped at the ${args.cap:.2f} cap")
                    return
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    got = list(
                        pool.map(
                            lambda b: jev.ask(b[0], b[1], token=token, model=args.model), bodies
                        )
                    )
                for (_, _, asking), response in zip(batch, got, strict=True):
                    used = jev.spent(response)
                    spent += used
                    line = {
                        "prompt": prompt,
                        "model": str(response.get("model") or args.model),
                        "tokens": used,
                        "dollars": round(used * jev.PER_TOKEN, 6),
                        "entry": entry_of[next(iter(asking))],
                        "answers": {
                            k: {
                                f: v
                                for f, v in answer.items()
                                if f in ("score", "confidence", "probabilities")
                            }
                            for k, answer in (response.get("answers") or {}).items()
                        },
                    }
                    ledger.write(json.dumps(line, ensure_ascii=False) + "\n")
                    ledger.flush()
        print(f"{prompt}: {len(todo)} requests; ${spent * jev.PER_TOKEN:.4f} spent so far")
    print(f"done: ${spent * jev.PER_TOKEN:.4f} spent on this sample")


def summary(rows: list[dict[str, Any]], levels: dict[str, sl.Level]) -> dict[str, Any]:
    got = [levels[row["key"]] for row in rows if row["key"] in levels]
    if not got:
        return {"n": 0}
    return {
        "n": len(got),
        "mean": round(mean(level.score for level in got), 2),
        "rungs": distribution(level.rung for level in got),
        "gimel_reads": round(sum(level.readable(4) for level in got) / len(got), 3),
        "hey_or_above": round(sum(level.rung >= 6 for level in got) / len(got), 3),
        "confidence": round(mean(level.confidence for level in got), 2),
    }


def per_text(rows: list[dict[str, Any]], levels: dict[str, sl.Level]) -> dict[str, float]:
    scores: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row["key"] in levels:
            scores[row["entry"]].append(levels[row["key"]].score)
    return {entry: mean(s) for entry, s in scores.items() if len(s) >= PER_TEXT}


def do_report(args: argparse.Namespace) -> None:
    sample = read_sample(args.dir)
    columns: dict[str, dict[str, sl.Level]] = {"library": sl.load()}
    spent = 0
    for prompt in sl.PROMPTS:
        columns[prompt], tokens = answers(args.dir, prompt)
        spent += tokens
    groups = {name: [r for r in sample if group_of(r["register"]) in (name,)] for name in GROUPS}
    report: dict[str, Any] = {"spent": round(spent * jev.PER_TOKEN, 4), "groups": {}}
    names = " ".join(f"{n[:5]:>5}" for n, _ in sl.LEVELS)
    for name, rows in groups.items():
        report["groups"][name] = {
            "texts": len({r["entry"] for r in rows}),
            "words": round(mean(len(r["words"]) for r in rows), 1),
            "known": [round(mean(r["profile"][i] for r in rows), 3) for i in range(len(ULPAN))],
            **{column: summary(rows, levels) for column, levels in columns.items()},
        }
    report["gap"] = {
        column: round(
            report["groups"]["biblical"][column].get("mean", 0)
            - report["groups"]["modern"][column].get("mean", 0),
            2,
        )
        for column in columns
    }
    current, variant = (columns[p] for p in sl.PROMPTS)
    order: dict[str, Any] = {}
    for scope, rows in [("all", sample), *groups.items()]:
        a, b = per_text(rows, current), per_text(rows, variant)
        both = sorted(set(a) & set(b))
        order[scope] = {
            "texts": len(both),
            "rho": round(spearman([a[t] for t in both], [b[t] for t in both]), 3),
        }
    report["order"] = order
    (args.dir / "report.json").write_text(json.dumps(report, indent=1), "utf-8")
    print(f"spent ${report['spent']:.4f}")
    for name, held in report["groups"].items():
        print(
            f"\n{name}: {held['texts']} texts, {held['words']} words a sentence, known at "
            f"each rung {held['known']}"
        )
        print(f"{'':18} {'n':>4} {'mean':>5} {'gimel':>6} {'hey+':>5}   {names}")
        for column in columns:
            one = held[column]
            if not one.get("n"):
                continue
            print(
                f"{column:18} {one['n']:>4} {one['mean']:>5} {one['gimel_reads']:>6} "
                f"{one['hey_or_above']:>5}   " + " ".join(f"{c:>5}" for c in one["rungs"])
            )
    print(f"\nbiblical minus modern, mean rung: {report['gap']}")
    print(f"per-text order, {'/'.join(sl.PROMPTS)}: {order}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    phases = parser.add_subparsers(dest="phase", required=True)
    one = phases.add_parser("draw")
    one.add_argument("--out", type=Path, default=Path("targum-out"))
    one.add_argument("--per-group", type=int, default=PER_GROUP)
    one.add_argument("--seed", type=int, default=SEED)
    two = phases.add_parser("score")
    two.add_argument("--cap", type=float, default=2.0, help="dollars, across both wordings")
    two.add_argument("--workers", type=int, default=4)
    two.add_argument("--model", default=jev.MODEL)
    three = phases.add_parser("report")
    for phase in (one, two, three):
        phase.add_argument("--dir", type=Path, required=True)
    args = parser.parse_args()
    {"draw": do_draw, "score": do_score, "report": do_report}[args.phase](args)


if __name__ == "__main__":
    main()
