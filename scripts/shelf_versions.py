"""Which built texts are behind the code that would build them now, at both stages.

    python scripts/shelf_versions.py
    python scripts/shelf_versions.py --out /var/lib/targum/targums --list

Two versions decide whether a text on the shelf is current, and a change to either
reaches it only by doing that stage again.

**The annotator**, through `rebuild --words`, which re-reads a text whose recorded
annotator name differs from the one this machine would use. On 2026-09-04 that was 411 of
418 here — every text in `library/` — all behind on `register/1 -> register/2` and 98 also
on `tanakh/1 -> tanakh/2` (targum-internal#207, #208).

**The ingester**, which nothing re-runs at all. This is the sharper one, because a rule
that changes what a *block* is cannot be recovered by re-annotating: the annotator never
sees the text again. On the same day, 228 of 646 documents were behind, including every
one of the 162 Sefaria texts against `sefaria/5` — whose own comment reads *"the Aramaic
of Daniel and Ezra says so"*. So Daniel and Ezra carried no Aramaic tags, and their
Aramaic was still being read as Hebrew (targum-internal#195).

Both were merged, closed and believed shipped. Nobody had done anything wrong; there was
simply no line anywhere that printed either number, so a shelf two versions behind looked
exactly like a shelf that was fine.

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


def split_version(name: str) -> tuple[str, int] | None:
    """`sefaria/5` into `("sefaria", 5)`, and `sefaria/siddur/1` into `("sefaria/siddur", 1)`.

    The version is the last segment and everything before it names the ingester, because
    two of them share a first segment and keying on that alone makes one stand in for the
    other.
    """
    head, _, tail = name.rpartition("/")
    return (head, int(tail)) if head and tail.isdigit() else None


def current_ingesters() -> dict[str, int]:
    """The newest version of every ingester this build carries, by name.

    Read off the classes rather than listed here, so an ingester added tomorrow is
    checked tomorrow without anybody remembering to add it.
    """
    import importlib
    import inspect
    import pkgutil

    from targum import ingest as ingest_module
    from targum.ingest import fetch as fetch_module

    modules = [ingest_module, fetch_module]
    for package in (ingest_module, fetch_module):
        for _, name, _ in pkgutil.iter_modules(package.__path__):
            try:
                modules.append(importlib.import_module(f"{package.__name__}.{name}"))
            except Exception:  # noqa: BLE001 - an ingester whose extra is absent is not fatal
                continue

    newest: dict[str, int] = {}
    for module in modules:
        for _, obj in inspect.getmembers(module, inspect.isclass):
            for attribute in ("name", "plain_name"):
                value = getattr(obj, attribute, None)
                if not isinstance(value, str):
                    continue
                if (split := split_version(value)) is None:
                    continue
                where, number = split
                newest[where] = max(newest.get(where, 0), number)
    return newest


def ingest_report(out: Path, home: str) -> None:
    """How many built texts were ingested by a version older than the current one.

    A separate question from the annotator's, and one nothing else asks. An ingest rule
    reaches a text already on the shelf only through a re-ingest, and a rule that changes
    what a *block* is — which language it is in, whether a footnote is inlined — cannot be
    recovered by re-annotating, because the annotator never sees the text again.

    On 2026-09-04 every one of the 162 Sefaria-ingested texts here was behind `sefaria/5`,
    whose own comment is "the Aramaic of Daniel and Ezra says so" — so Daniel and Ezra
    carried no Aramaic tags at all and their Aramaic was still being read as Hebrew
    (targum-internal#195).
    """
    newest = current_ingesters()
    behind: Counter[str] = Counter()
    homes: Counter[str] = Counter()
    seen: Counter[str] = Counter()
    for path in sorted(out.rglob("document.json")):
        if home and path.parent.parent.name != home:
            continue
        ingester = str(json.loads(path.read_text()).get("ingester") or "")
        if (split := split_version(ingester)) is None:
            continue
        where, number = split
        seen[where] += 1
        if number < newest.get(where, number):
            behind[f"{ingester} -> {where}/{newest[where]}"] += 1
            homes[path.parent.parent.name] += 1
    total = sum(behind.values())
    print(f"\ningested by an older version : {total} of {sum(seen.values())}")
    for moved, count in behind.most_common():
        print(f"  {count:4d}  {moved}")
    if homes:
        print("  by home:", dict(homes.most_common()))
    if total:
        print("  a re-ingest is free: a document is keyed by its text, which has not changed.")


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
    ingest_report(args.out, args.home)


if __name__ == "__main__":
    main()
