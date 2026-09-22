"""A Russian rendering for every sample line, drafted once for a person to read.

The public text page is the page a Russian searcher arrives at from a Russian search.
Its name and its blurb have answered in Russian since targum#362; the **sample** — the
opening lines, which are the only real reading on the page and the reason it is worth
indexing at all — was still English (targum-internal#188).

**Translated from the English, not from the Hebrew**, for the reason `russian_titles.py`
gives: the English rendering is a considered one, often a published translator's, and
going back to the Hebrew would re-decide it in a second language and disagree with the
first. The reader sees the Hebrew and one translation, and those two should say the same
thing.

**The licence was checked before anything was spent.** A Russian rendering of an English
translation is a derivative of it. All 303 sampled entries stand `free` (157) or `owed`
(146) — nothing closed, nothing unchecked — and the page already carries each one's
licence and credit in its provenance section, which is what `owed` owes.

**Never overwrites**, and a dry run prints and writes nothing. `--write` edits the
catalogue in place, which is the private file.

    .venv/bin/python scripts/russian_samples.py --sample 6
    set -a && . ./.env && set +a && .venv/bin/python scripts/russian_samples.py --write
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from targum.catalogue import catalogue_path  # noqa: E402
from targum.usage import Usage  # noqa: E402

#: Entries a batch. A sample is two or three lines of literary prose, so a batch is
#: bigger than the scenes script's four and smaller than the titles script's fifteen.
BATCH = 8

ASKED = """You are translating the opening lines of Hebrew texts into Russian, for
Russian-speaking learners of Hebrew.

Each text gives its title and a few lines. Every line has the Hebrew and the English
rendering that is published beside it.

Translate the English into Russian. The Hebrew is there so you can see what the line
really is; render the English, so that the Russian and the English say the same thing to
a reader comparing them with the Hebrew.

How to write it:
- Literary Russian where the English is literary, plain where it is plain. These are
  openings of novels, scripture, essays and news, and they do not all sound alike.
- Keep it the length of the English. This is shown beside the Hebrew, line for line.
- Keep proper names in their established Russian forms where there is one — Бытие for
  Genesis, Тель-Авив for Tel Aviv — and transliterate where there is not.
- Do not explain, gloss or add. A sample is read, not taught from.
- No exclamation marks unless the English has one.

Answer with JSON only: an object whose keys are the text ids, each holding a list of
Russian strings, one per line, in order, the same number as were given. Nothing else."""


def wanted(raw: dict[str, Any], language: str) -> bool:
    """Whether this entry's sample still needs drafting: any line without the language."""
    return any(not (line.get("said") or {}).get(language) for line in raw)


def asking(batch: list[tuple[str, str, list[dict[str, Any]]]]) -> str:
    return json.dumps(
        {
            eid: {
                "title": title,
                "lines": [{"hebrew": line["source"], "english": line["target"]} for line in lines],
            }
            for eid, title, lines in batch
        },
        ensure_ascii=False,
    )


def drafted(client: Any, batch: list[Any], model: str, usage: Usage) -> dict[str, Any]:
    reply = client.messages.create(
        model=model,
        max_tokens=8000,
        system=ASKED,
        messages=[{"role": "user", "content": asking(batch)}],
    )
    usage.add(model, reply.usage.input_tokens, reply.usage.output_tokens)
    said = "".join(getattr(block, "text", "") for block in reply.content).strip()
    if said.startswith("```"):
        said = said.split("\n", 1)[1].rsplit("```", 1)[0]
    return dict(json.loads(said))


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--write", action="store_true", help="edit the catalogue in place")
    parser.add_argument("--language", default="ru")
    parser.add_argument("--sample", type=int, default=0, help="draft only the first N entries")
    parser.add_argument("--catalogue", type=Path)
    args = parser.parse_args()

    path = args.catalogue or catalogue_path()
    if path is None:
        sys.exit("no catalogue file")
    body = json.loads(path.read_text(encoding="utf-8"))
    samples = body.get("samples") or {}
    names = {e["id"]: (e.get("english") or e.get("title") or e["id"]) for e in body["entries"]}

    todo = [
        (eid, names.get(eid, eid), lines)
        for eid, lines in samples.items()
        if wanted(lines, args.language)
    ]
    if args.sample:
        todo = todo[: args.sample]
    lines = sum(len(one[2]) for one in todo)
    words = sum(len(line["target"].split()) for _, _, ls in todo for line in ls)
    print(f"{len(samples)} entries carry a sample; {len(todo)} need {args.language}")
    print(f"{lines} lines, about {words} English words")
    if not todo:
        return
    if not args.write:
        print("\nNothing was called. Add --write to draft and edit the catalogue.")
        return

    import anthropic

    from targum.serve import HOSTED_MODEL

    client = anthropic.Anthropic()
    usage = Usage()
    backup = path.with_suffix(f".{date.today().isoformat()}.before-samples-{args.language}.json")
    shutil.copy2(path, backup)
    done = 0

    for start in range(0, len(todo), BATCH):
        batch = todo[start : start + BATCH]
        try:
            said = drafted(client, batch, HOSTED_MODEL, usage)
        except Exception as error:  # noqa: BLE001 - one bad batch is not the run
            print(f"  ! batch at {start} failed: {error}", file=sys.stderr)
            continue
        for eid, _title, held in batch:
            got = said.get(eid)
            if not isinstance(got, list) or len(got) != len(held):
                # Lines that do not line up would land under the wrong Hebrew, which is
                # worse than no Russian at all.
                print(
                    f"  ! {eid}: {len(got or [])} for {len(held)} lines, skipped", file=sys.stderr
                )
                continue
            for line, russian in zip(held, got, strict=True):
                line.setdefault("said", {})[args.language] = str(russian)
            done += 1
        # Written as each batch lands, not at the end: a run that dies halfway keeps
        # what it paid for.
        path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  {done}/{len(todo)} drafted, ${usage.cost():.2f} so far", flush=True)

    print(f"\n{done} samples drafted. This run cost ${usage.cost():.2f}.")
    print(f"The catalogue as it was is at {backup}.")


if __name__ == "__main__":
    main()
