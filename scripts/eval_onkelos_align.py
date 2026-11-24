"""Score the Onkelos-to-Hebrew alignment against ling-arc's hand gold (targum-internal G3;
design.md §12, 2026-10-25: "measured against a 300-verse gold that ling-arc reads by hand,
with a floor in `evals/floors.json`").

Two steps, the first once:

    PYTHONPATH=src .venv/bin/python scripts/eval_onkelos_align.py --sheet
    PYTHONPATH=src .venv/bin/python scripts/eval_onkelos_align.py

`--sheet` writes `SHEET`: 300 verses, every nineteenth of the Torah so the poems come in
at their own share, each with its Onkelos words and its Hebrew words numbered and an empty
`links`. Nothing the alignment says is on it, so the reading is not led. ling-arc fills
`links` (each Onkelos word's number → the number of the Hebrew word it renders, or null
where it renders none or the verse is paraphrase there) and saves it as `GOLD`. Both live
under `~/.targum/evals`, outside the repository: they are the text of the verses.

Scored: precision, of the links drawn, how many the gold draws the same (a link where the
gold says null is wrong); recall, of the gold's links, how many are drawn. No key, no
network.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from count_aramaic import DEFAULT_CACHE, fetched  # noqa: E402
from count_onkelos_alignment import BOOKS  # noqa: E402

from targum import evals  # noqa: E402
from targum.annotate import oshb  # noqa: E402
from targum.annotate.onkelos_align import NAME, align, words  # noqa: E402

STAGE = "align"
CORPUS = "onkelos-gold"
HERE = Path.home() / ".targum" / "evals"
SHEET = HERE / "onkelos-align-sheet.jsonl"
GOLD = HERE / "onkelos-align-gold.jsonl"
EVERY = 19
VERSES = 300


def verse_pairs() -> list[tuple[str, list[str], list[str]]]:
    out: list[tuple[str, list[str], list[str]]] = []
    for book, code in BOOKS.items():
        document = fetched(f"sefaria:arc:{book}", DEFAULT_CACHE)
        onkelos = {
            block.ref.removeprefix("Onkelos ").removeprefix(f"{book} "): block.text
            for block in document.blocks
            if block.ref
        }
        for name, hebrew in oshb.verses(code):
            _, chapter, verse = name.split(".")
            ref = f"{chapter}:{verse}"
            if ref in onkelos:
                out.append((f"{book} {ref}", words(onkelos[ref]), [w.text for w in hebrew]))
    return out


def sheet(path: Path) -> None:
    chosen = verse_pairs()[::EVERY][:VERSES]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        for ref, aramaic, hebrew in chosen:
            row = {
                "ref": ref,
                "onkelos": dict(enumerate(aramaic)),
                "hebrew": dict(enumerate(hebrew)),
                "links": {},
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"{len(chosen)} verses -> {path}")


def score(gold: list[dict[str, object]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for row in gold:
        aramaic = list(dict(row["onkelos"]).values())  # type: ignore[call-overload]
        hebrew = list(dict(row["hebrew"]).values())  # type: ignore[call-overload]
        said = dict(row["links"])  # type: ignore[call-overload]
        drawn = align(aramaic, hebrew)
        for at, link in enumerate(drawn):
            truth = said.get(str(at))
            if truth is not None:
                counts["gold"] += 1
            if link is None:
                continue
            counts["drawn"] += 1
            if truth is not None and int(truth) == link:
                counts["right"] += 1
    return counts


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sheet", action="store_true", help="write the sheet to read")
    parser.add_argument("--gold", type=Path, default=GOLD)
    parser.add_argument("--ledger", type=Path, default=evals.DEFAULT)
    parser.add_argument("--dry", action="store_true")
    args = parser.parse_args(argv)
    if not oshb.available():
        raise SystemExit("OSHB is not on disk; run `targum models fetch scripture` first")
    if args.sheet:
        sheet(SHEET)
        return
    if not args.gold.is_file():
        raise SystemExit(
            f"no gold at {args.gold}: write the sheet with --sheet, and ling-arc reads it"
        )
    gold = [json.loads(line) for line in args.gold.read_text(encoding="utf-8").splitlines()]
    counts = score(gold)
    precision = round(counts["right"] / max(1, counts["drawn"]), 4)
    recall = round(counts["right"] / max(1, counts["gold"]), 4)
    note = evals.pinned(f"verses={len(gold)} {dict(counts)}", [args.gold])
    today = date.today().isoformat()
    rows = [
        evals.Row(
            today, STAGE, NAME, NAME, "link_precision", precision, counts["drawn"], CORPUS, note
        ),
        evals.Row(today, STAGE, NAME, NAME, "link_recall", recall, counts["gold"], CORPUS, note),
    ]
    for row in rows:
        print(f"{row.metric:16} {row.score:.4f}  n={row.n}  {row.system}")
    if not args.dry:
        evals.append(rows, args.ledger)
        print(f"appended {len(rows)} rows to {args.ledger}")


if __name__ == "__main__":
    main()
