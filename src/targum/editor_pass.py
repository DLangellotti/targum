"""The file a paid editor hands back, read into correction rows (targum-internal#354).

An editor works where editors work — a spreadsheet, or a file of lines — and hands back
what they changed. This reads that file; `Store.editor_pass` writes it down. Nothing
here applies a correction to anything: the point of the door is that the judgements are
kept as rows, which a rebuild cannot overwrite.

Two shapes, told apart by the extension:

- **CSV** (`.csv`), with a header row.
- **JSON lines** (`.jsonl`), one object per line.

The columns, in either:

- `line` (or `span`): which line the judgement was made on, e.g. `market-01 t3`.
- `before`: what stood. `after`: what should stand; empty means "this is wrong and I have
  nothing to put there".
- `note` (or `reason`): why, in a few words.
- `term`: the word the row is about. It may be left out, and then it is `before` with
  its points taken off, which is how the scene audit filed its rows. A gloss is the one
  stage where that would be wrong, because there `before` is an English meaning and not
  the word, so a gloss row must name its term.
- `context`, `text`, `language` (default `he`), `target` (default `en`): optional.

A file with a bad row is refused whole, with every bad line named, so a pass is never
half in the store.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .dialogue.checks import bare
from .errors import TargumError

#: What a column may be called, and what it is called in the store.
ALIASES = {
    "line": "span",
    "span": "span",
    "id": "span",
    "note": "reason",
    "reason": "reason",
    "before": "before",
    "after": "after",
    "term": "term",
    "word": "term",
    "context": "context",
    "text": "text",
    "language": "language",
    "target": "target",
}


def _records(path: Path) -> list[tuple[int, dict[str, object]]]:
    """Each row with the line of the file it came from, for naming a bad one."""
    suffix = path.suffix.lower()
    body = path.read_text(encoding="utf-8-sig")
    if suffix == ".csv":
        reader = csv.DictReader(body.splitlines())
        return [(i, dict(row)) for i, row in enumerate(reader, start=2)]
    if suffix in (".jsonl", ".ndjson"):
        out: list[tuple[int, dict[str, object]]] = []
        for i, line in enumerate(body.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                one = json.loads(line)
            except json.JSONDecodeError as error:
                raise TargumError(
                    f"{path.name} line {i} is not JSON: {error.msg}.",
                    "One object per line, each with at least before and after.",
                ) from error
            if not isinstance(one, dict):
                raise TargumError(
                    f"{path.name} line {i} is not an object.",
                    'Write each line as {"line": ..., "before": ..., "after": ...}.',
                )
            out.append((i, one))
        return out
    raise TargumError(
        f"{path.name} is neither .csv nor .jsonl.",
        "Save the editor's pass as CSV with a header row, or as JSON lines.",
    )


def read_editor_pass(path: Path, stage: str) -> list[dict[str, str]]:
    """The rows of an editor's file, checked, in the store's own column names."""
    rows: list[dict[str, str]] = []
    wrong: list[str] = []
    for number, record in _records(path):
        row = {"language": "he", "target": "en"}
        for column, value in record.items():
            name = ALIASES.get(str(column or "").strip().lower())
            if name is not None and value is not None:
                row[name] = str(value).strip()
        if not any(row.get(k) for k in ("before", "after", "term")):
            continue  # an empty line in a spreadsheet is not a judgement
        if not row.get("before") and not row.get("after"):
            wrong.append(f"line {number}: neither before nor after")
            continue
        if not row.get("term"):
            if stage == "gloss":
                wrong.append(f"line {number}: a gloss row must name its term")
                continue
            row["term"] = bare(row.get("before") or row.get("after") or "")
        rows.append(row)
    if wrong:
        raise TargumError(
            f"{path.name} has {len(wrong)} row(s) that cannot be kept, so none were: "
            + "; ".join(wrong[:10])
            + ("; …" if len(wrong) > 10 else ""),
            "Fix those lines and run it again; the rest of the file is fine.",
        )
    return rows
