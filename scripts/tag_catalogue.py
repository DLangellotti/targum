"""Put a subject tag on the catalogue rows that plainly have one (targum-internal#311).

The arrival asks a reader to pick three subjects from nineteen. Measured on 2026-09-17,
17 of the 19 had nothing behind them: `catalogue.Tag` existed and its own comment said
"Nothing filters on this today", with 622 of 920 rows carrying no tag at all.

**Three of the nineteen need no tag.** `everyday`, `stories` and `poetry` are matched by
`Kind` — dialogue, story/novel/play, poetry — which every row already carries. That is
305 of the 622, and they are left alone here.

**This tags by rule, never by guess, and buys nothing.** Every rule below is a whole
publisher or author whose subject is not in question; a row that does not match one is
left untagged rather than filed on a hunch, because a wrong tag is worse than no tag —
it puts a text behind a door where a reader will not think to look for it, and nothing
ever tells them it is there. What is left over is the honest size of the job a person or
a model would have to do.

    .venv/bin/python scripts/tag_catalogue.py          # dry run, prints the counts
    .venv/bin/python scripts/tag_catalogue.py --write  # edits the catalogue in place

The catalogue is private, so the review and the commit happen in `targum-internal`.
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum.catalogue import catalogue_path  # noqa: E402

#: Whole channels and authors whose subject is not in question. The count beside each is
#: what it matched on 2026-09-17.
BY_AUTHOR: dict[str, tuple[str, ...]] = {
    # Physics, maths, biology. `Tag.science` names these as its whole content today. (20)
    "Khan Academy Hebrew": ("science",),
    # Channels that teach the language itself, which is what `Tag.language` is for — the
    # docstring says "Hebrew itself" because Hebrew was the only shelf when it was
    # written; the Russian and Italian shelves have the same thing on them. (200)
    "Russian with Dasha": ("language",),
    "mmmItalian – with Angela": ("language",),
    "Kalinka Cat": ("language",),
    "The Russian Flow: Learn Russian with Lёsha": ("language",),
    "Tania Klimova - Russian Podcast": ("language",),
    "Positive Russian": ("language",),
    "Europass Italian Language School": ("language",),
    # Technology for non-profits — the subject is the tooling. (18)
    "Теплица социальных технологий": ("technology",),
    # A history club, reading history. (10)
    "Исторический клуб + фильмы с Б. Г. Кипнисом": ("history",),
    # Paintings, painters and looking at them. (6)
    "Artesplorando": ("art",),
    # A teaching hospital. (3)
    "Policlinico di Milano": ("health",),
    # Science and technology news, in as many words. (3)
    "ВЕТЕР [Новости Науки и Технологий]": ("science", "technology"),
    # The Darwin Museum, for children. (2)
    "Дарвиновский музей Дети": ("science",),
    # Wikipedia, Commons and Wikisource, explained. (3)
    "Wikimedia Italia": ("technology",),
    # Getting a job and running a business, for disabled adults: CVs, application forms,
    # calling an employer, planning. `Tag.business` is "work, money, what things cost". (7)
    "Инклюзивное образование": ("business",),
}

#: Whole publications, by the address their rows come from. Teplitsa's site is the same
#: source as its channel, which `BY_AUTHOR` already files: data leaks, blocked sites,
#: hacked sites, the sovereign internet, staying anonymous. The rows carry individual
#: bylines rather than the outlet's name, so the author is no use and the address is.
BY_SOURCE: dict[str, tuple[str, ...]] = {
    "https://te-st.org/": ("technology",),
}

#: Two founding documents, filed as what a reader who came for history came for. Neither
#: is history *writing*, and that is the point: `Tag.history` is "what happened, and
#: writing about it", and a declaration of independence is the first of those.
DECLARATIONS = ("Israeli Declaration of Independence", "United States Declaration of Independence")

#: Ben-Yehuda's newspaper articles. Two of them are about how Hebrew is pronounced, which
#: is `Tag.language` and nothing else; the rest are the polemics that argue the country
#: into existence, which is the nearest thing the shelf has to `Tag.history`. Matched on
#: the English title because that is the considered one.
BEN_YEHUDA = "אליעזר בן־יהודה"
ABOUT_THE_LANGUAGE = ("The Pronunciation of Hebrew", "The Correct Pronunciation")

#: The revival essayists — Ahad Ha'am, Berdyczewski, Herzl. `Tag.philosophy` names them
#: outright: "Ideas, argued. The revival essayists are here once they are filed."
ESSAY_KIND = "essay"


def tags_for(row: dict[str, Any]) -> tuple[str, ...]:
    """The tags this row plainly has, or () where it is not plain."""
    author = str(row.get("author") or "").strip()
    english = str(row.get("english") or "").strip()
    if found := BY_AUTHOR.get(author):
        return found
    source = str(row.get("source") or "")
    for prefix, found in BY_SOURCE.items():
        if source.startswith(prefix):
            return found
    if english in DECLARATIONS:
        return ("history",)
    if author == BEN_YEHUDA:
        return ("language",) if english in ABOUT_THE_LANGUAGE else ("history",)
    if row.get("kind") == ESSAY_KIND and row.get("language") == "he":
        return ("philosophy",)
    return ()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--write", action="store_true", help="edit the catalogue in place")
    args = parser.parse_args(argv)

    path = catalogue_path()
    if path is None:
        print("no catalogue file", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8")
    loaded = json.loads(text)
    entries = loaded["entries"] if isinstance(loaded, dict) else loaded

    # Never overwrites: a row somebody tagged by hand is not a script's to disagree with.
    untagged = [row for row in entries if not (row.get("tags") or [])]
    given: collections.Counter[str] = collections.Counter()
    touched = 0
    for row in untagged:
        found = tags_for(row)
        if not found:
            continue
        touched += 1
        given.update(found)
        if args.write:
            row["tags"] = list(found)

    by_kind = collections.Counter(
        str(row.get("kind") or "(none)") for row in untagged if not tags_for(row)
    )
    print(f"untagged before: {len(untagged)} of {len(entries)}", file=sys.stderr)
    print(f"tagged by rule:  {touched}", file=sys.stderr)
    for tag, count in given.most_common():
        print(f"    {count:4}  {tag}", file=sys.stderr)
    print(f"left untagged:   {len(untagged) - touched}", file=sys.stderr)
    for kind, count in by_kind.most_common():
        matched = (
            " (matched by Kind, needs no tag)"
            if kind in {"dialogue", "story", "novel", "play", "poetry"}
            else ""
        )
        print(f"    {count:4}  {kind}{matched}", file=sys.stderr)

    if args.write:
        spare = path.with_suffix(".json.writing")
        indent = 2 if "\n  " in text[:200] else None
        spare.write_text(
            json.dumps(loaded, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8"
        )
        spare.replace(path)
        print(f"wrote {touched} rows to {path}", file=sys.stderr)
    else:
        print("dry run; nothing written. --write to edit the catalogue.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
