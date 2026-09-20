"""How many of the shelf's verbs get a conjugation table, and where the rest go.

The front door promises "the full table for any verb". targum-internal#307 decided that
coverage rises to meet the copy rather than the copy coming down, and that the number is
*measured* rather than assumed — so this is the measurement, run over whatever is built.

It reads `annotation.json` beside each built text: no model, no network, no annotator,
and nothing bought. Every verb token is put in one bucket:

  unique                the bare spelling names one verb, and that is the table
  settled by binyan     several verbs spell it the same; the binyan targum worked out
                        for this word matches exactly one of them (#307)
  settled by pointing   several; the pointed form the reader saw belongs to one
  settled, both agree   both signals decide and name the same verb
  refused: conflict     both decide and disagree, so neither is taken
  still ambiguous       several, and nothing settles it — the card draws no table
  no candidate          the source has never heard of this verb

The first four are coverage. The last three are the honest gaps, and `Table.of` answers
None for all of them, because a wrong conjugation table is worse than none: the reader
has no way to tell.

    .venv/bin/python scripts/measure_conjugations.py --out ~/.targum/targums
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum.annotate.paradigms import Table, bare, binyan_of, table  # noqa: E402

#: The buckets that mean the reader gets a table.
COVERED = ("unique", "settled by binyan", "settled by pointing", "settled, both agree")


def measure(out: Path) -> tuple[collections.Counter[str], dict[str, set[str]]]:
    """Every verb token under `out`, bucketed — and the distinct lemmas in each bucket."""
    verbs = table()
    tally: collections.Counter[str] = collections.Counter()
    lemmas: dict[str, set[str]] = collections.defaultdict(set)

    for path in sorted(out.glob("**/annotation.json")):
        try:
            found = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for tokens in (found.get("tokens") or {}).values():
            for token in tokens:
                if not isinstance(token, dict) or token.get("pos") != "VERB":
                    continue
                lemma = str(token.get("lemma") or "")
                if not lemma:
                    continue
                where = bucket(verbs, lemma, str(token.get("surface") or ""), token.get("binyan"))
                tally[where] += 1
                lemmas[where].add(lemma)
    return tally, lemmas


def bucket(verbs: Table, lemma: str, surface: str, binyan: object) -> str:
    """Which bucket one verb token falls in. The same three questions `Table.of` asks,
    kept apart here so the answer says *why* rather than only yes or no."""
    candidates = verbs.by_form.get(bare(lemma)) or ()
    if not candidates:
        return "no candidate"
    if len(candidates) == 1:
        return "unique"
    known = verbs.verbs
    pointed = [
        lid
        for lid in candidates
        if surface
        and (verb := known.get(lid))
        and (verb.lemma == surface or any(form.written == surface for form in verb.forms))
    ]
    built = [lid for lid in candidates if binyan and binyan_of(known[lid].lemma) == str(binyan)]
    if len(pointed) == 1 and len(built) == 1:
        return "settled, both agree" if pointed[0] == built[0] else "refused: conflict"
    if len(built) == 1:
        return "settled by binyan"
    if len(pointed) == 1:
        return "settled by pointing"
    return "still ambiguous"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path.home() / ".targum" / "targums",
        help="Where the built texts are. Default: ~/.targum/targums",
    )
    args = parser.parse_args()
    if not args.out.is_dir():
        sys.exit(f"nothing built at {args.out}")

    tally, lemmas = measure(args.out)
    total = sum(tally.values())
    if not total:
        sys.exit(f"no annotated verbs under {args.out}")

    print(f"{total:,} verb tokens under {args.out}\n")
    for where, count in tally.most_common():
        mark = "+" if where in COVERED else " "
        print(
            f"  {mark} {where:22} {count:7,} {count / total:6.1%}   {len(lemmas[where]):5} lemmas"
        )

    covered = sum(tally[where] for where in COVERED)
    distinct = set().union(*(lemmas[where] for where in COVERED)) if covered else set()
    every = set().union(*lemmas.values())
    print(f"\n  coverage {covered:,}/{total:,} = {covered / total:.1%} of tokens")
    print(
        f"           {len(distinct):,}/{len(every):,} = {len(distinct) / len(every):.1%} of lemmas"
    )


if __name__ == "__main__":
    main()
