"""Repair a recording reader whose parts never stop (targum-internal#727). One-off.

Two shapes, both found on the box on 2026-11-14:

- A subtitle reader written before #727 (`subtitles/1`): its paragraphs are redrawn at
  sentence ends (`--redraw`, free) and its refiner set back to fresh, so the build
  below buys its full stops where it is sparse (`ingest.subtitles.owes_punctuation`).
- A whisper reader refined before #261 (`rules/1`, `rules/2`): the build below redoes
  it with the punctuating rules from the hearing kept beside each part. Never heard
  again.

Either way the named parts are then rebuilt the way a part press is
(`Library.run_part`): Sonnet, owner's cache scope, words on, no glossing. Their
sentences change, so their English is bought again. Without `--spend` it prints what
it would buy and writes nothing at all.

Run on the box as the service user, never as root:

    systemd-run --uid=targum --gid=targum --pipe --wait --quiet \\
      -p EnvironmentFile=/etc/targum/targum.env -p WorkingDirectory=/srv/targum \\
      /srv/targum/.local/share/uv/tools/targum/bin/python -I /srv/targum/repair_unpunctuated.py \\
      --folder /var/lib/targum/targums/p1/hk11qvyhwqu-he \\
      --source https://www.youtube.com/watch?v=HK11qVyHwQU --parts 1 2 --redraw [--spend]
"""

from __future__ import annotations

import argparse
import math
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from targum.transcribe.models import Refined

if TYPE_CHECKING:
    from targum.pipeline import Build


def redrawn(folder: Path) -> dict[int, Refined]:
    """Every `subtitles/1` part, its paragraphs drawn again and its refiner made fresh."""
    from targum.ingest.subtitles import FRESH, drawn
    from targum.transcribe.models import load

    out: dict[int, Refined] = {}
    for path in sorted((folder / "audio" / "refined").glob("part-*.json")):
        kept = load(Refined, path)
        if kept is None or kept.provider != "subtitles":
            continue
        names = kept.refiner.split("+")
        if names[0] != "subtitles/1":
            continue
        words = [word for paragraph in kept.paragraphs for word in paragraph.words]
        out[int(path.stem.split("-")[1])] = kept.model_copy(
            update={"refiner": "+".join([FRESH, *names[1:]]), "paragraphs": drawn(words)}
        )
    return out


def write_redrawn(folder: Path, parts: dict[int, Refined]) -> None:
    """Written down, after a copy of the refined files is kept in `refined.pre727`."""
    from targum.ingest.audio import refined_path
    from targum.transcribe.models import write

    backup = folder / "audio" / "refined.pre727"
    if not backup.exists():
        shutil.copytree(folder / "audio" / "refined", backup)
    for number, refined in parts.items():
        write(refined_path(folder / "audio", number), refined)


def builder(folder: Path, source: str, owner: str) -> Build:
    """The build a part press makes (`Library._builder`), for this folder."""
    from targum.annotate.gloss import GLOSS_MODEL
    from targum.models import Style
    from targum.pipeline import Build
    from targum.serve import HOSTED_MODEL

    build = Build(
        source,
        target_language="en",
        source_language="he",
        style=Style.natural,
        model=HOSTED_MODEL,
        owner=owner,
        out_root=folder.parent,
        gloss=False,
        gloss_model=GLOSS_MODEL,
        difficulty=True,
    )
    build._resolved_out = folder
    build.notify = print
    return build


def main() -> None:
    from targum.audio import SPEECH_WORDS_PER_MINUTE, TOKENS_PER_SPOKEN_WORD, WORDS_PER_SENTENCE
    from targum.audio import parts as parts_module
    from targum.serve import FIRST_CHAPTERS

    ask = argparse.ArgumentParser()
    ask.add_argument("--folder", type=Path, required=True)
    ask.add_argument("--source", required=True)
    ask.add_argument("--parts", type=int, nargs="+", required=True)
    ask.add_argument("--owner", default="p1")
    ask.add_argument("--redraw", action="store_true")
    ask.add_argument("--spend", action="store_true")
    args = ask.parse_args()

    from targum.ingest.subtitles import owes_punctuation

    fresh = redrawn(args.folder) if args.redraw else {}
    print("parts redrawn:", sorted(fresh))
    build = builder(args.folder, args.source, args.owner)
    punctuator = getattr(build._refiner(), "punctuator", None)
    assert punctuator is not None, "no key in the environment: nothing could be marked"
    workspace = args.folder / "audio"
    owed = [
        n
        for n in args.parts
        if (owes_punctuation(fresh[n]) if n in fresh else build._needs_hearing(workspace, n))
    ]
    drafted = parts_module.load(workspace)
    assert drafted is not None
    seconds = {span.number: span.end - span.start for span in drafted.parts}
    marks = sum(seconds[n] for n in owed) / 60 * punctuator.dollars_per_minute()
    words = sum(seconds[n] for n in args.parts) / 60 * SPEECH_WORDS_PER_MINUTE
    batches = max(1, math.ceil(words / WORDS_PER_SENTENCE / 20))
    english = build.provider.estimate_from_counts(words * TOKENS_PER_SPOKEN_WORD, batches)
    print(f"marks owed for parts {owed}: about ${marks:.3f}")
    print(f"English for parts {args.parts}: about ${english:.3f}")
    if not args.spend:
        print("dry run: nothing written, nothing bought. Add --spend to rebuild.")
        return
    if fresh:
        write_redrawn(args.folder, fresh)
    result = build.run(chapters=FIRST_CHAPTERS, also=args.parts)
    print(f"spent ${result.spent.cost():.4f}")


if __name__ == "__main__":
    main()
