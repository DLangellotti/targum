"""Copy Lingua Libre's Hebrew word recordings into the cache, and say how many words they cover.

targum-internal#610 (David, 2026-10-31; design.md §12, "A word is said by a person where one
recorded it"). The work is `targum.voices`; this is its door on the laptop.

- Reads every file in `Category:Lingua_Libre_pronunciation-heb` off the Commons API, fifty
  a request and one request a second, each file's licence and speaker off its own page.
  CC0 and CC BY-SA pass; anything else is counted and left.
- Writes the manifest beside the files, in `targum.voices.folder()` (the cache, which is
  private and never in the repository).
- `--download` copies each file not already there: Commons' MP3 copy, about a second of
  speech each. Run it once the PR that serves them has merged.
- `--coverage` says how many of the top lemmas of the language tables have a recording:
  exact pointed match, bare with one candidate, bare with several, none. It reads the
  corpus ledger `TARGUM_LEDGER` names, or `--ledger`.

    .venv/bin/python scripts/fetch_lingualibre.py --coverage
    .venv/bin/python scripts/fetch_lingualibre.py --download --coverage
    .venv/bin/python scripts/fetch_lingualibre.py --coverage --offline   # the manifest kept

Shipping is a copy of the folder to the box's cache (`/var/lib/targum/cache/voices/`),
owned by `targum`; nothing restarts, because the manifest is read again when it changes.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from targum import voices
from targum.tables.store import Store
from targum.tables.words import WORDS


def top_lemmas(ledger: Path, limit: int) -> list[str]:
    """The commonest weighed lemmas over every register, as the tables count them."""
    store = Store(ledger)
    totals: dict[str, int] = {}
    for register in store.registers(WORDS):
        for key, n in store.top(WORDS, register, limit=10**7):
            totals[key] = totals.get(key, 0) + n
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return [key for key, _ in ranked[:limit]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--language", default="he", choices=sorted(voices.CATEGORIES))
    parser.add_argument("--download", action="store_true", help="Copy the files too.")
    parser.add_argument("--offline", action="store_true", help="Read the manifest kept.")
    parser.add_argument("--coverage", action="store_true", help="Match the top lemmas.")
    parser.add_argument("--top", type=int, default=5000)
    parser.add_argument("--ledger", type=Path, default=None)
    args = parser.parse_args()

    if args.offline:
        manifest = voices.load(args.language)
        if manifest is None:
            print(f"No manifest at {voices.manifest_path(args.language)}.", file=sys.stderr)
            return 1
    else:
        manifest = voices.fetch(args.language, download=args.download)
    licences: dict[str, int] = {}
    for one in manifest.recordings:
        licences[one.licence] = licences.get(one.licence, 0) + 1
    index = voices.Index(manifest.recordings)
    print(f"{len(manifest.recordings)} recordings, {len(index.by_pointed)} distinct words")
    print("by licence:", licences)
    kept = [one.path(args.language) for one in manifest.recordings]
    on_disk = [path for path in kept if path.is_file()]
    size = sum(path.stat().st_size for path in on_disk)
    print(f"{len(on_disk)} files on disk, {size / 1e6:.1f} MB, in {voices.folder(args.language)}")

    if args.coverage:
        raw = os.environ.get("TARGUM_LEDGER", "").strip()
        ledger = args.ledger or (
            Path(raw).expanduser() if raw else Path.home() / ".targum" / "corpus.db"
        )
        lemmas = top_lemmas(ledger, args.top)
        if not lemmas:
            print(f"No lemmas in {ledger}.", file=sys.stderr)
            return 1
        found = voices.coverage(index, lemmas)
        matched = found["pointed"] + found["bare"]
        print(
            f"top {len(lemmas)} lemmas: {matched} have a recording "
            f"({100 * matched / len(lemmas):.1f}%) — pointed {found['pointed']}, "
            f"bare with one candidate {found['bare']}, bare with several "
            f"{found['ambiguous']}, none {found['none']}"
        )
        for band in (100, 500, 1000, 2000):
            if band < len(lemmas):
                part = voices.coverage(index, lemmas[:band])
                share = part["pointed"] + part["bare"]
                print(f"  top {band}: {share} ({100 * share / band:.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
