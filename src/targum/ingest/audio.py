"""A recording as a Document: what has been heard so far, and where the rest will go.

The document grows as parts are transcribed, which is exactly the case every other
ingester never meets, and two rules keep the growth safe. Block ids are reserved per
part (`ids.audio_block_id`), so text arriving in part two moves nothing in part nine.
And the source hash states which parts have been heard, so a grown document reads as
"the file changed" — never as a hand edit the pipeline must preserve.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..audio import DEFAULT_LANGUAGE  # noqa: F401  (import cycle guard)
from ..audio import parts as parts_module
from ..audio import probe as probe_module
from ..errors import TargumError
from ..ids import MAX_PARTS, audio_block_id, content_hash
from ..models import Block, BlockKind, Document
from ..transcribe.models import Refined, load
from .base import build_document

REFINED = "refined"
TRANSCRIPTS = "transcripts"


def refined_path(workspace: Path, number: int) -> Path:
    return workspace / REFINED / f"part-{number:03d}.json"


def transcript_path(workspace: Path, number: int) -> Path:
    return workspace / TRANSCRIPTS / f"part-{number:03d}.json"


def waiting_ref(number: int) -> str:
    return f"part {number}:waiting"


class AudioIngester:
    # /2: part headings lead with the part's name in the text's own language rather
    # than a bare clock range. A version bump re-ingests — free — so texts already
    # built pick the new headings up on their next build.
    name = "audio/2"

    def load(self, source: str) -> Document:
        path = Path(source)
        workspace = path.parent
        found = probe_module.load(workspace)
        if found is None:
            # Called on a bare file — `targum fetch talk.mp3` — rather than through a
            # build that adopted it. Probe it here, in place, so the two entrances
            # answer the same way.
            found = probe_module.examine(path)
        plan = parts_module.load(workspace)
        if plan is None:
            plan = parts_module.plan(found)
        if len(plan.parts) > MAX_PARTS:
            raise TargumError("That recording is over 12 hours.")

        refinements: dict[int, Refined] = {}
        for part in plan.parts:
            kept = load(Refined, refined_path(workspace, part.number))
            if kept is not None:
                refinements[part.number] = kept

        blocks: list[Block] = []
        language_hint = plan.language or DEFAULT_LANGUAGE
        # The tag's own title first. The fallbacks are file names, which are slugs:
        # they get their hyphens and their language suffix taken off, because a title
        # is the first thing on the page and a slug is not a title anybody chose.
        raw = path.parent.parent.name if workspace.name == "audio" else path.stem
        if raw.endswith(f"-{language_hint}"):
            raw = raw[: -len(language_hint) - 1]
        title = found.title or " ".join(raw.replace("-", " ").replace("_", " ").split())
        blocks.append(Block(id=audio_block_id(0, 0), kind=BlockKind.heading, level=1, text=title))
        if found.artist:
            blocks.append(Block(id=audio_block_id(0, 1), kind=BlockKind.byline, text=found.artist))

        for part in plan.parts:
            heading = parts_module.heading_for(part, language_hint)
            blocks.append(
                Block(
                    id=audio_block_id(part.number, 0),
                    kind=BlockKind.heading,
                    level=2,
                    text=heading,
                    ref=f"part {part.number}",
                )
            )
            refined = refinements.get(part.number)
            if refined is None:
                # A placeholder with body in it, twice over: `split_sections` opens the
                # next section only past body text, and the segmenter must find a
                # sentence here — its clock is one, an ellipsis is not.
                blocks.append(
                    Block(
                        id=audio_block_id(part.number, 1),
                        kind=BlockKind.paragraph,
                        text=f"{parts_module.hms(part.start)}–{parts_module.hms(part.end)}",
                        ref=waiting_ref(part.number),
                    )
                )
                continue
            for n, paragraph in enumerate(refined.paragraphs, start=1):
                blocks.append(
                    Block(
                        id=audio_block_id(part.number, n),
                        kind=BlockKind.paragraph,
                        text=paragraph.text,
                        ref=f"part {part.number}:{n}",
                        speaker=paragraph.speaker or None,
                    )
                )

        language = plan.language or DEFAULT_LANGUAGE
        for refined in refinements.values():
            if refined.language:
                language = refined.language
                break

        document = build_document(
            str(path),
            blocks,
            ingester=self.name,
            language=language,
            title=title,
            author=found.artist or None,
        )
        # Which parts have been heard, and by what. Growth must read as the file having
        # changed — an unchanged source_hash with new text reads as a hand edit, which
        # the pipeline rightly preserves over anything an ingester says.
        heard = {
            str(number): content_hash(refined.provider, refined.refiner, refined.model_dump_json())
            for number, refined in sorted(refinements.items())
        }
        # The tags ride in the hash beside the audio and the refinements: a corrected
        # title is a changed source, or the reconciliation reads the fresh ingest as a
        # hand edit and keeps the old name forever.
        document.source_hash = content_hash(
            found.sha256, found.title, found.artist, json.dumps(heard, sort_keys=True)
        )
        return document
