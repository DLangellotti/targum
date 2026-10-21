"""Add Metsudah Rashi (Hebrew and English, CC-BY) to the five Torah rows' renderings
(targum-internal#414, gap 6).

    python3 scripts/file_metsudah_rashi.py                       # says what it would add
    python3 scripts/file_metsudah_rashi.py --write               # backs up, then writes
    python3 scripts/file_metsudah_rashi.py --write --to copy.json  # writes a copy instead

The catalogue is private data, so this runs on the machine that holds it
(~/.targum/catalogue.json) and ships to the box on the next deploy, where each Torah row's
rebuild then fetches Rashi beside it. Running it twice adds nothing the second time.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path

CATALOGUE = Path.home() / ".targum" / "catalogue.json"
BOOKS = ("Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy")
NAME = "Rashi Chumash, Metsudah Publications, 2009"


def renderings(book: str) -> list[dict[str, str]]:
    return [
        {
            "name": NAME,
            "source": f"sefaria:Rashi on {book}",
            "note": "Rashi's commentary, comment by comment beside the verse.",
            "publisher": "Metsudah Publications",
            "licence": "CC-BY",
            "licence_url": f"https://www.sefaria.org/api/v3/texts/Rashi_on_{book}?version=hebrew|{NAME}",
        },
        {
            "name": NAME,
            "source": f"sefaria:en:Rashi on {book}",
            "note": "Rashi in English, the same comments in the same order.",
            "publisher": "Metsudah Publications",
            "licence": "CC-BY",
            "licence_url": f"https://www.sefaria.org/api/v3/texts/Rashi_on_{book}?version=english|{NAME}",
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--to", type=Path, default=None)
    args = parser.parse_args()
    data = json.loads(CATALOGUE.read_text(encoding="utf-8"))
    added = 0
    for row in data["entries"]:
        source = str(row.get("source", ""))
        book = source.removeprefix("sefaria:")
        if source.count(":") != 1 or book not in BOOKS:
            continue
        have = {r.get("source") for r in row.get("translations", [])}
        for one in renderings(book):
            if one["source"] in have:
                print(f"  {row['id']}: already has {one['source']}")
                continue
            print(f"  {row['id']}: + {one['source']}")
            row.setdefault("translations", []).append(one)
            added += 1
    if not args.write or not added:
        print(f"{added} renderings would be added" if added else "nothing to add")
        return
    target = args.to or CATALOGUE
    if target == CATALOGUE:
        backup = CATALOGUE.with_name(f"catalogue.before-metsudah-rashi-{date.today()}.json")
        shutil.copy2(CATALOGUE, backup)
        print(f"backed up to {backup}")
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{added} renderings added to {target}")


if __name__ == "__main__":
    main()
