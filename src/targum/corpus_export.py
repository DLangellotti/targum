"""`targum corpus export`: the corpus ledger as a dataset (targum-internal#162, slice 3).

One JSONL file per table (texts, pointings, annotations and tokens, and since slice 4
translations and their aligned pairs), filtered on one export bit, and a datasheet
generated from the same rows (acceptance criteria 3 and 4). Two exports, and neither
reads the other's bit (David, 2026-10-08):

- **`exportable`**, the commercial one: public domain, CC0, CC BY, CC BY-SA and targum's
  own writing.
- **`research`**: the same, plus CC BY-NC and CC BY-NC-SA.

What never leaves, whichever is asked: a reader's private import, a text with no licence
string, anything ND (all three already read 0 on both bits, and each is refused again
here, so a wrong bit alone cannot export one), and any account id. The homes a private
text is held in live in `text_homes`, which is never read here, and no exported column
names a reader.

Only current rows go out: the value each key holds now, not its history. A unit row
(a pointing, a token) goes out when its head row does; the head carries the bit.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import ledger as ledger_module

#: The two exports, by the column each one filters on.
KINDS = ("exportable", "research")

#: What each export admits, as the datasheet says it.
RULES = {
    "exportable": "public domain, CC0, CC BY, CC BY-SA, targum's own writing",
    "research": "public domain, CC0, CC BY, CC BY-SA, targum's own writing, CC BY-NC, CC BY-NC-SA",
}

#: The datasheet's own format, so a consumer can tell one shape from the next.
DATASHEET_VERSION = 1


def _allow(db: sqlite3.Connection, bit: str) -> None:
    """Fill the temporary `allowed` table with the texts that may leave under one bit.

    A text must be current, marked public and held in no reader's home, its row must
    carry the bit, *and* the rule asked again now of its licence must give it: a bit
    written wrong, or by an older rule, is not enough on its own to export anything.
    """
    from .licensing import export_terms

    db.execute("CREATE TEMP TABLE allowed (document_hash TEXT PRIMARY KEY)")
    rows = db.execute(
        f"SELECT document_hash, licence, source FROM texts WHERE superseded_at IS NULL"  # noqa: S608
        f" AND {bit} = 1 AND private = 0"
        # And held in no reader's home: the private bucket, asked a second way.
        " AND document_hash NOT IN (SELECT document_hash FROM text_homes)"
    ).fetchall()
    db.executemany(
        "INSERT INTO allowed (document_hash) VALUES (?)",
        [
            (hash_,)
            for hash_, licence, source in rows
            if getattr(export_terms(licence), bit) and not _names_a_home(source)
        ],
    )
    # A rendering leaves when its text does and its own licence, asked again, allows it.
    db.execute("CREATE TEMP TABLE allowed_translations (id INTEGER PRIMARY KEY)")
    renderings = db.execute(
        f"SELECT id, licence FROM translations WHERE superseded_at IS NULL"  # noqa: S608
        f" AND {bit} = 1 AND document_hash IN (SELECT document_hash FROM allowed)"
    ).fetchall()
    db.executemany(
        "INSERT INTO allowed_translations (id) VALUES (?)",
        [(row_id,) for row_id, licence in renderings if getattr(export_terms(licence), bit)],
    )


def _names_a_home(source: str) -> bool:
    """Whether a source is a path through a reader's home (`p<id>`), which would carry an
    account id into the export. A public text is a link or a fetcher's name; one that is
    a path into somebody's home is not exported at all."""
    return any(ledger_module.is_home(part) for part in re.split(r"[/\\]", source))


#: The texts `_allow` let through.
_TEXTS = "SELECT document_hash FROM allowed"


def _queries(bit: str) -> dict[str, str]:
    """Each exported table's rows under one bit, by the file it goes to.

    Every head row must carry the bit itself *and* belong to a text that may leave, so
    neither a stale stamp on a row nor a wrong text row exports anything alone.
    """
    texts = _TEXTS
    heads = {
        "vocalizations": (
            "id, cache_key, document_hash, language, tool, tool_version, schema_version, written_at"
        ),
        "annotations": (
            "id, cache_key, document_hash, language, tool, tool_version, schema_version,"
            " head_json, written_at"
        ),
    }
    wanted = {
        head: (
            f"SELECT {columns} FROM {head} WHERE superseded_at IS NULL"  # noqa: S608
            f" AND {bit} = 1 AND document_hash IN ({texts})"
        )
        for head, columns in heads.items()
    }
    return {
        "texts": (
            "SELECT document_hash, source, licence, reader_publishable, tool AS ingester,"  # noqa: S608
            f" schema_version, written_at FROM texts WHERE superseded_at IS NULL"
            f" AND document_hash IN ({texts}) ORDER BY id"
        ),
        "vocalizations": wanted["vocalizations"] + " ORDER BY id",
        "pointings": (
            "SELECT vocalization_id, segment_id, pointed, segment_ord, machine_ord,"  # noqa: S608
            " rejected_ord FROM pointings WHERE vocalization_id IN"
            f" (SELECT id FROM ({wanted['vocalizations']}))"
            " ORDER BY vocalization_id, segment_id"
        ),
        "annotations": wanted["annotations"] + " ORDER BY id",
        "translations": (
            "SELECT id, cache_key, document_hash, source_language, target_language, kind,"
            " tool, tool_version, style, licence, schema_version, head_json, written_at"
            " FROM translations WHERE id IN (SELECT id FROM allowed_translations) ORDER BY id"
        ),
        "pairs": (
            "SELECT translation_id, segment_id, ord, source, target, confidence, coarse"
            " FROM pairs WHERE translation_id IN (SELECT id FROM allowed_translations)"
            " ORDER BY translation_id, ord"
        ),
        "tokens": (
            "SELECT annotation_id, segment_id, segment_ord, ord, form, lemma, pos, features,"  # noqa: S608
            " band, token_json FROM tokens WHERE annotation_id IN"
            f" (SELECT id FROM ({wanted['annotations']}))"
            " ORDER BY annotation_id, segment_ord, ord"
        ),
    }


def _rows(db: sqlite3.Connection, query: str) -> Iterator[dict[str, Any]]:
    cursor = db.execute(query)
    names = [column[0] for column in cursor.description]
    for row in cursor:
        yield dict(zip(names, row, strict=True))


def export(file: Path, to: Path, kind: str) -> dict[str, Any]:
    """Write one export of the ledger at `file` into the empty folder `to`.

    Returns the datasheet, which is also written beside the tables as `datasheet.json`
    and `DATASHEET.md`. Raises ValueError for an unknown kind, a folder that is not
    empty, or a ledger file that is not there.
    """
    if kind not in KINDS:
        raise ValueError(f"no export called {kind!r}: one of {', '.join(KINDS)}")
    if not file.is_file():
        raise ValueError(f"there is no ledger at {file}")
    if to.exists() and any(to.iterdir()):
        raise ValueError(f"{to} is not empty")
    to.mkdir(parents=True, exist_ok=True)
    # Opened through `Ledger`, so an older file is brought up to the schema first.
    with closing(ledger_module.Ledger(file)._connect()) as db:
        _allow(db, kind)
        counts: dict[str, int] = {}
        for table, query in _queries(kind).items():
            written = 0
            with (to / f"{table}.jsonl").open("w", encoding="utf-8") as out:
                for row in _rows(db, query):
                    out.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                    written += 1
            counts[table] = written
        sheet = _datasheet(db, kind, counts)
    (to / "datasheet.json").write_text(
        json.dumps(sheet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (to / "DATASHEET.md").write_text(_markdown(sheet), encoding="utf-8")
    return sheet


def _datasheet(db: sqlite3.Connection, kind: str, counts: dict[str, int]) -> dict[str, Any]:
    """What is in the export, read from the same rows: sources, licences, tools, counts."""
    queries = _queries(kind)
    texts = list(_rows(db, queries["texts"]))
    tools: list[dict[str, Any]] = []
    for head in ("vocalizations", "annotations", "translations"):
        seen = Counter((row["tool"], row["tool_version"]) for row in _rows(db, queries[head]))
        tools += [
            {"table": head, "tool": tool, "tool_version": version, "rows": rows}
            for (tool, version), rows in sorted(seen.items(), key=lambda item: str(item[0]))
        ]
    schema = db.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()
    return {
        "datasheet_version": DATASHEET_VERSION,
        "export": kind,
        "made": datetime.now(UTC).isoformat(timespec="seconds"),
        "ledger_schema": int(schema[0]) if schema else None,
        "rows": counts,
        "licences": dict(sorted(Counter(text["licence"] for text in texts).items())),
        "translation_licences": dict(
            sorted(Counter(row["licence"] for row in _rows(db, queries["translations"])).items())
        ),
        "sources": sorted(
            ({"source": text["source"], "licence": text["licence"]} for text in texts),
            key=lambda one: (one["source"], one["licence"]),
        ),
        "tools": tools,
        "rule": RULES[kind],
    }


def _markdown(sheet: dict[str, Any]) -> str:
    lines = [
        f"# targum corpus: {sheet['export']} export",
        "",
        f"Made {sheet['made']} from corpus ledger schema {sheet['ledger_schema']}.",
        f"Admits: {sheet['rule']}. Never: ND, no licence string, a reader's private import.",
        "Only the current value of each row; no history.",
        "",
        "## Rows",
        "",
        *(f"- `{table}`: {rows}" for table, rows in sheet["rows"].items()),
        "",
        "## Licences",
        "",
        *(f"- {licence}: {texts} texts" for licence, texts in sheet["licences"].items()),
        *(
            f"- {licence}: {rows} translations"
            for licence, rows in sheet["translation_licences"].items()
        ),
        "",
        "## Tools",
        "",
        *(
            f"- `{one['table']}` · {one['tool']}"
            + (f" ({one['tool_version']})" if one["tool_version"] else "")
            + f": {one['rows']}"
            for one in sheet["tools"]
        ),
        "",
        "## Sources",
        "",
        *(f"- {one['source']} — {one['licence']}" for one in sheet["sources"]),
        "",
    ]
    return "\n".join(lines)
