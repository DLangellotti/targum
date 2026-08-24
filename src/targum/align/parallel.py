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

from ..errors import TargumError
from ..models import Alignment, Link, SegmentedDocument

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


def pair(source: SegmentedDocument, target: SegmentedDocument, name: str) -> Alignment:
    """One link per segment, in order, at full confidence.

    Raises rather than returning a partial alignment. Reaching here means something has
    already claimed these two are parallel, so a disagreement is a real fault — the
    edition changed underneath us, or the claim was wrong — and either way pairing verse
    n of one book against verse n+1 of another would be a quiet, durable mistranslation
    of scripture. Refusing to build is the smaller harm by a long way.
    """
    if len(source.segments) != len(target.segments):
        raise TargumError(
            f"{name}: {len(source.segments)} segments against {len(target.segments)}.",
            "These two were meant to line up verse for verse and no longer do. "
            "The edition may have changed; nothing has been written.",
        )

    for index, (left, right) in enumerate(zip(source.segments, target.segments, strict=True)):
        if left.kind is not right.kind:
            raise TargumError(
                f"{name}: the two sides disagree about what unit {index + 1} is.",
                f"One calls it {left.kind.value}, the other {right.kind.value}. "
                "Nothing has been written.",
            )

    # Descriptive rather than load-bearing — nothing here consults it — but recorded
    # honestly so an artifact from this path can be read beside one the aligner made.
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
        links=[
            # Confidence 1.0 is not flattery. It is not a similarity estimate at all:
            # it is the publisher's own numbering, and marking it lower would have the
            # reader shown an approximation warning over a certainty.
            Link(source=[left.id], target=[right.id], confidence=1.0, coarse=False)
            for left, right in zip(source.segments, target.segments, strict=True)
        ],
    )
