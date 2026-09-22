"""A Russian rendering for every hand-written scene, drafted once for a person to read.

New accounts open on Scene 1, so the scenes are the first Hebrew many readers meet and
their translation is the first English — or, for an olah, the first thing targum gets
wrong. `dialogue/models.py` carried an `english` field and nothing else (see
targum-internal#288).

**Authored, not bought at build time.** A scene's English is written with the scene
because a dialogue is authored; its Russian is the same kind of thing, so it is carried
in the scene file and reviewed before it ships. The alternative — letting the ordinary
translation path buy it during a build — would work and would put a hundred unreviewed
renderings in front of every new Russian account, with the receipt in a cache nobody
reads.

**It never writes where the scenes live.** `--into` is a directory of its own and the
default is beside this script's output, not the corpus: applying a draft is a separate
act by a person who has read it. `--apply` is deliberately not a flag.

**Translated from the English, not from the Hebrew**, for the reason
`russian_titles.py` gives: the English is the considered rendering, a person wrote it
with the scene, and going back to the Hebrew would re-decide all of it in a second
language and disagree with the first.

    .venv/bin/python scripts/russian_scenes.py --from ~/…/dialogues --dry-run
    set -a && . ./.env && set +a && .venv/bin/python scripts/russian_scenes.py \\
        --from ~/…/dialogues --into ./russian-scenes
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from targum.dialogue.models import Dialogue  # noqa: E402
from targum.usage import Usage  # noqa: E402

#: Scenes a batch. Smaller than the titles script's fifteen: a scene is a title, a
#: sentence and up to forty turns, so one is several times the text of one catalogue row.
BATCH = 4

ASKED = """You are translating scenes from a Hebrew learning app into Russian, for
Russian-speaking learners of Hebrew — most of them olim living in Israel.

Each scene has a title, one sentence saying what happens, and a list of turns. Every
turn has Hebrew and the English a person wrote with the scene.

Translate the English into Russian. The Hebrew is there so you can see what the line
really is; render the English, not the Hebrew, so that the Russian and the English say
the same thing.

How to write it:
- Spoken Russian, the way people actually talk. These are conversations, not captions.
- Keep the register of the English: a scene at a pharmacy is plain, a scene in an office
  is not chatty.
- Keep names as they are: Dana is Дана, Yonatan is Йонатан.
- Keep it the length of the English. A line twice as long is a line that will not fit
  where the English fits.
- No exclamation marks unless the English has one.
- Israeli things keep their Israeli names: ulpan is ульпан, Tnuva is «Тнува».
- **The title is a title and gets translated too.** Handing back the English title
  unchanged is the one mistake to watch for here.

Answer with JSON only: an object whose keys are the scene ids, each holding
{"title": "…", "gloss": "…", "turns": ["…", "…"]} with one Russian string per turn, in
order, the same number of turns as were given. Nothing else."""


def scenes_from(where: Path) -> list[Dialogue]:
    files = sorted(where.glob("*.json"))
    if not files:
        sys.exit(f"No scenes in {where}.")
    return [Dialogue.model_validate(json.loads(p.read_text(encoding="utf-8"))) for p in files]


def asking(batch: list[Dialogue]) -> str:
    return json.dumps(
        {
            scene.id: {
                "title": scene.english,
                "gloss": scene.gloss,
                "turns": [{"hebrew": turn.text, "english": turn.english} for turn in scene.turns],
            }
            for scene in batch
        },
        ensure_ascii=False,
    )


def drafted(client: Any, batch: list[Dialogue], model: str, usage: Usage) -> dict[str, Any]:
    reply = client.messages.create(
        model=model,
        max_tokens=8000,
        system=ASKED,
        messages=[{"role": "user", "content": asking(batch)}],
    )
    usage.add(model, reply.usage.input_tokens, reply.usage.output_tokens)
    said = "".join(getattr(block, "text", "") for block in reply.content).strip()
    if said.startswith("```"):
        said = said.split("\n", 1)[1].rsplit("```", 1)[0]
    return dict(json.loads(said))


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--from", dest="source", type=Path, required=True)
    parser.add_argument(
        "--into",
        type=Path,
        default=Path("russian-scenes"),
        help="where the drafted copies go; never the directory they came from",
    )
    parser.add_argument("--language", default="ru")
    parser.add_argument("--sample", type=int, default=0, help="draft only the first N")
    parser.add_argument("--dry-run", action="store_true", help="say what it would do")
    args = parser.parse_args()

    source = args.source.expanduser().resolve()
    into = args.into.expanduser().resolve()
    if into == source:
        sys.exit("--into must not be where the scenes live: applying a draft is a person's act.")

    scenes = scenes_from(source)
    todo = [s for s in scenes if args.language not in s.said_languages]
    if args.sample:
        todo = todo[: args.sample]
    turns = sum(len(s.turns) for s in todo)
    words = sum(len(t.english.split()) for s in todo for t in s.turns)
    print(f"{len(scenes)} scenes in {source}")
    print(f"{len(todo)} without {args.language}: {turns} turns, about {words} English words")

    if args.dry_run or not todo:
        print("\nNothing was called." if args.dry_run else "\nNothing to draft.")
        return

    import anthropic

    from targum.serve import HOSTED_MODEL

    client = anthropic.Anthropic()
    usage = Usage()
    into.mkdir(parents=True, exist_ok=True)
    done = 0
    untranslated: list[str] = []
    for start in range(0, len(todo), BATCH):
        batch = todo[start : start + BATCH]
        try:
            said = drafted(client, batch, HOSTED_MODEL, usage)
        except Exception as error:  # noqa: BLE001 - one bad batch is not the run
            print(f"  ! batch at {start} failed: {error}", file=sys.stderr)
            continue
        for scene in batch:
            got = said.get(scene.id)
            if not isinstance(got, dict):
                print(f"  ! nothing for {scene.id}", file=sys.stderr)
                continue
            lines = got.get("turns") or []
            if len(lines) != len(scene.turns):
                # A scene with the wrong number of lines is not partly right: the lines
                # would land under the wrong turns, which is worse than no Russian.
                print(
                    f"  ! {scene.id}: {len(lines)} lines for {len(scene.turns)} turns, skipped",
                    file=sys.stderr,
                )
                continue
            title = str(got.get("title") or "").strip()
            if title and title == scene.english.strip():
                # Handed back the English unchanged, which happened to scene 01 on the
                # first sample. Left empty rather than recorded: `name_in` then falls
                # back to the English, which is honest, where a Russian field holding
                # English is a claim that the scene has a Russian name.
                untranslated.append(scene.id)
                title = ""
            scene.named[args.language] = title
            scene.glossed[args.language] = str(got.get("gloss") or "")
            for turn, line in zip(scene.turns, lines, strict=True):
                turn.said[args.language] = str(line)
            # Written as each batch lands, not at the end: a run that dies halfway keeps
            # what it paid for (targum-internal, 2026-09-16 — the first titles run lost
            # 920 rows and its spend to one OOM kill).
            (into / f"{scene.id}.json").write_text(
                scene.model_dump_json(indent=2, exclude_defaults=False) + "\n",
                encoding="utf-8",
            )
            done += 1
        print(f"  {done}/{len(todo)} drafted, ${usage.cost():.2f} so far", flush=True)

    if untranslated:
        print(f"\n{len(untranslated)} titles came back in English and were left empty:")
        for name in untranslated:
            print(f"  {name}")
    print(f"\n{done} scenes drafted into {into}. This run cost ${usage.cost():.2f}.")
    print("Nothing where the scenes live was touched. Read them, then copy them across.")


if __name__ == "__main__":
    main()
