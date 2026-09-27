"""The scene corrections, turned into lines a pointer can be scored against (targum-internal#351).

targum#396 put the scene audit's judgements in the correction store: 391 rows of
`stage="scene"`, `who="author"`, each with the word as it stood, the word a person
settled on, and the line it stood in. They are corrections, not a scored set: they say
where the answer was wrong and what it should be. This makes a set from them.

**A gold line** is the line as it stood with every settled correction applied. Each
corrected word keeps its place in the line and one of three kinds:

- `points`: the letters stayed and the points changed. The main question for a pointer.
- `letters`: the letters changed too. A pointer is given the settled letters, so these
  score only whether it points the new word right.
- `kept`: a correction a person looked at and turned down. The word as written is the
  settled answer.

Only these words were settled by hand. The rest of each line passed two independent
model readings with nothing found, and was not marked word by word by a person. So the
harness reports the settled words on their own (`settled_*` in `measure_pointing.py`)
beside the whole-line numbers, and the settled words are the hand-marked number.

A line is left out whole when one of its corrections cannot be placed: the word is in
neither its old nor its new form in the line the row carries. A gold line with one
correction missing would score a model against the error the correction fixed.

**The file is private.** The scenes are targum's own content, so the set is written to
the gold directory on this machine, beside the IAHLT treebanks, and never to the
repository. It is rebuilt from the store at any time. The store is opened read-only.

    PYTHONPATH=src .venv/bin/python scripts/scene_nikkud_gold.py [--store …] [--out …]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum.dialogue.checks import bare  # noqa: E402
from targum.paths import ensure, model_dir, write_atomic  # noqa: E402
from targum.vocalize.base import LETTERS, MARKS  # noqa: E402

#: The rows this reads: the scene audit, in the author's own hand.
STAGE, WHO = "scene", "author"
#: Where the set goes, in the gold directory `measure_pointing.py` reads.
NAME = "scene-nikkud.jsonl"


def gold_path() -> Path:
    return ensure(model_dir() / "gold") / NAME


def kind_of(before: str, after: str) -> str:
    if before == after:
        return "kept"
    return "points" if bare(before) == bare(after) else "letters"


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def _inside_word(char: str) -> bool:
    return ord(char) in LETTERS or ord(char) in MARKS


def find_word(line: str, word: str) -> int:
    """Where `word` stands in `line` as a whole word, or -1.

    Whole, because a short word is often inside a longer one: `אֶת` is in `אַתְּ`'s
    neighbourhood and `לוֹ` is in `שֶׁלּוֹ`. A match with a letter or a point on either
    side is part of another word and is passed over.
    """
    if not word:
        return -1
    start = line.find(word)
    while start != -1:
        end = start + len(word)
        before_ok = start == 0 or not _inside_word(line[start - 1]) or not _inside_word(word[0])
        after_ok = end == len(line) or not _inside_word(line[end]) or not _inside_word(word[-1])
        if before_ok and after_ok:
            return start
        start = line.find(word, start + 1)
    return -1


def settle(line: str, corrections: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    """One line with its corrections applied, or None when one cannot be placed.

    `corrections` are store rows for this line, oldest first. Each settled word is kept
    as `[start, end]` in the returned line, with its kind and the word it replaced.
    """
    text = _nfc(line)
    settled: list[dict[str, Any]] = []
    for row in corrections:
        before, after = _nfc(row["before"]), _nfc(row["after"])
        kind = kind_of(before, after)
        at = find_word(text, before)
        if at == -1:
            # Already applied in the line the row carries: the new form is there and the
            # old one is not. The word is still a settled one.
            at = find_word(text, after)
            if at == -1 or not after:
                return None
            settled.append({"start": at, "end": at + len(after), "kind": kind, "was": before})
            continue
        end = at + len(before)
        shift = len(after) - len(before)
        text = text[:at] + after + text[end:]
        kept: list[dict[str, Any]] = []
        for one in settled:
            if one["end"] <= at:
                kept.append(one)
            elif one["start"] >= end:
                kept.append({**one, "start": one["start"] + shift, "end": one["end"] + shift})
            # A settled word this correction overlaps is superseded by it.
        settled = kept
        if after.strip():
            settled.append({"start": at, "end": at + len(after), "kind": kind, "was": before})
    # The same judgement written twice (two passes reached it) is one settled word.
    unique = {(one["start"], one["end"]): one for one in settled}
    return {"line": text, "settled": [unique[key] for key in sorted(unique)]}


def build(rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    """The gold lines, and a count of what was left out and why.

    Rows are grouped by `span` (a scene and a turn) in the order they were written. A row
    with no line under it is not about a line — the cast rename is one — and is counted,
    not used.
    """
    by_span: dict[str, list[Mapping[str, Any]]] = {}
    english: dict[str, str] = {}
    left_out: Counter[str] = Counter()
    for row in sorted(rows, key=lambda r: (r.get("at", 0), r.get("id", 0))):
        if not row.get("context"):
            left_out["no line"] += 1
            continue
        by_span.setdefault(row["span"], []).append(row)
        english.setdefault(row["span"], row.get("text") or "")
    lines: list[dict[str, Any]] = []
    for span, group in by_span.items():
        contexts = {_nfc(row["context"]) for row in group}
        if len(contexts) > 1:
            left_out["line quoted two ways"] += len(group)
            continue
        done = settle(group[0]["context"], group)
        if done is None:
            left_out["correction not placed"] += len(group)
            continue
        lines.append(
            {
                "span": span,
                "english": english[span],
                "was": _nfc(group[0]["context"]),
                **done,
                "ids": [row.get("id") for row in group],
            }
        )
    return lines, left_out


def read_store(path: Path) -> list[dict[str, Any]]:
    """The scene rows, read-only: this is the store of every reader's list too."""
    uri = f"file:{path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        found = db.execute(
            "SELECT id, at, span, text, before, after, context, reason FROM correction"
            " WHERE stage = ? AND who = ? AND language = 'he' ORDER BY at, id",
            (STAGE, WHO),
        ).fetchall()
    return [dict(row) for row in found]


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--store", type=Path, default=Path.home() / ".targum" / "targum.db")
    parser.add_argument("--out", type=Path, default=None, help=f"default: <gold dir>/{NAME}")
    args = parser.parse_args()

    rows = read_store(args.store.expanduser())
    lines, left_out = build(rows)
    kinds = Counter(one["kind"] for line in lines for one in line["settled"])
    out = args.out or gold_path()
    write_atomic(out, "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines))
    print(f"{len(rows)} corrections in the store under stage={STAGE!r}, who={WHO!r}")
    print(f"{len(lines)} lines, {sum(kinds.values())} settled words: {dict(kinds)}")
    for why, count in left_out.items():
        print(f"  left out, {why}: {count}")
    print(f"written to {out} (private: never commit it)")


if __name__ == "__main__":
    main()
