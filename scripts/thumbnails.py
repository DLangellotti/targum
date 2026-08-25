"""The prompts for the library's cover images — one per text, and one per chapter that
has something to draw.

targum's provider draws no pictures, so this prints rather than generates: run the
prompts through whichever image model you use, and save what comes back as

    targum-out/thumbs/<entry id>.webp        (or .png / .jpg)

The library asks for `/thumb/<id>` and draws the text's own first letter until the file
is there, so a half-covered library looks deliberate rather than broken. `--missing`
prints only the texts that have no cover yet, which is what you want on the second run.

    uv run python scripts/thumbnails.py [--missing] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from targum.catalogue import (  # noqa: E402
    CATALOGUE,
    Entry,
    chapter_prompt,
    cover_prompt,
    names_something,
)

SUFFIXES = (".webp", ".png", ".jpg")


def has_cover(where: Path, entry_id: str) -> bool:
    return any((where / (entry_id + suffix)).is_file() for suffix in SUFFIXES)


def chapters_of(entry: Entry, out: Path) -> list[tuple[int, str]]:
    """The chapters of this text that name something, as (number, title).

    Read off the built text rather than the catalogue, because chapters are a product of
    how the text was ingested and sectioned. A text nobody has built yet has none to
    offer, which is correct: there is nothing to draw a chapter of until there are
    chapters.

    Most of them are excluded on purpose — see `catalogue.names_something`.
    """
    from targum.models import SegmentedDocument, read_artifact
    from targum.render.builder import split_sections

    for document in out.glob("*/*/document.json"):
        try:
            if json.loads(document.read_text(encoding="utf-8")).get("source") != entry.source:
                continue
        except (OSError, json.JSONDecodeError):
            continue
        segmented = read_artifact(SegmentedDocument, document.parent / "segments.json")
        if segmented is None:
            return []
        return [
            (section.number, section.title)
            for section in split_sections(segmented)
            if names_something(section.title or "", entry.title)
        ]
    return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("targum-out"))
    parser.add_argument("--missing", action="store_true", help="Only texts with no cover.")
    parser.add_argument("--json", action="store_true", help="As JSON, for a script to read.")
    parser.add_argument("--chapters", action="store_true", help="Chapters too, where titled.")
    parser.add_argument("--book", default="", help="One entry id.")
    args = parser.parse_args()

    where = args.out / "thumbs"
    jobs: list[dict[str, str]] = []
    for entry in CATALOGUE:
        if args.book and entry.id != args.book:
            continue
        if not (args.missing and has_cover(where, entry.id)):
            jobs.append({"id": entry.id, "of": entry.title, "prompt": cover_prompt(entry)})
        if not args.chapters:
            continue
        for number, title in chapters_of(entry, args.out):
            name = f"{entry.id}-c{number:03d}"
            if args.missing and has_cover(where, name):
                continue
            jobs.append(
                {
                    "id": name,
                    "of": f"{entry.title} — {title}",
                    "prompt": chapter_prompt(entry, title),
                }
            )

    if args.json:
        print(json.dumps(jobs, indent=1, ensure_ascii=False))
        return

    print(f"# {len(jobs)} image(s) to draw. Save each as {where}/<id>.webp\n")
    for job in jobs:
        print(f"## {job['id']}  ({job['of']})")
        print(job["prompt"])
        print()


if __name__ == "__main__":
    main()
