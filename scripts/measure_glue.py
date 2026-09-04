"""How much glue is actually left in the shelf (targum-internal#151).

`ingest/spacing.py` repairs words that arrived with the space between them missing, and
its rules only fire where the seam is provable. Everything they decline stays glued, is
looked up as one word, and finds nothing. #151 proposes letting
`dicta-il/dictabert-char-spacefix` propose a seam where the rules cannot see one, with
the rules still deciding — and asks, before any of that is built, how many words are in
that population at all.

This counts them. The population is the issue's own definition: a token `lexicon.known()`
rejects that splits somewhere into two halves it accepts. `known()` is the generous
question, so a token it rejects is one no amount of peeling reaches a word through, and
two halves it accepts is the weakest evidence of a seam there is. Anything outside that
set is either already a word or has nowhere to come apart, and a space-fixer has nothing
to say about it.

It reads the built shelf rather than the sources, which is the right place to look:
`unglue` runs at ingest, so what is on disk is the residue the rules left behind.

Nothing here loads a model. It reads `annotation.json`, asks the lexicon, and prints.
"""

from __future__ import annotations

import argparse
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from targum import lexicon
from targum.ingest.spacing import _MIN_PART, _MIN_WHOLE, _bare, _spellable


def seams(bare: str) -> list[int]:
    """Every place this comes apart into two words the lexicon knows at all.

    The same scan `_cuts` calls a rival, and deliberately the low bar: `known()` rather
    than `strength()`. A seam here is a candidate, not a repair.
    """
    found = []
    for n in range(_MIN_PART, len(bare) - _MIN_PART + 1):
        left, right = bare[:n], bare[n:]
        if not _spellable(left) or not _spellable(right):
            continue
        if lexicon.known(left) and lexicon.known(right):
            found.append(n)
    return found


def _pointed(token: str) -> bool:
    """Whether the token carries vowel points, which says which shelf it came off."""
    return any(unicodedata.category(c) == "Mn" for c in token)


def _read(out: Path) -> tuple[Counter[str], dict[str, set[str]], int]:
    """Every Hebrew surface form on the shelf, counted, with the texts it appears in."""
    surfaces: Counter[str] = Counter()
    where: dict[str, set[str]] = defaultdict(set)
    texts = 0
    for path in sorted(out.rglob("annotation.json")):
        document = json.loads(path.read_text())
        if document.get("language", "").split("-")[0].lower() != "he":
            continue
        texts += 1
        for tokens in document.get("tokens", {}).values():
            for token in tokens:
                surface = token.get("surface") or ""
                if surface:
                    surfaces[surface] += 1
                    where[surface].add(path.parent.name)
    return surfaces, where, texts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=Path("targum-out"))
    parser.add_argument("--limit", type=int, default=40, help="How many to list per group.")
    args = parser.parse_args()

    if not lexicon.available():
        raise SystemExit("no lexicon on this box: install the difficulty extra")

    surfaces, where, texts = _read(args.out)
    running = sum(surfaces.values())
    print(f"Hebrew texts read : {texts}")
    print(f"distinct surfaces : {len(surfaces):,}")
    print(f"running tokens    : {running:,}")

    # Split by the rule's own length gate. Below it the lexical rule never looks, so those
    # tokens are in the issue's population and out of the rules' reach — a separate
    # question from the one the rules decline having considered.
    above: dict[str, tuple[int, list[int]]] = {}
    below: dict[str, tuple[int, list[int]]] = {}
    for surface, count in surfaces.items():
        bare = _bare(surface)
        if len(bare) < 2 * _MIN_PART or lexicon.known(bare):
            continue
        found = seams(bare)
        if found:
            (above if len(bare) >= _MIN_WHOLE else below)[surface] = (count, found)

    groups = (
        (f"at or above the rule's {_MIN_WHOLE}-letter gate", above),
        ("below that gate, where the lexical rule never looks", below),
    )
    for label, group in groups:
        tokens = sum(count for count, _ in group.values())
        single = sum(1 for _, found in group.values() if len(found) == 1)
        share = tokens / max(running, 1) * 100
        print(f"\n=== {label} ===")
        print(f"  distinct types  : {len(group):,}")
        print(f"  running tokens  : {tokens:,} ({share:.4f}% of the shelf)")
        print(f"  one seam only   : {single}   more than one: {len(group) - single}")
        print(f"  carrying nikkud : {sum(1 for surface in group if _pointed(surface))}")
        ranked = sorted(group.items(), key=lambda item: (-item[1][0], item[0]))
        for surface, (count, found) in ranked[: args.limit]:
            bare = _bare(surface)
            cuts = " | ".join(f"{bare[:n]}·{bare[n:]}" for n in found[:3])
            print(f"    {count:5d}  {surface:24s} {cuts}   [{sorted(where[surface])[0]}]")


if __name__ == "__main__":
    main()
