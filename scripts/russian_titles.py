"""A Russian title and blurb for every catalogue text, drafted once for a person to read.

The front door sells in Russian. Behind it the shelf was entirely English, because
`english` was the only title a row had — see targum-internal#289. An entry now carries
`named` and `blurbs` by language code, and this fills the Russian.

**Translated from the English, not from the Hebrew.** The English title is already the
considered one — `english_titles.py` drafted it, a person reviewed it, and for a book of
the Bible or a known novel it is the standard name rather than a translation of anything.
Going back to the Hebrew would re-decide all of that in a second language and disagree
with the first. Where a row has no English yet, it is skipped: there is nothing to
translate and drafting from the Hebrew here would be the disagreement this avoids.

**Never overwrites.** A row whose Russian a person has written or corrected is left alone,
exactly as `english_titles.py` leaves an English title alone. `--redo` names the ones to
draft again.

**A dry run prints and writes nothing.** `--write` edits the catalogue in place, which is
the private file, so the review and the commit happen in `targum-internal`.
`--sample N` drafts only the first N and is what to run before the whole thing: the sample
is worth more before the money than after.

    set -a && . ./.env && set +a && .venv/bin/python scripts/russian_titles.py --sample 15
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum.catalogue import catalogue_path  # noqa: E402

#: Smaller than the English script's thirty: each row here carries a blurb in and a blurb
#: out, so a batch is several times the text even at the same count.
BATCH = 15

LANGUAGE = "ru"

INSTRUCTIONS = (
    "Below are texts from a Hebrew reading library, each with its title in English and a "
    "short blurb. Give the Russian for both, for a Russian speaker learning Hebrew.\n\n"
    "Rules. Use the established Russian name where the work has one — a book of the "
    "Bible, a known novel, an author's title — rather than translating the English. "
    "Keep a title to at most six words. Keep a blurb to the length of the English one, "
    "one or two sentences, plain and unexcited. No quotation marks around a title, no "
    "exclamation marks anywhere. A title that is a question keeps its question mark; no "
    "other title ends with punctuation.\n\n"
    'Answer with a JSON array of objects {"id": ..., "title": ..., "blurb": ...}, one per '
    "text, in the order given, and nothing else."
)


#: The Tanakh is named differently (decided 2026-09-17). The Synodal names a Russian
#: Bible uses — Бытие, Есфирь, Первая книга Царств — are the ones a Russian reader knows,
#: and they disagree with the Hebrew sitting beside them on the shelf: Samuel is filed
#: under "Kings", I Kings comes out *third*, and somebody hunting for שמואל א finds
#: nothing that looks like it. The transliterated names Israeli Russian-language Jewish
#: publishing uses match the Hebrew line exactly, which is the line this one is here to
#: help somebody read.
TANAKH = (
    "Below are books of the Hebrew Bible, each with its Hebrew title, its English title "
    "and a short blurb. Give the Russian for both, for a Russian-speaking oleh learning "
    "Hebrew.\n\n"
    "Name the book in two parts: the Hebrew name transliterated into Cyrillic, then the "
    "Synodal name in brackets after it — Берешит (Бытие), Шмот (Исход), Ваикра "
    "(Левит), Дварим (Второзаконие), Рут (Руфь), Эстер (Есфирь), Коѓелет "
    "(Екклесиаст), Теѓилим (Псалтирь), Мишлей (Притчи), Эйха (Плач Иеремии).\n\n"
    "The transliteration is what matches the Hebrew title on the page; the bracket is "
    "for a reader who knows the book by its Russian Bible name. A numbered book keeps "
    "the Hebrew numbering outside the bracket and the Synodal numbering inside it, so "
    "both readers find it: Шмуэль I (1-я Царств), Шмуэль II (2-я Царств), Мелахим I "
    "(3-я Царств), Мелахим II (4-я Царств), Диврей ѓа-ямим I (1-я Паралипоменон).\n\n"
    "Where the two names are the same word, give it once with no bracket — Амос, Йоэль. "
    "The blurb is ordinary Russian prose, never transliterated. Keep it to the length "
    "of the English one, plain and unexcited. No exclamation marks anywhere.\n\n"
    'Answer with a JSON array of objects {"id": ..., "title": ..., "blurb": ...}, one per '
    "text, in the order given, and nothing else."
)


def tidy(said: str) -> str:
    """What the brand allows. The same rule the English titles follow, and §4's: no
    exclamation marks anywhere in targum, so one arriving from the model is dropped
    rather than kept and caught later by `tests/test_brand.py`."""
    text = said.strip().strip("\"“”«»‘’'")
    text = text.replace("!", "").rstrip()
    asks = text.endswith("?")
    return " ".join(text.rstrip(".?…").split()) + ("?" if asks else "")


def tidy_blurb(said: str) -> str:
    """A blurb keeps its full stop — it is a sentence, not a title — and loses the rest."""
    text = " ".join(said.strip().strip('"“”«»').replace("!", ".").split())
    return text


def wanted(raw: dict[str, Any], redo: set[str]) -> bool:
    """Whether this row is one to draft.

    Skipped where there is no English to translate, and where a Russian is already there —
    somebody wrote or corrected that and a script does not get to disagree with it.
    """
    if raw["id"] in redo:
        return True
    if not str(raw.get("english", "")).strip():
        return False
    named = raw.get("named") or {}
    return not str(named.get(LANGUAGE, "")).strip()


def draft(
    entries: list[dict[str, Any]],
    ask: Any,
    after_batch: Any = None,
    instructions: str = INSTRUCTIONS,
) -> dict[str, dict[str, str]]:
    """The model, a batch at a time. `ask(prompt) -> str` is the one call.

    `after_batch(out)` is called when each batch lands, so a run that is interrupted has
    kept what it already paid for. The first version of this held all sixty-one batches
    in memory and wrote once at the end; it was killed two thirds of the way through and
    threw away every row *and* the spend behind them. A long run that buys things has to
    checkpoint.
    """
    out: dict[str, dict[str, str]] = {}
    for start in range(0, len(entries), BATCH):
        batch = entries[start : start + BATCH]
        given = [
            {
                "id": e["id"],
                "english": e.get("english", ""),
                "hebrew": e.get("title", ""),
                "author": e.get("author", ""),
                "blurb": e.get("blurb", ""),
            }
            for e in batch
        ]
        answer = ask(instructions + "\n\n" + json.dumps(given, ensure_ascii=False))
        found = re.search(r"\[.*\]", answer, re.S)
        try:
            rows = json.loads(found.group(0) if found else answer)
        except json.JSONDecodeError:
            print(f"  (a batch came back unreadable, skipped: {batch[0]['id']}…)", file=sys.stderr)
            continue
        here = {e["id"] for e in batch}
        for row in rows:
            if row.get("id") not in here:
                continue
            title = tidy(str(row.get("title", "")))
            blurb = tidy_blurb(str(row.get("blurb", "")))
            if title:
                out[row["id"]] = {"title": title, "blurb": blurb}
        if after_batch:
            after_batch(out)
    return out


def model_asker() -> Any:
    import anthropic

    from targum.serve import HOSTED_MODEL

    client = anthropic.Anthropic()

    def ask(prompt: str) -> str:
        reply = client.messages.create(
            model=HOSTED_MODEL,
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(getattr(part, "text", "") for part in reply.content)

    return ask


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--write", action="store_true", help="edit the catalogue file in place")
    parser.add_argument("--sample", type=int, default=0, metavar="N", help="draft only the first N")
    parser.add_argument(
        "--collections",
        action="store_true",
        help="the shelf's groups rather than its texts (targum-internal#289)",
    )
    parser.add_argument(
        "--tanakh",
        action="store_true",
        help="only the Tanakh, named the Israeli way; redraws whatever is already there",
    )
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
    if args.collections:
        # The groups the rows fold into. `draft` needs only an id, an English name, a
        # Hebrew one and a blurb, and a collection has all four — the `author` it also
        # asks for is simply absent, which is what it is for a group.
        entries = loaded.get("collections", []) if isinstance(loaded, dict) else []
        if not entries:
            print("no collections in the catalogue", file=sys.stderr)
            return 1

    if args.tanakh:
        # Every Tanakh row, whatever it already says: the point is to replace the Synodal
        # names, so "never overwrite" is exactly the rule being set aside here.
        todo = [raw for raw in entries if "tanakh" in (raw.get("tags") or [])]
    else:
        todo = [raw for raw in entries if wanted(raw, set(args.redo))]
    if args.sample:
        todo = todo[: args.sample]
    if not todo:
        print("nothing to draft", file=sys.stderr)
        return 0
    print(f"drafting {len(todo)} of {len(entries)}", file=sys.stderr)

    by_id = {raw["id"]: raw for raw in entries}
    indent = 2 if "\n  " in text[:200] else None
    said_already: set[str] = set()

    def keep(out: dict[str, dict[str, str]]) -> None:
        """Print what is new and, with --write, put the file on disk now."""
        for entry_id, said in out.items():
            if entry_id in said_already:
                continue
            said_already.add(entry_id)
            print(f"{entry_id}\t{by_id[entry_id].get('english', '')}\t{said['title']}", flush=True)
            print(f"\t\t{said['blurb']}", flush=True)
            if args.write:
                row = by_id[entry_id]
                row.setdefault("named", {})[LANGUAGE] = said["title"]
                if said["blurb"]:
                    row.setdefault("blurbs", {})[LANGUAGE] = said["blurb"]
        if args.write and out:
            # Atomically, so a kill between the two never leaves a half-written
            # catalogue where a whole one was.
            spare = path.with_suffix(".json.writing")
            spare.write_text(
                json.dumps(loaded, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8"
            )
            spare.replace(path)
            print(f"  … {len(said_already)} kept", file=sys.stderr, flush=True)

    drafted = draft(
        todo,
        model_asker(),
        after_batch=keep,
        instructions=TANAKH if args.tanakh else INSTRUCTIONS,
    )
    keep(drafted)
    if args.write:
        print(f"wrote {len(said_already)} Russian titles to {path}", file=sys.stderr)
    missing = [raw["id"] for raw in todo if raw["id"] not in drafted]
    if missing:
        print(f"no Russian came back for: {', '.join(missing[:10])}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
