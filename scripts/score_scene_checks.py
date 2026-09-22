"""Score the free checks against the judgements a person actually made.

`dialogue/checks.py` claims to catch things. This says how many, against the 275
corrections David settled one by one on 2026-09-22 — the only Hebrew gold targum owns
that was marked by hand rather than by another model (targum-internal#351 item 2).

Two numbers come out, and the second matters more than the first:

- **recall**: of the gold errors, how many the free checks find. It will be low. Most
  of the 275 are a wrong vowel in a word that is spelled correctly, and no rule decides
  those — that is what the paid reading is for.
- **findings not in the gold**: each is either a real error two model readings and a
  person all missed, or a false positive. A check that produces these in quantity is a
  check that will be ignored, which is worse than a check that finds nothing.

    python3 scripts/score_scene_checks.py --scenes ~/…/dialogues --gold …/decisions.json
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from targum.dialogue.checks import (  # noqa: E402
    bare,
    check_turn,
    inconsistent_pointing,
)


def gold_from(path: Path) -> set[tuple[str, int, str]]:
    """The settled corrections, as (scene, turn, the word's consonants).

    Matched on consonants because a judgement quotes the word as it was pointed and a
    check quotes it as it stands; they are the same word.
    """
    out = set()
    for one in json.loads(path.read_text(encoding="utf-8")):
        if one.get("turn") is None or not one.get("word"):
            continue
        out.add((one["scene"], int(one["turn"]), bare(one["word"])))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--scenes", type=Path, required=True, help="the scenes as they were")
    parser.add_argument("--gold", type=Path, required=True, help="decisions.json")
    parser.add_argument("--show", type=int, default=40, help="how many findings to print")
    args = parser.parse_args()

    files = sorted(args.scenes.expanduser().glob("*.json"))
    if not files:
        sys.exit(f"No scenes in {args.scenes}.")
    gold = gold_from(args.gold.expanduser())

    found: list[tuple[str, int, str, str, str]] = []
    lines_by_scene: dict[str, list[str]] = {}
    turns = 0
    for path in files:
        scene = json.loads(path.read_text(encoding="utf-8"))
        sid = scene["id"]
        cast = scene.get("cast") or {}
        lines_by_scene[sid] = [t["text"] for t in scene["turns"]]
        for n, turn in enumerate(scene["turns"]):
            turns += 1
            other = "B" if turn.get("who") == "A" else "A"
            addressee = (cast.get(other) or {}).get("gender", "")
            for one in check_turn(turn["text"], turn.get("english", ""), n, addressee, sid):
                found.append((sid, n, bare(one.word), one.kind, one.what))

    print(f"{len(files)} scenes, {turns} turns")
    print(f"gold: {len(gold)} settled corrections\n")

    def matches(one: tuple[str, int, str, str, str]) -> tuple[str, int, str] | None:
        """The gold entry this finding is about, if any.

        Not an equality: a judgement quotes what a person decided about — sometimes a
        phrase, `אֶחָד לְמֵאָה` — and a check quotes what it can point at, sometimes the
        whole line. Either containing the other is the same finding, and a finding with
        no word at all is about the turn.
        """
        sid, turn, word = one[0], one[1], one[2]
        for key in gold:
            if key[0] != sid or key[1] != turn:
                continue
            if not word or word in key[2] or key[2] in word:
                return key
        return None

    hit = [f for f in found if matches(f)]
    miss = [f for f in found if not matches(f)]
    caught = {k for f in found if (k := matches(f))}

    print(f"the free checks raised {len(found)} findings")
    print(
        f"  {len(caught)} are gold errors  -> recall {100 * len(caught) / max(len(gold), 1):.1f}%"
    )
    print(f"  {len(miss)} are not in the gold")

    kinds = collections.Counter(f[3] for f in hit)
    print(f"\ncaught, by kind: {dict(kinds)}")

    if miss:
        print("\nnot in the gold — each is a real error nobody found, or a false positive:")
        for sid, n, word, kind, what in miss[: args.show]:
            print(f"  {sid} t{n} [{kind}] {word or '(line)'}: {what}")
        if len(miss) > args.show:
            print(f"  … and {len(miss) - args.show} more")

    clashes = inconsistent_pointing(lines_by_scene)
    print(f"\n{len(clashes)} words the corpus points more than one way:")
    for row in clashes[: args.show]:
        print(f"  {row}")
    if len(clashes) > args.show:
        print(f"  … and {len(clashes) - args.show} more")


if __name__ == "__main__":
    main()
