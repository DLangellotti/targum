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
from collections import Counter
from pathlib import Path

# The comparison itself lives in the package, because `targum preflight` runs it every
# deploy and this script is the same survey with the detail on it (targum-internal#208).
from targum.annotate.versions import compare, survey


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

    shelf = survey(args.out, args.home)
    by_home: Counter[str] = Counter(
        Path(folder).parent.name for folder, _have, _want in shelf.behind
    )

    print(f"Hebrew texts on the shelf : {shelf.total}")
    print(f"  on the current annotator: {shelf.current}")
    print(f"  behind it               : {len(shelf.behind)}")
    if shelf.unknown:
        print(f"  could not be worked out : {shelf.unknown}")
    if moved := shelf.moved():
        print("\nwhich component is behind:")
        for where, count in moved.items():
            print(f"  {count:4d}  {where}")
    if by_home:
        print("\nbehind, by home:")
        for home, count in by_home.most_common():
            print(f"  {count:4d}  {home}")
    if args.list:
        print("\nbehind:")
        for folder, have, want in shelf.behind:
            where = ", ".join(f"{p}/{a} -> {p}/{b}" for p, a, b in compare(have, want))
            print(f"  {folder}\n    {where}")
    if shelf.behind:
        print(f"\n`targum rebuild --words` would re-annotate {len(shelf.behind)} of them.")
    ingest_report(args.out, args.home)


if __name__ == "__main__":
    main()
