"""Put newly voiced audio into the scene files, with the spans the voicer measured.

`voice_scenes.py` writes `<id>.mp3` and `<id>.spans.json` and touches nothing else. This
is the other half: it takes a folder of scene files, sets each voiced scene's `audio` and
every turn's `start` and `end` from those spans, and writes a folder that is the whole
shelf — every JSON and every mp3 — because `ship-audio.sh` syncs with `--delete` and a
folder with holes in it deletes recordings from the box.

It is not `dialogue/write.py`, which rebuilds the shelf from the corpus. That finds the
seams by listening for silences, and on per-turn audio a pause inside a line can be longer
than the gap between two: on 81-the-army-friend it found 44 silences where 29 were
needed. These spans are known because the voicer put the gaps there. It also leaves every
other field alone, so whatever the files carry beyond the corpus — the Russian, say —
arrives intact.

A scene that was not voiced again keeps its old audio from `--old`, and **only if what is
said did not change**: Gemini ignores the points, so old audio still says a re-pointed
line, but it says the old word for a re-worded one. A yod or vav dropped or added *inside*
a word is spelling (נִיפָּגֵשׁ and נִפָּגֵשׁ are one sound) and the old audio stands; at the
end of a word it is not (תֵּלְכִי is not תֵּלֵךְ). A scene whose words changed is refused by
name — or, with `--hold`, taken whole from `--old`, text and audio both, so the box keeps
saying and showing the same thing until its audio exists. Of the 2026-09-22 audit's 40
re-lettered lines, 14 were spelling and 26 were words.

    python scripts/place_scene_voices.py --scenes corrected/ --voiced voiced/ \\
        --old shelf-now/ --into to-ship/ [--hold]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from targum.dialogue.models import Dialogue  # noqa: E402

POINTS = re.compile("[֑-ׇ]")


FINALS = str.maketrans("ךםןףץ", "כמנפצ")


def said(text: str) -> list[str]:
    """The words as sounds, near enough: no points, no punctuation, and no yod or vav in
    the middle of a word, where they are spelling. First and last letters stay."""
    words = re.sub(r"[^\u05d0-\u05ea ]", " ", POINTS.sub("", text).translate(FINALS)).split()
    return [w if len(w) < 3 else w[0] + re.sub("[וי]", "", w[1:-1]) + w[-1] for w in words]


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--scenes", type=Path, required=True, help="the corrected scene files")
    parser.add_argument("--voiced", type=Path, required=True, help="voice_scenes.py's --into")
    parser.add_argument("--old", type=Path, required=True, help="the shelf as it is: JSON + mp3")
    parser.add_argument("--into", type=Path, required=True)
    parser.add_argument(
        "--hold", action="store_true", help="keep a re-worded, unvoiced scene as it is in --old"
    )
    args = parser.parse_args()

    if args.into.exists() and any(args.into.iterdir()):
        sys.exit(f"{args.into} is not empty; a staged shelf is written whole or not at all.")

    placed: list[tuple[str, dict]] = []
    new = kept = 0
    refused: list[str] = []
    for path in sorted(args.scenes.glob("*.json")):
        scene = json.loads(path.read_text(encoding="utf-8"))
        sid = scene["id"]
        mp3 = args.voiced / f"{sid}.mp3"
        spans_file = args.voiced / f"{sid}.spans.json"
        if mp3.exists() and spans_file.exists():
            spans = json.loads(spans_file.read_text(encoding="utf-8"))
            if len(spans) != len(scene["turns"]):
                sys.exit(f"{sid}: {len(spans)} spans for {len(scene['turns'])} turns")
            for turn, (start, end) in zip(scene["turns"], spans, strict=True):
                turn["start"], turn["end"] = start, end
            scene["audio"] = f"{sid}.mp3"
            placed.append((sid, {"json": scene, "mp3": mp3}))
            new += 1
            continue
        before = json.loads((args.old / f"{sid}.json").read_text(encoding="utf-8"))
        moved = [
            n
            for n, (a, b) in enumerate(zip(scene["turns"], before["turns"], strict=True))
            if said(a["text"]) != said(b["text"])
        ]
        if moved:
            refused.append(f"{sid} (turns {', '.join(map(str, moved))})")
            if args.hold:
                placed.append((sid, {"json": before, "mp3": args.old / f"{sid}.mp3"}))
            continue
        placed.append((sid, {"json": scene, "mp3": args.old / f"{sid}.mp3"}))
        kept += 1

    if refused and not args.hold:
        sys.exit(
            "changed letters and no new audio, so the old audio says the old word:\n  "
            + "\n  ".join(refused)
        )

    args.into.mkdir(parents=True, exist_ok=True)
    for sid, held in placed:
        text = json.dumps(held["json"], ensure_ascii=False, indent=2) + "\n"
        Dialogue.model_validate_json(text)
        (args.into / f"{sid}.json").write_text(text, encoding="utf-8")
        shutil.copyfile(held["mp3"], args.into / f"{sid}.mp3")
    print(f"{len(placed)} scenes into {args.into}: {new} newly voiced, {kept} kept their audio")
    if refused:
        print(f"{len(refused)} held as they were, until their words are voiced:")
        print("  " + "\n  ".join(refused))


if __name__ == "__main__":
    main()
