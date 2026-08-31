"""An English title for every catalogue text, drafted once for a person to review.

Every title and byline in the catalogue is Hebrew script. For a reader who cannot yet
read it, the library is a list of things they cannot tell apart; the `english` field on
an entry is what the pages show under the Hebrew. This drafts that field, three ways, and
never overwrites one that is already filled in:

1. A scene (`kind == dialogue`) already has its English beside its Hebrew in the dialogue
   file; failing the file, the slug in its id ("scene-01-nice-to-meet-you") is it.
2. A book of the Tanakh is named in its byline ("Ketuvim · Ruth"), last segment.
3. Everything else is drafted by the model, thirty at a time, from the Hebrew title, the
   byline and the blurb: the standard English title where one exists, a plain translation
   otherwise. Six words at most, no quotation marks, no trailing punctuation, and never an
   exclamation mark — the brand does not use them, and `tests/test_brand.py` would refuse.

A dry run prints what it would write, one line per entry, with the rule that produced it.
`--write` edits the catalogue file in place, in the order it was in, and prints only the
rows the model drafted — those are the ones a person has to read. The file it edits is
the private catalogue, so the review and the commit happen in `targum-internal`.

    set -a && . ./.env && set +a && .venv/bin/python scripts/english_titles.py [--write]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum.catalogue import Kind, Tag, catalogue_path  # noqa: E402

BATCH = 30
MOST_WORDS = 6

INSTRUCTIONS = (
    "For each Hebrew text below, give its title in English. Use the standard English title "
    "where the work has one (a book of the Bible, a known novel or essay); otherwise a plain "
    "translation of the Hebrew title, guided by the blurb. At most six words. No quotation "
    "marks, no exclamation marks, no commentary; a title that is a question ends with a "
    "question mark and no other title ends with punctuation. Answer with a JSON "
    'array of objects {"id": ..., "english": ...}, one per text, in the order given, and '
    "nothing else."
)


def from_scene(raw: dict[str, Any]) -> str:
    """Rule 1: the dialogue file's own English, or the slug in the id."""
    identifier = str(raw.get("source", "")).split(":", 1)[-1]
    try:
        from targum.dialogue.index import load

        english = load(identifier).english.strip()
        if english:
            return english
    except Exception:
        pass
    slug = re.sub(r"^scene-\d+-", "", str(raw["id"]))
    words = slug.replace("-", " ").strip()
    return words[:1].upper() + words[1:]


def from_byline(raw: dict[str, Any]) -> str:
    """Rule 2: "Ketuvim · Ruth" → "Ruth"."""
    return str(raw.get("author", "")).split(" · ")[-1].strip()


def tidy(english: str) -> str:
    """What the brand allows a title to be. Never cut short here: a title chopped at six
    words ("The Woman Who Walked Thousands of") is worse than a long one, so length is
    the model's to fix — see `shorten` — and a long title that survives that stays whole."""
    text = english.strip().strip("\"“”‘’'")
    # A question keeps its mark — "How was the weekend?" — and nothing else keeps any.
    text = text.replace("!", "").rstrip()
    asks = text.endswith("?")
    text = text.rstrip(".?…")
    return " ".join(text.split()) + ("?" if asks else "")


def too_long(english: str) -> bool:
    return len(english.split()) > MOST_WORDS


SHORTEN = (
    "Each of these English titles is too long. Give a shorter title of at most six words "
    "that still reads as a complete title — a headline may be rephrased, never cut off "
    "mid-phrase. Same rules: no quotation marks, no exclamation marks, a question mark only "
    'on a question. Answer with a JSON array of objects {"id": ..., "english": ...}, in the order '
    "given, and nothing else."
)


def draft(entries: list[dict[str, Any]], ask: Any) -> dict[str, str]:
    """Rule 3: the model, a batch at a time. `ask(prompt) -> str` is the one call."""
    out: dict[str, str] = {}
    for start in range(0, len(entries), BATCH):
        batch = entries[start : start + BATCH]
        given = [
            {
                "id": e["id"],
                "title": e["title"],
                "author": e.get("author", ""),
                "blurb": e.get("blurb", ""),
            }
            for e in batch
        ]
        answer = ask(INSTRUCTIONS + "\n\n" + json.dumps(given, ensure_ascii=False))
        found = re.search(r"\[.*\]", answer, re.S)
        rows = json.loads(found.group(0) if found else answer)
        wanted = {e["id"] for e in batch}
        for row in rows:
            if row.get("id") in wanted and str(row.get("english", "")).strip():
                out[row["id"]] = tidy(str(row["english"]))
    return shorten(out, entries, ask)


def shorten(drafted: dict[str, str], entries: list[dict[str, Any]], ask: Any) -> dict[str, str]:
    """A second ask for whatever came back longer than six words, once."""
    long = [e for e in entries if too_long(drafted.get(e["id"], ""))]
    if not long:
        return drafted
    given = [
        {
            "id": e["id"],
            "title": e["title"],
            "english": drafted[e["id"]],
            "blurb": e.get("blurb", ""),
        }
        for e in long
    ]
    answer = ask(SHORTEN + "\n\n" + json.dumps(given, ensure_ascii=False))
    found = re.search(r"\[.*\]", answer, re.S)
    for row in json.loads(found.group(0) if found else answer):
        english = tidy(str(row.get("english", "")))
        if row.get("id") in drafted and english and not too_long(english):
            drafted[row["id"]] = english
    return drafted


def rule_for(raw: dict[str, Any]) -> str:
    if raw.get("kind") == Kind.dialogue.value:
        return "scene"
    if Tag.tanakh.value in raw.get("tags", []):
        return "byline"
    return "model"


def plan(entries: list[dict[str, Any]], ask: Any) -> list[tuple[str, str, str]]:
    """(id, rule, english) for every entry that has no English yet."""
    todo = [e for e in entries if not str(e.get("english", "")).strip()]
    drafted = draft([e for e in todo if rule_for(e) == "model"], ask) if ask else {}
    out: list[tuple[str, str, str]] = []
    for raw in todo:
        rule = rule_for(raw)
        if rule == "scene":
            english = from_scene(raw)
        elif rule == "byline":
            english = from_byline(raw)
        else:
            english = drafted.get(raw["id"], "")
        out.append((raw["id"], rule, english))
    return out


def model_asker() -> Any:
    import anthropic

    from targum.serve import HOSTED_MODEL

    client = anthropic.Anthropic()

    def ask(prompt: str) -> str:
        reply = client.messages.create(
            model=HOSTED_MODEL,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(getattr(part, "text", "") for part in reply.content)

    return ask


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--write", action="store_true", help="edit the catalogue file in place")
    parser.add_argument("--no-model", action="store_true", help="rules 1 and 2 only")
    parser.add_argument(
        "--redo", nargs="*", default=[], metavar="ID", help="draft these again, whatever they say"
    )
    args = parser.parse_args(argv)

    path = catalogue_path()
    if path is None:
        print("no catalogue file", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8")
    loaded = json.loads(text)
    entries = loaded["entries"] if isinstance(loaded, dict) else loaded
    for raw in entries:
        if raw["id"] in set(args.redo):
            raw["english"] = ""

    planned = plan(entries, None if args.no_model else model_asker())
    by_id = {raw["id"]: raw for raw in entries}
    for entry_id, rule, english in planned:
        if args.write and english:
            by_id[entry_id]["english"] = english
        if not args.write or rule == "model":
            print(f"{entry_id}\t{rule}\t{english}")

    if args.write:
        indent = 2 if "\n  " in text[:200] else None
        path.write_text(
            json.dumps(loaded, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8"
        )
        print(f"wrote {sum(1 for _, _, e in planned if e)} titles to {path}", file=sys.stderr)
    missing = [entry_id for entry_id, _, english in planned if not english]
    if missing:
        print(f"still empty: {', '.join(missing)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
