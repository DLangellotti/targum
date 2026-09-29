"""Ask the shelf-search questions of every catalogue row, and score them (#319).

The first step #319 names: one sweep over a catalogue already on disk, scored against
rows a person already accepted or rejected. The catalogue is the accepted half. The
rejected half was the per-candidate evidence in `~/.targum/research` — the staged
Italian rows, the LibriVox table, the video probes — and it was deleted on 2026-09-27,
so what this can score is what the owner wrote on the rows they kept:

- **language**: every kept row is in the language it claims, so a Noul below 0.5 on one
  is a miss.
- **origin**: where a row has a published English, its note says which came first
  (`shelf_screen.said_translation`). Rows with no English carry no label and are skipped.
  The note says which of the two came first, not whether the row is itself a translation
  from a third language: on 2026-09-28 fifteen of the seventeen misses were Targum
  Jonathan and Ibn Tibbon's Hebrew of the Chovot HaLevavot, both translations, both
  called translations by the screen and "original" by the label.
- **subject**: where a row carries a tag (#289, #311), the screen's pick has to be one
  of them. Untagged rows are skipped: untagged means nobody filed it, not "no subject".
- **prose**: every sampled opening on the shelf is prose somebody chose, so the same.
- **accept**: `Screened.passes` over the kept rows is recall on accept. Precision needs
  rejected rows and is printed as not measurable rather than as a number.
- **learner** has no label; its mean is printed beside the shelf's own difficulty bands.

It spends, so it keeps the rules `sentence_levels.py` keeps: a `--cap` in dollars counted
across runs, every answer appended and flushed to `answers.jsonl` before the next is
counted, and a rerun that asks only what is not in it.

    set -a && . ./.env && set +a
    .venv/bin/python scripts/screen_shelf.py --out /tmp/shelf-screen --limit 20
    .venv/bin/python scripts/screen_shelf.py --out /tmp/shelf-screen
    .venv/bin/python scripts/screen_shelf.py --out /tmp/shelf-screen --score-only

The catalogue is private, and so is everything written to `--out`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum import jev, screen  # noqa: E402
from targum import shelf_screen as ss  # noqa: E402
from targum.catalogue import catalogue_path  # noqa: E402
from targum.licensing import Standing  # noqa: E402


def rows(path: Path) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    samples = {
        entry_id: [str(line.get("source") or "") for line in lines]
        for entry_id, lines in (raw.get("samples") or {}).items()
    }
    return list(raw.get("entries") or []), samples


def kept(answers: Path) -> tuple[dict[str, dict[str, Any]], int]:
    """Everything already bought: the answers by row id, and the tokens they cost."""
    got: dict[str, dict[str, Any]] = {}
    tokens = 0
    if not answers.exists():
        return got, tokens
    for line in answers.read_text(encoding="utf-8").splitlines():
        try:
            one = json.loads(line)
        except ValueError:
            continue  # a line cut off by a kill; only what it bought is lost
        tokens += int(one.get("tokens") or 0)
        got[str(one["id"])] = one.get("answers") or {}
    return got, tokens


def fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def score(
    catalogue: list[dict[str, Any]], samples: dict[str, list[str]], got: dict[str, Any]
) -> dict[str, Any]:
    """Per question and per language, over every row that has an answer."""
    by_language: dict[str, list[tuple[dict[str, Any], ss.Screened]]] = defaultdict(list)
    for raw in catalogue:
        answers = got.get(str(raw.get("id")))
        if answers is None:
            continue
        candidate = ss.from_row(raw, samples.get(str(raw.get("id")), []))
        by_language[candidate.language].append((raw, ss.read(candidate, answers)))
    by_language["all"] = [pair for pairs in list(by_language.values()) for pair in pairs]

    report: dict[str, Any] = {}
    for language, pairs in sorted(by_language.items()):
        yes = [(True, s.language is not None and s.language >= ss.YES) for _, s in pairs]
        prose = [(True, s.prose >= ss.YES) for _, s in pairs if s.prose is not None]
        origin = [
            (
                ss.said_translation(raw),
                None if not s.origin else s.origin == "translation",
            )
            for raw, s in pairs
        ]
        tagged = [
            (True, s.subject in (raw.get("tags") or [])) for raw, s in pairs if raw.get("tags")
        ]
        accepted = ss.confusion([(True, s.passes) for _, s in pairs])
        bands: dict[str, list[float]] = defaultdict(list)
        for raw, s in pairs:
            if s.learner is not None and int(raw.get("difficulty") or 0) > 0:
                bands[screen.band(int(raw["difficulty"]))].append(s.learner)
        origin_translations = [(g, a) for g, a in origin if g is True]
        origin_originals = [(g, a) for g, a in origin if g is False]
        report[language] = {
            "rows": len(pairs),
            "language": asdict(ss.agreement(yes)),
            "prose": asdict(ss.agreement(prose)),
            "origin": asdict(ss.agreement(origin)),
            "origin_on_translations": asdict(ss.agreement(origin_translations)),
            "origin_on_originals": asdict(ss.agreement(origin_originals)),
            "subject": asdict(ss.agreement(tagged)),
            "accept_recall": accepted.recall,
            "accept_precision": accepted.precision,
            "licence_unknown": sum(1 for _, s in pairs if s.licence is Standing.unknown),
            "learner_by_band": {
                band: round(sum(v) / len(v), 3) for band, v in sorted(bands.items())
            },
        }
    return report


def show(report: dict[str, Any]) -> None:
    def cell(one: dict[str, int]) -> str:
        n = one["n"]
        return f"{one['right'] / n:.3f} ({one['right']}/{n})" if n else "n/a"

    for language, one in report.items():
        print(f"\n== {language}: {one['rows']} rows")
        for key in (
            "language",
            "prose",
            "origin",
            "origin_on_translations",
            "origin_on_originals",
            "subject",
        ):
            print(f"  {key:24} {cell(one[key])}")
        print(f"  {'accept recall':24} {fmt(one['accept_recall'])}")
        print(f"  {'accept precision':24} {fmt(one['accept_precision'])} (no rejected rows)")
        print(f"  {'licence unknown':24} {one['licence_unknown']}")
        print(f"  {'learner mean by band':24} {one['learner_by_band']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--catalogue", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--languages", nargs="*", default=[])
    parser.add_argument("--limit", type=int, default=0, help="new rows to ask, at most")
    parser.add_argument("--cap", type=float, default=1.0, help="dollars, across every run")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--model", default=jev.MODEL)
    parser.add_argument("--score-only", action="store_true")
    args = parser.parse_args()

    path = args.catalogue or catalogue_path()
    if path is None:
        raise SystemExit("no catalogue; pass --catalogue")
    catalogue, samples = rows(path)
    if args.languages:
        catalogue = [raw for raw in catalogue if raw.get("language") in args.languages]
    args.out.mkdir(parents=True, exist_ok=True)
    answers_path = args.out / "answers.jsonl"
    got, tokens = kept(answers_path)
    print(
        f"{len(catalogue)} rows, {len(got)} already answered, ${tokens * jev.PER_TOKEN:.6f} spent"
    )

    if not args.score_only:
        token = jev.key()
        todo = [raw for raw in catalogue if str(raw.get("id")) not in got]
        if args.limit:
            todo = todo[: args.limit]
        # One request per row: the state is the row, the questions are the issue's. Its
        # size in bytes bounds its tokens from above, so the cap is checked before sending.
        planned = []
        for raw in todo:
            candidate = ss.from_row(raw, samples.get(str(raw.get("id")), []))
            body = {"state": ss.state(candidate), "questions": ss.questions(candidate)}
            planned.append((candidate, body, len(json.dumps(body, ensure_ascii=False).encode())))
        spend = tokens + sum(size for _, _, size in planned)
        if spend * jev.PER_TOKEN > args.cap:
            raise SystemExit(f"at most ${spend * jev.PER_TOKEN:.4f} would pass the ${args.cap} cap")

        def ask(item: tuple[ss.Candidate, dict[str, Any], int]) -> tuple[str, dict[str, Any]]:
            candidate, body, _ = item
            return candidate.id, jev.ask(
                body["state"], body["questions"], model=args.model, token=token
            )

        with (
            answers_path.open("a", encoding="utf-8") as ledger,
            ThreadPoolExecutor(max_workers=args.workers) as pool,
        ):
            for done, (row_id, response) in enumerate(pool.map(ask, planned), start=1):
                used = jev.spent(response)
                answers = response.get("answers") or {}
                line = {
                    "id": row_id,
                    "model": response.get("model"),
                    "tokens": used,
                    "answers": answers,
                }
                ledger.write(json.dumps(line, ensure_ascii=False) + "\n")
                ledger.flush()
                os.fsync(ledger.fileno())
                got[row_id] = answers
                tokens += used
                if done % 100 == 0:
                    print(
                        f"{done} of {len(planned)}, ${tokens * jev.PER_TOKEN:.6f}", file=sys.stderr
                    )
        print(
            f"asked {len(planned)} rows; total spent "
            f"${tokens * jev.PER_TOKEN:.6f} ({tokens} tokens)"
        )

    report = score(catalogue, samples, got)
    report["spent"] = {"tokens": tokens, "dollars": round(tokens * jev.PER_TOKEN, 6)}
    (args.out / "report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    show({k: v for k, v in report.items() if k != "spent"})


if __name__ == "__main__":
    main()
