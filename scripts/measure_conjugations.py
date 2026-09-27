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
  settled by reading    several, and no binyan; every form the word is written in on
                        the page is read as the same one of them by targum's own
                        tagging elsewhere on the shelf (#307, `paradigms.READINGS`)
  refused: conflict     both decide and disagree, so neither is taken
  refused: read         one of the first three decided, and a form of the same word
    otherwise           on the page is read as one of the other verbs (#307)
  still ambiguous       several, and nothing settles it — the card draws no table
  no candidate          the source has never heard of this verb

The first five are coverage. The last three are the honest gaps, and `Table.of` answers
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

from targum.annotate.paradigms import (  # noqa: E402
    Table,
    bare,
    binyan_of,
    table,
    written_form,
)

#: The buckets that mean the reader gets a table.
COVERED = (
    "unique",
    "settled by binyan",
    "settled by pointing",
    "settled, both agree",
    "settled by reading",
)


def measure(
    out: Path, language: str = "he"
) -> tuple[collections.Counter[str], dict[str, set[str]], int]:
    """Every verb token under `out`, bucketed — and the distinct lemmas in each bucket.

    **Only documents in `language`.** The table is Hebrew, and a directory can hold more
    than Hebrew: run this over one with Italian or Russian in it and every foreign verb
    lands in "no candidate", which reads as terrible Hebrew coverage rather than as the
    wrong question. Measured 2026-09-21 over a mixed video directory, the answer came
    back 5.3% and the commonest "missing Hebrew verbs" were `essere`, `avere` and `fare`.
    `annotation.json` records its own language, so this asks it rather than guessing.
    """
    verbs = table()
    tally: collections.Counter[str] = collections.Counter()
    lemmas: dict[str, set[str]] = collections.defaultdict(set)
    skipped = 0

    for path in sorted(out.glob("**/annotation.json")):
        try:
            found = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not str(found.get("language") or "").startswith(language):
            skipped += 1
            continue
        verbs_here = [
            token
            for tokens in (found.get("tokens") or {}).values()
            for token in tokens
            if isinstance(token, dict) and token.get("pos") == "VERB" and token.get("lemma")
        ]
        # Every form each word is written in, as the builder gathers them for a page.
        # A page is a section and this is the whole document, so a word here has more
        # forms to agree on than it has on any one page: a lower bound, not the number.
        written: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
        for token in verbs_here:
            written[(str(token["lemma"]), str(token.get("headword") or ""))].append(
                written_form(str(token.get("surface") or ""), token.get("built"))
            )
        for token in verbs_here:
            lemma = str(token["lemma"])
            where = bucket(
                verbs,
                lemma,
                str(token.get("surface") or ""),
                token.get("binyan"),
                tuple(written[(lemma, str(token.get("headword") or ""))]),
            )
            tally[where] += 1
            lemmas[where].add(lemma)
    return tally, lemmas, skipped


def bucket(
    verbs: Table, lemma: str, surface: str, binyan: object, written: tuple[str, ...] = ()
) -> str:
    """Which bucket one verb token falls in. The same questions `Table.of` asks, kept
    apart here so the answer says *why* rather than only yes or no."""
    candidates = verbs.by_form.get(bare(lemma)) or ()
    written = tuple(written)
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
        if pointed[0] != built[0]:
            return "refused: conflict"
        chosen, where = pointed[0], "settled, both agree"
    elif len(built) == 1:
        chosen, where = built[0], "settled by binyan"
    elif len(pointed) == 1:
        chosen, where = pointed[0], "settled by pointing"
    elif not binyan and written and verbs._by_reading(candidates, written) is not None:
        return "settled by reading"
    else:
        return "still ambiguous"
    if verbs._read_otherwise(candidates, chosen, written):
        return "refused: read otherwise"
    return where


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path.home() / ".targum" / "targums",
        help="Where the built texts are. Default: ~/.targum/targums",
    )
    parser.add_argument(
        "--language",
        default="he",
        help="Only documents in this language; the table is Hebrew's. Default: he",
    )
    args = parser.parse_args()
    if not args.out.is_dir():
        sys.exit(f"nothing built at {args.out}")

    tally, lemmas, skipped = measure(args.out, args.language)
    total = sum(tally.values())
    if not total:
        sys.exit(f"no {args.language} verbs under {args.out}")

    print(f"{total:,} {args.language} verb tokens under {args.out}")
    if skipped:
        print(f"  ({skipped:,} documents in another language left out)")
    print()
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
