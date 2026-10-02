"""File the olim texts under "Life in Israel" (targum-internal#393).

Two things on the shelf were made for olim and are filed under nothing that says so:

- **Scenes 101–200**, the Easy dialogues on everyday life in Israel (#386). They are on
  the dialogue shelf and have **no catalogue row at all**, and a scene with no row is
  not in the Library: scenes 01–100 are rows `scene-NN-slug` with source
  `dialogue:<id>`, written by hand once and never by code. This writes the missing rows
  in that same shape, tagged `israel`.
- **The 48 curated clips** from #382's batches 1–3, which are catalogue rows already.
  This adds `israel` to their tags and keeps the tags they have.

The catalogue is private data, so this runs on the machine that holds it and touches
nothing in the repository. Every row goes through `promote.merge_into_catalogue`, the one
door the catalogue grows through, so a new row is dated the day it arrives and an old
row keeps its date. It prints what it would do unless given `--write`, and running it
twice changes nothing the second time.

    PYTHONPATH=src TARGUM_DIALOGUE_DIR=… python scripts/file_life_in_israel.py
    PYTHONPATH=src TARGUM_DIALOGUE_DIR=… python scripts/file_life_in_israel.py --write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from targum import catalogue as catalogue_module  # noqa: E402
from targum.catalogue import Tag  # noqa: E402
from targum.dialogue import index as dialogue_index  # noqa: E402
from targum.dialogue.models import Dialogue  # noqa: E402

TAG = Tag.israel.value

#: The olim scenes, by the number their id starts with.
SCENES = range(101, 201)

#: The clips curated for olim in #382's batches 1–3 (2026-09-30), by catalogue id.
CLIPS = (
    "lifney-kulam-disability-protest mediko-weight-loss-injections hevratit-gan-not-a-storeroom "
    "maagalei-shema-clalit-2700 kochav-finansi-high-salary avramov-bituach-leumi-website "
    "kochav-finansi-long-term-care mediko-before-flying-abroad mediko-over-the-counter "
    "tibi-elderly-queues avramov-bituach-leumi-service mediko-polio-vaccines "
    "mediko-medicine-shortage kesher-hmo-treatments kochav-finansi-why-pay-adviser "
    "mediko-shared-carrier-gene hevratit-access-to-healthcare hevratit-working-in-the-family "
    "kesher-bituach-leumi-rights mediko-flight-medical-tips ono-interview-chemistry "
    "lilach-robotics-club maagalei-shema-sign-interpreting ono-interview-body-language "
    "lobby99-duplicate-health-insurance tel-hai-school-kiryat-shmona hevratit-danger-school "
    "lobby99-bank-securities-fees ono-salary-expectations yad-sarah-free-pharmacy "
    "interior-ministry-business-licensing mofet-salary-simulation "
    "kochav-finansi-pension-exemption-2025 maagalei-shema-doctor-visit "
    "hevratit-why-people-stay-poor meshutaf-joint-school-tel-aviv "
    "kochav-finansi-kids-dental-costs hevratit-children-behind-bars hevratit-hidden-committee "
    "eli-cohen-bank-account levjob-interview-strengths-weaknesses ono-interview-simulation "
    "eliad-cohen-interview-weaknesses mediko-back-to-routine mediko-pharmacy-privacy "
    "hevratit-the-real-wage eli-cohen-double-your-savings "
    "mediko-virtual-cardiac-catheterization"
).split()


def scene_row(scene: Dialogue) -> dict[str, Any]:
    """A catalogue row for a scene, in the shape scenes 01–100 were written in."""
    return {
        "id": f"scene-{scene.id}",
        "title": scene.title,
        "author": "targum",
        "language": "he",
        "source": f"dialogue:{scene.id}",
        "blurb": scene.gloss,
        "english": scene.english,
        "words": scene.words,
        "tags": [TAG],
        "translations": [],
        "kind": "dialogue",
        "register": "modern",
        "licence": "targum",
        "named": dict(scene.named),
        "blurbs": dict(scene.glossed),
    }


def olim_scenes() -> list[Dialogue]:
    found = []
    for path in sorted(dialogue_index.root().glob("*.json")):
        number = path.stem.split("-", 1)[0]
        if number.isdigit() and int(number) in SCENES:
            found.append(dialogue_index.load(path.stem))
    return found


def plan(rows: list[dict[str, Any]], scenes: list[Dialogue]) -> list[dict[str, Any]]:
    """The rows to merge: a new one per missing scene, and the clips with the tag added."""
    by_id = {str(row.get("id")): row for row in rows}
    out: list[dict[str, Any]] = []
    for scene in scenes:
        row = scene_row(scene)
        held = by_id.get(row["id"])
        if held is None:
            out.append(row)
        elif TAG not in (held.get("tags") or []):
            out.append({"id": row["id"], "tags": [*held.get("tags", []), TAG]})
    for clip in CLIPS:
        held = by_id.get(clip)
        if held is None:
            print(f"  ! {clip} is not in the catalogue; skipped", file=sys.stderr)
            continue
        if TAG not in (held.get("tags") or []):
            out.append({"id": clip, "tags": [*held.get("tags", []), TAG]})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true", help="merge into the catalogue")
    args = parser.parse_args()

    import json

    from targum.promote import merge_into_catalogue

    path = catalogue_module.catalogue_path()
    if path is None:
        raise SystemExit("No catalogue: set TARGUM_CATALOGUE or put one at ~/.targum.")
    rows = json.loads(path.read_text(encoding="utf-8")).get("entries") or []
    scenes = olim_scenes()
    todo = plan(rows, scenes)
    new = sum(1 for row in todo if "source" in row)
    print(f"{len(scenes)} olim scenes on the shelf at {dialogue_index.root()}")
    print(f"{new} scene rows to add, {len(todo) - new} rows to tag {TAG!r}")
    if not args.write:
        print("Nothing written. Add --write to merge into", path)
        return
    for row in todo:
        merge_into_catalogue(row)
    print(f"Merged {len(todo)} rows into {path}.")


if __name__ == "__main__":
    main()
