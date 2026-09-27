"""The Russian side of the Tatoeba pool, for the Russian recast eval.

targum-internal#286 asks what a Russian reader's recast is worth, and #222 already
settled that **Tatoeba, not NTREX, is the recast's yardstick** — NTREX measures
faithfulness to a full translation, which a graded recast does not aim for. So the
Russian number has to be taken on Tatoeba, and Tatoeba's Hebrew rows had no Russian.

They do have one, and it costs nothing to find: Tatoeba publishes a `heb-rus` link file
of 11,516 pairs and a Russian sentence export, 74 KB and 23 MB. This joins them onto the
pool `scripts/tatoeba_pool.py` already built, writing `ru` and `ru_by` beside the `en`
and `en_by` that are there. **Nothing is lemmatized**: every matching row was lemmatized
when the pool was built, so no model loads and no GPU is wanted.

Of 165,454 pool rows, 6,682 have a Russian translation and 6,644 of those are at
sentence length — far more than an eval draws.

**Licence.** Tatoeba is CC BY 2.0 FR per sentence per contributor, so the Russian
contributor's username is kept exactly as the Hebrew and English ones are. LICENSING.md
says what is owed and where it is given.

    .venv/bin/python scripts/tatoeba_russian.py \\
      --exports ~/.targum/tatoeba-ru --pool ~/.targum/exemplars.jsonl \\
      --out ~/.targum/exemplars-ru.jsonl

The exports: `heb-rus_links.tsv` and `rus_sentences_detailed.tsv`, from
https://downloads.tatoeba.org/exports/per_language/ , unpacked into one directory.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

#: Tatoeba's detailed export: id, language, text, username, added, modified.
ID, LANGUAGE, TEXT, BY = 0, 1, 2, 3


def linked(path: Path) -> dict[str, list[str]]:
    """Hebrew sentence id to the Russian ids linked to it.

    The file is named for its direction — `heb-rus` — and the first column is the
    Hebrew. Verified rather than assumed: of 11,516 rows, 11,515 have their *second*
    column in the Russian export and none has its first.
    """
    out: dict[str, list[str]] = {}
    with path.open(encoding="utf-8", newline="") as lines:
        for row in csv.reader(lines, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(row) >= 2 and row[0] and row[1]:
                out.setdefault(row[0], []).append(row[1])
    return out


def russian(path: Path, wanted: set[str]) -> dict[str, tuple[str, str]]:
    """The wanted Russian sentences, as id to (text, contributor).

    Streamed and filtered on the way in: the export is 1.2 million rows and only about
    ten thousand of them are linked to Hebrew. Holding all of it is what a previous
    pool run learned not to do on an 8 GB laptop.
    """
    out: dict[str, tuple[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as lines:
        for row in csv.reader(lines, delimiter="\t", quoting=csv.QUOTE_NONE):
            if len(row) > BY and row[ID] in wanted and row[LANGUAGE] == "rus" and row[TEXT].strip():
                out[row[ID]] = (row[TEXT].strip(), row[BY])
    return out


def shortest(ids: list[str], said: dict[str, tuple[str, str]]) -> tuple[str, str] | None:
    """The shortest linked Russian sentence, which is the rule the pool already uses for
    picking among several English ones: the shortest is the least likely to have carried
    an extra clause in from somewhere else."""
    found = [said[one] for one in ids if one in said]
    return min(found, key=lambda pair: len(pair[0])) if found else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exports", type=Path, required=True, help="where the two TSVs are")
    parser.add_argument("--pool", type=Path, required=True, help="the pool to add Russian to")
    parser.add_argument("--out", type=Path, required=True, help="where the new pool goes")
    args = parser.parse_args()

    links_path = args.exports / "heb-rus_links.tsv"
    sentences_path = args.exports / "rus_sentences_detailed.tsv"
    for path in (links_path, sentences_path, args.pool):
        if not path.is_file():
            sys.exit(f"not here: {path}")

    links = linked(links_path)
    print(f"{len(links):,} Hebrew sentences carry a Russian link", flush=True)
    said = russian(sentences_path, {one for ids in links.values() for one in ids})
    print(f"{len(said):,} of those Russian sentences are in the export", flush=True)

    kept = rows = 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.pool.open(encoding="utf-8") as source, args.out.open("w", encoding="utf-8") as sink:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            rows += 1
            picked = shortest(links.get(str(row.get("id")), []), said)
            if picked is not None:
                row["ru"], row["ru_by"] = picked
                kept += 1
            sink.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\n{rows:,} rows written to {args.out}")
    print(f"{kept:,} of them now carry a Russian sentence ({kept / rows:.1%})")


if __name__ == "__main__":
    main()
