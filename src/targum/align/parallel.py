"""Two texts that are already lined up, paired without asking a model.

Scripture is numbered by verse, and a published translation is numbered the same way. So
when both sides come from a source that hands over verses, the pairing is not something
to infer — it is stated, and the only honest thing to do is copy it down.

That is worth doing for three reasons beyond the obvious saving. It cannot be wrong where
embeddings can. It needs no LaBSE, so a Tanakh builds on a machine that never downloads
1.8 GB of weights. And the length prior the aligner leans on is at its least reliable
exactly here, because pointed Hebrew counts every vowel as a character.

**Parallelism is declared, never guessed.** Two documents are paired only when both name
the same text through a source that promises verse alignment. Deciding it structurally
instead — equal counts, matching kinds — would eventually pair two unrelated texts that
happened to line up, silently, and silence is the failure that matters when the text is
scripture.
"""

from __future__ import annotations

import logging
from typing import Any

from ..errors import TargumError
from ..models import Alignment, BlockKind, Link, SegmentedDocument

LOG = logging.getLogger(__name__)

NAME = "parallel/1"

# Sources whose two sides are numbered the same way by whoever published them. A new one
# joins this by adding a prefix here and nowhere else.
DECLARED = ("sefaria/",)


def parallel_key(document: object) -> str | None:
    """What this document is, if it came from somewhere that pairs by construction.

    Two documents claim to be parallel when their keys match. The language is stripped,
    since that is the one thing the two sides are meant to differ in.
    """
    ingester = str(getattr(document, "ingester", "") or "")
    if not ingester.startswith(DECLARED):
        return None
    source = str(getattr(document, "source", "") or "")
    scheme, _, rest = source.partition(":")
    head, sep, tail = rest.partition(":")
    if sep and len(head) <= 3 and head.isalpha():
        rest = tail
    return f"{scheme.lower()}:{' '.join(rest.split()).lower()}"


def _chapters(segments: list[Any]) -> list[list[Any]]:
    """Split a run of segments into chapters, each starting at its heading.

    Pairing is scoped to the chapter rather than the book, and that is what makes a
    missing verse survivable: a gap can then only ever shift the chapter it is in, and
    only from the gap onwards — never the other hundred and forty-nine.
    """
    out: list[list[Any]] = []
    for segment in segments:
        if segment.kind is BlockKind.heading or not out:
            out.append([])
        out[-1].append(segment)
    return out


def pair(source: SegmentedDocument, target: SegmentedDocument, name: str) -> Alignment:
    """One link per verse, chapter by chapter, at full confidence.

    Where a translation is complete this is exactly 1:1. Where it is not, the gap is
    allowed only in the one place it cannot do harm — see below — and everything else
    raises rather than returning a partial alignment. Reaching here means something has
    already claimed these two are parallel, so a disagreement is a real fault, and
    pairing verse n of one book against verse n+1 of another would be a quiet, durable
    mistranslation of scripture.
    """
    mine, theirs = _chapters(list(source.segments)), _chapters(list(target.segments))
    if len(mine) != len(theirs):
        raise TargumError(
            f"{name}: {len(mine)} chapters against {len(theirs)}.",
            "These two were meant to line up and no longer do. Nothing has been written.",
        )

    links: list[Link] = []
    missing = 0
    for number, (left, right) in enumerate(zip(mine, theirs, strict=True), start=1):
        if len(right) > len(left):
            # The translation claims verses the source does not have. That is not a gap,
            # it is a different numbering, and pairing through it would misalign the rest
            # of the chapter.
            raise TargumError(
                f"{name}, chapter {number}: the translation has {len(right)} units to "
                f"{len(left)} in the source.",
                "A translation cannot have more verses than the text. Nothing written.",
            )
        for here, there in zip(left, right, strict=False):
            if here.kind is not there.kind:
                raise TargumError(
                    f"{name}, chapter {number}: the two sides disagree about a unit.",
                    f"One calls it {here.kind.value}, the other {there.kind.value}. "
                    "Nothing has been written.",
                )
            links.append(Link(source=[here.id], target=[there.id], confidence=1.0, coarse=False))

        # Anything left over is untranslated, and it is safe to say so *only* because a
        # short chapter means the tail is missing. Sefaria writes a gap in the middle as
        # an empty verse in place — Psalms 30:7, 41:9 and 73:5 are all like that, and
        # their chapters still count correctly. A genuinely shorter chapter is the end
        # falling off, which shifts nothing before it. Silverstein's Psalm 82 has seven
        # verses to the Hebrew's eight, and 82:8 simply has no English.
        for orphan in left[len(right) :]:
            missing += 1
            links.append(Link(source=[orphan.id], target=[], confidence=0.0, coarse=False))

    if missing:
        LOG.info("%s: %d verses have no translation in this edition", name, missing)

    from .base import length_ratio

    ratio = length_ratio(
        [segment.text for segment in source.segments],
        [segment.text for segment in target.segments],
    )

    return Alignment(
        name=name,
        document_hash=source.document_hash,
        translation_hash=target.document_hash,
        source_language=source.language,
        target_language=target.language,
        aligner=NAME,
        length_ratio=round(ratio, 4),
        links=links,
    )
