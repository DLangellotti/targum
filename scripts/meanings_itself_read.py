"""Answers for a language owner's read of meanings in the language itself (#538).

Before a language's "Meanings of … words" row is offered (`accounts.MEANINGS_OPEN`), its
owner reads what the model writes: ling-he a hundred Hebrew answers, ling-fr, ling-ru and
ling-it fifty each. This asks for them the way a tap does, one word with its sentence,
through `gloss_one` and the in-language prompt, and prints a sheet to read.

**It spends.** About $0.002 a word on Sonnet 5, so a hundred is about $0.20; record it on
the card. It writes to a scratch cache, never the shared one, so an answer the read
rejects never reaches a reader. `--dry-run` prints the words and sentences and buys
nothing.

    op run --env-file op.env -- .venv/bin/python scripts/meanings_itself_read.py \\
        targum-out/library/<text> --language he --count 100 > he-read.tsv
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
from pathlib import Path


def main() -> int:
    from targum.annotate import gloss as gloss_module
    from targum.annotate.gloss import GLOSS_MODEL, AnthropicGlosses, gloss_one
    from targum.cache import Cache

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("texts", nargs="+", type=Path, help="built text folders")
    parser.add_argument("--language", default="he")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=538)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    picked: dict[str, str] = {}
    for folder in args.texts:
        annotation = json.loads((folder / "annotation.json").read_text(encoding="utf-8"))
        segments = json.loads((folder / "segments.json").read_text(encoding="utf-8"))
        text = {segment["id"]: segment["text"] for segment in segments["segments"]}
        for segment_id, tokens in annotation["tokens"].items():
            for token in tokens:
                form = token.get("glossed_as") or token.get("lemma") or ""
                if form and form not in picked and not token.get("entity"):
                    picked[form] = text.get(segment_id, "")
    forms = sorted(picked)
    random.Random(args.seed).shuffle(forms)
    forms = forms[: args.count]

    provider = AnthropicGlosses(GLOSS_MODEL)
    if not args.dry_run:
        usable, why = provider.available()
        if not usable:
            print(why, file=sys.stderr)
            return 1
    cache = Cache(Path(tempfile.mkdtemp(prefix="meanings-read-")))
    # A definition that writes the word itself is dropped before it is filed (#538); the
    # read names each one, so the sheet can count them rather than show an empty line.
    named: dict[str, str] = {}
    holds = gloss_module.names_itself

    def noted(form: str, definition: str, language: str) -> bool:
        if holds(form, definition, language):
            named[form] = definition
            return True
        return False

    gloss_module.names_itself = noted  # type: ignore[assignment]
    print("form\tsentence\tdefinition\tcitation\tplural\tdropped, names itself")
    for form in forms:
        sentence = " ".join(picked[form].split())
        if args.dry_run:
            print(f"{form}\t{sentence}\t\t\t")
            continue
        said = gloss_one(
            form, args.language, args.language, provider, cache=cache, context=sentence
        )
        print(
            f"{form}\t{sentence}\t{said.gloss if said else ''}"
            f"\t{said.citation if said else ''}\t{said.plural if said else ''}"
            f"\t{named.get(form, '')}"
        )
    if not args.dry_run:
        print(f"spent ${provider._provider.spent.cost():.4f}", file=sys.stderr)
        print(f"dropped as naming itself: {len(named)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
