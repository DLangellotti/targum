"""Read every scene's Hebrew closely and say what is wrong with it.

The scenes are hand-authored and are the first Hebrew a new account meets, so an error
in one is met by everybody. Two of them were found by pattern-matching on 2026-09-22 —
a male speaker called כָּנָה, and אִתָּה where אַתָּה was meant — and finding those two
established that pattern-matching is not the instrument. It has no lemmatiser, it knows
thirty-seven forms, and it cannot read.

**What this asks for, and what it refuses to ask for.** Errors only: a form that
disagrees with the cast, pointing that is wrong for the word, a spelling slip, a Hebrew
line and an English line that do not say the same thing. Not register, not word choice,
not "this could be more natural" — a hundred scenes' worth of taste is noise, and noise
is what stops somebody reading the list.

**Every finding must quote the word it is about.** A finding that cannot be located is a
finding nobody can act on, and one that quotes a word not in the line is a finding that
was invented; both are dropped here rather than passed on.

It spends. `--dry-run` prices it and calls nothing.

    .venv/bin/python scripts/audit_scenes.py --from ~/…/dialogues --dry-run
    set -a && . ./.env && set +a && .venv/bin/python scripts/audit_scenes.py \\
        --from ~/…/dialogues --out findings.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from targum.dialogue.models import Dialogue  # noqa: E402
from targum.usage import Usage  # noqa: E402

#: Scenes a call. Two, so the model has room to read every line of both rather than
#: skim eight. This is the opposite trade from the drafting scripts.
BATCH = 2

#: The kinds of finding worth having. Anything else the model volunteers is dropped.
KINDS = ("gender", "nikkud", "spelling", "mismatch", "grammar")

ASKED = """You are proofreading hand-written Hebrew dialogues for a Hebrew learning app.
These scenes are the first Hebrew a new learner meets, so an error in one is met by
everybody.

For each scene you are given the cast — who each speaker is and whether they are a man
or a woman — the level, and every turn with its Hebrew and the English written beside it.

Report **errors only**, of these kinds:

- "gender": a verb, adjective or pronoun whose form disagrees with the declared gender of
  the person speaking or the person being addressed. Hebrew's first-person past is
  gender-neutral (באתי), so it never disagrees; the present tense and adjectives do.
  **Generic or impersonal "you" takes the masculine in Hebrew and is not an error.**
- "nikkud": pointing that is wrong for the word — a wrong vowel, a missing or spurious
  dagesh, a mappiq where none belongs. A mappiq in a final ה (אוֹתָהּ, לָהּ) is correct.
- "spelling": a letter wrong, missing or doubled; a word that is not a word.
- "mismatch": the Hebrew and the English do not say the same thing. Not a loose or
  idiomatic rendering — a real difference in meaning, a missing clause, a wrong number.
- "grammar": agreement, construct state, preposition or word order that is wrong. Not
  unusual: wrong.

Do NOT report register, style, word choice, naturalness, or anything you would phrase as
"could be better". Only what a careful Hebrew speaker would call a mistake.

Answer with JSON only:
{"<scene id>": [{"turn": <index from 0>, "kind": "<one of the kinds>",
  "word": "<the exact word or phrase from the Hebrew line, copied character for
  character>", "what": "<one sentence>", "fix": "<the corrected word or phrase>"}]}

A scene with nothing wrong gets an empty list. Quote the word exactly as it appears,
with its pointing. Nothing else in the answer."""


def asking(batch: list[Dialogue]) -> str:
    return json.dumps(
        {
            scene.id: {
                "level": scene.level,
                "cast": {
                    side: {
                        "name": getattr(scene.cast, side).name or side,
                        "gender": getattr(scene.cast, side).gender,
                    }
                    for side in ("A", "B")
                },
                "turns": [
                    {
                        "turn": n,
                        "who": turn.who,
                        "hebrew": turn.text,
                        "english": turn.english,
                    }
                    for n, turn in enumerate(scene.turns)
                ],
            }
            for scene in batch
        },
        ensure_ascii=False,
    )


def read(client: Any, batch: list[Dialogue], model: str, usage: Usage) -> dict[str, Any]:
    reply = client.messages.create(
        model=model,
        # A scene with a dozen findings fills 8000 and comes back truncated mid-string,
        # which loses the whole batch rather than one finding. Two batches went that way
        # on the first pass over these hundred.
        max_tokens=16000,
        system=ASKED,
        messages=[{"role": "user", "content": asking(batch)}],
    )
    usage.add(model, reply.usage.input_tokens, reply.usage.output_tokens)
    said = "".join(getattr(block, "text", "") for block in reply.content).strip()
    if said.startswith("```"):
        said = said.split("\n", 1)[1].rsplit("```", 1)[0]
    return dict(json.loads(said))


POINTS = re.compile(r"[֑-ׇ]")


def bare(text: str) -> str:
    return POINTS.sub("", text)


def kept(scene: Dialogue, findings: Any) -> list[dict[str, Any]]:
    """The findings that can be located in the scene they are about.

    A finding is dropped where its turn does not exist, its kind is not one that was
    asked for, or the word it quotes is not in that line — unpointed, because a model
    re-pointing a word while quoting it is the likeliest harmless difference and the
    consonants are what identify it. What is left is a list somebody can act on without
    checking whether each row is real first.
    """
    out = []
    for one in findings if isinstance(findings, list) else []:
        if not isinstance(one, dict):
            continue
        n = one.get("turn")
        if not isinstance(n, int) or not 0 <= n < len(scene.turns):
            continue
        if str(one.get("kind")) not in KINDS:
            continue
        word = str(one.get("word") or "").strip()
        if not word or bare(word) not in bare(scene.turns[n].text):
            continue
        out.append(
            {
                "scene": scene.id,
                "turn": n,
                "who": scene.turns[n].who,
                "kind": one["kind"],
                "word": word,
                "what": str(one.get("what") or ""),
                "fix": str(one.get("fix") or ""),
                "hebrew": scene.turns[n].text,
                "english": scene.turns[n].english,
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--from", dest="source", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("scene-findings.json"))
    parser.add_argument("--model", default="claude-opus-5", help="the reader")
    parser.add_argument("--sample", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    files = sorted(args.source.expanduser().glob("*.json"))
    if not files:
        sys.exit(f"No scenes in {args.source}.")
    scenes = [Dialogue.model_validate(json.loads(p.read_text(encoding="utf-8"))) for p in files]
    if args.sample:
        scenes = scenes[: args.sample]
    turns = sum(len(s.turns) for s in scenes)
    print(f"{len(scenes)} scenes, {turns} turns, read {BATCH} at a time by {args.model}")
    if args.dry_run:
        print("\nNothing was called. Drop --dry-run to run it.")
        return

    import anthropic

    client = anthropic.Anthropic()
    usage = Usage()
    found: list[dict[str, Any]] = []
    dropped = 0
    for start in range(0, len(scenes), BATCH):
        batch = scenes[start : start + BATCH]
        try:
            said = read(client, batch, args.model, usage)
        except Exception as error:  # noqa: BLE001 - one bad batch is not the run
            print(f"  ! batch at {start} failed: {error}", file=sys.stderr)
            continue
        for scene in batch:
            raw = said.get(scene.id)
            good = kept(scene, raw)
            dropped += (len(raw) if isinstance(raw, list) else 0) - len(good)
            found.extend(good)
        # Written as it goes, so a run that dies keeps what it paid for.
        args.out.write_text(
            json.dumps(found, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"  {min(start + BATCH, len(scenes))}/{len(scenes)} read, "
            f"{len(found)} findings, ${usage.cost():.2f}",
            flush=True,
        )

    kinds: dict[str, int] = {}
    for one in found:
        kinds[one["kind"]] = kinds.get(one["kind"], 0) + 1
    print(f"\n{len(found)} findings across {len({o['scene'] for o in found})} scenes")
    for kind, count in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"  {count:>4}  {kind}")
    if dropped:
        print(f"\n{dropped} dropped: the word quoted was not in the line it named.")
    print(f"\nWritten to {args.out}. This run cost ${usage.cost():.2f}.")


if __name__ == "__main__":
    main()
