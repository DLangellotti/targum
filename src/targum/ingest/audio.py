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

#: A clip's caption, beside the recording: what the author typed under a reel or a TikTok
#: (targum-internal#158, rule 7 — "a clip's text is its transcript; the caption the author
#: typed is a separate item's text, drawn under the video"). Written by the build from what
#: the door said; absent for every other recording, whose documents are unchanged by it.
CAPTION = "caption.txt"

#: Where a caption's blocks are numbered: a range of its own past every part's, so no
#: part's growth moves it and it never falls inside a part's reserved range.
CAPTION_PART = MAX_PARTS + 1

#: What a caption block's `ref` starts with, which is how the post's manifest finds them.
CAPTION_REF = "caption"


def refined_path(workspace: Path, number: int) -> Path:
    return workspace / REFINED / f"part-{number:03d}.json"


def transcript_path(workspace: Path, number: int) -> Path:
    return workspace / TRANSCRIPTS / f"part-{number:03d}.json"


def waiting_ref(number: int) -> str:
    return f"part {number}:waiting"


def write_caption(workspace: Path, caption: str) -> None:
    """Keep a clip's caption beside its recording, for `load` to read. Only when it has
    changed, so an unchanged caption leaves the file and its hash where they were."""
    from ..paths import write_atomic

    target = workspace / CAPTION
    text = caption.strip() + "\n"
    try:
        if target.read_text(encoding="utf-8") == text:
            return
    except OSError:
        pass
    workspace.mkdir(parents=True, exist_ok=True)
    write_atomic(target, text)


def caption_of(workspace: Path) -> list[str]:
    """The kept caption's lines, or [] where the recording has none."""
    from .post import lines_of

    try:
        return lines_of((workspace / CAPTION).read_text(encoding="utf-8"))
    except OSError:
        return []


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
            raise TargumError("That recording is over 12 hours. Try a shorter one.")

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

        # The caption the author typed, after the transcript: under the film, as its own
        # item's text. After, never before — a paragraph above the first part's heading
        # would be body text, and a heading after body text opens a new page, which
        # would put the transcript the film follows on a page of its own.
        caption = caption_of(workspace)
        for n, line in enumerate(caption):
            blocks.append(
                Block(
                    id=audio_block_id(CAPTION_PART, n),
                    kind=BlockKind.paragraph,
                    text=line,
                    ref=f"{CAPTION_REF}:{n + 1}",
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
        # And the caption, only where there is one: every recording without one keeps
        # the hash it always had, and is not read as changed.
        document.source_hash = content_hash(
            found.sha256,
            found.title,
            found.artist,
            json.dumps(heard, sort_keys=True),
            *(["\n".join(caption)] if caption else []),
        )
        return document
