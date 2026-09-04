"""Which built texts are behind the annotator that would read them now.

    python scripts/shelf_versions.py
    python scripts/shelf_versions.py --out /var/lib/targum/targums --list

A change to what a word is reaches a text already on the shelf only through
`rebuild --words`, which re-annotates a text whose recorded annotator name differs from
the one this machine would use. That comparison is the whole mechanism, and until now
nothing said out loud how many texts were on the wrong side of it.

On 2026-09-04 the answer here was 411 of 418 — every text in `library/`, all 411 behind on
`register/1 -> register/2` and 98 of them also on `tanakh/1 -> tanakh/2`. Those are merged
and closed fixes that had never reached a built page (targum-internal#208, #207). Nobody
had done anything wrong; there was simply no line anywhere that printed the number, so a
shelf drifting two versions behind looked exactly like a shelf that was fine.

Loads no model and writes nothing. `for_source` picks the lemmatizer by where a text came
from and its name is a string, so the current name costs a hundredth of a second — the
same comparison `rebuild` makes, made out loud and without the rebuild.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


def current_name(source: str) -> str | None:
    """What this machine would call the annotator for a text from `source`.

    `None` where it cannot be worked out — a box without the scripture data answers
    differently from one with it, by design, and saying so is better than guessing.
    """
    from targum.annotate import Annotator, biblical, lemma

    try:
        return Annotator(
            lemmatizer=lemma.for_source(source, auto_download=False),
            bands=biblical.for_source(source),
        ).name
    except Exception:
        return None


#: A versioned piece of an annotator name: `register/2`, `oshb/2`, `tanakh/1`. The name is
#: a `+`-joined pile of these mixed with unversioned model identifiers, and only these can
#: be compared as older-or-newer.
VERSIONED = re.compile(r"(?:^|\+)([a-z_]+)/(\d+)(?=\+|$)")


def versions(name: str) -> dict[str, str]:
    """The versioned components of an annotator name, by component."""
    return {piece: number for piece, number in VERSIONED.findall(name)}


def compare(have: str, want: str) -> list[tuple[str, str, str]]:
    """Which versioned components the built text is behind on.

    Compared component by component rather than as whole strings, and only over the
    components both names carry. An `Annotator` built here for the comparison does not
    know what dictionary provider or vocalizer the build used, so its name is missing
    `anthropic/…/dictionary-3` and `phonikud/2` — pieces that say nothing about whether
    the *words* are current. Comparing the strings whole reports every text on the shelf
    as behind, which is how this was caught.
    """
    mine, theirs = versions(have), versions(want)
    return [
        (piece, mine[piece], theirs[piece])
        for piece in sorted(theirs)
        if piece in mine and mine[piece] != theirs[piece]
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=Path("targum-out"))
    parser.add_argument("--list", action="store_true", help="Name every text that is behind.")
    parser.add_argument(
        "--home", default="", help="Only this home — library, weekly, p3 — rather than all."
    )
    args = parser.parse_args()

    behind: list[tuple[str, str, str]] = []
    current = 0
    unknown = 0
    by_home: Counter[str] = Counter()
    stale: Counter[str] = Counter()
    # Cached because a shelf is mostly a few sources repeated, and the name is a pure
    # function of the source.
    names: dict[str, str | None] = {}

    for path in sorted(args.out.rglob("annotation.json")):
        if args.home and path.parent.parent.name != args.home:
            continue
        annotation = json.loads(path.read_text())
        if annotation.get("language", "").split("-")[0].lower() != "he":
            continue
        document = path.parent / "document.json"
        if not document.is_file():
            unknown += 1
            continue
        source = json.loads(document.read_text()).get("source", "")
        if source not in names:
            names[source] = current_name(source)
        want = names[source]
        have = annotation.get("annotator", "")
        if want is None:
            unknown += 1
            continue
        older = compare(have, want)
        if not older:
            current += 1
            continue
        behind.append((str(path.parent), have, want))
        by_home[path.parent.parent.name] += 1
        for piece, mine, theirs in older:
            stale[f"{piece}/{mine} -> {piece}/{theirs}"] += 1

    total = current + len(behind) + unknown
    print(f"Hebrew texts on the shelf : {total}")
    print(f"  on the current annotator: {current}")
    print(f"  behind it               : {len(behind)}")
    if unknown:
        print(f"  could not be worked out : {unknown}")
    if stale:
        print("\nwhich component is behind:")
        for moved, count in stale.most_common():
            print(f"  {count:4d}  {moved}")
    if by_home:
        print("\nbehind, by home:")
        for home, count in by_home.most_common():
            print(f"  {count:4d}  {home}")
    if args.list:
        print("\nbehind:")
        for folder, have, want in behind:
            moved = ", ".join(f"{p}/{a} -> {p}/{b}" for p, a, b in compare(have, want))
            print(f"  {folder}\n    {moved}")
    if behind:
        print(f"\n`targum rebuild --words` would re-annotate {len(behind)} of them.")


if __name__ == "__main__":
    main()
